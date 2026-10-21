"""BK-14 (unit half): booking references `BF-XXXXXX` (glossary §1, spec 02 §3.8, §7.6)."""

import re
from collections.abc import Callable, Iterator

import pytest

from app.modules.bookings.domain.references import (
    MAX_DRAWS,
    REFERENCE_ALPHABET,
    REFERENCE_PATTERN,
    is_booking_reference,
    is_reserved_reference,
    is_seed_reference,
    new_booking_reference,
)

DB_CHECK_PATTERN = r"^BF-[0-9A-HJKMNP-TV-Z]{6}$"  # ck_bookings_reference_format (spec 02 §3.8)


def chooser(characters: str) -> Callable[[str], str]:
    stream: Iterator[str] = iter(characters)

    def choose(alphabet: str) -> str:
        character = next(stream)
        assert character in alphabet
        return character

    return choose


def test_bk14_the_alphabet_is_crockford_base32_without_i_l_o_u() -> None:
    assert len(REFERENCE_ALPHABET) == 32
    assert len(set(REFERENCE_ALPHABET)) == 32
    assert not set("ILOU") & set(REFERENCE_ALPHABET)
    assert REFERENCE_ALPHABET == "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def test_bk14_the_pattern_is_the_database_check_and_matches_exactly_the_alphabet() -> None:
    assert REFERENCE_PATTERN.pattern == DB_CHECK_PATTERN
    for character in map(chr, range(32, 127)):
        accepted = is_booking_reference(f"BF-{character * 6}")
        assert accepted == (character in REFERENCE_ALPHABET), character


@pytest.mark.parametrize(
    "value",
    ["BF-7K2M9Q", "BF-000000", "BF-ZZZZZZ", "BF-SEED07"],
)
def test_well_formed_references(value: str) -> None:
    assert is_booking_reference(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "BF-7K2M9",
        "BF-7K2M9QX",
        "bf-7k2m9q",
        "BF7K2M9Q",
        "PO-7K2M9Q",
        "BF-7K2M9I",
        "BF-7K2M9Q\n",
    ],
)
def test_malformed_references(value: str) -> None:
    assert not is_booking_reference(value)


def test_bk14_new_references_have_the_format_and_vary() -> None:
    drawn = {new_booking_reference() for _ in range(500)}
    assert len(drawn) == 500
    for reference in drawn:
        assert re.fullmatch(DB_CHECK_PATTERN, reference)
        assert not is_reserved_reference(reference)


def test_bk14_a_code_starting_with_seed_is_redrawn() -> None:
    choose = chooser("SEED01" + "SEED02" + "7K2M9Q")
    assert new_booking_reference(choose) == "BF-7K2M9Q"


def test_a_code_merely_containing_seed_is_kept() -> None:
    assert new_booking_reference(chooser("XSEED1")) == "BF-XSEED1"


def test_a_broken_choice_function_fails_loudly_instead_of_looping() -> None:
    choose = chooser("SEED00" * MAX_DRAWS)
    with pytest.raises(RuntimeError, match="reserved 'SEED' prefix"):
        new_booking_reference(choose)


@pytest.mark.parametrize(
    ("value", "reserved", "seed"),
    [
        ("BF-SEED07", True, True),
        ("BF-SEED0X", True, True),
        ("BF-SEEDX", True, False),  # reserved prefix but malformed
        ("BF-7K2M9Q", False, False),
        ("BF-XSEED1", False, False),
    ],
)
def test_seed_references(value: str, reserved: bool, seed: bool) -> None:
    assert is_reserved_reference(value) is reserved
    assert is_seed_reference(value) is seed

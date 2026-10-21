"""INV-20 (domain half): PO numbers `PO-XXXXXX` in the Crockford alphabet, never starting with the
reserved `SEED` prefix (D43, glossary §1, §14)."""

import re
from collections.abc import Iterator

from app.modules.inventory.domain.po_numbers import (
    PO_ALPHABET,
    PO_NUMBER_PATTERN,
    is_po_number,
    is_reserved_po_number,
    new_po_number,
)

# The database's own check (spec 02 §3.16, `ck_purchase_orders_po_number_format`).
DB_FORMAT = re.compile(r"^PO-[0-9A-HJKMNP-TV-Z]{6}$")


def test_inv20_alphabet_is_crockford_base32() -> None:
    assert PO_ALPHABET == "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    assert len(set(PO_ALPHABET)) == 32
    assert not set("ILOU") & set(PO_ALPHABET)


def test_inv20_random_numbers_match_the_database_format() -> None:
    numbers = {new_po_number() for _ in range(2000)}
    assert all(DB_FORMAT.fullmatch(number) for number in numbers)
    assert all(PO_NUMBER_PATTERN.fullmatch(number) for number in numbers)
    assert len(numbers) > 1990  # 32**6 codes: collisions in 2,000 draws are vanishingly rare
    assert not any(is_reserved_po_number(number) for number in numbers)


def test_inv20_a_code_starting_with_seed_is_drawn_again() -> None:
    letters: Iterator[str] = iter("SEED01" + "SEEX01")

    def scripted(_alphabet: str) -> str:
        return next(letters)

    assert new_po_number(scripted) == "PO-SEEX01"


def test_seed_numbers_are_valid_but_reserved() -> None:
    assert is_po_number("PO-SEED01")
    assert is_reserved_po_number("PO-SEED02")
    assert not is_reserved_po_number("PO-4H8K2M")
    for bad in ("PO-SEED0", "po-4h8k2m", "PO-4H8K2I", "XX-4H8K2M", "PO-4H8K2M7"):
        assert not is_po_number(bad)

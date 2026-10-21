"""BK-13 (unit half): registration keys (D35, spec 02 §3.7). The key must never disagree with the
database's own derivation (`ck_vehicles_registration_key`); the DB half is in
`tests/modules/bookings/test_wizard.py`."""

import pytest

from app.modules.bookings.domain.vehicles import (
    REGISTRATION_KEY_PATTERN,
    REGISTRATION_SEPARATORS,
    is_valid_registration_key,
    registration_key,
)


@pytest.mark.parametrize(
    ("number", "key"),
    [
        ("LEA-1234", "LEA1234"),
        ("lea 1234", "LEA1234"),
        ("  Lea-12 34  ", "LEA1234"),
        ("LEA\t1234", "LEA1234"),
        ("lhr-17-a-99", "LHR17A99"),
        ("AB", "AB"),
    ],
)
def test_bk13_same_car_same_key(number: str, key: str) -> None:
    assert registration_key(number) == key
    assert is_valid_registration_key(key)


def test_separators_are_ascii_whitespace_and_hyphen_only() -> None:
    assert frozenset(" \t\n\v\f\r-") == REGISTRATION_SEPARATORS


@pytest.mark.parametrize(
    "number",
    [
        "L",  # one character
        "-- --",  # nothing left
        "LEA_1234",  # underscore
        "LEA.1234",
        "LÉA1234",  # non-ASCII letter stays and fails
        "straße1",  # ß is upper-cased to SS by str.upper(); never here
        "LEA\u20031234",  # a Unicode space is kept (PostgreSQL may or may not strip it)
        "LEA\u00a01234",
        "LEA\x001234",
        "A" * 21,
    ],
)
def test_invalid_numbers_give_invalid_keys(number: str) -> None:
    assert not is_valid_registration_key(registration_key(number))


def test_only_ascii_letters_are_upper_cased() -> None:
    assert registration_key("straße1") == "STRAßE1"
    assert registration_key("ﬁat9") == "ﬁAT9"


def test_the_key_pattern_mirrors_the_database_check() -> None:
    assert REGISTRATION_KEY_PATTERN.pattern == "^[A-Z0-9]{2,20}$"
    assert is_valid_registration_key("A" * 20)
    assert not is_valid_registration_key("A" * 21)
    assert not is_valid_registration_key("lea1234")
    assert not is_valid_registration_key("LEA1234\n")

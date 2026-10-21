"""The project `Phone` type (spec 03 §1.5, D84)."""

import pytest
from pydantic import BaseModel, ValidationError

from app.shared.phone import Phone


class Contact(BaseModel):
    phone: Phone


class OptionalContact(BaseModel):
    phone: Phone | None = None


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("+92 300 1234567", "+923001234567"),  # spec 03 §1.5 example
        ("0300-1234567", "03001234567"),
        ("  +92-42-0000-0101  ", "+924200000101"),  # surrounding whitespace ignored
        ("    +92 300 1234567    ", "+923001234567"),  # padding does not count toward 20
        ("1234567", "1234567"),  # 7 digits, the minimum
        ("+123456789012345", "+123456789012345"),  # 15 digits, the E.164 maximum
        ("+92 300 123 45 67", "+923001234567"),
    ],
)
def test_valid_numbers_are_stored_without_spaces_and_hyphens(raw: str, stored: str) -> None:
    assert Contact(phone=raw).phone == stored


@pytest.mark.parametrize(
    ("raw", "error_type"),
    [
        ("123456", "string_too_short"),  # 6 characters
        ("1 2 3 4 5 6 7 8 9 0 1", "string_too_long"),  # 21 characters, 11 digits
        ("0300-123456a", "string_pattern_mismatch"),  # letter
        ("+92+3001234567", "string_pattern_mismatch"),  # '+' not leading
        ("(0300) 1234567", "string_pattern_mismatch"),  # parentheses
        ("0300\t1234567", "string_pattern_mismatch"),  # inner tab
        ("١٢٣٤٥٦٧", "string_pattern_mismatch"),  # non-ASCII digits
        ("+------", "phone_invalid"),  # separators only
        ("12 34 5-6", "phone_invalid"),  # 6 digits
        ("+1234567890123456", "phone_invalid"),  # 16 digits
    ],
)
def test_invalid_numbers_are_rejected_with_a_specific_code(raw: str, error_type: str) -> None:
    with pytest.raises(ValidationError) as caught:
        Contact(phone=raw)
    assert caught.value.errors()[0]["type"] == error_type


def test_non_strings_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Contact(phone=3001234567)  # type: ignore[arg-type]


def test_optional_phone_accepts_none() -> None:
    assert OptionalContact().phone is None
    assert OptionalContact(phone=None).phone is None


def test_json_schema_documents_the_input_rules() -> None:
    schema = Contact.model_json_schema()["properties"]["phone"]
    assert schema["minLength"] == 7
    assert schema["maxLength"] == 20
    assert schema["pattern"] == r"^\+?[0-9 \-]+$"

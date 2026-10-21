"""The project `Email` type (D62, spec 12 API-12)."""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.shared.email import Email, is_reserved_domain

EMAIL = TypeAdapter(Email)


@pytest.mark.parametrize(
    ("raw", "normalised"),
    [
        ("fatima.owner@bayflow.test", "fatima.owner@bayflow.test"),
        ("Fatima.Owner@BayFlow.TEST", "fatima.owner@bayflow.test"),
        ("  bilal.sa@bayflow.test  ", "bilal.sa@bayflow.test"),
        ("smoke+1760000000@bayflow.test", "smoke+1760000000@bayflow.test"),
        ("ahmed@mail.com", "ahmed@mail.com"),
        ("AHMED@Mail.COM", "ahmed@mail.com"),
    ],
)
def test_valid_addresses_are_accepted_and_lower_cased(raw: str, normalised: str) -> None:
    assert EMAIL.validate_python(raw) == normalised


@pytest.mark.parametrize(
    "raw",
    [
        "not-an-email",
        "missing-domain@",
        "@missing-local.com",
        "two@@bayflow.test",
        "x@example.invalid",
        "x@foo.localhost",
        "x@localhost",
        "spaces in@bayflow.test",
        "a" * 250 + "@bayflow.test",
        "",
    ],
)
def test_invalid_addresses_are_rejected(raw: str) -> None:
    with pytest.raises(ValidationError):
        EMAIL.validate_python(raw)


def test_validation_never_needs_dns() -> None:
    # A syntactically valid address on a domain without mail servers still validates (offline).
    assert EMAIL.validate_python("someone@no-mx-record-domain-bayflow.example") == (
        "someone@no-mx-record-domain-bayflow.example"
    )


def test_json_schema_documents_the_email_format() -> None:
    schema = EMAIL.json_schema()
    assert schema["format"] == "email"
    assert schema["maxLength"] == 254


@pytest.mark.parametrize(
    ("address", "reserved"),
    [
        ("fatima.owner@bayflow.test", True),
        ("x@foo.example", True),
        ("x@example.com", True),
        ("x@mail.example.org", True),
        ("x@foo.invalid", True),
        ("x@host.localhost", True),
        ("ahmed@mail.com", False),
        ("owner@gmail.com", False),
    ],
)
def test_reserved_domains_are_never_mailed(address: str, reserved: bool) -> None:
    assert is_reserved_domain(address) is reserved

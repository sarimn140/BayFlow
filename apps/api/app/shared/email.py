"""The project e-mail type (D62).

`Email` validates with `email_validator.validate_email(value, check_deliverability=False,
test_environment=True)` and lower-cases the whole address. Pydantic's `EmailStr` is not used: it
rejects the reserved `.test` domain of every demo account (glossary §14). `test_environment=True`
permits `test` / `*.test` and skips DNS checks; other special-use names stay rejected.
"""

from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, Field, StringConstraints

MAX_EMAIL_LENGTH = 254  # users.email varchar(254)

# D26: e-mail is never sent to reserved / test names (RFC 2606, RFC 6761).
RESERVED_TLDS = frozenset({"test", "example", "invalid", "localhost"})
RESERVED_DOMAINS = frozenset({"example.com", "example.net", "example.org"})


def normalize_email(value: str) -> str:
    """Validate an address and return its normalised, fully lower-cased form."""
    try:
        result = validate_email(value, check_deliverability=False, test_environment=True)
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
    return result.normalized.lower()


Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=MAX_EMAIL_LENGTH),
    AfterValidator(normalize_email),
    Field(json_schema_extra={"format": "email"}, examples=["fatima.owner@bayflow.test"]),
]
"""A validated, lower-cased e-mail address (use it for every e-mail field in request schemas)."""


def is_reserved_domain(email: str) -> bool:
    """True when the address uses a reserved or test domain that must never receive e-mail (D26)."""
    domain = email.rsplit("@", 1)[-1].strip().lower().rstrip(".")
    if not domain or domain.rsplit(".", 1)[-1] in RESERVED_TLDS:
        return True
    return any(domain == name or domain.endswith(f".{name}") for name in RESERVED_DOMAINS)

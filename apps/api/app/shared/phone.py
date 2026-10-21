"""The project `Phone` type (spec 03 §1.5, D84).

Accepted input: 7 to 20 characters of digits, spaces and hyphens with an optional leading `+`
(surrounding whitespace is ignored). Stored and returned without spaces and hyphens:
`"+92 300 1234567"` → `"+923001234567"`. The normalised number must also hold 7 to 15 digits
(the ITU-T E.164 maximum), so separator-only input such as `"+------"` is rejected instead of
being stored as an empty number.
"""

from typing import Annotated

from pydantic import AfterValidator, StringConstraints
from pydantic_core import PydanticCustomError

MIN_LENGTH = 7
MAX_LENGTH = 20
MIN_DIGITS = 7
MAX_DIGITS = 15  # E.164
PHONE_PATTERN = r"^\+?[0-9 \-]+$"
PHONE_ERROR_MESSAGE = (
    "Enter a phone number of 7 to 15 digits; spaces, hyphens and a leading + are allowed."
)


def normalize_phone(value: str) -> str:
    """Remove spaces and hyphens; require 7 to 15 digits after an optional leading `+`."""
    normalized = value.replace(" ", "").replace("-", "")
    digits = normalized.removeprefix("+")
    if not digits.isdigit() or not MIN_DIGITS <= len(digits) <= MAX_DIGITS:
        raise PydanticCustomError("phone_invalid", PHONE_ERROR_MESSAGE)
    return normalized


Phone = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=MIN_LENGTH,
        max_length=MAX_LENGTH,
        pattern=PHONE_PATTERN,
    ),
    AfterValidator(normalize_phone),
]
"""Use as a field type: `phone: Phone` or `phone: Phone | None = None`."""

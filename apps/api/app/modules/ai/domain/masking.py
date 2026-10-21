"""Personal-data masking before a prompt is sent to a model or stored (spec 13 principle 4, D103).

Masks e-mail addresses, phone numbers, CNICs and (optionally) number plates. Keeps what features
need to reason about: amounts, booking references (`BF-…`), SKUs, dates and years. This is a
backstop: features still send only the fields a task needs.
"""

import re
from typing import Final

_CNIC: Final = re.compile(r"(?<![\d-])\d{5}-\d{7}-\d(?![\d-])")
_EMAIL: Final = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
# A run of digits with optional `+`, spaces or dashes; kept only when it holds 10-13 digits and is
# not a date (`2026-10-09`), so amounts like `16,100` and years never match.
_PHONE_CANDIDATE: Final = re.compile(r"(?<![\w+])\+?\d[\d \-]{8,18}\d(?![\w])")
_DATE: Final = re.compile(r"\d{4}-\d{2}-\d{2}")
# Pakistani plates: 2-3 letters, a dash or space, 3-4 digits (`LEA-1234`, `BKR 482`). The look-ahead
# keeps SKUs such as `TIR-185-65-R15` intact.
_PLATE: Final = re.compile(r"\b[A-Z]{2,3}[- ]\d{3,4}\b(?![-\w])")

# Replacement tokens (not secrets).
EMAIL_TOKEN: Final = "[email]"  # noqa: S105
PHONE_TOKEN: Final = "[phone]"  # noqa: S105
CNIC_TOKEN: Final = "[cnic]"  # noqa: S105
PLATE_TOKEN: Final = "[plate]"  # noqa: S105
PHONE_DIGITS: Final = range(10, 14)  # 10-13 digits: local `03…` to `+92…` and `0092…`


def _phone(match: re.Match[str]) -> str:
    text = match.group(0)
    digits = sum(character.isdigit() for character in text)
    if digits not in PHONE_DIGITS or _DATE.fullmatch(text.strip()):
        return text
    return PHONE_TOKEN


def mask_pii(text: str, *, plates: bool = True) -> str:
    """`text` with personal data replaced by tokens such as `[phone]`."""
    masked = _CNIC.sub(CNIC_TOKEN, text)
    masked = _EMAIL.sub(EMAIL_TOKEN, masked)
    masked = _PHONE_CANDIDATE.sub(_phone, masked)
    if plates:
        masked = _PLATE.sub(PLATE_TOKEN, masked)
    return masked

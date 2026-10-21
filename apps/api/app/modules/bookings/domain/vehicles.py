"""Vehicle registration keys (D35, spec 02 §3.7, `modules/bookings.md` §7.2). Pure.

A customer's vehicle is identified by the normalised registration key, so `lea 1234` and
`LEA-1234` are the same car. The database re-derives the key from the stored number
(`ck_vehicles_registration_key`: `upper(regexp_replace(registration_number, '[[:space:]-]', '',
'g'))` matching `^[A-Z0-9]{2,20}$`), so this function must never disagree with it:

- only the six ASCII whitespace characters and `-` are removed. They are exactly the ASCII
  members of PostgreSQL's `[[:space:]]`, and Unicode spaces (which the database might or might not
  remove, depending on its locale) are left in the key, where they fail the pattern;
- only ASCII letters are upper-cased. Python's `str.upper()` maps characters such as `ß` to
  `SS`, which PostgreSQL's `upper()` does not, so any other character is kept as is and fails the
  pattern.

The request schema therefore accepts a registration number only when its key is valid, which
means the stored number holds nothing but ASCII letters, digits, ASCII whitespace and hyphens.
"""

import re
import string
from typing import Final

__all__ = [
    "REGISTRATION_KEY_PATTERN",
    "REGISTRATION_SEPARATORS",
    "is_valid_registration_key",
    "registration_key",
]

REGISTRATION_KEY_PATTERN: Final = re.compile(r"^[A-Z0-9]{2,20}$")
REGISTRATION_SEPARATORS: Final = frozenset(" \t\n\v\f\r-")
"""Removed from the key: ASCII whitespace (PostgreSQL's `[[:space:]]` for ASCII) and hyphens."""

_ASCII_UPPER: Final = str.maketrans(string.ascii_lowercase, string.ascii_uppercase)


def registration_key(registration_number: str) -> str:
    """The normalised key of a registration number: trimmed, without ASCII whitespace and `-`,
    ASCII letters upper-cased (`"lea 1234"` → `"LEA1234"`). Other characters are kept, so an
    invalid number gives an invalid key."""
    kept = "".join(ch for ch in registration_number.strip() if ch not in REGISTRATION_SEPARATORS)
    return kept.translate(_ASCII_UPPER)


def is_valid_registration_key(key: str) -> bool:
    """2 to 20 characters, each `A`-`Z` or `0`-`9` (`ck_vehicles_registration_key`)."""
    return REGISTRATION_KEY_PATTERN.fullmatch(key) is not None

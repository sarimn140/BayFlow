"""Booking references `BF-XXXXXX` (glossary §1, spec 02 §3.8 and §7.6, `modules/bookings.md` §7.3).

Pure Python. A reference is a human identifier for phone and AI look-ups, never a secret: no
endpoint grants access because the caller knows one (spec 04). Codes are 6 characters of the
Crockford base32 alphabet; random codes never start with `SEED`, which is reserved for the seed's
sample bookings `BF-SEEDnn` (glossary §14, D51).
"""

import re
import secrets
from collections.abc import Callable
from typing import Final

__all__ = [
    "MAX_DRAWS",
    "REFERENCE_ALPHABET",
    "REFERENCE_CODE_LENGTH",
    "REFERENCE_PATTERN",
    "REFERENCE_PREFIX",
    "RESERVED_PREFIX",
    "is_booking_reference",
    "is_reserved_reference",
    "is_seed_reference",
    "new_booking_reference",
]

REFERENCE_ALPHABET: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
"""Crockford base32: digits and upper-case letters without I, L, O and U."""

REFERENCE_PREFIX: Final = "BF-"
REFERENCE_CODE_LENGTH: Final = 6
REFERENCE_PATTERN: Final = re.compile(r"^BF-[0-9A-HJKMNP-TV-Z]{6}$")
"""The same rule as the database's `ck_bookings_reference_format` (spec 02 §3.8)."""

RESERVED_PREFIX: Final = "SEED"
"""Codes starting with `SEED` belong to the seed (`BF-SEED01` …) and are never drawn at random."""

MAX_DRAWS: Final = 100
"""A random code starts with `SEED` with probability 32**-4 (about 1e-6); a hundred redraws in a
row only happen with a broken `choice` function, which then fails loudly instead of looping."""


def new_booking_reference(choice: Callable[[str], str] = secrets.choice) -> str:
    """A fresh `BF-XXXXXX` reference; a code starting with `SEED` is discarded and redrawn.

    `choice` picks one character of the alphabet (tests inject a deterministic one).
    """
    for _ in range(MAX_DRAWS):
        code = "".join(choice(REFERENCE_ALPHABET) for _ in range(REFERENCE_CODE_LENGTH))
        if not code.startswith(RESERVED_PREFIX):
            return REFERENCE_PREFIX + code
    msg = f"no booking reference outside the reserved {RESERVED_PREFIX!r} prefix after {MAX_DRAWS}"
    raise RuntimeError(msg)


def is_booking_reference(value: str) -> bool:
    """`value` is a well-formed reference (`BF-` + 6 Crockford characters)."""
    return REFERENCE_PATTERN.fullmatch(value) is not None


def is_reserved_reference(value: str) -> bool:
    """`value` uses the seed's reserved code prefix (`BF-SEED…`)."""
    return value.startswith(REFERENCE_PREFIX + RESERVED_PREFIX)


def is_seed_reference(value: str) -> bool:
    """A reference the seed may pass to `create_booking` (well-formed **and** reserved)."""
    return is_booking_reference(value) and is_reserved_reference(value)

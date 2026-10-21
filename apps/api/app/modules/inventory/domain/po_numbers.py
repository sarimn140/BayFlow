"""Purchase-order numbers `PO-XXXXXX` (D43, glossary §1, §14; spec 02 §3.16, §7.6).

Six characters of the Crockford base32 alphabet, the same alphabet as booking references. Codes
starting with `SEED` are reserved for seed data (`PO-SEED01`, `PO-SEED02`), so a random code that
starts with it is drawn again (INV-20). Uniqueness per shop is the database's job
(`uq_purchase_orders_shop_id_po_number`); the service retries on a collision.
"""

import re
import secrets
from collections.abc import Callable

PO_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
PO_PREFIX = "PO-"
PO_CODE_LENGTH = 6
RESERVED_PREFIX = "SEED"
PO_NUMBER_PATTERN = re.compile(r"^PO-[0-9A-HJKMNP-TV-Z]{6}$")
"""Mirrors `ck_purchase_orders_po_number_format`."""


def new_po_number(choice: Callable[[str], str] = secrets.choice) -> str:
    """A random `PO-XXXXXX` whose code never starts with the reserved `SEED` prefix."""
    while True:
        code = "".join(choice(PO_ALPHABET) for _ in range(PO_CODE_LENGTH))
        if not code.startswith(RESERVED_PREFIX):
            return PO_PREFIX + code


def is_po_number(value: str) -> bool:
    """True when `value` has the stored format (seed values such as `PO-SEED01` included)."""
    return PO_NUMBER_PATTERN.fullmatch(value) is not None


def is_reserved_po_number(value: str) -> bool:
    """True for the seed's numbers: the code part starts with `SEED`."""
    return value.startswith(PO_PREFIX + RESERVED_PREFIX)

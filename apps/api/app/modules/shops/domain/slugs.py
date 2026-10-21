"""Shop slugs (D68, `modules/shops.md` §7.3). Pure.

A slug is derived once from the shop's name and never changes, so public links stay valid after a
rename. It always matches `ck_shops_slug_format` (`^[a-z0-9]+(-[a-z0-9]+)*$`). On a clash the
next free candidate is used (`base`, `base-2`, `base-3`, …); a name clash is never an error.
"""

import re
import unicodedata
from collections.abc import Collection, Iterator
from itertools import count

SLUG_BASE_MAX_LENGTH = 72  # shops.slug is varchar(80): room for "-" and a 7-digit suffix
FALLBACK_SLUG = "shop"

_NOT_SLUG_CHARACTERS = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """NFKD → ASCII (other characters dropped) → lower case → runs of other characters become `-`
    → trimmed → at most 72 characters; an empty result becomes `shop`.

    "Lahore Auto Care" → `lahore-auto-care`; "Café Ñandú" → `cafe-nandu`; an Urdu-only name →
    `shop`.
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = _NOT_SLUG_CHARACTERS.sub("-", ascii_name.lower()).strip("-")
    slug = slug[:SLUG_BASE_MAX_LENGTH].rstrip("-")
    return slug or FALLBACK_SLUG


def slug_candidates(base: str) -> Iterator[str]:
    """`base`, `base-2`, `base-3`, … (endless)."""
    yield base
    for number in count(2):
        yield f"{base}-{number}"


def free_slug_candidates(base: str, taken: Collection[str]) -> Iterator[str]:
    """The candidates of `base` that are not in `taken`, in order (endless)."""
    return (candidate for candidate in slug_candidates(base) if candidate not in taken)

"""Caller verification by the AI Front Desk (spec 05 §4.2): normalise, then compare only with the
dispatched customer, strongest identifier first. A failed check never reveals a stored value.
"""

import re
import string
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from app.shared.enums import IdentityMethod

_REFERENCE_FIXES: Final = str.maketrans({"O": "0", "I": "1", "L": "1"})
_NON_DIGITS: Final = re.compile(r"\D")
_PUNCTUATION: Final = str.maketrans("", "", string.punctuation)
PHONE_DIGITS: Final = 10


@dataclass(frozen=True, slots=True)
class Claim:
    """What the caller said; at least one field is set."""

    name: str | None = None
    phone: str | None = None
    email: str | None = None
    booking_reference: str | None = None


@dataclass(frozen=True, slots=True)
class Customer:
    """The dispatched customer as stored (never returned on a failed match)."""

    full_name: str
    email: str
    phone: str | None
    references: frozenset[str]  # this customer's bookings at the call's shop


def normalise_reference(value: str) -> str:
    """`b f 7k2m-9q` → `BF-7K2M9Q`; Crockford fixes O→0 and I/L→1 apply to the code part."""
    compact = re.sub(r"[\s\-]", "", value.upper()).removeprefix("BF")
    return f"BF-{compact.translate(_REFERENCE_FIXES)}"


def _phone_key(value: str) -> str | None:
    digits = _NON_DIGITS.sub("", value)
    return digits[-PHONE_DIGITS:] if len(digits) >= PHONE_DIGITS else None


def _words(value: str) -> list[str]:
    return value.lower().translate(_PUNCTUATION).split()


def _within_one_edit(a: str, b: str) -> bool:
    """Levenshtein distance ≤ 1 ("Ahmad" matches "Ahmed")."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) <= 1
    shorter, longer = sorted((a, b), key=len)
    return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))


def _name_matches(claimed: str, full_name: str) -> bool:
    said, stored = _words(claimed), _words(full_name)
    if not said or not stored:
        return False
    return said == stored or _within_one_edit(said[0], stored[0])


def match(claim: Claim, customer: Customer) -> IdentityMethod | None:
    """The method that verified the caller, strongest first, or None."""
    if claim.booking_reference and normalise_reference(claim.booking_reference) in {
        normalise_reference(reference) for reference in customer.references
    }:
        return IdentityMethod.BOOKING_REFERENCE
    if claim.email and claim.email.strip().lower() == customer.email.strip().lower():
        return IdentityMethod.EMAIL
    if claim.phone and customer.phone:
        claimed_key = _phone_key(claim.phone)
        if claimed_key is not None and claimed_key == _phone_key(customer.phone):
            return IdentityMethod.PHONE
    if claim.name and _name_matches(claim.name, customer.full_name):
        return IdentityMethod.NAME
    return None


def first_name(full_name: str) -> str:
    parts = full_name.split(maxsplit=1)
    return parts[0] if parts else full_name


def known_references(values: Iterable[str]) -> frozenset[str]:
    return frozenset(normalise_reference(value) for value in values)

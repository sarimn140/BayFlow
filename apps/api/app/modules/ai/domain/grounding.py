"""Grounding checks: output may state only the facts it was given (AI-43, modules/ai.md).

Used at run time as a guard (`GUARD_BLOCKED`) and by the golden-set harness. The checks are
deliberately simple and conservative: an amount is money in context (`Rs 900`, `16,100 rupees`,
`PKR 5,200`) or a thousands-grouped number that is not a distance; a reference is a booking
reference `BF-XXXXXX` (glossary §1).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Final

_NUMBER: Final = r"\d{1,3}(?:,\d{3})+|\d+"
_MONEY_BEFORE: Final = re.compile(rf"(?:\brs\.?|\bpkr|₨)\s*({_NUMBER})(?:\.00)?\b", re.IGNORECASE)
_MONEY_AFTER: Final = re.compile(rf"\b({_NUMBER})(?:\.00)?\s*(?:rupees|rs\b|pkr\b)", re.IGNORECASE)
_GROUPED: Final = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+)(?:\.00)?(?![\w,])(?!\s*km\b)")
_REFERENCE: Final = re.compile(r"\bBF-?([0-9A-HJKMNP-TV-Z]{6})\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class GroundingFacts:
    """What the feature sent the model: whole-rupee amounts and booking references."""

    amounts: frozenset[int] = field(default_factory=frozenset)
    references: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def of(cls, *, amounts: Iterable[int] = (), references: Iterable[str] = ()) -> "GroundingFacts":
        return cls(frozenset(amounts), frozenset(normalise_reference(ref) for ref in references))


def normalise_reference(value: str) -> str:
    code = value.upper().replace(" ", "").removeprefix("BF").removeprefix("-")
    return f"BF-{code}"


def amounts_in(text: str) -> set[int]:
    found: set[int] = set()
    for pattern in (_MONEY_BEFORE, _MONEY_AFTER, _GROUPED):
        found.update(int(match.group(1).replace(",", "")) for match in pattern.finditer(text))
    return found


def references_in(text: str) -> set[str]:
    return {f"BF-{match.group(1).upper()}" for match in _REFERENCE.finditer(text)}


def texts_of(value: Any) -> list[str]:
    """Every string inside a JSON-like value (a model's `model_dump()`)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in texts_of(item)]
    if isinstance(value, list | tuple):
        return [text for item in value for text in texts_of(item)]
    return []


def ungrounded(output: Any, facts: GroundingFacts) -> list[str]:
    """Statements in `output` that the facts do not support (empty = grounded)."""
    text = "\n".join(texts_of(output))
    invented_amounts = sorted(amounts_in(text) - facts.amounts)
    foreign_references = sorted(references_in(text) - facts.references)
    return [f"amount {amount:,} is not in the facts" for amount in invented_amounts] + [
        f"reference {reference} is not in the facts" for reference in foreign_references
    ]

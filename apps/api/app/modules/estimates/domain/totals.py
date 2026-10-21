"""Estimate money (D41; `modules/estimates.md` §7.5): PKR in whole rupees, `Decimal` only.

Each line total is `quantity x unit_price` rounded **half-up** to whole rupees and kept with two
places (`Decimal("1499.00")`); estimate totals are sums of those rounded line totals. Half-up equals
PostgreSQL's `round(numeric)` for our non-negative values, so `ck_estimate_lines_line_total` always
holds. Python's default half-even rounding is never used for money.

Pure: the pure-domain contract forbids `app.shared.money`, so the one-line rounding rule is
re-implemented here; the unit tests prove it equals `app.shared.money.round_rupees` and the
integration tests prove it equals PostgreSQL's `round()` (EST-25).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Protocol

from app.shared.enums import EstimateLineType

RUPEE = Decimal("1")
CENTS = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_AMOUNT = Decimal("9999999999.00")
"""The largest amount `numeric(12,2)` can hold. Anything above is a 422, never a database 500."""

# Enough significant digits for the exact product of any two amounts this module handles, so the
# multiplication never rounds and `quantize` never traps, whatever the ambient decimal context is.
_PRECISION = 60


class TotalledLine(Protocol):
    """Anything with a line type and a rounded line total (a priced line or a stored line)."""

    @property
    def line_type(self) -> EstimateLineType: ...

    @property
    def line_total(self) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class Totals:
    """The cached totals of one estimate version (`parts_total + labour_total = grand_total`)."""

    parts_total: Decimal
    labour_total: Decimal
    grand_total: Decimal


def line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    """`quantity x unit_price`, rounded half-up to whole rupees, with two places.

    `line_total(Decimal("1.50"), Decimal("999"))` is `Decimal("1499.00")` (half-even would give
    1,498).
    """
    with localcontext(prec=_PRECISION):
        exact = quantity * unit_price
        return exact.quantize(RUPEE, rounding=ROUND_HALF_UP).quantize(CENTS)


def is_too_large(amount: Decimal) -> bool:
    """True when `amount` does not fit `numeric(12,2)` (the overflow guard, D41)."""
    return amount > MAX_AMOUNT


def estimate_totals(lines: Iterable[TotalledLine]) -> Totals:
    """Sum the rounded line totals per type. No lines -> all three totals are `0.00`."""
    parts_total = ZERO
    labour_total = ZERO
    for line in lines:
        if line.line_type == EstimateLineType.PART:
            parts_total += line.line_total
        else:  # EstimateLineType.LABOUR, the only other type
            labour_total += line.line_total
    return Totals(
        parts_total=parts_total,
        labour_total=labour_total,
        grand_total=parts_total + labour_total,
    )

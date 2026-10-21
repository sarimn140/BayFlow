"""Money: PKR in whole rupees (D41, glossary §9, spec 03 §1.5).

Amounts are `Decimal` (never `float`), stored as `numeric(12,2)` that always holds `.00`, and sent
in responses as decimal strings with exactly two places (`"16100.00"`). Requests send a JSON string
(`"6500"` or `"6500.00"`) or an integer, 0 to 9 999 999 999, in whole rupees; anything else is a
422 with the field code `not_whole_rupees`. Line totals are rounded half-up to whole rupees;
Python's default rounding (half-even) must never be used for money.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field, PlainSerializer
from pydantic_core import PydanticCustomError

RUPEE = Decimal("1")
CENTS = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999999")  # numeric(12,2) holds 10 integer digits

_NOT_WHOLE_RUPEES = "not_whole_rupees"


def round_rupees(value: Decimal) -> Decimal:
    """Round half-up to whole rupees, keeping two places: `2498.5` -> `Decimal("2499.00")`."""
    return value.quantize(RUPEE, rounding=ROUND_HALF_UP).quantize(CENTS)


def is_whole_rupees(value: Decimal) -> bool:
    return value.is_finite() and value == value.to_integral_value()


def _without_negative_zero(value: Decimal) -> Decimal:
    """`Decimal("-0")` equals 0 but keeps its sign through `quantize` and prints `"-0.00"`."""
    return value.copy_abs() if value.is_zero() else value


def format_decimal(value: Decimal, places: int = 2) -> str:
    """Plain notation with exactly `places` decimals: `Decimal("1.5")` -> `"1.50"`."""
    rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return f"{_without_negative_zero(rounded):f}"


def format_money(value: Decimal) -> str:
    """The wire form of an amount: `Decimal("16100")` -> `"16100.00"`."""
    return format_decimal(value, 2)


def _accept_string_or_integer(value: object) -> object:
    if isinstance(value, bool | float):
        raise PydanticCustomError(
            _NOT_WHOLE_RUPEES, "Send amounts as a whole number of rupees (a string or an integer)."
        )
    return value


def _require_whole_rupees(value: Decimal) -> Decimal:
    if not is_whole_rupees(value):
        raise PydanticCustomError(_NOT_WHOLE_RUPEES, "Amounts must be whole rupees (no paisa).")
    return _without_negative_zero(value.quantize(CENTS))


Money = Annotated[
    Decimal,
    BeforeValidator(_accept_string_or_integer),
    Field(ge=0, le=MAX_AMOUNT, max_digits=12, decimal_places=2, examples=["16100.00"]),
    AfterValidator(_require_whole_rupees),
    PlainSerializer(format_money, return_type=str, when_used="json"),
]
"""A non-negative whole-rupee amount; JSON output is always a 2-decimal string."""

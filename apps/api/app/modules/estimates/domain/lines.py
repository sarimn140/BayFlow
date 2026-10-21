"""Estimate line rules (D40, D41; `modules/estimates.md` §7.3-§7.5, spec 03 §5.3). Pure.

A `PART` line references an **active** part of the shop's catalogue: it takes the catalogue name
as its description (so an approved estimate never changes when the catalogue is edited), a whole
quantity from 1 to 9 999 and an optional whole-rupee unit price that defaults to the part's
`unit_cost`. A `LABOUR` line is free text x quantity (hours 0.01-999.99, or 1 for a flat fee) x a
required whole-rupee unit price. Totals are always computed here, never taken from a client.

`check_line_shape` is the one statement of the per-line rules: the request schema
(`EstimateLineWrite`) reports its findings as 422 field errors, and `price_lines` re-applies it
before pricing. Every error of every line is collected, so one 422 lists them all (EST-24).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.modules.estimates.domain.totals import (
    CENTS,
    MAX_AMOUNT,
    Totals,
    estimate_totals,
    is_too_large,
    line_total,
)
from app.shared.enums import EstimateLineType

MIN_LINES = 1
MAX_LINES = 50
PART_QUANTITY_MIN = Decimal("1")
PART_QUANTITY_MAX = Decimal("9999")
LABOUR_QUANTITY_MIN = Decimal("0.01")
LABOUR_QUANTITY_MAX = Decimal("999.99")
DESCRIPTION_MAX_LENGTH = 255

# Field error codes (spec 03 §2.3).
MISSING = "missing"
NOT_ALLOWED = "not_allowed"
NOT_WHOLE_RUPEES = "not_whole_rupees"
INVALID_REFERENCE = "invalid_reference"
VALUE_ERROR = "value_error"
STRING_TOO_SHORT = "string_too_short"
STRING_TOO_LONG = "string_too_long"
TOO_SHORT = "too_short"
TOO_LONG = "too_long"

AMOUNT_TOO_LARGE = "The amount is too large."
INACTIVE_OR_UNKNOWN_PART = "Choose an active part from this shop's catalogue."
NUL_NOT_ALLOWED = "Text must not contain NUL characters."


def contains_nul(text: str) -> bool:
    """PostgreSQL text cannot store U+0000 (SQLSTATE 22021): refuse it with a 422, never a 500."""
    return "\x00" in text


@dataclass(frozen=True, slots=True)
class LineInput:
    """One requested line, before pricing (the fields of `EstimateLineWrite`)."""

    line_type: EstimateLineType
    part_id: UUID | None
    description: str | None
    quantity: Decimal
    unit_price: Decimal | None


@dataclass(frozen=True, slots=True)
class CatalogPart:
    """What pricing needs to know about a part of this shop (from inventory, read at save time)."""

    name: str
    unit_cost: Decimal
    is_active: bool


@dataclass(frozen=True, slots=True)
class PricedLine:
    """A validated line, ready to store: `position` is 1-based, totals are whole rupees."""

    position: int
    line_type: EstimateLineType
    part_id: UUID | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


@dataclass(frozen=True, slots=True)
class ShapeError:
    """A rule broken by one line on its own; `field` is the line's field name (`part_id`)."""

    field: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class LineError:
    """A rule broken somewhere in the list; `field` is the body path (`lines.3.part_id`)."""

    field: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class PricingResult:
    """The priced lines and their totals, or every error found (then nothing may be stored)."""

    lines: tuple[PricedLine, ...]
    totals: Totals
    errors: tuple[LineError, ...]


def line_field(index: int, name: str) -> str:
    """The body path of a line field: `line_field(3, "part_id")` -> `"lines.3.part_id"`."""
    return f"lines.{index}.{name}"


def is_whole_rupees(amount: Decimal) -> bool:
    return amount.is_finite() and amount >= 0 and amount == amount.to_integral_value()


def _within(value: Decimal, low: Decimal, high: Decimal) -> bool:
    """A finite value inside `[low, high]`. Checked before anything quantizes the value: on an
    absurd input (`1e30`) `quantize` raises `decimal.InvalidOperation` instead of answering 422."""
    return value.is_finite() and low <= value <= high


def _has_at_most_two_places(value: Decimal) -> bool:
    """Only for a value already bounded by `_within` (see there)."""
    return value == value.quantize(CENTS)


def _without_negative_zero(value: Decimal) -> Decimal:
    """`Decimal("-0")` equals 0 but keeps its sign through `quantize` (and would print `-0.00`)."""
    return value.copy_abs() if value.is_zero() else value


def _unit_price_error(unit_price: Decimal) -> ShapeError | None:
    """A unit price is a whole-rupee amount from 0 to `MAX_AMOUNT` (D41); the integral check
    never quantizes, and the range is checked before any later `quantize` (EST-20, EST-21)."""
    if not is_whole_rupees(unit_price):
        return ShapeError(
            "unit_price", NOT_WHOLE_RUPEES, "Amounts must be whole rupees (no paisa)."
        )
    if is_too_large(unit_price):
        return ShapeError("unit_price", VALUE_ERROR, AMOUNT_TOO_LARGE)
    return None


def _part_shape_errors(line: LineInput) -> list[ShapeError]:
    errors: list[ShapeError] = []
    if line.part_id is None:
        errors.append(ShapeError("part_id", MISSING, "A part line needs a part_id."))
    if line.description is not None:
        errors.append(
            ShapeError(
                "description",
                NOT_ALLOWED,
                "A part line takes its description from the parts catalogue; leave it out.",
            )
        )
    quantity = line.quantity
    if not (
        _within(quantity, PART_QUANTITY_MIN, PART_QUANTITY_MAX)
        and quantity == quantity.to_integral_value()
    ):
        errors.append(
            ShapeError(
                "quantity", VALUE_ERROR, "A part quantity must be a whole number from 1 to 9999."
            )
        )
    return errors


def _labour_shape_errors(line: LineInput) -> list[ShapeError]:
    errors: list[ShapeError] = []
    if line.part_id is not None:
        errors.append(ShapeError("part_id", NOT_ALLOWED, "A labour line cannot reference a part."))
    description = line.description.strip() if line.description is not None else None
    if description is None:
        errors.append(ShapeError("description", MISSING, "A labour line needs a description."))
    elif not description:
        errors.append(
            ShapeError("description", STRING_TOO_SHORT, "String should have at least 1 character")
        )
    elif len(description) > DESCRIPTION_MAX_LENGTH:
        errors.append(
            ShapeError(
                "description",
                STRING_TOO_LONG,
                f"String should have at most {DESCRIPTION_MAX_LENGTH} characters",
            )
        )
    elif contains_nul(description):
        errors.append(ShapeError("description", VALUE_ERROR, NUL_NOT_ALLOWED))
    quantity = line.quantity
    if not (
        _within(quantity, LABOUR_QUANTITY_MIN, LABOUR_QUANTITY_MAX)
        and _has_at_most_two_places(quantity)
    ):
        errors.append(
            ShapeError(
                "quantity",
                VALUE_ERROR,
                "A labour quantity must be from 0.01 to 999.99, with at most two decimals.",
            )
        )
    if line.unit_price is None:
        errors.append(ShapeError("unit_price", MISSING, "A labour line needs a unit_price."))
    return errors


def check_line_shape(line: LineInput) -> list[ShapeError]:
    """Every rule one line breaks on its own (§7.4), in field order; empty when the line is fine."""
    if line.line_type == EstimateLineType.PART:
        errors = _part_shape_errors(line)
    else:
        errors = _labour_shape_errors(line)
    if line.unit_price is not None and (price_error := _unit_price_error(line.unit_price)):
        errors.append(price_error)
    return errors


def _invalid_part(index: int) -> LineError:
    return LineError(line_field(index, "part_id"), INVALID_REFERENCE, INACTIVE_OR_UNKNOWN_PART)


def _count_errors(count: int) -> list[LineError]:
    if count < MIN_LINES:
        message = f"List should have at least {MIN_LINES} item after validation, not {count}"
        return [LineError("lines", TOO_SHORT, message)]
    if count > MAX_LINES:
        message = f"List should have at most {MAX_LINES} items after validation, not {count}"
        return [LineError("lines", TOO_LONG, message)]
    return []


def _price_one(
    index: int, line: LineInput, parts: Mapping[UUID, CatalogPart]
) -> PricedLine | list[LineError]:
    shape_errors = check_line_shape(line)
    if shape_errors:
        return [
            LineError(line_field(index, error.field), error.code, error.message)
            for error in shape_errors
        ]
    description = line.description.strip() if line.description is not None else None
    unit_price = line.unit_price
    if line.line_type == EstimateLineType.PART:
        part = parts.get(line.part_id) if line.part_id is not None else None
        if part is None or not part.is_active:
            return [_invalid_part(index)]
        description = part.name
        if unit_price is None:
            unit_price = part.unit_cost  # D40: the catalogue cost unless the editor overrides it
            if price_error := _unit_price_error(unit_price):  # a catalogue cost skips the shape
                return [
                    LineError(
                        line_field(index, "unit_price"), price_error.code, price_error.message
                    )
                ]
    if description is None or unit_price is None:  # excluded by check_line_shape (labour lines)
        return [LineError(line_field(index, "description"), MISSING, "The line is incomplete.")]
    # Both values are bounded now (check_line_shape / _unit_price_error), so quantize is safe.
    quantity = line.quantity.quantize(CENTS)
    unit_price = _without_negative_zero(unit_price.quantize(CENTS))
    total = line_total(quantity, unit_price)
    if is_too_large(total):
        return [LineError(line_field(index, "quantity"), VALUE_ERROR, AMOUNT_TOO_LARGE)]
    return PricedLine(
        position=index + 1,
        line_type=line.line_type,
        part_id=line.part_id,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        line_total=total,
    )


def price_lines(lines: Sequence[LineInput], parts: Mapping[UUID, CatalogPart]) -> PricingResult:
    """Validate and price the full new list (§7.3): positions 1..n in request order.

    `parts` holds the catalogue facts of the referenced parts of **this** shop; an id missing from
    it is unknown or belongs to another shop. Errors: not 1-50 lines (`lines`, `too_short` /
    `too_long`), a line's own rules (`check_line_shape`), an unknown, foreign or inactive part
    (`lines.N.part_id` `invalid_reference`, EST-07), a line total above `MAX_AMOUNT`
    (`lines.N.quantity`), or, when every line is fine, a grand total above it (`lines`) - each
    `value_error` "The amount is too large." (EST-21).
    """
    priced: list[PricedLine] = []
    errors: list[LineError] = _count_errors(len(lines))
    for index, line in enumerate(lines):
        result = _price_one(index, line, parts)
        if isinstance(result, PricedLine):
            priced.append(result)
        else:
            errors.extend(result)
    totals = estimate_totals(priced)
    if not errors and totals.grand_total > MAX_AMOUNT:
        errors.append(LineError("lines", VALUE_ERROR, AMOUNT_TOO_LARGE))
    return PricingResult(lines=tuple(priced), totals=totals, errors=tuple(errors))


def inactive_part_errors(
    part_lines: Iterable[tuple[int, UUID]], parts: Mapping[UUID, CatalogPart]
) -> list[LineError]:
    """T06: every stored `PART` line, given as `(index, part_id)`, must still reference an active
    part of the shop; a part deactivated since it was added -> `lines.N.part_id`
    `invalid_reference` (spec 03 §5.2). Every offending line is reported."""
    return [
        _invalid_part(index)
        for index, part_id in part_lines
        if (part := parts.get(part_id)) is None or not part.is_active
    ]

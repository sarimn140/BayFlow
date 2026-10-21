"""Estimate line rules and pricing (D40, D41; `modules/estimates.md` §7.3-§7.5): EST-05, EST-07,
EST-08, EST-09, EST-21, EST-23, EST-24 (domain halves)."""

import uuid
from decimal import Decimal

import pytest

from app.modules.estimates.domain.lines import (
    AMOUNT_TOO_LARGE,
    DESCRIPTION_MAX_LENGTH,
    INVALID_REFERENCE,
    MISSING,
    NOT_ALLOWED,
    NOT_WHOLE_RUPEES,
    STRING_TOO_LONG,
    STRING_TOO_SHORT,
    TOO_LONG,
    TOO_SHORT,
    VALUE_ERROR,
    CatalogPart,
    LineError,
    LineInput,
    PricedLine,
    check_line_shape,
    inactive_part_errors,
    line_field,
    price_lines,
)
from app.modules.estimates.domain.totals import MAX_AMOUNT, Totals
from app.shared.enums import EstimateLineType

PART = EstimateLineType.PART
LABOUR = EstimateLineType.LABOUR

COIL, FILTER, OIL, RETIRED = (uuid.uuid4() for _ in range(4))
CATALOG = {
    COIL: CatalogPart(name="Ignition coil", unit_cost=Decimal("6500.00"), is_active=True),
    FILTER: CatalogPart(name="Oil filter", unit_cost=Decimal("900.00"), is_active=True),
    OIL: CatalogPart(name="Engine oil 4 L", unit_cost=Decimal("5200.00"), is_active=True),
    RETIRED: CatalogPart(name="Old coil", unit_cost=Decimal("100.00"), is_active=False),
}


def part(
    part_id: uuid.UUID | None, quantity: str = "1", unit_price: str | None = None
) -> LineInput:
    return LineInput(
        line_type=PART,
        part_id=part_id,
        description=None,
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price) if unit_price is not None else None,
    )


def labour(
    description: str | None = "Diagnosis and repair labour",
    quantity: str = "1",
    unit_price: str | None = "4000",
) -> LineInput:
    return LineInput(
        line_type=LABOUR,
        part_id=None,
        description=description,
        quantity=Decimal(quantity),
        unit_price=Decimal(unit_price) if unit_price is not None else None,
    )


def codes(line: LineInput) -> list[tuple[str, str]]:
    return [(error.field, error.code) for error in check_line_shape(line)]


def test_est_05_worked_example_prices_to_16600() -> None:
    """EST-05 ★: the technician's v1 (brief §6 step 5) priced from the catalogue."""
    result = price_lines([part(COIL), part(FILTER), part(OIL), labour()], CATALOG)
    assert result.errors == ()
    assert result.totals == Totals(Decimal("12600.00"), Decimal("4000.00"), Decimal("16600.00"))
    assert [line.position for line in result.lines] == [1, 2, 3, 4]
    assert [line.description for line in result.lines] == [
        "Ignition coil",
        "Oil filter",
        "Engine oil 4 L",
        "Diagnosis and repair labour",
    ]
    assert result.lines[3] == PricedLine(
        position=4,
        line_type=LABOUR,
        part_id=None,
        description="Diagnosis and repair labour",
        quantity=Decimal("1.00"),
        unit_price=Decimal("4000.00"),
        line_total=Decimal("4000.00"),
    )


def test_est_09_part_unit_price_defaults_to_unit_cost_and_can_be_overridden() -> None:
    """EST-09: no `unit_price` -> `parts.unit_cost`; a given one wins (also 0, a free part)."""
    result = price_lines(
        [part(FILTER), part(FILTER, unit_price="850"), part(FILTER, unit_price="0")], CATALOG
    )
    assert result.errors == ()
    assert [line.unit_price for line in result.lines] == [
        Decimal("900.00"),
        Decimal("850.00"),
        Decimal("0.00"),
    ]
    assert result.totals.parts_total == Decimal("1750.00")


def test_est_23_part_description_is_the_catalogue_name_at_save_time() -> None:
    """EST-23 (domain half): the stored description is whatever the catalogue says now."""
    renamed = {COIL: CatalogPart("Ignition coil (OEM)", Decimal("6500"), is_active=True)}
    assert price_lines([part(COIL)], CATALOG).lines[0].description == "Ignition coil"
    assert price_lines([part(COIL)], renamed).lines[0].description == "Ignition coil (OEM)"


def test_the_same_part_may_appear_on_several_lines() -> None:
    result = price_lines([part(OIL, "1"), part(OIL, "2", "5000")], CATALOG)
    assert result.errors == ()
    assert [line.line_total for line in result.lines] == [Decimal("5200.00"), Decimal("10000.00")]


@pytest.mark.parametrize(
    "bad_part", [RETIRED, uuid.uuid4()], ids=["inactive", "unknown-or-foreign"]
)
def test_est_07_part_must_be_an_active_part_of_this_shop(bad_part: uuid.UUID) -> None:
    """EST-07: inactive, unknown or another shop's part (absent from this shop's catalogue
    facts) -> `lines.N.part_id` `invalid_reference`; nothing is priced."""
    result = price_lines([labour(), part(bad_part)], CATALOG)
    assert result.errors == (
        LineError(
            "lines.1.part_id",
            INVALID_REFERENCE,
            "Choose an active part from this shop's catalogue.",
        ),
    )


def test_est_24_every_invalid_line_is_reported_at_once() -> None:
    """EST-24 (domain half): one pass reports every bad line, not just the first."""
    lines = [
        part(RETIRED),  # 0: inactive part
        labour(),  # 1: fine
        labour(description="  "),  # 2: blank description
        part(uuid.uuid4(), quantity="2"),  # 3: unknown part
        labour(unit_price=None, quantity="1000"),  # 4: two rules broken on one line
    ]
    result = price_lines(lines, CATALOG)
    assert [(error.field, error.code) for error in result.errors] == [
        ("lines.0.part_id", INVALID_REFERENCE),
        ("lines.2.description", STRING_TOO_SHORT),
        ("lines.3.part_id", INVALID_REFERENCE),
        ("lines.4.quantity", VALUE_ERROR),
        ("lines.4.unit_price", MISSING),
    ]


def test_est_21_a_line_above_the_numeric_limit_is_a_quantity_error() -> None:
    """EST-21: 9 999 x 9 999 999 999 -> `lines.N.quantity` "The amount is too large."."""
    result = price_lines([labour(), part(FILTER, "9999", "9999999999")], CATALOG)
    assert result.errors == (LineError("lines.1.quantity", VALUE_ERROR, AMOUNT_TOO_LARGE),)


def test_est_21_a_grand_total_above_the_numeric_limit_is_a_lines_error() -> None:
    """EST-21: every line fits but their sum does not -> field `lines`."""
    half = "5000000000"
    result = price_lines([labour(unit_price=half), labour(unit_price=half)], CATALOG)
    assert result.errors == (LineError("lines", VALUE_ERROR, AMOUNT_TOO_LARGE),)


def test_amounts_exactly_at_the_limit_are_accepted() -> None:
    result = price_lines([labour(unit_price="9999999999")], CATALOG)
    assert result.errors == ()
    assert result.totals.grand_total == MAX_AMOUNT


def test_labour_description_is_trimmed_and_quantities_get_two_places() -> None:
    result = price_lines([labour(description="  Wheel alignment  ", quantity="1.5")], CATALOG)
    assert result.errors == ()
    line = result.lines[0]
    assert line.description == "Wheel alignment"
    assert line.quantity == Decimal("1.50")
    assert line.quantity.as_tuple().exponent == -2
    assert line.line_total == Decimal("6000.00")


def test_est_08_part_line_rules() -> None:
    """EST-08: `part_id` required; no `description`; whole quantity 1-9 999."""
    assert codes(part(COIL)) == []
    assert codes(part(COIL, "9999")) == []
    assert codes(part(None)) == [("part_id", MISSING)]
    for quantity in ("0", "0.5", "1.5", "10000", "-1"):
        assert codes(part(COIL, quantity)) == [("quantity", VALUE_ERROR)], quantity
    with_description = LineInput(PART, COIL, "My own name", Decimal(1), None)
    assert codes(with_description) == [("description", NOT_ALLOWED)]
    blank_description = LineInput(PART, COIL, "", Decimal(1), None)
    assert codes(blank_description) == [("description", NOT_ALLOWED)]


def test_est_08_labour_line_rules() -> None:
    """EST-08: description required (1-255, trimmed); quantity 0.01-999.99; unit price required;
    no `part_id`."""
    assert codes(labour()) == []
    assert codes(labour(quantity="0.01")) == []
    assert codes(labour(quantity="999.99")) == []
    assert codes(labour(description="x" * DESCRIPTION_MAX_LENGTH)) == []
    assert codes(labour(description=None)) == [("description", MISSING)]
    assert codes(labour(description=" \t ")) == [("description", STRING_TOO_SHORT)]
    assert codes(labour(description="x" * (DESCRIPTION_MAX_LENGTH + 1))) == [
        ("description", STRING_TOO_LONG)
    ]
    for quantity in ("0", "0.001", "1000", "999.991", "-0.01"):
        assert codes(labour(quantity=quantity)) == [("quantity", VALUE_ERROR)], quantity
    assert codes(labour(unit_price=None)) == [("unit_price", MISSING)]
    with_part = LineInput(LABOUR, COIL, "Fit coil", Decimal(1), Decimal(500))
    assert codes(with_part) == [("part_id", NOT_ALLOWED)]
    assert codes(labour(description="Fit\x00coil")) == [("description", VALUE_ERROR)]


@pytest.mark.parametrize("unit_price", ["900.50", "0.01", "-1"])
def test_est_20_unit_prices_must_be_whole_non_negative_rupees(unit_price: str) -> None:
    """EST-20 (domain half): paisa or negative prices are refused on either line type."""
    assert codes(part(FILTER, unit_price=unit_price)) == [("unit_price", NOT_WHOLE_RUPEES)]
    assert codes(labour(unit_price=unit_price)) == [("unit_price", NOT_WHOLE_RUPEES)]


@pytest.mark.parametrize(
    ("line", "field", "code"),
    [
        (labour(quantity="1e30"), "quantity", VALUE_ERROR),
        (labour(quantity="-1e30"), "quantity", VALUE_ERROR),
        (labour(quantity="1.000000000000000000000000000000001"), "quantity", VALUE_ERROR),
        (labour(quantity="NaN"), "quantity", VALUE_ERROR),
        (labour(quantity="sNaN"), "quantity", VALUE_ERROR),
        (labour(quantity="-Infinity"), "quantity", VALUE_ERROR),
        (labour(unit_price="1e30"), "unit_price", VALUE_ERROR),
        (labour(unit_price="10000000000"), "unit_price", VALUE_ERROR),  # MAX_AMOUNT + 1
        (labour(unit_price="NaN"), "unit_price", NOT_WHOLE_RUPEES),
        (labour(unit_price="Infinity"), "unit_price", NOT_WHOLE_RUPEES),
        (part(FILTER, quantity="1e30"), "quantity", VALUE_ERROR),
        (part(FILTER, quantity="sNaN"), "quantity", VALUE_ERROR),
        (part(FILTER, unit_price="1e30"), "unit_price", VALUE_ERROR),
        (part(FILTER, unit_price="1e-30"), "unit_price", NOT_WHOLE_RUPEES),
    ],
)
def test_absurd_numbers_are_field_errors_never_decimal_exceptions(
    line: LineInput, field: str, code: str
) -> None:
    """Backstop for callers that skip the schema: values are range-checked before anything
    quantizes them, so `1e30`, NaN or infinities answer a 422 field error instead of raising
    `decimal.InvalidOperation` (a 500)."""
    result = price_lines([line], CATALOG)
    assert [(error.field, error.code) for error in result.errors] == [(f"lines.0.{field}", code)]
    assert result.lines == ()


def test_an_absurd_catalogue_cost_is_a_field_error_too() -> None:
    """The defaulted unit price (the catalogue cost) skips the line's own check, so it is
    checked as well - unreachable with the database's own checks, but never a 500."""
    catalog = {FILTER: CatalogPart(name="Oil filter", unit_cost=Decimal("1e30"), is_active=True)}
    result = price_lines([part(FILTER)], catalog)
    assert [(error.field, error.code) for error in result.errors] == [
        ("lines.0.unit_price", VALUE_ERROR)
    ]


def test_a_negative_zero_price_is_priced_as_plain_zero() -> None:
    """`Decimal("-0")` equals 0 but would print `-0.00`: the priced line holds `+0.00`."""
    result = price_lines([labour(unit_price="-0", quantity="2")], CATALOG)
    assert result.errors == ()
    [line] = result.lines
    assert (str(line.unit_price), str(line.line_total)) == ("0.00", "0.00")
    assert not line.unit_price.is_signed()
    assert not line.line_total.is_signed()


def test_shape_errors_come_back_as_body_paths_through_price_lines() -> None:
    result = price_lines([labour(), part(None)], CATALOG)
    assert result.errors == (LineError("lines.1.part_id", MISSING, "A part line needs a part_id."),)
    assert line_field(12, "unit_price") == "lines.12.unit_price"


def test_est_08_a_list_needs_one_to_fifty_lines() -> None:
    """EST-08 backstop for callers other than the schema (the seed, a future caller)."""
    empty = price_lines([], CATALOG)
    assert [(error.field, error.code) for error in empty.errors] == [("lines", TOO_SHORT)]
    assert empty.lines == ()
    too_many = price_lines([labour()] * 51, CATALOG)
    assert [(error.field, error.code) for error in too_many.errors] == [("lines", TOO_LONG)]
    fifty = price_lines([labour()] * 50, CATALOG)
    assert fifty.errors == ()
    assert [line.position for line in fifty.lines] == list(range(1, 51))


def test_t06_inactive_part_errors_report_every_deactivated_or_missing_part() -> None:
    """T06 (spec 03 §5.2): a part deactivated since it was added -> `lines.N.part_id`."""
    stored = [(0, COIL), (2, RETIRED), (3, uuid.uuid4()), (5, FILTER)]
    assert inactive_part_errors(stored, CATALOG) == [
        LineError(
            "lines.2.part_id",
            INVALID_REFERENCE,
            "Choose an active part from this shop's catalogue.",
        ),
        LineError(
            "lines.3.part_id",
            INVALID_REFERENCE,
            "Choose an active part from this shop's catalogue.",
        ),
    ]
    assert inactive_part_errors([(0, COIL), (1, OIL)], CATALOG) == []

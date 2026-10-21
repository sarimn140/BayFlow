"""Whole-rupee money (D41, spec 03 §1.5, spec 02 §2.3)."""

from decimal import ROUND_HALF_EVEN, Decimal

import pytest
from pydantic import BaseModel, ValidationError

from app.shared.money import Money, format_decimal, format_money, is_whole_rupees, round_rupees


class Line(BaseModel):
    unit_price: Money


@pytest.mark.parametrize(
    ("value", "rounded"),
    [
        ("2498.5", "2499.00"),  # half-up, where Python's default (half-even) gives 2498
        ("0.5", "1.00"),
        ("1.5", "2.00"),
        ("1498.49", "1498.00"),
        ("1498.50", "1499.00"),
        ("16100", "16100.00"),
        ("0", "0.00"),
    ],
)
def test_round_rupees_rounds_half_up_to_whole_rupees(value: str, rounded: str) -> None:
    assert round_rupees(Decimal(value)) == Decimal(rounded)
    assert str(round_rupees(Decimal(value))) == rounded


def test_half_up_differs_from_pythons_default_rounding() -> None:
    assert Decimal("2498.5").quantize(Decimal("1"), rounding=ROUND_HALF_EVEN) == Decimal("2498")
    assert round_rupees(Decimal("2498.5")) == Decimal("2499")


def test_worked_example_line_total() -> None:
    # Labour 1.50 h x 3500 = 5250 exactly; 0.5 x 4997 = 2498.5 -> 2499 (spec 02 §2.3).
    assert round_rupees(Decimal("1.50") * Decimal("3500")) == Decimal("5250.00")
    assert round_rupees(Decimal("0.50") * Decimal("4997.00")) == Decimal("2499.00")


@pytest.mark.parametrize(
    ("value", "text"),
    [("16100", "16100.00"), ("16100.00", "16100.00"), ("0", "0.00"), ("1E+4", "10000.00")],
)
def test_format_money_always_has_two_places(value: str, text: str) -> None:
    assert format_money(Decimal(value)) == text


def test_format_decimal_for_quantities() -> None:
    assert format_decimal(Decimal("1.5")) == "1.50"
    assert format_decimal(Decimal("1")) == "1.00"


def test_is_whole_rupees() -> None:
    assert is_whole_rupees(Decimal("6500.00"))
    assert not is_whole_rupees(Decimal("6500.50"))
    assert not is_whole_rupees(Decimal("NaN"))


@pytest.mark.parametrize(
    ("raw", "parsed"),
    [("6500", "6500.00"), ("6500.00", "6500.00"), (6500, "6500.00"), ("0", "0.00")],
)
def test_money_accepts_strings_and_integers(raw: object, parsed: str) -> None:
    line = Line.model_validate({"unit_price": raw})
    assert line.unit_price == Decimal(parsed)
    assert line.model_dump_json() == f'{{"unit_price":"{parsed}"}}'


@pytest.mark.parametrize(
    ("raw", "error_type"),
    [
        ("6500.50", "not_whole_rupees"),
        (6500.5, "not_whole_rupees"),
        (6500.0, "not_whole_rupees"),  # floats are never accepted for money
        (True, "not_whole_rupees"),
        ("-1", "greater_than_equal"),
        ("10000000000", "less_than_equal"),
        ("1.005", "decimal_max_places"),
        ("abc", "decimal_parsing"),
    ],
)
def test_money_rejects_everything_else(raw: object, error_type: str) -> None:
    with pytest.raises(ValidationError) as caught:
        Line.model_validate({"unit_price": raw})
    assert caught.value.errors()[0]["type"] == error_type


def test_money_json_schema_is_a_string_in_responses() -> None:
    schema = Line.model_json_schema(mode="serialization")
    assert schema["properties"]["unit_price"]["type"] == "string"


@pytest.mark.parametrize("raw", ["-0", "-0.00", "-000"])
def test_negative_zero_is_plain_zero(raw: str) -> None:
    line = Line.model_validate({"unit_price": raw})
    assert not line.unit_price.is_signed()
    assert line.model_dump_json() == '{"unit_price":"0.00"}'


@pytest.mark.parametrize("value", [Decimal("-0"), Decimal("-0.00"), round_rupees(Decimal("-0.4"))])
def test_formatting_never_prints_a_negative_zero(value: Decimal) -> None:
    assert format_money(value) == "0.00"
    assert format_decimal(value, 1) == "0.0"

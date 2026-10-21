"""Estimate money rules (D41; `modules/estimates.md` §7.5): EST-05, EST-20, EST-21, EST-25 (unit
halves). Whole rupees, half-up, `Decimal` only."""

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

import pytest

from app.modules.estimates.domain.totals import (
    MAX_AMOUNT,
    ZERO,
    Totals,
    estimate_totals,
    is_too_large,
    line_total,
)
from app.shared.enums import EstimateLineType
from app.shared.money import MAX_AMOUNT as SHARED_MAX_AMOUNT
from app.shared.money import round_rupees

PART = EstimateLineType.PART
LABOUR = EstimateLineType.LABOUR


@dataclass(frozen=True)
class Line:
    line_type: EstimateLineType
    line_total: Decimal


def priced(line_type: EstimateLineType, quantity: str, unit_price: str) -> Line:
    return Line(line_type, line_total(Decimal(quantity), Decimal(unit_price)))


def test_est_05_worked_example_v1_is_16600_and_v2_is_16100() -> None:
    """EST-05 ★: coil 6,500 + filter 900 + oil 5,200 + labour 4,000 = 16,600; labour 3,500 ->
    16,100 (brief §6 steps 5-6)."""
    parts = [priced(PART, "1", "6500"), priced(PART, "1", "900"), priced(PART, "1", "5200")]
    v1 = estimate_totals([*parts, priced(LABOUR, "1", "4000")])
    v2 = estimate_totals([*parts, priced(LABOUR, "1", "3500")])
    assert v1 == Totals(Decimal("12600.00"), Decimal("4000.00"), Decimal("16600.00"))
    assert v2 == Totals(Decimal("12600.00"), Decimal("3500.00"), Decimal("16100.00"))
    assert str(v2.grand_total) == "16100.00"


def test_est_20_line_total_rounds_half_up_not_half_even() -> None:
    """EST-20: 1.50 x 999 = 1,498.50 -> 1,499.00, where banker's rounding would give 1,498."""
    exact = Decimal("1.50") * Decimal("999")
    assert exact == Decimal("1498.50")
    assert exact.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN) == Decimal("1498")
    assert line_total(Decimal("1.50"), Decimal("999")) == Decimal("1499.00")
    assert str(line_total(Decimal("1.50"), Decimal("999"))) == "1499.00"


@pytest.mark.parametrize(
    ("quantity", "unit_price", "expected"),
    [
        ("0.50", "1", "1.00"),  # 0.5 -> 1
        ("1.50", "1", "2.00"),  # 1.5 -> 2 (half-even: 2)
        ("2.50", "1", "3.00"),  # 2.5 -> 3 (half-even: 2)
        ("0.25", "2", "1.00"),  # 0.5 -> 1 (half-even: 0)
        ("0.50", "4997", "2499.00"),  # spec 02 §2.3: PostgreSQL round(0.50 * 4997.00) = 2499
        ("2.50", "999", "2498.00"),  # 2497.5 -> 2498
        ("0.01", "49", "0.00"),  # 0.49 -> 0
        ("0.01", "50", "1.00"),  # 0.50 -> 1
        ("0.01", "51", "1.00"),  # 0.51 -> 1
        ("1.00", "0", "0.00"),  # free items are allowed (unit price >= 0)
        ("9999", "1", "9999.00"),
    ],
)
def test_est_20_line_total_examples(quantity: str, unit_price: str, expected: str) -> None:
    """EST-20: each line total is quantity x unit price rounded half-up to whole rupees, `.00`."""
    result = line_total(Decimal(quantity), Decimal(unit_price))
    assert result == Decimal(expected)
    assert result.as_tuple().exponent == -2


def test_est_25_line_total_equals_shared_round_rupees_on_every_half_tie() -> None:
    """EST-25 (unit half): the domain's re-implemented rounding equals
    `app.shared.money.round_rupees` for every quantity 0.01-9.99 against prices that produce
    every .5 tie (odd prices x quantities ending in 5 or 0)."""
    prices = [Decimal(p) for p in ("1", "2", "3", "5", "7", "9", "11", "99", "999", "4997")]
    ties = 0
    for hundredths in range(1, 1000):
        quantity = Decimal(hundredths).scaleb(-2)
        for price in prices:
            exact = quantity * price
            if exact % 1 == Decimal("0.5"):
                ties += 1
            assert line_total(quantity, price) == round_rupees(exact), (quantity, price)
    assert ties > 100  # the sample really contains many .5 ties


def test_line_total_is_exact_whatever_the_ambient_decimal_context() -> None:
    with localcontext(prec=3, rounding=ROUND_HALF_EVEN):
        assert line_total(Decimal("9999"), Decimal("9999999999")) == Decimal("99989999990001.00")
        assert line_total(Decimal("2.50"), Decimal("999")) == Decimal("2498.00")


def test_est_21_the_largest_possible_line_is_computed_and_flagged_not_trapped() -> None:
    """EST-21 (unit half): 9 999 x 9 999 999 999 is computed exactly and is too large."""
    total = line_total(Decimal("9999"), Decimal("9999999999"))
    assert total == Decimal("99989999990001.00")
    assert is_too_large(total)


def test_max_amount_is_the_numeric_12_2_limit() -> None:
    assert Decimal("9999999999.00") == MAX_AMOUNT == SHARED_MAX_AMOUNT
    assert not is_too_large(MAX_AMOUNT)
    assert is_too_large(MAX_AMOUNT + 1)
    assert not is_too_large(ZERO)


def test_estimate_totals_of_no_lines_are_zero() -> None:
    assert estimate_totals([]) == Totals(ZERO, ZERO, ZERO)


def test_estimate_totals_sum_the_rounded_lines_per_type() -> None:
    """Totals are sums of the **rounded** line totals (EST-20), never a rounding of the sum."""
    lines = [
        priced(LABOUR, "0.50", "1"),  # 0.5 -> 1
        priced(LABOUR, "0.50", "1"),  # 0.5 -> 1  (sum of exact values would be 1.0 -> 1)
        priced(PART, "3", "100"),
        priced(PART, "1", "0"),
    ]
    totals = estimate_totals(lines)
    assert totals.labour_total == Decimal("2.00")
    assert totals.parts_total == Decimal("300.00")
    assert totals.grand_total == totals.parts_total + totals.labour_total == Decimal("302.00")

"""Inventory stock maths and plans (`app.modules.inventory.domain.stock`), pure and DB-free.

INV-15 (low/out), INV-26 (order-free ledger checker), the domain halves of INV-02...INV-04,
INV-07, INV-10...INV-13, INV-25, INV-27, INV-28 and the PO status rule of spec 02 §6.
"""

import itertools
import random
import uuid
from uuid import UUID

import pytest

from app.core.errors import (
    ConcurrentUpdate,
    Conflict,
    InsufficientStock,
    ValidationFailed,
)
from app.modules.inventory.domain.stock import (
    MAX_ON_HAND,
    BookingPartLine,
    LedgerEntry,
    OrderedItem,
    PartBalance,
    PartQty,
    ReceiptLine,
    ReceiptPart,
    adjusted_on_hand,
    all_fully_reserved,
    available,
    booking_ledger,
    count_available,
    duplicate_positions,
    ledger_balances,
    movement_deltas,
    order_quantities,
    outstanding,
    plan_consumption,
    plan_full_reservation,
    plan_order,
    plan_receipt,
    plan_receipt_reservation,
    plan_release,
    purchase_order_status,
    receipt_on_hand_errors,
    running_balances,
    shortage,
    stock_state,
    sum_by_part,
)
from app.shared.enums import PurchaseOrderStatus, StockMovementType, StockState

# The worked example (spec 08 "Parts reservations"): ids sort as filter < oil < coil.
FILTER = UUID("00000000-0000-4000-8000-000000000001")
OIL = UUID("00000000-0000-4000-8000-000000000002")
COIL = UUID("00000000-0000-4000-8000-000000000003")
BOOKING = UUID("00000000-0000-4000-8000-0000000000b1")


def balances(**stock: tuple[int, int]) -> dict[UUID, PartBalance]:
    ids = {"filter": FILTER, "oil": OIL, "coil": COIL}
    return {
        ids[name]: PartBalance(part_id=ids[name], on_hand=on_hand, reserved=reserved)
        for name, (on_hand, reserved) in stock.items()
    }


def line(part_id: UUID, required: int, reserved: int = 0, consumed: int = 0) -> BookingPartLine:
    return BookingPartLine(
        part_id=part_id, required_qty=required, reserved_qty=reserved, consumed_qty=consumed
    )


WORKED_EXAMPLE_LINES = [line(FILTER, 1), line(OIL, 1), line(COIL, 1)]
WORKED_EXAMPLE_STOCK = balances(filter=(10, 0), oil=(8, 0), coil=(0, 0))


def codes(error: ValidationFailed) -> list[tuple[str, str]]:
    assert error.errors is not None
    return [(item["field"], item["code"]) for item in error.errors]


# --- INV-15: available, low and out (D45) -----------------------------------------------------


@pytest.mark.parametrize(
    ("available_qty", "reorder_level", "expected"),
    [
        (0, 0, StockState.OUT),  # OUT even with reorder level 0
        (0, 5, StockState.OUT),  # OUT wins over LOW
        (1, 5, StockState.LOW),
        (5, 5, StockState.LOW),  # "low" is available <= reorder level
        (6, 5, StockState.OK),
        (1, 0, StockState.OK),
    ],
)
def test_inv15_stock_state_is_out_then_low_then_ok(
    available_qty: int, reorder_level: int, expected: StockState
) -> None:
    assert stock_state(available_qty, reorder_level) is expected


def test_inv15_available_is_computed_from_on_hand_and_reserved() -> None:
    assert available(10, 3) == 7
    assert PartBalance(part_id=FILTER, on_hand=4, reserved=4).available == 0


def test_outstanding_and_shortage() -> None:
    assert outstanding(5, 2, 1) == 2
    assert shortage(3, 1) == 2
    assert shortage(3, 5) == 0
    assert line(COIL, 3, reserved=1, consumed=0).outstanding == 2
    assert line(COIL, 2, reserved=0, consumed=2).fully_reserved


def test_parts_counts_treat_zero_rows_as_all_available() -> None:
    counts = count_available([], {})
    assert (counts.required_count, counts.available_count, counts.shortage_count) == (0, 0, 0)
    assert counts.all_available


def test_parts_counts_follow_the_worked_example() -> None:
    counts = count_available(WORKED_EXAMPLE_LINES, WORKED_EXAMPLE_STOCK)
    assert (counts.required_count, counts.available_count, counts.shortage_count) == (3, 2, 1)
    assert not counts.all_available
    # A fully reserved row counts as available even when no stock is left.
    reserved = count_available([line(COIL, 1, reserved=1)], balances(coil=(1, 1)))
    assert reserved.all_available


def test_part_quantities_are_summed_per_part_in_id_order() -> None:
    merged = sum_by_part([PartQty(OIL, 1), PartQty(FILTER, 2), PartQty(OIL, 3)])
    assert merged == (PartQty(FILTER, 2), PartQty(OIL, 4))
    assert PartQty(COIL, 1).as_json() == {"part_id": str(COIL), "qty": 1}


def test_duplicate_positions_report_every_repeat_after_the_first() -> None:
    assert duplicate_positions(["a", "b", "a", "c", "b", "a"]) == [2, 4, 5]
    assert duplicate_positions([]) == []


# --- T13 order-parts (INV-02, INV-03, INV-04, INV-27) -------------------------------------------


def test_inv02_order_plan_reserves_what_is_available_and_orders_the_rest() -> None:
    plan = plan_order(WORKED_EXAMPLE_LINES, WORKED_EXAMPLE_STOCK)
    assert plan.reserve == (PartQty(FILTER, 1), PartQty(OIL, 1))
    assert plan.shortages == (PartQty(COIL, 1),)


def test_order_plan_reserves_a_partial_quantity_when_stock_is_short() -> None:
    plan = plan_order([line(COIL, 3)], balances(coil=(5, 4)))  # 1 available
    assert plan.reserve == (PartQty(COIL, 1),)
    assert plan.shortages == (PartQty(COIL, 2),)


def test_inv03_nothing_short_gives_no_shortages() -> None:
    assert plan_order([line(FILTER, 1)], balances(filter=(1, 0))).shortages == ()
    assert plan_order([], {}).shortages == ()  # zero rows: nothing short either


def test_order_items_omitted_order_exactly_the_shortages() -> None:
    assert order_quantities((PartQty(COIL, 2),), None) == (PartQty(COIL, 2),)


def test_order_items_may_order_more_than_the_shortage() -> None:
    assert order_quantities((PartQty(COIL, 2),), [PartQty(COIL, 5)]) == (PartQty(COIL, 5),)


def test_inv04_an_item_below_its_shortage_is_422() -> None:
    with pytest.raises(ValidationFailed) as caught:
        order_quantities((PartQty(COIL, 2),), [PartQty(COIL, 1)])
    assert codes(caught.value) == [("items.0.quantity", "below_shortage")]


def test_inv27_all_item_violations_are_reported_together() -> None:
    shortages = (PartQty(OIL, 1), PartQty(COIL, 2))
    items = [PartQty(FILTER, 1), PartQty(COIL, 1), PartQty(FILTER, 1)]
    with pytest.raises(ValidationFailed) as caught:
        order_quantities(shortages, items)
    assert codes(caught.value) == [
        ("items.0.part_id", "not_short"),
        ("items.1.quantity", "below_shortage"),
        ("items.2.part_id", "duplicate"),
        ("items", "missing_shortage"),
    ]


def test_an_empty_item_list_misses_every_shortage() -> None:
    with pytest.raises(ValidationFailed) as caught:
        order_quantities((PartQty(COIL, 1),), [])
    assert codes(caught.value) == [("items", "missing_shortage")]


# --- T14 / T15 / T16 / T22 ----------------------------------------------------------------------


def test_inv10_full_reservation_lists_every_short_part() -> None:
    plan = plan_full_reservation(WORKED_EXAMPLE_LINES, WORKED_EXAMPLE_STOCK)
    assert plan.short == (PartQty(COIL, 1),)
    assert plan.reserve == (PartQty(FILTER, 1), PartQty(OIL, 1), PartQty(COIL, 1))


def test_full_reservation_reserves_only_what_is_outstanding() -> None:
    lines = [line(FILTER, 2, reserved=1), line(OIL, 1, reserved=1)]
    plan = plan_full_reservation(lines, balances(filter=(5, 1), oil=(1, 1)))
    assert plan.short == ()
    assert plan.reserve == (PartQty(FILTER, 1),)
    assert plan_full_reservation([], {}).reserve == ()  # labour-only job (D31)


def test_receipt_reservation_caps_at_outstanding_and_keeps_the_excess_general() -> None:
    lines = [line(COIL, 2), line(OIL, 1, reserved=1)]
    received = [PartQty(COIL, 5), PartQty(OIL, 3), PartQty(FILTER, 2)]
    stock = balances(coil=(5, 0), oil=(4, 1), filter=(2, 0))
    assert plan_receipt_reservation(lines, stock, received) == (PartQty(COIL, 2),)


def test_partial_receipt_reserves_what_arrived() -> None:
    reserve = plan_receipt_reservation([line(COIL, 2)], balances(coil=(1, 0)), [PartQty(COIL, 1)])
    assert reserve == (PartQty(COIL, 1),)
    assert not all_fully_reserved([line(COIL, 2, reserved=1)])
    assert all_fully_reserved([line(COIL, 2, reserved=2), line(OIL, 1, consumed=1)])
    assert all_fully_reserved([])


def test_receipt_reservation_never_exceeds_available_stock() -> None:
    # Defensive cap: available is normally raised by the receipt itself.
    reserve = plan_receipt_reservation([line(COIL, 4)], balances(coil=(3, 2)), [PartQty(COIL, 3)])
    assert reserve == (PartQty(COIL, 1),)


def test_inv11_consumption_takes_every_required_quantity() -> None:
    lines = [line(FILTER, 1, reserved=1), line(OIL, 1, reserved=1), line(COIL, 1, reserved=1)]
    stock = balances(filter=(10, 1), oil=(8, 1), coil=(1, 1))
    assert plan_consumption(lines, stock) == (PartQty(FILTER, 1), PartQty(OIL, 1), PartQty(COIL, 1))
    assert plan_consumption([], {}) == ()


@pytest.mark.parametrize(
    "rows",
    [
        [line(COIL, 2, reserved=1)],  # partly reserved
        [line(COIL, 1)],  # nothing reserved
        [line(COIL, 1, consumed=1)],  # consumed already: no second allocation
    ],
)
def test_inv12_consumption_needs_full_reservations(rows: list[BookingPartLine]) -> None:
    with pytest.raises(InsufficientStock):
        plan_consumption(rows, balances(coil=(5, 2)))


def test_consumption_refuses_reservations_that_are_no_longer_on_hand() -> None:
    with pytest.raises(InsufficientStock):
        plan_consumption([line(COIL, 2, reserved=2)], balances(coil=(1, 1)))


def test_inv13_release_returns_every_reservation() -> None:
    lines = [line(FILTER, 1, reserved=1), line(OIL, 2, reserved=2), line(COIL, 1)]
    assert plan_release(lines) == (PartQty(FILTER, 1), PartQty(OIL, 2))


# --- Adjustments (D82, INV-25) ------------------------------------------------------------------


def test_inv25_adjustment_below_reserved_or_zero_is_insufficient_stock() -> None:
    assert adjusted_on_hand(on_hand=10, reserved=3, quantity_delta=-7) == 3
    with pytest.raises(InsufficientStock) as caught:
        adjusted_on_hand(on_hand=10, reserved=3, quantity_delta=-8)
    assert "lowest allowed change is -7" in caught.value.detail
    with pytest.raises(InsufficientStock):
        adjusted_on_hand(on_hand=2, reserved=0, quantity_delta=-3)


def test_adjustment_above_the_integer_column_is_422() -> None:
    with pytest.raises(ValidationFailed) as caught:
        adjusted_on_hand(on_hand=MAX_ON_HAND, reserved=0, quantity_delta=1)
    assert codes(caught.value) == [("quantity_delta", "value_error")]


# --- Purchase orders (D43, spec 02 §6) -----------------------------------------------------------


@pytest.mark.parametrize(
    ("quantities", "expected"),
    [
        ([(2, 0), (1, 0)], PurchaseOrderStatus.ORDERED),
        ([(2, 1), (1, 0)], PurchaseOrderStatus.PARTIALLY_RECEIVED),
        ([(2, 2), (1, 0)], PurchaseOrderStatus.PARTIALLY_RECEIVED),
        ([(2, 2), (1, 1)], PurchaseOrderStatus.RECEIVED),
    ],
)
def test_purchase_order_status_follows_its_items(
    quantities: list[tuple[int, int]], expected: PurchaseOrderStatus
) -> None:
    assert purchase_order_status(quantities) is expected


ITEM_A = UUID("00000000-0000-4000-8000-00000000000a")
ITEM_B = UUID("00000000-0000-4000-8000-00000000000b")
ITEMS = [
    OrderedItem(item_id=ITEM_A, part_id=COIL, ordered_qty=2, received_qty=1),
    OrderedItem(item_id=ITEM_B, part_id=OIL, ordered_qty=3, received_qty=0),
]


def test_receipt_plan_keeps_only_positive_quantities() -> None:
    plan = plan_receipt(
        PurchaseOrderStatus.PARTIALLY_RECEIVED,
        ITEMS,
        [ReceiptLine(ITEM_A, 1, expected_received_qty=1), ReceiptLine(ITEM_B, 0)],
    )
    assert plan == (ReceiptPart(item_id=ITEM_A, part_id=COIL, quantity=1),)


def test_inv07_receiving_a_received_po_is_conflict_before_anything_else() -> None:
    with pytest.raises(Conflict):
        plan_receipt(PurchaseOrderStatus.RECEIVED, ITEMS, [ReceiptLine(uuid.uuid4(), 99)])


def test_receipt_validation_order_reference_then_concurrency_then_quantities() -> None:
    unknown = uuid.uuid4()
    # invalid_reference (422) is reported before a stale expected_received_qty (409) ...
    with pytest.raises(ValidationFailed) as caught:
        plan_receipt(
            PurchaseOrderStatus.ORDERED,
            ITEMS,
            [ReceiptLine(ITEM_A, 9, expected_received_qty=0), ReceiptLine(unknown, 1)],
        )
    assert codes(caught.value) == [("items.1.item_id", "invalid_reference")]
    # ... and the stale expectation (409) before an excessive quantity (422).
    with pytest.raises(ConcurrentUpdate):
        plan_receipt(
            PurchaseOrderStatus.ORDERED, ITEMS, [ReceiptLine(ITEM_A, 9, expected_received_qty=0)]
        )


def test_inv28_a_repeated_receipt_with_the_same_expectation_is_concurrent_update() -> None:
    after_first = [OrderedItem(item_id=ITEM_A, part_id=COIL, ordered_qty=2, received_qty=1)]
    with pytest.raises(ConcurrentUpdate):
        plan_receipt(
            PurchaseOrderStatus.PARTIALLY_RECEIVED,
            after_first,
            [ReceiptLine(ITEM_A, 1, expected_received_qty=0)],
        )


def test_inv07_quantities_above_outstanding_are_all_reported() -> None:
    with pytest.raises(ValidationFailed) as caught:
        plan_receipt(
            PurchaseOrderStatus.PARTIALLY_RECEIVED,
            ITEMS,
            [ReceiptLine(ITEM_A, 2), ReceiptLine(ITEM_B, 4)],
        )
    assert codes(caught.value) == [
        ("items.0.quantity", "exceeds_outstanding"),
        ("items.1.quantity", "exceeds_outstanding"),
    ]


def test_all_zero_quantities_are_nothing_to_receive() -> None:
    with pytest.raises(ValidationFailed) as caught:
        plan_receipt(
            PurchaseOrderStatus.ORDERED, ITEMS, [ReceiptLine(ITEM_A, 0), ReceiptLine(ITEM_B, 0)]
        )
    assert codes(caught.value) == [("items", "nothing_to_receive")]


def test_receipts_may_not_push_on_hand_past_the_integer_column() -> None:
    plan = (ReceiptPart(item_id=ITEM_A, part_id=COIL, quantity=2),)
    errors = receipt_on_hand_errors(
        plan, {ITEM_A: 3}, {COIL: PartBalance(part_id=COIL, on_hand=MAX_ON_HAND - 1, reserved=0)}
    )
    assert [(error["field"], error["code"]) for error in errors] == [
        ("items.3.quantity", "value_error")
    ]
    fine = {COIL: PartBalance(part_id=COIL, on_hand=0, reserved=0)}
    assert receipt_on_hand_errors(plan, {ITEM_A: 0}, fine) == []


# --- The ledger (D42, D79; INV-01, INV-26) --------------------------------------------------------


@pytest.mark.parametrize(
    ("movement_type", "expected"),
    [
        (StockMovementType.RECEIVE, (3, 0)),
        (StockMovementType.RESERVE, (0, 3)),
        (StockMovementType.RELEASE, (0, -3)),
        (StockMovementType.CONSUME, (-3, -3)),
    ],
)
def test_movement_deltas_match_the_ledger_check(
    movement_type: StockMovementType, expected: tuple[int, int]
) -> None:
    assert movement_deltas(movement_type, 3) == expected


def test_movement_deltas_refuse_adjustments_and_non_positive_quantities() -> None:
    with pytest.raises(ValueError, match="signed delta"):
        movement_deltas(StockMovementType.ADJUST, 3)
    with pytest.raises(ValueError, match="positive"):
        movement_deltas(StockMovementType.RECEIVE, 0)


def entry(
    movement_type: StockMovementType, part_id: UUID, quantity: int, booking: UUID | None = None
) -> LedgerEntry:
    if movement_type == StockMovementType.ADJUST:
        deltas = (quantity, 0)
        quantity = abs(quantity)
    else:
        deltas = movement_deltas(movement_type, quantity)
    return LedgerEntry(
        part_id=part_id,
        movement_type=movement_type,
        quantity=quantity,
        on_hand_delta=deltas[0],
        reserved_delta=deltas[1],
        booking_id=booking,
    )


# The worked example's ledger: opening stock, order-parts, receipt + reservation, allocation.
WORKED_EXAMPLE_LEDGER = [
    entry(StockMovementType.ADJUST, FILTER, 10),
    entry(StockMovementType.ADJUST, OIL, 8),
    entry(StockMovementType.RESERVE, FILTER, 1, BOOKING),
    entry(StockMovementType.RESERVE, OIL, 1, BOOKING),
    entry(StockMovementType.RECEIVE, COIL, 1),
    entry(StockMovementType.RESERVE, COIL, 1, BOOKING),
    entry(StockMovementType.CONSUME, FILTER, 1, BOOKING),
    entry(StockMovementType.CONSUME, OIL, 1, BOOKING),
    entry(StockMovementType.CONSUME, COIL, 1, BOOKING),
]


def test_inv01_ledger_sums_reproduce_the_worked_example_balances() -> None:
    assert ledger_balances(WORKED_EXAMPLE_LEDGER) == {
        FILTER: (9, 0),
        OIL: (7, 0),
        COIL: (0, 0),
    }
    assert booking_ledger(WORKED_EXAMPLE_LEDGER) == {
        (BOOKING, FILTER): (0, 1),
        (BOOKING, OIL): (0, 1),
        (BOOKING, COIL): (0, 1),
    }


def test_inv01_balances_keep_parts_whose_sums_are_zero() -> None:
    ledger = [
        entry(StockMovementType.ADJUST, COIL, 2),
        entry(StockMovementType.ADJUST, COIL, -2),
    ]
    assert ledger_balances(ledger) == {COIL: (0, 0)}


def test_inv26_ledger_checks_are_order_free() -> None:
    expected_parts = ledger_balances(WORKED_EXAMPLE_LEDGER)
    expected_bookings = booking_ledger(WORKED_EXAMPLE_LEDGER)
    shuffler = random.Random(2026)  # noqa: S311 - deterministic shuffles, not security
    for _ in range(50):
        rows = list(WORKED_EXAMPLE_LEDGER)
        shuffler.shuffle(rows)
        assert ledger_balances(rows) == expected_parts
        assert booking_ledger(rows) == expected_bookings


def test_inv26_every_permutation_of_one_actions_rows_gives_the_same_verdict() -> None:
    order_parts = WORKED_EXAMPLE_LEDGER[2:4]  # one action: two RESERVE rows sharing created_at
    expected = ledger_balances(WORKED_EXAMPLE_LEDGER)
    for permutation in itertools.permutations(order_parts):
        rows = [*WORKED_EXAMPLE_LEDGER[:2], *permutation, *WORKED_EXAMPLE_LEDGER[4:]]
        assert ledger_balances(rows) == expected


def test_inv26_running_balance_ends_at_the_parts_balance() -> None:
    coil = [row for row in WORKED_EXAMPLE_LEDGER if row.part_id == COIL]
    assert running_balances(coil) == [(1, 0), (1, 1), (0, 0)]
    assert running_balances([]) == []

"""The booking-facing inventory services (spec 08 T12-T16, T22; `modules/inventory.md`), called the
way bookings will call them: inside one transaction that holds the booking row lock.

INV-02, INV-03, INV-04, INV-10, INV-11, INV-12, INV-13, INV-26 (one instant per action), INV-27,
SEC-45 (inventory half), the inventory halves of SM-11, SM-13 and EST-18, and the reads used by
estimates, bookings and reporting.
"""

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.database import Database
from app.core.errors import Conflict, InsufficientStock, ValidationFailed
from app.modules.inventory import service as inventory_service
from app.modules.inventory.domain.stock import PartQty
from app.modules.inventory.models import Part, PurchaseOrder, PurchaseOrderItem, StockMovement
from app.shared.clock import SimulatedClock, utcnow
from app.shared.enums import PurchaseOrderStatus, StockState
from tests.modules.inventory.support import (
    Team,
    World,
    allocate_parts,
    assert_ledger_invariants,
    assign_parts,
    bearer,
    booking_rows,
    cancel_reservations,
    lock_booking,
    mark_parts_ready,
    movements_of,
    new_part,
    order_missing,
    order_parts,
    part_balance,
    parts_pending_booking,
    qty,
    reserve_for_booking,
    transaction,
    url,
)

pytestmark = pytest.mark.db


# --- Helpers: one booking action's inventory side effect per transaction ------------------------


async def worked_example_parts(api: httpx.AsyncClient, team: Team) -> dict[str, dict[str, Any]]:
    """Spec 08 "Parts reservations": filter 10 @ 900, engine oil 8 @ 5,200, ignition coil 0."""
    return {
        "filter": await new_part(api, team, "OIL-FLT-01", name="Oil filter", stock=10),
        "oil": await new_part(
            api, team, "ENG-OIL-4L", name="Engine oil 4 L", unit_cost="5200", stock=8
        ),
        "coil": await new_part(api, team, "IGN-COIL-01", name="Ignition coil", unit_cost="6500"),
    }


async def counts(db: Database) -> tuple[int, int]:
    async with db.sessionmaker() as session:
        movements = (
            await session.execute(select(func.count()).select_from(StockMovement))
        ).scalar_one()
        orders = (
            await session.execute(select(func.count()).select_from(PurchaseOrder))
        ).scalar_one()
        return int(movements), int(orders)


def by_part(quantities: Any) -> list[PartQty]:
    return sorted(quantities, key=lambda item: item.part_id)


def error_fields(error: ValidationFailed) -> list[tuple[str, str]]:
    assert error.errors is not None
    return [(item["field"], item["code"]) for item in error.errors]


# --- T12 assign-parts-person ---------------------------------------------------------------------


async def test_t12_rows_sum_the_approved_part_lines_per_part(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    parts = await worked_example_parts(api, world.a)
    booking = await parts_pending_booking(db, world)
    before = await counts(db)
    await assign_parts(
        db,
        world.a,
        booking.id,
        [
            qty(parts["filter"], 1),
            qty(parts["oil"], 1),
            qty(parts["filter"], 2),
            qty(parts["coil"], 1),
        ],
    )
    rows = await booking_rows(db, booking.id)
    assert {
        part_id: (row.required_qty, row.reserved_qty, row.consumed_qty)
        for part_id, row in rows.items()
    } == {
        UUID(parts["filter"]["id"]): (3, 0, 0),
        UUID(parts["oil"]["id"]): (1, 0, 0),
        UUID(parts["coil"]["id"]): (1, 0, 0),
    }
    assert await counts(db) == before  # no stock change, no PO
    labour_only = await parts_pending_booking(db, world)
    await assign_parts(db, world.a, labour_only.id, [])
    assert await booking_rows(db, labour_only.id) == {}


async def test_t12_requirements_must_be_positive(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "X1")
    booking = await parts_pending_booking(db, world)
    with pytest.raises(ValueError, match="positive"):
        await assign_parts(db, world.a, booking.id, [qty(part, 0)])
    assert await booking_rows(db, booking.id) == {}


async def test_sec45_a_booking_part_cannot_reference_another_shops_part(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    theirs = await new_part(api, world.b, "THEIRS")
    booking = await parts_pending_booking(db, world)
    with pytest.raises(IntegrityError) as caught:
        await assign_parts(db, world.a, booking.id, [qty(theirs, 1)])
    assert "fk_booking_parts_shop_id_part_id_parts" in str(caught.value)


# --- T13 order-parts -----------------------------------------------------------------------------


async def test_inv02_inv26_order_parts_reserves_what_is_available_and_orders_the_shortage(
    api: httpx.AsyncClient, world: World, db: Database, stepping_clock: SimulatedClock
) -> None:
    parts = await worked_example_parts(api, world.a)
    booking, result = await order_parts(
        db, world.a, world.customer, {parts[name]["id"]: 1 for name in ("filter", "oil", "coil")}
    )
    assert list(result.reserved) == by_part([qty(parts["filter"], 1), qty(parts["oil"], 1)])
    assert [await part_balance(db, parts[name]["id"]) for name in ("filter", "oil", "coil")] == [
        (10, 1),
        (8, 1),
        (0, 0),
    ]
    response = await api.get(
        url(world.a.id, f"/purchase-orders/{result.purchase_order_id}"),
        headers=bearer(world.a.parts),
    )
    body = response.json()
    assert (body["po_number"], body["status"], body["supplier_name"]) == (
        result.po_number,
        "ORDERED",
        "City Auto Parts",
    )
    assert body["booking"]["id"] == str(booking.id)
    assert body["created_by"]["user_id"] == str(world.a.parts.id)
    assert [(i["part"]["sku"], i["ordered_qty"], i["unit_cost"]) for i in body["items"]] == [
        ("IGN-COIL-01", 1, "6500.00")
    ]
    rows = await booking_rows(db, booking.id)
    assert {name: rows[UUID(parts[name]["id"])].reserved_qty for name in parts} == {
        "filter": 1,
        "oil": 1,
        "coil": 0,
    }
    reservations = [
        movement
        for name in ("filter", "oil")
        for movement in await movements_of(db, parts[name]["id"])
        if movement.movement_type == "RESERVE"
    ]
    assert {(m.booking_id, m.purchase_order_id, m.actor_user_id) for m in reservations} == {
        (booking.id, None, world.a.parts.id)
    }
    # INV-26 / D63 under a clock that moves on every reading: one action, one instant.
    [instant] = {m.created_at for m in reservations}
    async with db.sessionmaker() as session:
        order = await session.get(PurchaseOrder, result.purchase_order_id)
        assert order is not None
        items = (
            (
                await session.execute(
                    select(PurchaseOrderItem).where(
                        PurchaseOrderItem.purchase_order_id == result.purchase_order_id
                    )
                )
            )
            .scalars()
            .all()
        )
        touched = [await session.get(Part, UUID(parts[name]["id"])) for name in ("filter", "oil")]
    assert {order.created_at, order.updated_at} == {instant}
    assert {item.created_at for item in items} | {item.updated_at for item in items} == {instant}
    assert {part.updated_at for part in touched if part is not None} == {instant}
    assert {rows[UUID(parts[name]["id"])].updated_at for name in ("filter", "oil")} == {instant}
    [opening] = [m for m in await movements_of(db, parts["filter"]["id"]) if m.note]
    assert opening.created_at < instant  # the clock did move between actions
    await assert_ledger_invariants(db)


async def test_inv03_nothing_short_is_conflict_and_nothing_is_written(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "OIL-FLT-01", stock=10)
    for requirements in ([qty(part, 2)], []):  # stock covers it / a labour-only job
        booking = await parts_pending_booking(db, world)
        await assign_parts(db, world.a, booking.id, requirements)
        before = await counts(db)
        with pytest.raises(Conflict, match="mark-parts-ready"):
            await order_missing(db, world.a, booking.id)
        assert await counts(db) == before
    assert await part_balance(db, part["id"]) == (10, 0)


async def test_inv04_inv27_item_errors_are_reported_together_and_write_nothing(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    parts = await worked_example_parts(api, world.a)
    booking = await parts_pending_booking(db, world)
    await assign_parts(db, world.a, booking.id, [qty(parts["filter"], 1), qty(parts["coil"], 2)])
    before = await counts(db)
    with pytest.raises(ValidationFailed) as caught:
        await order_missing(
            db, world.a, booking.id, items=[qty(parts["filter"], 1), qty(parts["coil"], 1)]
        )
    assert error_fields(caught.value) == [
        ("items.0.part_id", "not_short"),
        ("items.1.quantity", "below_shortage"),
    ]
    assert await counts(db) == before
    assert all(row.reserved_qty == 0 for row in (await booking_rows(db, booking.id)).values())


async def test_order_parts_may_order_more_and_inactive_parts_can_still_be_ordered(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    coil = await new_part(api, world.a, "IGN-COIL-01")
    await api.patch(
        url(world.a.id, f"/parts/{coil['id']}"),
        json={"is_active": False},
        headers=bearer(world.a.owner),
    )
    _, result = await order_parts(
        db, world.a, world.customer, {coil["id"]: 2}, items=[qty(coil, 5)]
    )
    response = await api.get(
        url(world.a.id, f"/purchase-orders/{result.purchase_order_id}"),
        headers=bearer(world.a.parts),
    )
    assert response.json()["items"][0]["ordered_qty"] == 5
    assert result.reserved == ()


async def test_order_parts_too_expensive_for_money_is_422(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    big = await new_part(api, world.a, "BIG", unit_cost="9999999999")
    booking = await parts_pending_booking(db, world)
    await assign_parts(db, world.a, booking.id, [qty(big, 2)])
    with pytest.raises(ValidationFailed) as caught:
        await order_missing(db, world.a, booking.id, supplier_name="  ")
    assert error_fields(caught.value) == [("items", "value_error")]
    small = await new_part(api, world.a, "SMALL", unit_cost="1")
    mixed = await parts_pending_booking(db, world)
    await assign_parts(db, world.a, mixed.id, [qty(small, 1), qty(big, 1)])
    with pytest.raises(ValidationFailed) as caught:
        await order_missing(db, world.a, mixed.id, items=[qty(small, 1), qty(big, 2)])
    assert error_fields(caught.value) == [("items.1.quantity", "value_error")]
    assert await counts(db) == (0, 0)  # nothing reserved, no purchase order


# --- T14 mark-parts-ready -----------------------------------------------------------------------


async def test_inv10_mark_parts_ready_is_all_or_nothing(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    parts = await worked_example_parts(api, world.a)
    booking = await parts_pending_booking(db, world)
    await assign_parts(db, world.a, booking.id, [qty(parts["filter"], 1), qty(parts["coil"], 1)])
    before = await counts(db)
    with pytest.raises(InsufficientStock) as caught:
        await mark_parts_ready(db, world.a, booking.id)
    assert "IGN-COIL-01 Ignition coil (short 1)" in caught.value.detail
    assert await counts(db) == before
    assert await part_balance(db, parts["filter"]["id"]) == (10, 0)
    await api.post(
        url(world.a.id, f"/parts/{parts['coil']['id']}/adjustments"),
        json={"quantity_delta": 1, "reason": "Delivered"},
        headers=bearer(world.a.parts),
    )
    reserved = await mark_parts_ready(db, world.a, booking.id)
    assert by_part(reserved) == by_part([qty(parts["filter"], 1), qty(parts["coil"], 1)])
    assert await part_balance(db, parts["coil"]["id"]) == (1, 1)
    await assert_ledger_invariants(db)


async def test_sm13_a_labour_only_job_passes_the_parts_steps(world: World, db: Database) -> None:
    booking = await parts_pending_booking(db, world)
    await assign_parts(db, world.a, booking.id, [])
    assert await mark_parts_ready(db, world.a, booking.id) == ()
    assert await allocate_parts(db, world.a, booking.id) == ()
    assert await cancel_reservations(db, world.a, booking.id, world.customer) == ()
    summary = await summaries(db, world.a, [booking.id])
    assert summary[booking.id].model_dump() == {
        "required_count": 0,
        "available_count": 0,
        "shortage_count": 0,
        "all_available": True,
    }


# --- T15 receipt reservation (called by the bookings handler) ------------------------------------


async def test_t15_received_stock_is_reserved_up_to_the_outstanding_quantity(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    coil = await new_part(api, world.a, "IGN-COIL-01")
    filt = await new_part(api, world.a, "OIL-FLT-01", stock=3)
    booking, ordered = await order_parts(db, world.a, world.customer, {coil["id"]: 2})
    await api.post(  # stock that a receipt would have brought in
        url(world.a.id, f"/parts/{coil['id']}/adjustments"),
        json={"quantity_delta": 5, "reason": "Arrived"},
        headers=bearer(world.a.parts),
    )

    async def reserve_received(received: list[PartQty]) -> Any:
        async with transaction(db) as uow:
            await lock_booking(uow.session, booking.id)
            return await inventory_service.reserve_received_for_booking(
                uow,
                shop_id=world.a.id,
                booking_id=booking.id,
                purchase_order_id=ordered.purchase_order_id,
                received=received,
                actor_user_id=world.a.parts2.id,
                now=utcnow(),
            )

    first = await reserve_received([qty(coil, 1), qty(filt, 2)])  # the filter is not on this job
    assert (first.reserved, first.all_reserved) == ((qty(coil, 1),), False)
    second = await reserve_received([qty(coil, 4)])
    assert (second.reserved, second.all_reserved) == ((qty(coil, 1),), True)
    third = await reserve_received([qty(coil, 1)])
    assert (third.reserved, third.all_reserved) == ((), True)
    assert await part_balance(db, coil["id"]) == (5, 2)
    assert await part_balance(db, filt["id"]) == (3, 0)
    reservations = [m for m in await movements_of(db, coil["id"]) if m.movement_type == "RESERVE"]
    assert {(m.booking_id, m.purchase_order_id) for m in reservations} == {
        (booking.id, ordered.purchase_order_id)
    }
    await assert_ledger_invariants(db)


# --- T16 allocate-parts and T22 cancel ------------------------------------------------------------


async def test_inv11_allocation_consumes_every_reservation(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    parts = await worked_example_parts(api, world.a)
    await api.post(
        url(world.a.id, f"/parts/{parts['coil']['id']}/adjustments"),
        json={"quantity_delta": 1, "reason": "Received the coil"},
        headers=bearer(world.a.parts),
    )
    booking = await reserve_for_booking(
        db, world.a, world.customer, {part["id"]: 1 for part in parts.values()}
    )
    consumed = await allocate_parts(db, world.a, booking.id)
    assert by_part(consumed) == by_part(qty(part, 1) for part in parts.values())
    assert [await part_balance(db, parts[name]["id"]) for name in ("filter", "oil", "coil")] == [
        (9, 0),
        (7, 0),
        (0, 0),
    ]
    rows = await booking_rows(db, booking.id)
    assert {(r.required_qty, r.reserved_qty, r.consumed_qty) for r in rows.values()} == {(1, 0, 1)}
    assert [m.movement_type for m in await movements_of(db, parts["coil"]["id"])][-1] == "CONSUME"
    await assert_ledger_invariants(db)


async def test_inv12_allocation_needs_every_part_fully_reserved(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    parts = await worked_example_parts(api, world.a)
    booking, _ = await order_parts(
        db, world.a, world.customer, {parts["filter"]["id"]: 1, parts["coil"]["id"]: 1}
    )
    before = await counts(db)
    with pytest.raises(InsufficientStock):
        await allocate_parts(db, world.a, booking.id)
    assert await counts(db) == before
    assert await part_balance(db, parts["filter"]["id"]) == (10, 1)


async def test_inv13_sm11_cancel_releases_every_reservation_and_leaves_the_po_open(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    parts = await worked_example_parts(api, world.a)
    booking, ordered = await order_parts(
        db, world.a, world.customer, {parts[name]["id"]: 1 for name in ("filter", "oil", "coil")}
    )
    released = await cancel_reservations(db, world.a, booking.id, world.customer)
    assert by_part(released) == by_part([qty(parts["filter"], 1), qty(parts["oil"], 1)])
    assert [await part_balance(db, parts[name]["id"]) for name in ("filter", "oil", "coil")] == [
        (10, 0),
        (8, 0),
        (0, 0),
    ]
    releases = [
        m for m in await movements_of(db, parts["filter"]["id"]) if m.movement_type == "RELEASE"
    ]
    assert [(m.booking_id, m.actor_user_id, m.reserved_delta) for m in releases] == [
        (booking.id, world.customer.id, -1)
    ]
    async with db.sessionmaker() as session:
        stored = await session.get(PurchaseOrder, ordered.purchase_order_id)
        assert stored is not None
        assert stored.status == PurchaseOrderStatus.ORDERED  # D24: linked POs stay open
    assert (
        await cancel_reservations(db, world.a, booking.id, world.customer) == ()
    )  # nothing left to release
    await assert_ledger_invariants(db)


# --- Reads for other modules ----------------------------------------------------------------------


async def summaries(db: Database, team: Team, booking_ids: list[UUID]) -> dict[UUID, Any]:
    async with db.sessionmaker() as session:
        return await inventory_service.get_booking_parts_summary(
            session, shop_id=team.id, booking_ids=booking_ids
        )


async def test_inv16_booking_parts_read_compares_required_with_stock(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    parts = await worked_example_parts(api, world.a)
    booking, ordered = await order_parts(
        db,
        world.a,
        world.customer,
        {parts["coil"]["id"]: 2, parts["filter"]["id"]: 1, parts["oil"]["id"]: 1},
    )
    async with db.sessionmaker() as session:
        read = await inventory_service.get_booking_parts(
            session, shop_id=world.a.id, booking_id=booking.id
        )
    assert (read.booking_id, read.required_count, read.available_count, read.all_available) == (
        booking.id,
        3,
        2,
        False,
    )
    assert [item.part.sku for item in read.items] == ["ENG-OIL-4L", "IGN-COIL-01", "OIL-FLT-01"]
    coil = read.items[1]
    assert (
        coil.required_qty,
        coil.reserved_qty,
        coil.consumed_qty,
        coil.outstanding_qty,
        coil.shortage_qty,
    ) == (2, 0, 0, 2, 2)
    assert (coil.part.available, coil.part.stock_state) == (0, StockState.OUT)
    filt = read.items[2]
    assert (filt.reserved_qty, filt.outstanding_qty, filt.shortage_qty, filt.part.available) == (
        1,
        0,
        0,
        9,
    )
    [po_ref] = read.purchase_orders
    assert (po_ref.id, po_ref.po_number, po_ref.status) == (
        ordered.purchase_order_id,
        ordered.po_number,
        PurchaseOrderStatus.ORDERED,
    )
    assert (po_ref.ordered_qty_total, po_ref.received_qty_total) == (2, 0)
    async with db.sessionmaker() as session:
        empty = await inventory_service.get_booking_parts(
            session, shop_id=world.a.id, booking_id=uuid4()
        )
    assert (empty.items, empty.purchase_orders, empty.all_available, empty.required_count) == (
        [],
        [],
        True,
        0,
    )


async def test_inv16_parts_summaries_are_batched_with_one_entry_per_booking(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    parts = await worked_example_parts(api, world.a)
    short = await parts_pending_booking(db, world)
    await assign_parts(
        db,
        world.a,
        short.id,
        [qty(parts["filter"], 1), qty(parts["oil"], 1), qty(parts["coil"], 1)],
    )
    covered = await parts_pending_booking(db, world)
    await assign_parts(db, world.a, covered.id, [qty(parts["filter"], 2)])
    unknown = uuid4()
    result = await summaries(db, world.a, [short.id, covered.id, unknown])
    assert set(result) == {short.id, covered.id, unknown}
    assert result[short.id].model_dump() == {
        "required_count": 3,
        "available_count": 2,
        "shortage_count": 1,
        "all_available": False,
    }
    assert result[covered.id].all_available is True
    assert result[unknown].model_dump() == {
        "required_count": 0,
        "available_count": 0,
        "shortage_count": 0,
        "all_available": True,
    }
    other_shop = await summaries(db, world.b, [short.id])  # scoped by shop: no rows there
    assert other_shop[short.id].required_count == 0


async def test_est18_parts_for_estimate_show_live_stock_and_hide_it_from_qc(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    parts = await worked_example_parts(api, world.a)
    retired = await new_part(api, world.a, "RETIRED", stock=1)
    await api.patch(
        url(world.a.id, f"/parts/{retired['id']}"),
        json={"is_active": False},
        headers=bearer(world.a.owner),
    )
    theirs = await new_part(api, world.b, "THEIRS")
    await reserve_for_booking(db, world.a, world.customer, {parts["filter"]["id"]: 3})
    ids = [UUID(parts["filter"]["id"]), UUID(retired["id"]), UUID(theirs["id"]), uuid4()]
    async with db.sessionmaker() as session:
        live = await inventory_service.get_parts_for_estimate(
            session, shop_id=world.a.id, part_ids=ids
        )
        hidden = await inventory_service.get_parts_for_estimate(
            session, shop_id=world.a.id, part_ids=set(ids), include_stock=False
        )
    assert set(live) == {UUID(parts["filter"]["id"]), UUID(retired["id"])}
    filt = live[UUID(parts["filter"]["id"])]
    assert (filt.on_hand, filt.reserved, filt.available, filt.stock_state, filt.unit_cost) == (
        10,
        3,
        7,
        StockState.OK,
        Decimal("900.00"),
    )
    assert live[UUID(retired["id"])].is_active is False
    qc_view = hidden[UUID(parts["filter"]["id"])]
    assert (
        qc_view.on_hand,
        qc_view.reserved,
        qc_view.available,
        qc_view.reorder_level,
        qc_view.stock_state,
    ) == (None, None, None, None, None)
    assert (qc_view.sku, qc_view.name, qc_view.unit_cost) == (
        "OIL-FLT-01",
        "Oil filter",
        Decimal("900.00"),
    )


async def test_stock_summary_counts_active_parts_only(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    coil = await new_part(api, world.a, "IGN-COIL-01", unit_cost="6500", reorder_level=1)  # OUT
    pads = await new_part(
        api, world.a, "BRK-PAD-F", unit_cost="4000", reorder_level=2, stock=2
    )  # LOW
    await new_part(api, world.a, "BRK-DSC-F", unit_cost="9000", stock=1, reorder_level=3)  # LOW
    await new_part(api, world.a, "OIL-FLT-01", unit_cost="900", stock=10)  # OK
    retired = await new_part(api, world.a, "AAA-OLD", unit_cost="100")  # OUT, but inactive
    await api.patch(
        url(world.a.id, f"/parts/{retired['id']}"),
        json={"is_active": False},
        headers=bearer(world.a.owner),
    )
    open_order = await api.post(
        url(world.a.id, "/purchase-orders"),
        json={"items": [{"part_id": coil["id"], "quantity": 2}]},
        headers=bearer(world.a.parts),
    )
    assert open_order.status_code == 201
    done = await api.post(
        url(world.a.id, "/purchase-orders"),
        json={"items": [{"part_id": pads["id"], "quantity": 1}]},
        headers=bearer(world.a.parts),
    )
    received = await api.post(
        url(world.a.id, f"/purchase-orders/{done.json()['id']}/receive"),
        json={"items": [{"item_id": done.json()["items"][0]["id"], "quantity": 1}]},
        headers=bearer(world.a.parts),
    )
    assert received.status_code == 200
    async with db.sessionmaker() as session:
        summary = await inventory_service.get_stock_summary(session, shop_id=world.a.id)
        empty = await inventory_service.get_stock_summary(session, shop_id=world.b.id)
    # The pads PO raised them to 3 on hand (LOW at reorder level 2 → OK at 3).
    assert (summary.parts_count, summary.low_stock_count, summary.out_of_stock_count) == (4, 2, 1)
    assert summary.stock_value == Decimal("30000.00")  # 3 x 4,000 + 1 x 9,000 + 10 x 900
    assert summary.open_purchase_orders == 1
    assert [p.sku for p in summary.low_stock] == ["IGN-COIL-01", "BRK-DSC-F"]
    assert summary.low_stock[0].on_order == 2
    assert (empty.parts_count, empty.stock_value, empty.low_stock) == (0, Decimal("0.00"), [])


async def test_stock_summary_lists_at_most_five_low_parts(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    for index in range(7):
        await new_part(api, world.a, f"LOW-{index}", reorder_level=10, stock=index)
    async with db.sessionmaker() as session:
        summary = await inventory_service.get_stock_summary(session, shop_id=world.a.id)
    assert summary.low_stock_count == 7
    assert [p.sku for p in summary.low_stock] == ["LOW-0", "LOW-1", "LOW-2", "LOW-3", "LOW-4"]


async def test_count_low_stock_per_shop(api: httpx.AsyncClient, world: World, db: Database) -> None:
    await new_part(api, world.a, "OUT")
    await new_part(api, world.a, "LOW", reorder_level=5, stock=1)
    await new_part(api, world.a, "OK", stock=1)
    await new_part(api, world.b, "FINE", stock=3)
    async with db.sessionmaker() as session:
        result = await inventory_service.count_low_stock(session, shop_ids=[world.a.id, world.b.id])
        nothing = await inventory_service.count_low_stock(session, shop_ids=[])
    assert result == {world.a.id: 2, world.b.id: 0}
    assert nothing == {}

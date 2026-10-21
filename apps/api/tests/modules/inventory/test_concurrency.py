"""Row locks under real concurrency (spec 12 §3.5 lock gate, `tests/lockgate.py`; D30, D43, D82).

`run_in_order` makes every race deterministic: the gate holds `SELECT … FOR UPDATE` on the
contended row from its own connection, racer A starts and queues on it, then racer B starts and
queues behind A (both proven through `pg_stat_activity`), and only then the gate releases.
PostgreSQL hands a row lock to its waiters in arrival order (a waiter first takes the tuple lock,
then waits for the holder), so A always runs first and B sees A's committed result. Races whose
outcome depends on the order are run in both orders.

INV-19, CON-04 (P1), concurrent receipts of one PO (INV-07, INV-28), concurrent adjustments and an
adjustment racing a reservation (INV-25).
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import httpx
import pytest

from app.core.database import Database
from app.core.errors import InsufficientStock
from app.modules.inventory import service as inventory_service
from app.shared.clock import utcnow
from app.shared.enums import BookingStatus
from tests.lockgate import hold_row_lock, wait_for_lock_waiters
from tests.modules.inventory.support import (
    FakeBookings,
    World,
    assert_ledger_invariants,
    assert_problem,
    assign_parts,
    bearer,
    booking_rows,
    booking_status,
    cancel_booking,
    field_codes,
    lock_booking,
    mark_parts_ready,
    movements_of,
    new_part,
    order_parts,
    part_balance,
    parts_pending_booking,
    qty,
    transaction,
    url,
)

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

Racer = Callable[[], Awaitable[Any]]


async def run_in_order(
    db: Database, table: str, row_id: UUID | str, first: Racer, second: Racer
) -> tuple[Any, Any]:
    """Run `first` then `second` against a row both need, each in its own transaction; returns
    their results (or exceptions) in that order."""
    async with hold_row_lock(db, table, id=UUID(str(row_id))):
        racer_a = asyncio.create_task(first())
        await wait_for_lock_waiters(db, 1)  # A queues on the gate's lock
        racer_b = asyncio.create_task(second())
        await wait_for_lock_waiters(db, 2)  # B queues behind A
    a, b = await asyncio.wait_for(
        asyncio.gather(racer_a, racer_b, return_exceptions=True), timeout=10
    )
    return a, b


async def test_inv19_two_bookings_race_for_the_last_unit(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "LAST-ONE", stock=1)
    first, second = await parts_pending_booking(db, world), await parts_pending_booking(db, world)
    for booking in (first, second):
        await assign_parts(db, world.a, booking.id, [qty(part, 1)])
    won, lost = await run_in_order(
        db,
        "parts",
        part["id"],
        lambda: mark_parts_ready(db, world.a, first.id),
        lambda: mark_parts_ready(db, world.a, second.id),
    )
    assert won == (qty(part, 1),)
    assert isinstance(lost, InsufficientStock), lost
    assert await part_balance(db, part["id"]) == (1, 1)
    assert (await booking_rows(db, first.id))[qty(part, 1).part_id].reserved_qty == 1
    assert (await booking_rows(db, second.id))[qty(part, 1).part_id].reserved_qty == 0
    await assert_ledger_invariants(db)


async def new_po(api: httpx.AsyncClient, world: World, part_id: str, quantity: int) -> Any:
    response = await api.post(
        url(world.a.id, "/purchase-orders"),
        json={"items": [{"part_id": part_id, "quantity": quantity}]},
        headers=bearer(world.a.parts),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_inv28_two_identical_receipts_count_once(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "X1")
    po = await new_po(api, world, part["id"], 4)
    line = {"item_id": po["items"][0]["id"], "quantity": 2, "expected_received_qty": 0}

    def receive(user: Any) -> Racer:
        return lambda: api.post(
            url(world.a.id, f"/purchase-orders/{po['id']}/receive"),
            json={"items": [line]},
            headers=bearer(user),
        )

    first, second = await run_in_order(
        db, "purchase_orders", po["id"], receive(world.a.parts), receive(world.a.parts2)
    )
    assert first.status_code == 200, first.text
    assert_problem(second, 409, "CONCURRENT_UPDATE")
    assert await part_balance(db, part["id"]) == (2, 0)
    await assert_ledger_invariants(db)


async def test_inv07_receipts_that_together_exceed_the_order_cannot_both_land(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "X1")
    po = await new_po(api, world, part["id"], 3)

    def receive_two() -> Awaitable[httpx.Response]:
        return api.post(
            url(world.a.id, f"/purchase-orders/{po['id']}/receive"),
            json={"items": [{"item_id": po["items"][0]["id"], "quantity": 2}]},
            headers=bearer(world.a.parts),
        )

    first, second = await run_in_order(db, "purchase_orders", po["id"], receive_two, receive_two)
    assert first.status_code == 200, first.text
    assert field_codes(second) == [("items.0.quantity", "exceeds_outstanding")]
    assert await part_balance(db, part["id"]) == (2, 0)
    await assert_ledger_invariants(db)


async def test_inv25_concurrent_adjustments_never_drop_below_zero(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "X1", stock=3)

    def take_two() -> Awaitable[httpx.Response]:
        return api.post(
            url(world.a.id, f"/parts/{part['id']}/adjustments"),
            json={"quantity_delta": -2, "reason": "Damaged"},
            headers=bearer(world.a.parts),
        )

    first, second = await run_in_order(db, "parts", part["id"], take_two, take_two)
    assert first.status_code == 201, first.text
    assert_problem(second, 409, "INSUFFICIENT_STOCK")
    assert await part_balance(db, part["id"]) == (1, 0)
    await assert_ledger_invariants(db)


@pytest.mark.parametrize("first", ["reservation", "adjustment"])
async def test_inv25_an_adjustment_racing_a_reservation_never_undercuts_it(
    api: httpx.AsyncClient, world: World, db: Database, first: str
) -> None:
    part = await new_part(api, world.a, "X1", stock=2)
    booking = await parts_pending_booking(db, world)
    await assign_parts(db, world.a, booking.id, [qty(part, 2)])

    def reserve() -> Awaitable[Any]:  # mark-parts-ready (T14): booking lock, then the part
        return mark_parts_ready(db, world.a, booking.id)

    def write_off() -> Awaitable[httpx.Response]:
        return api.post(
            url(world.a.id, f"/parts/{part['id']}/adjustments"),
            json={"quantity_delta": -1, "reason": "Lost"},
            headers=bearer(world.a.parts),
        )

    racers = (reserve, write_off) if first == "reservation" else (write_off, reserve)
    a, b = await run_in_order(db, "parts", part["id"], *racers)
    reserved, adjusted = (a, b) if first == "reservation" else (b, a)
    row = (await booking_rows(db, booking.id))[qty(part, 2).part_id]
    if first == "reservation":  # the write-off would leave 1 on hand under 2 reserved
        assert reserved == (qty(part, 2),)
        body = assert_problem(adjusted, 409, "INSUFFICIENT_STOCK")
        assert "lowest allowed change is 0" in body["detail"]
        assert await part_balance(db, part["id"]) == (2, 2)
        assert row.reserved_qty == 2
    else:  # 1 left after the write-off, 2 needed: nothing is reserved (all or nothing)
        assert adjusted.status_code == 201, adjusted.text
        assert isinstance(reserved, InsufficientStock), reserved
        assert await part_balance(db, part["id"]) == (1, 0)
        assert row.reserved_qty == 0
    await assert_ledger_invariants(db)


@pytest.mark.parametrize("first", ["receipt", "cancel"])
async def test_con04_a_receipt_racing_a_cancel_of_its_booking(
    api: httpx.AsyncClient, world: World, db: Database, bookings: FakeBookings, first: str
) -> None:
    coil = await new_part(api, world.a, "IGN-COIL-01")
    filt = await new_part(api, world.a, "OIL-FLT-01", stock=10)
    booking, ordered = await order_parts(
        db, world.a, world.customer, {coil["id"]: 1, filt["id"]: 1}
    )
    detail = await api.get(
        url(world.a.id, f"/purchase-orders/{ordered.purchase_order_id}"),
        headers=bearer(world.a.parts),
    )
    item_id = detail.json()["items"][0]["id"]

    async def cancel() -> None:  # CANCEL (T22) as bookings performs it: booking lock first
        async with transaction(db) as uow:
            await lock_booking(uow.session, booking.id)
            await inventory_service.release_reservations(
                uow,
                shop_id=world.a.id,
                booking_id=booking.id,
                actor_user_id=world.customer.id,
                now=utcnow(),
            )
            await cancel_booking(uow.session, booking.id, world.customer)

    def receive() -> Awaitable[
        httpx.Response
    ]:  # locks the booking first (`PurchaseOrderReceiving`)
        return api.post(
            url(world.a.id, f"/purchase-orders/{ordered.purchase_order_id}/receive"),
            json={"items": [{"item_id": item_id, "quantity": 1}]},
            headers=bearer(world.a.parts),
        )

    racers = (receive, cancel) if first == "receipt" else (cancel, receive)
    a, b = await run_in_order(db, "bookings", booking.id, *racers)
    received, cancelled = (a, b) if first == "receipt" else (b, a)
    assert cancelled is None, cancelled
    assert received.status_code == 200, received.text
    body = received.json()
    coil_ledger = [
        (m.movement_type, m.booking_id, m.purchase_order_id)
        for m in await movements_of(db, coil["id"])
    ]
    if first == "receipt":  # the receipt reserved and fired RECEIVE_PARTS, then the cancel released
        assert body["receive_parts_applied"] is True
        assert body["purchase_order"]["booking"]["status"] == "PARTS_READY"
        assert coil_ledger == [
            ("RECEIVE", None, ordered.purchase_order_id),
            ("RESERVE", booking.id, ordered.purchase_order_id),
            ("RELEASE", booking.id, None),
        ]
    else:  # the cancel won: the coil arrives as general stock and nothing is reserved (INV-24)
        assert body["receive_parts_applied"] is False
        assert body["purchase_order"]["booking"]["status"] == "CANCELLED"
        assert coil_ledger == [("RECEIVE", None, ordered.purchase_order_id)]
        assert bookings.reservations == []
    # Either way the end state is the same: cancelled, nothing held, the coil in stock.
    assert (await booking_status(db, booking.id))[0] == BookingStatus.CANCELLED
    assert all(row.reserved_qty == 0 for row in (await booking_rows(db, booking.id)).values())
    assert await part_balance(db, coil["id"]) == (1, 0)
    assert await part_balance(db, filt["id"]) == (10, 0)
    assert body["purchase_order"]["status"] == "RECEIVED"
    await assert_ledger_invariants(db)


async def test_two_parts_with_one_sku_at_once_give_one_part(
    api: httpx.AsyncClient, world: World
) -> None:
    """No row to gate here: the SKU pre-check and the unique index (`uq_parts_shop_id_sku`)
    answer 409 whichever way the two inserts interleave."""

    async def create() -> httpx.Response:
        return await api.post(
            url(world.a.id, "/parts"),
            json={"sku": "RACE-1", "name": "Race", "unit_cost": "100"},
            headers=bearer(world.a.parts),
        )

    responses = await asyncio.gather(create(), create())
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert_problem(next(r for r in responses if r.status_code == 409), 409, "CONFLICT")
    listing = await api.get(url(world.a.id, "/parts"), headers=bearer(world.a.parts))
    assert listing.json()["total"] == 1

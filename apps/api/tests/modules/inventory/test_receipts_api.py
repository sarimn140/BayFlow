"""Purchase-order receipts over HTTP (spec 03 §5.3; D24, D43, D83, D86; `modules/inventory.md`).

General restock: INV-07, INV-08, INV-28 and the receipt validation order. Booking-linked POs with
the bookings side of the receipt (`FakeBookings`, `modules/bookings.md` §7.7): INV-05, INV-06,
INV-09, INV-24, INV-30, the D83 reservation report (inventory half of INV-34), and a receipt with
no subscriber or no `BookingRefReader`. Under a clock that moves on every reading: every row of a
receipt carries its single post-lock instant (D63), and `receive_parts_applied` holds even when
the reader returns live objects that the handlers mutate.
"""

from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.modules.inventory import service as inventory_service
from app.modules.inventory.domain.stock import PartQty, ReceiptReservation
from app.modules.inventory.events import PurchaseOrderReceived
from app.modules.inventory.models import (
    BookingPart,
    Part,
    PurchaseOrder,
    PurchaseOrderItem,
    StockMovement,
)
from app.shared.clock import SimulatedClock, utcnow
from app.shared.enums import BookingStatus
from app.shared.event_bus import EventBus
from app.shared.timestamps import format_timestamp
from app.shared.uow import UnitOfWork
from tests.modules.inventory.support import (
    FakeBookings,
    World,
    assert_ledger_invariants,
    assert_problem,
    bearer,
    booking_rows,
    booking_status,
    cancel_booking,
    field_codes,
    lock_booking,
    move_booking,
    movements_of,
    new_part,
    order_parts,
    part_balance,
    read_booking_refs,
    transaction,
    url,
    without_booking_reader,
)

pytestmark = pytest.mark.db


async def restock_po(
    api: httpx.AsyncClient, world: World, part_id: str, quantity: int
) -> dict[str, Any]:
    response = await api.post(
        url(world.a.id, "/purchase-orders"),
        json={"items": [{"part_id": part_id, "quantity": quantity}]},
        headers=bearer(world.a.parts),
    )
    assert response.status_code == 201, response.text
    order: dict[str, Any] = response.json()
    return order


async def receive(
    api: httpx.AsyncClient,
    world: World,
    po_id: object,
    lines: list[dict[str, Any]],
    *,
    user: Any = None,
) -> httpx.Response:
    return await api.post(
        url(world.a.id, f"/purchase-orders/{po_id}/receive"),
        json={"items": lines},
        headers=bearer(user or world.a.parts),
    )


async def po_items(api: httpx.AsyncClient, world: World, po_id: object) -> list[dict[str, Any]]:
    response = await api.get(
        url(world.a.id, f"/purchase-orders/{po_id}"), headers=bearer(world.a.parts)
    )
    assert response.status_code == 200
    items: list[dict[str, Any]] = response.json()["items"]
    return items


# --- General restock (INV-07, INV-08, INV-28) ---------------------------------------------------


async def test_inv08_a_general_restock_receipt_only_raises_on_hand(
    api: httpx.AsyncClient,
    world: World,
    db: Database,
    bookings: FakeBookings,
    clock: SimulatedClock,
) -> None:
    part = await new_part(api, world.a, "WPR-PAIR", reorder_level=2)
    order = await restock_po(api, world, part["id"], 5)
    item_id = order["items"][0]["id"]
    clock.advance(timedelta(days=1))
    partial = await receive(
        api,
        world,
        order["id"],
        [{"item_id": item_id, "quantity": 2, "expected_received_qty": 0}],
        user=world.a.parts2,
    )
    assert partial.status_code == 200, partial.text
    body = partial.json()
    assert body["receive_parts_applied"] is False
    received = body["purchase_order"]
    assert (received["status"], received["received_qty_total"], received["received_at"]) == (
        "PARTIALLY_RECEIVED",
        2,
        None,
    )
    assert received["booking"] is None
    assert received["items"][0]["outstanding_qty"] == 3
    assert received["updated_at"] == "2026-10-15T04:00:00Z"
    assert await part_balance(db, part["id"]) == (2, 0)
    full = await receive(
        api, world, order["id"], [{"item_id": item_id, "quantity": 3, "expected_received_qty": 2}]
    )
    assert full.status_code == 200
    assert full.json()["purchase_order"]["status"] == "RECEIVED"
    assert full.json()["purchase_order"]["received_at"] == "2026-10-15T04:00:00Z"
    assert await part_balance(db, part["id"]) == (5, 0)
    ledger = await movements_of(db, part["id"])
    assert [
        (m.movement_type, m.quantity, m.booking_id, str(m.purchase_order_id)) for m in ledger
    ] == [
        ("RECEIVE", 2, None, order["id"]),
        ("RECEIVE", 3, None, order["id"]),
    ]
    assert ledger[0].actor_user_id == world.a.parts2.id
    assert bookings.locked == []  # no booking: `PurchaseOrderReceiving` is never published
    assert [event.booking_id for event in bookings.received_events] == [None, None]
    assert bookings.received_events[0].received == (PartQty(UUID(part["id"]), 2),)
    await assert_ledger_invariants(db)


async def test_inv07_over_receipts_and_received_orders_change_nothing(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "X1")
    order = await restock_po(api, world, part["id"], 2)
    item_id = order["items"][0]["id"]
    too_many = await receive(api, world, order["id"], [{"item_id": item_id, "quantity": 3}])
    assert field_codes(too_many) == [("items.0.quantity", "exceeds_outstanding")]
    assert await part_balance(db, part["id"]) == (0, 0)
    assert (
        await receive(api, world, order["id"], [{"item_id": item_id, "quantity": 2}])
    ).status_code == 200
    again = await receive(api, world, order["id"], [{"item_id": item_id, "quantity": 1}])
    assert_problem(again, 409, "CONFLICT")
    assert await part_balance(db, part["id"]) == (2, 0)
    await assert_ledger_invariants(db)


async def test_inv28_a_repeated_receipt_is_a_concurrent_update(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "X1")
    order = await restock_po(api, world, part["id"], 4)
    line = {"item_id": order["items"][0]["id"], "quantity": 1, "expected_received_qty": 0}
    assert (await receive(api, world, order["id"], [line])).status_code == 200
    repeated = await receive(api, world, order["id"], [line])
    assert_problem(repeated, 409, "CONCURRENT_UPDATE")
    assert await part_balance(db, part["id"]) == (1, 0)
    assert (await po_items(api, world, order["id"]))[0]["received_qty"] == 1


async def test_receipt_validation(api: httpx.AsyncClient, world: World, db: Database) -> None:
    part = await new_part(api, world.a, "X1")
    other = await new_part(api, world.a, "X2")
    order = await restock_po(api, world, part["id"], 4)
    second_order = await restock_po(api, world, other["id"], 4)
    item_id = order["items"][0]["id"]
    zero = await receive(api, world, order["id"], [{"item_id": item_id, "quantity": 0}])
    assert field_codes(zero) == [("items", "nothing_to_receive")]
    foreign_item = second_order["items"][0]["id"]
    wrong = await receive(
        api,
        world,
        order["id"],
        [{"item_id": item_id, "quantity": 1}, {"item_id": foreign_item, "quantity": 1}],
    )
    assert field_codes(wrong) == [("items.1.item_id", "invalid_reference")]
    twice = await receive(
        api,
        world,
        order["id"],
        [{"item_id": item_id, "quantity": 1}, {"item_id": item_id, "quantity": 1}],
    )
    assert field_codes(twice) == [("items.1.item_id", "duplicate")]
    for lines, expected in (
        ([], [("items", "too_short")]),
        ([{"item_id": item_id, "quantity": "1"}], [("items.0.quantity", "int_type")]),
        ([{"item_id": item_id, "quantity": -1}], [("items.0.quantity", "greater_than_equal")]),
        (
            [{"item_id": item_id, "quantity": 1, "part_id": part["id"]}],
            [("items.0.part_id", "extra_forbidden")],
        ),
    ):
        assert field_codes(await receive(api, world, order["id"], lines)) == expected
    assert await part_balance(db, part["id"]) == (0, 0)
    await assert_ledger_invariants(db)


async def test_inv18_receipt_roles_and_tenancy(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "X1")
    order = await restock_po(api, world, part["id"], 3)
    line = [{"item_id": order["items"][0]["id"], "quantity": 1}]
    for user in (world.a.owner, world.a.advisor, world.a.technician, world.a.qc):
        assert_problem(await receive(api, world, order["id"], line, user=user), 403, "FORBIDDEN")
    for user in (world.a.former_parts, world.b.parts, world.customer):
        assert_problem(await receive(api, world, order["id"], line, user=user), 404, "NOT_FOUND")
    assert_problem(await receive(api, world, uuid4(), line), 404, "NOT_FOUND")
    theirs = await new_part(api, world.b, "THEIRS")
    their_order = await api.post(
        url(world.b.id, "/purchase-orders"),
        json={"items": [{"part_id": theirs["id"], "quantity": 1}]},
        headers=bearer(world.b.parts),
    )
    cross = await receive(
        api,
        world,
        their_order.json()["id"],
        [{"item_id": their_order.json()["items"][0]["id"], "quantity": 1}],
    )
    assert_problem(cross, 404, "NOT_FOUND")
    assert (await receive(api, world, order["id"], line, user=world.a.parts2)).status_code == 200
    assert await part_balance(db, part["id"]) == (1, 0)
    assert await part_balance(db, theirs["id"]) == (0, 0)


# --- Booking-linked POs (D43, T15) ---------------------------------------------------------------


async def test_inv05_inv06_inv30_inv34_partial_then_final_delivery(
    api: httpx.AsyncClient, world: World, db: Database, bookings: FakeBookings
) -> None:
    coil = await new_part(api, world.a, "IGN-COIL-01", unit_cost="6500")
    pads = await new_part(api, world.a, "BRK-PAD-F", stock=4)
    booking, ordered = await order_parts(
        db, world.a, world.customer, {coil["id"]: 2, pads["id"]: 1}
    )
    assert ordered.reserved == (PartQty(UUID(pads["id"]), 1),)
    status, version = await booking_status(db, booking.id)
    assert status == BookingStatus.PARTS_ORDERED
    [item] = await po_items(api, world, ordered.purchase_order_id)
    assert (item["part"]["sku"], item["ordered_qty"]) == ("IGN-COIL-01", 2)

    partial = await receive(
        api, world, ordered.purchase_order_id, [{"item_id": item["id"], "quantity": 1}]
    )
    assert partial.status_code == 200, partial.text
    body = partial.json()
    assert body["receive_parts_applied"] is False
    assert body["purchase_order"]["status"] == "PARTIALLY_RECEIVED"
    assert body["purchase_order"]["booking"] == {
        "id": str(booking.id),
        "reference": booking.reference,
        "status": "PARTS_ORDERED",
        "version": version,
    }
    assert await part_balance(db, coil["id"]) == (1, 1)  # received and reserved for the booking
    assert (await booking_rows(db, booking.id))[UUID(coil["id"])].reserved_qty == 1
    # D83: the receipt reports what it reserved, without completing the booking.
    assert bookings.reservations == [
        ReceiptReservation(reserved=(PartQty(UUID(coil["id"]), 1),), all_reserved=False)
    ]

    final = await receive(
        api, world, ordered.purchase_order_id, [{"item_id": item["id"], "quantity": 1}]
    )
    assert final.status_code == 200, final.text
    assert final.json()["receive_parts_applied"] is True
    order = final.json()["purchase_order"]
    assert order["status"] == "RECEIVED"
    assert order["booking"]["status"] == "PARTS_READY"
    assert order["booking"]["version"] == version + 1
    assert await part_balance(db, coil["id"]) == (2, 2)
    assert bookings.locked == [booking.id, booking.id]  # the booking is lock 1 of each receipt

    coil_ledger = await movements_of(db, coil["id"])
    assert [(m.movement_type, m.booking_id, m.purchase_order_id) for m in coil_ledger] == [
        ("RECEIVE", None, ordered.purchase_order_id),  # INV-30
        ("RESERVE", booking.id, ordered.purchase_order_id),
        ("RECEIVE", None, ordered.purchase_order_id),
        ("RESERVE", booking.id, ordered.purchase_order_id),
    ]
    await assert_ledger_invariants(db)


async def test_excess_received_stock_stays_general(
    api: httpx.AsyncClient, world: World, db: Database, bookings: FakeBookings
) -> None:
    coil = await new_part(api, world.a, "IGN-COIL-01")
    booking, ordered = await order_parts(
        db, world.a, world.customer, {coil["id"]: 1}, items=[PartQty(UUID(coil["id"]), 3)]
    )
    [item] = await po_items(api, world, ordered.purchase_order_id)
    assert item["ordered_qty"] == 3
    response = await receive(
        api, world, ordered.purchase_order_id, [{"item_id": item["id"], "quantity": 3}]
    )
    assert response.json()["receive_parts_applied"] is True
    assert await part_balance(db, coil["id"]) == (3, 1)  # 1 for the job, 2 general
    assert bookings.reservations[-1].reserved == (PartQty(UUID(coil["id"]), 1),)
    assert (await booking_status(db, booking.id))[0] == BookingStatus.PARTS_READY
    await assert_ledger_invariants(db)


async def test_inv09_a_cancelled_bookings_order_arrives_as_general_stock(
    api: httpx.AsyncClient, world: World, db: Database, bookings: FakeBookings
) -> None:
    coil = await new_part(api, world.a, "IGN-COIL-01")
    oil = await new_part(api, world.a, "OIL-4L", stock=8)
    booking, ordered = await order_parts(db, world.a, world.customer, {coil["id"]: 1, oil["id"]: 1})
    assert await part_balance(db, oil["id"]) == (8, 1)
    async with transaction(db) as uow:  # CANCEL (T22), as bookings performs it
        await lock_booking(uow.session, booking.id)
        released = await inventory_service.release_reservations(
            uow,
            shop_id=world.a.id,
            booking_id=booking.id,
            actor_user_id=world.customer.id,
            now=utcnow(),
        )
        await cancel_booking(uow.session, booking.id, world.customer)
    assert released == (PartQty(UUID(oil["id"]), 1),)
    assert await part_balance(db, oil["id"]) == (8, 0)
    status, version = await booking_status(db, booking.id)
    [item] = await po_items(api, world, ordered.purchase_order_id)
    assert item["received_qty"] == 0  # the PO stays open (D24)
    response = await receive(
        api, world, ordered.purchase_order_id, [{"item_id": item["id"], "quantity": 1}]
    )
    assert response.status_code == 200
    assert response.json()["receive_parts_applied"] is False
    assert response.json()["purchase_order"]["booking"]["status"] == "CANCELLED"
    assert await part_balance(db, coil["id"]) == (1, 0)
    assert await booking_status(db, booking.id) == (status, version)
    assert bookings.reservations == []
    assert all(row.reserved_qty == 0 for row in (await booking_rows(db, booking.id)).values())
    await assert_ledger_invariants(db)


async def test_inv24_a_booking_made_ready_another_way_gets_nothing_from_its_order(
    api: httpx.AsyncClient, world: World, db: Database, bookings: FakeBookings
) -> None:
    coil = await new_part(api, world.a, "IGN-COIL-01")
    booking, ordered = await order_parts(db, world.a, world.customer, {coil["id"]: 1})
    stocked = await api.post(  # the coil arrives another way: a general count correction
        url(world.a.id, f"/parts/{coil['id']}/adjustments"),
        json={"quantity_delta": 1, "reason": "Found one on the shelf"},
        headers=bearer(world.a.parts),
    )
    assert stocked.status_code == 201
    async with transaction(db) as uow:  # MARK_PARTS_READY from PARTS_ORDERED (T14, D43)
        await lock_booking(uow.session, booking.id)
        reserved = await inventory_service.reserve_outstanding(
            uow,
            shop_id=world.a.id,
            booking_id=booking.id,
            actor_user_id=world.a.parts.id,
            now=utcnow(),
        )
        await move_booking(uow.session, booking.id, BookingStatus.PARTS_READY)
    assert reserved == (PartQty(UUID(coil["id"]), 1),)
    before = await booking_status(db, booking.id)
    [item] = await po_items(api, world, ordered.purchase_order_id)
    response = await receive(
        api, world, ordered.purchase_order_id, [{"item_id": item["id"], "quantity": 1}]
    )
    assert response.status_code == 200
    assert response.json()["receive_parts_applied"] is False
    assert await part_balance(db, coil["id"]) == (2, 1)  # the receipt is general stock
    assert await booking_status(db, booking.id) == before
    assert (await booking_rows(db, booking.id))[UUID(coil["id"])].reserved_qty == 1
    assert bookings.reservations == []
    await assert_ledger_invariants(db)


async def test_a_linked_receipt_without_subscribers_still_completes(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    coil = await new_part(api, world.a, "IGN-COIL-01")
    booking, ordered = await order_parts(db, world.a, world.customer, {coil["id"]: 1})
    [item] = await po_items(api, world, ordered.purchase_order_id)
    response = await receive(
        api, world, ordered.purchase_order_id, [{"item_id": item["id"], "quantity": 1}]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["receive_parts_applied"] is False
    assert body["purchase_order"]["booking"]["id"] == str(booking.id)
    assert body["purchase_order"]["status"] == "RECEIVED"
    assert body["purchase_order"]["booking"]["status"] == "PARTS_ORDERED"
    assert await part_balance(db, coil["id"]) == (1, 0)
    assert [m.movement_type for m in await movements_of(db, coil["id"])] == ["RECEIVE"]
    await assert_ledger_invariants(db)


async def test_a_linked_receipt_fails_loud_without_a_booking_reader_and_changes_nothing(
    api: httpx.AsyncClient, world: World, db: Database, bookings: FakeBookings
) -> None:
    coil = await new_part(api, world.a, "IGN-COIL-01")
    booking, ordered = await order_parts(db, world.a, world.customer, {coil["id"]: 1})
    [item] = await po_items(api, world, ordered.purchase_order_id)
    general = await restock_po(api, world, coil["id"], 2)
    with without_booking_reader():
        response = await receive(
            api, world, ordered.purchase_order_id, [{"item_id": item["id"], "quantity": 1}]
        )
        assert_problem(response, 500, "INTERNAL_ERROR")
        listing = await api.get(url(world.a.id, "/purchase-orders"), headers=bearer(world.a.owner))
        assert_problem(listing, 500, "INTERNAL_ERROR")  # a linked PO is on the page
        restock = await receive(  # no booking involved: the port is never touched
            api, world, general["id"], [{"item_id": general["items"][0]["id"], "quantity": 2}]
        )
        assert restock.status_code == 200, restock.text
    assert await part_balance(db, coil["id"]) == (2, 0)  # only the general receipt landed
    assert (await po_items(api, world, ordered.purchase_order_id))[0]["received_qty"] == 0
    assert (await booking_status(db, booking.id))[0] == BookingStatus.PARTS_ORDERED
    assert bookings.reservations == []
    await assert_ledger_invariants(db)


@dataclass
class LiveBooking:
    """A mutable booking object, as an ORM `Booking` row held in the session's identity map."""

    id: UUID
    reference: str
    status: BookingStatus
    version: int


@dataclass
class IdentityMapReader:
    """A `BookingRefReader` that hands back the *same* live object on every read, as a reader
    returning ORM rows from the session's identity map would."""

    rows: dict[UUID, LiveBooking] = field(default_factory=dict)

    async def __call__(
        self, session: AsyncSession, *, shop_id: UUID, booking_ids: Collection[UUID]
    ) -> dict[UUID, LiveBooking]:
        fresh = await read_booking_refs(session, shop_id=shop_id, booking_ids=booking_ids)
        for booking_id, ref in fresh.items():
            self.rows.setdefault(
                booking_id, LiveBooking(ref.id, ref.reference, ref.status, ref.version)
            )
        return {booking_id: self.rows[booking_id] for booking_id in fresh}


async def test_receive_parts_applied_survives_a_reader_that_returns_live_rows(
    api: httpx.AsyncClient, world: World, db: Database, bus: EventBus, bookings: FakeBookings
) -> None:
    reader = IdentityMapReader()
    inventory_service.register_booking_ref_reader(reader)  # restored by the `booking_refs` fixture

    async def move_the_live_row(event: PurchaseOrderReceived, uow: UnitOfWork) -> None:
        """What an ORM-based handler does: it changes the very object it loaded."""
        if event.booking_id is not None and event.booking_id in reader.rows:
            status = await booking_status_in(uow.session, event.booking_id)
            reader.rows[event.booking_id].status = status

    bus.subscribe(PurchaseOrderReceived, move_the_live_row)  # after the bookings handler
    coil = await new_part(api, world.a, "IGN-COIL-01")
    booking, ordered = await order_parts(db, world.a, world.customer, {coil["id"]: 1})
    [item] = await po_items(api, world, ordered.purchase_order_id)
    response = await receive(
        api, world, ordered.purchase_order_id, [{"item_id": item["id"], "quantity": 1}]
    )
    assert response.status_code == 200, response.text
    assert reader.rows[booking.id].status == BookingStatus.PARTS_READY  # the same object moved
    assert response.json()["purchase_order"]["booking"]["status"] == "PARTS_READY"
    assert response.json()["receive_parts_applied"] is True


async def booking_status_in(session: AsyncSession, booking_id: UUID) -> BookingStatus:
    result = await session.execute(
        text("SELECT status FROM bookings WHERE id = :id"), {"id": booking_id}
    )
    return BookingStatus(result.scalar_one())


async def test_a_receipt_writes_everything_with_its_single_post_lock_instant(
    api: httpx.AsyncClient,
    world: World,
    db: Database,
    bookings: FakeBookings,
    stepping_clock: SimulatedClock,
) -> None:
    """D63 under a clock that moves on every reading: the pre-lock `PurchaseOrderReceiving`
    instant is never written, and every row of the receipt (and of its handlers) carries
    `PurchaseOrderReceived.occurred_at`."""
    coil = await new_part(api, world.a, "IGN-COIL-01")
    filt = await new_part(api, world.a, "OIL-FLT-01")
    booking, ordered = await order_parts(
        db, world.a, world.customer, {coil["id"]: 2, filt["id"]: 1}
    )
    items = await po_items(api, world, ordered.purchase_order_id)
    response = await receive(
        api,
        world,
        ordered.purchase_order_id,
        [{"item_id": item["id"], "quantity": item["ordered_qty"]} for item in items],
    )
    assert response.status_code == 200, response.text
    assert response.json()["receive_parts_applied"] is True
    [receiving] = bookings.receiving_events
    [received] = bookings.received_events
    instant = received.occurred_at
    assert receiving.occurred_at < instant  # a separate, earlier reading (before the locks)
    written = await receipt_timestamps(db, ordered.purchase_order_id, booking.id)
    assert written == {instant}, written
    assert receiving.occurred_at not in written
    body = response.json()["purchase_order"]
    assert body["updated_at"] == body["received_at"] == format_timestamp(instant)
    assert {m.created_at for m in await movements_of(db, coil["id"]) if m.purchase_order_id} == {
        instant
    }


async def receipt_timestamps(db: Database, po_id: UUID, booking_id: UUID) -> set[datetime]:
    """Every instant the receipt (and its handlers) wrote: its movements, the PO, its items, the
    parts it touched and the booking parts it reserved."""
    async with db.sessionmaker() as session:
        order = await session.get(PurchaseOrder, po_id)
        assert order is not None
        items = (
            (
                await session.execute(
                    select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == po_id)
                )
            )
            .scalars()
            .all()
        )
        movements = (
            (
                await session.execute(
                    select(StockMovement).where(StockMovement.purchase_order_id == po_id)
                )
            )
            .scalars()
            .all()
        )
        parts = (
            (await session.execute(select(Part).where(Part.id.in_([i.part_id for i in items]))))
            .scalars()
            .all()
        )
        rows = (
            (await session.execute(select(BookingPart).where(BookingPart.booking_id == booking_id)))
            .scalars()
            .all()
        )
    assert {m.movement_type for m in movements} == {"RECEIVE", "RESERVE"}
    return (
        {order.updated_at, order.received_at}
        | {item.updated_at for item in items}
        | {movement.created_at for movement in movements}
        | {part.updated_at for part in parts}
        | {row.updated_at for row in rows if row.reserved_qty}
    ) - {None}


async def test_received_event_payload(
    api: httpx.AsyncClient,
    world: World,
    db: Database,
    bookings: FakeBookings,
    stepping_clock: SimulatedClock,
) -> None:
    coil = await new_part(api, world.a, "IGN-COIL-01")
    booking, ordered = await order_parts(db, world.a, world.customer, {coil["id"]: 2})
    [item] = await po_items(api, world, ordered.purchase_order_id)
    stepping_clock.advance(timedelta(hours=2))
    await receive(
        api,
        world,
        ordered.purchase_order_id,
        [{"item_id": item["id"], "quantity": 2}],
        user=world.a.parts2,
    )
    [event] = bookings.received_events
    assert (event.shop_id, event.purchase_order_id, event.booking_id) == (
        world.a.id,
        ordered.purchase_order_id,
        booking.id,
    )
    assert event.po_number == ordered.po_number
    assert event.received == (PartQty(UUID(coil["id"]), 2),)
    assert event.actor_user_id == world.a.parts2.id
    [receive_row] = [m for m in await movements_of(db, coil["id"]) if m.movement_type == "RECEIVE"]
    assert event.occurred_at == receive_row.created_at
    listed = await api.get(
        url(world.a.id, "/purchase-orders"),
        params={"booking_id": str(booking.id)},
        headers=bearer(world.a.parts),
    )
    assert [o["id"] for o in listed.json()["items"]] == [str(ordered.purchase_order_id)]
    assert listed.json()["items"][0]["booking"]["reference"] == booking.reference

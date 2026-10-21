"""SM-18, steps 8-10 — the inventory half of the worked example (brief §6; spec 08 "Parts
reservations"), driven the way the bookings executor will drive it, with the receipt over HTTP.

filter 10/0, oil 8/0, coil 0/0 → order-parts → 10/1, 8/1, 0/0 + PO for 1 coil → receipt fires
RECEIVE_PARTS → coil 1/1 → allocate-parts → 9/0, 7/0, 0/0.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest

from app.core.database import Database
from app.modules.inventory import service as inventory_service
from app.shared.clock import SimulatedClock
from app.shared.enums import BookingStatus
from tests.modules.inventory.support import (
    FakeBookings,
    Team,
    World,
    allocate_parts,
    assert_ledger_invariants,
    assign_parts,
    bearer,
    booking_rows,
    booking_status,
    lock_booking,
    move_booking,
    new_part,
    order_missing,
    part_balance,
    parts_pending_booking,
    qty,
    transaction,
    url,
)

pytestmark = [pytest.mark.db, pytest.mark.scenario]


async def parts_summary(db: Database, team: Team, booking_id: UUID) -> dict[str, Any]:
    async with db.sessionmaker() as session:
        summary = await inventory_service.get_booking_parts_summary(
            session, shop_id=team.id, booking_ids=[booking_id]
        )
    return summary[booking_id].model_dump()


async def inventory_table(api: httpx.AsyncClient, team: Team) -> dict[str, tuple[Any, ...]]:
    """SKU → (on hand, available, stock state, on order) from `GET …/parts` (brief §7.4)."""
    listing = await api.get(url(team.id, "/parts"), headers=bearer(team.parts))
    return {
        p["sku"]: (p["on_hand"], p["available"], p["stock_state"], p["on_order"])
        for p in listing.json()["items"]
    }


async def test_sm18_steps_8_to_10_inventory_half(
    api: httpx.AsyncClient,
    world: World,
    db: Database,
    bookings: FakeBookings,
    clock: SimulatedClock,
) -> None:
    team = world.a
    filt = await new_part(api, team, "OIL-FLT-01", name="Oil filter", stock=10)
    oil = await new_part(api, team, "ENG-OIL-4L", name="Engine oil 4 L", unit_cost="5200", stock=8)
    coil = await new_part(api, team, "IGN-COIL-01", name="Ignition coil", unit_cost="6500")
    parts = (filt, oil, coil)

    async def balances() -> list[tuple[int, int]]:
        return [await part_balance(db, part["id"]) for part in parts]

    # Step 8 — Bilal assigns Usman (T12): booking parts from the approved estimate.
    booking = await parts_pending_booking(db, world)
    await assign_parts(db, team, booking.id, [qty(part, 1) for part in parts])
    assert await parts_summary(db, team, booking.id) == {
        "required_count": 3,
        "available_count": 2,
        "shortage_count": 1,
        "all_available": False,
    }
    assert await balances() == [(10, 0), (8, 0), (0, 0)]

    # Step 9 — Usman orders the missing coil (T13); the booking becomes PARTS_ORDERED.
    clock.advance(timedelta(hours=1))
    ordered = await order_missing(db, team, booking.id, supplier_name="City Auto Parts")
    async with transaction(db) as uow:
        await lock_booking(uow.session, booking.id)
        await move_booking(uow.session, booking.id, BookingStatus.PARTS_ORDERED)
    assert await balances() == [(10, 1), (8, 1), (0, 0)]
    metadata = {
        "purchase_order_id": str(ordered.purchase_order_id),
        "po_number": ordered.po_number,
        "reserved": [item.as_json() for item in ordered.reserved],
    }
    assert sorted(entry["part_id"] for entry in metadata["reserved"]) == sorted(
        [filt["id"], oil["id"]]
    )
    detail = await api.get(
        url(team.id, f"/purchase-orders/{ordered.purchase_order_id}"), headers=bearer(team.parts)
    )
    order = detail.json()
    assert (order["status"], order["total_cost"], order["booking"]["status"]) == (
        "ORDERED",
        "6500.00",
        "PARTS_ORDERED",
    )
    [item] = order["items"]
    assert (item["part"]["sku"], item["ordered_qty"]) == ("IGN-COIL-01", 1)

    # Step 10 — the coil arrives the next day: the receipt fires RECEIVE_PARTS (T15).
    clock.advance(timedelta(days=1))
    received = await api.post(
        url(team.id, f"/purchase-orders/{ordered.purchase_order_id}/receive"),
        json={"items": [{"item_id": item["id"], "quantity": 1, "expected_received_qty": 0}]},
        headers=bearer(team.parts),
    )
    assert received.status_code == 200, received.text
    assert received.json()["receive_parts_applied"] is True
    assert received.json()["purchase_order"]["status"] == "RECEIVED"
    assert received.json()["purchase_order"]["booking"]["status"] == "PARTS_READY"
    assert await balances() == [(10, 1), (8, 1), (1, 1)]
    assert (await booking_status(db, booking.id))[0] == BookingStatus.PARTS_READY

    # Step 10 — Usman allocates all three parts (T16): stock deducted.
    consumed = await allocate_parts(db, team, booking.id)
    assert sorted(item.part_id for item in consumed) == sorted(UUID(p["id"]) for p in parts)
    assert await balances() == [(9, 0), (7, 0), (0, 0)]
    rows = await booking_rows(db, booking.id)
    assert all((r.required_qty, r.reserved_qty, r.consumed_qty) == (1, 0, 1) for r in rows.values())
    states = await inventory_table(api, team)
    assert states == {
        "ENG-OIL-4L": (7, 7, "OK", 0),
        "IGN-COIL-01": (0, 0, "OUT", 0),
        "OIL-FLT-01": (9, 9, "OK", 0),
    }
    await assert_ledger_invariants(db)

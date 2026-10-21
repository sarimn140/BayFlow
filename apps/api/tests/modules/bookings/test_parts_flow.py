"""Parts through the booking flows (spec 08 T12-T16, T22; D24, D31, D43, D83;
`modules/bookings.md` §7.6, §7.7).

INV-05, INV-06, INV-08 (bookings half), INV-09, INV-13, INV-24, SM-11 ★, SM-12 ★, SM-13, BK-33
(the published half of D83: `BookingPartsChanged` with an unchanged version), the `order-parts`
guards (409 `CONFLICT`, 422 `items`), 409 `INSUFFICIENT_STOCK`, and the linked purchase order's
`booking` reference read through bookings' port in the real app.
"""

from typing import Any

import pytest

from app.core.database import Database
from app.modules.bookings.events import BookingActionApplied, BookingPartsChanged
from app.shared.enums import ActorRole, BookingAction, BookingStatus
from app.shared.event_bus import Event
from tests.modules.bookings.support import (
    Desk,
    Journey,
    World,
    booking_row,
    drive_booking_to,
    events_of,
    field_codes,
    labour_lines,
    problem,
    slot_count,
)
from tests.modules.identity.builders import bearer

pytestmark = pytest.mark.db

S = BookingStatus


async def parts_pending_with(desk: Desk, lines: list[dict[str, Any]]) -> Journey:
    """A `PARTS_PENDING` booking whose approved estimate is `lines` (Usman assigned)."""
    world = desk.world
    journey = await drive_booking_to(desk, S.INSPECTING)
    await desk.edit(world.technician, journey.id, lines)
    await desk.act(world.technician, journey.id, "submit-estimate")
    await desk.act(world.advisor, journey.id, "send-estimate")
    estimate_id = (await desk.my_detail(journey.customer, journey.id))["estimate"]["id"]
    await desk.my_act(
        journey.customer, journey.id, "approve-estimate", {"estimate_id": estimate_id}
    )
    body = {"parts_person_user_id": str(world.parts.id)}
    journey.booking = await desk.act(world.advisor, journey.id, "assign-parts-person", body)
    return journey


def part_line(part: dict[str, Any], quantity: int) -> dict[str, Any]:
    return {"line_type": "PART", "part_id": part["id"], "quantity": str(quantity)}


async def booking_parts(desk: Desk, journey: Journey) -> dict[str, tuple[int, int, int, int]]:
    """`(required, reserved, consumed, outstanding)` per SKU, as the assigned parts person sees
    it."""
    view = await desk.get(desk.world.parts.id, desk.booking_path(journey.id, "/parts"))
    return {
        item["part"]["sku"]: (
            item["required_qty"],
            item["reserved_qty"],
            item["consumed_qty"],
            item["outstanding_qty"],
        )
        for item in view["items"]
    }


async def purchase_order(desk: Desk, order_id: str) -> dict[str, Any]:
    order: dict[str, Any] = await desk.get(
        desk.world.parts.id, desk.shop_path(f"/purchase-orders/{order_id}")
    )
    return order


def of_type[T](events: list[Event], kind: type[T]) -> list[T]:
    return [event for event in events if isinstance(event, kind)]


# --- T13 order-parts ------------------------------------------------------------------------------


async def test_order_parts_reserves_the_stock_there_is_and_orders_the_shortage(
    desk: Desk, world: World
) -> None:
    journey = await drive_booking_to(desk, S.PARTS_ORDERED)
    catalogue = world.catalogue
    assert await desk.balance(catalogue.coil) == (0, 0)
    assert await desk.balance(catalogue.oil_filter) == (100, 1)
    assert await desk.balance(catalogue.engine_oil) == (100, 1)
    assert await booking_parts(desk, journey) == {
        "IGN-COIL-01": (1, 0, 0, 1),
        "OIL-FILTER-01": (1, 1, 0, 0),
        "ENGINE-OIL-4L": (1, 1, 0, 0),
    }
    order = await purchase_order(desk, str(journey.purchase_order_id))
    assert order["status"] == "ORDERED"
    assert [(item["part"]["sku"], item["ordered_qty"]) for item in order["items"]] == [
        ("IGN-COIL-01", 1)
    ]
    detail = await desk.detail(world.parts, journey.id)
    assert order["booking"] == {  # bookings' read port, through the real app (D86)
        "id": journey.id,
        "reference": journey.reference,
        "status": "PARTS_ORDERED",
        "version": detail["version"],
    }
    listing = await desk.get(world.parts.id, desk.shop_path("/purchase-orders"))
    (summary,) = listing["items"]
    assert summary["booking"] == order["booking"]
    assert detail["parts_summary"] == {
        "required_count": 3,
        "available_count": 2,
        "shortage_count": 1,
        "all_available": False,
    }
    view = await desk.get(world.parts.id, desk.booking_path(journey.id, "/parts"))
    assert [ref["po_number"] for ref in view["purchase_orders"]] == [order["po_number"]]


async def test_order_parts_with_nothing_short_is_409_and_writes_nothing(
    desk: Desk, world: World, db: Database
) -> None:
    lines = [part_line(world.catalogue.oil_filter, 2), *labour_lines()]
    journey = await parts_pending_with(desk, lines)
    before = await desk.detail(world.parts, journey.id)
    problem(await desk.act_raw(world.parts.id, journey.id, "order-parts"), 409, "CONFLICT")
    assert await desk.balance(world.catalogue.oil_filter) == (100, 0)
    after = await desk.detail(world.parts, journey.id)
    assert (after["status"], after["version"]) == ("PARTS_PENDING", before["version"])
    assert (await desk.get(world.parts.id, desk.shop_path("/purchase-orders")))["total"] == 0
    labour = await drive_booking_to(desk, S.PARTS_PENDING, labour_only=True)
    problem(await desk.act_raw(world.parts.id, labour.id, "order-parts"), 409, "CONFLICT")


async def test_order_parts_items_must_cover_exactly_the_shortages(desk: Desk, world: World) -> None:
    catalogue = world.catalogue
    lines = [part_line(catalogue.coil, 2), part_line(catalogue.oil_filter, 1), *labour_lines()]
    journey = await parts_pending_with(desk, lines)
    before = await desk.detail(world.parts, journey.id)
    cases = [
        (
            [{"part_id": catalogue.oil_filter["id"], "quantity": 1}],
            [("items.0.part_id", "not_short"), ("items", "missing_shortage")],
        ),
        (
            [{"part_id": catalogue.coil["id"], "quantity": 1}],
            [("items.0.quantity", "below_shortage")],
        ),
        (
            [
                {"part_id": catalogue.coil["id"], "quantity": 2},
                {"part_id": catalogue.coil["id"], "quantity": 3},
            ],
            [("items.1.part_id", "duplicate")],
        ),
        (
            [{"part_id": catalogue.coil["id"], "quantity": 0}],
            [("items.0.quantity", "greater_than_equal")],
        ),
    ]
    for items, expected in cases:
        response = await desk.act_raw(world.parts.id, journey.id, "order-parts", {"items": items})
        codes = field_codes(problem(response, 422, "VALIDATION_ERROR"))
        assert sorted(codes) == sorted(expected), (items, codes)
    after = await desk.detail(world.parts, journey.id)
    assert (after["status"], after["version"]) == ("PARTS_PENDING", before["version"])
    assert await desk.balance(catalogue.oil_filter) == (100, 0)
    body = {
        "supplier_name": "  Lahore Auto Parts  ",
        "items": [{"part_id": catalogue.coil["id"], "quantity": 5}],
    }
    ordered = await desk.act(world.parts, journey.id, "order-parts", body)
    metadata = ordered["last_event"]["metadata"]
    order = await purchase_order(desk, metadata["purchase_order_id"])
    assert order["supplier_name"] == "Lahore Auto Parts"
    assert [(item["part"]["sku"], item["ordered_qty"]) for item in order["items"]] == [
        ("IGN-COIL-01", 5)
    ]
    assert metadata["reserved"] == [{"part_id": catalogue.oil_filter["id"], "qty": 1}]
    receipt = await desk.receive(metadata["purchase_order_id"])
    assert receipt["receive_parts_applied"] is True
    assert await desk.balance(catalogue.coil) == (5, 2)  # the excess stays general stock


# --- T14 mark-parts-ready and INSUFFICIENT_STOCK --------------------------------------------------


async def test_mark_parts_ready_is_all_or_nothing(desk: Desk, world: World, db: Database) -> None:
    pending = await drive_booking_to(desk, S.PARTS_PENDING)  # the coil is out of stock
    before = await desk.detail(world.parts, pending.id)
    problem(
        await desk.act_raw(world.parts.id, pending.id, "mark-parts-ready"),
        409,
        "INSUFFICIENT_STOCK",
    )
    assert await desk.balance(world.catalogue.oil_filter) == (100, 0)  # nothing half-reserved
    after = await desk.detail(world.parts, pending.id)
    assert (after["status"], after["version"]) == ("PARTS_PENDING", before["version"])
    assert len(await events_of(db, pending.id)) == before["version"]
    stocked = await parts_pending_with(desk, [part_line(world.catalogue.engine_oil, 3)])
    ready = await desk.act(world.parts, stocked.id, "mark-parts-ready")
    assert ready["status"] == "PARTS_READY"
    oil = world.catalogue.engine_oil["id"]
    assert ready["last_event"]["metadata"] == {"reserved": [{"part_id": oil, "qty": 3}]}
    assert await desk.balance(world.catalogue.engine_oil) == (100, 3)
    allocated = await desk.act(world.parts, stocked.id, "allocate-parts")
    assert allocated["status"] == "IN_REPAIR"
    assert allocated["last_event"]["metadata"] == {"consumed": [{"part_id": oil, "qty": 3}]}
    assert await desk.balance(world.catalogue.engine_oil) == (97, 0)
    assert await booking_parts(desk, stocked) == {"ENGINE-OIL-4L": (3, 0, 3, 0)}


# --- SM-12, INV-05, INV-06, BK-33 (D83) -----------------------------------------------------------


async def test_sm12_inv05_inv06_partial_then_full_receipt(
    desk: Desk, world: World, db: Database, published: list[Event]
) -> None:
    coil = world.catalogue.coil
    journey = await parts_pending_with(desk, [part_line(coil, 2), *labour_lines()])
    ordered = await desk.act(world.parts, journey.id, "order-parts")
    order_id = ordered["last_event"]["metadata"]["purchase_order_id"]
    version = ordered["version"]
    seen = len(published)
    partial = await desk.receive(order_id, {coil["id"]: 1}, by=world.parts2)
    assert partial["receive_parts_applied"] is False
    assert partial["purchase_order"]["status"] == "PARTIALLY_RECEIVED"
    assert partial["purchase_order"]["booking"]["status"] == "PARTS_ORDERED"
    assert await desk.balance(coil) == (1, 1)  # reserved for the linked booking (INV-05)
    assert await booking_parts(desk, journey) == {"IGN-COIL-01": (2, 1, 0, 1)}
    row = await booking_row(db, journey.id)
    assert (row.status, row.version) == (S.PARTS_ORDERED, version)  # no event, no bump (D30)
    assert len(await events_of(db, journey.id)) == version
    (changed,) = published[seen:]
    assert isinstance(changed, BookingPartsChanged)
    assert (changed.shop_id, str(changed.booking_id), changed.status, changed.version) == (
        world.shop_id,
        journey.id,
        S.PARTS_ORDERED,
        version,  # D83: the unchanged version, clients refetch on an equal one
    )
    seen = len(published)
    final = await desk.receive(order_id, by=world.parts2)
    assert final["receive_parts_applied"] is True
    assert final["purchase_order"]["status"] == "RECEIVED"
    assert final["purchase_order"]["booking"] == {
        "id": journey.id,
        "reference": journey.reference,
        "status": "PARTS_READY",
        "version": version + 1,
    }
    assert await desk.balance(coil) == (2, 2)
    event = (await events_of(db, journey.id))[-1]
    assert (event.action, event.from_status, event.to_status) == (
        BookingAction.RECEIVE_PARTS,
        S.PARTS_ORDERED,
        S.PARTS_READY,
    )
    assert (event.actor_user_id, event.actor_role) == (world.parts2.id, ActorRole.PARTS_PERSON)
    assert event.metadata_ == {"purchase_order_id": order_id}
    (applied,) = published[seen:]
    assert isinstance(applied, BookingActionApplied)
    assert (applied.action, applied.version, applied.actor_user_id) == (
        BookingAction.RECEIVE_PARTS,
        version + 1,
        world.parts2.id,
    )
    assert applied.parts_person_user_id == world.parts.id  # the assignment is unchanged
    detail = await desk.detail(world.parts, journey.id)
    assert (detail["status"], detail["version"]) == ("PARTS_READY", version + 1)
    assert detail["parts_summary"]["all_available"] is True
    assert detail["allowed_actions"] == ["allocate-parts"]


# --- INV-08 (bookings half), INV-24, INV-09 -------------------------------------------------------


async def test_inv08_inv24_stock_that_arrives_another_way_leaves_the_linked_po_general(
    desk: Desk, world: World, db: Database, published: list[Event]
) -> None:
    coil = world.catalogue.coil
    journey = await drive_booking_to(desk, S.PARTS_ORDERED)
    problem(
        await desk.act_raw(world.parts.id, journey.id, "mark-parts-ready"),
        409,
        "INSUFFICIENT_STOCK",
    )
    restock = await desk.api.post(
        desk.shop_path("/purchase-orders"),
        json={"items": [{"part_id": coil["id"], "quantity": 4}]},
        headers=bearer(world.parts.id),
    )
    assert restock.status_code == 201, restock.text
    version = (await booking_row(db, journey.id)).version
    seen = len(published)
    general = await desk.receive(restock.json()["id"])
    assert general["receive_parts_applied"] is False
    assert general["purchase_order"]["booking"] is None
    assert await desk.balance(coil) == (4, 0)  # INV-08: on_hand only, nothing reserved
    assert (await booking_row(db, journey.id)).version == version
    assert published[seen:] == []
    ready = await desk.act(world.parts, journey.id, "mark-parts-ready")
    assert ready["status"] == "PARTS_READY"
    assert await desk.balance(coil) == (4, 1)
    before_parts = await booking_parts(desk, journey)
    before_events = len(await events_of(db, journey.id))
    seen = len(published)
    late = await desk.receive(str(journey.purchase_order_id))
    assert late["receive_parts_applied"] is False
    assert late["purchase_order"]["status"] == "RECEIVED"
    assert await desk.balance(coil) == (5, 1)  # INV-24: general stock
    assert await booking_parts(desk, journey) == before_parts
    assert len(await events_of(db, journey.id)) == before_events
    assert published[seen:] == []
    assert (await booking_row(db, journey.id)).status == S.PARTS_READY


async def test_inv09_a_receipt_for_a_cancelled_booking_is_general_stock(
    desk: Desk, world: World, db: Database, published: list[Event]
) -> None:
    journey = await drive_booking_to(desk, S.PARTS_ORDERED)
    await desk.act(world.advisor, journey.id, "cancel", {"reason": "Customer sold the car"})
    order = await purchase_order(desk, str(journey.purchase_order_id))
    assert (order["status"], order["booking"]["status"]) == ("ORDERED", "CANCELLED")  # D24
    events = len(await events_of(db, journey.id))
    seen = len(published)
    receipt = await desk.receive(str(journey.purchase_order_id))
    assert receipt["receive_parts_applied"] is False
    assert await desk.balance(world.catalogue.coil) == (1, 0)
    assert (await booking_row(db, journey.id)).status == S.CANCELLED
    assert len(await events_of(db, journey.id)) == events
    assert of_type(published[seen:], BookingActionApplied) == []
    assert of_type(published[seen:], BookingPartsChanged) == []


# --- SM-11, INV-13: cancel releases everything held for the booking -------------------------------


async def test_sm11_inv13_cancel_in_parts_ordered_releases_stock_and_frees_the_slot(
    desk: Desk, world: World, db: Database
) -> None:
    catalogue = world.catalogue
    journey = await drive_booking_to(desk, S.PARTS_ORDERED)
    slot = (await booking_row(db, journey.id)).slot_start
    assert await slot_count(db, world.shop_id, slot) == 1
    cancelled = await desk.act(world.advisor, journey.id, "cancel", {"reason": "Sold"})
    released = sorted([catalogue.oil_filter["id"], catalogue.engine_oil["id"]])
    assert cancelled["last_event"]["metadata"] == {
        "released": [{"part_id": part_id, "qty": 1} for part_id in released]
    }
    assert await desk.balance(catalogue.oil_filter) == (100, 0)
    assert await desk.balance(catalogue.engine_oil) == (100, 0)
    assert await desk.balance(catalogue.coil) == (0, 0)
    assert await slot_count(db, world.shop_id, slot) == 0
    assert (await purchase_order(desk, str(journey.purchase_order_id)))["status"] == "ORDERED"
    assert await booking_parts(desk, journey) == {
        "IGN-COIL-01": (1, 0, 0, 1),
        "OIL-FILTER-01": (1, 0, 0, 1),
        "ENGINE-OIL-4L": (1, 0, 0, 1),
    }
    movements = await desk.get(
        world.parts.id, desk.shop_path(f"/parts/{catalogue.oil_filter['id']}/movements")
    )
    assert movements["items"][0]["movement_type"] == "RELEASE"
    rebooked = await desk.book(slot=slot)
    assert rebooked.booking["status"] == "PENDING"  # the place is free again (BK-10)


async def test_cancel_after_allocation_is_impossible_and_consumed_stock_stays(
    desk: Desk, world: World
) -> None:
    journey = await drive_booking_to(desk, S.IN_REPAIR)
    problem(
        await desk.act_raw(world.advisor.id, journey.id, "cancel", {"reason": "Too late"}),
        409,
        "INVALID_TRANSITION",
    )
    assert await desk.balance(world.catalogue.oil_filter) == (99, 0)


# --- SM-13: labour-only jobs pass the parts steps with zero parts ---------------------------------


async def test_sm13_a_labour_only_job_passes_the_parts_steps_with_zero_parts(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.PARTS_PENDING, labour_only=True)
    assert journey.booking["last_event"]["metadata"] == {
        "parts_person_user_id": str(world.parts.id),
        "required": [],
    }
    assert journey.booking["parts_summary"] == {
        "required_count": 0,
        "available_count": 0,
        "shortage_count": 0,
        "all_available": True,
    }
    view = await desk.get(world.parts.id, desk.booking_path(journey.id, "/parts"))
    assert (view["items"], view["purchase_orders"], view["all_available"]) == ([], [], True)
    ready = await desk.act(world.parts, journey.id, "mark-parts-ready")
    assert ready["last_event"]["metadata"] == {"reserved": []}
    allocated = await desk.act(world.parts, journey.id, "allocate-parts")
    assert (allocated["status"], allocated["last_event"]["metadata"]) == (
        "IN_REPAIR",
        {"consumed": []},
    )
    for part in (world.catalogue.coil, world.catalogue.oil_filter, world.catalogue.engine_oil):
        assert (await desk.balance(part))[1] == 0

"""Stock adjustments (D82, P0) and the movement ledger (P1) over HTTP: INV-18 and SEC-06 (adjust
half), INV-21, INV-25, INV-26 (ledger order) and the D86 references on movements."""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from app.core.database import Database
from app.modules.inventory import service as inventory_service
from app.shared.clock import SimulatedClock
from app.shared.enums import MembershipRole
from app.shared.pagination import PageParams
from tests.modules.inventory.support import (
    World,
    assert_ledger_invariants,
    assert_problem,
    bearer,
    field_codes,
    movements_of,
    new_part,
    part_balance,
    reserve_for_booking,
    shop_context,
    url,
    without_booking_reader,
)

pytestmark = pytest.mark.db


async def adjust(
    api: httpx.AsyncClient, world: World, part_id: str, delta: object, reason: object = "Count"
) -> httpx.Response:
    return await api.post(
        url(world.a.id, f"/parts/{part_id}/adjustments"),
        json={"quantity_delta": delta, "reason": reason},
        headers=bearer(world.a.parts),
    )


async def test_inv21_opening_stock_and_corrections_are_adjust_movements(
    api: httpx.AsyncClient, world: World, db: Database, clock: SimulatedClock
) -> None:
    part = await new_part(api, world.a, "SPK-PLG-IR", reorder_level=4)
    opening = await adjust(api, world, part["id"], 10, " Opening stock ")
    assert opening.status_code == 201, opening.text
    body = opening.json()
    assert (body["part"]["on_hand"], body["part"]["available"], body["part"]["stock_state"]) == (
        10,
        10,
        "OK",
    )
    movement = body["movement"]
    assert movement == {
        "id": movement["id"],
        "part_id": part["id"],
        "movement_type": "ADJUST",
        "quantity": 10,
        "on_hand_delta": 10,
        "reserved_delta": 0,
        "booking": None,
        "purchase_order": None,
        "actor": {"user_id": str(world.a.parts.id), "full_name": world.a.parts.full_name},
        "note": "Opening stock",
        "created_at": "2026-10-14T04:00:00Z",
    }
    clock.advance(timedelta(hours=1))
    correction = await adjust(api, world, part["id"], -7, "Damaged in storage")
    assert correction.status_code == 201
    assert correction.json()["movement"]["quantity"] == 7
    assert correction.json()["movement"]["on_hand_delta"] == -7
    assert (correction.json()["part"]["on_hand"], correction.json()["part"]["stock_state"]) == (
        3,
        "LOW",
    )
    assert correction.json()["part"]["updated_at"] == "2026-10-14T05:00:00Z"
    ledger = await movements_of(db, part["id"])
    assert [(m.movement_type, m.on_hand_delta, m.note) for m in ledger] == [
        ("ADJUST", 10, "Opening stock"),
        ("ADJUST", -7, "Damaged in storage"),
    ]
    await assert_ledger_invariants(db)


async def test_inv25_an_adjustment_below_reserved_or_below_zero_is_insufficient_stock(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "BRK-PAD-F", stock=5)
    await reserve_for_booking(db, world.a, world.customer, {part["id"]: 3})
    before = await movements_of(db, part["id"])
    below_reserved = await adjust(api, world, part["id"], -3)
    body = assert_problem(below_reserved, 409, "INSUFFICIENT_STOCK")
    assert "lowest allowed change is -2" in body["detail"]
    assert await part_balance(db, part["id"]) == (5, 3)
    exactly_reserved = await adjust(api, world, part["id"], -2)
    assert exactly_reserved.status_code == 201
    assert (
        exactly_reserved.json()["part"]["on_hand"],
        exactly_reserved.json()["part"]["available"],
    ) == (
        3,
        0,
    )
    assert_problem(await adjust(api, world, part["id"], -1), 409, "INSUFFICIENT_STOCK")
    unreserved = await new_part(api, world.a, "OIL-4L", stock=2)
    assert_problem(await adjust(api, world, unreserved["id"], -3), 409, "INSUFFICIENT_STOCK")
    assert await part_balance(db, unreserved["id"]) == (2, 0)
    assert len(await movements_of(db, part["id"])) == len(before) + 1
    await assert_ledger_invariants(db)


async def test_inv18_sec06_only_the_parts_person_adjusts_stock(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "OIL-FLT-01", stock=1)
    for user in (world.a.owner, world.a.advisor, world.a.technician, world.a.qc):
        response = await api.post(
            url(world.a.id, f"/parts/{part['id']}/adjustments"),
            json={"quantity_delta": 5, "reason": "Owner tries"},
            headers=bearer(user),
        )
        assert_problem(response, 403, "FORBIDDEN")
    any_parts_person = await api.post(
        url(world.a.id, f"/parts/{part['id']}/adjustments"),
        json={"quantity_delta": 1, "reason": "Second parts person"},
        headers=bearer(world.a.parts2),
    )
    assert any_parts_person.status_code == 201
    assert await part_balance(db, part["id"]) == (2, 0)


async def test_adjusting_an_unknown_or_other_shops_part_is_404(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    theirs = await new_part(api, world.b, "THEIRS", stock=4)
    for part_id in (theirs["id"], str(uuid4())):
        assert_problem(await adjust(api, world, part_id, 1), 404, "NOT_FOUND")
    assert await part_balance(db, theirs["id"]) == (4, 0)
    outsider = await api.post(
        url(world.b.id, f"/parts/{theirs['id']}/adjustments"),
        json={"quantity_delta": 1, "reason": "x"},
        headers=bearer(world.a.parts),
    )
    assert_problem(outsider, 404, "NOT_FOUND")


@pytest.mark.parametrize(
    ("delta", "reason", "expected"),
    [
        (0, "Count", [("quantity_delta", "value_error")]),
        (100_001, "Count", [("quantity_delta", "less_than_equal")]),
        (-100_001, "Count", [("quantity_delta", "greater_than_equal")]),
        ("5", "Count", [("quantity_delta", "int_type")]),
        (2.5, "Count", [("quantity_delta", "int_type")]),
        (5, "", [("reason", "string_too_short")]),
        (5, " " * 3, [("reason", "string_too_short")]),
        (5, "r" * 501, [("reason", "string_too_long")]),
        (5, None, [("reason", "string_type")]),
    ],
)
async def test_adjustment_validation(
    api: httpx.AsyncClient,
    world: World,
    db: Database,
    delta: object,
    reason: object,
    expected: list[tuple[str, str]],
) -> None:
    part = await new_part(api, world.a, "X1")
    assert field_codes(await adjust(api, world, part["id"], delta, reason)) == expected
    assert await movements_of(db, part["id"]) == []


async def test_extra_fields_on_an_adjustment_are_refused(
    api: httpx.AsyncClient, world: World
) -> None:
    part = await new_part(api, world.a, "X1")
    response = await api.post(
        url(world.a.id, f"/parts/{part['id']}/adjustments"),
        json={"quantity_delta": 1, "reason": "x", "reserved_delta": 1},
        headers=bearer(world.a.parts),
    )
    assert field_codes(response) == [("reserved_delta", "extra_forbidden")]


async def test_inactive_parts_can_still_be_adjusted(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "OLD-PART", stock=3)
    deactivate = await api.patch(
        url(world.a.id, f"/parts/{part['id']}"),
        json={"is_active": False},
        headers=bearer(world.a.owner),
    )
    assert deactivate.status_code == 200
    response = await adjust(api, world, part["id"], -3, "Written off")
    assert response.status_code == 201
    assert response.json()["part"]["is_active"] is False
    assert await part_balance(db, part["id"]) == (0, 0)


# --- The ledger (P1): newest first by (created_at, seq), D79 ------------------------------------


async def movement_page(
    api: httpx.AsyncClient, world: World, part_id: str, **params: Any
) -> dict[str, Any]:
    response = await api.get(
        url(world.a.id, f"/parts/{part_id}/movements"), params=params, headers=bearer(world.a.owner)
    )
    assert response.status_code == 200, response.text
    page: dict[str, Any] = response.json()
    return page


async def test_inv26_movements_are_newest_first_and_ties_follow_insert_order(
    api: httpx.AsyncClient, world: World, db: Database, clock: SimulatedClock
) -> None:
    part = await new_part(api, world.a, "OIL-FLT-01")
    for delta in (5, 3, -2):  # the frozen clock gives all three one instant (D79)
        assert (await adjust(api, world, part["id"], delta)).status_code == 201
    clock.advance(timedelta(minutes=1))
    assert (await adjust(api, world, part["id"], 1)).status_code == 201
    page = await movement_page(api, world, part["id"])
    assert [m["on_hand_delta"] for m in page["items"]] == [1, -2, 3, 5]
    assert [m["created_at"] for m in page["items"]] == [
        "2026-10-14T04:01:00Z",
        "2026-10-14T04:00:00Z",
        "2026-10-14T04:00:00Z",
        "2026-10-14T04:00:00Z",
    ]
    stored = await movements_of(db, part["id"])
    assert [m.seq for m in stored] == sorted(m.seq for m in stored)
    running = 0
    for movement in reversed(page["items"]):  # oldest first: the running balance ends at on_hand
        running += movement["on_hand_delta"]
    assert running == (await part_balance(db, part["id"]))[0] == 7
    second = await movement_page(api, world, part["id"], limit=2, offset=2)
    assert ([m["on_hand_delta"] for m in second["items"]], second["total"]) == ([3, 5], 4)


async def test_movement_ledger_roles_and_tenancy(api: httpx.AsyncClient, world: World) -> None:
    part = await new_part(api, world.a, "OIL-FLT-01", stock=1)
    path = url(world.a.id, f"/parts/{part['id']}/movements")
    for user in (world.a.owner, world.a.parts):
        assert (await api.get(path, headers=bearer(user))).status_code == 200
    for user in (world.a.advisor, world.a.technician, world.a.qc):
        assert_problem(await api.get(path, headers=bearer(user)), 403, "FORBIDDEN")
    assert_problem(await api.get(path, headers=bearer(world.b.parts)), 404, "NOT_FOUND")
    theirs = await new_part(api, world.b, "THEIRS")
    other = await api.get(
        url(world.a.id, f"/parts/{theirs['id']}/movements"), headers=bearer(world.a.parts)
    )
    assert_problem(other, 404, "NOT_FOUND")
    unknown = await api.get(
        url(world.a.id, f"/parts/{uuid4()}/movements"), headers=bearer(world.a.parts)
    )
    assert_problem(unknown, 404, "NOT_FOUND")


async def test_movements_name_their_booking_and_purchase_order(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "IGN-COIL-01", stock=2)
    booking = await reserve_for_booking(db, world.a, world.customer, {part["id"]: 1})
    order = await api.post(
        url(world.a.id, "/purchase-orders"),
        json={"items": [{"part_id": part["id"], "quantity": 1}]},
        headers=bearer(world.a.parts),
    )
    received = await api.post(
        url(world.a.id, f"/purchase-orders/{order.json()['id']}/receive"),
        json={"items": [{"item_id": order.json()["items"][0]["id"], "quantity": 1}]},
        headers=bearer(world.a.parts2),
    )
    assert received.status_code == 200, received.text
    page = await movement_page(api, world, part["id"])
    by_type = {m["movement_type"]: m for m in page["items"]}
    assert by_type["RESERVE"]["booking"] == {"id": str(booking.id), "reference": booking.reference}
    assert by_type["RESERVE"]["purchase_order"] is None
    assert by_type["RECEIVE"]["booking"] is None
    assert by_type["RECEIVE"]["purchase_order"] == {
        "id": order.json()["id"],
        "po_number": order.json()["po_number"],
    }
    assert by_type["RECEIVE"]["actor"]["user_id"] == str(world.a.parts2.id)


async def test_an_unregistered_booking_reader_fails_loud_once_a_booking_is_involved(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    part = await new_part(api, world.a, "IGN-COIL-01", stock=2)
    with without_booking_reader():
        plain = await movement_page(api, world, part["id"])  # no booking id: the port is unused
        assert [m["movement_type"] for m in plain["items"]] == ["ADJUST"]
    await reserve_for_booking(db, world.a, world.customer, {part["id"]: 1})
    with without_booking_reader():
        response = await api.get(
            url(world.a.id, f"/parts/{part['id']}/movements"), headers=bearer(world.a.owner)
        )
        assert_problem(response, 500, "INTERNAL_ERROR")
        async with db.sessionmaker() as session:
            with pytest.raises(RuntimeError, match="no BookingRefReader is registered"):
                await inventory_service.list_part_movements(
                    session,
                    shop_context(world.a, world.a.owner, MembershipRole.OWNER),
                    UUID(part["id"]),
                    PageParams(),
                )
    assert len((await movement_page(api, world, part["id"]))["items"]) == 2

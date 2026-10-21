"""NOT-07 and spec 08 principle 4: one action is one transaction (`modules/bookings.md` §11).

A subscriber of the published event runs inside the action's transaction (after the
notifications handler wrote its rows), so when it fails, everything the action wrote is rolled
back together: status, version, event, estimates, stock, slot counter, purchase orders and the
notification rows. Asserted for a staff cancel (409 and 500 failures), the wizard, an estimate
edit that creates a version, and a partial receipt's `BookingPartsChanged` (D83).
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI

from app.core.database import Database
from app.core.errors import Conflict
from app.modules.bookings.events import BookingActionApplied, BookingPartsChanged
from app.shared.enums import BookingStatus
from app.shared.event_bus import Event
from app.shared.uow import UnitOfWork
from tests.modules.bookings.support import (
    Desk,
    World,
    booking_row,
    count_rows,
    drive_booking_to,
    estimate_statuses,
    events_of,
    labour_lines,
    problem,
    slot_count,
    worked_lines,
)
from tests.modules.identity.builders import TEST_PASSWORD, unique_email

pytestmark = pytest.mark.db

S = BookingStatus
TABLES = (
    "users",
    "vehicles",
    "bookings",
    "booking_events",
    "booking_services",
    "estimates",
    "estimate_lines",
    "booking_parts",
    "stock_movements",
    "purchase_orders",
    "qc_inspections",
    "notifications",
)

type Install = Callable[[type[Event], Exception], None]


@pytest.fixture
def fail_on(db_app: FastAPI) -> Install:
    """Subscribe a handler that raises `error` whenever `kind` is published (last in line)."""

    def install(kind: type[Event], error: Exception) -> None:
        async def fail(event: Event, uow: UnitOfWork) -> None:
            raise error

        db_app.state.event_bus.subscribe(kind, fail)

    return install


async def snapshot(db: Database) -> dict[str, int]:
    return {table: await count_rows(db, table) for table in TABLES}


async def booking_state(desk: Desk, db: Database, booking_id: str) -> tuple[Any, ...]:
    row = await booking_row(db, booking_id)
    catalogue = desk.world.catalogue
    return (
        row.status,
        row.version,
        row.updated_at,
        row.cancelled_at,
        len(await events_of(db, booking_id)),
        await estimate_statuses(db, booking_id),
        await slot_count(db, row.shop_id, row.slot_start),
        await desk.balance(catalogue.coil),
        await desk.balance(catalogue.oil_filter),
        await desk.balance(catalogue.engine_oil),
    )


@pytest.mark.parametrize(
    "failure",
    [
        (Conflict("A downstream rule refused it."), 409, "CONFLICT"),
        (RuntimeError("downstream bug"), 500, "INTERNAL_ERROR"),
    ],
)
async def test_not07_a_failing_subscriber_rolls_back_the_whole_cancel(
    desk: Desk, world: World, db: Database, fail_on: Install, failure: tuple[Exception, int, str]
) -> None:
    error, status, code = failure
    journey = await drive_booking_to(desk, S.PARTS_ORDERED)
    before = (await booking_state(desk, db, journey.id), await snapshot(db))
    fail_on(BookingActionApplied, error)
    response = await desk.act_raw(world.advisor.id, journey.id, "cancel", {"reason": "Sold"})
    problem(response, status, code)
    assert (await booking_state(desk, db, journey.id), await snapshot(db)) == before


async def test_not07_a_failed_wizard_leaves_no_account_car_booking_or_place(
    desk: Desk, world: World, db: Database, fail_on: Install
) -> None:
    before = await snapshot(db)
    fail_on(BookingActionApplied, Conflict("A downstream rule refused it."))
    body = desk.booking_body()
    body["customer"] = {"full_name": "Ahmed", "email": unique_email(), "password": TEST_PASSWORD}
    response = await desk.wizard(body)
    problem(response, 409, "CONFLICT")
    assert "set-cookie" not in response.headers
    assert await snapshot(db) == before
    assert await count_rows(db, "slot_counters") == 0


async def test_not07_a_failed_estimate_edit_keeps_the_submitted_version(
    desk: Desk, world: World, db: Database, fail_on: Install
) -> None:
    journey = await drive_booking_to(desk, S.ESTIMATE_REVIEW)
    inspecting = await drive_booking_to(desk, S.INSPECTING)
    before = (await booking_state(desk, db, journey.id), await snapshot(db))
    fail_on(BookingActionApplied, Conflict("A downstream rule refused it."))
    await desk.edit(world.advisor, journey.id, worked_lines(world, labour="3500"), expect=409)
    assert (await booking_state(desk, db, journey.id), await snapshot(db)) == before
    assert await estimate_statuses(db, journey.id) == [(1, "SUBMITTED")]
    saved = await desk.edit(world.technician, inspecting.id, labour_lines())  # no event: no failure
    assert saved["created_new_version"] is False


async def test_not07_a_failed_partial_receipt_receives_nothing(
    desk: Desk, world: World, db: Database, fail_on: Install
) -> None:
    coil = world.catalogue.coil
    journey = await drive_booking_to(desk, S.INSPECTING)
    lines = [{"line_type": "PART", "part_id": coil["id"], "quantity": "2"}]
    await desk.edit(world.technician, journey.id, lines)
    await desk.act(world.technician, journey.id, "submit-estimate")
    await desk.act(world.advisor, journey.id, "send-estimate")
    estimate_id = (await desk.my_detail(journey.customer, journey.id))["estimate"]["id"]
    await desk.my_act(
        journey.customer, journey.id, "approve-estimate", {"estimate_id": estimate_id}
    )
    body = {"parts_person_user_id": str(world.parts.id)}
    await desk.act(world.advisor, journey.id, "assign-parts-person", body)
    ordered = await desk.act(world.parts, journey.id, "order-parts")
    order_id = ordered["last_event"]["metadata"]["purchase_order_id"]
    before = (await booking_state(desk, db, journey.id), await snapshot(db))
    fail_on(BookingPartsChanged, Conflict("A downstream rule refused it."))
    await desk.receive(order_id, {coil["id"]: 1}, expect=409)
    assert (await booking_state(desk, db, journey.id), await snapshot(db)) == before
    order = await desk.get(world.parts.id, desk.shop_path(f"/purchase-orders/{order_id}"))
    assert (order["status"], order["items"][0]["received_qty"]) == ("ORDERED", 0)


async def test_text_the_database_cannot_store_rolls_the_whole_action_back(
    desk: Desk, world: World, db: Database
) -> None:
    """A NUL reaches PostgreSQL only at the flush, after `decline` already released the slot:
    the 422 must undo the release too."""
    pending = await drive_booking_to(desk, S.PENDING)
    queued = await drive_booking_to(desk, S.QC_IN_PROGRESS)
    before = (
        await booking_state(desk, db, pending.id),
        await booking_state(desk, db, queued.id),
        await snapshot(db),
    )
    attempts = [
        (world.advisor.id, pending.id, "decline", {"reason": "Bays\u0000 full"}),
        (world.advisor.id, pending.id, "confirm", {"note": "VIP\u0000"}),
        (
            world.qc.id,
            queued.id,
            "fail-qc",
            {"issue_title": "Leak\u0000", "issue_description": "x"},
        ),
    ]
    for user_id, booking_id, slug, body in attempts:
        response = await desk.act_raw(user_id, booking_id, slug, body)
        problem(response, 422, "VALIDATION_ERROR")
    after = (
        await booking_state(desk, db, pending.id),
        await booking_state(desk, db, queued.id),
        await snapshot(db),
    )
    assert after == before

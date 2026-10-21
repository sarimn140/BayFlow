"""SM-18 ★: the brief's worked example end to end over HTTP (spec 08 "Worked example trace").

Lahore Auto Care with 10 oil filters, 8 engine oils and no ignition coil; Ahmed books Friday
10:00 through the wizard, and every later step is the real route of its actor: the estimate
(16,600 → 16,100, v1 `SUPERSEDED`), the out-of-stock coil ordered, received and allocated, a
failed QC round, the re-test, the pass, notify-ready and completion. The desk steps run once as
Bilal (SA) and once as Fatima (Owner), who may perform every SA action (SM-16). INV-13 checks
the same stock coming back on a cancel.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from app.core.database import Database
from app.modules.bookings.events import BookingActionApplied, BookingPartsChanged
from app.modules.bookings.models import BookingEvent
from app.shared.clock import SimulatedClock
from app.shared.enums import ActorRole, BookingAction, BookingStatus
from app.shared.event_bus import Event
from tests.assertions import assert_invariants
from tests.modules.bookings.support import (
    FRIDAY_1000,
    Desk,
    World,
    build_world,
    drive_booking_to,
    estimate_statuses,
    full_checklist,
    slot_count,
    worked_lines,
)
from tests.modules.identity.builders import TEST_PASSWORD, bearer, unique_email

pytestmark = [pytest.mark.db, pytest.mark.scenario]

S = BookingStatus
A = BookingAction


@pytest.fixture
async def world(db: Database, clock: SimulatedClock) -> World:
    """The brief's stock: 10 oil filters, 8 engine oils, no ignition coil; 2 cars per slot."""
    return await build_world(db, capacity=2, filters=10, oil=8, coils=0)


async def stock(desk: Desk) -> dict[str, tuple[int, int]]:
    catalogue = desk.world.catalogue
    return {
        "coil": await desk.balance(catalogue.coil),
        "filter": await desk.balance(catalogue.oil_filter),
        "oil": await desk.balance(catalogue.engine_oil),
    }


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """October 2026, Karachi time (UTC+5) as UTC."""
    return datetime(2026, 10, day, hour - 5, minute, tzinfo=UTC)


@pytest.mark.parametrize("desk_role", ["advisor", "owner"])
async def test_sm18_the_worked_example_end_to_end(  # noqa: PLR0915 - the brief's 16 steps
    desk: Desk,
    world: World,
    db: Database,
    clock: SimulatedClock,
    published: list[Event],
    desk_role: str,
) -> None:
    front = world.advisor if desk_role == "advisor" else world.owner
    front_id = front.id
    front_role = ActorRole.SERVICE_ADVISOR if desk_role == "advisor" else ActorRole.OWNER
    imran, usman, sara = world.technician, world.parts, world.qc
    assert await stock(desk) == {"coil": (0, 0), "filter": (10, 0), "oil": (8, 0)}

    # Steps 1-3: Ahmed books through the wizard (Wednesday 09:00): account created, logged in.
    body = desk.booking_body(slot=FRIDAY_1000)
    body["customer"] = {
        "full_name": "Ahmed Khan",
        "email": unique_email("ahmed"),
        "password": TEST_PASSWORD,
        "phone": "+92 300 1234567",
    }
    body["customer_notes"] = "Check engine light is on; oil change due."
    created = await desk.wizard(body)
    assert created.status_code == 201, created.text
    assert created.json()["account_created"] is True
    assert created.headers["set-cookie"].startswith("bf_session=")
    ahmed = {"Authorization": f"Bearer {created.json()['access_token']}"}
    booking = created.json()["booking"]
    booking_id = booking["id"]
    assert (booking["status"], booking["slot_start"]) == ("PENDING", "2026-10-16T05:00:00Z")
    assert [service["name"] for service in booking["services"]] == [
        "Check engine light",
        "Oil change",
    ]
    assert await slot_count(db, world.shop_id, FRIDAY_1000) == 1

    async def staff(member_id: uuid.UUID, slug: str, json: dict[str, Any] | None = None) -> Any:
        response = await desk.api.post(
            desk.booking_path(booking_id, f"/actions/{slug}"),
            json=json or {},
            headers=bearer(member_id),
        )
        assert response.status_code == 200, (slug, response.text)
        return response.json()

    async def customer(slug: str, json: dict[str, Any]) -> Any:
        response = await desk.api.post(
            desk.my_path(booking_id, f"/actions/{slug}"), json=json, headers=ahmed
        )
        assert response.status_code == 200, (slug, response.text)
        return response.json()

    async def put_estimate(member_id: uuid.UUID, lines: list[dict[str, Any]]) -> Any:
        response = await desk.api.put(
            desk.booking_path(booking_id, "/estimate"),
            json={"lines": lines},
            headers=bearer(member_id),
        )
        assert response.status_code == 200, response.text
        return response.json()

    # Step 4: confirm and assign Imran.
    clock.set(at(14, 10))
    await staff(front_id, "confirm")
    assigned = await staff(front_id, "assign-technician", {"technician_user_id": str(imran.id)})
    assert assigned["status"] == "ASSIGNED"

    # Step 5 (Friday 10:00, the car is in): inspection, estimate v1 = 16,600, submitted.
    clock.set(at(16, 10))
    await staff(imran.id, "start-inspection")
    v1 = await put_estimate(imran.id, worked_lines(world))
    assert (v1["version"], v1["grand_total"], v1["created_new_version"]) == (1, "16600.00", False)
    coil_line = next(
        line for line in v1["lines"] if line["part"] and line["part"]["sku"] == "IGN-COIL-01"
    )
    assert coil_line["part"]["stock_state"] == "OUT"
    review = await staff(imran.id, "submit-estimate")
    assert review["status"] == "ESTIMATE_REVIEW"

    # Step 6: the desk lowers the labour to 3,500 (v2 = 16,100, v1 SUPERSEDED) and sends it.
    clock.set(at(16, 11))
    v2 = await put_estimate(front_id, worked_lines(world, labour="3500"))
    assert (v2["version"], v2["grand_total"], v2["created_new_version"]) == (2, "16100.00", True)
    sent = await staff(front_id, "send-estimate")
    assert sent["status"] == "AWAITING_CUSTOMER"
    assert await estimate_statuses(db, booking_id) == [(1, "SUPERSEDED"), (2, "SENT")]

    # Step 7: Ahmed approves v2 (timestamped).
    clock.set(at(16, 12))
    mine = (await desk.api.get(desk.my_path(booking_id), headers=ahmed)).json()
    assert (mine["estimate"]["version"], mine["estimate"]["grand_total"]) == (2, "16100.00")
    assert mine["allowed_actions"] == ["approve-estimate", "reject-estimate", "cancel"]
    approved = await customer("approve-estimate", {"estimate_id": mine["estimate"]["id"]})
    assert approved["estimate"]["status"] == "APPROVED"
    assert approved["estimate"]["decided_at"] == "2026-10-16T07:00:00Z"

    # Step 8: Usman is assigned; three booking parts.
    pending = await staff(front_id, "assign-parts-person", {"parts_person_user_id": str(usman.id)})
    assert pending["status"] == "PARTS_PENDING"
    assert pending["parts_summary"] == {
        "required_count": 3,
        "available_count": 2,
        "shortage_count": 1,
        "all_available": False,
    }

    # Step 9: order-parts reserves the filter and the oil and orders one coil.
    clock.set(at(16, 13))
    ordered = await staff(usman.id, "order-parts")
    assert ordered["status"] == "PARTS_ORDERED"
    order_id = ordered["last_event"]["metadata"]["purchase_order_id"]
    assert await stock(desk) == {"coil": (0, 0), "filter": (10, 1), "oil": (8, 1)}

    # Step 10: the coil arrives (RECEIVE_PARTS) and the parts are allocated.
    clock.set(at(16, 13, 30))
    receipt = await desk.receive(order_id, by=usman)
    assert receipt["receive_parts_applied"] is True
    assert receipt["purchase_order"]["status"] == "RECEIVED"
    assert receipt["purchase_order"]["booking"]["status"] == "PARTS_READY"
    assert await stock(desk) == {"coil": (1, 1), "filter": (10, 1), "oil": (8, 1)}
    in_repair = await staff(usman.id, "allocate-parts")
    assert in_repair["status"] == "IN_REPAIR"
    assert await stock(desk) == {"coil": (0, 0), "filter": (9, 0), "oil": (7, 0)}

    # Step 11: Imran repairs and sends it to QC.
    clock.set(at(16, 14))
    started = await staff(imran.id, "start-repair")
    assert started["repair_started_at"] == "2026-10-16T09:00:00Z"
    queued = await staff(imran.id, "send-to-qc")
    assert (queued["status"], queued["qc_round"]) == ("QC_PENDING", 1)

    # Step 12: Sara picks it and fails it ("Oil leak at filter").
    clock.set(at(16, 15))
    await staff(sara.id, "pick-qc")
    failed = await staff(
        sara.id,
        "fail-qc",
        {"issue_title": "Oil leak at filter", "issue_description": "Seal weeps after the drive."},
    )
    assert failed["status"] == "IN_REPAIR"
    issues = (await desk.get(imran.id, desk.booking_path(booking_id, "/qc-inspections")))["items"]
    assert [(issue["title"], issue["status"]) for issue in issues[0]["issues"]] == [
        ("Oil leak at filter", "OPEN")
    ]

    # Step 13: Imran fixes it and sends it back; the issue is resolved.
    clock.set(at(16, 16))
    await staff(imran.id, "send-to-qc", {"repair_notes": "Seal replaced"})
    issues = (await desk.get(imran.id, desk.booking_path(booking_id, "/qc-inspections")))["items"]
    assert issues[0]["issues"][0]["status"] == "RESOLVED"

    # Step 14: Sara re-tests and passes it.
    clock.set(at(16, 16, 30))
    await staff(sara.id, "pick-qc")
    ready = await staff(sara.id, "pass-qc", {"checklist": full_checklist()})
    assert (ready["status"], ready["qc_inspector"]["full_name"], ready["qc_round"]) == (
        "READY_FOR_PICKUP",
        "Sara",
        2,
    )

    # Step 15: the desk tells Ahmed his car is ready.
    clock.set(at(16, 17))
    notified = await staff(front_id, "notify-ready")
    assert notified["ready_notified_at"] == "2026-10-16T12:00:00Z"

    # Step 16: Ahmed collects it and completes the booking.
    clock.set(at(16, 17, 30))
    done = await customer("complete", {})
    assert (done["status"], done["completed_at"]) == ("COMPLETED", "2026-10-16T12:30:00Z")
    assert done["allowed_actions"] == []

    # The trail: one event per action, each published once, in order (SM-20, NOT-01's input).
    expected = [
        (A.CREATE, None, S.PENDING, ActorRole.CUSTOMER),
        (A.CONFIRM, S.PENDING, S.CONFIRMED, front_role),
        (A.ASSIGN_TECHNICIAN, S.CONFIRMED, S.ASSIGNED, front_role),
        (A.START_INSPECTION, S.ASSIGNED, S.INSPECTING, ActorRole.TECHNICIAN),
        (A.SUBMIT_ESTIMATE, S.INSPECTING, S.ESTIMATE_REVIEW, ActorRole.TECHNICIAN),
        (A.EDIT_ESTIMATE, S.ESTIMATE_REVIEW, S.ESTIMATE_REVIEW, front_role),
        (A.SEND_ESTIMATE, S.ESTIMATE_REVIEW, S.AWAITING_CUSTOMER, front_role),
        (A.APPROVE_ESTIMATE, S.AWAITING_CUSTOMER, S.ESTIMATE_APPROVED, ActorRole.CUSTOMER),
        (A.ASSIGN_PARTS_PERSON, S.ESTIMATE_APPROVED, S.PARTS_PENDING, front_role),
        (A.ORDER_PARTS, S.PARTS_PENDING, S.PARTS_ORDERED, ActorRole.PARTS_PERSON),
        (A.RECEIVE_PARTS, S.PARTS_ORDERED, S.PARTS_READY, ActorRole.PARTS_PERSON),
        (A.ALLOCATE_PARTS, S.PARTS_READY, S.IN_REPAIR, ActorRole.PARTS_PERSON),
        (A.START_REPAIR, S.IN_REPAIR, S.IN_REPAIR, ActorRole.TECHNICIAN),
        (A.SEND_TO_QC, S.IN_REPAIR, S.QC_PENDING, ActorRole.TECHNICIAN),
        (A.PICK_QC, S.QC_PENDING, S.QC_IN_PROGRESS, ActorRole.QC_INSPECTOR),
        (A.FAIL_QC, S.QC_IN_PROGRESS, S.IN_REPAIR, ActorRole.QC_INSPECTOR),
        (A.SEND_TO_QC, S.IN_REPAIR, S.QC_PENDING, ActorRole.TECHNICIAN),
        (A.PICK_QC, S.QC_PENDING, S.QC_IN_PROGRESS, ActorRole.QC_INSPECTOR),
        (A.PASS_QC, S.QC_IN_PROGRESS, S.READY_FOR_PICKUP, ActorRole.QC_INSPECTOR),
        (A.NOTIFY_READY, S.READY_FOR_PICKUP, S.READY_FOR_PICKUP, front_role),
        (A.COMPLETE, S.READY_FOR_PICKUP, S.COMPLETED, ActorRole.CUSTOMER),
    ]
    async with db.sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(BookingEvent)
                    .where(BookingEvent.booking_id == uuid.UUID(booking_id))
                    .order_by(BookingEvent.created_at, BookingEvent.seq)
                )
            )
            .scalars()
            .all()
        )
        await assert_invariants(session)
    assert [(e.action, e.from_status, e.to_status, e.actor_role) for e in rows] == expected
    applied = [event for event in published if isinstance(event, BookingActionApplied)]
    assert [(e.action, e.from_status, e.to_status, e.actor_role) for e in applied] == expected
    assert [e.version for e in applied] == list(range(1, len(expected) + 1))
    assert [event for event in published if isinstance(event, BookingPartsChanged)] == []
    final = await desk.detail(front, booking_id)
    assert (final["status"], final["version"]) == ("COMPLETED", len(expected))
    assert final["estimate_summary"]["grand_total"] == "16100.00"
    staff_timeline = (await desk.get(front_id, desk.booking_path(booking_id, "/events")))["items"]
    assert [event["action"] for event in staff_timeline] == [
        action.value for action, *_ in expected
    ]
    customer_timeline = (
        await desk.api.get(desk.my_path(booking_id, "/events"), headers=ahmed)
    ).json()["items"]
    assert "EDIT_ESTIMATE" not in [event["action"] for event in customer_timeline]
    assert len(customer_timeline) == len(expected) - 1


async def test_inv13_cancel_returns_the_worked_example_stock(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.PARTS_ORDERED, slot=FRIDAY_1000)
    assert await stock(desk) == {"coil": (0, 0), "filter": (10, 1), "oil": (8, 1)}
    await desk.my_act(journey.customer, journey.id, "cancel", {"reason": "Sold the car"})
    assert await stock(desk) == {"coil": (0, 0), "filter": (10, 0), "oil": (8, 0)}
    assert await slot_count(db, world.shop_id, FRIDAY_1000) == 0
    order = await desk.get(
        world.parts.id, desk.shop_path(f"/purchase-orders/{journey.purchase_order_id}")
    )
    assert order["status"] == "ORDERED"  # linked POs are untouched (D24)

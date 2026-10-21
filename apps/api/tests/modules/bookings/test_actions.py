"""The action executor (spec 08 "How an action is executed"; `modules/bookings.md` §7.4, §7.6).

SM-02, SM-15, SM-20, BK-21…BK-25, API-10, the published `BookingActionApplied` contract (§8),
D63's single instant per action (under a stepping clock), and the programming errors of the
service entry points (never reachable over HTTP).
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.core.database import Database
from app.modules.bookings import service as bookings_service
from app.modules.bookings.events import BookingActionApplied
from app.modules.bookings.schemas import (
    ApproveEstimateRequest,
    CancelRequest,
    ConfirmRequest,
    CustomerCancelRequest,
    StartInspectionRequest,
)
from app.modules.identity import service as identity_service
from app.shared.auth import CurrentUser
from app.shared.clock import SimulatedClock, use_clock
from app.shared.enums import ActorRole, BookingAction, BookingStatus, MembershipRole
from app.shared.event_bus import Event
from tests.assertions import assert_invariants
from tests.modules.bookings.support import (
    FRIDAY_1000,
    Desk,
    Journey,
    World,
    booking_row,
    context,
    drive_booking_to,
    events_of,
    field_codes,
    full_checklist,
    new_customer,
    problem,
    slot_count,
)
from tests.modules.identity.builders import bearer, make_user, unit_of_work
from tests.modules.shops.builders import add_member, make_services, make_shop, set_member_active

pytestmark = pytest.mark.db


def actors(world: World, journey: Journey) -> dict[str, uuid.UUID]:
    return {
        "customer": journey.customer.user_id,
        "advisor": world.advisor.id,
        "technician": world.technician.id,
        "parts": world.parts.id,
        "qc": world.qc.id,
    }


# --- SM-02, SM-20: every action writes exactly one event ------------------------------------------


async def test_sm02_sm20_the_full_path_writes_one_event_per_action(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.COMPLETED)
    who = actors(world, journey)
    events = await events_of(db, journey.id)
    observed = [
        (event.action, event.from_status, event.to_status, event.actor_user_id, event.actor_role)
        for event in events
    ]
    s = BookingStatus
    a = BookingAction
    assert observed == [
        (a.CREATE, None, s.PENDING, who["customer"], ActorRole.CUSTOMER),
        (a.CONFIRM, s.PENDING, s.CONFIRMED, who["advisor"], ActorRole.SERVICE_ADVISOR),
        (a.ASSIGN_TECHNICIAN, s.CONFIRMED, s.ASSIGNED, who["advisor"], ActorRole.SERVICE_ADVISOR),
        (a.START_INSPECTION, s.ASSIGNED, s.INSPECTING, who["technician"], ActorRole.TECHNICIAN),
        (
            a.SUBMIT_ESTIMATE,
            s.INSPECTING,
            s.ESTIMATE_REVIEW,
            who["technician"],
            ActorRole.TECHNICIAN,
        ),
        (
            a.SEND_ESTIMATE,
            s.ESTIMATE_REVIEW,
            s.AWAITING_CUSTOMER,
            who["advisor"],
            ActorRole.SERVICE_ADVISOR,
        ),
        (
            a.APPROVE_ESTIMATE,
            s.AWAITING_CUSTOMER,
            s.ESTIMATE_APPROVED,
            who["customer"],
            ActorRole.CUSTOMER,
        ),
        (
            a.ASSIGN_PARTS_PERSON,
            s.ESTIMATE_APPROVED,
            s.PARTS_PENDING,
            who["advisor"],
            ActorRole.SERVICE_ADVISOR,
        ),
        (a.ORDER_PARTS, s.PARTS_PENDING, s.PARTS_ORDERED, who["parts"], ActorRole.PARTS_PERSON),
        (a.RECEIVE_PARTS, s.PARTS_ORDERED, s.PARTS_READY, who["parts"], ActorRole.PARTS_PERSON),
        (a.ALLOCATE_PARTS, s.PARTS_READY, s.IN_REPAIR, who["parts"], ActorRole.PARTS_PERSON),
        (a.SEND_TO_QC, s.IN_REPAIR, s.QC_PENDING, who["technician"], ActorRole.TECHNICIAN),
        (a.PICK_QC, s.QC_PENDING, s.QC_IN_PROGRESS, who["qc"], ActorRole.QC_INSPECTOR),
        (a.PASS_QC, s.QC_IN_PROGRESS, s.READY_FOR_PICKUP, who["qc"], ActorRole.QC_INSPECTOR),
        (a.COMPLETE, s.READY_FOR_PICKUP, s.COMPLETED, who["advisor"], ActorRole.SERVICE_ADVISOR),
    ]
    row = await booking_row(db, journey.id)
    assert row.version == len(events) == 15
    assert journey.booking["version"] == 15
    async with db.sessionmaker() as session:
        await assert_invariants(session)


async def test_sm02_operations_keep_the_status_and_still_write_an_event(
    desk: Desk, world: World, db: Database, clock: SimulatedClock
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.IN_REPAIR)
    clock.advance(timedelta(minutes=10))
    repaired = await desk.act(world.technician, journey.id, "start-repair")
    assert repaired["status"] == "IN_REPAIR"
    assert repaired["repair_started_at"] == "2026-10-14T04:10:00Z"
    assert repaired["version"] == journey.booking["version"] + 1
    last = repaired["last_event"]
    assert (last["action"], last["from_status"], last["to_status"]) == (
        "START_REPAIR",
        "IN_REPAIR",
        "IN_REPAIR",
    )
    ready = await drive_booking_to(desk, BookingStatus.READY_FOR_PICKUP)
    notified = await desk.act(world.advisor, ready.id, "notify-ready")
    assert notified["status"] == "READY_FOR_PICKUP"
    assert notified["ready_notified_at"] == "2026-10-14T04:10:00Z"
    assert notified["last_event"]["action"] == "NOTIFY_READY"


# --- SM-15: expected_version ----------------------------------------------------------------------


async def test_sm15_a_stale_expected_version_is_409_concurrent_update(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.PENDING)
    stale = await desk.act_raw(world.advisor.id, journey.id, "confirm", {"expected_version": 2})
    problem(stale, 409, "CONCURRENT_UPDATE")
    assert (await booking_row(db, journey.id)).version == 1
    confirmed = await desk.act(world.advisor, journey.id, "confirm", {"expected_version": 1})
    assert confirmed["version"] == 2
    # A double click from the same render: the status is checked first (spec 03 §7.5).
    again = await desk.act_raw(world.advisor.id, journey.id, "confirm", {"expected_version": 1})
    body = problem(again, 409, "INVALID_TRANSITION")
    assert body["detail"] == "'confirm' is not allowed while the booking is CONFIRMED."
    assert len(await events_of(db, journey.id)) == 2


async def test_sm15_repeatable_operations_are_deduplicated_by_expected_version(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.READY_FOR_PICKUP)
    version = journey.booking["version"]
    first = await desk.act(world.advisor, journey.id, "notify-ready", {"expected_version": version})
    assert first["version"] == version + 1
    second = await desk.act_raw(
        world.advisor.id, journey.id, "notify-ready", {"expected_version": version}
    )
    problem(second, 409, "CONCURRENT_UPDATE")
    assert [e.action for e in await events_of(db, journey.id)].count(
        BookingAction.NOTIFY_READY
    ) == 1


async def test_sm15_customer_actions_check_the_version_too(desk: Desk, db: Database) -> None:
    journey = await drive_booking_to(desk, BookingStatus.AWAITING_CUSTOMER)
    estimate_id = journey.booking["estimate_summary"]["estimate_id"]
    response = await desk.api.post(
        desk.my_path(journey.id, "/actions/approve-estimate"),
        json={"estimate_id": estimate_id, "expected_version": 1},
        headers=journey.customer.headers,
    )
    problem(response, 409, "CONCURRENT_UPDATE")
    approved = await desk.my_act(
        journey.customer,
        journey.id,
        "approve-estimate",
        {"estimate_id": estimate_id, "expected_version": journey.booking["version"]},
    )
    assert approved["status"] == "ESTIMATE_APPROVED"
    assert approved["allowed_actions"] == ["cancel"]


# --- BK-21: eligible assignees --------------------------------------------------------------------


async def test_bk21_assignees_must_be_active_members_with_the_required_role(
    desk: Desk, world: World, db: Database
) -> None:
    confirmed = await drive_booking_to(desk, BookingStatus.CONFIRMED)
    departed = await add_member(db, world.shop, MembershipRole.TECHNICIAN, full_name="Departed")
    await set_member_active(db, world.shop, departed.membership_id, active=False)
    locked_out = await add_member(db, world.shop, MembershipRole.TECHNICIAN, full_name="Locked")
    async with unit_of_work(db) as uow:
        await identity_service.set_user_active(uow, user_id=locked_out.id, is_active=False)
    other_shop_tech = await add_member(db, world.other, MembershipRole.TECHNICIAN)
    candidates = [
        world.parts.id,  # wrong role
        world.owner.id,  # the Owner is no technician
        departed.id,  # inactive membership
        locked_out.id,  # inactive account
        other_shop_tech.id,  # another shop
        uuid.uuid4(),  # unknown
    ]
    for candidate in candidates:
        response = await desk.act_raw(
            world.advisor.id,
            confirmed.id,
            "assign-technician",
            {"technician_user_id": str(candidate)},
        )
        body = problem(response, 422, "MEMBER_NOT_ELIGIBLE")
        assert field_codes(body) == [("technician_user_id", "invalid_reference")]
    row = await booking_row(db, confirmed.id)
    assert (row.status, row.version, row.technician_user_id) == (BookingStatus.CONFIRMED, 2, None)
    approved = await drive_booking_to(desk, BookingStatus.ESTIMATE_APPROVED)
    response = await desk.act_raw(
        world.advisor.id,
        approved.id,
        "assign-parts-person",
        {"parts_person_user_id": str(world.technician.id)},
    )
    body = problem(response, 422, "MEMBER_NOT_ELIGIBLE")
    assert field_codes(body) == [("parts_person_user_id", "invalid_reference")]
    assert (await booking_row(db, approved.id)).status == BookingStatus.ESTIMATE_APPROVED


# --- BK-22: reasons -------------------------------------------------------------------------------


async def test_bk22_decline_and_staff_cancel_need_a_reason_the_customer_may_omit_it(
    desk: Desk, world: World, db: Database
) -> None:
    pending = await drive_booking_to(desk, BookingStatus.PENDING)
    for body in ({}, {"reason": "   "}, {"reason": "r" * 501}):
        response = await desk.act_raw(world.advisor.id, pending.id, "decline", body)
        problem(response, 422, "VALIDATION_ERROR")
        response = await desk.act_raw(world.advisor.id, pending.id, "cancel", body)
        problem(response, 422, "VALIDATION_ERROR")
    assert (await booking_row(db, pending.id)).version == 1
    cancelled = await desk.my_act(pending.customer, pending.id, "cancel")
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["cancel_reason"] is None
    assert cancelled["cancelled_by_customer"] is True
    declined = await drive_booking_to(desk, BookingStatus.PENDING)
    detail = await desk.act(world.advisor, declined.id, "decline", {"reason": "  Bays full.  "})
    assert (detail["status"], detail["cancel_reason"]) == ("CANCELLED", "Bays full.")
    assert detail["cancelled_by"] == {"user_id": str(world.advisor.id), "full_name": "Bilal"}
    assert detail["last_event"]["note"] == "Bays full."


# --- BK-10: a freed place can be booked again -----------------------------------------------------


async def test_bk10_decline_and_cancel_free_the_place_and_never_go_below_zero(
    desk: Desk, world: World, db: Database
) -> None:
    small = await make_shop(db, owner=world.owner, name="Raza Auto Works", capacity=1)
    services = await make_services(db, small, ["Oil change"])
    customers = [await new_customer(db, full_name=f"Customer {n}") for n in range(4)]

    async def book(index: int) -> Any:
        body = desk.booking_body(slot=FRIDAY_1000, shop_id=small.id, services=services)
        return await desk.wizard(body, headers=customers[index].headers)

    first = await book(0)
    assert first.status_code == 201, first.text
    problem(await book(1), 409, "SLOT_FULL")
    first_id = first.json()["booking"]["id"]
    owner = small.owner  # the Owner may do every SA action (D16)
    path = desk.booking_path(first_id, "/actions/decline", shop_id=small.id)
    declined = await desk.api.post(path, json={"reason": "Lift broken"}, headers=bearer(owner.id))
    assert declined.status_code == 200, declined.text
    assert await slot_count(db, small.id, FRIDAY_1000) == 0
    again = await desk.api.post(path, json={"reason": "Twice"}, headers=bearer(owner.id))
    problem(again, 409, "INVALID_TRANSITION")
    assert await slot_count(db, small.id, FRIDAY_1000) == 0  # never below zero
    second = await book(2)
    assert second.status_code == 201, second.text  # the place is bookable again
    second_id = second.json()["booking"]["id"]
    cancel = await desk.api.post(
        desk.my_path(second_id, "/actions/cancel"), json={}, headers=customers[2].headers
    )
    assert cancel.status_code == 200, cancel.text
    assert await slot_count(db, small.id, FRIDAY_1000) == 0
    third = await book(3)
    assert third.status_code == 201, third.text
    assert await slot_count(db, small.id, FRIDAY_1000) == 1


# --- BK-23, BK-24: operations ---------------------------------------------------------------------


async def test_bk23_notify_ready_is_repeatable_and_completion_by_customer_or_staff(
    desk: Desk, world: World, db: Database, clock: SimulatedClock, published: list[Event]
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.READY_FOR_PICKUP)
    published.clear()
    for minutes in (5, 30):
        clock.advance(timedelta(minutes=minutes - (5 if minutes == 30 else 0)))
        detail = await desk.act(world.advisor, journey.id, "notify-ready")
    assert detail["ready_notified_at"] == "2026-10-14T04:30:00Z"
    assert [event.action for event in published] == [BookingAction.NOTIFY_READY] * 2  # type: ignore[attr-defined]
    completed = await desk.my_act(journey.customer, journey.id, "complete")
    assert completed["status"] == "COMPLETED"
    assert completed["completed_at"] == "2026-10-14T04:30:00Z"
    assert completed["allowed_actions"] == []
    twice = await desk.act_raw(world.advisor.id, journey.id, "complete")
    problem(twice, 409, "INVALID_TRANSITION")
    by_staff = await drive_booking_to(desk, BookingStatus.READY_FOR_PICKUP)
    owner_done = await desk.act(world.owner, by_staff.id, "complete")
    assert owner_done["status"] == "COMPLETED"


async def test_bk24_start_repair_overwrites_the_time_each_round(
    desk: Desk, world: World, db: Database, clock: SimulatedClock
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.IN_REPAIR)
    clock.advance(timedelta(hours=1))
    first = await desk.act(world.technician, journey.id, "start-repair")
    await desk.act(world.technician, journey.id, "send-to-qc")
    await desk.act(world.qc, journey.id, "pick-qc")
    await desk.act(
        world.qc,
        journey.id,
        "fail-qc",
        {"issue_title": "Oil leak at filter", "issue_description": "Seal leaks at idle."},
    )
    clock.advance(timedelta(hours=1))
    second = await desk.act(world.technician, journey.id, "start-repair")
    assert first["repair_started_at"] == "2026-10-14T05:00:00Z"
    assert second["repair_started_at"] == "2026-10-14T06:00:00Z"
    events = [e for e in await events_of(db, journey.id) if e.action == BookingAction.START_REPAIR]
    assert [e.created_at for e in events] == [
        datetime(2026, 10, 14, 5, tzinfo=UTC),
        datetime(2026, 10, 14, 6, tzinfo=UTC),
    ]


# --- BK-25: reassignments (P1) --------------------------------------------------------------------


async def test_bk25_reassign_technician_keeps_the_draft_and_moves_visibility(
    desk: Desk, world: World, db: Database, published: list[Event]
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.INSPECTING)
    lines = [
        {"line_type": "LABOUR", "description": "Diagnosis", "quantity": "1", "unit_price": "1500"}
    ]
    draft = await desk.edit(world.technician, journey.id, lines)
    same = await desk.act_raw(
        world.advisor.id,
        journey.id,
        "reassign-technician",
        {"technician_user_id": str(world.technician.id)},
    )
    assert field_codes(problem(same, 422, "VALIDATION_ERROR")) == [
        ("technician_user_id", "unchanged")
    ]
    wrong = await desk.act_raw(
        world.advisor.id,
        journey.id,
        "reassign-technician",
        {"technician_user_id": str(world.qc.id)},
    )
    problem(wrong, 422, "MEMBER_NOT_ELIGIBLE")
    published.clear()
    moved = await desk.act(
        world.advisor,
        journey.id,
        "reassign-technician",
        {"technician_user_id": str(world.technician2.id)},
    )
    assert moved["status"] == "INSPECTING"
    assert moved["technician"]["user_id"] == str(world.technician2.id)
    assert moved["last_event"]["metadata"] == {
        "technician_user_id": str(world.technician2.id),
        "previous_technician_user_id": str(world.technician.id),
    }
    (event,) = published
    assert isinstance(event, BookingActionApplied)
    assert event.technician_user_id == world.technician2.id
    await desk.get(world.technician.id, desk.booking_path(journey.id), expect=404)
    estimates = await desk.get(world.technician2.id, desk.booking_path(journey.id, "/estimates"))
    assert [(e["id"], e["status"]) for e in estimates["items"]] == [(draft["id"], "DRAFT")]
    edited = await desk.edit(world.technician2, journey.id, lines)  # the new technician edits it
    assert edited["id"] == draft["id"]


async def test_bk25_reassign_parts_person_leaves_reservations_and_orders_alone(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.PARTS_ORDERED)
    before = await desk.get(world.parts.id, desk.booking_path(journey.id, "/parts"))
    moved = await desk.act(
        world.owner,
        journey.id,
        "reassign-parts-person",
        {"parts_person_user_id": str(world.parts2.id)},
    )
    assert moved["parts_person"]["user_id"] == str(world.parts2.id)
    assert moved["allowed_actions"] == ["cancel", "reassign-parts-person"]
    after = await desk.get(world.parts2.id, desk.booking_path(journey.id, "/parts"))
    assert after == before
    await desk.get(world.parts.id, desk.booking_path(journey.id), expect=404)
    ready = await desk.act(world.parts2, journey.id, "mark-parts-ready", expect=409)
    assert ready["code"] == "INSUFFICIENT_STOCK"  # the coil is still on order


# --- API-10 ---------------------------------------------------------------------------------------


async def test_api10_unknown_slugs_are_404_and_terminal_bookings_are_409(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.COMPLETED)
    for path, headers in (
        (desk.booking_path(journey.id, "/actions/frobnicate"), bearer(world.advisor.id)),
        (desk.booking_path(journey.id, "/actions/approve-estimate"), bearer(world.advisor.id)),
        (desk.booking_path(journey.id, "/actions/edit-estimate"), bearer(world.advisor.id)),
        (desk.booking_path(journey.id, "/actions/receive-parts"), bearer(world.parts.id)),
        (desk.my_path(journey.id, "/actions/confirm"), journey.customer.headers),
        (desk.my_path(journey.id, "/actions/frobnicate"), journey.customer.headers),
    ):
        problem(await desk.api.post(path, json={}, headers=headers), 404, "NOT_FOUND")
    cancelled = await drive_booking_to(desk, BookingStatus.CANCELLED)
    for target in (journey, cancelled):
        for slug, body in (
            ("confirm", {}),
            ("decline", {"reason": "x"}),
            ("cancel", {"reason": "x"}),
            ("notify-ready", {}),
            ("complete", {}),
        ):
            response = await desk.act_raw(world.advisor.id, target.id, slug, body)
            problem(response, 409, "INVALID_TRANSITION")
        response = await desk.api.post(
            desk.my_path(target.id, "/actions/cancel"), json={}, headers=target.customer.headers
        )
        problem(response, 409, "INVALID_TRANSITION")


async def test_cancel_from_in_repair_on_is_409(desk: Desk, world: World) -> None:
    journey = await drive_booking_to(desk, BookingStatus.IN_REPAIR)
    response = await desk.act_raw(world.advisor.id, journey.id, "cancel", {"reason": "No"})
    problem(response, 409, "INVALID_TRANSITION")
    mine = await desk.api.post(
        desk.my_path(journey.id, "/actions/cancel"), json={}, headers=journey.customer.headers
    )
    problem(mine, 409, "INVALID_TRANSITION")


# --- The BookingActionApplied contract (`modules/bookings.md` §8) ---------------------------------


async def test_every_published_event_matches_its_event_row_and_the_booking_after_it(
    desk: Desk, world: World, db: Database, published: list[Event]
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.COMPLETED)
    rows = await events_of(db, journey.id)
    applied = [event for event in published if isinstance(event, BookingActionApplied)]
    assert len(applied) == len(rows) == 15
    for version, (event, row) in enumerate(zip(applied, rows, strict=True), start=1):
        assert event.booking_id == row.booking_id
        assert event.shop_id == world.shop_id
        assert event.reference == journey.reference
        assert (event.action, event.from_status, event.to_status) == (
            row.action,
            row.from_status,
            row.to_status,
        )
        assert (event.actor_user_id, event.actor_role) == (row.actor_user_id, row.actor_role)
        assert event.note == row.note
        assert dict(event.metadata) == row.metadata_
        assert event.occurred_at == row.created_at
        assert event.version == version
        assert event.customer_user_id == journey.customer.user_id
    by_action = {event.action: event for event in applied}
    assert by_action[BookingAction.CONFIRM].technician_user_id is None
    assert by_action[BookingAction.ASSIGN_TECHNICIAN].technician_user_id == world.technician.id
    assert by_action[BookingAction.ASSIGN_PARTS_PERSON].parts_person_user_id == world.parts.id
    assert by_action[BookingAction.PICK_QC].qc_inspector_user_id == world.qc.id
    assert by_action[BookingAction.SEND_TO_QC].qc_inspector_user_id is None
    assert by_action[BookingAction.PASS_QC].qc_inspector_user_id == world.qc.id  # kept (D47)


async def test_event_metadata_shapes_follow_spec_08(desk: Desk, world: World, db: Database) -> None:
    journey = await drive_booking_to(desk, BookingStatus.COMPLETED)
    metadata = {e.action: e.metadata_ for e in await events_of(db, journey.id)}
    parts = world.catalogue
    estimate = metadata[BookingAction.SUBMIT_ESTIMATE]
    assert estimate == {
        "estimate_id": journey.estimate_ids[0],
        "version": 1,
        "grand_total": "16600.00",
    }
    assert metadata[BookingAction.START_INSPECTION] == {
        "estimate_id": journey.estimate_ids[0],
        "version": 1,
    }
    assert metadata[BookingAction.SEND_ESTIMATE] == estimate
    assert metadata[BookingAction.APPROVE_ESTIMATE] == estimate
    assert metadata[BookingAction.CONFIRM] == metadata[BookingAction.COMPLETE] == {}
    assert metadata[BookingAction.ASSIGN_TECHNICIAN] == {
        "technician_user_id": str(world.technician.id)
    }
    required = sorted(({"part_id": pid, "qty": 1} for pid in parts.ids), key=lambda i: i["part_id"])
    assert metadata[BookingAction.ASSIGN_PARTS_PERSON] == {
        "parts_person_user_id": str(world.parts.id),
        "required": required,
    }
    order = metadata[BookingAction.ORDER_PARTS]
    assert order["purchase_order_id"] == journey.purchase_order_id
    assert order["po_number"].startswith("PO-")
    in_stock = sorted([parts.oil_filter["id"], parts.engine_oil["id"]])
    assert order["reserved"] == [{"part_id": pid, "qty": 1} for pid in in_stock]
    assert metadata[BookingAction.RECEIVE_PARTS] == {"purchase_order_id": journey.purchase_order_id}
    assert metadata[BookingAction.ALLOCATE_PARTS] == {"consumed": required}
    assert metadata[BookingAction.SEND_TO_QC] == {"resolved_qc_issue_ids": []}
    pick = metadata[BookingAction.PICK_QC]
    assert metadata[BookingAction.PASS_QC] == pick
    assert set(pick) == {"qc_inspection_id"}


# --- D63: one instant per action ------------------------------------------------------------------

STAMPED_ROWS = """
SELECT 'booking' AS what, updated_at AS at FROM bookings WHERE id = :b
UNION ALL SELECT 'event', created_at FROM booking_events
    WHERE booking_id = :b
      AND created_at = (SELECT max(created_at) FROM booking_events WHERE booking_id = :b)
UNION ALL SELECT 'movement', created_at FROM stock_movements
    WHERE booking_id = :b AND created_at >= :since
UNION ALL SELECT 'booking_part', updated_at FROM booking_parts
    WHERE booking_id = :b AND updated_at >= :since
UNION ALL SELECT 'part', p.updated_at FROM parts p WHERE p.updated_at >= :since
UNION ALL SELECT 'estimate', updated_at FROM estimates
    WHERE booking_id = :b AND updated_at >= :since
UNION ALL SELECT 'qc_inspection', updated_at FROM qc_inspections
    WHERE booking_id = :b AND updated_at >= :since
UNION ALL SELECT 'qc_issue', updated_at FROM qc_issues
    WHERE booking_id = :b AND updated_at >= :since
UNION ALL SELECT 'purchase_order', updated_at FROM purchase_orders
    WHERE booking_id = :b AND updated_at >= :since
UNION ALL SELECT 'slot_counter', updated_at FROM slot_counters WHERE updated_at >= :since
"""


async def stamps(db: Database, booking_id: str, since: datetime) -> dict[str, set[datetime]]:
    found: dict[str, set[datetime]] = {}
    async with db.sessionmaker() as session:
        rows = await session.execute(
            text(STAMPED_ROWS), {"b": uuid.UUID(booking_id), "since": since}
        )
        for row in rows:
            found.setdefault(row.what, set()).add(row.at)
    return found


async def test_d63_every_row_an_action_writes_carries_its_single_instant(
    desk: Desk, world: World, db: Database
) -> None:
    """Under a stepping clock every read of "now" is a new second, so a second read inside one
    action (or an ORM `onupdate` falling back to the clock) would show as a different instant."""
    journey = await drive_booking_to(desk, BookingStatus.ESTIMATE_REVIEW)
    stepping = SimulatedClock(datetime(2026, 10, 14, 6, 0, tzinfo=UTC), step=timedelta(seconds=1))
    steps: list[tuple[Any, str, dict[str, Any]]] = [
        (world.advisor, "send-estimate", {}),
        (None, "approve-estimate", {}),
        (world.advisor, "assign-parts-person", {"parts_person_user_id": str(world.parts.id)}),
        (world.parts, "order-parts", {}),
        ("receive", "", {}),
        (world.parts, "allocate-parts", {}),
        (world.technician, "start-repair", {}),
        (world.technician, "send-to-qc", {}),
        (world.qc, "pick-qc", {}),
        (world.qc, "fail-qc", {"issue_title": "Leak", "issue_description": "Seal leaks."}),
        (world.technician, "send-to-qc", {"repair_notes": "Seal replaced"}),
        (world.qc2, "pick-qc", {}),
        (world.qc2, "pass-qc", {"checklist": full_checklist()}),
        (world.advisor, "notify-ready", {}),
        (world.advisor, "complete", {}),
    ]
    with use_clock(stepping):
        for actor, slug, body in steps:
            since = stepping.now()  # one tick before the request
            if actor is None:
                detail = await desk.my_detail(journey.customer, journey.id)
                estimate_id = detail["estimate"]["id"]
                await desk.my_act(journey.customer, journey.id, slug, {"estimate_id": estimate_id})
            elif actor == "receive":
                order_id = (await desk.detail(world.parts, journey.id))["last_event"]["metadata"][
                    "purchase_order_id"
                ]
                await desk.receive(order_id)
            else:
                await desk.act(actor, journey.id, slug, body)
            found = await stamps(db, journey.id, since)
            instants = set().union(*found.values())
            assert len(instants) == 1, (slug or "receive", found)
            (instant,) = instants
            assert found["booking"] == found["event"] == {instant}


async def test_d63_cancellation_stamps_release_slot_and_estimates_with_one_instant(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.PARTS_ORDERED)
    stepping = SimulatedClock(datetime(2026, 10, 14, 7, 0, tzinfo=UTC), step=timedelta(seconds=1))
    with use_clock(stepping):
        since = stepping.now()
        await desk.act(world.advisor, journey.id, "cancel", {"reason": "Customer sold the car"})
        found = await stamps(db, journey.id, since)
    instants = set().union(*found.values())
    assert len(instants) == 1, found
    assert {"booking", "event", "movement", "booking_part", "part", "slot_counter"} <= set(found)


# --- Programming errors of the entry points -------------------------------------------------------


async def test_the_service_refuses_actions_outside_their_family_and_wrong_payloads(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.AWAITING_CUSTOMER)
    ctx = context(world, world.advisor)
    booking_id = uuid.UUID(journey.id)
    cases: list[tuple[BookingAction, Any, type[Exception]]] = [
        (
            BookingAction.APPROVE_ESTIMATE,
            ApproveEstimateRequest(estimate_id=uuid.uuid4()),
            ValueError,
        ),
        (BookingAction.EDIT_ESTIMATE, StartInspectionRequest(), ValueError),
        (BookingAction.CREATE, StartInspectionRequest(), ValueError),
        (BookingAction.RECEIVE_PARTS, StartInspectionRequest(), ValueError),
        (BookingAction.CONFIRM, StartInspectionRequest(), TypeError),
        (BookingAction.CANCEL, CustomerCancelRequest(), TypeError),
    ]
    for action, payload, error in cases:
        with pytest.raises(error):
            async with unit_of_work(db) as uow:
                await bookings_service.apply_staff_action(
                    uow, ctx, booking_id=booking_id, action=action, payload=payload
                )
    customer = CurrentUser(
        id=journey.customer.user_id, email=journey.customer.email, full_name="Ahmed"
    )
    for action, payload, error in [
        (BookingAction.CONFIRM, ConfirmRequest(), ValueError),
        (BookingAction.CANCEL, CancelRequest(reason="x"), TypeError),
    ]:
        with pytest.raises(error):
            async with unit_of_work(db) as uow:
                await bookings_service.apply_customer_action(
                    uow, customer, booking_id=booking_id, action=action, payload=payload
                )
    assert (await booking_row(db, journey.id)).version == journey.booking["version"]


async def test_a_member_of_another_role_with_a_matching_slug_is_403_forbidden(
    desk: Desk, world: World
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.PENDING)
    stranger = await make_user(desk.world.db)  # no membership: 404 before anything else
    problem(await desk.act_raw(stranger.id, journey.id, "confirm"), 404, "NOT_FOUND")
    owner_pick = await drive_booking_to(desk, BookingStatus.QC_PENDING)
    body = problem(await desk.act_raw(world.owner.id, owner_pick.id, "pick-qc"), 403, "FORBIDDEN")
    assert body["detail"] == "The OWNER role may not perform 'pick-qc'."

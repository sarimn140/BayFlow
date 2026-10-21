"""Estimates through the booking flows (spec 08 T05-T11, O1; D39, D40; `modules/bookings.md`
§7.6, §7.6.1).

EST-01, EST-02, EST-03, EST-10, EST-11, EST-13, EST-14 (= SM-14), EST-15, EST-17, EST-18 (the
editor's live stock), EST-19, BK-38, SEC-35, SM-08 ★ and SM-09, plus the customer's estimate
history (`GET /api/v1/me/bookings/{id}/estimates`, P1).
"""

import uuid
from datetime import timedelta
from typing import Any

import pytest

from app.core.database import Database
from app.modules.bookings.events import BookingActionApplied
from app.shared.clock import SimulatedClock
from app.shared.enums import ActorRole, BookingAction, BookingStatus
from app.shared.event_bus import Event
from tests.modules.bookings.support import (
    Desk,
    Journey,
    World,
    drive_booking_to,
    estimate_statuses,
    events_of,
    field_codes,
    labour_lines,
    new_customer,
    problem,
    worked_lines,
)
from tests.modules.identity.builders import bearer

pytestmark = pytest.mark.db

S = BookingStatus


async def versions(desk: Desk, journey: Journey) -> list[dict[str, Any]]:
    """Every version as the SA sees it (`GET …/estimates`), oldest first."""
    path = desk.booking_path(journey.id, "/estimates")
    items: list[dict[str, Any]] = (await desk.get(desk.world.advisor.id, path))["items"]
    return items


async def customer_versions(desk: Desk, journey: Journey) -> list[tuple[int, str]]:
    path = desk.my_path(journey.id, "/estimates")
    items = (await desk.get(journey.customer.user_id, path))["items"]
    return [(item["version"], item["status"]) for item in items]


def line_shapes(estimate: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (
            line["line_type"],
            None if line["part"] is None else line["part"]["id"],
            line["description"],
            line["quantity"],
            line["unit_price"],
        )
        for line in estimate["lines"]
    ]


async def current_sent_id(desk: Desk, journey: Journey) -> str:
    estimate_id: str = (await desk.my_detail(journey.customer, journey.id))["estimate"]["id"]
    return estimate_id


# --- EST-01, EST-02, EST-18 -----------------------------------------------------------------------


async def test_est01_start_inspection_opens_an_empty_draft_v1_for_the_technician(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.ASSIGNED)
    assert await estimate_statuses(db, journey.id) == []
    started = await desk.act(world.technician, journey.id, "start-inspection")
    (draft,) = await versions(desk, journey)
    assert (draft["version"], draft["status"], draft["lines"], draft["grand_total"]) == (
        1,
        "DRAFT",
        [],
        "0.00",
    )
    assert draft["created_by"] == {"user_id": str(world.technician.id), "full_name": "Imran"}
    assert started["estimate_summary"] == {
        "estimate_id": draft["id"],
        "version": 1,
        "status": "DRAFT",
        "grand_total": "0.00",
        "line_count": 0,
    }
    assert started["last_event"]["metadata"] == {"estimate_id": draft["id"], "version": 1}
    again = await desk.act_raw(world.technician.id, journey.id, "start-inspection")
    problem(again, 409, "INVALID_TRANSITION")
    assert await estimate_statuses(db, journey.id) == [(1, "DRAFT")]


async def test_est02_est18_the_technicians_saves_replace_the_draft_in_place(
    desk: Desk, world: World, db: Database, published: list[Event]
) -> None:
    journey = await drive_booking_to(desk, S.INSPECTING)
    before = await desk.detail(world.advisor, journey.id)
    seen = len(published)
    first = await desk.edit(
        world.technician, journey.id, worked_lines(world), inspection_notes="  Coil cracked  "
    )
    assert (first["version"], first["status"], first["created_new_version"]) == (1, "DRAFT", False)
    assert first["booking_version"] == before["version"]
    assert (first["parts_total"], first["labour_total"], first["grand_total"]) == (
        "12600.00",
        "4000.00",
        "16600.00",
    )
    stock = {
        line["part"]["sku"]: (line["part"]["available"], line["part"]["stock_state"])
        for line in first["lines"]
        if line["part"] is not None
    }
    assert stock == {  # EST-18: live availability, the coil flagged as out of stock
        "IGN-COIL-01": (0, "OUT"),
        "OIL-FILTER-01": (100, "OK"),
        "ENGINE-OIL-4L": (100, "OK"),
    }
    second = await desk.edit(world.technician, journey.id, labour_lines("3000"))
    assert (second["id"], second["version"], second["created_new_version"]) == (
        first["id"],
        1,
        False,
    )
    assert [line["description"] for line in second["lines"]] == ["Four-wheel alignment"]
    assert second["grand_total"] == "3000.00"
    after = await desk.detail(world.advisor, journey.id)
    assert after["version"] == before["version"]  # no event, no bump (D30)
    assert after["inspection_notes"] == "Coil cracked"  # kept: the second save sent none
    assert len(await events_of(db, journey.id)) == before["version"]
    assert len(published) == seen
    assert await estimate_statuses(db, journey.id) == [(1, "DRAFT")]
    blank = await desk.edit(world.technician, journey.id, labour_lines(), inspection_notes="   ")
    assert blank["created_new_version"] is False
    assert (await desk.detail(world.advisor, journey.id))["inspection_notes"] == "Coil cracked"
    await desk.edit(world.technician, journey.id, labour_lines(), inspection_notes="Coil fine")
    assert (await desk.detail(world.technician, journey.id))["inspection_notes"] == "Coil fine"


# --- EST-03, BK-38 --------------------------------------------------------------------------------


async def test_est03_the_first_desk_edit_supersedes_the_submitted_version(
    desk: Desk, world: World, db: Database, published: list[Event]
) -> None:
    journey = await drive_booking_to(desk, S.ESTIMATE_REVIEW)  # v1 SUBMITTED, 16,600
    before = await desk.detail(world.advisor, journey.id)
    seen = len(published)
    v2 = await desk.edit(world.advisor, journey.id, worked_lines(world, labour="3500"))
    assert (v2["version"], v2["status"], v2["created_new_version"]) == (2, "DRAFT", True)
    assert v2["booking_version"] == before["version"] + 1
    assert v2["created_by"] == {"user_id": str(world.advisor.id), "full_name": "Bilal"}
    assert v2["grand_total"] == "16100.00"
    assert await estimate_statuses(db, journey.id) == [(1, "SUPERSEDED"), (2, "DRAFT")]
    event = (await events_of(db, journey.id))[-1]
    assert (event.action, event.from_status, event.to_status) == (
        BookingAction.EDIT_ESTIMATE,
        S.ESTIMATE_REVIEW,
        S.ESTIMATE_REVIEW,
    )
    assert (event.actor_user_id, event.actor_role) == (world.advisor.id, ActorRole.SERVICE_ADVISOR)
    assert event.metadata_ == {"estimate_id": v2["id"], "version": 2, "grand_total": "16100.00"}
    (applied,) = published[seen:]
    assert isinstance(applied, BookingActionApplied)
    assert (applied.action, applied.version) == (BookingAction.EDIT_ESTIMATE, v2["booking_version"])
    again = await desk.edit(world.owner, journey.id, worked_lines(world, labour="3000"))
    assert (again["id"], again["version"], again["created_new_version"]) == (v2["id"], 2, False)
    assert again["booking_version"] == v2["booking_version"]
    assert again["grand_total"] == "15600.00"
    assert len(published) == seen + 1
    frozen = (await versions(desk, journey))[0]
    assert (frozen["status"], frozen["grand_total"]) == ("SUPERSEDED", "16600.00")
    detail = await desk.detail(world.advisor, journey.id)
    assert detail["estimate_summary"]["version"] == 2
    assert detail["estimate_summary"]["grand_total"] == "15600.00"


async def test_bk38_only_the_technician_writes_inspection_notes(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.ESTIMATE_REVIEW)
    before = await desk.detail(world.advisor, journey.id)
    for member in (world.advisor, world.owner):
        response = await desk.api.put(
            desk.booking_path(journey.id, "/estimate"),
            json={"lines": labour_lines(), "inspection_notes": "Desk note"},
            headers=bearer(member.id),
        )
        body = problem(response, 422, "VALIDATION_ERROR")
        assert field_codes(body) == [("inspection_notes", "not_allowed")]
    assert await estimate_statuses(db, journey.id) == [(1, "SUBMITTED")]  # nothing was saved
    after = await desk.detail(world.advisor, journey.id)
    assert (after["version"], after["inspection_notes"]) == (before["version"], None)
    blank = await desk.edit(world.advisor, journey.id, labour_lines(), inspection_notes="  ")
    assert blank["created_new_version"] is True  # blank notes = no notes
    technician_job = await drive_booking_to(desk, S.INSPECTING)
    saved = await desk.edit(
        world.technician, technician_job.id, labour_lines(), inspection_notes="Worn bushes"
    )
    assert saved["created_new_version"] is False
    detail = await desk.detail(world.advisor, technician_job.id)
    assert (detail["inspection_notes"], detail["version"]) == ("Worn bushes", 4)
    mine = await desk.my_detail(technician_job.customer, technician_job.id)
    assert "inspection_notes" not in mine


# --- EST-11, SEC-35: locked edits -----------------------------------------------------------------


async def put(desk: Desk, user_id: uuid.UUID, journey: Journey, **body: Any) -> Any:
    return await desk.api.put(
        desk.booking_path(journey.id, "/estimate"),
        json={"lines": labour_lines("9999"), **body},
        headers=bearer(user_id),
    )


async def test_est11_edits_outside_the_callers_status_are_409_estimate_locked(
    desk: Desk, world: World, db: Database
) -> None:
    owner, advisor, imran = world.owner.id, world.advisor.id, world.technician.id
    cases: list[tuple[BookingStatus, list[uuid.UUID]]] = [
        (S.INSPECTING, [owner, advisor]),
        (S.ESTIMATE_REVIEW, [imran]),
        (S.AWAITING_CUSTOMER, [owner, advisor, imran]),
        (S.ESTIMATE_APPROVED, [owner, advisor, imran]),
        (S.ESTIMATE_REJECTED, [owner, advisor, imran]),
        (S.PARTS_PENDING, [owner, advisor, imran]),
        (S.COMPLETED, [owner, advisor, imran]),
    ]
    for status, callers in cases:
        journey = await drive_booking_to(desk, status)
        before = (await versions(desk, journey), await desk.detail(world.advisor, journey.id))
        for user_id in callers:
            problem(await put(desk, user_id, journey), 409, "ESTIMATE_LOCKED")
            stale = await put(desk, user_id, journey, expected_version=1)
            problem(stale, 409, "ESTIMATE_LOCKED")  # the status is checked before the version
        assert (await versions(desk, journey), await desk.detail(world.advisor, journey.id)) == (
            before
        )
    pending = await drive_booking_to(desk, S.PARTS_PENDING)
    problem(await put(desk, world.parts.id, pending), 403, "FORBIDDEN")
    queued = await drive_booking_to(desk, S.QC_PENDING)
    problem(await put(desk, world.qc.id, queued), 403, "FORBIDDEN")
    inspecting = await drive_booking_to(desk, S.INSPECTING)
    problem(await put(desk, world.technician2.id, inspecting), 404, "NOT_FOUND")
    problem(await put(desk, world.parts.id, inspecting), 404, "NOT_FOUND")  # not visible yet
    stale = await put(desk, imran, inspecting, expected_version=1)
    problem(stale, 409, "CONCURRENT_UPDATE")
    fresh = await put(desk, imran, inspecting, expected_version=4)
    assert fresh.status_code == 200, fresh.text


async def test_sec35_totals_are_computed_by_the_server_only(desk: Desk, world: World) -> None:
    journey = await drive_booking_to(desk, S.INSPECTING)
    coil = world.catalogue.coil["id"]
    lines = [
        {"line_type": "PART", "part_id": coil, "quantity": "2", "unit_price": "7000"},
        {"line_type": "PART", "part_id": world.catalogue.oil_filter["id"], "quantity": "1"},
        {"line_type": "LABOUR", "description": "Labour", "quantity": "1.5", "unit_price": "2000"},
    ]
    edit = await desk.edit(world.technician, journey.id, lines)
    assert [line["line_total"] for line in edit["lines"]] == ["14000.00", "900.00", "3000.00"]
    assert [line["unit_price"] for line in edit["lines"]] == ["7000.00", "900.00", "2000.00"]
    assert (edit["parts_total"], edit["labour_total"], edit["grand_total"]) == (
        "14900.00",
        "3000.00",
        "17900.00",
    )
    assert edit["lines"][0]["description"] == "Ignition coil"  # the catalogue name
    smuggled = [
        ({"lines": [{**lines[2], "line_total": "1"}]}, ("lines.0.line_total", "extra_forbidden")),
        ({"lines": lines, "grand_total": "1"}, ("grand_total", "extra_forbidden")),
        ({"lines": lines, "parts_total": "1"}, ("parts_total", "extra_forbidden")),
    ]
    for body, expected in smuggled:
        response = await desk.api.put(
            desk.booking_path(journey.id, "/estimate"),
            json=body,
            headers=bearer(world.technician.id),
        )
        assert expected in field_codes(problem(response, 422, "VALIDATION_ERROR"))
    empty = await desk.api.put(
        desk.booking_path(journey.id, "/estimate"),
        json={"lines": []},
        headers=bearer(world.technician.id),
    )
    assert ("lines", "too_short") in field_codes(problem(empty, 422, "VALIDATION_ERROR"))
    assert (await versions(desk, journey))[0]["grand_total"] == "17900.00"


# --- EST-10 ---------------------------------------------------------------------------------------


async def test_est10_an_empty_draft_cannot_be_submitted(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.INSPECTING)
    before = await desk.detail(world.advisor, journey.id)
    body = problem(
        await desk.act_raw(world.technician.id, journey.id, "submit-estimate"),
        422,
        "ESTIMATE_EMPTY",
    )
    assert field_codes(body) == [("lines", "too_short")]
    after = await desk.detail(world.advisor, journey.id)
    assert (after["status"], after["version"]) == ("INSPECTING", before["version"])
    assert await estimate_statuses(db, journey.id) == [(1, "DRAFT")]
    assert len(await events_of(db, journey.id)) == before["version"]


# --- EST-13, EST-14 / SM-14 -----------------------------------------------------------------------


async def test_est13_approval_records_who_approved_and_when(
    desk: Desk, world: World, clock: SimulatedClock
) -> None:
    journey = await drive_booking_to(desk, S.AWAITING_CUSTOMER)
    sent_at = (await desk.my_detail(journey.customer, journey.id))["estimate"]["sent_at"]
    clock.advance(timedelta(hours=3))
    approved = await desk.my_act(
        journey.customer,
        journey.id,
        "approve-estimate",
        {"estimate_id": await current_sent_id(desk, journey)},
    )
    estimate = approved["estimate"]
    assert estimate["status"] == "APPROVED"
    assert estimate["decided_at"] == approved["updated_at"] == "2026-10-14T07:00:00Z"
    assert estimate["sent_at"] == sent_at != estimate["decided_at"]
    staff = (await versions(desk, journey))[0]
    assert staff["decided_by"] == {
        "user_id": str(journey.customer.user_id),
        "full_name": journey.customer.full_name,
    }
    assert staff["decided_at"] == estimate["decided_at"]
    assert staff["sent_by"] == {"user_id": str(world.advisor.id), "full_name": "Bilal"}
    assert await customer_versions(desk, journey) == [(1, "APPROVED")]


async def test_est14_sm14_only_the_current_sent_version_can_be_decided(
    desk: Desk, world: World, db: Database
) -> None:
    customer = await new_customer(db)
    journey = await drive_booking_to(desk, S.ESTIMATE_REVIEW, customer=customer)
    v1 = journey.booking["estimate_summary"]["estimate_id"]
    await desk.edit(world.advisor, journey.id, worked_lines(world, labour="3500"))  # v1 SUPERSEDED
    await desk.act(world.advisor, journey.id, "send-estimate")
    v2 = await current_sent_id(desk, journey)
    other = await drive_booking_to(desk, S.AWAITING_CUSTOMER, customer=customer)
    other_sent = await current_sent_id(desk, other)
    before = await desk.detail(world.advisor, journey.id)
    for slug in ("approve-estimate", "reject-estimate"):
        for estimate_id in (v1, other_sent, str(uuid.uuid4())):
            response = await desk.api.post(
                desk.my_path(journey.id, f"/actions/{slug}"),
                json={"estimate_id": estimate_id},
                headers=customer.headers,
            )
            problem(response, 409, "STALE_ESTIMATE")
    after = await desk.detail(world.advisor, journey.id)
    assert (after["status"], after["version"]) == ("AWAITING_CUSTOMER", before["version"])
    assert await estimate_statuses(db, journey.id) == [(1, "SUPERSEDED"), (2, "SENT")]
    assert await estimate_statuses(db, other.id) == [(1, "SENT")]
    await desk.my_act(customer, journey.id, "approve-estimate", {"estimate_id": v2})
    repeat = await desk.api.post(
        desk.my_path(journey.id, "/actions/approve-estimate"),
        json={"estimate_id": v2},
        headers=customer.headers,
    )
    problem(repeat, 409, "INVALID_TRANSITION")  # the status is checked first
    missing = await desk.api.post(
        desk.my_path(other.id, "/actions/approve-estimate"), json={}, headers=customer.headers
    )
    assert ("estimate_id", "missing") in field_codes(problem(missing, 422, "VALIDATION_ERROR"))


async def test_est14_a_rejected_version_can_never_be_approved_later(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.ESTIMATE_REJECTED)
    v1 = journey.estimate_ids[0]
    await desk.act(world.advisor, journey.id, "revise-estimate")
    await desk.act(world.advisor, journey.id, "send-estimate")
    response = await desk.api.post(
        desk.my_path(journey.id, "/actions/approve-estimate"),
        json={"estimate_id": v1},
        headers=journey.customer.headers,
    )
    problem(response, 409, "STALE_ESTIMATE")
    assert await estimate_statuses(db, journey.id) == [(1, "REJECTED"), (2, "SENT")]


# --- EST-15, SM-08 ★, SM-09, EST-19 ---------------------------------------------------------------


async def test_sm08_est15_reject_revise_send_approve(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.AWAITING_CUSTOMER)
    v1 = await current_sent_id(desk, journey)
    await desk.my_act(
        journey.customer,
        journey.id,
        "reject-estimate",
        {"estimate_id": v1, "reason": "  Too expensive, skip the oil  "},
    )
    rejected = (await versions(desk, journey))[0]
    assert (rejected["status"], rejected["customer_note"]) == (
        "REJECTED",
        "Too expensive, skip the oil",
    )
    revised = await desk.act(world.advisor, journey.id, "revise-estimate")
    assert revised["status"] == "ESTIMATE_REVIEW"
    old, new = await versions(desk, journey)
    assert old == rejected  # the rejected version is untouched
    assert (new["version"], new["status"], new["created_by"]["full_name"]) == (2, "DRAFT", "Bilal")
    assert line_shapes(new) == line_shapes(old)  # a copy of the rejected lines
    assert revised["last_event"]["metadata"] == {"estimate_id": new["id"], "version": 2}
    lines = worked_lines(world, labour="3500")
    edit = await desk.edit(world.advisor, journey.id, lines)
    assert (edit["version"], edit["created_new_version"]) == (2, False)  # a DRAFT: in place
    await desk.act(world.advisor, journey.id, "send-estimate")
    assert await customer_versions(desk, journey) == [(1, "REJECTED"), (2, "SENT")]
    v2 = await current_sent_id(desk, journey)
    assert v2 == new["id"]
    await desk.my_act(journey.customer, journey.id, "approve-estimate", {"estimate_id": v2})
    assert await estimate_statuses(db, journey.id) == [(1, "REJECTED"), (2, "APPROVED")]
    assert await customer_versions(desk, journey) == [(1, "REJECTED"), (2, "APPROVED")]
    detail = await desk.detail(world.advisor, journey.id)
    assert detail["status"] == "ESTIMATE_APPROVED"
    assert detail["estimate_summary"]["grand_total"] == "16100.00"
    events = await events_of(db, journey.id)
    tail = [(event.action, event.metadata_) for event in events[-4:]]
    v1_total = {"estimate_id": v1, "version": 1, "grand_total": "16600.00"}
    v2_total = {"estimate_id": v2, "version": 2, "grand_total": "16100.00"}
    assert tail == [  # EST-19
        (BookingAction.REJECT_ESTIMATE, v1_total),
        (BookingAction.REVISE_ESTIMATE, {"estimate_id": v2, "version": 2}),
        (BookingAction.SEND_ESTIMATE, v2_total),
        (BookingAction.APPROVE_ESTIMATE, v2_total),
    ]
    assert events[-4].note == "Too expensive, skip the oil"


async def test_sm09_est15_reject_return_to_technician_submit_send_approve(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.ESTIMATE_REJECTED)
    returned = await desk.act(
        world.owner, journey.id, "return-to-technician", {"note": "Re-check the coil"}
    )
    assert returned["status"] == "INSPECTING"
    old, new = await versions(desk, journey)
    assert (new["version"], new["status"], new["created_by"]["full_name"]) == (
        2,
        "DRAFT",
        "Fatima Raza",
    )
    assert line_shapes(new) == line_shapes(old)
    assert returned["last_event"]["note"] == "Re-check the coil"
    assert returned["last_event"]["metadata"] == {"estimate_id": new["id"], "version": 2}
    edit = await desk.edit(world.technician, journey.id, labour_lines("2500"))
    assert (edit["id"], edit["created_new_version"]) == (new["id"], False)
    await desk.act(world.technician, journey.id, "submit-estimate")
    await desk.act(world.advisor, journey.id, "send-estimate")
    v2 = await current_sent_id(desk, journey)
    await desk.my_act(journey.customer, journey.id, "approve-estimate", {"estimate_id": v2})
    assert await estimate_statuses(db, journey.id) == [(1, "REJECTED"), (2, "APPROVED")]
    actions = [event.action for event in await events_of(db, journey.id)]
    assert actions[-5:] == [  # the technician's draft saves write no event
        BookingAction.REJECT_ESTIMATE,
        BookingAction.RETURN_TO_TECHNICIAN,
        BookingAction.SUBMIT_ESTIMATE,
        BookingAction.SEND_ESTIMATE,
        BookingAction.APPROVE_ESTIMATE,
    ]
    timeline = (await desk.get(journey.customer.user_id, desk.my_path(journey.id, "/events")))[
        "items"
    ]
    returned_event = [event for event in timeline if event["action"] == "RETURN_TO_TECHNICIAN"]
    assert [event["note"] for event in returned_event] == [None]  # a staff note


# --- EST-17: cancel supersedes the open versions only ---------------------------------------------


async def test_est17_cancel_supersedes_open_versions_and_keeps_decided_ones(
    desk: Desk, world: World, db: Database
) -> None:
    cases = [
        (S.INSPECTING, [(1, "SUPERSEDED")]),
        (S.ESTIMATE_REVIEW, [(1, "SUPERSEDED")]),
        (S.AWAITING_CUSTOMER, [(1, "SUPERSEDED")]),
        (S.ESTIMATE_APPROVED, [(1, "APPROVED")]),
        (S.ESTIMATE_REJECTED, [(1, "REJECTED")]),
    ]
    for status, expected in cases:
        journey = await drive_booking_to(desk, status)
        cancelled = await desk.act(world.advisor, journey.id, "cancel", {"reason": "Car sold"})
        assert cancelled["status"] == "CANCELLED"
        assert await estimate_statuses(db, journey.id) == expected, status
        assert cancelled["last_event"]["metadata"] == {"released": []}
    revised = await drive_booking_to(desk, S.ESTIMATE_REJECTED)
    await desk.act(world.advisor, revised.id, "revise-estimate")
    await desk.my_act(revised.customer, revised.id, "cancel")
    assert await estimate_statuses(db, revised.id) == [(1, "REJECTED"), (2, "SUPERSEDED")]
    mine = await desk.my_detail(revised.customer, revised.id)
    assert (mine["estimate"]["version"], mine["estimate"]["status"]) == (1, "REJECTED")
    assert mine["estimate_revision_in_progress"] is False
    sent = await drive_booking_to(desk, S.AWAITING_CUSTOMER)
    await desk.my_act(sent.customer, sent.id, "cancel", {"reason": "Found a cheaper garage"})
    assert await estimate_statuses(db, sent.id) == [(1, "SUPERSEDED")]
    assert await customer_versions(desk, sent) == []
    assert (await desk.my_detail(sent.customer, sent.id))["estimate"] is None

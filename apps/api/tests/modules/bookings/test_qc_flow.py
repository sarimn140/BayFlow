"""QC through the booking flows (spec 08 T17-T20; D46, D47; `modules/bookings.md` §7.6).

QC-03, QC-04, QC-05, QC-09, QC-10, QC-11, QC-14 (through the booking reads), SM-10 ★ (the fail
loop twice, then a pass), BK-39's sequential half (`ALREADY_PICKED` names the picker, also for
the picker's own repeated click), D47 reached through a role change (a technician who became a QC
inspector never picks their own job), and the checklist guards on `pass-qc`.
"""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.core.database import Database
from app.modules.qc.models import QcInspection, QcIssue
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import MemberUpdate, StaffRole
from app.shared.clock import SimulatedClock
from app.shared.enums import BookingAction, BookingStatus, MembershipRole, QcResult
from tests.modules.bookings.support import (
    Desk,
    Journey,
    World,
    booking_row,
    drive_booking_to,
    events_of,
    field_codes,
    full_checklist,
    problem,
)
from tests.modules.identity.builders import bearer, unit_of_work
from tests.modules.shops.builders import Member

pytestmark = pytest.mark.db

S = BookingStatus
LEAK = {"issue_title": "Oil leak at filter", "issue_description": "The filter seal weeps oil."}
NOISE = {"issue_title": "Brake squeal", "issue_description": "Front left squeals at low speed."}


async def history(desk: Desk, journey: Journey, member: Member) -> list[dict[str, Any]]:
    path = desk.booking_path(journey.id, "/qc-inspections")
    items: list[dict[str, Any]] = (await desk.get(member.id, path))["items"]
    return items


async def round_and_issues(desk: Desk, journey: Journey) -> tuple[str, int, int]:
    detail = await desk.detail(desk.world.advisor, journey.id)
    listed = await desk.get(desk.world.advisor.id, desk.shop_path("/bookings"), q=journey.reference)
    (item,) = listed["items"]
    assert (item["qc_round"], item["open_qc_issues_count"]) == (
        detail["qc_round"],
        detail["open_qc_issues_count"],
    )
    return detail["status"], detail["qc_round"], detail["open_qc_issues_count"]


# --- QC-03, QC-09, QC-11: a failed round ----------------------------------------------------------


async def test_qc03_qc11_a_failed_round_returns_the_job_to_its_technician(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.QC_IN_PROGRESS)
    checklist = full_checklist(failed=["fluid_levels"])
    body = {**LEAK, "checklist": checklist, "notes": "Top up after the fix."}
    failed = await desk.act(world.qc, journey.id, "fail-qc", body)
    assert (failed["status"], failed["qc_inspector"]) == ("IN_REPAIR", None)
    assert failed["technician"] == {
        "user_id": str(world.technician.id),
        "full_name": "Imran",
        "is_active": True,
    }
    assert failed["allowed_actions"] == []  # Sara inspected it, so she still sees it (D21)
    advisor_view = await desk.detail(world.advisor, journey.id)
    assert advisor_view["allowed_actions"] == ["reassign-technician"]  # no cancel from IN_REPAIR
    (inspection,) = await history(desk, journey, world.advisor)
    assert (inspection["round"], inspection["result"], inspection["notes"]) == (
        1,
        "FAIL",
        "Top up after the fix.",
    )
    assert inspection["inspector"] == {"user_id": str(world.qc.id), "full_name": "Sara"}
    assert [item["key"] for item in inspection["checklist"]] == [i["key"] for i in checklist]
    assert [item["passed"] for item in inspection["checklist"]] == [i["passed"] for i in checklist]
    (issue,) = inspection["issues"]
    assert (issue["title"], issue["description"], issue["status"]) == (
        LEAK["issue_title"],
        LEAK["issue_description"],
        "OPEN",
    )
    event = (await events_of(db, journey.id))[-1]
    assert (event.action, event.note) == (BookingAction.FAIL_QC, "Oil leak at filter")
    assert event.metadata_ == {"qc_inspection_id": inspection["id"], "qc_issue_id": issue["id"]}
    # QC-09: the technician sees the issue sent back on the job.
    seen_by_imran = await history(desk, journey, world.technician)
    assert seen_by_imran[0]["issues"][0]["title"] == "Oil leak at filter"
    detail = await desk.detail(world.technician, journey.id)
    assert (detail["open_qc_issues_count"], detail["qc_round"]) == (1, 1)
    assert detail["allowed_actions"] == ["start-repair", "send-to-qc"]
    without_checklist = await drive_booking_to(desk, S.QC_IN_PROGRESS)
    await desk.act(world.qc, without_checklist.id, "fail-qc", NOISE)
    (bare,) = await history(desk, without_checklist, world.advisor)
    assert (bare["result"], bare["checklist"], bare["notes"]) == ("FAIL", None, None)


# --- QC-05, QC-10, QC-11, QC-14, SM-10 ★: the loop ------------------------------------------------


async def test_sm10_two_failed_rounds_then_a_pass(  # noqa: PLR0915 - one scenario, step by step
    desk: Desk, world: World, db: Database, clock: SimulatedClock
) -> None:
    """Each round happens later than the previous one (qc orders rounds by `picked_at`)."""
    journey = await drive_booking_to(desk, S.IN_REPAIR)
    assert await round_and_issues(desk, journey) == ("IN_REPAIR", 0, 0)
    await desk.act(world.technician, journey.id, "send-to-qc")
    assert await round_and_issues(desk, journey) == ("QC_PENDING", 1, 0)
    clock.advance(timedelta(minutes=10))
    await desk.act(world.qc, journey.id, "pick-qc")
    assert await round_and_issues(desk, journey) == ("QC_IN_PROGRESS", 1, 0)
    await desk.act(world.qc, journey.id, "fail-qc", LEAK)
    assert await round_and_issues(desk, journey) == ("IN_REPAIR", 1, 1)
    first_issue = (await history(desk, journey, world.advisor))[0]["issues"][0]["id"]
    resent = await desk.act(world.technician, journey.id, "send-to-qc", {"repair_notes": "Seal"})
    assert resent["last_event"]["metadata"] == {"resolved_qc_issue_ids": [first_issue]}
    assert await round_and_issues(desk, journey) == ("QC_PENDING", 2, 0)
    clock.advance(timedelta(minutes=10))
    await desk.act(world.qc2, journey.id, "pick-qc")  # QC-10: another inspector may re-test
    await desk.act(world.qc2, journey.id, "fail-qc", NOISE)
    assert await round_and_issues(desk, journey) == ("IN_REPAIR", 2, 1)
    await desk.act(world.technician, journey.id, "start-repair")
    await desk.act(world.technician, journey.id, "send-to-qc")
    assert await round_and_issues(desk, journey) == ("QC_PENDING", 3, 0)
    clock.advance(timedelta(minutes=10))
    await desk.act(world.qc, journey.id, "pick-qc")
    passed = await desk.act(
        world.qc, journey.id, "pass-qc", {"checklist": full_checklist(), "notes": "All good"}
    )
    assert passed["status"] == "READY_FOR_PICKUP"
    assert passed["qc_inspector"]["full_name"] == "Sara"  # QC-11: the picker is kept
    assert await round_and_issues(desk, journey) == ("READY_FOR_PICKUP", 3, 0)
    rounds = await history(desk, journey, world.advisor)
    assert [(r["round"], r["inspector"]["full_name"], r["result"]) for r in rounds] == [
        (1, "Sara", "FAIL"),
        (2, "Hina", "FAIL"),
        (3, "Sara", "PASS"),
    ]
    assert rounds[2]["notes"] == "All good"
    assert all(item["passed"] for item in rounds[2]["checklist"])
    issues = [issue for r in rounds for issue in r["issues"]]
    assert [(issue["title"], issue["status"]) for issue in issues] == [
        ("Oil leak at filter", "RESOLVED"),
        ("Brake squeal", "RESOLVED"),
    ]
    assert {issue["resolved_by"]["full_name"] for issue in issues} == {"Imran"}  # QC-05
    assert all(issue["resolved_at"] is not None for issue in issues)
    actions = [event.action for event in await events_of(db, journey.id)]
    assert actions[-10:] == [
        BookingAction.SEND_TO_QC,
        BookingAction.PICK_QC,
        BookingAction.FAIL_QC,
        BookingAction.SEND_TO_QC,
        BookingAction.PICK_QC,
        BookingAction.FAIL_QC,
        BookingAction.START_REPAIR,
        BookingAction.SEND_TO_QC,
        BookingAction.PICK_QC,
        BookingAction.PASS_QC,
    ]
    async with db.sessionmaker() as session:
        inspections = (
            await session.execute(
                select(QcInspection.result).where(QcInspection.booking_id == uuid.UUID(journey.id))
            )
        ).scalars()
        assert sorted(result.value for result in inspections if result) == ["FAIL", "FAIL", "PASS"]
        open_issues = (
            await session.execute(
                select(QcIssue.id).where(
                    QcIssue.booking_id == uuid.UUID(journey.id), QcIssue.resolved_at.is_(None)
                )
            )
        ).all()
        assert open_issues == []
    await desk.act(world.advisor, journey.id, "notify-ready")
    completed = await desk.my_act(journey.customer, journey.id, "complete")
    assert completed["status"] == "COMPLETED"
    assert await round_and_issues(desk, journey) == ("COMPLETED", 3, 0)


# --- BK-39 (sequential half), D47 -----------------------------------------------------------------


async def test_bk39_already_picked_names_the_picker_even_for_the_pickers_own_click(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.QC_IN_PROGRESS)  # Sara picked
    version = (await booking_row(db, journey.id)).version
    for member in (world.qc2, world.qc):
        body = problem(await desk.act_raw(member.id, journey.id, "pick-qc"), 409, "ALREADY_PICKED")
        assert body["detail"] == "Already picked by Sara."
    assert (await booking_row(db, journey.id)).version == version
    (round_one,) = await history(desk, journey, world.advisor)
    assert round_one["result"] is None  # still Sara's open round


async def test_d47_a_technician_who_became_a_qc_inspector_never_picks_their_own_job(
    desk: Desk, world: World
) -> None:
    journey = await drive_booking_to(desk, S.QC_PENDING)
    async with unit_of_work(world.db) as uow:
        await shops_service.update_member(
            uow,
            shop_id=world.shop_id,
            actor_user_id=world.owner.id,
            membership_id=world.technician.membership_id,
            data=MemberUpdate(role=StaffRole(MembershipRole.QC_INSPECTOR.value)),
        )
    imran = world.technician.id
    detail = await desk.get(imran, desk.booking_path(journey.id))  # the queue makes it visible
    assert "pick-qc" not in detail["allowed_actions"]
    problem(await desk.act_raw(imran, journey.id, "pick-qc"), 403, "FORBIDDEN")
    problem(await desk.act_raw(imran, journey.id, "start-repair"), 403, "FORBIDDEN")
    picked = await desk.act(world.qc, journey.id, "pick-qc")
    assert picked["qc_inspector"]["full_name"] == "Sara"
    response = await desk.api.get(desk.booking_path(journey.id), headers=bearer(world.qc2.id))
    assert "pick-qc" not in response.json()["allowed_actions"]


# --- pass-qc checklist guards (D46) ---------------------------------------------------------------


async def test_pass_qc_needs_every_checklist_item_passed(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.QC_IN_PROGRESS)
    before = await booking_row(db, journey.id)
    cases: list[tuple[list[dict[str, Any]], str]] = [
        (full_checklist()[:-1], "checklist_incomplete"),
        (full_checklist(failed=["no_leaks"]), "checklist_item_failed"),
    ]
    for checklist, code in cases:
        response = await desk.act_raw(world.qc.id, journey.id, "pass-qc", {"checklist": checklist})
        codes = [found for _, found in field_codes(problem(response, 422, "VALIDATION_ERROR"))]
        assert code in codes, codes
    missing = await desk.act_raw(world.qc.id, journey.id, "pass-qc", {})
    assert ("checklist", "missing") in field_codes(problem(missing, 422, "VALIDATION_ERROR"))
    after = await booking_row(db, journey.id)
    assert (after.status, after.version) == (before.status, before.version)
    (round_one,) = await history(desk, journey, world.advisor)
    assert (round_one["result"], round_one["checklist"]) == (None, None)
    async with db.sessionmaker() as session:
        results = (await session.execute(select(QcInspection.result))).scalars().all()
    assert results == [None]
    assert QcResult.PASS not in results

"""qc's nested writes on PostgreSQL, run inside real booking transactions (spec 08 T17-T20).

The qc halves of QC-01, QC-02, QC-03, QC-05, QC-06, QC-10, QC-11, QC-15, QC-17 and SM-10 (the HTTP
halves are the bookings action routes), plus D47, D63, tenant isolation (D20) and the
data-integrity backstops of `modules/qc.md`.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import AlreadyPicked, ErrorCode, Forbidden, ValidationFailed
from app.modules.bookings.models import Booking
from app.modules.qc import service as qc
from app.modules.qc.models import QcInspection, QcIssue
from app.modules.qc.schemas import QcChecklistItemWrite
from app.modules.qc.service import QcIntegrityError
from app.shared.enums import BookingStatus, QcChecklistKey, QcIssueStatus, QcResult
from app.shared.repository import FOREIGN_KEY_VIOLATION, constraint_name, error_code_for, sqlstate
from tests.modules.qc.support import BookingsStandIn, QcWorld, checklist, uow_for
from tests.rows import add_rows

pytestmark = pytest.mark.db

K = QcChecklistKey


async def picked(world: QcWorld, bookings: BookingsStandIn) -> tuple[Booking, uuid.UUID]:
    """A shop A booking sent to QC and picked by Sara; returns the booking and the round id."""
    booking = await world.booking(world.a)
    await bookings.send_to_qc(booking)
    return booking, await bookings.pick(booking, world.a.inspector)


# --- The loop (SM-10, QC-06, QC-10) ---------------------------------------------------------------


async def test_sm10_qc06_qc10_qc_loop_fails_twice_then_passes(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking = await world.booking(world.a)
    sara, hina, imran = world.a.inspector, world.a.inspector_2, world.a.technician

    assert await bookings.send_to_qc(booking) == []
    round_1 = await bookings.pick(booking, sara)
    first = await bookings.fail(booking, sara, items=checklist(failed=[K.NO_LEAKS]))
    assert await bookings.send_to_qc(booking) == [first.qc_issue_id]
    first_resolved_at = bookings.last_now
    round_2 = await bookings.pick(booking, hina)  # QC-10: another inspector takes the re-test
    second = await bookings.fail(booking, hina, title="Warning light still on")
    assert await bookings.send_to_qc(booking) == [second.qc_issue_id]
    second_resolved_at = bookings.last_now
    round_3 = await bookings.pick(booking, sara)
    assert await bookings.pass_(booking, sara, checklist(), notes="All fine now.") == round_3

    rounds = await world.rounds(booking)  # QC-06: one row per round, in order
    assert [inspection.id for inspection in rounds] == [round_1, round_2, round_3]
    assert [inspection.result for inspection in rounds] == [QcResult.FAIL] * 2 + [QcResult.PASS]
    assert [inspection.inspector_user_id for inspection in rounds] == [sara.id, hina.id, sara.id]
    assert [first.qc_inspection_id, second.qc_inspection_id] == [round_1, round_2]

    issues = await world.issues(booking)
    assert [issue.id for issue in issues] == [first.qc_issue_id, second.qc_issue_id]
    assert [issue.qc_inspection_id for issue in issues] == [round_1, round_2]
    assert {issue.status for issue in issues} == {QcIssueStatus.RESOLVED}
    assert {issue.resolved_by_user_id for issue in issues} == {imran.id}
    assert [issue.resolved_at for issue in issues] == [first_resolved_at, second_resolved_at]

    row = await world.reload(booking)
    assert (row.status, row.qc_inspector_user_id) == (BookingStatus.READY_FOR_PICKUP, sara.id)


# --- fail-qc (QC-03, QC-15) -----------------------------------------------------------------------


async def test_qc03_fail_records_a_failed_round_and_one_open_issue(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking, inspection_id = await picked(world, bookings)
    picked_at = bookings.last_now
    recorded = await bookings.fail(
        booking,
        world.a.inspector,
        title="  Oil leak at filter ",
        description="  Minor oil leak at the filter seal.\n",
    )
    failed_at = bookings.last_now

    (inspection,) = await world.rounds(booking)
    assert inspection.id == recorded.qc_inspection_id == inspection_id
    assert inspection.result is QcResult.FAIL
    assert (inspection.picked_at, inspection.completed_at) == (picked_at, failed_at)  # D63
    assert inspection.updated_at == failed_at
    assert (inspection.checklist, inspection.notes) == (None, None)

    (issue,) = await world.issues(booking)
    assert issue.id == recorded.qc_issue_id
    assert (issue.shop_id, issue.booking_id) == (world.a.id, booking.id)  # the round's booking
    assert issue.qc_inspection_id == inspection.id
    assert (issue.title, issue.description) == (
        "Oil leak at filter",
        "Minor oil leak at the filter seal.",
    )
    assert issue.status is QcIssueStatus.OPEN
    assert issue.created_by_user_id == world.a.inspector.id
    assert (issue.created_at, issue.updated_at) == (failed_at, failed_at)
    assert (issue.resolved_at, issue.resolved_by_user_id) == (None, None)

    row = await world.reload(booking)  # the stand-in's T20 part: same technician, picker cleared
    assert (row.status, row.technician_user_id, row.qc_inspector_user_id) == (
        BookingStatus.IN_REPAIR,
        world.a.technician.id,
        None,
    )


async def test_qc15_fail_without_a_checklist_stores_null(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking, _ = await picked(world, bookings)
    await bookings.fail(booking, world.a.inspector, items=None, notes="   ")
    (inspection,) = await world.rounds(booking)
    assert (inspection.checklist, inspection.notes) == (None, None)


async def test_qc15_fail_with_a_checklist_stores_labels_in_template_order_and_item_notes(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking, _ = await picked(world, bookings)
    items = checklist(
        failed=[K.NO_LEAKS, K.ROAD_TEST],
        notes={K.NO_LEAKS: " Oil at the filter ", K.ROAD_TEST: "Pulls left"},
        order=[K.COMPLAINT_RESOLVED, K.NO_LEAKS, K.ROAD_TEST, K.FLUID_LEVELS, K.NO_WARNING_LIGHTS],
    )
    await bookings.fail(booking, world.a.inspector, items=items, notes=" Re-test after the seal. ")
    (inspection,) = await world.rounds(booking)
    assert inspection.checklist == [
        {"key": "road_test", "label": "Road test", "passed": False, "note": "Pulls left"},
        {"key": "no_warning_lights", "label": "No warning lights", "passed": True},
        {"key": "no_leaks", "label": "No leaks", "passed": False, "note": "Oil at the filter"},
        {"key": "fluid_levels", "label": "Fluid levels OK", "passed": True},
        {"key": "complaint_resolved", "label": "Customer complaint resolved", "passed": True},
    ]
    assert inspection.notes == "Re-test after the seal."


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        ("", "Leak.", [("issue_title", "string_too_short")]),
        ("   ", "Leak.", [("issue_title", "string_too_short")]),
        ("t" * 121, "Leak.", [("issue_title", "string_too_long")]),
        ("Leak", "", [("issue_description", "string_too_short")]),
        ("Leak", " \n\t", [("issue_description", "string_too_short")]),
        ("Leak", "d" * 2001, [("issue_description", "string_too_long")]),
        ("", "", [("issue_title", "string_too_short"), ("issue_description", "string_too_short")]),
    ],
    ids=[
        "title-empty",
        "title-blank",
        "title-121",
        "description-empty",
        "description-blank",
        "description-2001",
        "both-missing",
    ],
)
async def test_qc02_fail_needs_an_issue_title_and_description(
    world: QcWorld,
    bookings: BookingsStandIn,
    title: str,
    description: str,
    expected: list[tuple[str, str]],
) -> None:
    booking, inspection_id = await picked(world, bookings)
    with pytest.raises(ValidationFailed) as caught:
        await bookings.fail(booking, world.a.inspector, title=title, description=description)
    assert caught.value.status_code == 422
    assert [(error["field"], error["code"]) for error in caught.value.errors or []] == expected
    await assert_round_untouched(world, booking, inspection_id)


async def test_qc02_title_and_description_at_their_limits_are_accepted(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking, _ = await picked(world, bookings)
    await bookings.fail(booking, world.a.inspector, title="t" * 120, description="d" * 2000)
    (issue,) = await world.issues(booking)
    assert (len(issue.title), len(issue.description)) == (120, 2000)


async def test_fail_with_an_incomplete_checklist_is_refused(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking, inspection_id = await picked(world, bookings)
    with pytest.raises(ValidationFailed) as caught:
        await bookings.fail(booking, world.a.inspector, items=[])
    assert [(error["field"], error["code"]) for error in caught.value.errors or []] == [
        ("checklist", "checklist_incomplete")
    ]
    await assert_round_untouched(world, booking, inspection_id)


async def test_every_invalid_fail_field_is_reported_at_once(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking, inspection_id = await picked(world, bookings)
    with pytest.raises(ValidationFailed) as caught:
        await bookings.fail(
            booking,
            world.a.inspector,
            title=" ",
            description="d" * 2001,
            items=[*checklist(), checklist()[1]],
            notes="n" * 2001,
        )
    assert [(error["field"], error["code"]) for error in caught.value.errors or []] == [
        ("issue_title", "string_too_short"),
        ("issue_description", "string_too_long"),
        ("checklist", "checklist_incomplete"),
        ("notes", "string_too_long"),
    ]
    await assert_round_untouched(world, booking, inspection_id)


# --- pass-qc (QC-01, QC-11) -----------------------------------------------------------------------


async def test_qc11_pass_completes_the_round_with_the_checklist_and_notes(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking, inspection_id = await picked(world, bookings)
    items = checklist(notes={K.COMPLAINT_RESOLVED: "Check-engine light is off"})
    assert await bookings.pass_(booking, world.a.inspector, items, notes="  Road test fine.  ") == (
        inspection_id
    )
    passed_at = bookings.last_now

    (inspection,) = await world.rounds(booking)
    assert inspection.result is QcResult.PASS
    assert (inspection.completed_at, inspection.updated_at) == (passed_at, passed_at)
    assert inspection.notes == "Road test fine."
    assert inspection.checklist == [
        {"key": "road_test", "label": "Road test", "passed": True},
        {"key": "no_warning_lights", "label": "No warning lights", "passed": True},
        {"key": "no_leaks", "label": "No leaks", "passed": True},
        {"key": "fluid_levels", "label": "Fluid levels OK", "passed": True},
        {
            "key": "complaint_resolved",
            "label": "Customer complaint resolved",
            "passed": True,
            "note": "Check-engine light is off",
        },
    ]
    assert await world.issues(booking) == []  # a pass raises no issue
    row = await world.reload(booking)
    assert row.qc_inspector_user_id == world.a.inspector.id  # D47: the picker is kept


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        (checklist()[:4], [("checklist", "checklist_incomplete")]),
        ([*checklist(), checklist()[0]], [("checklist", "checklist_incomplete")]),
        ([], [("checklist", "checklist_incomplete")]),
        (
            checklist(failed=[K.ROAD_TEST, K.FLUID_LEVELS]),
            [
                ("checklist.0.passed", "checklist_item_failed"),
                ("checklist.3.passed", "checklist_item_failed"),
            ],
        ),
        (
            checklist(failed=list(K))[:4],
            [("checklist", "checklist_incomplete")]
            + [(f"checklist.{n}.passed", "checklist_item_failed") for n in range(4)],
        ),
    ],
    ids=["missing-item", "repeated-item", "empty", "two-failed-items", "incomplete-and-failed"],
)
async def test_qc01_pass_needs_every_item_exactly_once_and_passed(
    world: QcWorld,
    bookings: BookingsStandIn,
    items: list[QcChecklistItemWrite],
    expected: list[tuple[str, str]],
) -> None:
    booking, inspection_id = await picked(world, bookings)
    with pytest.raises(ValidationFailed) as caught:
        await bookings.pass_(booking, world.a.inspector, items)
    assert caught.value.code is ErrorCode.VALIDATION_ERROR
    assert [(error["field"], error["code"]) for error in caught.value.errors or []] == expected
    await assert_round_untouched(world, booking, inspection_id)


async def test_pass_notes_over_2000_characters_are_refused(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking, inspection_id = await picked(world, bookings)
    with pytest.raises(ValidationFailed) as caught:
        await bookings.pass_(booking, world.a.inspector, checklist(), notes="n" * 2001)
    assert [(error["field"], error["code"]) for error in caught.value.errors or []] == [
        ("notes", "string_too_long")
    ]
    await assert_round_untouched(world, booking, inspection_id)


async def assert_round_untouched(
    world: QcWorld, booking: Booking, inspection_id: uuid.UUID
) -> None:
    """A refused pass or fail writes nothing: the round stays open and no issue exists."""
    (inspection,) = await world.rounds(booking)
    assert inspection.id == inspection_id
    assert (inspection.result, inspection.completed_at, inspection.checklist) == (None, None, None)
    assert await world.issues(booking) == []
    row = await world.reload(booking)
    assert row.status is BookingStatus.QC_IN_PROGRESS


# --- send-to-qc (QC-05) ---------------------------------------------------------------------------


async def test_qc05_send_to_qc_resolves_the_open_issues_of_that_booking_only(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    mine, other = await world.booking(world.a), await world.booking(world.a)
    for booking in (mine, other):
        await bookings.send_to_qc(booking)
        await bookings.pick(booking, world.a.inspector)
        await bookings.fail(booking, world.a.inspector)
    (open_mine,) = await world.issues(mine)

    assert await bookings.send_to_qc(mine) == [open_mine.id]
    resolved_at = bookings.last_now

    (resolved,) = await world.issues(mine)
    assert resolved.status is QcIssueStatus.RESOLVED
    assert (resolved.resolved_at, resolved.updated_at) == (resolved_at, resolved_at)
    assert resolved.resolved_by_user_id == world.a.technician.id
    (untouched,) = await world.issues(other)
    assert untouched.status is QcIssueStatus.OPEN
    assert (untouched.resolved_at, untouched.resolved_by_user_id) == (None, None)


async def test_qc05_every_open_issue_is_resolved_oldest_first_and_resolved_ones_keep_their_time(
    world: QcWorld,
) -> None:
    """Defence in depth: even several OPEN issues (the flow never leaves more than one) go."""
    booking = await world.booking(world.a)
    t0 = world.clock.now()
    inspection = QcInspection(
        shop_id=world.a.id,
        booking_id=booking.id,
        inspector_user_id=world.a.inspector.id,
        picked_at=t0,
        completed_at=t0,
        result=QcResult.FAIL,
    )

    def issue(minutes: int, status: QcIssueStatus = QcIssueStatus.OPEN) -> QcIssue:
        resolved = status is QcIssueStatus.RESOLVED
        return QcIssue(
            shop_id=world.a.id,
            booking_id=booking.id,
            qc_inspection_id=inspection.id,
            title=f"Issue {minutes}",
            description="Found during the road test.",
            status=status,
            created_by_user_id=world.a.inspector.id,
            created_at=t0 + timedelta(minutes=minutes),
            resolved_at=t0 if resolved else None,
            resolved_by_user_id=world.a.technician.id if resolved else None,
        )

    later, earlier, done = issue(5), issue(1), issue(0, QcIssueStatus.RESOLVED)
    await add_rows(world.db.sessionmaker, inspection, later, earlier, done)

    now = t0 + timedelta(hours=1)
    async with world.db.sessionmaker() as session:
        uow = uow_for(session)
        resolved = await qc.resolve_open_issues(
            uow,
            shop_id=world.a.id,
            booking_id=booking.id,
            resolved_by_user_id=world.a.technician.id,
            now=now,
        )
        await uow.commit()
    assert resolved == [earlier.id, later.id]
    by_id = {row.id: row for row in await world.issues(booking)}
    assert {by_id[earlier.id].resolved_at, by_id[later.id].resolved_at} == {now}
    assert by_id[done.id].resolved_at == t0  # already resolved: untouched


async def test_send_to_qc_without_open_issues_resolves_nothing(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking = await world.booking(world.a)
    assert await bookings.send_to_qc(booking) == []
    assert await world.issues(booking) == []


async def test_resolving_with_another_shops_id_touches_nothing(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    theirs = await world.booking(world.b)
    await bookings.send_to_qc(theirs)
    await bookings.pick(theirs, world.b.inspector)
    await bookings.fail(theirs, world.b.inspector)

    async with world.db.sessionmaker() as session:
        uow = uow_for(session)
        resolved = await qc.resolve_open_issues(
            uow,
            shop_id=world.a.id,  # shop A's request carrying shop B's booking id
            booking_id=theirs.id,
            resolved_by_user_id=world.a.technician.id,
            now=world.clock.now(),
        )
        await uow.commit()
    assert resolved == []
    (issue,) = await world.issues(theirs)
    assert issue.status is QcIssueStatus.OPEN


# --- pick-qc (QC-17, D30, D47) --------------------------------------------------------------------


async def test_pick_opens_a_round_stamped_with_the_actions_instant(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking, inspection_id = await picked(world, bookings)
    (inspection,) = await world.rounds(booking)
    assert inspection.id == inspection_id
    assert (inspection.shop_id, inspection.inspector_user_id) == (world.a.id, world.a.inspector.id)
    assert (
        inspection.picked_at == inspection.created_at == inspection.updated_at == bookings.last_now
    )
    assert (inspection.result, inspection.completed_at, inspection.checklist) == (None, None, None)
    assert inspection.notes is None


@pytest.mark.parametrize(
    "second_picker", ["inspector", "inspector_2"], ids=["double-click", "other"]
)
async def test_qc17_a_second_open_round_of_a_booking_is_already_picked(
    world: QcWorld, bookings: BookingsStandIn, second_picker: str
) -> None:
    booking, first = await picked(world, bookings)
    async with world.db.sessionmaker() as session:
        uow = uow_for(session)
        with pytest.raises(AlreadyPicked) as caught:
            await qc.open_inspection(
                uow,
                shop_id=world.a.id,
                booking_id=booking.id,
                inspector_user_id=getattr(world.a, second_picker).id,
                now=world.clock.now(),
            )
        assert (caught.value.status_code, caught.value.code) == (409, ErrorCode.ALREADY_PICKED)
        # The unique-index violation was contained in a savepoint: the transaction still works.
        assert await qc.list_inspector_ids(session, shop_id=world.a.id, booking_id=booking.id) == {
            world.a.inspector.id
        }
        await uow.commit()
    assert [inspection.id for inspection in await world.rounds(booking)] == [first]


async def test_open_inspection_refuses_a_booking_of_another_shop(world: QcWorld) -> None:
    """Only a tenant-scoping bug in the caller reaches the composite FK (D20). It must stay an
    unmapped integrity error — a logged 500 (spec 03 §2.4) — never a quiet, unlogged 404."""
    theirs = await world.booking(world.b)
    async with world.db.sessionmaker() as session:
        uow = uow_for(session)
        with pytest.raises(IntegrityError) as caught:
            await qc.open_inspection(
                uow,
                shop_id=world.a.id,
                booking_id=theirs.id,
                inspector_user_id=world.a.inspector.id,
                now=world.clock.now(),
            )
        assert constraint_name(caught.value) == "fk_qc_inspections_shop_id_booking_id_bookings"
        assert sqlstate(caught.value) == FOREIGN_KEY_VIOLATION
        assert error_code_for(caught.value) is None  # unmapped: the global handler answers 500
        # The savepoint rolled the refused insert back, so even committing writes nothing.
        await uow.commit()
    assert await world.rounds(theirs) == []


async def test_d47_the_bookings_technician_can_never_open_its_round(world: QcWorld) -> None:
    booking = await world.booking(world.a)
    async with world.db.sessionmaker() as session:
        uow = uow_for(session)
        with pytest.raises(Forbidden) as caught:
            await qc.open_inspection(
                uow,
                shop_id=world.a.id,
                booking_id=booking.id,
                inspector_user_id=world.a.technician.id,
                now=world.clock.now(),
                booking_technician_user_id=world.a.technician.id,
            )
        assert caught.value.status_code == 403
        # The refusal comes before any write: even a caller that went on and committed its
        # transaction would leave no round behind.
        await uow.commit()
    assert await world.rounds(booking) == []


# --- Data-integrity backstops (modules/qc.md "A QC round": -> 500, never a user error) ------------


QcState = tuple[list[tuple[object, ...]], list[tuple[object, ...]]]


async def qc_state(world: QcWorld, booking: Booking) -> QcState:
    """Every column a pass or fail could write, per round, and the booking's issues — read in
    fresh sessions, so only committed data counts."""
    rounds = [
        (
            inspection.id,
            inspection.inspector_user_id,
            inspection.result,
            inspection.completed_at,
            inspection.checklist,
            inspection.notes,
            inspection.updated_at,
        )
        for inspection in await world.rounds(booking)
    ]
    issues = [
        (issue.id, issue.status, issue.resolved_at, issue.updated_at)
        for issue in await world.issues(booking)
    ]
    return rounds, issues


async def test_pass_or_fail_without_an_open_round_is_an_integrity_error(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking = await world.booking(world.a)
    await bookings.send_to_qc(booking)  # QC_PENDING: nobody picked it
    async with world.db.sessionmaker() as session:
        uow = uow_for(session)
        with pytest.raises(QcIntegrityError, match="no open QC round"):
            await qc.record_pass(
                uow,
                shop_id=world.a.id,
                booking_id=booking.id,
                inspector_user_id=world.a.inspector.id,
                checklist=checklist(),
                notes="Passed",
                now=world.clock.now(),
            )
        # Commit anyway: a write made before the refusal would now be visible.
        await uow.commit()
        assert await qc_state(world, booking) == ([], [])

        with pytest.raises(QcIntegrityError, match="no open QC round"):
            await qc.record_fail(
                uow,
                shop_id=world.a.id,
                booking_id=booking.id,
                inspector_user_id=world.a.inspector.id,
                issue_title="Leak",
                issue_description="Leak.",
                checklist=checklist(failed=[K.NO_LEAKS]),
                notes="Failed",
                now=world.clock.now(),
            )
        await uow.commit()
        assert await qc_state(world, booking) == ([], [])


@pytest.mark.parametrize("finished_as", [QcResult.FAIL, QcResult.PASS], ids=["failed", "passed"])
async def test_a_finished_round_cannot_be_passed_or_failed_again(
    world: QcWorld, bookings: BookingsStandIn, finished_as: QcResult
) -> None:
    booking, inspection_id = await picked(world, bookings)
    if finished_as is QcResult.FAIL:
        await bookings.fail(booking, world.a.inspector)
    else:
        await bookings.pass_(booking, world.a.inspector, checklist(), notes="Road test fine.")
    (before,) = await world.rounds(booking)
    issues_before = [
        (issue.id, issue.status, issue.updated_at) for issue in await world.issues(booking)
    ]

    async with world.db.sessionmaker() as session:
        uow = uow_for(session)
        with pytest.raises(QcIntegrityError, match="no open QC round"):
            await qc.record_pass(
                uow,
                shop_id=world.a.id,
                booking_id=booking.id,
                inspector_user_id=world.a.inspector.id,
                checklist=checklist(),
                notes="Passed again",
                now=world.clock.now(),
            )
        with pytest.raises(QcIntegrityError, match="no open QC round"):
            await qc.record_fail(
                uow,
                shop_id=world.a.id,
                booking_id=booking.id,
                inspector_user_id=world.a.inspector.id,
                issue_title="Leak",
                issue_description="Leak found again.",
                checklist=checklist(failed=[K.NO_LEAKS]),
                notes="Failed again",
                now=world.clock.now(),
            )
        # Both refusals come before any write, so committing the transaction changes nothing.
        await uow.commit()

    (after,) = await world.rounds(booking)
    assert after.id == inspection_id
    assert after.result is finished_as
    assert (after.completed_at, after.checklist, after.notes, after.updated_at) == (
        before.completed_at,
        before.checklist,
        before.notes,
        before.updated_at,
    )
    assert [
        (issue.id, issue.status, issue.updated_at) for issue in await world.issues(booking)
    ] == issues_before
    assert len(issues_before) == (1 if finished_as is QcResult.FAIL else 0)  # no new issue


async def test_pass_or_fail_by_someone_other_than_the_picker_is_an_integrity_error(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    """QC-04's 403 `NOT_ASSIGNED` is the state machine's; reaching qc anyway is a bug (500)."""
    booking, inspection_id = await picked(world, bookings)
    before = await qc_state(world, booking)
    async with world.db.sessionmaker() as session:
        uow = uow_for(session)
        with pytest.raises(QcIntegrityError, match="picked by"):
            await qc.record_pass(
                uow,
                shop_id=world.a.id,
                booking_id=booking.id,
                inspector_user_id=world.a.inspector_2.id,
                checklist=checklist(),
                notes="Passed by the wrong inspector",
                now=world.clock.now(),
            )
        # Commit anyway: a write made before the refusal would now be visible.
        await uow.commit()
        assert await qc_state(world, booking) == before

        with pytest.raises(QcIntegrityError, match="picked by"):
            await qc.record_fail(
                uow,
                shop_id=world.a.id,
                booking_id=booking.id,
                inspector_user_id=world.a.inspector_2.id,
                issue_title="Leak",
                issue_description="Leak.",
                checklist=checklist(failed=[K.NO_LEAKS]),
                notes="Failed by the wrong inspector",
                now=world.clock.now(),
            )
        await uow.commit()
        assert await qc_state(world, booking) == before
    await assert_round_untouched(world, booking, inspection_id)


async def test_pass_or_fail_with_another_shops_id_never_reaches_that_shops_round(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    theirs = await world.booking(world.b)
    await bookings.send_to_qc(theirs)
    their_round = await bookings.pick(theirs, world.b.inspector)
    before = await qc_state(world, theirs)
    async with world.db.sessionmaker() as session:
        uow = uow_for(session)
        with pytest.raises(QcIntegrityError, match="no open QC round"):
            await qc.record_pass(
                uow,
                shop_id=world.a.id,  # shop A's request carrying shop B's booking id
                booking_id=theirs.id,
                inspector_user_id=world.b.inspector.id,
                checklist=checklist(),
                notes="Passed through the wrong shop",
                now=world.clock.now(),
            )
        # Commit anyway: a write made before the refusal would now be visible.
        await uow.commit()
        assert await qc_state(world, theirs) == before

        with pytest.raises(QcIntegrityError, match="no open QC round"):
            await qc.record_fail(
                uow,
                shop_id=world.a.id,
                booking_id=theirs.id,
                inspector_user_id=world.b.inspector.id,
                issue_title="Leak",
                issue_description="Leak.",
                checklist=checklist(failed=[K.NO_LEAKS]),
                notes="Failed through the wrong shop",
                now=world.clock.now(),
            )
        await uow.commit()
        assert await qc_state(world, theirs) == before
    (inspection,) = await world.rounds(theirs)
    assert (inspection.id, inspection.result) == (their_round, None)  # shop B's round, still open
    assert await world.issues(theirs) == []


# --- P1, planned D87: moving a stuck pick to another inspector ------------------------------------


async def reassign(
    world: QcWorld, booking: Booking, new_inspector: uuid.UUID, technician: uuid.UUID | None = None
) -> uuid.UUID:
    async with world.db.sessionmaker() as session:
        uow = uow_for(session)
        moved = await qc.reassign_open_inspection(
            uow,
            shop_id=world.a.id,
            booking_id=booking.id,
            new_inspector_user_id=new_inspector,
            now=world.clock.now(),
            booking_technician_user_id=technician,
        )
        await uow.commit()
    return moved


async def test_d87_the_open_round_moves_to_the_new_inspector(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking, inspection_id = await picked(world, bookings)
    picked_at = bookings.last_now
    assert await reassign(world, booking, world.a.inspector_2.id) == inspection_id

    (inspection,) = await world.rounds(booking)
    assert inspection.inspector_user_id == world.a.inspector_2.id
    assert inspection.picked_at == picked_at  # the round started when it was first picked
    assert inspection.updated_at > picked_at

    async with world.db.sessionmaker() as session:  # the new picker can now finish the round
        uow = uow_for(session)
        await qc.record_pass(
            uow,
            shop_id=world.a.id,
            booking_id=booking.id,
            inspector_user_id=world.a.inspector_2.id,
            checklist=checklist(),
            notes=None,
            now=world.clock.now(),
        )
        await uow.commit()
    (inspection,) = await world.rounds(booking)
    assert inspection.result is QcResult.PASS


async def test_d87_reassigning_without_an_open_round_or_to_the_technician_is_refused(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking = await world.booking(world.a)
    await bookings.send_to_qc(booking)
    with pytest.raises(QcIntegrityError, match="no open QC round to reassign"):
        await reassign(world, booking, world.a.inspector_2.id)

    await bookings.pick(booking, world.a.inspector)
    with pytest.raises(Forbidden):
        await reassign(world, booking, world.a.technician.id, technician=world.a.technician.id)
    (inspection,) = await world.rounds(booking)
    assert inspection.inspector_user_id == world.a.inspector.id

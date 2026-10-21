"""qc's reads on PostgreSQL: the QC history, summaries and the D21 / realtime helpers.

QC-06, QC-09 (history with the issues sent back), QC-14 (summaries through a fail loop), QC-16
(an inspector keeps seeing bookings they inspected; qc half), NOT-12's QC viewers (qc half) and
tenant isolation (D20): another shop's booking id matches nothing.
"""

import uuid
from collections.abc import Collection

import pytest
from sqlalchemy import update

from app.modules.identity import service as identity_service
from app.modules.identity.models import User
from app.modules.identity.schemas import UserRef
from app.modules.qc import service as qc
from app.modules.qc.models import QcInspection
from app.modules.qc.schemas import QcSummary
from app.modules.qc.service import QcIntegrityError
from app.shared.enums import BookingStatus, QcChecklistKey, QcIssueStatus, QcResult
from tests.modules.qc.support import BookingsStandIn, QcWorld, checklist, uow_for

pytestmark = pytest.mark.db

K = QcChecklistKey


def ref(user: User) -> UserRef:
    return UserRef(user_id=user.id, full_name=user.full_name)


# --- History (QC-06, QC-09) -----------------------------------------------------------------------


async def test_qc06_qc09_history_lists_every_round_in_order_with_its_issue_and_names(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking = await world.booking(world.a)
    sara, hina, imran = world.a.inspector, world.a.inspector_2, world.a.technician
    await bookings.send_to_qc(booking)
    round_1 = await bookings.pick(booking, sara)
    picked_1 = bookings.last_now
    failed = await bookings.fail(
        booking,
        sara,
        title="Oil leak at filter",
        description="Minor oil leak at the filter seal.",
        items=checklist(failed=[K.NO_LEAKS], notes={K.NO_LEAKS: "Drip under the filter"}),
        notes="Road tested 5 km.",
    )
    failed_at = bookings.last_now
    await bookings.send_to_qc(booking)
    resolved_at = bookings.last_now
    round_2 = await bookings.pick(booking, hina)

    async with world.db.sessionmaker() as session:
        history = await qc.list_booking_qc_history(
            session, shop_id=world.a.id, booking_id=booking.id
        )

    assert [(item.id, item.round) for item in history] == [(round_1, 1), (round_2, 2)]
    first, second = history
    assert first.inspector == ref(sara)
    assert (first.picked_at, first.completed_at, first.result) == (
        picked_1,
        failed_at,
        QcResult.FAIL,
    )
    assert first.notes == "Road tested 5 km."
    assert first.checklist is not None
    assert [(item.key, item.passed, item.note) for item in first.checklist] == [
        (K.ROAD_TEST, True, None),
        (K.NO_WARNING_LIGHTS, True, None),
        (K.NO_LEAKS, False, "Drip under the filter"),
        (K.FLUID_LEVELS, True, None),
        (K.COMPLAINT_RESOLVED, True, None),
    ]
    assert [item.label for item in first.checklist][3] == "Fluid levels OK"
    (issue,) = first.issues  # QC-09: what QC sent back to the technician
    assert issue.id == failed.qc_issue_id
    assert issue.qc_inspection_id == round_1
    assert (issue.title, issue.description) == (
        "Oil leak at filter",
        "Minor oil leak at the filter seal.",
    )
    assert (issue.status, issue.created_by, issue.created_at) == (
        QcIssueStatus.RESOLVED,
        ref(sara),
        failed_at,
    )
    assert (issue.resolved_at, issue.resolved_by) == (resolved_at, ref(imran))

    # Round 2 is in progress: no result, no completion, no checklist yet.
    assert second.inspector == ref(hina)
    assert (second.result, second.completed_at, second.checklist, second.notes) == (
        None,
        None,
        None,
        None,
    )
    assert second.issues == []


async def test_an_open_issue_shows_no_resolution(world: QcWorld, bookings: BookingsStandIn) -> None:
    booking = await world.booking(world.a)
    await bookings.send_to_qc(booking)
    await bookings.pick(booking, world.a.inspector)
    await bookings.fail(booking, world.a.inspector)
    async with world.db.sessionmaker() as session:
        (inspection,) = await qc.list_booking_qc_history(
            session, shop_id=world.a.id, booking_id=booking.id
        )
    (issue,) = inspection.issues
    assert (issue.status, issue.resolved_at, issue.resolved_by) == (QcIssueStatus.OPEN, None, None)


async def test_history_is_empty_before_qc_and_for_another_shops_booking(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    mine, theirs = await world.booking(world.a), await world.booking(world.b)
    await bookings.send_to_qc(theirs)
    await bookings.pick(theirs, world.b.inspector)
    async with world.db.sessionmaker() as session:
        assert (
            await qc.list_booking_qc_history(session, shop_id=world.a.id, booking_id=mine.id) == []
        )
        assert (
            await qc.list_booking_qc_history(session, shop_id=world.a.id, booking_id=theirs.id)
            == []
        )
        assert (
            await qc.list_booking_qc_history(session, shop_id=world.a.id, booking_id=uuid.uuid4())
            == []
        )
        assert (
            len(await qc.list_booking_qc_history(session, shop_id=world.b.id, booking_id=theirs.id))
            == 1
        )


async def test_history_names_come_from_one_identity_batch(
    world: QcWorld, bookings: BookingsStandIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    booking = await world.booking(world.a)
    for inspector in (world.a.inspector, world.a.inspector_2, world.a.inspector):
        await bookings.send_to_qc(booking)
        await bookings.pick(booking, inspector)
        await bookings.fail(booking, inspector)
    await bookings.send_to_qc(booking)

    calls: list[set[uuid.UUID]] = []
    real = identity_service.get_users_by_ids

    async def spy(session: object, user_ids: Collection[uuid.UUID]) -> object:
        calls.append(set(user_ids))
        return await real(session, user_ids)  # type: ignore[arg-type]

    monkeypatch.setattr(identity_service, "get_users_by_ids", spy)
    async with world.db.sessionmaker() as session:
        history = await qc.list_booking_qc_history(
            session, shop_id=world.a.id, booking_id=booking.id
        )
    assert [item.round for item in history] == [1, 2, 3]
    assert calls == [{world.a.inspector.id, world.a.inspector_2.id, world.a.technician.id}]


async def test_a_deactivated_inspector_keeps_their_name_in_the_history(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    """Names come from identity whatever the account status (D19: history is never rewritten)."""
    booking = await world.booking(world.a)
    await bookings.send_to_qc(booking)
    await bookings.pick(booking, world.a.inspector)
    await bookings.fail(booking, world.a.inspector)
    async with world.db.sessionmaker() as session:
        await session.execute(
            update(User).where(User.id == world.a.inspector.id).values(is_active=False)
        )
        await session.commit()
        (inspection,) = await qc.list_booking_qc_history(
            session, shop_id=world.a.id, booking_id=booking.id
        )
    assert inspection.inspector.full_name == "Sara"


async def test_history_keeps_the_label_stored_with_the_round(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    """D46: the label is copied at write time, so a finished round keeps its wording."""
    booking = await world.booking(world.a)
    await bookings.send_to_qc(booking)
    inspection_id = await bookings.pick(booking, world.a.inspector)
    await bookings.pass_(booking, world.a.inspector, checklist())
    stored = [dict(item) for item in (await world.rounds(booking))[0].checklist or []]
    stored[0]["label"] = "Road test (old wording)"
    async with world.db.sessionmaker() as session:
        await session.execute(
            update(QcInspection).where(QcInspection.id == inspection_id).values(checklist=stored)
        )
        await session.commit()
        (inspection,) = await qc.list_booking_qc_history(
            session, shop_id=world.a.id, booking_id=booking.id
        )
    assert inspection.checklist is not None
    assert inspection.checklist[0].label == "Road test (old wording)"


async def test_a_round_whose_inspector_is_unknown_to_identity_is_an_integrity_error(
    world: QcWorld, bookings: BookingsStandIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    booking = await world.booking(world.a)
    await bookings.send_to_qc(booking)
    await bookings.pick(booking, world.a.inspector)

    async def nobody(session: object, user_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, object]:
        return {}

    monkeypatch.setattr(identity_service, "get_users_by_ids", nobody)
    async with world.db.sessionmaker() as session:
        with pytest.raises(QcIntegrityError, match="not found"):
            await qc.list_booking_qc_history(session, shop_id=world.a.id, booking_id=booking.id)


# --- Summaries (QC-14) ----------------------------------------------------------------------------


async def summary(world: QcWorld, booking_id: uuid.UUID) -> QcSummary:
    async with world.db.sessionmaker() as session:
        return (await qc.get_qc_summaries(session, shop_id=world.a.id, booking_ids=[booking_id]))[
            booking_id
        ]


async def test_qc14_summaries_and_qc_round_through_a_fail_loop(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking = await world.booking(world.a)

    async def state() -> tuple[int, int, int]:
        current = await summary(world, booking.id)
        status = (await world.reload(booking)).status
        return current.inspections, current.open_issues, current.qc_round(status)

    assert await state() == (0, 0, 0)  # IN_REPAIR, never reached QC
    await bookings.send_to_qc(booking)
    assert await state() == (0, 0, 1)  # QC_PENDING: round 1 waits
    await bookings.pick(booking, world.a.inspector)
    assert await state() == (1, 0, 1)
    await bookings.fail(booking, world.a.inspector)
    assert await state() == (1, 1, 1)  # IN_REPAIR with one open issue
    await bookings.send_to_qc(booking)
    assert await state() == (1, 0, 2)  # the re-test: issue resolved, round 2 waits
    await bookings.pick(booking, world.a.inspector_2)
    assert await state() == (2, 0, 2)
    await bookings.pass_(booking, world.a.inspector_2, checklist())
    assert await state() == (2, 0, 2)  # READY_FOR_PICKUP


async def test_summaries_have_one_entry_per_id_zeros_included_and_are_shop_scoped(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    failed, picked, untouched = [await world.booking(world.a) for _ in range(3)]
    theirs = await world.booking(world.b)
    for booking in (failed, picked):
        await bookings.send_to_qc(booking)
        await bookings.pick(booking, world.a.inspector)
    await bookings.fail(failed, world.a.inspector)
    await bookings.send_to_qc(theirs)
    await bookings.pick(theirs, world.b.inspector)
    unknown = uuid.uuid4()

    async with world.db.sessionmaker() as session:
        summaries = await qc.get_qc_summaries(
            session,
            shop_id=world.a.id,
            booking_ids=[failed.id, picked.id, untouched.id, theirs.id, unknown, failed.id],
        )
    assert summaries == {
        failed.id: QcSummary(inspections=1, open_issues=1),
        picked.id: QcSummary(inspections=1, open_issues=0),
        untouched.id: QcSummary(inspections=0, open_issues=0),
        theirs.id: QcSummary(inspections=0, open_issues=0),  # shop B's round is invisible here
        unknown: QcSummary(inspections=0, open_issues=0),
    }
    assert list(summaries) == [failed.id, picked.id, untouched.id, theirs.id, unknown]


async def test_summaries_of_no_bookings_are_empty(world: QcWorld) -> None:
    async with world.db.sessionmaker() as session:
        assert await qc.get_qc_summaries(session, shop_id=world.a.id, booking_ids=[]) == {}
        assert await qc.get_qc_summaries(session, shop_id=world.a.id, booking_ids=()) == {}


# --- D21 and realtime helpers (QC-16, NOT-12 qc half) ---------------------------------------------


async def test_qc16_an_inspector_keeps_seeing_the_bookings_they_inspected(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    sara, hina = world.a.inspector, world.a.inspector_2
    inspected, never = await world.booking(world.a), await world.booking(world.a)
    await bookings.send_to_qc(inspected)
    await bookings.pick(inspected, sara)
    await bookings.pass_(inspected, sara, checklist())  # left QC: READY_FOR_PICKUP
    await bookings.send_to_qc(never)  # in the queue, nobody picked it yet

    async with world.db.sessionmaker() as session:
        assert await qc.list_inspected_booking_ids(
            session, shop_id=world.a.id, inspector_user_id=sara.id
        ) == frozenset({inspected.id})
        assert (
            await qc.list_inspected_booking_ids(
                session, shop_id=world.a.id, inspector_user_id=hina.id
            )
            == frozenset()
        )
        assert await qc.has_inspected(
            session, shop_id=world.a.id, booking_id=inspected.id, inspector_user_id=sara.id
        )
        assert not await qc.has_inspected(
            session, shop_id=world.a.id, booking_id=inspected.id, inspector_user_id=hina.id
        )
        assert not await qc.has_inspected(
            session, shop_id=world.a.id, booking_id=never.id, inspector_user_id=sara.id
        )


async def test_an_open_round_already_counts_as_inspected(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking = await world.booking(world.a)
    await bookings.send_to_qc(booking)
    await bookings.pick(booking, world.a.inspector)
    async with world.db.sessionmaker() as session:
        assert await qc.has_inspected(
            session,
            shop_id=world.a.id,
            booking_id=booking.id,
            inspector_user_id=world.a.inspector.id,
        )


async def test_inspected_bookings_are_scoped_to_the_shop(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    theirs = await world.booking(world.b)
    await bookings.send_to_qc(theirs)
    await bookings.pick(theirs, world.b.inspector)
    inspector = world.b.inspector.id
    async with world.db.sessionmaker() as session:
        assert await qc.list_inspected_booking_ids(
            session, shop_id=world.b.id, inspector_user_id=inspector
        ) == frozenset({theirs.id})
        assert (
            await qc.list_inspected_booking_ids(
                session, shop_id=world.a.id, inspector_user_id=inspector
            )
            == frozenset()
        )
        assert not await qc.has_inspected(
            session, shop_id=world.a.id, booking_id=theirs.id, inspector_user_id=inspector
        )
        assert await qc.list_inspector_ids(session, shop_id=world.a.id, booking_id=theirs.id) == (
            frozenset()
        )


async def test_list_inspector_ids_names_everyone_who_inspected_the_booking(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    booking, other = await world.booking(world.a), await world.booking(world.a)
    async with world.db.sessionmaker() as session:
        assert await qc.list_inspector_ids(session, shop_id=world.a.id, booking_id=booking.id) == (
            frozenset()
        )
    await bookings.send_to_qc(booking)
    await bookings.pick(booking, world.a.inspector)
    await bookings.fail(booking, world.a.inspector)
    await bookings.send_to_qc(booking)
    await bookings.pick(booking, world.a.inspector_2)
    await bookings.send_to_qc(other)
    async with world.db.sessionmaker() as session:
        assert await qc.list_inspector_ids(session, shop_id=world.a.id, booking_id=booking.id) == (
            frozenset({world.a.inspector.id, world.a.inspector_2.id})
        )
        assert await qc.list_inspector_ids(session, shop_id=world.a.id, booking_id=other.id) == (
            frozenset()
        )


async def test_reads_see_the_callers_uncommitted_writes(world: QcWorld) -> None:
    """Bookings reads QC facts on the action's own session (e.g. a response built before commit)."""
    booking = await world.booking(world.a)
    async with world.db.sessionmaker() as session:
        uow = uow_for(session)
        await qc.open_inspection(
            uow,
            shop_id=world.a.id,
            booking_id=booking.id,
            inspector_user_id=world.a.inspector.id,
            now=world.clock.now(),
        )
        summaries = await qc.get_qc_summaries(session, shop_id=world.a.id, booking_ids=[booking.id])
        assert summaries[booking.id] == QcSummary(inspections=1, open_issues=0)
        assert summaries[booking.id].qc_round(BookingStatus.QC_IN_PROGRESS) == 1
        await uow.rollback()
    assert await world.rounds(booking) == []

"""Notification rows written in the action's transaction (PostgreSQL).

NOT-01 / NOT-02 (the whole trigger table, incl. the cancel-by-customer vs cancel-by-staff split),
NOT-03 (SAs of the shop and the D26 Owner fallback), NOT-04 (tenant safety across the worked
example), NOT-07 (rows roll back with the action), NOT-11 (`recipient_role` + server-built `link`),
D9 (named staff only while active members), D63 (`created_at` = the action's instant), D91 (one row
per user, first role wins, the actor is not excluded) and "one `INSERT … VALUES …` per action".
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import event, func, select, update

from app.core.database import Database
from app.modules.bookings.events import BookingActionApplied
from app.modules.bookings.models import Booking
from app.modules.identity.models import User
from app.modules.notifications.domain.links import is_relative_link
from app.modules.notifications.models import Notification
from app.modules.shops import service as shops_service
from app.shared.enums import (
    ActorRole,
    BookingAction,
    BookingStatus,
    MembershipRole,
    NotificationType,
)
from app.shared.event_bus import EventBus
from app.shared.uow import UnitOfWork, pending_after_commit_tasks
from tests.assertions import invariant_violations
from tests.modules.notifications.support import (
    START,
    World,
    applied,
    notifications_bus,
    publish,
    summary,
)

pytestmark = pytest.mark.db

A = BookingAction
R = ActorRole
T = NotificationType


def who(world: World, path: str) -> User:
    """`"ayesha"`, `"a.advisor"`, `"b.owner"` … → the user."""
    target: Any = world
    for part in path.split("."):
        target = getattr(target, part)
    assert isinstance(target, User)
    return target


def link(role: ActorRole, booking: Booking) -> str:
    if role == R.CUSTOMER:
        return f"/bookings/{booking.id}"
    surface = {
        R.SERVICE_ADVISOR: "bookings",
        R.OWNER: "bookings",
        R.TECHNICIAN: "jobs",
        R.PARTS_PERSON: "parts",
        R.QC_INSPECTOR: "qc",
    }[role]
    return f"/pos/shops/{booking.shop_id}/{surface}/{booking.id}"


SAS = (("a.advisor", R.SERVICE_ADVISOR), ("a.advisor_2", R.SERVICE_ADVISOR))
CUSTOMER = (("ayesha", R.CUSTOMER),)
TECHNICIAN = (("a.technician", R.TECHNICIAN),)


@dataclass(frozen=True)
class Case:
    """One trigger-table row, stated independently of the implementation (glossary §6)."""

    action: BookingAction
    actor: str
    actor_role: ActorRole
    type: NotificationType | None
    recipients: tuple[tuple[str, ActorRole], ...] = ()
    assignees: tuple[tuple[str, str], ...] = ()  # event field -> cast member (after the action)

    @property
    def id(self) -> str:
        return f"{self.action}-by-{self.actor_role}"


CASES = (
    Case(A.CREATE, "ayesha", R.CUSTOMER, T.BOOKING_CREATED, SAS),
    Case(A.CONFIRM, "a.advisor", R.SERVICE_ADVISOR, T.BOOKING_CONFIRMED, CUSTOMER),
    Case(A.CONFIRM, "a.owner", R.OWNER, T.BOOKING_CONFIRMED, CUSTOMER),
    Case(A.DECLINE, "a.advisor", R.SERVICE_ADVISOR, T.BOOKING_CANCELLED, CUSTOMER),
    Case(A.ASSIGN_TECHNICIAN, "a.advisor", R.SERVICE_ADVISOR, T.TECHNICIAN_ASSIGNED, TECHNICIAN),
    Case(A.START_INSPECTION, "a.technician", R.TECHNICIAN, None),
    Case(A.EDIT_ESTIMATE, "a.advisor", R.SERVICE_ADVISOR, None),
    Case(A.SUBMIT_ESTIMATE, "a.technician", R.TECHNICIAN, T.ESTIMATE_SUBMITTED, SAS),
    Case(A.SEND_ESTIMATE, "a.advisor", R.SERVICE_ADVISOR, T.ESTIMATE_SENT, CUSTOMER),
    Case(A.APPROVE_ESTIMATE, "ayesha", R.CUSTOMER, T.ESTIMATE_APPROVED, SAS),
    Case(A.REJECT_ESTIMATE, "ayesha", R.CUSTOMER, T.ESTIMATE_REJECTED, SAS),
    Case(A.REVISE_ESTIMATE, "a.advisor", R.SERVICE_ADVISOR, None),
    Case(A.RETURN_TO_TECHNICIAN, "a.advisor", R.SERVICE_ADVISOR, T.ESTIMATE_RETURNED, TECHNICIAN),
    Case(
        A.ASSIGN_PARTS_PERSON,
        "a.advisor",
        R.SERVICE_ADVISOR,
        T.PARTS_NEEDED,
        (("a.parts", R.PARTS_PERSON),),
    ),
    Case(A.ORDER_PARTS, "a.parts", R.PARTS_PERSON, None),
    Case(A.MARK_PARTS_READY, "a.parts", R.PARTS_PERSON, None),
    Case(A.RECEIVE_PARTS, "a.parts", R.PARTS_PERSON, None),
    Case(A.ALLOCATE_PARTS, "a.parts", R.PARTS_PERSON, T.PARTS_READY, TECHNICIAN),
    Case(A.START_REPAIR, "a.technician", R.TECHNICIAN, None),
    Case(
        A.SEND_TO_QC,
        "a.technician",
        R.TECHNICIAN,
        T.QC_REQUESTED,
        (("a.inspector", R.QC_INSPECTOR), ("a.inspector_2", R.QC_INSPECTOR)),
    ),
    Case(A.PICK_QC, "a.inspector", R.QC_INSPECTOR, None),
    Case(A.PASS_QC, "a.inspector", R.QC_INSPECTOR, T.QC_PASSED, SAS),
    Case(A.FAIL_QC, "a.inspector", R.QC_INSPECTOR, T.QC_FAILED, TECHNICIAN),
    Case(A.NOTIFY_READY, "a.advisor", R.SERVICE_ADVISOR, T.VEHICLE_READY, CUSTOMER),
    Case(A.COMPLETE, "ayesha", R.CUSTOMER, None),
    Case(A.COMPLETE, "a.advisor", R.SERVICE_ADVISOR, None),
    Case(A.CANCEL, "a.advisor", R.SERVICE_ADVISOR, T.BOOKING_CANCELLED, CUSTOMER),
    Case(A.CANCEL, "a.owner", R.OWNER, T.BOOKING_CANCELLED, CUSTOMER),
    Case(
        A.CANCEL,
        "ayesha",
        R.CUSTOMER,
        T.BOOKING_CANCELLED,
        (*SAS, ("a.technician", R.TECHNICIAN), ("a.parts", R.PARTS_PERSON)),
    ),
    Case(
        A.REASSIGN_TECHNICIAN,
        "a.advisor",
        R.SERVICE_ADVISOR,
        T.TECHNICIAN_ASSIGNED,
        (("a.technician_2", R.TECHNICIAN),),
        (("technician_user_id", "a.technician_2"),),
    ),
    Case(
        A.REASSIGN_PARTS_PERSON,
        "a.advisor",
        R.SERVICE_ADVISOR,
        T.PARTS_NEEDED,
        (("a.parts_2", R.PARTS_PERSON),),
        (("parts_person_user_id", "a.parts_2"),),
    ),
)


def test_the_cases_cover_every_booking_action() -> None:
    assert {case.action for case in CASES} == set(BookingAction)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
async def test_not01_not02_not11_trigger_table(world: World, case: Case) -> None:
    booking = await world.job(world.a)
    assignees = {field: who(world, member).id for field, member in case.assignees}
    action = applied(
        booking,
        case.action,
        actor=who(world, case.actor),
        actor_role=case.actor_role,
        note="Some note",
        metadata={"version": 2, "grand_total": "16100.00"},
        **assignees,
    )

    await publish(world.db, action)

    rows = await world.notifications(booking)
    expected = {(who(world, member).id, role, case.type) for member, role in case.recipients}
    assert summary(rows) == expected
    assert len(rows) == len(expected)  # one row per recipient
    for row in rows:
        assert row.link == link(row.recipient_role, booking)  # D67: chosen by recipient_role
        assert is_relative_link(row.link)
        assert row.shop_id == booking.shop_id
        assert row.booking_id == booking.id
        assert row.created_at == action.occurred_at  # D63
        assert row.read_at is None
        assert row.title.strip()
        assert row.body.strip()
        assert row.recipient_role != R.SYSTEM


# --- Recipient rules ------------------------------------------------------------------------------


async def test_not03_inactive_sas_get_nothing(world: World) -> None:
    booking = await world.job(world.a)
    await world.set_membership_active(world.a.shop, world.a.advisor, active=False)

    await publish(world.db, applied(booking, A.CREATE, actor=world.ayesha, actor_role=R.CUSTOMER))

    rows = await world.notifications(booking)
    assert summary(rows) == {(world.a.advisor_2.id, R.SERVICE_ADVISOR, T.BOOKING_CREATED)}


async def test_not03_an_sa_whose_account_is_deactivated_gets_nothing(world: World) -> None:
    booking = await world.job(world.a)
    await world.set_user_active(world.a.advisor_2, active=False)

    await publish(
        world.db,
        applied(booking, A.SUBMIT_ESTIMATE, actor=world.a.technician, actor_role=R.TECHNICIAN),
    )

    rows = await world.notifications(booking)
    assert summary(rows) == {(world.a.advisor.id, R.SERVICE_ADVISOR, T.ESTIMATE_SUBMITTED)}


async def test_not03_without_an_active_sa_the_owner_is_notified_as_owner(world: World) -> None:
    booking = await world.job(world.a)
    await world.set_membership_active(world.a.shop, world.a.advisor, active=False)
    await world.set_user_active(world.a.advisor_2, active=False)

    await publish(
        world.db,
        applied(booking, A.APPROVE_ESTIMATE, actor=world.ayesha, actor_role=R.CUSTOMER),
        applied(booking, A.PASS_QC, actor=world.a.inspector, actor_role=R.QC_INSPECTOR),
    )

    rows = await world.notifications(booking)
    assert summary(rows) == {
        (world.a.owner.id, R.OWNER, T.ESTIMATE_APPROVED),
        (world.a.owner.id, R.OWNER, T.QC_PASSED),
    }
    assert {row.link for row in rows} == {link(R.OWNER, booking)}


async def test_not03_a_shop_without_sas_notifies_its_owner(world: World) -> None:
    booking = await world.booking(world.c, status=BookingStatus.PENDING)

    await publish(world.db, applied(booking, A.CREATE, actor=world.ayesha, actor_role=R.CUSTOMER))

    [row] = await world.notifications(booking)
    assert (row.recipient_user_id, row.recipient_role) == (world.a.owner.id, R.OWNER)
    assert row.link == f"/pos/shops/{world.c.id}/bookings/{booking.id}"


async def test_customer_cancel_without_active_sas_falls_back_to_the_owner(world: World) -> None:
    booking = await world.job(world.a)
    for advisor in (world.a.advisor, world.a.advisor_2):
        await world.set_membership_active(world.a.shop, advisor, active=False)

    await publish(world.db, applied(booking, A.CANCEL, actor=world.ayesha, actor_role=R.CUSTOMER))

    rows = await world.notifications(booking)
    assert summary(rows) == {
        (world.a.owner.id, R.OWNER, T.BOOKING_CANCELLED),
        (world.a.technician.id, R.TECHNICIAN, T.BOOKING_CANCELLED),
        (world.a.parts.id, R.PARTS_PERSON, T.BOOKING_CANCELLED),
    }


async def test_qc_requested_reaches_active_inspectors_only_with_no_fallback(world: World) -> None:
    first = await world.job(world.a)
    second = await world.job(world.a)
    await world.set_membership_active(world.a.shop, world.a.inspector_2, active=False)

    await publish(
        world.db, applied(first, A.SEND_TO_QC, actor=world.a.technician, actor_role=R.TECHNICIAN)
    )
    await world.set_user_active(world.a.inspector, active=False)
    await publish(
        world.db, applied(second, A.SEND_TO_QC, actor=world.a.technician, actor_role=R.TECHNICIAN)
    )

    assert summary(await world.notifications(first)) == {
        (world.a.inspector.id, R.QC_INSPECTOR, T.QC_REQUESTED)
    }
    assert await world.notifications(second) == []  # nobody: no SA or Owner fallback


@pytest.mark.parametrize(
    "deactivate", ["membership", "account"], ids=["inactive-membership", "inactive-account"]
)
async def test_d9_a_deactivated_assignee_gets_nothing(world: World, deactivate: str) -> None:
    booking = await world.job(world.a)
    if deactivate == "membership":
        await world.set_membership_active(world.a.shop, world.a.technician, active=False)
    else:
        await world.set_user_active(world.a.technician, active=False)

    await publish(
        world.db,
        applied(booking, A.ALLOCATE_PARTS, actor=world.a.parts, actor_role=R.PARTS_PERSON),
        applied(booking, A.FAIL_QC, actor=world.a.inspector, actor_role=R.QC_INSPECTOR),
        applied(booking, A.CANCEL, actor=world.ayesha, actor_role=R.CUSTOMER),
    )

    rows = await world.notifications(booking)
    assert world.a.technician.id not in {row.recipient_user_id for row in rows}
    assert summary(rows) == {
        (world.a.advisor.id, R.SERVICE_ADVISOR, T.BOOKING_CANCELLED),
        (world.a.advisor_2.id, R.SERVICE_ADVISOR, T.BOOKING_CANCELLED),
        (world.a.parts.id, R.PARTS_PERSON, T.BOOKING_CANCELLED),
    }


async def test_a_member_of_another_shop_is_not_a_named_recipient(world: World) -> None:
    """The event names a user who is no member of the booking's shop: no row (NOT-04)."""
    booking = await world.job(world.a)

    await publish(
        world.db,
        applied(
            booking,
            A.REASSIGN_TECHNICIAN,
            actor=world.a.advisor,
            actor_role=R.SERVICE_ADVISOR,
            technician_user_id=world.b.technician.id,
        ),
    )

    assert await world.notifications(booking) == []


async def test_customer_cancel_skips_assignees_that_are_not_set(world: World) -> None:
    booking = await world.booking(world.a, status=BookingStatus.CONFIRMED)

    await publish(world.db, applied(booking, A.CANCEL, actor=world.ayesha, actor_role=R.CUSTOMER))

    assert summary(await world.notifications(booking)) == {
        (world.a.advisor.id, R.SERVICE_ADVISOR, T.BOOKING_CANCELLED),
        (world.a.advisor_2.id, R.SERVICE_ADVISOR, T.BOOKING_CANCELLED),
    }


async def test_d91_a_user_who_qualifies_twice_keeps_the_first_role(world: World) -> None:
    """Imran is re-roled to SA while still the booking's technician: one row, as SA."""
    booking = await world.job(world.a)
    await world.set_membership_role(
        world.a.shop, world.a.technician, MembershipRole.SERVICE_ADVISOR
    )

    await publish(world.db, applied(booking, A.CANCEL, actor=world.ayesha, actor_role=R.CUSTOMER))

    rows = await world.notifications(booking)
    imran = [row for row in rows if row.recipient_user_id == world.a.technician.id]
    assert len(imran) == 1
    assert imran[0].recipient_role == R.SERVICE_ADVISOR
    assert imran[0].link == link(R.SERVICE_ADVISOR, booking)
    assert len(rows) == 4  # Bilal, Kashif, Imran (as SA), Usman


async def test_d91_the_actor_is_not_excluded(world: World) -> None:
    """Bilal (an SA of shop A) books his own car there: recipients are applied literally."""
    bilal, kashif = world.a.advisor, world.a.advisor_2
    booking = await world.booking(world.a, customer=bilal, status=BookingStatus.PENDING)

    await publish(world.db, applied(booking, A.CREATE, actor=bilal, actor_role=R.CUSTOMER))
    await publish(world.db, applied(booking, A.CONFIRM, actor=kashif, actor_role=R.SERVICE_ADVISOR))
    await publish(world.db, applied(booking, A.CANCEL, actor=bilal, actor_role=R.CUSTOMER))

    rows = await world.notifications(booking)
    assert summary(rows) == {
        (bilal.id, R.SERVICE_ADVISOR, T.BOOKING_CREATED),
        (kashif.id, R.SERVICE_ADVISOR, T.BOOKING_CREATED),
        (bilal.id, R.CUSTOMER, T.BOOKING_CONFIRMED),
        (bilal.id, R.SERVICE_ADVISOR, T.BOOKING_CANCELLED),
        (kashif.id, R.SERVICE_ADVISOR, T.BOOKING_CANCELLED),
    }
    confirmed = next(row for row in rows if row.type == T.BOOKING_CONFIRMED)
    assert confirmed.link == f"/bookings/{booking.id}"
    cancelled = next(row for row in rows if row.type == T.BOOKING_CANCELLED)
    assert cancelled.body == "Bilal cancelled the booking."


async def test_staff_of_one_shop_are_plain_customers_elsewhere(world: World) -> None:
    """Imran (technician at A) books at shop B: B's SAs are notified, never A's staff."""
    booking = await world.booking(
        world.b, customer=world.a.technician, status=BookingStatus.PENDING
    )

    await publish(
        world.db, applied(booking, A.CREATE, actor=world.a.technician, actor_role=R.CUSTOMER)
    )

    assert summary(await world.notifications(booking)) == {
        (world.b.advisor.id, R.SERVICE_ADVISOR, T.BOOKING_CREATED),
        (world.b.advisor_2.id, R.SERVICE_ADVISOR, T.BOOKING_CREATED),
    }


# --- Texts ----------------------------------------------------------------------------------------


async def test_texts_are_composed_from_the_event_and_live_names(world: World) -> None:
    booking = await world.job(world.a)
    estimate = {"estimate_id": str(uuid.uuid4()), "version": 2, "grand_total": "16100.00"}
    ref = booking.reference
    await publish(
        world.db,
        applied(booking, A.CREATE, actor=world.ayesha, actor_role=R.CUSTOMER),
        applied(booking, A.ASSIGN_TECHNICIAN, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR),
        applied(
            booking,
            A.SUBMIT_ESTIMATE,
            actor=world.a.technician,
            actor_role=R.TECHNICIAN,
            metadata={**estimate, "version": 1, "grand_total": "16600.00"},
        ),
        applied(
            booking,
            A.SEND_ESTIMATE,
            actor=world.a.advisor,
            actor_role=R.SERVICE_ADVISOR,
            metadata=estimate,
        ),
        applied(
            booking,
            A.APPROVE_ESTIMATE,
            actor=world.ayesha,
            actor_role=R.CUSTOMER,
            metadata=estimate,
        ),
        applied(
            booking, A.REJECT_ESTIMATE, actor=world.ayesha, actor_role=R.CUSTOMER, metadata=estimate
        ),
        applied(
            booking,
            A.RETURN_TO_TECHNICIAN,
            actor=world.a.advisor,
            actor_role=R.SERVICE_ADVISOR,
            note="Use the cheaper coil.",
            metadata={"estimate_id": estimate["estimate_id"], "version": 3},
        ),
        applied(
            booking,
            A.FAIL_QC,
            actor=world.a.inspector,
            actor_role=R.QC_INSPECTOR,
            note="Oil leak at filter",
        ),
        applied(booking, A.NOTIFY_READY, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR),
        applied(
            booking,
            A.DECLINE,
            actor=world.a.advisor,
            actor_role=R.SERVICE_ADVISOR,
            note="We cannot take this car",
        ),
    )
    texts = {
        (row.type, row.recipient_user_id): (row.title, row.body)
        for row in await world.notifications(booking)
    }
    bilal, imran, ayesha = world.a.advisor.id, world.a.technician.id, world.ayesha.id
    assert texts[(T.BOOKING_CREATED, bilal)] == (
        f"New booking {ref}",
        "Ayesha Khan booked a visit at Lahore Auto Care.",
    )
    assert texts[(T.TECHNICIAN_ASSIGNED, imran)] == (
        f"New job {ref}",
        "Bilal assigned this booking to you.",
    )
    assert texts[(T.ESTIMATE_SUBMITTED, bilal)] == (
        f"Estimate to review — {ref}",
        "Imran submitted estimate v1 (PKR 16,600).",
    )
    assert texts[(T.ESTIMATE_SENT, ayesha)] == (
        f"Your estimate is ready — {ref}",
        "Lahore Auto Care sent estimate v2: PKR 16,100. Review and approve it in BayFlow.",
    )
    assert texts[(T.ESTIMATE_APPROVED, bilal)] == (
        f"Estimate approved — {ref}",
        "Ayesha Khan approved estimate v2 (PKR 16,100).",
    )
    assert texts[(T.ESTIMATE_REJECTED, bilal)] == (
        f"Estimate declined — {ref}",
        "Ayesha Khan declined estimate v2. Reason: none given.",
    )
    assert texts[(T.ESTIMATE_RETURNED, imran)] == (
        f"Estimate returned — {ref}",
        "Bilal returned the estimate to you. Use the cheaper coil.",
    )
    assert texts[(T.QC_FAILED, imran)] == (  # D92: the note is the QC issue title
        f"QC failed — {ref}",
        "Sara returned the job with an issue to fix. Oil leak at filter",
    )
    assert texts[(T.VEHICLE_READY, ayesha)] == (
        "Your vehicle is ready for pick-up",
        f"Booking {ref} at Lahore Auto Care is ready for pick-up.",
    )
    assert texts[(T.BOOKING_CANCELLED, ayesha)] == (
        f"Booking cancelled — {ref}",
        "Lahore Auto Care cancelled your booking. Reason: We cannot take this car.",
    )


async def test_not15_a_2000_character_cancel_reason_is_cut_to_the_body_size(world: World) -> None:
    booking = await world.job(world.a)

    await publish(
        world.db,
        applied(
            booking, A.CANCEL, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR, note="x" * 2000
        ),
    )

    [row] = await world.notifications(booking)
    assert len(row.body) == 1000
    assert row.body.startswith("Lahore Auto Care cancelled your booking. Reason: xxx")
    assert row.body.endswith("x…")


async def test_missing_metadata_never_fails_the_action(world: World) -> None:
    booking = await world.job(world.a)

    await publish(
        world.db,
        applied(
            booking,
            A.SEND_ESTIMATE,
            actor=world.a.advisor,
            actor_role=R.SERVICE_ADVISOR,
            metadata={"version": "not-a-number", "grand_total": None},
        ),
    )

    [row] = await world.notifications(booking)
    assert row.body == "Lahore Auto Care sent the estimate. Review and approve it in BayFlow."


# --- One statement, the action's transaction ------------------------------------------------------


@contextmanager
def captured_statements(db: Database) -> Iterator[list[str]]:
    statements: list[str] = []

    def capture(*args: Any) -> None:
        statements.append(args[2])

    engine = db.engine.sync_engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", capture)


@pytest.mark.parametrize(
    ("action", "actor", "role", "rows"),
    [
        (A.SEND_TO_QC, "a.technician", R.TECHNICIAN, 2),
        (A.CANCEL, "ayesha", R.CUSTOMER, 4),
        (A.CREATE, "ayesha", R.CUSTOMER, 2),
    ],
)
async def test_one_insert_statement_per_action(
    world: World, action: BookingAction, actor: str, role: ActorRole, rows: int
) -> None:
    booking = await world.job(world.a)

    with captured_statements(world.db) as statements:
        await publish(world.db, applied(booking, action, actor=who(world, actor), actor_role=role))

    inserts = [s for s in statements if s.lstrip().upper().startswith("INSERT INTO NOTIFICATIONS")]
    assert len(inserts) == 1
    assert len(await world.notifications(booking)) == rows


async def test_rows_join_the_action_transaction_and_its_pending_writes(world: World) -> None:
    """The booking a `CREATE` inserts is still unflushed when the handler runs: the rows' composite
    foreign key must see it (pending ORM writes are flushed before the INSERT)."""
    vehicle = await world.vehicle_for(world.ayesha)
    async with world.db.sessionmaker() as session:
        uow = UnitOfWork(session, notifications_bus())
        booking = Booking(
            shop_id=world.a.id,
            reference="BF-PEND01",
            customer_user_id=world.ayesha.id,
            vehicle_id=vehicle.id,
            slot_start=START,
            slot_end=START + timedelta(hours=1),
            status=BookingStatus.PENDING,
            version=1,
        )
        session.add(booking)  # not flushed
        await uow.publish(applied(booking, A.CREATE, actor=world.ayesha, actor_role=R.CUSTOMER))
        await uow.commit()

    assert len(await world.notifications(booking)) == 2


async def test_not07_rows_roll_back_with_the_action(world: World) -> None:
    booking = await world.job(world.a)
    async with world.db.sessionmaker() as session:
        uow = UnitOfWork(session, notifications_bus())
        await session.execute(update(Booking).where(Booking.id == booking.id).values(version=9))
        await uow.publish(applied(booking, A.CREATE, actor=world.ayesha, actor_role=R.CUSTOMER))
        assert await session.scalar(select(func.count()).select_from(Notification)) == 2
        await uow.rollback()

    assert await world.notifications(booking) == []


async def test_not07_a_later_failure_in_the_action_leaves_no_rows(world: World) -> None:
    booking = await world.job(world.a)
    bus = notifications_bus()

    async def fails_after_notifications(event: BookingActionApplied, uow: UnitOfWork) -> None:
        msg = "a later step of the action failed"
        raise RuntimeError(msg)

    bus.subscribe(BookingActionApplied, fails_after_notifications)

    with pytest.raises(RuntimeError, match="later step"):
        await publish(
            world.db,
            applied(booking, A.SEND_TO_QC, actor=world.a.technician, actor_role=R.TECHNICIAN),
            bus=bus,
        )

    assert await world.notifications(booking) == []


async def test_not07_a_notification_failure_rolls_the_whole_action_back(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No partial success: when writing the rows fails, the booking change is undone too."""
    booking = await world.job(world.a)

    async def broken(*args: object, **kwargs: object) -> object:
        msg = "shops read failed"
        raise ConnectionError(msg)

    monkeypatch.setattr(shops_service, "get_shop_briefs", broken)

    async def action() -> None:
        async with world.db.sessionmaker() as session:
            uow = UnitOfWork(session, notifications_bus())
            await session.execute(
                update(Booking).where(Booking.id == booking.id).values(version=42)
            )
            await uow.publish(
                applied(
                    booking, A.NOTIFY_READY, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR
                )
            )
            await uow.commit()

    with pytest.raises(ConnectionError):
        await action()

    async with world.db.sessionmaker() as session:
        row = await session.get(Booking, booking.id)
        assert row is not None
        assert row.version == booking.version
    assert await world.notifications(booking) == []


async def test_without_app_state_rows_are_written_and_nothing_is_queued(world: World) -> None:
    """The seed and scripts build their unit of work without `app_state` (D90): quiet."""
    booking = await world.job(world.a)
    async with world.db.sessionmaker() as session:
        uow = UnitOfWork(session, notifications_bus(), app_state=None)
        await uow.publish(
            applied(booking, A.NOTIFY_READY, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR)
        )
        await uow.commit()
        assert pending_after_commit_tasks() == 0

    assert len(await world.notifications(booking)) == 1


async def test_actions_without_a_type_write_nothing(world: World) -> None:
    booking = await world.job(world.a)
    bus: EventBus = notifications_bus()
    quiet = [
        A.START_INSPECTION,
        A.EDIT_ESTIMATE,
        A.REVISE_ESTIMATE,
        A.ORDER_PARTS,
        A.MARK_PARTS_READY,
        A.RECEIVE_PARTS,
        A.START_REPAIR,
        A.PICK_QC,
        A.COMPLETE,
    ]

    with captured_statements(world.db) as statements:
        await publish(
            world.db,
            *(
                applied(booking, action, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR)
                for action in quiet
            ),
            bus=bus,
        )

    assert await world.notifications(booking) == []
    assert not [s for s in statements if "notifications" in s.lower()]


# --- NOT-04 across the worked example (spec 08 trace) ---------------------------------------------


async def test_not04_worked_example_recipients(world: World) -> None:
    """Spec 08's trace with the brief's cast (Bilal the only SA): the 13 notifications reach
    exactly the listed people, and every recipient is the customer or an active member."""
    await world.set_membership_active(world.a.shop, world.a.advisor_2, active=False)
    a = world.a
    bilal, imran, usman, sara, hina = a.advisor, a.technician, a.parts, a.inspector, a.inspector_2
    ahmed = world.ahmed
    booking = await world.booking(a, customer=ahmed, status=BookingStatus.PENDING)

    def step(action: BookingAction, actor: User, role: ActorRole, **extra: Any) -> None:
        steps.append(applied(booking, action, actor=actor, actor_role=role, **extra))

    steps: list[BookingActionApplied] = []
    step(A.CREATE, ahmed, R.CUSTOMER, technician_user_id=None, parts_person_user_id=None)
    step(A.CONFIRM, bilal, R.SERVICE_ADVISOR, technician_user_id=None, parts_person_user_id=None)
    step(
        A.ASSIGN_TECHNICIAN,
        bilal,
        R.SERVICE_ADVISOR,
        technician_user_id=imran.id,
        parts_person_user_id=None,
    )
    step(
        A.START_INSPECTION,
        imran,
        R.TECHNICIAN,
        technician_user_id=imran.id,
        parts_person_user_id=None,
    )
    step(
        A.SUBMIT_ESTIMATE,
        imran,
        R.TECHNICIAN,
        technician_user_id=imran.id,
        parts_person_user_id=None,
        metadata={"version": 1, "grand_total": "16600.00"},
    )
    step(
        A.EDIT_ESTIMATE,
        bilal,
        R.SERVICE_ADVISOR,
        technician_user_id=imran.id,
        parts_person_user_id=None,
    )
    step(
        A.SEND_ESTIMATE,
        bilal,
        R.SERVICE_ADVISOR,
        technician_user_id=imran.id,
        parts_person_user_id=None,
        metadata={"version": 2, "grand_total": "16100.00"},
    )
    step(
        A.APPROVE_ESTIMATE,
        ahmed,
        R.CUSTOMER,
        technician_user_id=imran.id,
        parts_person_user_id=None,
        metadata={"version": 2, "grand_total": "16100.00"},
    )
    for action, actor, role in [
        (A.ASSIGN_PARTS_PERSON, bilal, R.SERVICE_ADVISOR),
        (A.ORDER_PARTS, usman, R.PARTS_PERSON),
        (A.RECEIVE_PARTS, usman, R.PARTS_PERSON),
        (A.ALLOCATE_PARTS, usman, R.PARTS_PERSON),
        (A.START_REPAIR, imran, R.TECHNICIAN),
        (A.SEND_TO_QC, imran, R.TECHNICIAN),
        (A.PICK_QC, sara, R.QC_INSPECTOR),
    ]:
        step(action, actor, role, technician_user_id=imran.id, parts_person_user_id=usman.id)
    step(
        A.FAIL_QC,
        sara,
        R.QC_INSPECTOR,
        technician_user_id=imran.id,
        parts_person_user_id=usman.id,
        note="Oil leak at filter",
    )
    for action, actor, role in [
        (A.SEND_TO_QC, imran, R.TECHNICIAN),
        (A.PICK_QC, sara, R.QC_INSPECTOR),
        (A.PASS_QC, sara, R.QC_INSPECTOR),
        (A.NOTIFY_READY, bilal, R.SERVICE_ADVISOR),
        (A.COMPLETE, ahmed, R.CUSTOMER),
    ]:
        step(action, actor, role, technician_user_id=imran.id, parts_person_user_id=usman.id)
    for action_event in steps:  # one transaction per action, in the trace's order
        await publish(world.db, action_event)

    rows = await world.notifications(booking)
    trace = [(row.type, row.recipient_user_id) for row in rows]
    assert trace == [
        (T.BOOKING_CREATED, bilal.id),
        (T.BOOKING_CONFIRMED, ahmed.id),
        (T.TECHNICIAN_ASSIGNED, imran.id),
        (T.ESTIMATE_SUBMITTED, bilal.id),
        (T.ESTIMATE_SENT, ahmed.id),
        (T.ESTIMATE_APPROVED, bilal.id),
        (T.PARTS_NEEDED, usman.id),
        (T.PARTS_READY, imran.id),
        *sorted([(T.QC_REQUESTED, sara.id), (T.QC_REQUESTED, hina.id)], key=lambda r: r[1]),
        (T.QC_FAILED, imran.id),
        *sorted([(T.QC_REQUESTED, sara.id), (T.QC_REQUESTED, hina.id)], key=lambda r: r[1]),
        (T.QC_PASSED, bilal.id),
        (T.VEHICLE_READY, ahmed.id),
    ]
    async with world.db.sessionmaker() as session:
        problems = await invariant_violations(session)
    assert not [problem for problem in problems if problem.startswith("NOT-04")]

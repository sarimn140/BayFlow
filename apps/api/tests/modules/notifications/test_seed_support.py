"""Seed support (spec 11 "Notifications after seeding"): `list_for_bookings` and `mark_read_bulk`.

The seed writes rows through the same handlers (without `app_state`, so nothing is pushed), then
lists them per booking with their addressee and marks most of them read at `run_now` (D63).
"""

import uuid
from datetime import timedelta

import pytest

from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationRead, NotificationRecord
from app.shared.clock import SimulatedClock
from app.shared.enums import ActorRole, BookingAction, BookingStatus
from app.shared.event_bus import EventBus
from app.shared.uow import UnitOfWork
from tests.modules.notifications.support import World, applied, publish

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("booking_reads")]

A = BookingAction
R = ActorRole


async def seeded(world: World) -> tuple[list[uuid.UUID], uuid.UUID]:
    """Two Lahore bookings with rows, and one Clifton booking with rows."""
    lahore = [await world.job(world.a), await world.job(world.a)]
    for booking in lahore:
        await publish(
            world.db,
            applied(booking, A.CREATE, actor=world.ayesha, actor_role=R.CUSTOMER),
        )
        await publish(
            world.db,
            applied(booking, A.CONFIRM, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR),
        )
    clifton = await world.booking(world.b, status=BookingStatus.PENDING)
    await publish(world.db, applied(clifton, A.CREATE, actor=world.ayesha, actor_role=R.CUSTOMER))
    return [booking.id for booking in lahore], clifton.id


async def test_list_for_bookings_returns_the_rows_of_those_bookings_of_that_shop(
    world: World,
) -> None:
    lahore_ids, clifton_id = await seeded(world)

    async with world.db.sessionmaker() as session:
        records = await service.list_for_bookings(
            session, shop_id=world.a.id, booking_ids=[*lahore_ids, clifton_id, uuid.uuid4()]
        )
        none = await service.list_for_bookings(session, shop_id=world.a.id, booking_ids=[])

    assert none == []
    assert {record.booking_id for record in records} == set(lahore_ids)  # shop-scoped (D20)
    assert len(records) == 6  # per booking: 2 SAs (BOOKING_CREATED) + Ayesha (CONFIRMED)
    order = [(record.created_at, record.id) for record in records]
    assert order == sorted(order)  # oldest first
    for record in records:
        assert isinstance(record, NotificationRecord)
        assert isinstance(record, NotificationRead)  # the spec's return type
        assert record.shop_name == "Lahore Auto Care"
        assert record.booking_reference is not None
        assert record.booking_reference.startswith("BF-")
    assert {record.recipient_user_id for record in records} == {
        world.a.advisor.id,
        world.a.advisor_2.id,
        world.ayesha.id,
    }


async def test_mark_read_bulk_marks_only_that_users_rows(
    world: World, clock: SimulatedClock
) -> None:
    lahore_ids, _ = await seeded(world)
    async with world.db.sessionmaker() as session:
        records = await service.list_for_bookings(
            session, shop_id=world.a.id, booking_ids=lahore_ids
        )
    bilal = [record.id for record in records if record.recipient_user_id == world.a.advisor.id]
    kashif = [r.id for r in records if r.recipient_user_id == world.a.advisor_2.id]
    clock.advance(timedelta(hours=2))
    run_now = clock.now()

    async with world.db.sessionmaker() as session:
        uow = UnitOfWork(session, EventBus())
        changed = await service.mark_read_bulk(
            uow, user_id=world.a.advisor.id, notification_ids=[*bilal, *kashif, uuid.uuid4()]
        )
    async with world.db.sessionmaker() as session:
        again = await service.mark_read_bulk(
            UnitOfWork(session, EventBus()), user_id=world.a.advisor.id, notification_ids=bilal
        )
    async with world.db.sessionmaker() as session:
        nothing = await service.mark_read_bulk(
            UnitOfWork(session, EventBus()), user_id=world.a.advisor.id, notification_ids=[]
        )

    assert (changed, again, nothing) == (2, 0, 0)
    rows = {row.id: row for row in await world.notifications()}
    assert all(rows[notification_id].read_at == run_now for notification_id in bilal)
    assert all(rows[notification_id].read_at is None for notification_id in kashif)  # ignored

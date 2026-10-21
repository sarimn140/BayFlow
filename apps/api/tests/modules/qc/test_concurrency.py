"""QC-17 under a real race: two transactions open a round for the same booking at once.

The booking lock and status check of the state machine normally decide "first pick wins"
(SM-06, a bookings test). This proves the database backstop behind it (D30, spec 02 §7.5):
`uq_qc_inspections_one_open_per_booking` makes the second insert wait for the first transaction;
when the first commits, the second is refused with 409 `ALREADY_PICKED`; when the first rolls
back, the second wins. The race is made deterministic by waiting until PostgreSQL reports the
second transaction blocked on a lock (spec 12 §3.5).
"""

import asyncio
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.core.errors import AlreadyPicked
from app.modules.identity.models import User
from app.modules.qc import service as qc
from tests.modules.qc.support import BookingsStandIn, QcWorld, uow_for

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

LOCK_WAITERS = text(
    "SELECT count(*) FROM pg_stat_activity "
    "WHERE datname = current_database() AND wait_event_type = 'Lock' "
    "AND pid <> pg_backend_pid()"
)


async def wait_for_lock_waiters(db: Database, count: int, timeout_s: float = 5.0) -> None:
    async with asyncio.timeout(timeout_s):
        while True:
            async with db.engine.connect() as connection:
                waiting = (await connection.execute(LOCK_WAITERS)).scalar_one()
            if waiting >= count:
                return
            await asyncio.sleep(0.02)


@dataclass
class Race:
    booking_id: uuid.UUID
    first_id: uuid.UUID
    second: asyncio.Task[uuid.UUID]


async def race(world: QcWorld, bookings: BookingsStandIn, *, first_commits: bool) -> Race:
    """Sara's pick holds an uncommitted round while Hina's pick of the same booking waits."""
    booking = await world.booking(world.a)
    await bookings.send_to_qc(booking)
    now = world.clock.now()

    async def open_round(session: AsyncSession, inspector: User) -> uuid.UUID:
        return await qc.open_inspection(
            uow_for(session),
            shop_id=world.a.id,
            booking_id=booking.id,
            inspector_user_id=inspector.id,
            now=now,
        )

    async def second_pick() -> uuid.UUID:
        async with world.db.sessionmaker() as second:
            inspection_id = await open_round(second, world.a.inspector_2)
            await second.commit()
            return inspection_id

    async with world.db.sessionmaker() as first:
        first_id = await open_round(first, world.a.inspector)  # inserted, not yet committed
        task = asyncio.create_task(second_pick())
        await wait_for_lock_waiters(world.db, 1)  # the second insert waits on the first's row
        if first_commits:
            await first.commit()
        else:
            await first.rollback()
    return Race(booking.id, first_id, task)


async def test_qc17_concurrent_picks_one_round_wins_the_other_is_already_picked(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    outcome = await race(world, bookings, first_commits=True)
    with pytest.raises(AlreadyPicked):
        await outcome.second
    async with world.db.sessionmaker() as session:
        history = await qc.list_booking_qc_history(
            session, shop_id=world.a.id, booking_id=outcome.booking_id
        )
    assert [(item.id, item.inspector.user_id) for item in history] == [
        (outcome.first_id, world.a.inspector.id)
    ]


async def test_when_the_first_pick_rolls_back_the_waiting_pick_wins(
    world: QcWorld, bookings: BookingsStandIn
) -> None:
    outcome = await race(world, bookings, first_commits=False)
    second_id = await outcome.second
    async with world.db.sessionmaker() as session:
        history = await qc.list_booking_qc_history(
            session, shop_id=world.a.id, booking_id=outcome.booking_id
        )
    assert [(item.id, item.inspector.user_id) for item in history] == [
        (second_id, world.a.inspector_2.id)
    ]

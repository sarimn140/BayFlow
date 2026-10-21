"""Concurrent estimate edits (D30; `modules/estimates.md` §11; spec 02 §7.5; spec 12 §3.5).

Under the booking row lock that every bookings action takes first, two desk edits of the same
`SUBMITTED` version serialise: exactly one creates the new version and the other updates it in
place - last write wins on the draft. Without that lock (a buggy caller) the partial unique
indexes still refuse a second new version, and the violation maps to 409 `CONCURRENT_UPDATE`.
Both races are made deterministic with a lock gate instead of hoping two tasks overlap."""

import asyncio
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.database import Database
from app.core.errors import ErrorCode
from app.modules.estimates import service
from app.modules.estimates.schemas import EstimateEdit, EstimateLineWrite
from app.shared.enums import BookingStatus, EstimateStatus
from app.shared.repository import error_code_for
from tests.modules.estimates.support import (
    World,
    assert_estimate_invariants,
    at,
    edit,
    insert_version,
    lines_of,
    lock_booking,
    new_uow,
    versions_of,
    wait_for_lock_waiters,
    worked_example_lines,
    worked_example_v1,
)

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

ESTIMATE_REVIEW = BookingStatus.ESTIMATE_REVIEW


async def test_two_desk_edits_under_the_booking_lock_create_one_version(
    db: Database, world: World
) -> None:
    """D30: one new version only; the edit that ran second updated it in place (last write
    wins); the database is consistent (EST-16)."""
    await insert_version(
        db, world, version=1, status=EstimateStatus.SUBMITTED, lines=worked_example_v1(world)
    )
    bilal_lines = worked_example_lines(world, labour="3500")
    owner_lines = worked_example_lines(world, labour="3000")

    async def desk_edit(
        actor: uuid.UUID, lines: list[EstimateLineWrite], minute: int
    ) -> EstimateEdit:
        return await edit(
            db, world, status=ESTIMATE_REVIEW, actor=actor, lines=lines, now=at(minute)
        )

    async with db.sessionmaker() as gate:
        await lock_booking(gate, world.booking_id)
        bilal = asyncio.create_task(desk_edit(world.sa_id, bilal_lines, 3))
        owner = asyncio.create_task(desk_edit(world.owner_id, owner_lines, 4))
        await wait_for_lock_waiters(db, 2)
        await gate.commit()  # open the gate: both edits now run one after the other
    results = {"bilal": await bilal, "owner": await owner}

    created = [name for name, result in results.items() if result.created_new_version]
    assert len(created) == 1
    [later] = [name for name in results if name not in created]
    versions = await versions_of(db, world.booking_id)
    assert [(v.version, v.status) for v in versions] == [
        (1, EstimateStatus.SUPERSEDED),
        (2, EstimateStatus.DRAFT),
    ]
    assert results["bilal"].estimate.id == results["owner"].estimate.id == versions[1].id
    expected_labour = {"bilal": "3500.00", "owner": "3000.00"}[later]
    assert str(versions[1].labour_total) == expected_labour
    assert str((await lines_of(db, versions[1].id))[3].unit_price) == expected_labour
    author = world.sa_id if created == ["bilal"] else world.owner_id
    assert versions[1].created_by_user_id == author
    await assert_estimate_invariants(db, world.booking_id)


async def test_without_the_booking_lock_the_database_refuses_a_second_new_version(
    db: Database, world: World
) -> None:
    """Spec 02 §7.5 backstop: two unlocked writers both decide "new version"; the second is
    refused by `uq_estimates_*` (mapped to 409 `CONCURRENT_UPDATE`), never a duplicate v2."""
    await insert_version(
        db, world, version=1, status=EstimateStatus.SUBMITTED, lines=worked_example_v1(world)
    )
    first_flushed = asyncio.Event()
    release_first = asyncio.Event()

    async def unlocked_edit(
        actor: uuid.UUID, labour: str, minute: int, *, hold: bool
    ) -> EstimateEdit:
        async with db.sessionmaker() as session:
            uow = new_uow(session)
            result = await service.replace_lines(
                uow,
                shop_id=world.shop_id,
                booking_id=world.booking_id,
                booking_status=ESTIMATE_REVIEW,
                actor_user_id=actor,
                lines=worked_example_lines(world, labour=labour),
                now=at(minute),
            )
            if hold:
                first_flushed.set()
                await release_first.wait()
            await uow.commit()
            return result

    first = asyncio.create_task(unlocked_edit(world.sa_id, "3500", 3, hold=True))
    await first_flushed.wait()  # v1 superseded and v2 inserted, not committed yet
    second = asyncio.create_task(unlocked_edit(world.owner_id, "3000", 4, hold=False))
    await wait_for_lock_waiters(db, 1)  # the second writer waits on v1's row lock
    release_first.set()
    winner = await first
    with pytest.raises(IntegrityError) as caught:
        await second
    assert error_code_for(caught.value) is ErrorCode.CONCURRENT_UPDATE
    assert winner.created_new_version is True
    versions = await versions_of(db, world.booking_id)
    assert [(v.version, v.status, str(v.labour_total)) for v in versions] == [
        (1, EstimateStatus.SUPERSEDED, "4000.00"),
        (2, EstimateStatus.DRAFT, "3500.00"),
    ]
    await assert_estimate_invariants(db, world.booking_id)

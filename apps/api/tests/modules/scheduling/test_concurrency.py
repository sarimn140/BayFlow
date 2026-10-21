"""Races on slots and on the shop row, proven with the lock gate (spec 12 §3.5; D30, D37).

SM-07 ★ (scheduling half: the last place of a slot, gated and as an ungated burst on a counter row
that does not exist yet), CON-03 (two cancellations in one slot) and CON-05 (shops half: a grid
change and a booking serialise on the shop row, `FOR UPDATE` vs `FOR SHARE`).
"""

import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.core.database import Database
from app.modules.shops.events import ShopGridChanging
from app.shared.clock import SimulatedClock
from app.shared.uow import UnitOfWork
from tests.lockgate import hold_row_lock, wait_for_lock_waiters
from tests.modules.identity.builders import bearer
from tests.modules.scheduling.helpers import book, booked_count, free
from tests.modules.scheduling.lockgate import hold_shop_share_lock
from tests.modules.shops.builders import make_shop

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

FRIDAY_1000_PKT = datetime(2026, 10, 16, 5, tzinfo=UTC)


async def test_sm07_two_customers_race_for_the_last_place(
    db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db, capacity=2)
    assert await book(db, ctx.id, FRIDAY_1000_PKT) == "booked"  # one place left
    async with hold_row_lock(db, "slot_counters", shop_id=ctx.id, slot_start=FRIDAY_1000_PKT):
        racers = [asyncio.create_task(book(db, ctx.id, FRIDAY_1000_PKT)) for _ in range(2)]
        await wait_for_lock_waiters(db, 2)  # both queue on the counter row
    results = await asyncio.gather(*racers)
    assert sorted(results) == ["booked", "full"]  # exactly one 201, one 409 SLOT_FULL
    assert await booked_count(db, ctx.id, FRIDAY_1000_PKT) == 2  # = capacity, never above


async def test_sm07_an_ungated_burst_on_a_brand_new_slot(
    db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db, capacity=1)
    assert await booked_count(db, ctx.id, FRIDAY_1000_PKT) is None  # no counter row yet
    results = await asyncio.gather(*(book(db, ctx.id, FRIDAY_1000_PKT) for _ in range(6)))
    assert results.count("booked") == 1
    assert results.count("full") == 5
    assert await booked_count(db, ctx.id, FRIDAY_1000_PKT) == 1


async def test_con03_two_cancellations_in_one_slot(db: Database, clock: SimulatedClock) -> None:
    ctx = await make_shop(db, capacity=2)
    await book(db, ctx.id, FRIDAY_1000_PKT)
    await book(db, ctx.id, FRIDAY_1000_PKT)
    async with hold_row_lock(db, "slot_counters", shop_id=ctx.id, slot_start=FRIDAY_1000_PKT):
        cancellations = [asyncio.create_task(free(db, ctx.id, FRIDAY_1000_PKT)) for _ in range(2)]
        await wait_for_lock_waiters(db, 2)
    await asyncio.gather(*cancellations)
    assert await booked_count(db, ctx.id, FRIDAY_1000_PKT) == 0  # exactly 2 off, never below 0


async def test_con05_a_grid_change_waits_for_an_in_flight_booking(
    db_client: httpx.AsyncClient, db: Database, db_app: FastAPI, clock: SimulatedClock
) -> None:
    """An uncommitted booking holds the shop row `FOR SHARE`; the grid change (`FOR UPDATE`)
    waits for it, so its `ShopGridChanging` veto sees the booking once it has committed."""
    ctx = await make_shop(db)
    seen: list[ShopGridChanging] = []

    async def record(event: ShopGridChanging, uow: UnitOfWork) -> None:
        seen.append(event)

    db_app.state.event_bus.subscribe(ShopGridChanging, record)
    async with hold_shop_share_lock(db, ctx.id):
        change = asyncio.create_task(
            db_client.patch(
                f"/api/v1/shops/{ctx.id}",
                json={"slot_duration_minutes": 30},
                headers=bearer(ctx.owner.id),
            )
        )
        await wait_for_lock_waiters(db, 1)
        assert not change.done()
        assert seen == []  # nothing published while the booking holds the row
    response = await change
    assert response.status_code == 200
    assert [event.changed_fields for event in seen] == [("slot_duration_minutes",)]


async def test_con05_a_booking_waits_for_a_grid_change_in_progress(
    db: Database, clock: SimulatedClock
) -> None:
    """A grid change holds the shop row `FOR UPDATE`; booking creation's first lock (`FOR SHARE`)
    waits, then validates against whatever grid committed."""
    ctx = await make_shop(db)
    async with hold_row_lock(db, "shops", id=ctx.id):
        booking = asyncio.create_task(book(db, ctx.id, FRIDAY_1000_PKT))
        await wait_for_lock_waiters(db, 1)
        assert not booking.done()
    assert await booking == "booked"


async def test_two_bookings_never_wait_for_each_other_on_the_shop_row(
    db: Database, clock: SimulatedClock
) -> None:
    """`FOR SHARE` does not conflict with `FOR SHARE`: bookings of one shop proceed together."""
    ctx = await make_shop(db, capacity=5)
    async with hold_shop_share_lock(db, ctx.id):
        results = await asyncio.wait_for(
            asyncio.gather(*(book(db, ctx.id, FRIDAY_1000_PKT) for _ in range(3))), timeout=5
        )
    assert results == ["booked", "booked", "booked"]

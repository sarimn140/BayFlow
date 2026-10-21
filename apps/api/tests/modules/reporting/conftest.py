"""Fixtures of the reporting tests.

- `bookings_reads` (autouse): bookings' `count_by_status`, `count_open_jobs` and
  `count_day_activity` are the real functions wherever the bookings build has implemented them,
  and the plain-SQL stand-ins of `support.py` while they still raise `NotImplementedError`. The
  fixture's value says which is in use (`"real"` / `"fake"` per function).
- `world`: Shop A and Shop B with full teams (rows) and a customer, under the frozen test clock.
- `activity_reader`: a fake D86 `ShopActivityReader` for the few shops routes a test calls
  (`PATCH` shop, `PATCH` member); registered after the app wired its modules, restored after.
"""

from collections.abc import Collection, Iterator
from datetime import datetime
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.modules.bookings import service as bookings_service
from app.modules.shops import service as shops_service
from app.shared.clock import SimulatedClock
from tests.modules.reporting.support import (
    FAKE_BOOKINGS_READS,
    World,
    is_implemented,
    make_cast,
)
from tests.rows import add_rows, make_user


@pytest.fixture(autouse=True)
async def bookings_reads(db: Database, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    modes: dict[str, str] = {}
    async with db.sessionmaker() as session:
        for name, fake in FAKE_BOOKINGS_READS.items():
            if await is_implemented(name, session):
                modes[name] = "real"
            else:
                monkeypatch.setattr(bookings_service, name, fake)
                modes[name] = "fake"
    return modes


@pytest.fixture
async def world(db: Database, clock: SimulatedClock) -> World:
    a, b = await make_cast(db), await make_cast(db)
    customer = make_user(full_name="Ayesha Khan")
    await add_rows(db.sessionmaker, customer)
    return World(a=a, b=b, customer=customer)


@pytest.fixture
def api(db_client: httpx.AsyncClient) -> httpx.AsyncClient:
    return db_client


class _NoBookingsActivity:
    """A `ShopActivityReader` that reports no bookings (shops' own responses only)."""

    async def has_future_bookings(
        self, session: AsyncSession, *, shop_id: UUID, now: datetime
    ) -> bool:
        return False

    async def count_open_jobs(
        self, session: AsyncSession, *, shop_id: UUID, user_ids: Collection[UUID]
    ) -> dict[UUID, int]:
        return dict.fromkeys(user_ids, 0)


@pytest.fixture
def activity_reader(db_app: FastAPI) -> Iterator[None]:
    previous = shops_service.register_activity_reader(_NoBookingsActivity())
    yield
    shops_service.register_activity_reader(previous)

"""A fake D86 `ShopActivityReader` (bookings facts on shops responses) and its fixtures.

The real reader is bookings' `shop_activity_reader`, registered by `bookings.service.
register_ports()` when the app wires its modules (D86, D89). Until then — and in tests that need
specific facts — a fake is registered and the previous registration is restored afterwards.
"""

import uuid
from collections.abc import Collection, Iterator
from dataclasses import dataclass, field
from datetime import datetime

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.shops import service as shops_service


@dataclass
class FakeActivityReader:
    future_bookings: bool = False
    open_jobs: dict[uuid.UUID, int] = field(default_factory=dict)
    calls: list[tuple[str, uuid.UUID]] = field(default_factory=list)

    async def has_future_bookings(
        self, session: AsyncSession, *, shop_id: uuid.UUID, now: datetime
    ) -> bool:
        self.calls.append(("has_future_bookings", shop_id))
        return self.future_bookings

    async def count_open_jobs(
        self, session: AsyncSession, *, shop_id: uuid.UUID, user_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        self.calls.append(("count_open_jobs", shop_id))
        return {
            user_id: self.open_jobs[user_id] for user_id in user_ids if user_id in self.open_jobs
        }


@pytest.fixture(autouse=True)
def default_activity_reader() -> Iterator[FakeActivityReader]:
    """A port with no bookings for every test (bookings is wave 2); restored afterwards."""
    reader = FakeActivityReader()
    previous = shops_service.register_activity_reader(reader)
    yield reader
    shops_service.register_activity_reader(previous)


@pytest.fixture
def activity_reader(db_app: FastAPI) -> Iterator[FakeActivityReader]:
    """A configurable fake registered after `db_app` wired its modules, so it also wins over
    bookings' real reader once that exists."""
    reader = FakeActivityReader()
    previous = shops_service.register_activity_reader(reader)
    yield reader
    shops_service.register_activity_reader(previous)

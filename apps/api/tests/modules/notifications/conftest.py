"""Fixtures of the notifications module's DB tests (see `support.py` and `fakes.py`)."""

import pytest

from app.core.database import Database
from tests.modules.notifications.fakes import booking_reads  # noqa: F401 - fixture
from tests.modules.notifications.support import World


@pytest.fixture
async def world(db: Database) -> World:
    return await World.build(db)

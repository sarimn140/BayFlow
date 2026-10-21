"""Fixtures of the audit tests (spec 19 §3, §9 "Audit"; D95).

The app is the real one, so every catalogue event reaches the audit handlers exactly as in
production. The world and the admin are built through the services on an unsubscribed bus, so
the setup writes no audit row and every row a test sees comes from what it did.
"""

import httpx
import pytest

from app.core.database import Database
from app.modules.identity.schemas import UserRecord
from app.shared.clock import SimulatedClock
from tests.modules.admin.support import make_admin
from tests.modules.bookings.support import Desk, World, build_world
from tests.modules.identity.builders import fast_password_hashing  # noqa: F401 - autouse fixture


@pytest.fixture
async def world(db: Database, clock: SimulatedClock) -> World:
    return await build_world(db)


@pytest.fixture
def desk(db_client: httpx.AsyncClient, world: World) -> Desk:
    return Desk(db_client, world)


@pytest.fixture
async def admin(db: Database) -> UserRecord:
    return await make_admin(db)

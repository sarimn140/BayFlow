"""Fixtures of the platform admin tests (spec 19 §9).

The app under test is the real one (`create_app()` → `wire_modules()`), so the audit handlers and
the bookings read ports are registered exactly as in production. `world` is the bookings tests'
Lahore Auto Care with its full team and a second tenant; `admin` is Areeba Hashmi, a platform
admin without memberships (spec 19 §8).
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

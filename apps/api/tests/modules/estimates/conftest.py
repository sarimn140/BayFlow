"""Fixtures for the estimates service tests (all `db`: tables are truncated after each test)."""

import pytest

from app.core.database import Database
from tests.modules.estimates.support import World, build_world


@pytest.fixture
async def world(db: Database) -> World:
    return await build_world(db)

"""The single baseline migration: round trip and no drift (spec 02 §9, spec 12 §1.3)."""

from collections.abc import Awaitable, Callable

import pytest

from app.core.database import Database

pytestmark = pytest.mark.db

AlembicCli = Callable[..., Awaitable[str]]


async def test_migrations_round_trip_without_drift(db: Database, alembic_cli: AlembicCli) -> None:
    downgraded = await alembic_cli("downgrade", "base")
    assert "Running downgrade" in downgraded
    upgraded = await alembic_cli("upgrade", "head")
    assert "Running upgrade" in upgraded
    checked = await alembic_cli("check")
    assert "No new upgrade operations detected" in checked


async def test_head_is_the_single_baseline(db: Database, alembic_cli: AlembicCli) -> None:
    heads = await alembic_cli("heads")
    assert heads.strip().endswith("(head)")
    assert len([line for line in heads.splitlines() if "(head)" in line]) == 1

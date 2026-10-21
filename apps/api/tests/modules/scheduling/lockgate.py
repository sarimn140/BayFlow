"""A `FOR SHARE` gate: holds a shop row the way an in-flight booking does (D37, CON-05).

The shared `tests.lockgate.hold_row_lock` takes `FOR UPDATE`; booking creation's first lock is
`SELECT … FOR SHARE` on the shop row, which only a grid change (`FOR UPDATE`) must wait for.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text

from app.core.database import Database

SHARE_SHOP_ROW = text("SELECT id FROM shops WHERE id = :shop_id FOR SHARE")


@asynccontextmanager
async def hold_shop_share_lock(database: Database, shop_id: UUID) -> AsyncIterator[None]:
    """Hold the shop row `FOR SHARE` on a separate connection until the block exits."""
    async with database.engine.connect() as connection:
        transaction = await connection.begin()
        try:
            locked = (await connection.execute(SHARE_SHOP_ROW, {"shop_id": shop_id})).all()
            assert len(locked) == 1, "the gate must lock the shop row"
            yield
        finally:
            await transaction.rollback()

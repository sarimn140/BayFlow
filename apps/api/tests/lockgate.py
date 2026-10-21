"""Lock gate: deterministic concurrency tests (spec 12 §3.5).

Firing two requests with `asyncio.gather` and hoping they overlap proves nothing: they often run
one after the other, and naive read-then-write code then passes. The gate makes the race certain:

    async with hold_row_lock(db, "bookings", id=booking_id):
        first = asyncio.create_task(client.post(url, headers=sara))
        second = asyncio.create_task(client.post(url, headers=hina))
        await wait_for_lock_waiters(db, 2)  # both requests now queue on the booking row
    # leaving the block rolls the gate back and releases the lock
    responses = [await first, await second]  # exactly one 200 and one 409 expected

Each request uses its own connection (the test engine runs with `NullPool`), so both block on the
gate's lock. The test database also sets `lock_timeout = '5s'`, so a lock-order bug fails within
seconds instead of hanging.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import and_, column, literal, select, table, text

from app.core.database import Database

DEFAULT_TIMEOUT_SECONDS = 5.0

LOCK_WAITERS = text(
    "SELECT count(*) FROM pg_stat_activity "
    "WHERE datname = current_database() AND wait_event_type = 'Lock'"
)


@asynccontextmanager
async def hold_row_lock(db: Database, table_name: str, **key: object) -> AsyncIterator[None]:
    """Lock exactly one row (`SELECT … FOR UPDATE` by the given key columns) on a separate
    connection until the block exits; the gate's transaction is always rolled back."""
    if not key:
        msg = "hold_row_lock needs the key columns of the row, e.g. id=booking_id"
        raise ValueError(msg)
    target = table(table_name, *(column(name) for name in key))
    statement = (
        select(literal(1))
        .select_from(target)
        .where(and_(*(target.c[name] == value for name, value in key.items())))
        .with_for_update()
    )
    async with db.engine.connect() as connection:
        transaction = await connection.begin()
        try:
            locked = len((await connection.execute(statement)).all())
            if locked != 1:
                msg = f"hold_row_lock: expected one {table_name} row for {key}, locked {locked}"
                raise AssertionError(msg)
            yield
        finally:
            await transaction.rollback()


async def lock_waiters(db: Database) -> int:
    """Backends of the test database currently waiting on a lock."""
    async with db.engine.connect() as connection:
        return int((await connection.execute(LOCK_WAITERS)).scalar_one())


async def wait_for_lock_waiters(
    db: Database, count: int, *, timeout_s: float = DEFAULT_TIMEOUT_SECONDS
) -> None:
    """Wait until at least `count` backends wait on a lock; fail the test after `timeout_s`.

    The state lives in PostgreSQL (`pg_stat_activity`), so it is polled; no in-process event exists.
    """
    try:
        async with asyncio.timeout(timeout_s):
            while True:
                if await lock_waiters(db) >= count:
                    return
                await asyncio.sleep(0.02)
    except TimeoutError:
        msg = f"{count} lock waiter(s) never appeared within {timeout_s} s"
        raise AssertionError(msg) from None

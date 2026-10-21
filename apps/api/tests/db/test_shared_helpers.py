"""The shared test helpers themselves: `tests/lockgate.py` (spec 12 §3.5) and
`tests/assertions.py` (spec 12 §4.5)."""

import asyncio
import json
import uuid

import httpx
import pytest
from sqlalchemy import text

from app.core.database import Database
from tests.assertions import assert_invariants, assert_problem, invariant_violations
from tests.lockgate import hold_row_lock, lock_waiters, wait_for_lock_waiters
from tests.rows import add_rows, make_booking, make_part, make_shop, make_user, make_vehicle

# --- assert_invariants ----------------------------------------------------------------------------


async def test_every_invariant_query_runs_and_holds_on_an_empty_database(db: Database) -> None:
    async with db.sessionmaker() as session:
        assert await invariant_violations(session) == []
        await assert_invariants(session)


async def test_violations_are_reported_with_their_invariant(db: Database) -> None:
    shop = make_shop()
    customer = make_user()
    vehicle = make_vehicle(customer)
    booking = make_booking(shop, customer, vehicle)  # no CREATE event, no slot counter
    part = make_part(shop, on_hand=5)  # stock without a ledger
    await add_rows(db.sessionmaker, shop, customer, vehicle, booking, part)

    async with db.sessionmaker() as session:
        problems = "\n".join(await invariant_violations(session))
        assert "DI-1 part balance" in problems
        assert "DI-4 slot counter" in problems
        assert "DI-7 latest event" in problems
        assert "DI-2" not in problems  # nothing is reserved, so DI-2 still holds
        with pytest.raises(AssertionError, match="invariants violated"):
            await assert_invariants(session)


# --- lock gate ------------------------------------------------------------------------------------


async def test_the_gate_holds_a_competing_lock_until_it_is_left(db: Database) -> None:
    shop = make_shop()
    await add_rows(db.sessionmaker, shop)

    async def competitor() -> int:
        async with db.engine.connect() as connection, connection.begin():
            result = await connection.execute(
                text("SELECT 1 FROM shops WHERE id = :id FOR UPDATE"), {"id": shop.id}
            )
            return len(result.all())

    async with hold_row_lock(db, "shops", id=shop.id):
        task = asyncio.create_task(competitor())
        await wait_for_lock_waiters(db, 1)
        assert not task.done()
    assert await asyncio.wait_for(task, timeout=5) == 1
    assert await lock_waiters(db) == 0


async def test_the_gate_needs_exactly_one_row(db: Database) -> None:
    with pytest.raises(AssertionError, match="locked 0"):
        async with hold_row_lock(db, "shops", id=uuid.uuid4()):
            pytest.fail("the block must not run without a locked row")


async def test_the_gate_needs_a_key(db: Database) -> None:
    with pytest.raises(ValueError, match="key columns"):
        async with hold_row_lock(db, "shops"):
            pytest.fail("the block must not run without a key")


async def test_waiting_for_absent_waiters_fails_fast(db: Database) -> None:
    with pytest.raises(AssertionError, match="never appeared"):
        await wait_for_lock_waiters(db, 1, timeout_s=0.2)


# --- assert_problem -------------------------------------------------------------------------------


async def test_assert_problem_accepts_a_real_problem(client: httpx.AsyncClient) -> None:
    body = assert_problem(await client.get("/api/v1/does-not-exist"), 404, "NOT_FOUND")
    assert body["instance"] == "/api/v1/does-not-exist"


def problem(status: int, code: str, detail: str) -> httpx.Response:
    body = {
        "type": "about:blank",
        "title": "Error",
        "status": status,
        "detail": detail,
        "instance": "/api/v1/x",
        "code": code,
    }
    return httpx.Response(
        status,
        content=json.dumps(body).encode(),
        headers={"content-type": "application/problem+json"},
    )


@pytest.mark.parametrize(
    "detail",
    [
        "IntegrityError: duplicate key value",
        'Traceback (most recent call last):\n  File "app.py", line 3',
        "SELECT * FROM users",
        "asyncpg failed",
    ],
)
def test_assert_problem_refuses_leaked_internals(detail: str) -> None:
    with pytest.raises(AssertionError, match="leaks internals"):
        assert_problem(problem(500, "INTERNAL_ERROR", detail), 500, "INTERNAL_ERROR")


def test_assert_problem_checks_status_code_and_media_type() -> None:
    ok = problem(409, "CONFLICT", "Already exists.")
    assert assert_problem(ok, 409, "CONFLICT")["code"] == "CONFLICT"
    with pytest.raises(AssertionError):
        assert_problem(ok, 409, "SLOT_FULL")
    with pytest.raises(AssertionError):
        assert_problem(ok, 404, "CONFLICT")
    plain = httpx.Response(409, json={"code": "CONFLICT"})
    with pytest.raises(AssertionError):
        assert_problem(plain, 409, "CONFLICT")

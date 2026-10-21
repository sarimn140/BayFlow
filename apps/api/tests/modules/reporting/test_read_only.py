"""The reporting module only reads (`modules/reporting.md` "Concurrency and transactions"): every
statement of both routes is a query (`SELECT`, or `WITH … SELECT`) that neither writes nor locks
rows (`FOR UPDATE` / `FOR SHARE` and their variants), and the number of statements does not grow
with the data (no N+1: open jobs for the whole team in one call; the owner summary costs a fixed
number of statements per owned shop)."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from sqlalchemy import event

from app.core.database import Database
from app.modules.identity.models import User
from app.shared.enums import BookingStatus, MembershipRole, PurchaseOrderStatus
from tests.modules.reporting.support import (
    SUMMARY_URL,
    World,
    bearer,
    booking_rows,
    make_cast,
    overview_url,
    part_row,
    purchase_order_rows,
)
from tests.rows import add_rows, make_membership, make_user

pytestmark = pytest.mark.db

_UNASSIGNED = {BookingStatus.PENDING, BookingStatus.CONFIRMED}
_WRITES_OR_LOCKS = re.compile(
    r"\b(INSERT\s+INTO|UPDATE\s+\S+\s+SET|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE"
    r"|FOR\s+(NO\s+KEY\s+)?UPDATE|FOR\s+(KEY\s+)?SHARE)\b"
)


@contextmanager
def statements(db: Database) -> Iterator[list[str]]:
    """Every SQL statement sent through the test engine inside the block."""
    seen: list[str] = []

    def record(*args: Any) -> None:
        seen.append(str(args[2]))

    event.listen(db.engine.sync_engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", record)


async def run(db: Database, api: httpx.AsyncClient, url: str, user: User) -> list[str]:
    with statements(db) as seen:
        response = await api.get(url, headers=bearer(user))
    assert response.status_code == 200, response.text
    return list(seen)


def assert_reads_only(seen: list[str]) -> None:
    assert seen
    for statement in seen:
        normalised = " ".join(statement.split()).upper()
        assert normalised.startswith(("SELECT ", "WITH ")), statement
        assert not _WRITES_OR_LOCKS.search(normalised), statement


def test_the_write_and_lock_detector() -> None:
    for statement in (
        "INSERT INTO parts (id) VALUES ($1)",
        "UPDATE bookings SET status = $1",
        "DELETE FROM notifications",
        "SELECT id FROM bookings WHERE id = $1 FOR UPDATE",
        "SELECT id FROM shops WHERE id = $1 FOR SHARE",
        "SELECT id FROM parts ORDER BY id FOR NO KEY UPDATE",
        "WITH x AS (UPDATE parts SET on_hand = 0 RETURNING id) SELECT * FROM x",
    ):
        assert _WRITES_OR_LOCKS.search(statement), statement
    for statement in (
        "SELECT parts.updated_at, parts.on_hand FROM parts",
        "WITH counts AS (SELECT status FROM bookings) SELECT * FROM counts",
    ):
        assert not _WRITES_OR_LOCKS.search(statement.upper()), statement


async def test_the_overview_only_reads_and_its_cost_is_fixed(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    a = world.a
    first_part = part_row(a, "FIRST-OUT", on_hand=0)
    await add_rows(
        db.sessionmaker, first_part, *booking_rows(a, world.customer, BookingStatus.IN_REPAIR)
    )
    small = await run(db, api, overview_url(a.id), a.owner)
    assert_reads_only(small)

    extra_staff = [make_user() for _ in range(10)]
    parts = [part_row(a, f"P-{index:02d}", on_hand=index % 3) for index in range(20)]
    rows: list[object] = [*extra_staff, *parts]
    rows += [
        make_membership(a.shop, user, MembershipRole.TECHNICIAN, created_by=a.owner)
        for user in extra_staff
    ]
    for index, status in enumerate(list(BookingStatus) * 2):
        assignee = (
            {} if status in _UNASSIGNED else {"technician_user_id": extra_staff[index % 10].id}
        )
        rows += booking_rows(a, world.customer, status, **assignee)
    rows += purchase_order_rows(a, PurchaseOrderStatus.ORDERED, [(parts[0], 3, 0)])
    rows += purchase_order_rows(a, PurchaseOrderStatus.PARTIALLY_RECEIVED, [(first_part, 2, 1)])
    await add_rows(db.sessionmaker, *rows)

    large = await run(db, api, overview_url(a.id), a.owner)
    assert_reads_only(large)
    assert len(large) == len(small)


async def test_the_owner_summary_only_reads_and_costs_the_same_per_shop(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    owner = make_user(full_name="Asif Memon")
    await add_rows(db.sessionmaker, owner)
    nothing = await run(db, api, SUMMARY_URL, owner)  # owns no shop: no per-shop reads at all
    assert_reads_only(nothing)

    first = await make_cast(db, owner=owner, name="First Garage")
    one = await run(db, api, SUMMARY_URL, owner)
    await make_cast(db, owner=owner, name="Second Garage")
    two = await run(db, api, SUMMARY_URL, owner)
    await make_cast(db, owner=owner, name="Third Garage")
    three = await run(db, api, SUMMARY_URL, owner)
    for seen in (one, two, three):
        assert_reads_only(seen)
    assert len(nothing) < len(one)
    assert len(three) - len(two) == len(two) - len(one) > 0  # a fixed cost per owned shop

    # More bookings and parts in a shop change no statement count.
    rows = [row for status in BookingStatus for row in booking_rows(first, world.customer, status)]
    rows += [part_row(first, "X-OUT", on_hand=0), part_row(first, "X-LOW", reorder_level=2)]
    await add_rows(db.sessionmaker, *rows)
    assert len(await run(db, api, SUMMARY_URL, owner)) == len(three)

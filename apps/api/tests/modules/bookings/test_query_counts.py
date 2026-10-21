"""API-11 (P1): the booking lists issue the same number of SQL statements for 1 and for 20 items
(spec 12 §8; `modules/bookings.md` §7.10 "No N+1"): users, member refs, services, vehicles,
estimate, parts and QC summaries and `status_changed_at` are each read once per page."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import event

from app.core.database import Database
from app.shared.enums import BookingStatus
from tests.modules.bookings.support import Desk, World, drive_booking_to, new_customer
from tests.modules.identity.builders import bearer

pytestmark = pytest.mark.db

S = BookingStatus


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


async def count_get(desk: Desk, db: Database, user_id: Any, path: str, **params: Any) -> int:
    with statements(db) as seen:
        response = await desk.api.get(path, params=params, headers=bearer(user_id))
    assert response.status_code == 200, response.text
    return len(seen)


async def test_api11_the_staff_list_is_batched(desk: Desk, world: World, db: Database) -> None:
    await drive_booking_to(desk, S.QC_IN_PROGRESS)  # every facet: members, estimate, parts, QC
    path = desk.shop_path("/bookings")
    callers = [world.owner.id, world.technician.id, world.parts.id, world.qc.id]
    one = {user_id: await count_get(desk, db, user_id, path, limit=50) for user_id in callers}
    for _ in range(12):
        await desk.book()
    for status in (S.INSPECTING, S.PARTS_ORDERED, S.QC_PENDING, S.READY_FOR_PICKUP, S.CANCELLED):
        await drive_booking_to(desk, status)
    await drive_booking_to(desk, S.QC_IN_PROGRESS)
    await drive_booking_to(desk, S.COMPLETED)
    listing = await desk.get(world.owner.id, path, limit=50)
    assert listing["total"] == 20
    twenty = {user_id: await count_get(desk, db, user_id, path, limit=50) for user_id in callers}
    assert twenty == one
    assert (await desk.get(world.qc.id, path, limit=50))["total"] == 5  # queue + inspected


async def test_api11_the_customer_list_is_batched(desk: Desk, world: World, db: Database) -> None:
    customer = await new_customer(db)
    await drive_booking_to(desk, S.AWAITING_CUSTOMER, customer=customer)
    one = await count_get(desk, db, customer.user_id, "/api/v1/me/bookings", limit=50)
    for _ in range(10):
        await desk.book(customer)
    for _ in range(5):
        body = desk.booking_body(shop_id=world.other.id, services=world.other_services)
        response = await desk.wizard(body, headers=customer.headers)
        assert response.status_code == 201, response.text
    for status in (S.ESTIMATE_APPROVED, S.CANCELLED, S.COMPLETED, S.ESTIMATE_REJECTED):
        await drive_booking_to(desk, status, customer=customer)
    listing = await desk.get(customer.user_id, "/api/v1/me/bookings", limit=50)
    assert listing["total"] == 20
    assert {item["shop"]["id"] for item in listing["items"]} == {
        str(world.shop_id),
        str(world.other.id),
    }
    twenty = await count_get(desk, db, customer.user_id, "/api/v1/me/bookings", limit=50)
    assert twenty == one

"""End to end with bookings' real reads: the overview and the owner summary of one shop, computed
by `bookings.service.count_by_status`, `count_open_jobs` and `count_day_activity` themselves (no
stand-in). Skipped only while the bookings build still raises `NotImplementedError` for one of
them; every other reporting test uses the real functions as soon as they exist."""

from datetime import UTC, datetime

import httpx
import pytest

from app.core.database import Database
from app.shared.clock import SimulatedClock
from app.shared.enums import BookingStatus
from tests.modules.reporting.support import (
    SUMMARY_URL,
    World,
    bearer,
    booking_rows,
    overview_url,
    part_row,
)
from tests.rows import add_rows

pytestmark = pytest.mark.db

S = BookingStatus


async def test_overview_and_summary_with_the_real_bookings_reads(
    api: httpx.AsyncClient,
    world: World,
    db: Database,
    clock: SimulatedClock,
    bookings_reads: dict[str, str],
) -> None:
    stand_ins = sorted(name for name, mode in bookings_reads.items() if mode != "real")
    if stand_ins:
        pytest.skip(f"bookings.service still raises NotImplementedError: {', '.join(stand_ins)}")
    clock.set(datetime(2026, 10, 15, 19, 30, tzinfo=UTC))  # Fri 16 Oct 00:30 PKT
    a, customer = world.a, world.customer
    today = datetime(2026, 10, 16, 5, 0, tzinfo=UTC)
    rows: list[object] = [
        *booking_rows(a, customer, S.PENDING, slot_start=today),
        *booking_rows(a, customer, S.CANCELLED, slot_start=today),
        *booking_rows(a, customer, S.IN_REPAIR, slot_start=datetime(2026, 10, 14, 5, tzinfo=UTC)),
        *booking_rows(
            a,
            customer,
            S.COMPLETED,
            slot_start=datetime(2026, 10, 12, 5, tzinfo=UTC),
            completed_at=datetime(2026, 10, 15, 19, 5, tzinfo=UTC),
        ),
        *booking_rows(
            a,
            customer,
            S.READY_FOR_PICKUP,
            slot_start=datetime(2026, 10, 11, 5, tzinfo=UTC),
        ),
        part_row(a, "OUT", on_hand=0, reorder_level=1),
    ]
    await add_rows(db.sessionmaker, *rows)

    overview = await api.get(overview_url(a.id), headers=bearer(a.owner))
    assert overview.status_code == 200, overview.text
    body = overview.json()
    counts = {item["status"]: item["count"] for item in body["status_counts"]}
    assert len(counts) == 17
    assert {status: count for status, count in counts.items() if count} == {
        "PENDING": 1,
        "IN_REPAIR": 1,
        "READY_FOR_PICKUP": 1,
        "COMPLETED": 1,
        "CANCELLED": 1,
    }
    assert body["today"] == {
        "date": "2026-10-16",
        "bookings": 1,
        "ready_for_pickup": 1,
        "completed": 1,
    }
    open_jobs = {member["full_name"]: member["open_jobs"] for member in body["team"]}
    assert open_jobs["Imran"] == 1  # IN_REPAIR; not the ready, completed or cancelled ones
    assert open_jobs["Usman"] == 1
    assert open_jobs["Sara"] == 0

    summary = await api.get(SUMMARY_URL, headers=bearer(a.owner))
    assert summary.status_code == 200, summary.text
    assert summary.json()["items"] == [
        {
            "shop": {
                "id": str(a.id),
                "slug": a.shop.slug,
                "name": a.shop.name,
                "city": a.shop.city,
            },
            "today_bookings": 1,
            "needs_sa_action": 2,  # PENDING, READY_FOR_PICKUP
            "in_progress": 1,  # IN_REPAIR
            "ready_for_pickup": 1,
            "low_stock_count": 1,
        }
    ]

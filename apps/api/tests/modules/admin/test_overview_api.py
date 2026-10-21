"""The platform overview, E-61 (spec 19 §4; D38, D63).

"Today", the last 7 / 30 days and the 14-day series are `Asia/Karachi` local days; bookings are
counted by when they were placed. The clock is moved between the bookings, so each lands on a
known local day.
"""

from datetime import UTC, date, datetime, timedelta

from app.core.database import Database
from app.modules.identity.schemas import UserRecord
from app.shared.clock import SimulatedClock
from tests.modules.admin.support import REASON, admin_get, admin_post
from tests.modules.bookings.support import THURSDAY_0900, Desk, World
from tests.modules.identity.builders import make_user

TODAY = date(2026, 10, 14)
HOUR = timedelta(hours=1)


async def test_e61_counts_shops_users_and_bookings(
    desk: Desk, world: World, db: Database, admin: UserRecord, clock: SimulatedClock
) -> None:
    # Fixed slots on 15 Oct: within the 30-day horizon of every clock below, whatever other tests
    # took from the shared `next_slot()` sequence.
    clock.set(datetime(2026, 10, 4, 4, 0, tzinfo=UTC))  # Sunday 4 Oct, 09:00 in Karachi
    await desk.book(slot=THURSDAY_0900)
    clock.set(datetime(2026, 10, 10, 4, 0, tzinfo=UTC))  # Saturday 10 Oct
    await desk.book(shop_id=world.other.id, services=world.other_services, slot=THURSDAY_0900)
    clock.set(datetime(2026, 10, 14, 4, 0, tzinfo=UTC))  # today
    declined = await desk.book(slot=THURSDAY_0900 + HOUR)
    await desk.act(world.advisor, declined.id, "decline", {"reason": "No bay free that morning"})
    await desk.book(slot=THURSDAY_0900 + 2 * HOUR)
    await make_user(db, full_name="Dormant Account", active=False)
    clock.advance(timedelta(minutes=1))
    await admin_post(desk.api, admin, f"/shops/{world.other.id}/suspend", {"reason": REASON})

    overview = await admin_get(desk.api, admin, "/overview")
    assert (overview["timezone"], overview["today"]) == ("Asia/Karachi", TODAY.isoformat())
    assert overview["shops"] == {
        "total": 2,
        "active": 1,
        "suspended": 1,
        "listed": 2,
        "new_30d": 2,
    }
    # The world's 10 staff accounts, the admin, 4 new customers and the dormant account.
    assert overview["users"] == {
        "total": 16,
        "customers": 6,
        "staff": 10,
        "platform_admins": 1,
        "inactive": 1,
        "new_30d": 16,
    }
    bookings = overview["bookings"]
    assert {key: value for key, value in bookings.items() if key != "open_by_phase"} == {
        "today": 2,
        "last_7_days": 3,
        "last_30_days": 4,
        "open": 3,
        "completed_30d": 0,
        "cancelled_30d": 1,
    }
    assert bookings["open_by_phase"] == [
        {"phase": "INTAKE", "count": 3},
        {"phase": "INSPECTION", "count": 0},
        {"phase": "ESTIMATE", "count": 0},
        {"phase": "PARTS", "count": 0},
        {"phase": "REPAIR_QC", "count": 0},
        {"phase": "HANDOVER", "count": 0},
        {"phase": "CLOSED", "count": 0},
    ]
    series = overview["bookings_per_day"]
    assert [day["date"] for day in series] == [
        (TODAY - timedelta(days=offset)).isoformat() for offset in range(13, -1, -1)
    ]
    counts = {day["date"]: day["count"] for day in series if day["count"]}
    assert counts == {"2026-10-04": 1, "2026-10-10": 1, "2026-10-14": 2}
    assert [(row["shop"]["name"], row["bookings_30d"]) for row in overview["top_shops"]] == [
        ("Lahore Auto Care", 3),
        ("Clifton Car Clinic", 1),
    ]
    latest = overview["latest_audit_events"]
    assert len(latest) == 10
    assert latest[0]["action"] == "shop.suspended"  # newest first


async def test_e61_today_is_the_karachi_date(
    desk: Desk, world: World, admin: UserRecord, clock: SimulatedClock
) -> None:
    """19:30 UTC on 14 Oct is already 00:30 on 15 Oct in Karachi (UTC+5)."""
    clock.set(datetime(2026, 10, 14, 18, 59, tzinfo=UTC))
    await desk.book()
    clock.set(datetime(2026, 10, 14, 19, 30, tzinfo=UTC))
    overview = await admin_get(desk.api, admin, "/overview")
    assert overview["today"] == "2026-10-15"
    assert overview["bookings"]["today"] == 0
    assert overview["bookings_per_day"][-2:] == [
        {"date": "2026-10-14", "count": 1},
        {"date": "2026-10-15", "count": 0},
    ]

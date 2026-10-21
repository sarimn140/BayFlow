"""`GET /api/v1/public/shops/{shop_slug}/availability?date=` (spec 03 §4.5; D37, D38, D64, D68).

The clock is frozen at Wednesday 14 Oct 2026 09:00 PKT (spec 12 §4.4). Covers BK-11, BK-12,
BK-27 (availability), SCH-02 (API half), SCH-03, SCH-04, SCH-05 and the public half of SEC-04.
"""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from app.core.database import Database
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import ShopUpdate
from app.shared.clock import SimulatedClock
from tests.assertions import assert_problem
from tests.modules.identity.builders import field_errors, unit_of_work
from tests.modules.scheduling.helpers import book
from tests.modules.shops.builders import ShopCtx, make_services, make_shop, week

pytestmark = pytest.mark.db

FRIDAY = "2026-10-16"
FRIDAY_1000_PKT = datetime(2026, 10, 16, 5, tzinfo=UTC)


def url(ctx: ShopCtx) -> str:
    return f"/api/v1/public/shops/{ctx.slug}/availability"


async def slots(client: httpx.AsyncClient, ctx: ShopCtx, day: str) -> list[dict[str, object]]:
    response = await client.get(url(ctx), params={"date": day})
    assert response.status_code == 200, response.text
    items: list[dict[str, object]] = response.json()["slots"]
    return items


async def set_capacity(db: Database, ctx: ShopCtx, capacity: int) -> None:
    async with unit_of_work(db) as uow:
        await shops_service.update_shop(
            uow,
            shop_id=ctx.id,
            actor_user_id=ctx.owner.id,
            data=ShopUpdate(slot_capacity=capacity),
        )


async def test_bk12_friday_slots_in_the_shop_timezone(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db, name="Lahore Auto Care")
    await make_services(db, ctx)
    response = await db_client.get(url(ctx), params={"date": FRIDAY})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"shop_id", "date", "timezone", "slot_duration_minutes", "slots"}
    assert (body["shop_id"], body["date"], body["timezone"], body["slot_duration_minutes"]) == (
        str(ctx.id),
        FRIDAY,
        "Asia/Karachi",
        60,
    )
    assert len(body["slots"]) == 9  # 09:00 … 17:00 PKT
    assert body["slots"][0] == {
        "slot_start": "2026-10-16T04:00:00Z",
        "slot_end": "2026-10-16T05:00:00Z",
        "remaining": 2,
    }
    assert body["slots"][1]["slot_start"] == "2026-10-16T05:00:00Z"  # Friday 10:00 PKT
    assert body["slots"][-1]["slot_end"] == "2026-10-16T13:00:00Z"  # 18:00 PKT
    assert all(set(slot) == {"slot_start", "slot_end", "remaining"} for slot in body["slots"])


async def test_bk11_sch03_today_offers_only_slots_after_now(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    today = await slots(db_client, ctx, "2026-10-14")  # now = 09:00 PKT exactly
    assert today[0]["slot_start"] == "2026-10-14T05:00:00Z"  # 10:00: the 09:00 slot started now
    assert len(today) == 8
    clock.advance(timedelta(hours=7, minutes=59))  # 16:59 PKT
    assert [slot["slot_start"] for slot in await slots(db_client, ctx, "2026-10-14")] == [
        "2026-10-14T12:00:00Z"
    ]
    clock.advance(timedelta(minutes=1))  # 17:00 PKT: the last slot starts now
    assert await slots(db_client, ctx, "2026-10-14") == []


async def test_bk11_full_slots_are_omitted_and_remaining_counts_down(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db, capacity=2)
    assert await book(db, ctx.id, FRIDAY_1000_PKT) == "booked"
    friday = {slot["slot_start"]: slot["remaining"] for slot in await slots(db_client, ctx, FRIDAY)}
    assert friday["2026-10-16T05:00:00Z"] == 1
    assert friday["2026-10-16T04:00:00Z"] == 2
    assert await book(db, ctx.id, FRIDAY_1000_PKT) == "booked"
    starts = [slot["slot_start"] for slot in await slots(db_client, ctx, FRIDAY)]
    assert "2026-10-16T05:00:00Z" not in starts  # full: not offered (brief §7.3)
    assert len(starts) == 8


async def test_bk11_sch02_past_closed_and_beyond_horizon_dates_are_empty(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    assert await slots(db_client, ctx, "2026-10-13") == []  # yesterday
    assert await slots(db_client, ctx, "2026-10-18") == []  # Sunday: closed
    last_day = date(2026, 10, 14) + timedelta(days=30)  # Friday 13 Nov: inside the horizon
    assert len(await slots(db_client, ctx, last_day.isoformat())) == 9
    beyond = (last_day + timedelta(days=1)).isoformat()  # Saturday 14 Nov: one day too far
    assert await slots(db_client, ctx, beyond) == []
    for extreme in ("0001-01-01", "9999-12-31"):
        assert await slots(db_client, ctx, extreme) == []


async def test_bk12_another_timezone(db_client: httpx.AsyncClient, db: Database) -> None:
    ctx = await make_shop(db, timezone="Asia/Dubai", hours=week("09:00", "11:00"))
    response = await db_client.get(url(ctx), params={"date": "2026-10-16"})
    assert response.json()["timezone"] == "Asia/Dubai"
    assert [slot["slot_start"] for slot in response.json()["slots"]] == [
        "2026-10-16T05:00:00Z",  # 09:00 GST (UTC+4)
        "2026-10-16T06:00:00Z",
    ]


async def test_sch04_capacity_below_the_booked_count_closes_the_slot(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db, capacity=2)
    await book(db, ctx.id, FRIDAY_1000_PKT)
    await book(db, ctx.id, FRIDAY_1000_PKT)
    await set_capacity(db, ctx, 1)  # always allowed; existing bookings are kept (D37)
    friday = await slots(db_client, ctx, FRIDAY)
    assert "2026-10-16T05:00:00Z" not in [slot["slot_start"] for slot in friday]
    assert all(slot["remaining"] == 1 for slot in friday)  # never negative
    await set_capacity(db, ctx, 3)
    reopened = {
        slot["slot_start"]: slot["remaining"] for slot in await slots(db_client, ctx, FRIDAY)
    }
    assert reopened["2026-10-16T05:00:00Z"] == 1


async def test_sch05_a_listed_shop_without_services_still_answers(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)  # no services: not in the directory, not bookable (D64)
    assert len(await slots(db_client, ctx, FRIDAY)) == 9
    hidden = await make_shop(db, listed=False)
    await make_services(db, hidden)
    response = await db_client.get(url(hidden), params={"date": FRIDAY})
    assert_problem(response, 404, "NOT_FOUND")


async def test_bk27_unknown_slugs_and_uuids_are_404(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    for slug in ("no-such-shop", str(ctx.id)):
        response = await db_client.get(
            f"/api/v1/public/shops/{slug}/availability", params={"date": FRIDAY}
        )
        assert_problem(response, 404, "NOT_FOUND")
    body = (await db_client.get(url(ctx), params={"date": FRIDAY})).json()
    assert all("available" not in slot for slot in body["slots"])


@pytest.mark.parametrize("value", ["16-10-2026", "2026-10-16T05:00:00Z", "tomorrow", "2026-02-30"])
async def test_a_malformed_date_is_422(
    db_client: httpx.AsyncClient, db: Database, value: str
) -> None:
    ctx = await make_shop(db)
    response = await db_client.get(url(ctx), params={"date": value})
    problem = assert_problem(response, 422, "VALIDATION_ERROR")
    assert [field for field, _ in field_errors(problem)] == ["query.date"]


async def test_the_date_is_required(db_client: httpx.AsyncClient, db: Database) -> None:
    ctx = await make_shop(db)
    problem = assert_problem(await db_client.get(url(ctx)), 422, "VALIDATION_ERROR")
    assert field_errors(problem) == [("query.date", "missing")]


async def test_sec04_availability_is_public_and_never_cached(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    anonymous = await db_client.get(url(ctx), params={"date": FRIDAY})
    garbage = await db_client.get(
        url(ctx), params={"date": FRIDAY}, headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert anonymous.status_code == garbage.status_code == 200  # credentials are never read
    assert anonymous.json() == garbage.json()
    assert anonymous.headers["cache-control"] == "no-store"  # polled every 15 s (D14, D61)

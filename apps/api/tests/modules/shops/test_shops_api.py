"""Shops over HTTP: create, read, update, working hours and the D37 grid guard (spec 03 §4.9).

Covers SHP-01…SHP-04, the shops halves of BK-29 and BK-30 (the bookings veto is simulated by a
`ShopGridChanging` subscriber, as bookings' handler will do), SEC-40 and the shop routes' errors.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.core.database import Database
from app.core.errors import Conflict
from app.modules.shops.events import ShopGridChanging
from app.modules.shops.models import Shop, ShopMembership, ShopWorkingHours
from app.modules.shops.repository import ShopRepository
from app.shared.clock import SimulatedClock
from app.shared.enums import MembershipRole
from app.shared.uow import UnitOfWork
from tests.assertions import assert_problem
from tests.modules.identity.builders import bearer, field_errors, make_user
from tests.modules.shops.builders import (
    MON_SAT_9_TO_18,
    add_member,
    make_shop,
    shop_payload,
    week,
)

pytestmark = pytest.mark.db

SHOPS = "/api/v1/shops"


def shop_url(shop_id: uuid.UUID, suffix: str = "") -> str:
    return f"{SHOPS}/{shop_id}{suffix}"


async def row_counts(db: Database) -> tuple[int, int, int]:
    async with db.sessionmaker() as session:
        shops = await session.scalar(select(func.count()).select_from(Shop))
        hours = await session.scalar(select(func.count()).select_from(ShopWorkingHours))
        memberships = await session.scalar(select(func.count()).select_from(ShopMembership))
    return int(shops or 0), int(hours or 0), int(memberships or 0)


@dataclass
class VetoSwitch:
    active: bool = True


@pytest.fixture
def grid_events(db_app: FastAPI) -> list[ShopGridChanging]:
    """Records every `ShopGridChanging` published by this app."""
    events: list[ShopGridChanging] = []

    async def record(event: ShopGridChanging, uow: UnitOfWork) -> None:
        events.append(event)

    db_app.state.event_bus.subscribe(ShopGridChanging, record)
    return events


@pytest.fixture
def veto(db_app: FastAPI) -> VetoSwitch:
    """Stands in for bookings' `on_shop_grid_changing`: 409 while "future bookings exist"."""
    switch = VetoSwitch()

    async def on_shop_grid_changing(event: ShopGridChanging, uow: UnitOfWork) -> None:
        if switch.active:
            msg = "This shop has upcoming bookings."
            raise Conflict(msg)

    db_app.state.event_bus.subscribe(ShopGridChanging, on_shop_grid_changing)
    return switch


# --- Create --------------------------------------------------------------------------------------


async def test_create_shop_creates_the_shop_its_hours_and_the_owner_membership(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    owner = await make_user(db)
    response = await db_client.post(
        SHOPS, json=shop_payload(name="Lahore Auto Care"), headers=bearer(owner.id)
    )
    assert response.status_code == 201, response.text
    shop = response.json()
    assert shop["slug"] == "lahore-auto-care"
    assert shop["timezone"] == "Asia/Karachi"
    assert shop["phone"] == "+924200000101"
    assert (shop["rating"], shop["logo_url"], shop["is_listed"]) == (None, None, True)
    assert shop["has_future_bookings"] is False
    assert (shop["slot_duration_minutes"], shop["slot_capacity"]) == (60, 2)
    assert shop["created_at"] == shop["updated_at"] == "2026-10-14T04:00:00Z"
    assert shop["working_hours"][0] == {
        "weekday": 0,
        "is_closed": False,
        "opens_at": "09:00",
        "closes_at": "18:00",
    }
    assert shop["working_hours"][6] == {
        "weekday": 6,
        "is_closed": True,
        "opens_at": None,
        "closes_at": None,
    }
    assert [day["weekday"] for day in shop["working_hours"]] == list(range(7))
    assert await row_counts(db) == (1, 7, 1)

    me = (await db_client.get("/api/v1/me", headers=bearer(owner.id))).json()
    assert me["memberships"] == [
        {
            "membership_id": me["memberships"][0]["membership_id"],
            "shop_id": shop["id"],
            "shop_name": "Lahore Auto Care",
            "shop_slug": "lahore-auto-care",
            "shop_suspended": False,  # D96, spec 19 §2
            "role": "OWNER",
            "capabilities": ["parts.manage", "services.manage", "shop.manage", "team.manage"],
        }
    ]
    fetched = await db_client.get(shop_url(shop["id"]), headers=bearer(owner.id))
    assert fetched.json() == shop


async def test_create_shop_needs_a_session(db_client: httpx.AsyncClient) -> None:
    assert_problem(await db_client.post(SHOPS, json=shop_payload()), 401, "UNAUTHENTICATED")
    unauthenticated_invalid = await db_client.post(SHOPS, json={})
    assert_problem(unauthenticated_invalid, 401, "UNAUTHENTICATED")  # 401 beats 422


async def test_shp01_slugs_never_clash_and_never_change(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    owner = await make_user(db)
    headers = bearer(owner.id)
    first = (
        await db_client.post(SHOPS, json=shop_payload(name="Lahore Auto Care"), headers=headers)
    ).json()
    second = (
        await db_client.post(SHOPS, json=shop_payload(name="LAHORE auto-care!"), headers=headers)
    ).json()
    urdu = (
        await db_client.post(SHOPS, json=shop_payload(name="لاہور آٹو کیئر"), headers=headers)
    ).json()
    urdu_2 = (await db_client.post(SHOPS, json=shop_payload(name="کراچی"), headers=headers)).json()
    assert [first["slug"], second["slug"], urdu["slug"], urdu_2["slug"]] == [
        "lahore-auto-care",
        "lahore-auto-care-2",
        "shop",
        "shop-2",
    ]
    renamed = await db_client.patch(
        shop_url(first["id"]), json={"name": "Lahore Auto Care & Tyres"}, headers=headers
    )
    assert renamed.json()["name"] == "Lahore Auto Care & Tyres"
    assert renamed.json()["slug"] == "lahore-auto-care"  # public links stay valid (D68)


async def test_shp01_a_lost_slug_race_retries_with_the_next_candidate(
    db_client: httpx.AsyncClient, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await make_user(db)
    await make_shop(db, owner=owner, name="Clifton Car Clinic")

    async def stale_read(self: ShopRepository, base: str) -> set[str]:
        return set()  # as if the other shop committed right after this read

    monkeypatch.setattr(ShopRepository, "taken_slugs", stale_read)
    response = await db_client.post(
        SHOPS, json=shop_payload(name="Clifton Car Clinic"), headers=bearer(owner.id)
    )
    assert response.status_code == 201, response.text
    assert response.json()["slug"] == "clifton-car-clinic-2"
    assert await row_counts(db) == (2, 14, 2)


async def test_shp01_after_six_lost_races_the_creation_fails_loudly(
    db_client: httpx.AsyncClient, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await make_user(db)
    for _ in range(6):  # takes "garage", "garage-2" … "garage-6"
        await make_shop(db, owner=owner, name="Garage")
    other = await make_user(db)

    async def stale_read(self: ShopRepository, base: str) -> set[str]:
        return set()

    monkeypatch.setattr(ShopRepository, "taken_slugs", stale_read)
    response = await db_client.post(
        SHOPS, json=shop_payload(name="Garage"), headers=bearer(other.id)
    )
    assert_problem(response, 500, "INTERNAL_ERROR")  # ≤ 5 retries, then 500 (§7.3)
    assert await row_counts(db) == (6, 42, 6)  # nothing of the failed creation remains


async def test_shp02_shop_creation_is_atomic(db_client: httpx.AsyncClient, db: Database) -> None:
    owner = await make_user(db)
    hours = week()
    hours[2]["opens_at"] = "09:30"  # off the 60-minute grid
    response = await db_client.post(
        SHOPS, json=shop_payload(working_hours=hours), headers=bearer(owner.id)
    )
    problem = assert_problem(response, 422, "VALIDATION_ERROR")
    assert field_errors(problem) == [("working_hours.2.opens_at", "not_on_grid")]
    assert await row_counts(db) == (0, 0, 0)


async def test_shp03_working_hours_rules_on_create(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    owner = await make_user(db)
    hours: list[dict[str, Any]] = week()
    hours[1] = {**hours[1], "weekday": 0}  # duplicate weekday
    hours[2] = {"weekday": 2, "is_closed": False}  # missing times
    hours[3] = {**hours[3], "opens_at": "18:00", "closes_at": "09:00"}  # invalid range
    hours[4] = {**hours[4], "closes_at": "17:45"}  # off grid
    response = await db_client.post(
        SHOPS, json=shop_payload(working_hours=hours), headers=bearer(owner.id)
    )
    problem = assert_problem(response, 422, "VALIDATION_ERROR")
    assert field_errors(problem) == [
        ("working_hours.1.weekday", "duplicate"),
        ("working_hours.2.opens_at", "missing"),
        ("working_hours.2.closes_at", "missing"),
        ("working_hours.3.closes_at", "invalid_range"),
        ("working_hours.4.closes_at", "not_on_grid"),
    ]


async def test_shp03_schema_level_week_errors(db_client: httpx.AsyncClient, db: Database) -> None:
    owner = await make_user(db)
    headers = bearer(owner.id)
    six = await db_client.post(SHOPS, json=shop_payload(working_hours=week()[:6]), headers=headers)
    assert field_errors(assert_problem(six, 422, "VALIDATION_ERROR")) == [
        ("working_hours", "too_short")
    ]
    eight = await db_client.post(
        SHOPS, json=shop_payload(working_hours=[*week(), week()[0]]), headers=headers
    )
    assert field_errors(assert_problem(eight, 422, "VALIDATION_ERROR")) == [
        ("working_hours", "too_long")
    ]
    hours = week()
    hours[0]["opens_at"] = "9:00"
    bad_format = await db_client.post(
        SHOPS, json=shop_payload(working_hours=hours), headers=headers
    )
    assert field_errors(assert_problem(bad_format, 422, "VALIDATION_ERROR")) == [
        ("working_hours.0.opens_at", "value_error")
    ]


async def test_shp03_a_closed_day_with_times_is_stored_without_them(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    owner = await make_user(db)
    hours = week()
    hours[6] = {"weekday": 6, "is_closed": True, "opens_at": "10:13", "closes_at": "11:00"}
    response = await db_client.post(
        SHOPS, json=shop_payload(working_hours=hours), headers=bearer(owner.id)
    )
    assert response.status_code == 201
    assert response.json()["working_hours"][6] == {
        "weekday": 6,
        "is_closed": True,
        "opens_at": None,
        "closes_at": None,
    }


async def test_bk30_45_minute_grid_on_create(db_client: httpx.AsyncClient, db: Database) -> None:
    owner = await make_user(db)
    headers = bearer(owner.id)
    on_grid = shop_payload(slot_duration_minutes=45, working_hours=week("09:00", "18:00"))
    assert (await db_client.post(SHOPS, json=on_grid, headers=headers)).status_code == 201
    off_grid = shop_payload(slot_duration_minutes=45, working_hours=week("09:30", "18:00"))
    problem = assert_problem(
        await db_client.post(SHOPS, json=off_grid, headers=headers), 422, "VALIDATION_ERROR"
    )
    assert ("working_hours.0.opens_at", "not_on_grid") in field_errors(problem)


@pytest.mark.parametrize(
    "smuggled",
    [{"slug": "my-own-slug"}, {"rating": 5}, {"owner_user_id": str(uuid.uuid4())}],
)
async def test_sec17_create_shop_refuses_extra_fields(
    db_client: httpx.AsyncClient, db: Database, smuggled: dict[str, Any]
) -> None:
    owner = await make_user(db)
    response = await db_client.post(SHOPS, json=shop_payload(**smuggled), headers=bearer(owner.id))
    assert field_errors(assert_problem(response, 422, "VALIDATION_ERROR")) == [
        (next(iter(smuggled)), "extra_forbidden")
    ]


async def test_create_shop_validates_timezone_and_logo(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    owner = await make_user(db)
    headers = bearer(owner.id)
    zoned = await db_client.post(
        SHOPS,
        json=shop_payload(timezone="Europe/London", logo_url="https://cdn.bayflow.test/l.png"),
        headers=headers,
    )
    assert zoned.status_code == 201
    assert zoned.json()["timezone"] == "Europe/London"
    assert zoned.json()["logo_url"] == "https://cdn.bayflow.test/l.png"
    for overrides, field in (
        ({"timezone": "Pakistan/Lahore"}, "timezone"),
        ({"logo_url": "javascript:alert(1)"}, "logo_url"),
        ({"logo_url": "http://cdn.bayflow.test/l.png"}, "logo_url"),
    ):
        response = await db_client.post(SHOPS, json=shop_payload(**overrides), headers=headers)
        assert field_errors(assert_problem(response, 422, "VALIDATION_ERROR")) == [
            (field, "value_error")
        ]


@pytest.mark.parametrize(
    ("sent", "timezone", "is_listed"),
    [
        ({}, "Asia/Karachi", True),
        ({"timezone": None, "is_listed": None, "logo_url": None}, "Asia/Karachi", True),
        ({"timezone": "Asia/Dubai", "is_listed": False}, "Asia/Dubai", False),
    ],
)
async def test_optional_create_fields_may_be_omitted_or_null(
    db_client: httpx.AsyncClient,
    db: Database,
    sent: dict[str, Any],
    timezone: str,
    is_listed: bool,
) -> None:
    """Spec 03 §1.5: omitted or `null` optional fields take their defaults (D38)."""
    owner = await make_user(db)
    response = await db_client.post(SHOPS, json=shop_payload(**sent), headers=bearer(owner.id))
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["timezone"], body["is_listed"], body["logo_url"]) == (timezone, is_listed, None)


async def test_sec27_shop_creation_limit_per_user(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    owner = await make_user(db)
    other = await make_user(db)
    for _ in range(10):  # 10 per user per day (D69)
        response = await db_client.post(SHOPS, json=shop_payload(), headers=bearer(owner.id))
        assert response.status_code == 201
    blocked = await db_client.post(SHOPS, json=shop_payload(), headers=bearer(owner.id))
    assert_problem(blocked, 429, "RATE_LIMITED")
    assert int(blocked.headers["retry-after"]) >= 1
    assert (await row_counts(db))[0] == 10
    other_user = await db_client.post(SHOPS, json=shop_payload(), headers=bearer(other.id))
    assert other_user.status_code == 201  # the limit is per user


async def test_sec40_any_user_creates_a_shop_and_owns_only_that_one(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    lahore = await make_shop(db)
    imran = await add_member(db, lahore, MembershipRole.TECHNICIAN)
    created = await db_client.post(
        SHOPS, json=shop_payload(name="Imran Motors"), headers=bearer(imran.id)
    )
    assert created.status_code == 201
    roles = {
        item["shop_slug"]: item["role"]
        for item in (await db_client.get("/api/v1/me", headers=bearer(imran.id))).json()[
            "memberships"
        ]
    }
    assert roles == {lahore.slug: "TECHNICIAN", "imran-motors": "OWNER"}
    still_forbidden = await db_client.patch(
        shop_url(lahore.id), json={"slot_capacity": 3}, headers=bearer(imran.id)
    )
    assert_problem(still_forbidden, 403, "FORBIDDEN")
    own = await db_client.patch(
        shop_url(created.json()["id"]), json={"slot_capacity": 3}, headers=bearer(imran.id)
    )
    assert own.status_code == 200


# --- Read and update ------------------------------------------------------------------------------


async def test_every_active_member_reads_the_shop(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    for role in MembershipRole:
        if role is MembershipRole.OWNER:
            caller = ctx.owner.id
        else:
            caller = (await add_member(db, ctx, role)).id
        response = await db_client.get(shop_url(ctx.id), headers=bearer(caller))
        assert response.status_code == 200
        assert response.json()["id"] == str(ctx.id)


async def test_update_shop_applies_only_real_changes(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    headers = bearer(ctx.owner.id)
    clock.advance(timedelta(hours=1))
    same = await db_client.patch(
        shop_url(ctx.id), json={"name": ctx.shop.name, "slot_capacity": 2}, headers=headers
    )
    assert same.status_code == 200
    assert same.json()["updated_at"] == "2026-10-14T04:00:00Z"  # nothing written
    changed = await db_client.patch(
        shop_url(ctx.id),
        json={
            "address": "  Shop 3, Block 5  ",
            "city": "Karachi",
            "phone": "0300-1234567",
            "logo_url": "https://cdn.bayflow.test/logo.png",
            "is_listed": False,
            "slot_capacity": 5,
        },
        headers=headers,
    )
    body = changed.json()
    assert (body["address"], body["city"], body["phone"]) == (
        "Shop 3, Block 5",
        "Karachi",
        "03001234567",
    )
    assert (body["logo_url"], body["is_listed"], body["slot_capacity"]) == (
        "https://cdn.bayflow.test/logo.png",
        False,
        5,
    )
    assert body["updated_at"] == "2026-10-14T05:00:00Z"
    cleared = await db_client.patch(shop_url(ctx.id), json={"logo_url": None}, headers=headers)
    assert cleared.json()["logo_url"] is None


async def test_update_shop_validation(db_client: httpx.AsyncClient, db: Database) -> None:
    ctx = await make_shop(db)
    headers = bearer(ctx.owner.id)
    for body, expected in (
        ({}, [("", "value_error")]),
        ({"name": None}, [("name", "value_error")]),
        ({"slug": "new-slug"}, [("slug", "extra_forbidden")]),
        ({"rating": 4.5}, [("rating", "extra_forbidden")]),
        ({"slot_duration_minutes": 50}, [("slot_duration_minutes", "multiple_of")]),
    ):
        response = await db_client.patch(shop_url(ctx.id), json=body, headers=headers)
        assert field_errors(assert_problem(response, 422, "VALIDATION_ERROR")) == expected


async def test_shp04_duration_change_without_future_bookings(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)  # 09:00-18:00, 60-minute slots
    headers = bearer(ctx.owner.id)
    to_45 = await db_client.patch(
        shop_url(ctx.id), json={"slot_duration_minutes": 45}, headers=headers
    )
    assert to_45.status_code == 200  # 09:00 and 18:00 lie on the 45-minute grid
    assert to_45.json()["slot_duration_minutes"] == 45
    to_120 = await db_client.patch(
        shop_url(ctx.id), json={"slot_duration_minutes": 120}, headers=headers
    )
    problem = assert_problem(to_120, 422, "VALIDATION_ERROR")  # 09:00 is not 2-hourly
    assert field_errors(problem) == [("slot_duration_minutes", "hours_not_on_grid")]
    fetched = (await db_client.get(shop_url(ctx.id), headers=headers)).json()
    assert fetched["slot_duration_minutes"] == 45  # rolled back


async def test_shp04_bk29_future_bookings_veto_duration_and_timezone_changes(
    db_client: httpx.AsyncClient, db: Database, veto: VetoSwitch
) -> None:
    ctx = await make_shop(db)
    headers = bearer(ctx.owner.id)
    for body in (
        {"slot_duration_minutes": 30},  # the hours would fit: still 409
        {"timezone": "Asia/Dubai"},
        {"slot_duration_minutes": 120},  # off the new grid too: the veto answers first
        {"slot_duration_minutes": 30, "name": "Renamed"},
    ):
        response = await db_client.patch(shop_url(ctx.id), json=body, headers=headers)
        assert_problem(response, 409, "CONFLICT")
    unchanged = (await db_client.get(shop_url(ctx.id), headers=headers)).json()
    assert unchanged == ctx.shop.model_dump(mode="json")

    capacity = await db_client.patch(shop_url(ctx.id), json={"slot_capacity": 1}, headers=headers)
    assert capacity.status_code == 200  # never vetoed
    hours = await db_client.put(
        shop_url(ctx.id, "/working-hours"),
        json={"working_hours": week("10:00", "16:00")},
        headers=headers,
    )
    assert hours.status_code == 200
    same_duration = await db_client.patch(
        shop_url(ctx.id), json={"slot_duration_minutes": 60}, headers=headers
    )
    assert same_duration.status_code == 200  # not a change → no event, no veto

    veto.active = False  # every future booking cancelled
    allowed = await db_client.patch(
        shop_url(ctx.id), json={"slot_duration_minutes": 30}, headers=headers
    )
    assert allowed.status_code == 200
    assert allowed.json()["slot_duration_minutes"] == 30


async def test_the_grid_event_is_published_only_for_real_grid_changes(
    db_client: httpx.AsyncClient,
    db: Database,
    clock: SimulatedClock,
    grid_events: list[ShopGridChanging],
) -> None:
    ctx = await make_shop(db)
    headers = bearer(ctx.owner.id)
    for body in (
        {"slot_capacity": 4},
        {"name": "New Name"},
        {"slot_duration_minutes": 60, "timezone": "Asia/Karachi"},  # equal to the stored values
    ):
        assert (
            await db_client.patch(shop_url(ctx.id), json=body, headers=headers)
        ).status_code == 200
    assert grid_events == []
    await db_client.patch(shop_url(ctx.id), json={"timezone": "Asia/Dubai"}, headers=headers)
    await db_client.patch(
        shop_url(ctx.id),
        json={"timezone": "Asia/Karachi", "slot_duration_minutes": 30},
        headers=headers,
    )
    assert [event.changed_fields for event in grid_events] == [
        ("timezone",),
        ("slot_duration_minutes", "timezone"),
    ]
    assert {event.shop_id for event in grid_events} == {ctx.id}
    assert {event.actor_user_id for event in grid_events} == {ctx.owner.id}
    assert grid_events[0].occurred_at == clock.now()


# --- Working hours --------------------------------------------------------------------------------


async def test_replace_working_hours(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    headers = bearer(ctx.owner.id)
    url = shop_url(ctx.id, "/working-hours")
    clock.advance(timedelta(hours=2))
    hours = week("08:00", "17:00", closed=(5, 6))
    response = await db_client.put(url, json={"working_hours": hours}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["working_hours"][0] == {
        "weekday": 0,
        "is_closed": False,
        "opens_at": "08:00",
        "closes_at": "17:00",
    }
    assert body["working_hours"][5]["is_closed"] is True
    assert body["updated_at"] == "2026-10-14T06:00:00Z"

    clock.advance(timedelta(hours=1))
    again = await db_client.put(url, json={"working_hours": hours}, headers=headers)
    assert again.json() == body  # idempotent: nothing rewritten (spec 03 §1.7)
    assert await row_counts(db) == (1, 7, 1)


async def test_replace_working_hours_validates_against_the_current_duration(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db, slot_minutes=45)
    url = shop_url(ctx.id, "/working-hours")
    hours = week("09:00", "18:00")
    hours[1] = {"weekday": 1, "is_closed": False, "opens_at": "09:30", "closes_at": "18:00"}
    response = await db_client.put(url, json={"working_hours": hours}, headers=bearer(ctx.owner.id))
    problem = assert_problem(response, 422, "VALIDATION_ERROR")
    assert field_errors(problem) == [("working_hours.1.opens_at", "not_on_grid")]
    bare_list = await db_client.put(url, json=MON_SAT_9_TO_18, headers=bearer(ctx.owner.id))
    assert_problem(bare_list, 422, "VALIDATION_ERROR")  # the body is {working_hours: [...]}

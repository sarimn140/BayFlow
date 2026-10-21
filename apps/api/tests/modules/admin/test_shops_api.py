"""Tenants in the admin console: E-62 … E-65 (spec 19 §2, §4, §7, §9; D96)."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.core.database import Database
from app.core.errors import Forbidden
from app.modules.identity.schemas import UserRecord
from app.modules.shops import service as shops_service
from app.shared.clock import SimulatedClock
from app.shared.enums import BookingStatus, MembershipRole
from tests.assertions import assert_problem
from tests.lockgate import hold_row_lock, wait_for_lock_waiters
from tests.modules.admin.support import (
    ADMIN,
    REASON,
    admin_get,
    admin_post,
    audit_rows,
    make_admin,
)
from tests.modules.bookings.support import Desk, World, drive_booking_to
from tests.modules.identity.builders import bearer, make_user, unit_of_work
from tests.modules.shops.builders import make_shop


def names(page: dict[str, object]) -> list[str]:
    items = page["items"]
    assert isinstance(items, list)
    return [str(item["shop"]["name"]) for item in items]


# --- E-62 -----------------------------------------------------------------------------------------


async def test_e62_lists_every_tenant_with_owners_members_and_bookings(
    desk: Desk, world: World, admin: UserRecord
) -> None:
    await drive_booking_to(desk, BookingStatus.PENDING)
    await drive_booking_to(desk, BookingStatus.CONFIRMED)
    page = await admin_get(desk.api, admin, "/shops")
    assert page["total"] == 2
    rows = {row["shop"]["name"]: row for row in page["items"]}
    lahore = rows["Lahore Auto Care"]
    assert lahore["shop"] == {
        "id": str(world.shop_id),
        "slug": "lahore-auto-care",
        "name": "Lahore Auto Care",
    }
    assert (lahore["city"], lahore["is_listed"], lahore["suspension"]) == ("Lahore", True, None)
    assert lahore["owners"] == [
        {"user_id": str(world.owner.id), "full_name": "Fatima Raza", "email": world.owner.email}
    ]
    assert (lahore["active_members"], lahore["bookings_30d"]) == (8, 2)
    assert (
        rows["Clifton Car Clinic"]["active_members"],
        rows["Clifton Car Clinic"]["bookings_30d"],
    ) == (2, 0)


async def test_e62_filters(desk: Desk, world: World, db: Database, admin: UserRecord) -> None:
    hidden = await make_shop(db, name="Hidden Garage", listed=False, city="Multan")
    await admin_post(desk.api, admin, f"/shops/{world.other.id}/suspend", {"reason": REASON})

    async def get(**params: object) -> list[str]:
        return names(await admin_get(desk.api, admin, "/shops", sort="name", **params))

    assert await get(q="lahore-auto") == ["Lahore Auto Care"]  # slug
    assert await get(q="KARACHI") == ["Clifton Car Clinic"]  # city
    assert await get(q=world.other.owner.email) == ["Clifton Car Clinic"]  # the owner's e-mail
    assert await get(q=hidden.owner.email[:-5]) == ["Hidden Garage"]  # part of an e-mail
    assert await get(status="SUSPENDED") == ["Clifton Car Clinic"]
    assert await get(status="ACTIVE") == ["Hidden Garage", "Lahore Auto Care"]
    assert await get(listed="false") == ["Hidden Garage"]
    assert await get(listed="true", status="ACTIVE") == ["Lahore Auto Care"]
    assert await get(city="multan") == ["Hidden Garage"]
    assert await get(q="_") == []  # literal
    for bad in ({"status": "CLOSED"}, {"sort": "city"}, {"q": "x" * 101}):
        response = await desk.api.get(f"{ADMIN}/shops", headers=bearer(admin.id), params=bad)
        assert_problem(response, 422, "VALIDATION_ERROR")


async def test_e62_sorts_and_pages(
    desk: Desk, world: World, db: Database, admin: UserRecord, clock: SimulatedClock
) -> None:
    clock.advance(timedelta(minutes=1))
    newest = await make_shop(db, name="Anarkali Motors")
    for _ in range(2):
        body = desk.booking_body(shop_id=world.other.id, services=world.other_services)
        body["customer"] = {
            "full_name": "Sana",
            "email": f"sana-{_}@bayflow.test",
            "password": "test-password-1234",
        }
        response = await desk.wizard(body, headers={"X-Real-IP": f"2001:db8::a{_}"})
        assert response.status_code == 201, response.text
    await drive_booking_to(desk, BookingStatus.PENDING)
    assert names(await admin_get(desk.api, admin, "/shops"))[0] == newest.shop.name
    assert names(await admin_get(desk.api, admin, "/shops", sort="name")) == [
        "Anarkali Motors",
        "Clifton Car Clinic",
        "Lahore Auto Care",
    ]
    busiest = await admin_get(desk.api, admin, "/shops", sort="-bookings_30d")
    assert [(row["shop"]["name"], row["bookings_30d"]) for row in busiest["items"]] == [
        ("Clifton Car Clinic", 2),
        ("Lahore Auto Care", 1),
        ("Anarkali Motors", 0),
    ]
    second = await admin_get(desk.api, admin, "/shops", sort="-bookings_30d", limit=1, offset=1)
    assert (names(second), second["total"]) == (["Lahore Auto Care"], 3)


# --- E-63 -----------------------------------------------------------------------------------------


async def test_e63_shows_profile_team_bookings_and_trail(
    desk: Desk, world: World, admin: UserRecord
) -> None:
    await drive_booking_to(desk, BookingStatus.PENDING)
    await drive_booking_to(desk, BookingStatus.ASSIGNED)
    await drive_booking_to(desk, BookingStatus.CANCELLED)
    detail = await admin_get(desk.api, admin, f"/shops/{world.shop_id}")
    assert (detail["shop"]["name"], detail["shop"]["slug"]) == (
        "Lahore Auto Care",
        "lahore-auto-care",
    )
    assert detail["suspension"] is None
    roles = {group["role"]: group["members"] for group in detail["members_by_role"]}
    assert list(roles) == [role.value for role in MembershipRole]
    assert [member["full_name"] for member in roles["TECHNICIAN"]] == ["Hamza", "Imran"]
    assert roles["OWNER"][0]["email"] == world.owner.email
    phases = {item["phase"]: item["count"] for item in detail["booking_counts_by_phase"]}
    assert phases == {
        "INTAKE": 1,
        "INSPECTION": 1,
        "ESTIMATE": 0,
        "PARTS": 0,
        "REPAIR_QC": 0,
        "HANDOVER": 0,
        "CLOSED": 1,
    }
    assert len(detail["latest_bookings"]) == 3
    assert all("allowed_actions" not in booking for booking in detail["latest_bookings"])
    trail = {event["action"] for event in detail["latest_audit_events"]}
    assert {"booking.create", "booking.confirm", "booking.decline"} <= trail
    assert all(event["shop_id"] == str(world.shop_id) for event in detail["latest_audit_events"])
    # create; create, confirm, assign-technician; create, decline (user rows have no shop)
    assert len(detail["latest_audit_events"]) == 6


# --- E-64, E-65 -----------------------------------------------------------------------------------


async def test_e64_e65_suspend_and_reactivate(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    detail = await admin_post(
        desk.api, admin, f"/shops/{world.shop_id}/suspend", {"reason": REASON}
    )
    suspension = detail["suspension"]
    assert suspension["reason"] == REASON
    assert suspension["at"] == "2026-10-14T04:00:00Z"  # the frozen test clock
    assert suspension["by"] == {
        "user_id": str(admin.id),
        "full_name": "Areeba Hashmi",
        "email": admin.email,
    }
    again = await desk.api.post(
        f"{ADMIN}/shops/{world.shop_id}/suspend", headers=bearer(admin.id), json={"reason": REASON}
    )
    assert_problem(again, 409, "CONFLICT")
    listed = await admin_get(desk.api, admin, "/shops", status="SUSPENDED")
    assert listed["items"][0]["suspension"]["reason"] == REASON
    restored = await admin_post(desk.api, admin, f"/shops/{world.shop_id}/reactivate")
    assert restored["suspension"] is None
    twice = await desk.api.post(
        f"{ADMIN}/shops/{world.shop_id}/reactivate", headers=bearer(admin.id)
    )
    assert_problem(twice, 409, "CONFLICT")
    suspended, reactivated = (
        await audit_rows(db, action="shop.suspended"),
        await audit_rows(db, action="shop.reactivated"),
    )
    assert len(suspended) == len(reactivated) == 1
    assert suspended[0].metadata_ == {"reason": REASON}
    assert suspended[0].summary == "Areeba Hashmi suspended Lahore Auto Care."
    assert reactivated[0].metadata_ == {}


async def test_e64_needs_a_reason_of_5_to_500_characters(
    desk: Desk, world: World, admin: UserRecord
) -> None:
    for body in ({}, {"reason": "Bad"}, {"reason": "  ab  "}, {"reason": "x" * 501}, None):
        response = await desk.api.post(
            f"{ADMIN}/shops/{world.shop_id}/suspend", headers=bearer(admin.id), json=body
        )
        assert_problem(response, 422, "VALIDATION_ERROR")
    exact = await admin_post(
        desk.api, admin, f"/shops/{world.shop_id}/suspend", {"reason": "x" * 500}
    )
    assert len(exact["suspension"]["reason"]) == 500


@pytest.mark.concurrency
async def test_two_admins_suspending_one_shop_at_once_get_one_409(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    """Spec 19 §7: each write locks the shop row; the second admin re-reads it and gets 409."""
    ali = await make_admin(db, full_name="Ali Raza")
    url = f"{ADMIN}/shops/{world.shop_id}/suspend"
    async with hold_row_lock(db, "shops", id=world.shop_id):
        first = asyncio.create_task(
            desk.api.post(url, headers=bearer(admin.id), json={"reason": "First admin's reason"})
        )
        second = asyncio.create_task(
            desk.api.post(url, headers=bearer(ali.id), json={"reason": "Second admin's reason"})
        )
        await wait_for_lock_waiters(db, 2)
    responses = [await first, await second]
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert len(await audit_rows(db, action="shop.suspended")) == 1


@pytest.mark.concurrency
async def test_a_suspension_waiting_on_its_admin_sees_a_concurrent_revoke(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    """Spec 19 §1: the shops service locks the acting admin's row `FOR SHARE` before the shop row.
    An admin revoked while their suspension waits on that row is refused (403); nothing changes."""
    url = f"{ADMIN}/shops/{world.shop_id}/suspend"
    async with db.engine.connect() as connection:
        transaction = await connection.begin()
        locked = text("SELECT id FROM users WHERE id = :id FOR UPDATE")
        await connection.execute(locked, {"id": admin.id})
        suspend = asyncio.create_task(
            desk.api.post(url, headers=bearer(admin.id), json={"reason": REASON})
        )
        await wait_for_lock_waiters(db, 1)  # past the route's check, waiting on the admin's row
        revoke = text("UPDATE users SET is_platform_admin = false WHERE id = :id")
        await connection.execute(revoke, {"id": admin.id})
        await transaction.commit()
    assert_problem(await suspend, 403, "FORBIDDEN")
    async with db.sessionmaker() as session:
        assert await shops_service.get_shop_suspension(session, shop_id=world.shop_id) is None
    assert await audit_rows(db, action="shop.suspended") == []


@pytest.mark.concurrency
async def test_a_revoke_waits_for_the_suspension_its_admin_is_applying(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    """The other order: the suspension holds its admin's row `FOR SHARE`, so a concurrent revoke
    of that admin waits until the suspension commits; both then succeed in that order."""
    ali = await make_admin(db, full_name="Ali Raza")
    suspend_url = f"{ADMIN}/shops/{world.shop_id}/suspend"
    revoke_url = f"{ADMIN}/users/{admin.id}/revoke-platform-admin"
    async with hold_row_lock(db, "shops", id=world.shop_id):
        suspend = asyncio.create_task(
            desk.api.post(suspend_url, headers=bearer(admin.id), json={"reason": REASON})
        )
        await wait_for_lock_waiters(db, 1)  # holds the admin's row, waits on the shop row
        revoke = asyncio.create_task(desk.api.post(revoke_url, headers=bearer(ali.id)))
        await wait_for_lock_waiters(db, 2)  # the revoke waits on the admin's row
    assert (await suspend).status_code == 200
    revoked = await revoke
    assert revoked.status_code == 200, revoked.text
    async with db.sessionmaker() as session:
        suspension = await shops_service.get_shop_suspension(session, shop_id=world.shop_id)
    assert suspension is not None
    assert suspension.suspended_by_user_id == admin.id
    assert (await desk.get(admin.id, "/api/v1/me"))["is_platform_admin"] is False


async def test_suspension_needs_a_platform_admin_even_through_the_service(
    world: World, db: Database
) -> None:
    """Defence in depth: the shops service re-checks the actor (D94)."""
    stranger = await make_user(db)
    async with unit_of_work(db) as uow:
        with pytest.raises(Forbidden):
            await shops_service.suspend_shop(
                uow, shop_id=world.shop_id, actor_user_id=stranger.id, reason=REASON
            )
    async with db.sessionmaker() as session:
        assert await shops_service.get_shop_suspension(session, shop_id=world.shop_id) is None

"""Accounts in the admin console: E-66 … E-71 (spec 19 §1, §4, §9 "Safeguards"; D9, D94).

The safeguards: no admin deactivates or revokes themself (403), the last active platform admin can
be neither revoked nor deactivated (409, also when two admins demote each other at the same time),
granting needs an active account (422 on `path.user_id`), and every no-op is 409.
"""

import asyncio
from datetime import timedelta

import pytest

from app.core.database import Database
from app.core.errors import Conflict
from app.modules.identity import service as identity_service
from app.modules.identity.schemas import UserRecord
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
from tests.modules.bookings.support import Desk, World, drive_booking_to, new_customer
from tests.modules.identity.builders import TEST_PASSWORD, bearer, make_user, unit_of_work
from tests.modules.shops.builders import add_member, set_member_active

LAST_ADMIN = "BayFlow needs at least one active platform admin."


def emails(page: dict[str, object]) -> set[str]:
    items = page["items"]
    assert isinstance(items, list)
    return {str(item["email"]) for item in items}


# --- E-66 -----------------------------------------------------------------------------------------


async def test_e66_lists_every_account_with_its_memberships(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    customer = await new_customer(db, full_name="Ayesha Khan", phone="+92 300 7654321")
    page = await admin_get(desk.api, admin, "/users", limit=100)
    rows = {row["email"]: row for row in page["items"]}
    assert page["total"] == len(rows) == 12  # the world's 10 accounts, the admin, Ayesha
    owner = rows[world.owner.email]
    assert (owner["full_name"], owner["is_active"], owner["is_platform_admin"]) == (
        "Fatima Raza",
        True,
        False,
    )
    assert [(m["shop"]["name"], m["role"], m["is_active"]) for m in owner["memberships"]] == [
        ("Lahore Auto Care", "OWNER", True)
    ]
    assert set(owner) == {
        "id",
        "full_name",
        "email",
        "phone",
        "is_active",
        "is_platform_admin",
        "created_at",
        "last_login_at",
        "memberships",
    }
    assert rows[admin.email]["is_platform_admin"] is True
    assert rows[admin.email]["memberships"] == []
    assert rows[customer.email]["phone"] == "+923007654321"


async def test_e66_filters_by_text_kind_and_status(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    customer = await new_customer(db, full_name="Ayesha Khan", phone="+92 300 7654321")
    gone = await make_user(db, full_name="Gone Customer", active=False)
    # Hina's only membership is inactive: she counts as a customer now (E-66 `kind`).
    await set_member_active(db, world.shop, world.qc2.membership_id, active=False)

    def get(**params: object) -> object:
        return admin_get(desk.api, admin, "/users", limit=100, **params)

    assert emails(await get(q="ayesha")) == {customer.email}  # name, case-insensitive
    assert emails(await get(q=customer.email.upper())) == {customer.email}  # e-mail
    assert emails(await get(q="300 765")) == {customer.email}  # phone, spaces ignored
    assert emails(await get(q="%")) == set()  # `%` is literal
    platform_admins = await get(kind="PLATFORM_ADMIN")
    assert emails(platform_admins) == {admin.email}
    staff = emails(await get(kind="STAFF"))
    assert world.qc2.user.email not in staff
    assert {world.owner.email, world.advisor.user.email, world.other_advisor.user.email} <= staff
    customers = emails(await get(kind="CUSTOMER"))
    assert customers == {customer.email, gone.email, admin.email, world.qc2.user.email}
    assert emails(await get(status="INACTIVE")) == {gone.email}
    assert gone.email not in emails(await get(status="ACTIVE"))
    assert emails(await get(kind="CUSTOMER", status="INACTIVE")) == {gone.email}
    for bad in ({"kind": "OWNER"}, {"status": "DELETED"}, {"sort": "email"}, {"limit": 101}):
        response = await desk.api.get(f"{ADMIN}/users", headers=bearer(admin.id), params=bad)
        assert_problem(response, 422, "VALIDATION_ERROR")


async def test_e66_sorts_and_pages(
    desk: Desk, world: World, db: Database, admin: UserRecord, clock: SimulatedClock
) -> None:
    clock.advance(timedelta(minutes=5))
    newest = await make_user(db, full_name="Zara Newest")
    clock.advance(timedelta(minutes=5))
    login = await desk.api.post(
        "/api/v1/auth/login", json={"email": world.advisor.user.email, "password": TEST_PASSWORD}
    )
    assert login.status_code == 200
    by_created = await admin_get(desk.api, admin, "/users", limit=1)
    assert (by_created["total"], by_created["items"][0]["email"]) == (12, newest.email)
    by_login = await admin_get(desk.api, admin, "/users", sort="-last_login_at", limit=1)
    assert by_login["items"][0]["email"] == world.advisor.user.email
    names = [
        row["full_name"]
        for row in (await admin_get(desk.api, admin, "/users", sort="name", limit=100))["items"]
    ]
    assert names == sorted(names, key=str.lower)
    second = await admin_get(desk.api, admin, "/users", sort="name", limit=5, offset=5)
    assert [row["full_name"] for row in second["items"]] == names[5:10]
    assert (second["limit"], second["offset"], second["total"]) == (5, 5, 12)


# --- E-67 -----------------------------------------------------------------------------------------


async def test_e67_shows_the_account_its_bookings_and_its_trail_and_is_recorded(
    desk: Desk, world: World, db: Database, admin: UserRecord, clock: SimulatedClock
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.CONFIRMED)
    customer = journey.customer
    clock.advance(timedelta(minutes=1))
    detail = await admin_get(desk.api, admin, f"/users/{customer.user_id}")
    assert detail["user"]["email"] == customer.email
    assert detail["bookings_as_customer"]["count"] == 1
    (booking,) = detail["bookings_as_customer"]["latest"]
    assert (booking["reference"], booking["shop"]["name"]) == (
        journey.reference,
        "Lahore Auto Care",
    )
    assert "allowed_actions" not in booking
    trail = [event["action"] for event in detail["latest_audit_events"]]
    assert "user.customer_created" in trail  # by or about the user
    assert "booking.create" in trail
    assert "admin.user_viewed" not in trail  # the view is recorded after it is read
    (viewed,) = await audit_rows(db, action="admin.user_viewed")
    assert (viewed.actor_user_id, viewed.target_id, viewed.actor_role) == (
        admin.id,
        customer.user_id,
        "PLATFORM_ADMIN",
    )
    assert viewed.summary == f"Areeba Hashmi viewed the account of {customer.full_name}."
    again = await admin_get(desk.api, admin, f"/users/{customer.user_id}")
    assert again["latest_audit_events"][0]["action"] == "admin.user_viewed"


# --- E-68, E-69 -----------------------------------------------------------------------------------


async def test_e68_deactivates_an_account_whose_tokens_stop_at_once(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    advisor = world.advisor.user
    assert (await desk.api.get("/api/v1/me", headers=bearer(advisor.id))).status_code == 200
    detail = await admin_post(
        desk.api, admin, f"/users/{advisor.id}/deactivate", {"reason": REASON}
    )
    assert detail["user"]["is_active"] is False
    me = await desk.api.get("/api/v1/me", headers=bearer(advisor.id))
    assert_problem(me, 401, "UNAUTHENTICATED")  # D9: at the very next request
    again = await desk.api.post(
        f"{ADMIN}/users/{advisor.id}/deactivate", headers=bearer(admin.id), json={"reason": REASON}
    )
    assert_problem(again, 409, "CONFLICT")
    (row,) = await audit_rows(db, action="user.deactivated")
    assert (row.metadata_, row.actor_user_id, row.target_id) == (
        {"reason": REASON},
        admin.id,
        advisor.id,
    )
    restored = await admin_post(desk.api, admin, f"/users/{advisor.id}/reactivate")
    assert restored["user"]["is_active"] is True
    assert (await desk.api.get("/api/v1/me", headers=bearer(advisor.id))).status_code == 200
    twice = await desk.api.post(f"{ADMIN}/users/{advisor.id}/reactivate", headers=bearer(admin.id))
    assert_problem(twice, 409, "CONFLICT")
    assert len(await audit_rows(db, action="user.reactivated")) == 1


async def test_e68_refuses_yourself_and_needs_a_reason(
    desk: Desk, world: World, admin: UserRecord
) -> None:
    headers = bearer(admin.id)
    myself = await desk.api.post(
        f"{ADMIN}/users/{admin.id}/deactivate", headers=headers, json={"reason": REASON}
    )
    assert_problem(myself, 403, "FORBIDDEN")
    for body in ({}, {"reason": "abc"}, {"reason": "    x    "}, {"reason": "x" * 501}):
        response = await desk.api.post(
            f"{ADMIN}/users/{world.advisor.id}/deactivate", headers=headers, json=body
        )
        assert_problem(response, 422, "VALIDATION_ERROR")
    extra = await desk.api.post(
        f"{ADMIN}/users/{world.advisor.id}/deactivate",
        headers=headers,
        json={"reason": REASON, "is_active": True},
    )
    assert_problem(extra, 422, "VALIDATION_ERROR")
    me = await desk.api.get("/api/v1/me", headers=headers)
    assert me.status_code == 200  # still active


# --- E-70, E-71 -----------------------------------------------------------------------------------


async def test_e70_e71_grant_and_revoke_platform_admin(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    advisor = world.advisor.user
    granted = await admin_post(desk.api, admin, f"/users/{advisor.id}/grant-platform-admin")
    assert granted["user"]["is_platform_admin"] is True
    assert (await desk.api.get(f"{ADMIN}/overview", headers=bearer(advisor.id))).status_code == 200
    twice = await desk.api.post(
        f"{ADMIN}/users/{advisor.id}/grant-platform-admin", headers=bearer(admin.id)
    )
    assert_problem(twice, 409, "CONFLICT")
    revoked = await admin_post(desk.api, admin, f"/users/{advisor.id}/revoke-platform-admin")
    assert revoked["user"]["is_platform_admin"] is False
    not_admin = await desk.api.post(
        f"{ADMIN}/users/{advisor.id}/revoke-platform-admin", headers=bearer(admin.id)
    )
    assert_problem(not_admin, 409, "CONFLICT")
    actions = sorted(row.action for row in await audit_rows(db))  # one frozen instant
    assert actions == ["user.platform_admin_granted", "user.platform_admin_revoked"]


async def test_e70_needs_an_active_account(desk: Desk, db: Database, admin: UserRecord) -> None:
    inactive = await make_user(db, full_name="Dormant Account", active=False)
    response = await desk.api.post(
        f"{ADMIN}/users/{inactive.id}/grant-platform-admin", headers=bearer(admin.id)
    )
    body = assert_problem(response, 422, "VALIDATION_ERROR")
    assert [(error["field"], error["code"]) for error in body["errors"]] == [
        ("path.user_id", "inactive_account")
    ]
    assert await audit_rows(db) == []


async def test_e71_refuses_revoking_yourself(desk: Desk, admin: UserRecord, db: Database) -> None:
    await make_admin(db, full_name="Ali Raza")  # not the last admin: self is refused anyway
    response = await desk.api.post(
        f"{ADMIN}/users/{admin.id}/revoke-platform-admin", headers=bearer(admin.id)
    )
    assert_problem(response, 403, "FORBIDDEN")
    me = await desk.api.get("/api/v1/me", headers=bearer(admin.id))
    assert me.json()["is_platform_admin"] is True


async def test_the_last_active_admin_can_be_neither_revoked_nor_deactivated(
    db: Database, admin: UserRecord
) -> None:
    """The rule itself, at the identity port: an actor other than the target (here one that is
    not an admin, as a revoked admin's stale request would be) meets the last active admin."""
    stranger = await make_user(db, full_name="Stale Request")
    async with unit_of_work(db) as uow:
        with pytest.raises(Conflict) as revoked:
            await identity_service.change_platform_admin(
                uow, actor_user_id=stranger.id, user_id=admin.id, is_platform_admin=False
            )
    assert revoked.value.detail == LAST_ADMIN
    async with unit_of_work(db) as uow:
        with pytest.raises(Conflict) as deactivated:
            await identity_service.change_user_active(
                uow, actor_user_id=stranger.id, user_id=admin.id, is_active=False, reason=REASON
            )
    assert deactivated.value.detail == LAST_ADMIN
    async with db.sessionmaker() as session:
        still = await identity_service.get_active_user(session, admin.id)
    assert still is not None
    assert still.is_platform_admin


@pytest.mark.concurrency
@pytest.mark.parametrize("lever", ["revoke-platform-admin", "deactivate"])
async def test_two_admins_cannot_demote_each_other_at_once(
    desk: Desk, db: Database, admin: UserRecord, lever: str
) -> None:
    """Spec 19 §1/§7: both requests queue on the active admins' row locks; the first wins, the
    second re-reads the committed change, sees one admin left and gets 409."""
    ali = await make_admin(db, full_name="Ali Raza")
    body = {"reason": REASON} if lever == "deactivate" else None
    async with hold_row_lock(db, "users", id=admin.id):
        first = asyncio.create_task(
            desk.api.post(f"{ADMIN}/users/{ali.id}/{lever}", headers=bearer(admin.id), json=body)
        )
        second = asyncio.create_task(
            desk.api.post(f"{ADMIN}/users/{admin.id}/{lever}", headers=bearer(ali.id), json=body)
        )
        await wait_for_lock_waiters(db, 2)
    responses = [await first, await second]
    statuses = sorted(response.status_code for response in responses)
    assert statuses == [200, 409], [response.text for response in responses]
    loser = next(response for response in responses if response.status_code == 409)
    assert assert_problem(loser, 409, "CONFLICT")["detail"] == LAST_ADMIN
    async with db.sessionmaker() as session:
        users = await identity_service.get_users_by_ids(session, [admin.id, ali.id])
    survivors = [user for user in users.values() if user.is_platform_admin and user.is_active]
    assert len(survivors) == 1


async def test_deactivating_a_shops_only_owner_is_allowed(
    desk: Desk, world: World, admin: UserRecord
) -> None:
    """Spec 19 §7: allowed (the console warns first); the shop keeps working for its staff."""
    await admin_post(
        desk.api, admin, f"/users/{world.owner.id}/deactivate", {"reason": "Owner account sold"}
    )
    shop = await desk.get(world.advisor.id, desk.shop_path())
    assert shop["id"] == str(world.shop_id)


async def test_membership_kinds_follow_live_memberships(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    newcomer = await make_user(db, full_name="New Hire")
    assert newcomer.email in emails(
        await admin_get(desk.api, admin, "/users", kind="CUSTOMER", limit=100)
    )
    await add_member(db, world.shop, MembershipRole.TECHNICIAN, user=newcomer)
    assert newcomer.email in emails(
        await admin_get(desk.api, admin, "/users", kind="STAFF", limit=100)
    )

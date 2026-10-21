"""The audit catalogue end to end (spec 19 §3.2, §3.3, §9 "Audit"; D95).

- Every catalogue action writes exactly one row, with its category, actor, actor role, shop,
  target and metadata.
- The row is written in the action's own transaction: a rolled-back action leaves none.
- Failed and rate-limited logins are recorded although the login fails.
- The request's IP, user agent and request id are captured; scripts leave them empty.
- No password, token or hash ever reaches a row.
"""

import json
from collections import Counter
from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select

from app.core.database import Database
from app.modules.audit.models import AuditEvent
from app.modules.bookings.models import Booking
from app.modules.identity import service as identity_service
from app.modules.identity.schemas import UserRecord
from app.shared.enums import AuditActorRole, AuditCategory, AuditTargetType, BookingStatus
from app.shared.uow import UnitOfWork
from tests.assertions import assert_problem
from tests.modules.admin.support import ADMIN, REASON, admin_get, admin_post, audit_rows
from tests.modules.bookings.support import Desk, World, drive_booking_to, events_of
from tests.modules.identity.builders import TEST_PASSWORD, bearer, make_user, unique_email
from tests.modules.shops.builders import make_services, make_shop, shop_payload, week

LOGIN = "/api/v1/auth/login"
LOGOUT = "/api/v1/auth/logout"
REGISTER = "/api/v1/auth/register-owner"


async def _register(api: httpx.AsyncClient, email: str, password: str = TEST_PASSWORD) -> str:
    response = await api.post(
        REGISTER, json={"full_name": "Nadia Owner", "email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    api.cookies.clear()
    token: str = response.json()["access_token"]
    return token


async def _login(
    api: httpx.AsyncClient, email: str, password: str, **headers: str
) -> httpx.Response:
    response = await api.post(LOGIN, json={"email": email, "password": password}, headers=headers)
    api.cookies.clear()
    return response


async def test_every_catalogue_action_writes_exactly_one_row(  # noqa: PLR0915 - the catalogue
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    api = desk.api
    expected: Counter[str] = Counter()

    # AUTH
    email = unique_email("nadia")
    token = await _register(api, email)
    expected["auth.owner_registered"] += 1
    assert (await _login(api, email, TEST_PASSWORD)).status_code == 200
    expected["auth.login_succeeded"] += 1
    assert (await _login(api, email, "wrong-password-0")).status_code == 401
    expected["auth.login_failed"] += 1
    assert (await api.post(LOGOUT, headers={"Authorization": f"Bearer {token}"})).status_code == 204
    expected["auth.logged_out"] += 1

    # USER and BOOKING: the wizard creates an account and a booking
    journey = await desk.book()
    expected["user.customer_created"] += 1
    expected["booking.create"] += 1
    await desk.act(world.advisor, journey.id, "confirm")
    expected["booking.confirm"] += 1

    # SHOP + MEMBERSHIP, by the new owner
    owner_headers = {"Authorization": f"Bearer {token}"}
    created = await api.post(
        "/api/v1/shops", json=shop_payload(name="Nadia Motors"), headers=owner_headers
    )
    assert created.status_code == 201, created.text
    shop_id = created.json()["id"]
    expected["shop.created"] += 1
    patched = await api.patch(
        f"/api/v1/shops/{shop_id}", json={"name": "Nadia Motors & Sons"}, headers=owner_headers
    )
    assert patched.status_code == 200, patched.text
    expected["shop.updated"] += 1
    hours = await api.put(
        f"/api/v1/shops/{shop_id}/working-hours",
        json={"working_hours": week("10:00", "17:00")},
        headers=owner_headers,
    )
    assert hours.status_code == 200, hours.text
    expected["shop.working_hours_replaced"] += 1
    member = await api.post(
        f"/api/v1/shops/{shop_id}/members",
        json={
            "email": unique_email("tech"),
            "full_name": "Tariq Tech",
            "role": "TECHNICIAN",
            "password": "member-password-99",
        },
        headers=owner_headers,
    )
    assert member.status_code == 201, member.text
    expected["membership.added"] += 1
    member_url = f"/api/v1/shops/{shop_id}/members/{member.json()['membership_id']}"
    for body, action in (
        ({"role": "PARTS_PERSON"}, "membership.role_changed"),
        ({"is_active": False}, "membership.deactivated"),
        ({"is_active": True}, "membership.reactivated"),
    ):
        response = await api.patch(member_url, json=body, headers=owner_headers)
        assert response.status_code == 200, response.text
        expected[action] += 1

    # The platform admin's levers and audited reads
    await admin_post(api, admin, f"/shops/{shop_id}/suspend", {"reason": REASON})
    expected["shop.suspended"] += 1
    await admin_post(api, admin, f"/shops/{shop_id}/reactivate")
    expected["shop.reactivated"] += 1
    customer_id = journey.customer.user_id
    await admin_post(api, admin, f"/users/{customer_id}/deactivate", {"reason": REASON})
    expected["user.deactivated"] += 1
    await admin_post(api, admin, f"/users/{customer_id}/reactivate")
    expected["user.reactivated"] += 1
    owner = await api.get("/api/v1/me", headers=owner_headers)
    owner_id = owner.json()["id"]
    await admin_post(api, admin, f"/users/{owner_id}/grant-platform-admin")
    expected["user.platform_admin_granted"] += 1
    await admin_post(api, admin, f"/users/{owner_id}/revoke-platform-admin")
    expected["user.platform_admin_revoked"] += 1
    await admin_get(api, admin, f"/users/{customer_id}")
    expected["admin.user_viewed"] += 1
    await admin_get(api, admin, f"/bookings/{journey.id}")
    expected["admin.booking_viewed"] += 1
    export = await api.get(f"{ADMIN}/audit-events/export", headers=bearer(admin.id))
    assert export.status_code == 200
    expected["admin.audit_exported"] += 1

    rows = await audit_rows(db)
    assert Counter(row.action for row in rows) == expected
    # Every non-booking action of spec 19 §3.3 but `auth.login_rate_limited` (tested on its own).
    assert len(expected) == 23
    for row in rows:
        assert row.category == AuditCategory(row.action.split(".")[0].upper()), row.action
        assert row.request_id, row.action  # every one of them came through HTTP
        assert row.summary.endswith("."), row.summary


async def test_rows_carry_actor_role_shop_target_and_metadata(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.CONFIRMED)
    await desk.act(
        world.advisor,
        journey.id,
        "assign-technician",
        {"technician_user_id": str(world.technician.id)},
    )
    customer = journey.customer
    created = (await audit_rows(db, action="user.customer_created"))[0]
    assert (created.actor_user_id, created.actor_role, created.shop_id) == (
        customer.user_id,
        AuditActorRole.CUSTOMER,
        None,
    )
    assert (created.target_type, created.target_id, created.target_label) == (
        AuditTargetType.USER,
        customer.user_id,
        customer.email,
    )
    booked = (await audit_rows(db, action="booking.create"))[0]
    assert (booked.shop_id, booked.target_type, booked.target_label) == (
        world.shop_id,
        AuditTargetType.BOOKING,
        journey.reference,
    )
    assert booked.metadata_ == {"from_status": None, "to_status": "PENDING", "version": 1}
    assert booked.summary == f"Ahmed booked {journey.reference} at Lahore Auto Care."
    assigned = (await audit_rows(db, action="booking.assign_technician"))[0]
    assert (assigned.actor_user_id, assigned.actor_role) == (
        world.advisor.id,
        AuditActorRole.SERVICE_ADVISOR,
    )
    assert assigned.metadata_ == {"from_status": "CONFIRMED", "to_status": "ASSIGNED", "version": 3}
    declined = await drive_booking_to(desk, BookingStatus.CANCELLED)
    (decline,) = [
        row
        for row in await audit_rows(db, action="booking.decline")
        if row.target_label == declined.reference
    ]
    assert decline.metadata_["note"] == "Both bays are booked that morning."


async def test_one_row_per_booking_event_through_a_whole_job(
    desk: Desk, world: World, db: Database
) -> None:
    """`booking.<action>` mirrors `booking_events` one to one (spec 19 §3.2), the PO receipt's
    `RECEIVE_PARTS` included."""
    journey = await drive_booking_to(desk, BookingStatus.COMPLETED)
    events = await events_of(db, journey.id)
    rows = [
        row
        for row in await audit_rows(db)
        if row.category == AuditCategory.BOOKING and row.target_label == journey.reference
    ]
    assert Counter(row.action for row in rows) == Counter(
        f"booking.{event.action.value.lower()}" for event in events
    )
    assert "booking.receive_parts" in {row.action for row in rows}
    assert all(row.shop_id == world.shop_id for row in rows)


async def test_a_rolled_back_action_leaves_no_row(
    db_app: FastAPI, db: Database, admin: UserRecord
) -> None:
    """The row is written in the action's transaction: rolled back together, committed together."""
    target = await make_user(db, full_name="Promoted Later")
    bus = db_app.state.event_bus
    async with db.sessionmaker() as session:
        uow = UnitOfWork(session, bus)
        await identity_service.change_platform_admin(
            uow, actor_user_id=admin.id, user_id=target.id, is_platform_admin=True
        )
        in_transaction = await session.execute(select(func.count()).select_from(AuditEvent))
        assert in_transaction.scalar_one() == 1  # written by the handler, not yet committed
        await uow.rollback()
    assert await audit_rows(db) == []
    async with db.sessionmaker() as session:
        unchanged = await identity_service.get_user(session, target.id)
    assert unchanged is not None
    assert not unchanged.is_platform_admin
    async with db.sessionmaker() as session:
        uow = UnitOfWork(session, bus)
        await identity_service.change_platform_admin(
            uow, actor_user_id=admin.id, user_id=target.id, is_platform_admin=True
        )
        await uow.commit()
    (row,) = await audit_rows(db)
    assert (row.action, row.target_id) == ("user.platform_admin_granted", target.id)


async def test_a_failed_booking_rolls_its_new_account_and_audit_rows_back(
    desk: Desk, db: Database
) -> None:
    """Wizard case B on a full slot: the account and `user.customer_created` vanish with the
    409 (D32, spec 19 §3.2)."""
    tiny = await make_shop(db, name="One Bay Garage", capacity=1)
    services = await make_services(db, tiny, ("Oil change",))
    slot_body = desk.booking_body(shop_id=tiny.id, services=services)
    first = dict(
        slot_body,
        customer={"full_name": "First", "email": unique_email("first"), "password": TEST_PASSWORD},
    )
    assert (await desk.wizard(first, headers={"X-Real-IP": "2001:db8::f1"})).status_code == 201
    late_email = unique_email("late")
    late = dict(
        slot_body, customer={"full_name": "Late", "email": late_email, "password": TEST_PASSWORD}
    )
    response = await desk.wizard(late, headers={"X-Real-IP": "2001:db8::f2"})
    assert_problem(response, 409, "SLOT_FULL")
    async with db.sessionmaker() as session:
        assert await identity_service.find_user_by_email(session, late_email) is None
    created = await audit_rows(db, action="user.customer_created")
    assert [row.target_label for row in created] == [first["customer"]["email"]]
    assert len(await audit_rows(db, action="booking.create")) == 1


async def test_failed_and_rate_limited_logins_persist(desk: Desk, db: Database) -> None:
    user = await make_user(db, full_name="Locked Out")
    mixed_case = user.email.upper()
    for _ in range(5):
        assert_problem(
            await _login(desk.api, mixed_case, "wrong-password-1"), 401, "INVALID_CREDENTIALS"
        )
    blocked = await _login(desk.api, user.email, TEST_PASSWORD)  # even with the right password
    assert_problem(blocked, 429, "RATE_LIMITED")
    failed = await audit_rows(db, action="auth.login_failed")
    limited = await audit_rows(db, action="auth.login_rate_limited")
    assert (len(failed), len(limited)) == (5, 1)
    for row in (*failed, *limited):
        assert row.metadata_ == {"email": user.email}  # lower-cased (D62)
        assert (row.actor_user_id, row.actor_role, row.target_type) == (
            None,
            AuditActorRole.ANONYMOUS,
            None,
        )
    assert limited[0].summary == f"Sign-in for {user.email} blocked after too many failed attempts."
    assert await audit_rows(db, action="auth.login_succeeded") == []
    unknown = await _login(desk.api, "nobody@bayflow.test", "whatever-password")
    assert_problem(unknown, 401, "INVALID_CREDENTIALS")
    assert len(await audit_rows(db, action="auth.login_failed")) == 6  # unknown e-mails too


def _wizard_sign_in(desk: Desk, email: str, password: str, **body: Any) -> dict[str, Any]:
    """A wizard body for an existing e-mail (cases C/D, D32)."""
    return dict(
        desk.booking_body(**body),
        customer={"full_name": "Wizard Customer", "email": email, "password": password},
    )


async def test_failed_wizard_sign_ins_are_recorded_on_their_own(desk: Desk, db: Database) -> None:
    """D100: a wrong password in the wizard (409) records `auth.login_failed` in a transaction of
    its own, which survives the booking's rollback; nothing else commits. The per-account limiter
    is unchanged: the sixth attempt is blocked (429) and recorded as `auth.login_rate_limited`."""
    user = await make_user(db, full_name="Careful Customer")
    for index in range(5):
        body = _wizard_sign_in(desk, user.email.upper(), f"wrong-password-{index}")
        response = await desk.wizard(body, headers={"X-Real-IP": f"198.51.100.{index}"})
        assert_problem(response, 409, "EMAIL_ALREADY_REGISTERED")
    blocked = await desk.wizard(_wizard_sign_in(desk, user.email, TEST_PASSWORD))
    assert_problem(blocked, 429, "RATE_LIMITED")  # even the right password
    rows = await audit_rows(db)
    assert Counter(row.action for row in rows) == {
        "auth.login_failed": 5,
        "auth.login_rate_limited": 1,
    }
    for row in rows:
        assert row.metadata_ == {"email": user.email}
        assert (row.actor_user_id, row.actor_role) == (None, AuditActorRole.ANONYMOUS)
    async with db.sessionmaker() as session:
        bookings = await session.execute(select(func.count()).select_from(Booking))
        assert bookings.scalar_one() == 0


async def test_a_wizard_sign_in_is_recorded_with_its_booking(desk: Desk, db: Database) -> None:
    """D100: a successful wizard sign-in publishes `auth.login_succeeded` in the booking's
    transaction: it commits with the booking, and is lost with a booking that fails later."""
    user = await make_user(db, full_name="Returning Customer")
    booked = await desk.wizard(_wizard_sign_in(desk, user.email, TEST_PASSWORD))
    assert booked.status_code == 201, booked.text
    rows = await audit_rows(db)
    assert sorted(row.action for row in rows) == ["auth.login_succeeded", "booking.create"]
    (signed_in,) = [row for row in rows if row.action == "auth.login_succeeded"]
    assert (signed_in.actor_user_id, signed_in.target_id) == (user.id, user.id)

    tiny = await make_shop(db, name="One Bay Garage", capacity=1)
    services = await make_services(db, tiny, ("Oil change",))
    first = await desk.wizard(
        _wizard_sign_in(desk, user.email, TEST_PASSWORD, shop_id=tiny.id, services=services)
    )
    assert first.status_code == 201, first.text
    late = await make_user(db, full_name="Late Customer")
    slot = first.json()["booking"]["slot_start"]
    full = await desk.wizard(
        _wizard_sign_in(
            desk,
            late.email,
            TEST_PASSWORD,
            shop_id=tiny.id,
            services=services,
            slot=datetime.fromisoformat(slot),
        )
    )
    assert_problem(full, 409, "SLOT_FULL")
    sign_ins = await audit_rows(db, action="auth.login_succeeded")
    assert [row.actor_user_id for row in sign_ins] == [user.id, user.id]  # the late one rolled back


async def test_logout_is_recorded_only_when_it_names_an_active_user(
    desk: Desk, db: Database
) -> None:
    user = await make_user(db, full_name="Leaving Soon")
    assert (await desk.api.post(LOGOUT)).status_code == 204
    desk.api.cookies.set("bf_session", "garbage")
    assert (await desk.api.post(LOGOUT)).status_code == 204
    desk.api.cookies.clear()
    assert (await desk.api.post(LOGOUT, headers={"Authorization": "Basic x"})).status_code == 204
    assert await audit_rows(db) == []
    assert (await desk.api.post(LOGOUT, headers=bearer(user.id))).status_code == 204
    (row,) = await audit_rows(db)
    assert (row.action, row.actor_user_id, row.target_id) == ("auth.logged_out", user.id, user.id)
    assert row.summary == "Leaving Soon signed out."


async def test_the_request_context_is_captured(desk: Desk, db: Database) -> None:
    user = await make_user(db)
    long_agent = "Mozilla/5.0 (X11; Linux x86_64) " + "x" * 400
    response = await _login(
        desk.api,
        user.email,
        TEST_PASSWORD,
        **{"X-Real-IP": "203.0.113.7", "User-Agent": long_agent, "X-Request-ID": "audit-req-1"},
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "audit-req-1"
    (row,) = await audit_rows(db, action="auth.login_succeeded")
    assert (str(row.ip), row.request_id) == ("203.0.113.7", "audit-req-1")
    assert row.user_agent == long_agent[:255]
    await _login(desk.api, user.email, TEST_PASSWORD, **{"X-Real-IP": "not-an-address"})
    await _login(desk.api, user.email, TEST_PASSWORD)  # no proxy header: the socket peer
    rows = await audit_rows(db, action="auth.login_succeeded")
    addresses = {None if row.ip is None else str(row.ip) for row in rows}
    assert addresses == {"203.0.113.7", None, "127.0.0.1"}  # a malformed header is dropped
    assert all(row.request_id for row in rows)


async def test_no_password_token_or_hash_reaches_a_row(
    desk: Desk, world: World, db: Database
) -> None:
    secrets = {"owner-password-777", "wrong-password-888", "member-password-999"}
    email = unique_email("secret")
    token = await _register(desk.api, email, "owner-password-777")
    await _login(desk.api, email, "wrong-password-888")
    login = await _login(desk.api, email, "owner-password-777")
    session_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    shop = await desk.api.post("/api/v1/shops", json=shop_payload(), headers=headers)
    await desk.api.post(
        f"/api/v1/shops/{shop.json()['id']}/members",
        json={
            "email": unique_email("member"),
            "full_name": "New Member",
            "role": "SERVICE_ADVISOR",
            "password": "member-password-999",
        },
        headers=headers,
    )
    journey = await desk.book()  # the wizard's password (TEST_PASSWORD)
    await desk.api.post(LOGOUT, headers=headers)
    rows = await audit_rows(db)
    assert len(rows) >= 8
    forbidden = {*secrets, TEST_PASSWORD, token, session_token, "$argon2", "password"}
    for row in rows:
        dumped = json.dumps(
            {
                "summary": row.summary,
                "label": row.target_label,
                "metadata": row.metadata_,
                "agent": row.user_agent,
            }
        ).lower()
        leaked = [value for value in forbidden if value.lower() in dumped]
        assert not leaked, (row.action, leaked)
    assert journey.reference in {row.target_label for row in rows}


async def test_scripts_have_no_request_context(db_app: FastAPI, db: Database) -> None:
    """Outside a request (scripts, the seed) the context columns stay empty (spec 19 §3.2)."""
    user = await make_user(db, full_name="Script Target")
    async with db.sessionmaker() as session:
        uow = UnitOfWork(session, db_app.state.event_bus)
        await identity_service.set_user_active(uow, user_id=user.id, is_active=False)
    (row,) = await audit_rows(db)
    assert (row.action, row.actor_user_id, row.actor_role) == (
        "user.deactivated",
        None,
        AuditActorRole.SYSTEM,
    )
    assert (row.ip, row.user_agent, row.request_id) == (None, None, None)
    assert row.summary == "BayFlow deactivated the account of Script Target."


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


async def test_shop_updates_record_only_the_changed_fields(
    desk: Desk, world: World, db: Database
) -> None:
    url = desk.shop_path()
    owner = bearer(world.owner.id)
    same = await desk.api.patch(
        url, json={"name": "Lahore Auto Care", "slot_capacity": 50}, headers=owner
    )
    assert same.status_code == 200
    assert await audit_rows(db) == []  # nothing changed, nothing recorded
    changed = await desk.api.patch(
        url,
        json={"name": "Lahore Auto Care Gulberg", "slot_capacity": 40, "city": "Lahore"},
        headers=owner,
    )
    assert changed.status_code == 200, changed.text
    (row,) = await audit_rows(db, action="shop.updated")
    assert row.metadata_ == {
        "changes": {
            "name": {"from": "Lahore Auto Care", "to": "Lahore Auto Care Gulberg"},
            "slot_capacity": {"from": 50, "to": 40},
        }
    }
    assert row.summary == "Fatima Raza updated Lahore Auto Care Gulberg (name, slot_capacity)."
    assert "password" not in _keys(row.metadata_)

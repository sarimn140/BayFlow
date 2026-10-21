"""`/api/v1/auth/*` over HTTP (spec 03 §4.3, spec 04 "Authentication flows", `modules/identity.md`).

Covers IDN-01…IDN-04, IDN-06 and the identity halves of SEC-16, SEC-17, SEC-22…SEC-27, SEC-29,
SEC-30, SEC-38, SEC-44, SEC-48 and API-12.
"""

import asyncio
import base64
import json
import logging
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import httpx
import jwt
import pytest
from fastapi import FastAPI
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import func, select, text, update

import app.shared.auth as auth_module
from app.core.database import Database
from app.core.security import SESSION_COOKIE_NAME
from app.modules.identity import service as identity_service
from app.modules.identity.events import LoggedOut
from app.modules.identity.models import User
from app.shared.clock import SimulatedClock
from app.shared.enums import MembershipRole
from app.shared.uow import UnitOfWork
from tests.assertions import assert_problem
from tests.conftest import make_settings
from tests.lockgate import wait_for_lock_waiters
from tests.modules.admin.support import audit_rows
from tests.modules.identity.builders import (
    TEST_PASSWORD,
    bearer,
    field_errors,
    make_user,
    unique_email,
)
from tests.modules.shops.builders import add_member, make_shop, set_member_active

pytestmark = pytest.mark.db

REGISTER = "/api/v1/auth/register-owner"
LOGIN = "/api/v1/auth/login"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/me"
DEMO_PASSWORD = "BayFlow@2026"  # 12 characters: the D10 minimum (glossary §14)
WEEK_SECONDS = 604_800
REGISTERED_DETAIL = "This e-mail already has a BayFlow account. Log in, then create your shop."


def registration(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "full_name": "Fatima Raza",
        "email": unique_email("owner"),
        "password": DEMO_PASSWORD,
    }
    body.update(overrides)
    return body


async def stored_user(db: Database, email: str) -> User:
    async with db.sessionmaker() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        session.expunge(user)
        return user


def token_claims(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    padded = payload + "=" * (-len(payload) % 4)
    claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
    return claims


@pytest.fixture
def secure_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    """`COOKIE_SECURE=true` for the cookie helpers of `app.shared.auth` (SEC-23)."""
    settings = make_settings(cookie_secure=True)
    monkeypatch.setattr(auth_module, "get_settings", lambda: settings)


@pytest.fixture
def argon2_verifications(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts every Argon2 verification (real ones and the dummy one) — SEC-22."""
    calls: list[int] = []
    lock = threading.Lock()
    original = Argon2Hasher.verify

    def counting_verify(self: Argon2Hasher, password: str | bytes, digest: str | bytes) -> bool:
        with lock:
            calls.append(1)
        return original(self, password, digest)

    monkeypatch.setattr(Argon2Hasher, "verify", counting_verify)
    return calls


# --- Owner registration ---------------------------------------------------------------------------


async def test_idn01_register_owner_logs_in_without_memberships(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    body = registration(phone="+92 300 1234567")
    response = await db_client.post(REGISTER, json=body)
    assert response.status_code == 201, response.text
    session = response.json()
    assert set(session) == {"access_token", "token_type", "expires_in", "user"}
    assert session["token_type"] == "bearer"
    assert session["expires_in"] == WEEK_SECONDS
    assert set(session["user"]) == {"id", "email", "full_name", "phone"}  # no memberships (D81)
    assert session["user"]["email"] == body["email"]
    assert session["user"]["phone"] == "+923001234567"  # normalised Phone (spec 03 §1.5)
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}={session['access_token']};")

    user = await stored_user(db, body["email"])
    assert user.last_login_at == clock.now()  # a session starts (identity §7.3)
    assert user.is_active

    me = await db_client.get(ME)  # the cookie set above authenticates
    assert me.status_code == 200
    assert me.json()["memberships"] == []


async def test_register_owner_with_an_existing_email_is_409(db_client: httpx.AsyncClient) -> None:
    body = registration()
    assert (await db_client.post(REGISTER, json=body)).status_code == 201
    again = await db_client.post(REGISTER, json=registration(email=body["email"].upper()))
    problem = assert_problem(again, 409, "EMAIL_ALREADY_REGISTERED")
    assert problem["detail"] == REGISTERED_DETAIL
    assert "set-cookie" not in again.headers


@asynccontextmanager
async def uncommitted_account(db: Database, email: str) -> AsyncIterator[None]:
    """A gate for the registration race: an uncommitted `users` row with `email`. Concurrent
    registrations don't see it (Read Committed), pass the pre-check, and then wait on its
    `uq_users_email` entry, so both reach the INSERT before either commits."""
    async with db.engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash, full_name) "
                    "VALUES (:id, :email, 'gate-not-a-hash', 'Gate')"
                ),
                {"id": uuid.uuid4(), "email": email},
            )
            yield
        finally:
            await transaction.rollback()


async def test_a_concurrent_registration_race_answers_with_the_registration_detail(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    email = unique_email("race")
    async with uncommitted_account(db, email):
        racers = [
            asyncio.create_task(
                db_client.post(
                    REGISTER,
                    json=registration(email=email, full_name=f"Racer {n}"),
                    headers={"X-Real-IP": f"203.0.113.{n + 1}"},
                )
            )
            for n in range(2)
        ]
        await wait_for_lock_waiters(db, 2)  # both passed the pre-check and wait on the INSERT
    responses = sorted(await asyncio.gather(*racers), key=lambda response: response.status_code)
    assert [response.status_code for response in responses] == [201, 409]
    problem = assert_problem(responses[1], 409, "EMAIL_ALREADY_REGISTERED")
    assert problem["detail"] == REGISTERED_DETAIL  # not the generic constraint-map text
    assert "set-cookie" not in responses[1].headers
    async with db.sessionmaker() as session:
        accounts = await session.scalar(
            select(func.count()).select_from(User).where(User.email == email)
        )
    assert accounts == 1
    winner = responses[0].json()["user"]
    assert (await stored_user(db, email)).id == uuid.UUID(winner["id"])


@pytest.mark.parametrize(
    "smuggled",
    [
        {"role": "OWNER"},
        {"shop_id": "3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c"},
        {"memberships": [{"role": "OWNER"}]},
        {"is_active": False},
    ],
)
async def test_sec16_sec17_register_owner_refuses_extra_fields(
    db_client: httpx.AsyncClient, db: Database, smuggled: dict[str, Any]
) -> None:
    body = registration(**smuggled)
    response = await db_client.post(REGISTER, json=body)
    problem = assert_problem(response, 422, "VALIDATION_ERROR")
    assert field_errors(problem) == [(next(iter(smuggled)), "extra_forbidden")]
    async with db.sessionmaker() as session:
        count = await session.scalar(select(User.id).where(User.email == body["email"]))
    assert count is None  # nothing created


@pytest.mark.parametrize(
    ("password", "status", "code"),
    [
        ("A" * 11, 422, "string_too_short"),
        ("A" * 129, 422, "string_too_long"),
        (DEMO_PASSWORD, 201, None),
        ("x" * 128, 201, None),
        ("  spaces kept  ", 201, None),
    ],
)
async def test_sec29_password_policy_on_registration(
    db_client: httpx.AsyncClient, password: str, status: int, code: str | None
) -> None:
    response = await db_client.post(REGISTER, json=registration(password=password))
    if code is None:
        assert response.status_code == status, response.text
        return
    problem = assert_problem(response, status, "VALIDATION_ERROR")
    assert field_errors(problem) == [("password", code)]
    assert password not in response.text  # no `input` echoed (spec 04)
    assert "ctx" not in problem["errors"][0]


async def test_sec29_never_trims_passwords(db_client: httpx.AsyncClient) -> None:
    body = registration(password="  padded password  ")
    assert (await db_client.post(REGISTER, json=body)).status_code == 201
    trimmed = await db_client.post(
        LOGIN, json={"email": body["email"], "password": "padded password"}
    )
    assert_problem(trimmed, 401, "INVALID_CREDENTIALS")
    exact = await db_client.post(LOGIN, json={"email": body["email"], "password": body["password"]})
    assert exact.status_code == 200


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("full_name", "   ", "string_too_short"),
        ("full_name", "x" * 121, "string_too_long"),
        ("phone", "12345", "string_too_short"),
        ("phone", "+92 300 12a4567", "string_pattern_mismatch"),
        ("email", "x" * 250 + "@b.test", "string_too_long"),
    ],
)
async def test_registration_field_limits(
    db_client: httpx.AsyncClient, field: str, value: str, code: str
) -> None:
    response = await db_client.post(REGISTER, json=registration(**{field: value}))
    problem = assert_problem(response, 422, "VALIDATION_ERROR")
    assert field_errors(problem) == [(field, code)]


async def test_registration_trims_the_name(db_client: httpx.AsyncClient) -> None:
    response = await db_client.post(REGISTER, json=registration(full_name="  Fatima Raza  "))
    assert response.json()["user"]["full_name"] == "Fatima Raza"


# --- E-mail type (D62) ----------------------------------------------------------------------------


async def test_sec48_email_is_normalised_on_register_and_login(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    mixed = " Fatima.Owner@BayFlow.TEST "
    registered = await db_client.post(REGISTER, json=registration(email=mixed))
    assert registered.status_code == 201
    assert registered.json()["user"]["email"] == "fatima.owner@bayflow.test"
    assert (await stored_user(db, "fatima.owner@bayflow.test")).email == "fatima.owner@bayflow.test"
    login = await db_client.post(LOGIN, json={"email": mixed, "password": DEMO_PASSWORD})
    assert login.status_code == 200


@pytest.mark.parametrize(
    "email", ["x@localhost", "bad@@x", "x@example.invalid", "x@foo.localhost", "no-at-sign"]
)
async def test_sec48_api12_malformed_and_special_use_emails_are_422(
    db_client: httpx.AsyncClient, email: str
) -> None:
    for path, body in (
        (REGISTER, registration(email=email)),
        (LOGIN, {"email": email, "password": DEMO_PASSWORD}),
    ):
        problem = assert_problem(await db_client.post(path, json=body), 422, "VALIDATION_ERROR")
        assert [field for field, _ in field_errors(problem)] == ["email"]


@pytest.mark.parametrize(
    "email", ["smoke+17@bayflow.test", "ahmed@mail.com", "Fatima.Owner@BayFlow.TEST"]
)
async def test_api12_demo_and_real_addresses_are_accepted(
    db_client: httpx.AsyncClient, email: str
) -> None:
    response = await db_client.post(REGISTER, json=registration(email=email))
    assert response.status_code == 201, response.text
    assert response.json()["user"]["email"] == email.lower()
    login = await db_client.post(LOGIN, json={"email": email, "password": DEMO_PASSWORD})
    assert login.status_code == 200


# --- Login ----------------------------------------------------------------------------------------


async def test_login_returns_the_session_and_sets_the_cookie(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    user = await make_user(db, phone="+92 300 7654321")
    clock.advance(timedelta(hours=1))
    response = await db_client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD})
    assert response.status_code == 200
    session = response.json()
    assert session["user"] == {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "phone": "+923007654321",
    }
    assert session["expires_in"] == WEEK_SECONDS
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}={session['access_token']};")
    assert "HttpOnly" in cookie
    assert f"Max-Age={WEEK_SECONDS}" in cookie
    assert "Path=/" in cookie
    assert "SameSite=lax" in cookie
    assert "Domain" not in cookie
    assert (await stored_user(db, user.email)).last_login_at == clock.now()

    db_client.cookies.clear()
    me = await db_client.get(ME, headers={"Authorization": f"Bearer {session['access_token']}"})
    assert me.json()["id"] == str(user.id)


async def test_login_never_reads_credentials(db_client: httpx.AsyncClient, db: Database) -> None:
    user = await make_user(db)
    response = await db_client.post(
        LOGIN,
        json={"email": user.email, "password": TEST_PASSWORD},
        headers={"Authorization": "Bearer not-a-jwt"},  # public routes ignore it (spec 03 §1.2)
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("password", "code"), [("", "string_too_short"), ("x" * 129, "string_too_long")]
)
async def test_login_password_is_1_to_128_characters(
    db_client: httpx.AsyncClient, password: str, code: str
) -> None:
    response = await db_client.post(
        LOGIN, json={"email": "someone@bayflow.test", "password": password}
    )
    problem = assert_problem(response, 422, "VALIDATION_ERROR")
    assert field_errors(problem) == [("password", code)]


async def test_login_accepts_a_short_existing_password_length(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    """The D10 policy applies to new passwords only: an 11-character login attempt is a 401."""
    user = await make_user(db)
    response = await db_client.post(LOGIN, json={"email": user.email, "password": "A" * 11})
    assert_problem(response, 401, "INVALID_CREDENTIALS")


async def test_sec22_failures_are_identical_with_exactly_one_argon2_verify(
    db_client: httpx.AsyncClient, db: Database, argon2_verifications: list[int]
) -> None:
    known = await make_user(db)
    inactive = await make_user(db, active=False)
    attempts = [
        {"email": unique_email("nobody"), "password": TEST_PASSWORD},  # unknown e-mail
        {"email": known.email, "password": "wrong-password-123"},  # wrong password
        {"email": inactive.email, "password": TEST_PASSWORD},  # deactivated, right password
    ]
    bodies = []
    for attempt in attempts:
        before = len(argon2_verifications)
        response = await db_client.post(LOGIN, json=attempt)
        bodies.append(assert_problem(response, 401, "INVALID_CREDENTIALS"))
        assert response.headers["www-authenticate"] == "Bearer"
        assert "set-cookie" not in response.headers
        assert len(argon2_verifications) - before == 1
    assert bodies[0] == bodies[1] == bodies[2]
    assert bodies[0]["detail"] == "The e-mail or password is incorrect."


async def test_sec24_token_payload_and_lifetime(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    user = await make_user(db)
    response = await db_client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD})
    claims = token_claims(response.json()["access_token"])
    assert set(claims) == {"sub", "iat", "exp", "typ"}
    assert claims["sub"] == str(user.id)
    assert claims["typ"] == "session"
    assert claims["iat"] == int(clock.now().timestamp())
    assert claims["exp"] - claims["iat"] == WEEK_SECONDS
    header = jwt.get_unverified_header(response.json()["access_token"])
    assert header["alg"] == "HS256"


async def test_sec25_the_session_expires_by_the_app_clock(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    user = await make_user(db)
    response = await db_client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD})
    token = response.json()["access_token"]
    db_client.cookies.clear()
    headers = {"Authorization": f"Bearer {token}"}
    clock.advance(timedelta(days=7) - timedelta(seconds=1))
    assert (await db_client.get(ME, headers=headers)).status_code == 200
    clock.advance(timedelta(seconds=1))
    assert_problem(await db_client.get(ME, headers=headers), 401, "UNAUTHENTICATED")
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    clock.set(clock.now() - timedelta(days=1))
    assert_problem(
        await db_client.get(ME, headers={"Authorization": f"Bearer {tampered}"}),
        401,
        "UNAUTHENTICATED",
    )


async def test_idn02_transparent_rehash_and_failed_login_never_rewrites(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    user = await make_user(db)
    outdated = PasswordHash((Argon2Hasher(time_cost=2, memory_cost=19_456, parallelism=1),)).hash(
        TEST_PASSWORD
    )
    async with db.sessionmaker() as session:
        await session.execute(update(User).where(User.id == user.id).values(password_hash=outdated))
        await session.commit()

    wrong = await db_client.post(LOGIN, json={"email": user.email, "password": "not-the-password"})
    assert wrong.status_code == 401
    assert (await stored_user(db, user.email)).password_hash == outdated

    right = await db_client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD})
    assert right.status_code == 200
    upgraded = (await stored_user(db, user.email)).password_hash
    assert upgraded != outdated
    assert upgraded.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert PasswordHash.recommended().verify(TEST_PASSWORD, upgraded)
    again = await db_client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD})
    assert again.status_code == 200
    assert (await stored_user(db, user.email)).password_hash == upgraded  # no needless rewrite


async def test_a_corrupted_stored_hash_is_a_failed_check(
    db_client: httpx.AsyncClient, db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    user = await make_user(db)
    async with db.sessionmaker() as session:
        await session.execute(
            update(User).where(User.id == user.id).values(password_hash="garbage")
        )
        await session.commit()
    with caplog.at_level(logging.WARNING):
        response = await db_client.post(
            LOGIN, json={"email": user.email, "password": TEST_PASSWORD}
        )
    assert_problem(response, 401, "INVALID_CREDENTIALS")
    assert "stored password hash is not recognised" in caplog.text
    assert "garbage" not in caplog.text


# --- Per-account limiter (D69) --------------------------------------------------------------------


async def test_idn03_the_limiter_is_cleared_by_a_success(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    user = await make_user(db)
    wrong = {"email": user.email, "password": "wrong-password-123"}
    right = {"email": user.email, "password": TEST_PASSWORD}
    sequence = [wrong] * 4 + [right] + [wrong] * 4 + [right] + [wrong] * 5 + [right]
    statuses = [(await db_client.post(LOGIN, json=body)).status_code for body in sequence]
    # a success clears the counter; after 5 failures even the right password is blocked
    assert statuses == [401] * 4 + [200] + [401] * 4 + [200] + [401] * 5 + [429]


async def test_sec27_a_concurrent_burst_reaches_argon2_at_most_five_times(
    db_client: httpx.AsyncClient, db: Database, argon2_verifications: list[int]
) -> None:
    """Each attempt is reserved atomically before any await (`modules/identity.md` §7.4): 30
    parallel wrong guesses from 30 IPs → 5 checks (401) and 25 x 429, never 30 checks."""
    user = await make_user(db)
    guesses = [
        db_client.post(
            LOGIN,
            json={"email": user.email, "password": f"wrong-password-{n:02d}"},
            headers={"X-Real-IP": f"198.51.100.{n + 1}"},
        )
        for n in range(30)
    ]
    responses = await asyncio.gather(*guesses)
    statuses = [response.status_code for response in responses]
    assert (statuses.count(401), statuses.count(429)) == (5, 25)
    assert len(argon2_verifications) == 5
    for response in responses:
        if response.status_code == 429:
            assert_problem(response, 429, "RATE_LIMITED")
            assert int(response.headers["retry-after"]) >= 1
    blocked = await db_client.post(
        LOGIN,
        json={"email": user.email, "password": TEST_PASSWORD},
        headers={"X-Real-IP": "198.51.100.200"},
    )
    assert_problem(blocked, 429, "RATE_LIMITED")  # still blocked, even with the right password
    assert len(argon2_verifications) == 5


async def test_sec27_failed_checks_are_limited_per_account_whatever_the_ip(
    db_client: httpx.AsyncClient, db: Database, argon2_verifications: list[int]
) -> None:
    user = await make_user(db)
    wrong = {"email": user.email, "password": "wrong-password-123"}
    for attempt in range(5):
        ip = "203.0.113.1" if attempt % 2 else "198.51.100.7"
        response = await db_client.post(LOGIN, json=wrong, headers={"X-Real-IP": ip})
        assert response.status_code == 401
    before = len(argon2_verifications)
    blocked = await db_client.post(
        LOGIN,
        json={"email": user.email, "password": TEST_PASSWORD},  # even the right password
        headers={"X-Real-IP": "192.0.2.99"},
    )
    problem = assert_problem(blocked, 429, "RATE_LIMITED")
    retry_after = int(blocked.headers["retry-after"])
    assert 1 <= retry_after <= 15 * 60
    assert problem["detail"] == f"Too many attempts. Try again in {retry_after} seconds."
    assert len(argon2_verifications) == before  # blocked before any hash work
    assert "set-cookie" not in blocked.headers


async def test_sec27_unknown_emails_are_counted_like_known_ones(
    db_client: httpx.AsyncClient,
) -> None:
    attempt = {"email": unique_email("ghost"), "password": "wrong-password-123"}
    for _ in range(5):
        assert (await db_client.post(LOGIN, json=attempt)).status_code == 401
    assert_problem(await db_client.post(LOGIN, json=attempt), 429, "RATE_LIMITED")


async def test_sec27_the_limit_is_released_by_a_reset(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    from app.core.security import reset_rate_limits  # noqa: PLC0415

    user = await make_user(db)
    for _ in range(5):
        await db_client.post(LOGIN, json={"email": user.email, "password": "wrong-password-1"})
    right = {"email": user.email, "password": TEST_PASSWORD}
    assert (await db_client.post(LOGIN, json=right)).status_code == 429
    reset_rate_limits()
    assert (await db_client.post(LOGIN, json=right)).status_code == 200


async def test_sec27_login_per_ip_ceiling(db_client: httpx.AsyncClient) -> None:
    headers = {"X-Real-IP": "203.0.113.50"}
    for _ in range(30):  # 30 per minute per IP, different accounts
        attempt = {"email": unique_email("probe"), "password": "wrong-password-123"}
        assert (await db_client.post(LOGIN, json=attempt, headers=headers)).status_code == 401
    attempt = {"email": unique_email("probe"), "password": "wrong-password-123"}
    blocked = await db_client.post(LOGIN, json=attempt, headers=headers)
    assert_problem(blocked, 429, "RATE_LIMITED")
    assert int(blocked.headers["retry-after"]) >= 1
    other_ip = await db_client.post(LOGIN, json=attempt, headers={"X-Real-IP": "203.0.113.51"})
    assert other_ip.status_code == 401


async def test_sec27_owner_registration_per_ip_ceiling(db_client: httpx.AsyncClient) -> None:
    headers = {"X-Real-IP": "203.0.113.60"}
    taken = registration()
    assert (await db_client.post(REGISTER, json=taken, headers=headers)).status_code == 201
    for _ in range(19):  # 20 per hour per IP; conflicts count as attempts too
        response = await db_client.post(REGISTER, json=taken, headers=headers)
        assert response.status_code == 409
    blocked = await db_client.post(REGISTER, json=registration(), headers=headers)
    assert_problem(blocked, 429, "RATE_LIMITED")
    assert "retry-after" in blocked.headers


# --- Inactive users and memberships (D9) ----------------------------------------------------------


async def test_idn04_inactive_memberships_still_log_in_inactive_users_do_not(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    member = await add_member(db, ctx, MembershipRole.TECHNICIAN)
    await set_member_active(db, ctx, member.membership_id, active=False)
    login = await db_client.post(
        LOGIN, json={"email": member.user.email, "password": TEST_PASSWORD}
    )
    assert login.status_code == 200  # they may be a customer
    assert (await db_client.get(ME)).json()["memberships"] == []

    inactive = await make_user(db, active=False)
    right = {"email": inactive.email, "password": TEST_PASSWORD}
    for _ in range(5):  # the right password of an inactive account counts as a failure
        assert_problem(await db_client.post(LOGIN, json=right), 401, "INVALID_CREDENTIALS")
    assert_problem(await db_client.post(LOGIN, json=right), 429, "RATE_LIMITED")


# --- Logout and cookies ---------------------------------------------------------------------------


async def test_idn06_logout_is_idempotent_and_the_bearer_token_stays_valid(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    for cookie in (None, "garbage-cookie"):
        db_client.cookies.clear()
        if cookie is not None:
            db_client.cookies.set(SESSION_COOKIE_NAME, cookie)
        response = await db_client.post(LOGOUT)
        assert response.status_code == 204
        assert response.content == b""
        assert response.headers["set-cookie"].startswith(f'{SESSION_COOKIE_NAME}=""')
        assert "Max-Age=0" in response.headers["set-cookie"]

    user = await make_user(db)
    login = await db_client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD})
    token = login.json()["access_token"]
    assert (await db_client.get(ME)).status_code == 200  # cookie session
    logout = await db_client.post(LOGOUT)
    assert logout.status_code == 204
    assert (await db_client.get(ME)).status_code == 401  # the cookie is gone
    still_valid = await db_client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert still_valid.status_code == 200  # stateless JWT caveat (spec 04)


async def test_logout_clears_the_cookie_even_when_its_audit_row_fails(
    db_app: FastAPI, db_client: httpx.AsyncClient, db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    """Spec 19 §3.3: recording `auth.logged_out` is best effort. A failing audit write is logged
    (never the token), rolled back, and the answer is still 204 with the cookie expired."""
    user = await make_user(db)

    async def broken_audit_store(event: LoggedOut, uow: UnitOfWork) -> None:
        raise RuntimeError("audit store unavailable")

    db_app.state.event_bus.subscribe(LoggedOut, broken_audit_store)  # runs after the audit row
    login = await db_client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD})
    token = login.json()["access_token"]
    with caplog.at_level(logging.WARNING):
        response = await db_client.post(LOGOUT)
    assert response.status_code == 204
    assert response.headers["set-cookie"].startswith(f'{SESSION_COOKIE_NAME}=""')
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert (await db_client.get(ME)).status_code == 401  # the cookie is gone
    assert await audit_rows(db, action="auth.logged_out") == []  # rolled back with the failure
    assert "auth.logout_not_recorded" in caplog.text
    assert token not in caplog.text


async def test_logout_clears_the_cookie_when_the_database_fails(
    db_client: httpx.AsyncClient, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_logout(uow: UnitOfWork, *, user_id: uuid.UUID | None) -> None:
        await uow.session.execute(text("SELECT 1 / 0"))  # a real error: the transaction aborts

    monkeypatch.setattr(identity_service, "logout", failing_logout)
    user = await make_user(db)
    response = await db_client.post(LOGOUT, headers=bearer(user.id))
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    db_client.cookies.set(SESSION_COOKIE_NAME, "a-cookie")
    again = await db_client.post(LOGOUT)
    assert again.status_code == 204
    assert "Max-Age=0" in again.headers["set-cookie"]


async def test_logout_per_ip_ceiling(db_client: httpx.AsyncClient) -> None:
    """Spec 04 "Rate limiting": 30 logouts per minute per IP, then 429 (the cookie stays)."""
    headers = {"X-Real-IP": "203.0.113.70"}
    for _ in range(30):
        assert (await db_client.post(LOGOUT, headers=headers)).status_code == 204
    blocked = await db_client.post(LOGOUT, headers=headers)
    assert_problem(blocked, 429, "RATE_LIMITED")
    assert int(blocked.headers["retry-after"]) >= 1
    other_ip = await db_client.post(LOGOUT, headers={"X-Real-IP": "203.0.113.71"})
    assert other_ip.status_code == 204


async def test_sec23_cookie_flags_when_cookie_secure(
    db_client: httpx.AsyncClient, db: Database, secure_cookies: None
) -> None:
    registered = await db_client.post(REGISTER, json=registration())
    user = await make_user(db)
    login = await db_client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD})
    for response in (registered, login):
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "Secure" in cookie
        assert "SameSite=lax" in cookie
        assert "Path=/" in cookie
        assert f"Max-Age={WEEK_SECONDS}" in cookie
        assert "Domain" not in cookie
    cleared = (await db_client.post(LOGOUT)).headers["set-cookie"]
    assert "Max-Age=0" in cleared
    assert "Secure" in cleared
    assert "HttpOnly" in cleared


async def test_sec30_logout_get_is_405_and_bodies_must_be_json(
    db_client: httpx.AsyncClient,
) -> None:
    response = await db_client.get(LOGOUT)
    assert_problem(response, 405, "METHOD_NOT_ALLOWED")
    assert response.headers["allow"] == "POST"
    body = json.dumps({"email": "a@bayflow.test", "password": TEST_PASSWORD})
    for content_type in ("text/plain", "application/x-www-form-urlencoded", None):
        headers = {"Content-Type": content_type} if content_type else {}
        sent = await db_client.post(LOGIN, content=body, headers=headers)
        assert_problem(sent, 422, "VALIDATION_ERROR")


async def test_auth_responses_are_never_cached(db_client: httpx.AsyncClient, db: Database) -> None:
    user = await make_user(db)
    responses = [
        await db_client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD}),
        await db_client.post(LOGIN, json={"email": user.email, "password": "wrong-password-1"}),
        await db_client.post(LOGOUT),
        await db_client.post(REGISTER, json={}),
    ]
    for response in responses:
        assert response.headers["cache-control"] == "no-store"  # D61
        assert "x-request-id" in response.headers


# --- Secrets: logs, storage, responses ------------------------------------------------------------


async def test_sec38_auth_logs_hold_no_password_or_token(
    db_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    body = registration(password="Very-Secret-Pass-42")
    with caplog.at_level(logging.DEBUG):
        registered = await db_client.post(REGISTER, json=body)
        await db_client.post(LOGIN, json={"email": body["email"], "password": "wrong-password!"})
        await db_client.post(LOGIN, json={"email": body["email"], "password": body["password"]})
        await db_client.post(REGISTER, json=registration(password="short"))
        await db_client.post(LOGOUT)
    token = registered.json()["access_token"]
    assert body["password"] not in caplog.text
    assert "wrong-password!" not in caplog.text
    assert token not in caplog.text
    assert "eyJ" not in caplog.text
    assert "auth.login_failed" in caplog.text
    assert "auth.login_succeeded" in caplog.text


def _collect_properties(
    node: object, components: dict[str, Any], seen: set[str], properties: set[str]
) -> None:
    if isinstance(node, list):
        for item in node:
            _collect_properties(item, components, seen, properties)
        return
    if not isinstance(node, dict):
        return
    reference = node.get("$ref")
    if isinstance(reference, str) and reference not in seen:
        seen.add(reference)
        _collect_properties(components[reference.rsplit("/", 1)[-1]], components, seen, properties)
    properties.update(node.get("properties", {}))
    for value in node.values():
        _collect_properties(value, components, seen, properties)


def _response_schema_properties(schema: dict[str, Any]) -> set[str]:
    """Every property name reachable from a 2xx response body of any operation."""
    properties: set[str] = set()
    seen: set[str] = set()
    for operations in schema["paths"].values():
        for operation in operations.values():
            for status, response in operation.get("responses", {}).items():
                if str(status).startswith("2"):
                    _collect_properties(
                        response.get("content", {}),
                        schema["components"]["schemas"],
                        seen,
                        properties,
                    )
    return properties


async def test_sec44_only_argon2id_hashes_are_stored_and_never_returned(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    body = registration()
    await db_client.post(REGISTER, json=body)
    stored = await stored_user(db, body["email"])
    assert stored.password_hash.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert body["password"] not in stored.password_hash
    schema = (await db_client.get("/openapi.json")).json()
    properties = _response_schema_properties(schema)
    assert "access_token" in properties  # the walk does reach the session schema
    assert not {name for name in properties if "password" in name}

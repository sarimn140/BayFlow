"""`identity.service` functions other modules and the seed call (`modules/identity.md` §5).

Covers IDN-05 (internal functions idempotent, `password_matches` outside the limiter), the
wizard's credential check (`authenticate`, D32: shared limiter, inactive = wrong password), the
look-ups and `set_phone_if_empty` (D33, the identity half of BK-05).
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select, update

from app.core.database import Database
from app.core.errors import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    NotFound,
    RateLimited,
    ValidationFailed,
)
from app.core.security import decode_token
from app.modules.identity import service as identity_service
from app.modules.identity.models import User
from app.modules.identity.schemas import UserRead, UserRecord, UserRef, to_user_read
from app.shared.clock import SimulatedClock, use_clock, utcnow
from tests.modules.identity.builders import TEST_PASSWORD, make_user, unique_email, unit_of_work

pytestmark = pytest.mark.db


async def load(db: Database, user_id: uuid.UUID) -> User:
    async with db.sessionmaker() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
        session.expunge(user)
        return user


# --- create_user ---------------------------------------------------------------------------------


async def test_create_user_normalises_and_hashes(db: Database, clock: SimulatedClock) -> None:
    async with unit_of_work(db) as uow:
        record = await identity_service.create_user(
            uow,
            email="  Ahmed@Mail.COM ",
            full_name="  Ahmed  ",
            password=SecretStr(TEST_PASSWORD),
            phone="+92 300 1234567",
        )
        await uow.commit()
    assert isinstance(record, UserRecord)
    assert (record.email, record.full_name, record.phone, record.is_active) == (
        "ahmed@mail.com",
        "Ahmed",
        "+923001234567",
        True,
    )
    stored = await load(db, record.id)
    assert stored.password_hash.startswith("$argon2id$")
    assert stored.created_at == stored.updated_at == clock.now()
    assert stored.last_login_at is None


async def test_create_user_takes_the_callers_clock_instant(db: Database) -> None:
    instant = datetime(2026, 10, 1, 8, 30, tzinfo=UTC)
    async with unit_of_work(db) as uow:
        record = await identity_service.create_user(
            uow,
            email=unique_email(),
            full_name="Kamran",
            password=SecretStr(TEST_PASSWORD),
            now=instant,
        )
        await uow.commit()
    stored = await load(db, record.id)
    assert stored.created_at == instant
    assert stored.last_login_at is None  # a created account is not logged in by default


async def test_create_user_starts_a_session_only_when_asked(
    db: Database, clock: SimulatedClock
) -> None:
    """`last_login_at` (identity open question 2): set when the action logs the new account in
    (register-owner, wizard case B), not when an Owner adds staff (`add_member`)."""
    instant = datetime(2026, 10, 2, 9, 15, tzinfo=UTC)
    async with unit_of_work(db) as uow:
        logged_in = await identity_service.create_user(
            uow,
            email=unique_email(),
            full_name="Ahmed",
            password=SecretStr(TEST_PASSWORD),
            now=instant,
            starts_session=True,
        )
        clock_default = await identity_service.create_user(
            uow,
            email=unique_email(),
            full_name="Zainab",
            password=SecretStr(TEST_PASSWORD),
            starts_session=True,
        )
        not_logged_in = await identity_service.create_user(
            uow,
            email=unique_email(),
            full_name="Usman",
            password=SecretStr(TEST_PASSWORD),
            starts_session=False,
        )
        await uow.commit()
    assert (await load(db, logged_in.id)).last_login_at == instant
    assert (await load(db, clock_default.id)).last_login_at == clock.now()
    assert (await load(db, not_logged_in.id)).last_login_at is None


async def test_create_user_refuses_an_existing_email(db: Database) -> None:
    existing = await make_user(db)
    async with unit_of_work(db) as uow:
        with pytest.raises(EmailAlreadyRegistered):
            await identity_service.create_user(
                uow,
                email=existing.email.upper(),
                full_name="Someone Else",
                password=SecretStr(TEST_PASSWORD),
            )


@pytest.mark.parametrize(
    ("overrides", "field", "code"),
    [
        ({"password": SecretStr("short-pass")}, "password", "string_too_short"),
        ({"password": SecretStr("x" * 129)}, "password", "string_too_long"),
        ({"full_name": "   "}, "full_name", "string_too_short"),
        ({"full_name": "x" * 121}, "full_name", "string_too_long"),
        ({"email": "x@localhost"}, "email", "value_error"),
        ({"phone": "+------"}, "phone", "phone_invalid"),
    ],
)
async def test_create_user_enforces_the_rules_for_direct_callers(
    db: Database, overrides: dict[str, object], field: str, code: str
) -> None:
    arguments: dict[str, object] = {
        "email": unique_email(),
        "full_name": "Direct Caller",
        "password": SecretStr(TEST_PASSWORD),
    }
    arguments.update(overrides)
    async with unit_of_work(db) as uow:
        with pytest.raises(ValidationFailed) as caught:
            await identity_service.create_user(uow, **arguments)  # type: ignore[arg-type]
    assert [(error["field"], error["code"]) for error in caught.value.errors or []] == [
        (field, code)
    ]


async def test_create_user_is_nested_and_rolls_back_with_its_caller(db: Database) -> None:
    email = unique_email()
    async with unit_of_work(db) as uow:
        created = await identity_service.create_user(
            uow, email=email, full_name="Rolled Back", password=SecretStr(TEST_PASSWORD)
        )
        found = await identity_service.find_user_by_email(uow.session, email)
        assert found is not None  # flushed: visible inside the caller's transaction …
        assert found.id == created.id
        await uow.rollback()  # … e.g. a booking whose slot was full (spec 04 SEC-18)
    async with db.sessionmaker() as session:
        assert await identity_service.find_user_by_email(session, email) is None  # … and gone


# --- authenticate (the wizard's credential check, D32) ------------------------------------------


async def test_authenticate_returns_the_account_and_stamps_last_login(
    db: Database, clock: SimulatedClock
) -> None:
    user = await make_user(db)
    clock.advance(timedelta(minutes=5))
    async with unit_of_work(db) as uow:
        record = await identity_service.authenticate(
            uow, email=user.email.upper(), password=SecretStr(TEST_PASSWORD)
        )
        await uow.commit()  # the caller commits (booking creation)
    assert record.id == user.id
    assert (await load(db, user.id)).last_login_at == clock.now()


async def test_authenticate_writes_nothing_without_the_callers_commit(db: Database) -> None:
    user = await make_user(db)
    async with unit_of_work(db) as uow:
        await identity_service.authenticate(
            uow, email=user.email, password=SecretStr(TEST_PASSWORD)
        )
        await uow.rollback()
    assert (await load(db, user.id)).last_login_at is None


@pytest.mark.parametrize("case", ["unknown", "wrong", "inactive"])
async def test_authenticate_treats_unknown_wrong_and_inactive_alike(
    db: Database, case: str
) -> None:
    user = await make_user(db, active=case != "inactive")
    email = unique_email("ghost") if case == "unknown" else user.email
    password = "wrong-password-42" if case == "wrong" else TEST_PASSWORD
    async with unit_of_work(db) as uow:
        with pytest.raises(InvalidCredentials):
            await identity_service.authenticate(uow, email=email, password=SecretStr(password))


async def test_sec27_wizard_and_login_share_the_per_account_limiter(
    db: Database, db_client: httpx.AsyncClient
) -> None:
    user = await make_user(db)
    for _ in range(3):  # three failed wizard checks (case D) …
        async with unit_of_work(db) as uow:
            with pytest.raises(InvalidCredentials):
                await identity_service.authenticate(
                    uow, email=user.email, password=SecretStr("wrong-password-42")
                )
    for _ in range(2):  # … and two failed logins
        response = await db_client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "wrong-password-42"}
        )
        assert response.status_code == 401
    async with unit_of_work(db) as uow:
        with pytest.raises(RateLimited) as caught:
            await identity_service.authenticate(
                uow, email=user.email, password=SecretStr(TEST_PASSWORD)
            )
    assert int(caught.value.headers["Retry-After"]) >= 1
    login = await db_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": TEST_PASSWORD}
    )
    assert login.status_code == 429


# --- Sessions -------------------------------------------------------------------------------------


async def test_issue_session_signs_a_session_token(clock: SimulatedClock) -> None:
    user_id = uuid.uuid4()
    token = identity_service.issue_session(user_id)
    assert token.token_type == "bearer"
    assert token.expires_in == 7 * 24 * 3600
    assert decode_token(token.access_token, utcnow(), "session") == user_id


# --- Look-ups -------------------------------------------------------------------------------------


async def test_look_ups(db: Database) -> None:
    active = await make_user(db, full_name="Ayesha Khan")
    inactive = await make_user(db, full_name="Kamran Shah", active=False)
    unknown = uuid.uuid4()
    async with db.sessionmaker() as session:
        assert (await identity_service.get_active_user(session, active.id)) == active
        assert await identity_service.get_active_user(session, inactive.id) is None
        assert await identity_service.get_active_user(session, unknown) is None
        found = await identity_service.get_user(session, inactive.id)
        assert found is not None
        assert found.is_active is False
        assert await identity_service.get_user(session, unknown) is None

        users = await identity_service.get_users_by_ids(session, [active.id, inactive.id, unknown])
        assert set(users) == {active.id, inactive.id}
        assert await identity_service.get_users_by_ids(session, []) == {}
        refs = await identity_service.get_user_refs(session, [active.id])
        assert refs == {active.id: UserRef(user_id=active.id, full_name="Ayesha Khan")}

        by_email = await identity_service.find_user_by_email(session, f" {active.email.upper()} ")
        assert by_email is not None
        assert by_email.id == active.id
        assert await identity_service.find_user_by_email(session, "nobody@bayflow.test") is None
        assert await identity_service.find_user_by_email(session, "not an e-mail") is None


async def test_find_user_ids_by_name_matches_literally(db: Database) -> None:
    ayesha = await make_user(db, full_name="Ayesha Khan")
    percent = await make_user(db, full_name="100% Motors_Owner")
    await make_user(db, full_name="Bilal")
    async with db.sessionmaker() as session:
        assert await identity_service.find_user_ids_by_name(session, q="khan") == [ayesha.id]
        assert await identity_service.find_user_ids_by_name(session, q="AYESHA K") == [ayesha.id]
        assert await identity_service.find_user_ids_by_name(session, q="%") == [percent.id]
        assert await identity_service.find_user_ids_by_name(session, q="s_o") == [percent.id]
        assert await identity_service.find_user_ids_by_name(session, q="   ") == []
        many = await identity_service.find_user_ids_by_name(session, q="a", limit=1)
        assert len(many) == 1


def test_to_user_read_drops_internal_fields() -> None:
    record = UserRecord(
        id=uuid.uuid4(), email="a@bayflow.test", full_name="A", phone=None, is_active=True
    )
    wire = to_user_read(record)
    assert type(wire) is UserRead
    assert wire.model_dump() == {
        "id": record.id,
        "email": "a@bayflow.test",
        "full_name": "A",
        "phone": None,
    }


# --- One instant per action (D63) -----------------------------------------------------------------

STEPPING_START = datetime(2026, 10, 14, 4, 0, tzinfo=UTC)


async def test_wizard_case_c_stamps_the_user_with_one_instant(db: Database) -> None:
    """Wizard case C writes the same user twice in one transaction: `authenticate` (last login,
    maybe a rehash), then `set_phone_if_empty`. With a clock that moves on every read, both writes
    must still carry the action's single instant."""
    user = await make_user(db)
    with use_clock(SimulatedClock(STEPPING_START, step=timedelta(seconds=1))):
        instant = utcnow()  # the action's instant; every later read returns a later one
        async with unit_of_work(db) as uow:
            await identity_service.authenticate(
                uow, email=user.email, password=SecretStr(TEST_PASSWORD), now=instant
            )
            assert await identity_service.set_phone_if_empty(
                uow, user_id=user.id, phone="0300-1234567", now=instant
            )
            await uow.commit()
    stored = await load(db, user.id)
    assert stored.updated_at == stored.last_login_at == instant
    assert stored.phone == "03001234567"


async def test_a_row_stamped_twice_at_one_instant_keeps_that_instant(db: Database) -> None:
    """`touch()` sends `updated_at` even when it already holds the action's instant, so the
    `onupdate` safety net never reads a stepping clock a second time (`app.shared.orm.touch`)."""
    with use_clock(SimulatedClock(STEPPING_START, step=timedelta(seconds=1))):
        instant = utcnow()
        async with unit_of_work(db) as uow:
            created = await identity_service.create_user(
                uow,
                email=unique_email(),
                full_name="Same Instant",
                password=SecretStr(TEST_PASSWORD),
                now=instant,
            )
            await identity_service.authenticate(  # the second write of the same row
                uow, email=created.email, password=SecretStr(TEST_PASSWORD), now=instant
            )
            await uow.commit()
    stored = await load(db, created.id)
    assert stored.created_at == stored.updated_at == stored.last_login_at == instant


# --- set_phone_if_empty (D33) ---------------------------------------------------------------------


async def test_set_phone_if_empty_never_overwrites(db: Database, clock: SimulatedClock) -> None:
    without = await make_user(db)
    with_phone = await make_user(db, phone="+923000000101")
    clock.advance(timedelta(minutes=1))
    async with unit_of_work(db) as uow:
        assert await identity_service.set_phone_if_empty(
            uow, user_id=without.id, phone="0300-1234567"
        )
        assert not await identity_service.set_phone_if_empty(
            uow, user_id=with_phone.id, phone="0300-7654321"
        )
        assert not await identity_service.set_phone_if_empty(
            uow, user_id=uuid.uuid4(), phone="0300-7654321"
        )
        await uow.commit()
    stored = await load(db, without.id)
    assert stored.phone == "03001234567"
    assert stored.updated_at == clock.now()
    assert (await load(db, with_phone.id)).phone == "+923000000101"


# --- Internal account maintenance (D60, IDN-05) ---------------------------------------------------


async def test_idn05_set_user_active_writes_only_real_changes(
    db: Database, clock: SimulatedClock
) -> None:
    user = await make_user(db)
    created = (await load(db, user.id)).updated_at
    clock.advance(timedelta(hours=1))
    async with unit_of_work(db) as uow:
        assert not await identity_service.set_user_active(uow, user_id=user.id, is_active=True)
    assert (await load(db, user.id)).updated_at == created  # nothing written
    async with unit_of_work(db) as uow:
        assert await identity_service.set_user_active(uow, user_id=user.id, is_active=False)
    stored = await load(db, user.id)
    assert (stored.is_active, stored.updated_at) == (False, clock.now())
    async with unit_of_work(db) as uow:
        with pytest.raises(NotFound):
            await identity_service.set_user_active(uow, user_id=uuid.uuid4(), is_active=True)


async def test_idn05_set_password_is_idempotent_and_replaces_a_changed_password(
    db: Database, clock: SimulatedClock, db_client: httpx.AsyncClient
) -> None:
    user = await make_user(db)
    before = await load(db, user.id)
    clock.advance(timedelta(hours=1))
    async with unit_of_work(db) as uow:
        await identity_service.set_password(
            uow, user_id=user.id, new_password=SecretStr(TEST_PASSWORD)
        )
    unchanged = await load(db, user.id)
    assert (unchanged.password_hash, unchanged.updated_at) == (
        before.password_hash,
        before.updated_at,
    )

    async with unit_of_work(db) as uow:
        await identity_service.set_password(
            uow, user_id=user.id, new_password=SecretStr("BayFlow@2026")
        )
    changed = await load(db, user.id)
    assert changed.password_hash != before.password_hash
    assert changed.updated_at == clock.now()
    old = await db_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": TEST_PASSWORD}
    )
    assert old.status_code == 401
    new = await db_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "BayFlow@2026"}
    )
    assert new.status_code == 200

    async with unit_of_work(db) as uow:
        with pytest.raises(ValidationFailed):
            await identity_service.set_password(
                uow, user_id=user.id, new_password=SecretStr("too-short")
            )
        with pytest.raises(NotFound):
            await identity_service.set_password(
                uow, user_id=uuid.uuid4(), new_password=SecretStr(TEST_PASSWORD)
            )


async def test_idn05_password_matches_bypasses_the_limiter(
    db: Database, db_client: httpx.AsyncClient
) -> None:
    user = await make_user(db)
    async with db.sessionmaker() as session:
        for _ in range(10):
            assert not await identity_service.password_matches(
                session, user_id=user.id, password=SecretStr("wrong-password-42")
            )
        assert await identity_service.password_matches(
            session, user_id=user.id, password=SecretStr(TEST_PASSWORD)
        )
        assert not await identity_service.password_matches(
            session, user_id=uuid.uuid4(), password=SecretStr(TEST_PASSWORD)
        )
    login = await db_client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": TEST_PASSWORD}
    )
    assert login.status_code == 200  # ten mismatches never counted as failed logins


async def test_password_matches_is_false_for_an_unusable_hash(db: Database) -> None:
    user = await make_user(db)
    async with db.sessionmaker() as session:
        await session.execute(update(User).where(User.id == user.id).values(password_hash="x"))
        await session.commit()
        assert not await identity_service.password_matches(
            session, user_id=user.id, password=SecretStr(TEST_PASSWORD)
        )

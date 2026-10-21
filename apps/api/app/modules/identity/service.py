"""Use cases and look-ups of the identity module (`modules/identity.md` §5; spec 04 "Authentication
flows").

- Top-level use cases (commit): `register_owner`, `login`, `logout`; internal, seed only (D60):
  `set_user_active`, `set_password`; the bootstrap script's `bootstrap_platform_admin` (D94).
- Nested (join the caller's transaction, never commit): `create_user`, `create_customer` (the
  wizard's new account, D32), `authenticate` (the one credential check behind login and the
  booking wizard, D32), `sign_in_for_booking` (the wizard's audited sign-in, D100),
  `set_phone_if_empty` (D33), and the platform admin's levers
  `change_user_active` / `change_platform_admin` with the spec 19 §1 safeguards;
  `lock_acting_platform_admin` re-checks the actor of another module's lever under a row lock.
- Pure: `issue_session` (reads the clock and the settings).
- Reads: `get_active_user` (used by `app.shared.auth`, D9), `get_user`, `get_users_by_ids`,
  `get_user_refs`, `find_user_by_email`, `find_user_ids_by_name`, `find_user_ids_by_email`,
  internal `password_matches`; the admin ports `list_users_for_admin`, `get_user_for_admin`,
  `count_users` (spec 19 §4 E-61, E-66, E-67).

Audit events (spec 19 §3.3, D95): `events.py` lists what this module publishes. The `audit`
module subscribes and writes each row in the same transaction; identity never imports it. A failed
or rate-limited login commits its (otherwise empty) transaction before raising, so the attempt is
recorded although the login fails; `authenticate` itself publishes nothing and never commits. The
booking wizard signs in through `sign_in_for_booking` (D100): a success is published in the
booking's transaction, a failed or blocked attempt is recorded in a short transaction of its own,
so it survives the booking's rollback while nothing of the booking commits.

Login is constant time: unknown e-mails are verified against a dummy hash, so every attempt runs
exactly one Argon2 verification, and unknown, wrong and inactive accounts get the same 401. The
per-account failure limiter (D69) is keyed by the normalised e-mail: each attempt is reserved with
one atomic `hit()` before the first `await`, so even a burst of parallel attempts reaches the
database and Argon2 at most 5 times per window; a success clears the counter. Identity is the
lowest module: it imports no other module and never imports `app.shared.auth` (spec 01 rule 8).
"""

import logging
import uuid
from collections.abc import Collection
from datetime import datetime
from typing import Protocol

from pwdlib.exceptions import UnknownHashError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    Conflict,
    EmailAlreadyRegistered,
    FieldError,
    Forbidden,
    InvalidCredentials,
    NotFound,
    RateLimited,
    ValidationFailed,
)
from app.core.security import (
    FAILED_PASSWORD_LIMIT,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    account_limiter,
    hash_password,
    issue_token,
    retry_after_seconds,
    verify_password,
)
from app.modules.identity.events import (
    CustomerAccountCreated,
    LoggedOut,
    LoginFailed,
    LoginRateLimited,
    LoginSucceeded,
    OwnerRegistered,
    PlatformAdminChanged,
    UserActiveChanged,
)
from app.modules.identity.models import User
from app.modules.identity.repository import UserRepository
from app.modules.identity.schemas import (
    FULL_NAME_MAX_LENGTH,
    SessionRead,
    SessionToken,
    UserAdminQuery,
    UserAdminRecord,
    UserRecord,
    UserRef,
    UserStats,
    to_user_read,
)
from app.shared.clock import utcnow
from app.shared.email import normalize_email
from app.shared.orm import touch
from app.shared.phone import normalize_phone
from app.shared.repository import constraint_name
from app.shared.uow import UnitOfWork

logger = logging.getLogger(__name__)

FAILED_PASSWORD_SCOPE = "failed-password"  # noqa: S105 - a limiter namespace, not a secret
"""Namespace of the per-account limiter key: `("failed-password", <normalised e-mail>)`."""

NAME_SEARCH_LIMIT = 1000
EMAIL_UNIQUE_CONSTRAINT = "uq_users_email"
EMAIL_ALREADY_REGISTERED_DETAIL = (
    "This e-mail already has a BayFlow account. Log in, then create your shop."
)

# Platform admin safeguards (spec 19 §1, D94).
REASON_MIN_LENGTH = 5
REASON_MAX_LENGTH = 500
LAST_ADMIN_DETAIL = "BayFlow needs at least one active platform admin."
SELF_DEACTIVATE_DETAIL = "You cannot deactivate your own account."
SELF_REVOKE_DETAIL = "You cannot revoke your own platform admin access."
ALREADY_INACTIVE_DETAIL = "This account is already deactivated."
ALREADY_ACTIVE_DETAIL = "This account is already active."
ALREADY_ADMIN_DETAIL = "This account is already a platform admin."
NOT_ADMIN_DETAIL = "This account is not a platform admin."
INACTIVE_GRANT_DETAIL = "Reactivate the account before granting platform admin access."
PLATFORM_ADMIN_ONLY_DETAIL = "Only an active BayFlow platform admin can do this."


class SecretValue(Protocol):
    """A masked secret (`pydantic.SecretStr` or the `Password` type's `Secret[str]`)."""

    def get_secret_value(self) -> str: ...


# --- Input guards for direct (non-HTTP) callers ------------------------------------------------
# HTTP inputs are already validated by the request schemas; the seed and other modules call these
# services directly, so the same rules are enforced here (defence in depth, spec 11 "no bypass").


def _field_error(field: str, code: str, message: str) -> ValidationFailed:
    return ValidationFailed(errors=[FieldError(field=field, code=code, message=message)])


def _normalised_email(value: str) -> str:
    try:
        return normalize_email(value.strip())
    except ValueError as exc:
        raise _field_error("email", "value_error", str(exc)) from None


def _lookup_key(email: str) -> str:
    """The normalised e-mail for look-ups and the limiter key (an invalid one never matches)."""
    try:
        return normalize_email(email.strip())
    except ValueError:
        return email.strip().lower()


def _required_full_name(value: str) -> str:
    name = value.strip()
    if not name:
        message = "String should have at least 1 character"
        raise _field_error("full_name", "string_too_short", message)
    if len(name) > FULL_NAME_MAX_LENGTH:
        message = f"String should have at most {FULL_NAME_MAX_LENGTH} characters"
        raise _field_error("full_name", "string_too_long", message)
    return name


def _new_password(password: SecretValue, *, field: str = "password") -> str:
    """The D10 policy for every new password: 12-128 characters, never trimmed."""
    value = password.get_secret_value()
    if len(value) < MIN_PASSWORD_LENGTH:
        message = f"String should have at least {MIN_PASSWORD_LENGTH} characters"
        raise _field_error(field, "string_too_short", message)
    if len(value) > MAX_PASSWORD_LENGTH:
        message = f"String should have at most {MAX_PASSWORD_LENGTH} characters"
        raise _field_error(field, "string_too_long", message)
    return value


def _optional_phone(value: str | None) -> str | None:
    """The shared `Phone` normalisation (spec 03 §1.5); idempotent for normalised values."""
    if value is None:
        return None
    try:
        return normalize_phone(value.strip())
    except ValueError as exc:
        raise _field_error("phone", "phone_invalid", str(exc)) from None


def _record(user: User) -> UserRecord:
    return UserRecord.model_validate(user)


def _admin_record(user: User) -> UserAdminRecord:
    return UserAdminRecord.model_validate(user)


async def _verify(password: str, user: User | None) -> tuple[bool, str | None]:
    """Exactly one Argon2 verification (a dummy one for an unknown user, spec 04).

    A stored hash pwdlib cannot parse (a corrupted row) is treated as a failed check and logged
    with the user id, never the hash (`modules/identity.md` §7.1).
    """
    try:
        return await verify_password(password, user.password_hash if user is not None else None)
    except UnknownHashError:
        user_id = str(user.id) if user is not None else None
        logger.warning("stored password hash is not recognised", extra={"user_id": user_id})
        return False, None


def _rate_limited(retry_after: int) -> RateLimited:
    return RateLimited(
        f"Too many attempts. Try again in {retry_after} seconds.",
        headers={"Retry-After": str(retry_after)},
    )


def _reserve_attempt(key: str) -> None:
    """D69: count this password check for `key` with one atomic `hit()` (`modules/identity.md`
    §7.4). Synchronous, and called before the first `await`, so parallel attempts can never all
    pass a check before any of them is counted: at most 5 per 15 minutes reach the database or
    Argon2. A blocked account gets 429 even with the right password; unknown e-mails are counted
    exactly like known ones, so the 429 reveals nothing."""
    if not account_limiter().hit(FAILED_PASSWORD_LIMIT, FAILED_PASSWORD_SCOPE, key):
        logger.warning("auth.account_rate_limited")
        raise _rate_limited(retry_after_seconds(FAILED_PASSWORD_LIMIT, FAILED_PASSWORD_SCOPE, key))


# --- Sessions -------------------------------------------------------------------------------------


def issue_session(user_id: uuid.UUID) -> SessionToken:
    """A `typ = session` token for `user_id` (D8), stamped with the app clock (D63)."""
    return SessionToken(
        access_token=issue_token(user_id, "session", utcnow()),
        token_type="bearer",  # noqa: S106 - the OAuth token type, not a secret
        expires_in=get_settings().jwt_lifetime_seconds,
    )


def _session_for(user: UserRecord) -> SessionRead:
    token = issue_session(user.id)
    return SessionRead(
        access_token=token.access_token,
        token_type=token.token_type,
        expires_in=token.expires_in,
        user=to_user_read(user),
    )


# --- Writes ---------------------------------------------------------------------------------------


async def _insert_user(  # noqa: PLR0913 - one keyword per users column the caller sets
    uow: UnitOfWork,
    *,
    email: str,
    full_name: str,
    password: SecretValue,
    phone: str | None,
    now: datetime,
    last_login_at: datetime | None = None,
) -> User:
    normalised_email = _normalised_email(email)
    name = _required_full_name(full_name)
    secret = _new_password(password)
    normalised_phone = _optional_phone(phone)
    repository = UserRepository(uow.session)
    if await repository.get_by_email(normalised_email) is not None:
        raise EmailAlreadyRegistered
    password_hash = await hash_password(secret)  # Argon2 off the event loop; no row lock held
    user = repository.add(
        User(
            email=normalised_email,
            password_hash=password_hash,
            full_name=name,
            phone=normalised_phone,
            is_active=True,
            last_login_at=last_login_at,
            created_at=now,
            updated_at=now,
        )
    )
    try:
        await repository.flush()
    except IntegrityError as exc:
        # A concurrent insert of the same e-mail won the race on `uq_users_email` (spec 02 §7.5):
        # the same 409 the pre-check gives, as a typed error every caller (and the seed) sees.
        if constraint_name(exc) != EMAIL_UNIQUE_CONSTRAINT:
            raise
        raise EmailAlreadyRegistered from exc
    return user


async def create_user(  # noqa: PLR0913 - spec signature plus the caller's instant and session flag
    uow: UnitOfWork,
    *,
    email: str,
    full_name: str,
    password: SecretValue,
    phone: str | None = None,
    now: datetime | None = None,
    starts_session: bool = False,
) -> UserRecord:
    """Create an account for an e-mail that has none (nested; the caller commits).

    Used by `register_owner`, `shops.add_member` (D18: the Owner set the password) and the booking
    wizard's case B (D32). Call it without holding row locks: it runs Argon2 (~55 ms). `now` lets
    the caller pass its action's clock instant (D63); it defaults to `utcnow()`.
    `starts_session=True` when the new account is logged in by this action (register-owner,
    wizard case B): `last_login_at` is set to `now` (`modules/identity.md` open question 2).
    A concurrent registration of the same e-mail → 409 `EMAIL_ALREADY_REGISTERED`.
    """
    instant = now or utcnow()
    user = await _insert_user(
        uow,
        email=email,
        full_name=full_name,
        password=password,
        phone=phone,
        now=instant,
        last_login_at=instant if starts_session else None,
    )
    return _record(user)


async def register_owner(
    uow: UnitOfWork,
    *,
    email: str,
    full_name: str,
    password: SecretValue,
    phone: str | None = None,
) -> SessionRead:
    """`POST /api/v1/auth/register-owner` (D17): a bare user, no membership; logged in (D81).

    An existing e-mail — found by the pre-check or by losing the `uq_users_email` race to a
    concurrent registration — is 409 with spec 03 §4.3's detail. The token is issued only after
    the commit, so it never names a rolled-back user.
    """
    now = utcnow()
    try:
        user = await create_user(
            uow,
            email=email,
            full_name=full_name,
            password=password,
            phone=phone,
            now=now,
            starts_session=True,
        )
    except EmailAlreadyRegistered:
        await uow.rollback()
        raise EmailAlreadyRegistered(EMAIL_ALREADY_REGISTERED_DETAIL) from None
    await uow.publish(OwnerRegistered(user_id=user.id, occurred_at=now))
    await uow.commit()
    logger.info("auth.owner_registered", extra={"user_id": str(user.id)})
    return _session_for(user)


async def create_customer(
    uow: UnitOfWork,
    *,
    email: str,
    full_name: str,
    password: SecretValue,
    phone: str | None = None,
    now: datetime | None = None,
) -> UserRecord:
    """The booking wizard's new account (D32 case B; nested, the booking commits): `create_user`
    logged in by the booking, plus `CustomerAccountCreated` for the audit log (spec 19 §3.3)."""
    instant = now or utcnow()
    user = await create_user(
        uow,
        email=email,
        full_name=full_name,
        password=password,
        phone=phone,
        now=instant,
        starts_session=True,
    )
    await uow.publish(CustomerAccountCreated(user_id=user.id, occurred_at=instant))
    return user


async def authenticate(
    uow: UnitOfWork,
    *,
    email: str,
    password: SecretValue,
    now: datetime | None = None,
) -> UserRecord:
    """The one credential check behind login and the wizard's cases C/D (nested, no commit).

    Order (`modules/identity.md` §7.4): reserve the attempt with the per-account limiter's atomic
    `hit` before any `await` (429 when the window is full) → user look-up (no row lock) → exactly
    one Argon2 verify → 401 `INVALID_CREDENTIALS` on failure (already counted; identical for
    unknown, wrong and inactive) → on success `clear`, `last_login_at`, transparent rehash. The
    bookings module maps `InvalidCredentials` to 409 `EMAIL_ALREADY_REGISTERED`; `RateLimited`
    passes through.
    """
    key = _lookup_key(email)
    _reserve_attempt(key)  # no `await` before this line: the check-and-count is atomic
    repository = UserRepository(uow.session)
    user = await repository.get_by_email(key)
    valid, new_hash = await _verify(password.get_secret_value(), user)
    if user is None or not valid or not user.is_active:
        logger.info("auth.login_failed")
        raise InvalidCredentials
    account_limiter().clear(FAILED_PASSWORD_LIMIT, FAILED_PASSWORD_SCOPE, key)
    instant = now or utcnow()
    user.last_login_at = instant
    touch(user, instant)  # always sent, even when the row was already stamped at `instant` (D63)
    if new_hash is not None:  # transparent Argon2 parameter upgrade (OWASP)
        user.password_hash = new_hash
    await repository.flush()
    return _record(user)


async def _record_failed_attempt(uow: UnitOfWork, event: LoginFailed | LoginRateLimited) -> None:
    """Spec 19 §3.2: publish the failed or blocked attempt and commit that transaction on its own
    before the caller re-raises the 401 / 429. It holds nothing else (a failed check writes no row),
    so only the audit row commits and the attempt is recorded although the login fails."""
    await uow.publish(event)
    await uow.commit()


async def _record_on_its_own(uow: UnitOfWork, event: LoginFailed | LoginRateLimited) -> None:
    """Publish a failed or blocked wizard sign-in in a separate session and transaction on the
    same engine and commit only that (D100). The caller's transaction (the booking) is neither
    committed nor touched; it still holds no row lock and wrote nothing at this point."""
    bind = uow.session.bind
    if not isinstance(bind, AsyncEngine):
        msg = "recording on its own needs a session bound to an engine"
        raise TypeError(msg)
    async with AsyncSession(bind, expire_on_commit=False) as session:
        own = UnitOfWork(session, uow.bus, app_state=uow.app_state)
        await own.publish(event)
        await own.commit()


async def sign_in_for_booking(
    uow: UnitOfWork, *, email: str, password: SecretValue, now: datetime
) -> UserRecord:
    """The booking wizard's cases C/D (nested; the booking commits): `authenticate`, audited like
    a login (spec 19 §3.3; D95, D100).

    - Success publishes `LoginSucceeded` in the booking's transaction: the row commits with the
      booking and is lost with it when the booking fails later (409 `SLOT_FULL` …).
    - A wrong password or an inactive account (`InvalidCredentials`, which the wizard turns into
      409 `EMAIL_ALREADY_REGISTERED`) records `LoginFailed`, and a blocked account (`RateLimited`,
      429) records `LoginRateLimited`, each in its own short transaction committed before the
      error is re-raised, so the attempt survives the booking's rollback.

    The per-account limiter behaves exactly as for login: `authenticate` reserves the attempt
    before its first `await` and clears the counter on success.
    """
    key = _lookup_key(email)
    try:
        user = await authenticate(uow, email=email, password=password, now=now)
    except InvalidCredentials:
        await _record_on_its_own(uow, LoginFailed(email=key, occurred_at=now))
        raise
    except RateLimited:
        await _record_on_its_own(uow, LoginRateLimited(email=key, occurred_at=now))
        raise
    await uow.publish(LoginSucceeded(user_id=user.id, occurred_at=now))
    return user


async def login(uow: UnitOfWork, *, email: str, password: SecretValue) -> SessionRead:
    """`POST /api/v1/auth/login`: the token fields and the `user`, no memberships (D81).

    Publishes `LoginSucceeded`, or `LoginFailed` / `LoginRateLimited` with the normalised e-mail
    (committed before the error is raised, spec 19 §3.2). The clock is read once (D63) and handed
    to `authenticate`, with no `await` before its atomic limiter `hit()`.
    """
    key = _lookup_key(email)
    now = utcnow()
    try:
        user = await authenticate(uow, email=email, password=password, now=now)
    except InvalidCredentials:
        await _record_failed_attempt(uow, LoginFailed(email=key, occurred_at=now))
        raise
    except RateLimited:
        await _record_failed_attempt(uow, LoginRateLimited(email=key, occurred_at=now))
        raise
    await uow.publish(LoginSucceeded(user_id=user.id, occurred_at=now))
    await uow.commit()
    logger.info("auth.login_succeeded", extra={"user_id": str(user.id)})
    return _session_for(user)


async def logout(uow: UnitOfWork, *, user_id: uuid.UUID | None) -> None:
    """`POST /api/v1/auth/logout` (top-level; never fails): publishes `LoggedOut` and commits when
    the request's cookie or Bearer token named an active user (spec 19 §3.3). The JWT is stateless,
    so nothing else changes: the router expires the cookie whatever happens here."""
    if user_id is None:
        return
    user = await UserRepository(uow.session).get(user_id)
    if user is None or not user.is_active:
        return
    await uow.publish(LoggedOut(user_id=user.id, occurred_at=utcnow()))
    await uow.commit()


async def set_phone_if_empty(
    uow: UnitOfWork, *, user_id: uuid.UUID, phone: str, now: datetime | None = None
) -> bool:
    """Fill `users.phone` only while it is NULL; never overwrite it (D33). True when written."""
    normalised = _optional_phone(phone)
    if normalised is None:
        return False
    return await UserRepository(uow.session).set_phone_if_empty(
        user_id=user_id, phone=normalised, now=now or utcnow()
    )


# --- Internal account maintenance for the seed's demo-cast reconciliation (D60) ------------------
# Never mounted on a route. Each function writes only when the value differs, so a run with nothing
# to repair changes no row (SEED-19).


async def set_user_active(uow: UnitOfWork, *, user_id: uuid.UUID, is_active: bool) -> bool:
    """Activate or deactivate an account (top-level). True when changed; 404 for an unknown id.

    A change publishes `UserActiveChanged` without an actor, so the audit log records it as a
    `SYSTEM` action (spec 19 §3.3)."""
    user = await UserRepository(uow.session).get(user_id)
    if user is None:
        raise NotFound
    now = utcnow()
    if user.is_active == is_active:
        return False
    user.is_active = is_active
    touch(user, now)
    await uow.publish(
        UserActiveChanged(user_id=user.id, is_active=is_active, actor_user_id=None, occurred_at=now)
    )
    await uow.commit()
    return True


async def password_matches(
    session: AsyncSession, *, user_id: uuid.UUID, password: SecretValue
) -> bool:
    """One Argon2 verification of the stored hash: no limiter, no rehash write (D60, D69).

    False for an unknown user and for a hash pwdlib cannot parse.
    """
    user = await UserRepository(session).get(user_id)
    if user is None:
        return False
    valid, _ = await _verify(password.get_secret_value(), user)
    return valid


async def set_password(uow: UnitOfWork, *, user_id: uuid.UUID, new_password: SecretValue) -> None:
    """Store an Argon2id hash of `new_password` (top-level; D10 policy). 404 for an unknown id.

    Writes nothing when the stored hash already verifies the password (idempotent, SEED-19).
    """
    secret = _new_password(new_password, field="new_password")
    repository = UserRepository(uow.session)
    user = await repository.get(user_id)
    if user is None:
        raise NotFound
    now = utcnow()
    already_set, _ = await _verify(secret, user)
    if already_set:
        return
    user.password_hash = await hash_password(secret)
    touch(user, now)
    await uow.commit()


# --- Look-ups for other modules -------------------------------------------------------------------


async def get_active_user(session: AsyncSession, user_id: uuid.UUID) -> UserRecord | None:
    """The user if it exists and is active, re-read on every request (D9); otherwise None."""
    user = await UserRepository(session).get(user_id)
    if user is None or not user.is_active:
        return None
    return _record(user)


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> UserRecord | None:
    """The user whatever its status, or None when the id is unknown."""
    user = await UserRepository(session).get(user_id)
    return _record(user) if user is not None else None


async def get_users_by_ids(
    session: AsyncSession, user_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, UserRecord]:
    """Users by id, any status, in one query; unknown ids are absent from the result."""
    users = await UserRepository(session).get_many(set(user_ids))
    return {user.id: _record(user) for user in users}


async def get_user_refs(
    session: AsyncSession, user_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, UserRef]:
    """`UserRef`s (spec 03 §3.1) for actor and author names, in one query."""
    users = await get_users_by_ids(session, user_ids)
    return {
        user_id: UserRef(user_id=user_id, full_name=user.full_name)
        for user_id, user in users.items()
    }


async def find_user_by_email(session: AsyncSession, email: str) -> UserRecord | None:
    """The account of an e-mail (normalised like the `Email` type, D62), any status."""
    user = await UserRepository(session).get_by_email(_lookup_key(email))
    return _record(user) if user is not None else None


async def find_user_ids_by_name(
    session: AsyncSession, *, q: str, limit: int = NAME_SEARCH_LIMIT
) -> list[uuid.UUID]:
    """Ids of users whose name contains `q` (case-insensitive, `%`/`_` literal), at most `limit`.

    Used by the staff booking search (`q` matches the customer name, spec 03 §4.8).
    """
    text = q.strip()
    if not text or limit < 1:
        return []
    return await UserRepository(session).find_ids_by_name(text, limit=limit)


async def find_user_ids_by_email(
    session: AsyncSession, *, q: str, limit: int = NAME_SEARCH_LIMIT
) -> list[uuid.UUID]:
    """Ids of users whose e-mail contains `q` (case-insensitive, `%`/`_` literal), at most `limit`.

    Used by the platform admin's searches (shops by owner e-mail, bookings by customer e-mail).
    """
    text = q.strip().lower()
    if not text or limit < 1:
        return []
    return await UserRepository(session).find_ids_by_email(text, limit=limit)


# --- Platform admin ports (spec 19 §1, §4; D94) ---------------------------------------------------


async def list_users_for_admin(
    session: AsyncSession, query: UserAdminQuery
) -> tuple[list[UserAdminRecord], int]:
    """E-66: one page of accounts and the total over every page (filters and sorts of the query)."""
    users, total = await UserRepository(session).admin_page(query)
    return [_admin_record(user) for user in users], total


async def get_user_for_admin(session: AsyncSession, user_id: uuid.UUID) -> UserAdminRecord | None:
    """E-67: one account, whatever its status; None for an unknown id."""
    user = await UserRepository(session).get(user_id)
    return _admin_record(user) if user is not None else None


async def count_users(session: AsyncSession, *, since: datetime) -> UserStats:
    """E-61: every account, the platform admins, the deactivated ones, those created since."""
    return await UserRepository(session).stats(since=since)


def _admin_reason(reason: str | None) -> str:
    """A restricting lever needs a reason of 5-500 characters (spec 19 §1)."""
    text = (reason or "").strip()
    if not REASON_MIN_LENGTH <= len(text) <= REASON_MAX_LENGTH:
        message = f"Give a reason of {REASON_MIN_LENGTH} to {REASON_MAX_LENGTH} characters."
        raise _field_error("reason", "value_error", message)
    return text


async def _lock_for_admin_change(
    uow: UnitOfWork, user_id: uuid.UUID
) -> tuple[User, frozenset[uuid.UUID]]:
    """The target row and the ids of the active platform admins, all locked `FOR UPDATE` before
    anything is counted (spec 19 §1). Unknown target → 404."""
    rows = await UserRepository(uow.session).lock_for_admin_change(user_id=user_id)
    target = next((row for row in rows if row.id == user_id), None)
    if target is None:
        raise NotFound
    admins = frozenset(row.id for row in rows if row.is_platform_admin and row.is_active)
    return target, admins


def _keep_an_active_admin(target: User, active_admins: frozenset[uuid.UUID]) -> None:
    """409 when `target` is the last active platform admin (spec 19 §1)."""
    if active_admins == {target.id}:
        raise Conflict(LAST_ADMIN_DETAIL)


def _require_acting_admin(actor_user_id: uuid.UUID, active_admins: frozenset[uuid.UUID]) -> None:
    """Defence in depth behind `require_platform_admin`: under the locks the actor must still be an
    active platform admin, so an admin revoked or deactivated by a concurrent request cannot act
    (403). It runs after the last-admin rule, so two admins demoting each other at once give the
    loser the spec's 409 (spec 19 §1)."""
    if actor_user_id not in active_admins:
        raise Forbidden(PLATFORM_ADMIN_ONLY_DETAIL)


async def lock_acting_platform_admin(session: AsyncSession, *, actor_user_id: uuid.UUID) -> None:
    """For another module's platform lever (shops' suspension, D96; nested, no commit): lock the
    actor's row `FOR SHARE` and require an active platform admin, else 403 `FORBIDDEN`.

    Like `_require_acting_admin`, this closes the race with a concurrent revoke or deactivation of
    the actor (spec 19 §1): that change locks the row `FOR UPDATE`, so it either waits until the
    lever commits or committed first, and then this fresh read refuses.
    """
    actor = await UserRepository(session).get_for_share(actor_user_id)
    if actor is None or not actor.is_active or not actor.is_platform_admin:
        raise Forbidden(PLATFORM_ADMIN_ONLY_DETAIL)


async def change_user_active(
    uow: UnitOfWork,
    *,
    actor_user_id: uuid.UUID,
    user_id: uuid.UUID,
    is_active: bool,
    reason: str | None = None,
) -> UserAdminRecord:
    """E-68 / E-69 (nested; the admin use case commits): deactivate or reactivate an account.

    Deactivate: yourself → 403 `FORBIDDEN`; a reason of 5-500 characters (422); unknown → 404;
    already inactive → 409; the last active platform admin → 409 `CONFLICT`. Reactivate: unknown
    → 404; already active → 409. Then the actor must still be an active admin (403). The account's
    tokens stop working at its next request (D9). Publishes `UserActiveChanged` with the reason
    (deactivation) for the audit log.
    """
    text = None
    if not is_active:
        if actor_user_id == user_id:
            raise Forbidden(SELF_DEACTIVATE_DETAIL)
        text = _admin_reason(reason)
    user, active_admins = await _lock_for_admin_change(uow, user_id)
    now = utcnow()
    if user.is_active == is_active:
        raise Conflict(ALREADY_ACTIVE_DETAIL if is_active else ALREADY_INACTIVE_DETAIL)
    if not is_active:
        _keep_an_active_admin(user, active_admins)
    _require_acting_admin(actor_user_id, active_admins)
    user.is_active = is_active
    touch(user, now)
    await uow.publish(
        UserActiveChanged(
            user_id=user.id,
            is_active=is_active,
            actor_user_id=actor_user_id,
            reason=text,
            occurred_at=now,
        )
    )
    return _admin_record(user)


async def change_platform_admin(
    uow: UnitOfWork, *, actor_user_id: uuid.UUID, user_id: uuid.UUID, is_platform_admin: bool
) -> UserAdminRecord:
    """E-70 / E-71 (nested; the admin use case commits): grant or revoke platform admin (D94).

    Grant: unknown → 404; already an admin → 409; an inactive account → 422 `VALIDATION_ERROR` on
    `path.user_id`. Revoke: yourself → 403 `FORBIDDEN`; unknown → 404; not an admin → 409; the last
    active platform admin → 409 `CONFLICT`. Then the actor must still be an active admin (403).
    Publishes `PlatformAdminChanged` for the audit log.
    """
    if not is_platform_admin and actor_user_id == user_id:
        raise Forbidden(SELF_REVOKE_DETAIL)
    user, active_admins = await _lock_for_admin_change(uow, user_id)
    now = utcnow()
    if user.is_platform_admin == is_platform_admin:
        raise Conflict(ALREADY_ADMIN_DETAIL if is_platform_admin else NOT_ADMIN_DETAIL)
    if is_platform_admin and not user.is_active:
        raise _field_error("path.user_id", "inactive_account", INACTIVE_GRANT_DETAIL)
    if not is_platform_admin:
        _keep_an_active_admin(user, active_admins)
    _require_acting_admin(actor_user_id, active_admins)
    user.is_platform_admin = is_platform_admin
    touch(user, now)
    await uow.publish(
        PlatformAdminChanged(
            user_id=user.id,
            is_platform_admin=is_platform_admin,
            actor_user_id=actor_user_id,
            occurred_at=now,
        )
    )
    return _admin_record(user)


async def bootstrap_platform_admin(
    uow: UnitOfWork, *, email: str, full_name: str, password: SecretValue | None
) -> tuple[UserRecord, bool, bool]:
    """`python -m app.scripts.create_platform_admin` (top-level, D94, spec 19 §1): idempotent.

    A missing account is created with `password` (the D10 policy; required then) and made a
    platform admin; an existing one is only promoted — its password, name and status never change.
    Returns `(user, created, promoted)`; an account that already is an admin writes nothing.
    The grant publishes `PlatformAdminChanged` without an actor (`SYSTEM` in the audit log).
    """
    existing = await UserRepository(uow.session).get_by_email(_normalised_email(email))
    created = existing is None
    now = utcnow()  # one instant for the whole use case (D63)
    if existing is None:
        if password is None:
            raise _field_error("password", "missing", "A new account needs a password.")
        record = await create_user(
            uow, email=email, full_name=full_name, password=password, now=now
        )
        user_id = record.id
    else:
        user_id = existing.id
    user, _ = await _lock_for_admin_change(uow, user_id)
    if user.is_platform_admin:
        unchanged = _record(user)  # read before the rollback expires the row
        await uow.rollback()
        return unchanged, False, False
    user.is_platform_admin = True
    touch(user, now)
    await uow.publish(
        PlatformAdminChanged(
            user_id=user.id, is_platform_admin=True, actor_user_id=None, occurred_at=now
        )
    )
    await uow.commit()
    return _record(user), created, True

"""Passwords, session tokens and rate limits (D8, D9, D10, D69; spec 04).

- **Passwords:** Argon2id via pwdlib (`PasswordHash.recommended()`), hashed off the event loop
  with a small concurrency cap; unknown users are verified against a dummy hash so timing does not
  reveal whether an account exists. Policy: 12-128 characters, no composition rules (D10).
- **Tokens:** stateless HS256 JWTs carrying exactly `sub`, `iat`, `exp`, `typ`. `typ` is `session`
  (cookie `bf_session` or `Authorization: Bearer`) or `ws` (60-second WebSocket ticket, D70).
  `iat`/`exp` follow the app clock (D63). `app.core` may not import `app.shared` (spec 01 rule 8),
  so `issue_token` / `decode_token` take `now` as an argument; callers pass
  `app.shared.clock.utcnow()`. PyJWT's own `exp`/`iat` checks (system time) are switched off and
  done here against `now`.
- **Rate limits:** the limit constants and limiter instances (spec 01, spec 04 "Rate limiting").
  Their windows run on system time: the one documented exception to D63.
"""

import asyncio
import functools
import math
import time
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import jwt
from limits import RateLimitItem, parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from pwdlib import PasswordHash
from pydantic import Field, Secret, StringConstraints
from slowapi import Limiter
from starlette.requests import Request

from app.core.config import get_settings, parse_duration
from app.core.errors import Unauthenticated

__all__ = [
    "ANONYMOUS_BOOKING_IP_LIMIT",
    "AUTHENTICATED_BOOKING_LIMIT",
    "FAILED_PASSWORD_LIMIT",
    "JWT_ALGORITHM",
    "LOGIN_IP_LIMIT",
    "LOGOUT_IP_LIMIT",
    "MAX_PASSWORD_LENGTH",
    "MEMBER_CREATION_LIMIT",
    "MIN_PASSWORD_LENGTH",
    "REGISTER_OWNER_IP_LIMIT",
    "SESSION_COOKIE_NAME",
    "SHOP_CREATION_LIMIT",
    "WS_TICKET_LIFETIME_SECONDS",
    "Password",
    "TokenType",
    "account_limiter",
    "client_ip",
    "decode_token",
    "hash_password",
    "ip_retry_after_seconds",
    "issue_token",
    "limiter",
    "parse_duration",
    "reset_rate_limits",
    "retry_after_seconds",
    "verify_password",
]

# --- Passwords (D10) ------------------------------------------------------------------------

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

Password = Annotated[
    Secret[
        Annotated[
            str, StringConstraints(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
        ]
    ],
    Field(json_schema_extra={"format": "password", "writeOnly": True}),
]
"""A request password: 12-128 characters, never trimmed; masked in reprs and tracebacks.

`Secret[str]` (not `SecretStr` + `Field(min_length=...)`) so a short password reports the string
error spec 03 §2.5 shows: `string_too_short`, "String should have at least 12 characters"."""

_password_hash = PasswordHash.recommended()
# At most 4 hashes in flight (each Argon2id call uses 64 MiB of memory).
_hash_slots = asyncio.Semaphore(4)


@functools.cache
def _dummy_hash() -> str:
    """A real Argon2id hash of a throwaway value: verifying against it costs as much as a real
    check. Computed lazily (first unknown-user login), so importing this module stays cheap."""
    return _password_hash.hash("timing-equaliser-not-a-real-password")


def _verify_dummy(password: str) -> None:
    _password_hash.verify(password, _dummy_hash())


async def hash_password(password: str) -> str:
    """Return the Argon2id PHC string for `password` (computed in a worker thread)."""
    async with _hash_slots:
        return await asyncio.to_thread(_password_hash.hash, password)


async def verify_password(password: str, stored_hash: str | None) -> tuple[bool, str | None]:
    """Check `password` against `stored_hash`.

    Returns `(valid, new_hash)`: `new_hash` is set when the stored hash uses outdated parameters
    and should be replaced (transparent upgrade on login). With `stored_hash=None` (unknown user)
    one dummy verification still runs, so the response time does not reveal the account exists.
    """
    async with _hash_slots:
        if stored_hash is None:
            await asyncio.to_thread(_verify_dummy, password)
            return False, None
        return await asyncio.to_thread(_password_hash.verify_and_update, password, stored_hash)


# --- Tokens (D8, D9, D70) ---------------------------------------------------------------------

TokenType = Literal["session", "ws"]

JWT_ALGORITHM = "HS256"
REQUIRED_CLAIMS = ["sub", "iat", "exp", "typ"]
SESSION_COOKIE_NAME = "bf_session"
WS_TICKET_LIFETIME_SECONDS = 60


def _epoch_seconds(moment: datetime) -> int:
    if moment.tzinfo is None:
        msg = "token times must be timezone-aware"
        raise ValueError(msg)
    return int(moment.timestamp())


def issue_token(
    user_id: UUID,
    typ: TokenType,
    now: datetime,
    lifetime_seconds: int | None = None,
) -> str:
    """Sign a JWT for `user_id` with exactly `sub`, `iat`, `exp`, `typ`.

    `now` comes from the app clock (`utcnow()`). The default lifetime is `JWT_EXPIRES_IN` for
    `session` tokens and 60 s for `ws` tickets.
    """
    settings = get_settings()
    if lifetime_seconds is None:
        lifetime_seconds = (
            settings.jwt_lifetime_seconds if typ == "session" else WS_TICKET_LIFETIME_SECONDS
        )
    issued_at = _epoch_seconds(now)
    claims = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + lifetime_seconds,
        "typ": typ,
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)


def _is_epoch_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def decode_token(token: str, now: datetime, expected_typ: TokenType) -> UUID:
    """Verify `token` against the clock instant `now` and return its user id.

    Checks: HS256 signature (algorithm pinned), every required claim present, integer `iat`/`exp`,
    `exp` after `now` and `iat` not after `now` (no leeway: the same server issues and checks),
    `typ` equal to `expected_typ`, `sub` a UUID. Any failure raises `Unauthenticated` (401).
    """
    secret = get_settings().jwt_secret.get_secret_value()
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            # PyJWT would compare exp/iat with the system time; D63 compares them with the clock.
            options={"require": REQUIRED_CLAIMS, "verify_exp": False, "verify_iat": False},
        )
        issued_at, expires_at = claims["iat"], claims["exp"]
        if not (_is_epoch_int(issued_at) and _is_epoch_int(expires_at)):
            msg = "iat and exp must be integers"
            raise jwt.InvalidTokenError(msg)
        current = _epoch_seconds(now)
        if expires_at <= current or issued_at > current:
            msg = "token expired or not yet valid"
            raise jwt.InvalidTokenError(msg)
        if claims["typ"] != expected_typ:
            msg = "unexpected token type"
            raise jwt.InvalidTokenError(msg)
        return UUID(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError) as exc:
        # Every PyJWT error subclasses InvalidTokenError; UUID() raises ValueError/TypeError/
        # AttributeError for a malformed `sub`.
        raise Unauthenticated from exc


# --- Rate limits (D69; spec 04 "Rate limiting") --------------------------------------------------

# Per-IP ceilings, applied with slowapi decorators on the routes (`@limiter.limit(LOGIN_IP_LIMIT)`).
LOGIN_IP_LIMIT = "30/minute"
LOGOUT_IP_LIMIT = "30/minute"
REGISTER_OWNER_IP_LIMIT = "20/hour"
ANONYMOUS_BOOKING_IP_LIMIT = "20/minute"

# Per-account / per-user / per-shop limits, applied in services with `account_limiter`.
FAILED_PASSWORD_LIMIT: RateLimitItem = parse("5/15 minutes")  # key: normalised e-mail (primary)
AUTHENTICATED_BOOKING_LIMIT: RateLimitItem = parse("30/hour")  # key: user id
SHOP_CREATION_LIMIT: RateLimitItem = parse("10/day")  # key: user id
MEMBER_CREATION_LIMIT: RateLimitItem = parse("30/hour")  # key: shop id


def client_ip(request: Request) -> str:
    """The caller's IP: `X-Real-IP` (set by Railway's edge), else the socket peer.

    Behind the Vercel rewrite this may be a shared Vercel egress address, which is why per-IP
    limits are only generous ceilings (spec 04).
    """
    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


# Module-level so route decorators can use it at import time. In-memory storage: correct with one
# API replica only (D14). `create_app()` exposes it as `app.state.limiter`.
limiter = Limiter(
    key_func=client_ip,
    storage_uri="memory://",
    strategy="moving-window",
    headers_enabled=False,
)


@functools.cache
def _account_storage() -> MemoryStorage:
    return MemoryStorage()


@functools.cache
def account_limiter() -> MovingWindowRateLimiter:
    """The moving-window limiter for per-account, per-user and per-shop limits (created lazily)."""
    return MovingWindowRateLimiter(_account_storage())


def retry_after_seconds(item: RateLimitItem, *identifiers: str) -> int:
    """Seconds until `item` frees a slot for `identifiers` (for the `Retry-After` header).

    The window's reset time is kept by `limits` on system time (D63's documented exception).
    """
    stats = account_limiter().get_window_stats(item, *identifiers)
    return max(1, math.ceil(stats.reset_time - time.time()))  # noqa: TID251 - D63 exception


def ip_retry_after_seconds(request: Request) -> int | None:
    """Seconds until the per-IP limit that blocked `request` frees a slot (None if unknown)."""
    current = getattr(request.state, "view_rate_limit", None)
    if current is None:
        return None
    item, identifiers = current
    stats = limiter.limiter.get_window_stats(item, *identifiers)
    return max(1, math.ceil(stats.reset_time - time.time()))  # noqa: TID251 - D63 exception


def reset_rate_limits() -> None:
    """Clear every in-memory counter (tests; counters also reset on every redeploy)."""
    limiter.reset()
    _account_storage().reset()

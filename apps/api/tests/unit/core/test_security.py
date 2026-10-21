"""Passwords, tokens and rate limits (D8-D10, D63, D69; spec 04 SEC-24, SEC-25)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.errors import Unauthenticated
from app.core.security import (
    FAILED_PASSWORD_LIMIT,
    JWT_ALGORITHM,
    WS_TICKET_LIFETIME_SECONDS,
    account_limiter,
    decode_token,
    hash_password,
    issue_token,
    reset_rate_limits,
    retry_after_seconds,
    verify_password,
)
from app.shared.clock import SystemClock

NOW = datetime(2026, 10, 14, 4, 0, tzinfo=UTC)
USER_ID = uuid.UUID("6f1c0d3e-4b2a-4c8d-9e7f-1a2b3c4d5e6f")


def secret() -> str:
    return get_settings().jwt_secret.get_secret_value()


def forge(claims: dict[str, object], *, key: str | None = None, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key if key is not None else secret(), algorithm=algorithm)


def valid_claims() -> dict[str, object]:
    issued = int(NOW.timestamp())
    return {"sub": str(USER_ID), "iat": issued, "exp": issued + 3600, "typ": "session"}


# --- Passwords ------------------------------------------------------------------------------------


async def test_hash_password_uses_argon2id_and_verifies() -> None:
    hashed = await hash_password("BayFlow@2026")
    assert hashed.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert await verify_password("BayFlow@2026", hashed) == (True, None)
    assert await verify_password("BayFlow@2027", hashed) == (False, None)


async def test_verify_password_for_unknown_user_still_fails_cleanly() -> None:
    assert await verify_password("BayFlow@2026", None) == (False, None)


async def test_verify_password_returns_an_upgraded_hash_for_old_parameters() -> None:
    from pwdlib import PasswordHash  # noqa: PLC0415 - only this test needs a second hasher
    from pwdlib.hashers.argon2 import Argon2Hasher  # noqa: PLC0415

    weak = PasswordHash((Argon2Hasher(time_cost=2, memory_cost=19456, parallelism=1),))
    old_hash = weak.hash("BayFlow@2026")
    valid, new_hash = await verify_password("BayFlow@2026", old_hash)
    assert valid
    assert new_hash is not None
    assert new_hash.startswith("$argon2id$v=19$m=65536,t=3,p=4$")


# --- Tokens ---------------------------------------------------------------------------------------


def test_session_token_carries_exactly_the_four_claims() -> None:
    token = issue_token(USER_ID, "session", NOW)
    claims = jwt.decode(
        token,
        secret(),
        algorithms=[JWT_ALGORITHM],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert set(claims) == {"sub", "iat", "exp", "typ"}
    assert claims["sub"] == str(USER_ID)
    assert claims["typ"] == "session"
    assert claims["iat"] == int(NOW.timestamp())
    assert claims["exp"] - claims["iat"] == get_settings().jwt_lifetime_seconds == 604_800
    assert jwt.get_unverified_header(token) == {"alg": "HS256", "typ": "JWT"}


def test_ws_ticket_lives_sixty_seconds() -> None:
    token = issue_token(USER_ID, "ws", NOW)
    claims = jwt.decode(
        token,
        secret(),
        algorithms=[JWT_ALGORITHM],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims["exp"] - claims["iat"] == WS_TICKET_LIFETIME_SECONDS == 60


def test_decode_round_trip_uses_the_given_clock_instant() -> None:
    token = issue_token(USER_ID, "session", NOW, lifetime_seconds=600)
    assert decode_token(token, NOW, "session") == USER_ID
    assert decode_token(token, NOW + timedelta(seconds=599), "session") == USER_ID


def test_validity_follows_the_app_clock_not_system_time() -> None:
    # Issued and checked under a simulated clock years in the past: PyJWT's own checks would call
    # it expired (system time); D63 judges it by the app clock, so it is still valid there.
    past = datetime(2020, 1, 1, tzinfo=UTC)
    assert past + timedelta(seconds=600) < SystemClock().now()
    token = issue_token(USER_ID, "session", past, lifetime_seconds=600)
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(token, secret(), algorithms=[JWT_ALGORITHM])
    assert decode_token(token, past + timedelta(seconds=1), "session") == USER_ID


def test_expired_token_is_rejected_at_exp() -> None:
    token = issue_token(USER_ID, "session", NOW, lifetime_seconds=600)
    with pytest.raises(Unauthenticated):
        decode_token(token, NOW + timedelta(seconds=600), "session")


def test_token_issued_in_the_future_is_rejected() -> None:
    token = issue_token(USER_ID, "session", NOW + timedelta(minutes=5))
    with pytest.raises(Unauthenticated):
        decode_token(token, NOW, "session")


def test_wrong_token_type_is_rejected_both_ways() -> None:
    ticket = issue_token(USER_ID, "ws", NOW)
    session = issue_token(USER_ID, "session", NOW)
    with pytest.raises(Unauthenticated):
        decode_token(ticket, NOW, "session")
    with pytest.raises(Unauthenticated):
        decode_token(session, NOW, "ws")


@pytest.mark.parametrize(
    "make_token",
    [
        pytest.param(
            lambda: forge(valid_claims(), key="another-secret-of-sufficient-length"),
            id="tampered-signature",
        ),
        pytest.param(
            lambda: forge(valid_claims(), key=secret() * 2, algorithm="HS512"), id="hs512"
        ),
        pytest.param(lambda: jwt.encode(valid_claims(), key=None, algorithm="none"), id="alg-none"),
        pytest.param(
            lambda: forge({k: v for k, v in valid_claims().items() if k != "typ"}), id="missing-typ"
        ),
        pytest.param(
            lambda: forge({k: v for k, v in valid_claims().items() if k != "exp"}), id="missing-exp"
        ),
        pytest.param(
            lambda: forge({k: v for k, v in valid_claims().items() if k != "iat"}), id="missing-iat"
        ),
        pytest.param(lambda: forge({**valid_claims(), "sub": "not-a-uuid"}), id="non-uuid-sub"),
        pytest.param(lambda: forge({**valid_claims(), "exp": "tomorrow"}), id="string-exp"),
        pytest.param(lambda: forge({**valid_claims(), "iat": 1.5}), id="float-iat"),
        pytest.param(lambda: "not.a.jwt", id="garbage"),
    ],
)
def test_malformed_or_forged_tokens_are_rejected(make_token: object) -> None:
    assert callable(make_token)
    with pytest.raises(Unauthenticated):
        decode_token(make_token(), NOW, "session")


def test_naive_clock_instants_are_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        issue_token(USER_ID, "session", NOW.replace(tzinfo=None))


# --- Rate limits (D69) ----------------------------------------------------------------------------


def test_failed_password_limit_blocks_the_sixth_attempt_and_reports_retry_after() -> None:
    limiter = account_limiter()
    key = "fatima.owner@bayflow.test"
    assert all(limiter.hit(FAILED_PASSWORD_LIMIT, key) for _ in range(5))
    assert not limiter.hit(FAILED_PASSWORD_LIMIT, key)
    assert limiter.hit(FAILED_PASSWORD_LIMIT, "someone.else@bayflow.test")
    assert 0 < retry_after_seconds(FAILED_PASSWORD_LIMIT, key) <= 15 * 60
    reset_rate_limits()
    assert limiter.hit(FAILED_PASSWORD_LIMIT, key)

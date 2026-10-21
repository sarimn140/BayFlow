"""Test builders and helpers for the identity module (spec 12 §4.3).

Builders go through the real service layer (never raw SQL), so test data is always reachable and
consistent. Shared by the identity, shops and scheduling test packages.
"""

import itertools
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest
from pydantic import SecretStr

from app.core.database import Database
from app.core.security import issue_token
from app.modules.identity import service as identity_service
from app.modules.identity.schemas import UserRecord
from app.shared.clock import utcnow
from app.shared.event_bus import EventBus
from app.shared.uow import UnitOfWork

TEST_PASSWORD = "test-password-1234"  # 12-128 characters (D10)

_sequence = itertools.count(1)
_hash_cache: dict[str, str] = {}


def unique_email(prefix: str = "user") -> str:
    """A fresh, valid `.test` address (D62), e.g. `user-7-1a2b3c4d@bayflow.test`."""
    return f"{prefix}-{next(_sequence)}-{uuid.uuid4().hex[:8]}@bayflow.test"


@asynccontextmanager
async def unit_of_work(database: Database) -> AsyncIterator[UnitOfWork]:
    """A unit of work on a fresh session (no event subscribers), closed afterwards."""
    async with database.sessionmaker() as session:
        yield UnitOfWork(session, EventBus())


async def make_user(
    database: Database,
    *,
    email: str | None = None,
    password: str = TEST_PASSWORD,
    full_name: str | None = None,
    phone: str | None = None,
    active: bool = True,
) -> UserRecord:
    """A user created through `identity.service.create_user` (spec 12 §4.3)."""
    number = next(_sequence)
    async with unit_of_work(database) as uow:
        user = await identity_service.create_user(
            uow,
            email=email or unique_email(),
            full_name=full_name or f"Test User {number}",
            password=SecretStr(password),
            phone=phone,
        )
        await uow.commit()
    if not active:
        async with unit_of_work(database) as uow:
            await identity_service.set_user_active(uow, user_id=user.id, is_active=False)
    return user


def bearer(user_id: uuid.UUID) -> dict[str, str]:
    """`Authorization: Bearer <session token>` stamped with the app clock (spec 12 §4.2)."""
    return {"Authorization": f"Bearer {issue_token(user_id, 'session', utcnow())}"}


def field_errors(body: dict[str, Any]) -> list[tuple[str, str]]:
    """`(field, code)` of every 422 field error."""
    return [(error["field"], error["code"]) for error in body["errors"]]


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hash each distinct password once per test session (real Argon2id, cached).

    Every stored hash is still a genuine `$argon2id$` hash of its password; only the ~55 ms cost
    of re-hashing the same test password for every new user is saved. Verification is untouched.
    """
    real_hash: Callable[[str], Awaitable[str]] = identity_service.hash_password

    async def cached_hash(password: str) -> str:
        if password not in _hash_cache:
            _hash_cache[password] = await real_hash(password)
        return _hash_cache[password]

    monkeypatch.setattr(identity_service, "hash_password", cached_hash)

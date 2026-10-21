"""Builders and helpers for the platform admin and audit tests (spec 19 §9; spec 12 §4.3).

Platform admins are made through the identity service (the bootstrap use case), tenants and
bookings through the bookings test world (`tests.modules.bookings.support`). Builders run on a unit
of work with an empty event bus, so the setup itself writes no audit row: only what a test does
through the API (the real, wired app) is audited.
"""

import uuid
from typing import Any

import httpx
from sqlalchemy import select

from app.core.database import Database
from app.modules.audit.models import AuditEvent
from app.modules.identity import service as identity_service
from app.modules.identity.schemas import UserRecord
from tests.modules.identity.builders import bearer, make_user, unit_of_work

ADMIN = "/api/v1/admin"
REASON = "Repeated customer complaints about billing"


async def make_admin(db: Database, *, full_name: str = "Areeba Hashmi") -> UserRecord:
    """An active platform admin (D94), promoted through `bootstrap_platform_admin`."""
    user = await make_user(db, full_name=full_name)
    async with unit_of_work(db) as uow:
        admin, created, promoted = await identity_service.bootstrap_platform_admin(
            uow, email=user.email, full_name=user.full_name, password=None
        )
    assert (created, promoted) == (False, True)
    return admin


async def audit_rows(db: Database, *, action: str | None = None) -> list[AuditEvent]:
    """Every audit row (or one action's), oldest first (read-only, for assertions)."""
    async with db.sessionmaker() as session:
        statement = select(AuditEvent).order_by(AuditEvent.occurred_at, AuditEvent.id)
        if action is not None:
            statement = statement.where(AuditEvent.action == action)
        return list((await session.execute(statement)).scalars())


async def admin_get(
    api: httpx.AsyncClient, admin: UserRecord, path: str, *, expect: int = 200, **params: Any
) -> Any:
    response = await api.get(f"{ADMIN}{path}", headers=bearer(admin.id), params=params)
    assert response.status_code == expect, (path, response.status_code, response.text)
    return response.json()


async def admin_post(
    api: httpx.AsyncClient,
    admin: UserRecord,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    expect: int = 200,
) -> Any:
    response = await api.post(f"{ADMIN}{path}", headers=bearer(admin.id), json=body)
    assert response.status_code == expect, (path, response.status_code, response.text)
    return response.json()


def ids(items: list[dict[str, Any]], key: str = "id") -> list[str]:
    return [str(item[key]) for item in items]


def uid(value: object) -> uuid.UUID:
    return uuid.UUID(str(value))

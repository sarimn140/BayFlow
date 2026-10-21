"""SQL for the identity module's table (`users`). Users are global, not shop-owned.

Every read is fresh (`populate_existing`), so a row changed by another transaction is never served
from an earlier identity-map copy (D9). A `uq_users_email` violation surfaces as 409
`EMAIL_ALREADY_REGISTERED` through the global constraint map (`app.core.db_errors`).

The platform admin's reads (spec 19 §4 E-61, E-66) and the lock behind the last-admin safeguard
(`lock_for_admin_change`, spec 19 §1) live here too.
"""

import re
import uuid
from collections.abc import Collection
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ColumnElement,
    CursorResult,
    UnaryExpression,
    all_,
    and_,
    any_,
    bindparam,
    false,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import Uuid

from app.modules.identity.models import User
from app.modules.identity.schemas import UserAdminQuery, UserStats
from app.shared.repository import Repository

_PHONE_SEPARATORS = re.compile(r"[\s-]+")


def _id_array(name: str, ids: Collection[uuid.UUID]) -> Any:
    """One `uuid[]` parameter (never one parameter per id, whatever the size of the set)."""
    return bindparam(name, value=sorted(ids), type_=ARRAY(Uuid()))


def _admin_conditions(query: UserAdminQuery) -> list[ColumnElement[bool]]:
    """E-66's filters. `q` is a case-insensitive substring of the name, the e-mail or the phone
    (also without spaces and hyphens, the stored form of `Phone`); `%`, `_` and the escape
    character are matched literally."""
    conditions: list[ColumnElement[bool]] = []
    text = (query.q or "").strip()
    if text:
        matches = [
            User.full_name.icontains(text, autoescape=True),
            User.email.icontains(text, autoescape=True),
            User.phone.icontains(text, autoescape=True),
        ]
        compact = _PHONE_SEPARATORS.sub("", text)
        if compact and compact != text:
            matches.append(User.phone.icontains(compact, autoescape=True))
        conditions.append(or_(*matches))
    if query.is_active is not None:
        conditions.append(User.is_active.is_(query.is_active))
    if query.is_platform_admin is not None:
        conditions.append(User.is_platform_admin.is_(query.is_platform_admin))
    if query.only_ids is not None:
        conditions.append(
            User.id == any_(_id_array("only_ids", query.only_ids)) if query.only_ids else false()
        )
    if query.excluded_ids:
        conditions.append(User.id != all_(_id_array("excluded_ids", query.excluded_ids)))
    return conditions


def _admin_order(sort: str) -> list[UnaryExpression[Any]]:
    """E-66's sorts, each ending in `id` so every page order is deterministic (spec 03 §1.6)."""
    if sort == "name":
        return [func.lower(User.full_name).asc(), User.id.asc()]
    if sort == "-last_login_at":
        return [User.last_login_at.desc().nulls_last(), User.id.asc()]
    return [User.created_at.desc(), User.id.asc()]


class UserRepository(Repository):
    async def get(self, user_id: uuid.UUID) -> User | None:
        """A fresh read of the row (D9: never served from an earlier identity-map copy)."""
        statement = select(User).where(User.id == user_id).execution_options(populate_existing=True)
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_for_share(self, user_id: uuid.UUID) -> User | None:
        """`SELECT … FOR SHARE`, fresh: the actor of another module's platform lever (a shop
        suspension, spec 19 §1). It conflicts with `lock_for_admin_change`'s `FOR UPDATE` and with
        a plain `UPDATE`, so a concurrent revoke or deactivation of the actor either waits for the
        lever's commit or has committed first and is seen by this read."""
        statement = (
            select(User)
            .where(User.id == user_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """The account of a normalised (lower-case) e-mail; `uq_users_email` serves it."""
        statement = (
            select(User).where(User.email == email).execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_many(self, user_ids: Collection[uuid.UUID]) -> list[User]:
        """The users with these ids, any status, in one query (unknown ids are skipped)."""
        if not user_ids:
            return []
        statement = (
            select(User)
            .where(User.id.in_(list(user_ids)))
            .execution_options(populate_existing=True)
        )
        return list((await self.session.execute(statement)).scalars())

    async def find_ids_by_name(self, q: str, *, limit: int) -> list[uuid.UUID]:
        """Ids of users whose `full_name` contains `q`, case-insensitively.

        `autoescape` escapes `%`, `_` and the escape character, so user input is matched literally.
        """
        statement = (
            select(User.id)
            .where(User.full_name.icontains(q, autoescape=True))
            .order_by(User.id)
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars())

    async def set_phone_if_empty(self, *, user_id: uuid.UUID, phone: str, now: datetime) -> bool:
        """`UPDATE … SET phone WHERE phone IS NULL` (D33): never overwrites; True when written."""
        statement = (
            update(User)
            .where(User.id == user_id, User.phone.is_(None))
            .values(phone=phone, updated_at=now)
        )
        result = await self.session.execute(statement)
        return isinstance(result, CursorResult) and result.rowcount == 1

    async def find_ids_by_email(self, q: str, *, limit: int) -> list[uuid.UUID]:
        """Ids of users whose e-mail contains `q`, case-insensitively (`%`, `_` literal)."""
        statement = (
            select(User.id)
            .where(User.email.icontains(q, autoescape=True))
            .order_by(User.id)
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars())

    # --- Platform admin (spec 19) -----------------------------------------------------------------

    async def lock_for_admin_change(self, *, user_id: uuid.UUID) -> list[User]:
        """`SELECT … FOR UPDATE` on the target **and** every active platform admin, in `id` order.

        The last-admin safeguard counts the active admins under these locks (spec 19 §1): two
        admins revoking or deactivating each other queue on the same rows, and the second one
        re-reads the first one's committed change (READ COMMITTED re-checks a locked row against
        the WHERE clause), so it sees one admin left and answers 409. One statement in `id` order
        means two such transactions always lock in the same order and cannot deadlock.
        """
        statement = (
            select(User)
            .where(
                or_(
                    User.id == user_id,
                    and_(User.is_platform_admin.is_(True), User.is_active.is_(True)),
                )
            )
            .order_by(User.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list((await self.session.execute(statement)).scalars())

    async def admin_page(self, query: UserAdminQuery) -> tuple[list[User], int]:
        """One page of E-66 and the total over every page (two statements)."""
        conditions = _admin_conditions(query)
        statement = (
            select(User)
            .where(*conditions)
            .order_by(*_admin_order(query.sort))
            .limit(query.limit)
            .offset(query.offset)
            .execution_options(populate_existing=True)
        )
        users = list((await self.session.execute(statement)).scalars())
        counted = select(func.count()).select_from(User).where(*conditions)
        total = (await self.session.execute(counted)).scalar_one()
        return users, int(total)

    async def stats(self, *, since: datetime) -> UserStats:
        """E-61's account counts in one statement."""
        statement = select(
            func.count(),
            func.count().filter(User.is_platform_admin.is_(True)),
            func.count().filter(User.is_active.is_(False)),
            func.count().filter(User.created_at >= since),
        ).select_from(User)
        row = (await self.session.execute(statement)).one()
        return UserStats(
            total=int(row[0]),
            platform_admins=int(row[1]),
            inactive=int(row[2]),
            created_since=int(row[3]),
        )

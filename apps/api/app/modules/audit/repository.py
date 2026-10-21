"""SQL for the audit module's table (`audit_events`, spec 19 §3.1).

Append-only (spec 02 §8, D95): this repository only adds and reads rows; the database trigger
`trg_audit_events_append_only` rejects any `UPDATE` or `DELETE`. Lists are ordered by
`(occurred_at, id)` (`ix_audit_events_occurred_at_id`); the export reads newest first in keyset
batches, so 10 000 rows never need an `OFFSET` scan.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, UnaryExpression, and_, func, or_, select, tuple_

from app.modules.audit.models import AuditEvent
from app.modules.audit.schemas import AuditFilters, AuditSort
from app.shared.enums import AuditTargetType
from app.shared.repository import Repository


def _equality_conditions(filters: AuditFilters) -> list[ColumnElement[bool]]:
    """The filters that compare one column with one value."""
    pairs: list[tuple[Any, object]] = [
        (AuditEvent.action, filters.action),
        (AuditEvent.actor_user_id, filters.actor_user_id),
        (AuditEvent.shop_id, filters.shop_id),
        (AuditEvent.target_type, filters.target_type),
        (AuditEvent.target_id, filters.target_id),
    ]
    return [column == value for column, value in pairs if value is not None]


def _conditions(filters: AuditFilters) -> list[ColumnElement[bool]]:
    """E-74's filters (spec 19 §4); `%`, `_` and the escape character in `q` match literally."""
    conditions = _equality_conditions(filters)
    if filters.categories:
        conditions.append(AuditEvent.category.in_(filters.categories))
    if filters.occurred_from is not None:
        conditions.append(AuditEvent.occurred_at >= filters.occurred_from)
    if filters.occurred_to is not None:
        conditions.append(AuditEvent.occurred_at < filters.occurred_to)
    text = (filters.q or "").strip()
    if text:
        conditions.append(
            or_(
                AuditEvent.summary.icontains(text, autoescape=True),
                AuditEvent.target_label.icontains(text, autoescape=True),
            )
        )
    if filters.involving_user_id is not None:
        conditions.append(
            or_(
                AuditEvent.actor_user_id == filters.involving_user_id,
                and_(
                    AuditEvent.target_type == AuditTargetType.USER,
                    AuditEvent.target_id == filters.involving_user_id,
                ),
            )
        )
    return conditions


def _order(sort: AuditSort) -> list[UnaryExpression[Any]]:
    if sort == "occurred_at":
        return [AuditEvent.occurred_at.asc(), AuditEvent.id.asc()]
    return [AuditEvent.occurred_at.desc(), AuditEvent.id.desc()]


class AuditEventRepository(Repository):
    """`audit_events` rows: add and read, never update or delete (spec 02 §8)."""

    async def page(
        self, filters: AuditFilters, *, sort: AuditSort, limit: int, offset: int
    ) -> tuple[list[AuditEvent], int]:
        """One page of E-74 and the total over every page (two statements)."""
        conditions = _conditions(filters)
        statement = (
            select(AuditEvent)
            .where(*conditions)
            .order_by(*_order(sort))
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self.session.execute(statement)).scalars())
        counted = select(func.count()).select_from(AuditEvent).where(*conditions)
        total = (await self.session.execute(counted)).scalar_one()
        return rows, int(total)

    async def newest(
        self,
        filters: AuditFilters,
        *,
        limit: int,
        before: tuple[datetime, uuid.UUID] | None = None,
    ) -> Sequence[AuditEvent]:
        """At most `limit` rows, newest first, strictly older than `before` (keyset paging)."""
        conditions = _conditions(filters)
        if before is not None:
            conditions.append(tuple_(AuditEvent.occurred_at, AuditEvent.id) < tuple_(*before))
        statement = (
            select(AuditEvent).where(*conditions).order_by(*_order("-occurred_at")).limit(limit)
        )
        return list((await self.session.execute(statement)).scalars())

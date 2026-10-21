"""SQL for the notifications module's table, `notifications` (spec 02 §3.20).

Rows are addressed to one user: every bell query filters by `recipient_user_id` (the caller), so
another user's rows simply match nothing. Rows are inserted in the publishing action's transaction
(one `INSERT … VALUES …` per action) and only `read_at` ever changes afterwards, by idempotent
`UPDATE … WHERE read_at IS NULL` statements. Indexes: the list (newest first) uses
`ix_notifications_recipient_user_id_created_at`, the count and "mark all" the partial
`ix_notifications_unread`.
"""

import uuid
from collections.abc import Collection, Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, CursorResult, exists, func, insert, select, update

from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NewNotification
from app.shared.repository import Repository


def _recipient_rows(*, user_id: uuid.UUID, unread_only: bool) -> list[ColumnElement[bool]]:
    """The caller's rows (all, or only the unread ones)."""
    conditions = [Notification.recipient_user_id == user_id]
    if unread_only:
        conditions.append(Notification.read_at.is_(None))
    return conditions


class NotificationRepository(Repository):
    async def insert_many(self, rows: Sequence[NewNotification]) -> None:
        """Insert every row of one action with a single `INSERT … VALUES …` statement.

        Pending ORM writes of the action (e.g. the new booking of `CREATE`) are flushed first, so
        the composite booking foreign key always finds its target.
        """
        if not rows:
            return
        await self.session.flush()
        values = [
            {
                "id": row.id,
                "recipient_user_id": row.recipient_user_id,
                "recipient_role": row.recipient_role,
                "shop_id": row.shop_id,
                "booking_id": row.booking_id,
                "type": row.type,
                "title": row.title,
                "body": row.body,
                "link": row.link,
                "read_at": None,
                "created_at": row.created_at,
            }
            for row in rows
        ]
        await self.session.execute(insert(Notification).values(values))

    async def page_for_recipient(
        self, *, user_id: uuid.UUID, unread_only: bool, limit: int, offset: int
    ) -> list[Notification]:
        """One page of the user's rows, newest first (`created_at DESC, id DESC`)."""
        statement = (
            select(Notification)
            .where(*_recipient_rows(user_id=user_id, unread_only=unread_only))
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
            .execution_options(populate_existing=True)
        )
        return list((await self.session.execute(statement)).scalars())

    async def count_for_recipient(self, *, user_id: uuid.UUID, unread_only: bool) -> int:
        statement = (
            select(func.count())
            .select_from(Notification)
            .where(*_recipient_rows(user_id=user_id, unread_only=unread_only))
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def exists_for_recipient(self, *, user_id: uuid.UUID, notification_id: uuid.UUID) -> bool:
        statement = select(
            exists().where(
                Notification.id == notification_id, Notification.recipient_user_id == user_id
            )
        )
        return bool((await self.session.execute(statement)).scalar_one())

    async def mark_read(
        self, *, user_id: uuid.UUID, notification_ids: Collection[uuid.UUID] | None, now: datetime
    ) -> int:
        """`UPDATE … SET read_at = now WHERE recipient = user AND read_at IS NULL [AND id IN …]`.

        `notification_ids=None` marks every unread row of the user. Rows already read keep their
        `read_at`; other users' ids match nothing. Returns the number of rows changed.
        """
        if notification_ids is not None and not notification_ids:
            return 0
        statement = update(Notification).where(
            Notification.recipient_user_id == user_id, Notification.read_at.is_(None)
        )
        if notification_ids is not None:
            statement = statement.where(Notification.id.in_(list(notification_ids)))
        statement = statement.values(read_at=now).execution_options(synchronize_session=False)
        result = await self.session.execute(statement)
        return result.rowcount if isinstance(result, CursorResult) else 0

    async def list_for_bookings(
        self, *, shop_id: uuid.UUID, booking_ids: Collection[uuid.UUID]
    ) -> list[Notification]:
        """Every row about these bookings of `shop_id`, oldest first (`created_at, id`)."""
        if not booking_ids:
            return []
        statement = (
            select(Notification)
            .where(
                Notification.shop_id == shop_id,
                Notification.booking_id.in_(list(booking_ids)),
            )
            .order_by(Notification.created_at, Notification.id)
            .execution_options(populate_existing=True)
        )
        return list((await self.session.execute(statement)).scalars())

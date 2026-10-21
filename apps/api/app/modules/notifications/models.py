"""ORM models of the notifications module: `notifications` (spec 02 §3.20, D26, D67)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.enums import ActorRole, NotificationType
from app.shared.orm import CreatedAtMixin, UUIDPrimaryKeyMixin, enum_type, not_blank


class Notification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An in-app message under the bell icon (brief §5.4). Only `read_at` ever changes."""

    __tablename__ = "notifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "booking_id"], ["bookings.shop_id", "bookings.id"], ondelete="RESTRICT"
        ),
        # MATCH SIMPLE would skip the composite FK when shop_id is NULL (spec 02 §4.3).
        CheckConstraint("booking_id IS NULL OR shop_id IS NOT NULL", name="booking_needs_shop"),
        # Server-computed relative deep link: no external, protocol-relative or backslash URLs.
        CheckConstraint(
            "link LIKE '/%' AND link NOT LIKE '//%' AND strpos(link, '\\') = 0",
            name="link_relative",
        ),
        not_blank("title"),
        not_blank("body"),
        # Bell dropdown, newest first.
        Index("ix_notifications_recipient_user_id_created_at", "recipient_user_id", "created_at"),
        # Unread badge count; "mark all read".
        Index(
            "ix_notifications_unread",
            "recipient_user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    recipient_role: Mapped[ActorRole] = mapped_column(enum_type(ActorRole, "recipient_role"))
    shop_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    booking_id: Mapped[uuid.UUID | None] = mapped_column()
    type: Mapped[NotificationType] = mapped_column(enum_type(NotificationType, "type"))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(1000))
    link: Mapped[str] = mapped_column(String(500))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

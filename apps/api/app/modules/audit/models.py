"""ORM model of the audit module: `audit_events` (spec 19 §3.1, spec 02 §3.22; D95).

The platform-wide, append-only audit log: one row per catalogue action (spec 19 §3.3), written by
this module's event handlers in the publisher's transaction. Rows are never updated or deleted:
the repository only adds and reads, and the trigger `trg_audit_events_append_only` rejects
`UPDATE` and `DELETE` for every client (spec 02 §8; `TRUNCATE` still works for test clean-up).

`occurred_at` is the action's clock instant (D63); there is no `created_at` (spec 19 §3.1).
`category`, `actor_role` and `target_type` are stored enums (D29: VARCHAR + CHECK). `target_id`
has no foreign key: a target may be a user, a shop, a membership or a booking.
"""

import uuid
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.enums import AuditActorRole, AuditCategory, AuditTargetType
from app.shared.orm import UUIDPrimaryKeyMixin, enum_type

ACTION_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
"""Dotted, lower snake case (`shop.suspended`, `booking.approve_estimate`)."""


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    """Who did what to which target in which shop, when and from where (glossary §1)."""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(f"action ~ '{ACTION_PATTERN}'", name="action_format"),
        CheckConstraint("jsonb_typeof(metadata) = 'object'", name="metadata_object"),
        # E-74 filters by target (the admin's user and booking trails).
        Index("ix_audit_events_target_type_target_id", "target_type", "target_id"),
    )

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    category: Mapped[AuditCategory] = mapped_column(enum_type(AuditCategory, "category"))
    action: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(300))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    actor_role: Mapped[AuditActorRole | None] = mapped_column(
        enum_type(AuditActorRole, "actor_role")
    )
    shop_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    target_type: Mapped[AuditTargetType | None] = mapped_column(
        enum_type(AuditTargetType, "target_type")
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column()
    target_label: Mapped[str | None] = mapped_column(String(200))
    # `metadata` is reserved by SQLAlchemy's declarative base, hence the attribute name.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    # Written as text; asyncpg reads `inet` back as an `ipaddress` object.
    ip: Mapped[IPv4Address | IPv6Address | str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    request_id: Mapped[str | None] = mapped_column(String(64))


# The admin's audit log, newest first (E-61, E-74, E-75).
Index("ix_audit_events_occurred_at_id", AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
# A shop's trail (E-63) and the shop filter.
Index("ix_audit_events_shop_id_occurred_at", AuditEvent.shop_id, AuditEvent.occurred_at.desc())
# What a person did (E-67) and the actor filter.
Index(
    "ix_audit_events_actor_user_id_occurred_at",
    AuditEvent.actor_user_id,
    AuditEvent.occurred_at.desc(),
)
# The category filter.
Index("ix_audit_events_category_occurred_at", AuditEvent.category, AuditEvent.occurred_at.desc())

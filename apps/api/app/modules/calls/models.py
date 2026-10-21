"""ORM models of the bonus calls module (spec 05 §7, mirrored in spec 02 §3.21).

Tables: `call_logs` (one in-app call attempt; an AI-answered call stays `MISSED`, its AI leg lives
in the `ai_*` columns), `ai_call_summaries`, `tasks`. Spec 05 §7 is authoritative for them.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.clock import utcnow
from app.shared.enums import (
    CallDirection,
    CallIntent,
    CallStatus,
    IdentityMethod,
    MissedReason,
    Sentiment,
    TaskKind,
    TaskStatus,
)
from app.shared.orm import (
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
    not_blank,
)

_RINGING = CallStatus.RINGING.value
_CONNECTED = CallStatus.CONNECTED.value
_ENDED = CallStatus.ENDED.value
_MISSED = CallStatus.MISSED.value


class CallLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One in-app call attempt, stored against a booking (brief §8.1)."""

    __tablename__ = "call_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "booking_id"], ["bookings.shop_id", "bookings.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("room_name"),
        UniqueConstraint("shop_id", "id"),  # composite-FK target for summaries and tasks (D20)
        CheckConstraint(
            f"(status = '{_MISSED}') = (missed_reason IS NOT NULL)", name="missed_fields"
        ),
        CheckConstraint(
            f"status <> '{_CONNECTED}' OR answered_at IS NOT NULL", name="connected_fields"
        ),
        CheckConstraint(
            f"status NOT IN ('{_ENDED}', '{_MISSED}') OR ended_at IS NOT NULL",
            name="ended_fields",
        ),
        CheckConstraint(
            "ai_dispatched_at IS NULL OR"
            f" (direction = '{CallDirection.CUSTOMER_TO_SHOP.value}' AND status = '{_MISSED}')",
            name="ai_dispatch",
        ),
        CheckConstraint(
            "(duration_seconds IS NULL OR duration_seconds >= 0)"
            " AND (ai_duration_seconds IS NULL OR ai_duration_seconds >= 0)",
            name="durations",
        ),
        # One active call (human or AI leg) per booking -> 409 CALL_BUSY (spec 05 §3.9).
        Index(
            "uq_call_logs_one_active_per_booking",
            "booking_id",
            unique=True,
            postgresql_where=text(
                f"status IN ('{_RINGING}', '{_CONNECTED}')"
                " OR (ai_dispatched_at IS NOT NULL AND ai_ended_at IS NULL)"
            ),
        ),
        # Sweepers (spec 05 §3.5, §3.7).
        Index(
            "ix_call_logs_ringing_deadline",
            "ring_deadline",
            postgresql_where=text(f"status = '{_RINGING}'"),
        ),
        Index(
            "ix_call_logs_ai_leg_open",
            "ai_dispatched_at",
            postgresql_where=text("ai_dispatched_at IS NOT NULL AND ai_ended_at IS NULL"),
        ),
        Index(
            "ix_call_logs_connected_answered_at",
            "answered_at",
            postgresql_where=text(f"status = '{_CONNECTED}'"),
        ),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column()
    booking_id: Mapped[uuid.UUID] = mapped_column()
    customer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    direction: Mapped[CallDirection] = mapped_column(enum_type(CallDirection, "direction"))
    status: Mapped[CallStatus] = mapped_column(
        enum_type(CallStatus, "status"),
        default=CallStatus.RINGING,
        server_default=text(f"'{_RINGING}'"),
    )
    missed_reason: Mapped[MissedReason | None] = mapped_column(
        enum_type(MissedReason, "missed_reason")
    )
    caller_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    answered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    ended_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    # Ids come from the server's ring list, never from input (no FKs on array elements).
    rung_user_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), default=list, server_default=text("'{}'::uuid[]")
    )
    declined_user_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), default=list, server_default=text("'{}'::uuid[]")
    )
    room_name: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    ring_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    ai_dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_dispatch_id: Mapped[str | None] = mapped_column(String(64))
    ai_call_token_hash: Mapped[str | None] = mapped_column(CHAR(64))
    ai_answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    ai_error: Mapped[str | None] = mapped_column(String(200))
    ai_identity_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_identity_method: Mapped[IdentityMethod | None] = mapped_column(
        enum_type(IdentityMethod, "ai_identity_method")
    )
    ai_identity_attempts: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default=text("0")
    )


# Call lists, the call-start rate limit and the monthly minutes cap (spec 05 §7.4, §11.3).
Index("ix_call_logs_shop_id_started_at", CallLog.shop_id, CallLog.started_at.desc())
Index("ix_call_logs_booking_id_started_at", CallLog.booking_id, CallLog.started_at.desc())
Index(
    "ix_call_logs_customer_user_id_started_at",
    CallLog.customer_user_id,
    CallLog.started_at.desc(),
)
Index("ix_call_logs_caller_user_id_started_at", CallLog.caller_user_id, CallLog.started_at.desc())


class AiCallSummary(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The structured summary of one AI leg (brief §8.2); written once by the API."""

    __tablename__ = "ai_call_summaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "call_log_id"], ["call_logs.shop_id", "call_logs.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["shop_id", "booking_id"], ["bookings.shop_id", "bookings.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("call_log_id"),  # one summary per call: the summary POST is idempotent
        CheckConstraint("jsonb_typeof(transcript) = 'array'", name="transcript_array"),
        not_blank("intent"),
        not_blank("details"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column()
    call_log_id: Mapped[uuid.UUID] = mapped_column()
    booking_id: Mapped[uuid.UUID] = mapped_column()
    customer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    intent: Mapped[str] = mapped_column(String(120))
    intent_category: Mapped[CallIntent] = mapped_column(enum_type(CallIntent, "intent_category"))
    details: Mapped[str] = mapped_column(String(4000))
    sentiment: Mapped[Sentiment] = mapped_column(enum_type(Sentiment, "sentiment"))
    is_urgent: Mapped[bool] = mapped_column(Boolean)
    language: Mapped[str] = mapped_column(String(8))
    transcript: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    is_fallback: Mapped[bool] = mapped_column(Boolean)
    model: Mapped[str | None] = mapped_column(String(64))


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A to-do for Service Advisors created from an AI call (brief §8.2)."""

    __tablename__ = "tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "booking_id"], ["bookings.shop_id", "bookings.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["shop_id", "call_log_id"], ["call_logs.shop_id", "call_logs.id"], ondelete="RESTRICT"
        ),
        CheckConstraint(
            f"((status = '{TaskStatus.DONE.value}') = (done_at IS NOT NULL))"
            " AND ((done_at IS NULL) = (done_by_user_id IS NULL))",
            name="done_fields",
        ),
        CheckConstraint("jsonb_typeof(metadata) = 'object'", name="metadata_object"),
        not_blank("title"),
        # No duplicate task per call and kind; a repeated kind updates the task (spec 05 §6.4).
        Index(
            "uq_tasks_one_per_call_and_kind",
            "call_log_id",
            "kind",
            unique=True,
            postgresql_where=text("call_log_id IS NOT NULL"),
        ),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    booking_id: Mapped[uuid.UUID | None] = mapped_column()
    call_log_id: Mapped[uuid.UUID | None] = mapped_column()
    customer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    kind: Mapped[TaskKind] = mapped_column(enum_type(TaskKind, "kind"))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(String(2000))
    is_urgent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    status: Mapped[TaskStatus] = mapped_column(
        enum_type(TaskStatus, "status"),
        default=TaskStatus.OPEN,
        server_default=text(f"'{TaskStatus.OPEN.value}'"),
    )
    # `metadata` is reserved by SQLAlchemy's declarative base, hence the attribute name.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    done_note: Mapped[str | None] = mapped_column(String(500))


# The SA / Owner tasks panel: open first, urgent first, newest first (spec 05 §6.5).
Index(
    "ix_tasks_shop_id_status_is_urgent_created_at",
    Task.shop_id,
    Task.status,
    Task.is_urgent.desc(),
    Task.created_at.desc(),
)

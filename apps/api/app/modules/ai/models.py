"""ORM models of the ai module (modules/ai.md "Tables", D103).

`ai_audit_events`: one append-only row per model call (AI-41; the `forbid_mutation` trigger).
`ai_drafts`: model output that waits for a person's decision (AI-42).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.enums import ActorRole, AiCallStatus, AiDraftStatus, AiFeature, AiSubjectType
from app.shared.orm import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin, enum_type

MAX_INPUT_CHARS = 32_000
MAX_ERROR_CHARS = 500
MAX_NOTE_CHARS = 500


class AiAuditEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One model call: what was asked (masked), what came back, and how it went."""

    __tablename__ = "ai_audit_events"
    __table_args__ = (
        UniqueConstraint("shop_id", "id"),  # composite-FK target for ai_drafts (D20)
        CheckConstraint(
            f"char_length(input_masked) <= {MAX_INPUT_CHARS}", name="input_masked_length"
        ),
        CheckConstraint(
            f"status <> '{AiCallStatus.SUCCEEDED.value}' OR output IS NOT NULL",
            name="succeeded_output",
        ),
        CheckConstraint(
            "latency_ms >= 0 AND (input_tokens IS NULL OR input_tokens >= 0)"
            " AND (output_tokens IS NULL OR output_tokens >= 0)",
            name="non_negative_counts",
        ),
        Index("ix_ai_audit_events_shop_id_created_at", "shop_id", "created_at"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    feature: Mapped[AiFeature] = mapped_column(enum_type(AiFeature, "feature"))
    prompt_version: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    actor_role: Mapped[ActorRole] = mapped_column(enum_type(ActorRole, "actor_role"))
    subject_type: Mapped[AiSubjectType] = mapped_column(enum_type(AiSubjectType, "subject_type"))
    subject_id: Mapped[uuid.UUID] = mapped_column()
    input_masked: Mapped[str] = mapped_column(Text)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[AiCallStatus] = mapped_column(enum_type(AiCallStatus, "status"))
    error: Mapped[str | None] = mapped_column(String(MAX_ERROR_CHARS))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)


class AiDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Model output that a person in an approver role accepts (as is or edited) or rejects."""

    __tablename__ = "ai_drafts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "audit_event_id"],
            ["ai_audit_events.shop_id", "ai_audit_events.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("audit_event_id"),
        CheckConstraint(
            f"(status = '{AiDraftStatus.PENDING.value}')"
            " = (decided_by_user_id IS NULL AND decided_at IS NULL)",
            name="decision",
        ),
        CheckConstraint(
            f"(status IN ('{AiDraftStatus.ACCEPTED.value}', '{AiDraftStatus.EDITED.value}'))"
            " = (final_payload IS NOT NULL)",
            name="final_payload",
        ),
        CheckConstraint(
            "decision_note IS NULL OR btrim(decision_note) <> ''", name="decision_note_not_blank"
        ),
        Index("ix_ai_drafts_shop_id_status_created_at", "shop_id", "status", "created_at"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    feature: Mapped[AiFeature] = mapped_column(enum_type(AiFeature, "feature"))
    audit_event_id: Mapped[uuid.UUID] = mapped_column()
    subject_type: Mapped[AiSubjectType] = mapped_column(enum_type(AiSubjectType, "subject_type"))
    subject_id: Mapped[uuid.UUID] = mapped_column()
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[AiDraftStatus] = mapped_column(enum_type(AiDraftStatus, "status"))
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decision_note: Mapped[str | None] = mapped_column(String(MAX_NOTE_CHARS))

"""ORM models of the qc module (spec 02 §3.18-§3.19, D46, D47).

Tables: `qc_inspections` (one row per QC round) and `qc_issues` (raised by a failed round).
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
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.enums import QcIssueStatus, QcResult
from app.shared.orm import TimestampMixin, UUIDPrimaryKeyMixin, enum_type, not_blank


class QcInspection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One QC attempt: who picked it, the checklist, notes and the result (NULL = in progress)."""

    __tablename__ = "qc_inspections"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "booking_id"], ["bookings.shop_id", "bookings.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["shop_id", "inspector_user_id"],
            ["shop_memberships.shop_id", "shop_memberships.user_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("shop_id", "id"),  # composite-FK target for qc_issues (D20)
        CheckConstraint("(result IS NULL) = (completed_at IS NULL)", name="completion"),
        CheckConstraint(
            f"result <> '{QcResult.PASS.value}' OR checklist IS NOT NULL", name="pass_checklist"
        ),
        CheckConstraint(
            "checklist IS NULL OR jsonb_typeof(checklist) = 'array'", name="checklist_array"
        ),
        # Database backstop for "first QC inspector to pick wins" (T18).
        Index(
            "uq_qc_inspections_one_open_per_booking",
            "booking_id",
            unique=True,
            postgresql_where=text("result IS NULL"),
        ),
        Index("ix_qc_inspections_booking_id_picked_at", "booking_id", "picked_at"),
        Index(
            "ix_qc_inspections_shop_id_inspector_user_id_picked_at",
            "shop_id",
            "inspector_user_id",
            "picked_at",
        ),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column()
    booking_id: Mapped[uuid.UUID] = mapped_column()
    inspector_user_id: Mapped[uuid.UUID] = mapped_column()
    picked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[QcResult | None] = mapped_column(enum_type(QcResult, "result"))
    checklist: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(String(2000))


class QcIssue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A problem recorded by a failed inspection; resolved when the job is sent to QC again."""

    __tablename__ = "qc_issues"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "booking_id"], ["bookings.shop_id", "bookings.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["shop_id", "qc_inspection_id"],
            ["qc_inspections.shop_id", "qc_inspections.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"((status = '{QcIssueStatus.RESOLVED.value}') = (resolved_at IS NOT NULL))"
            " AND ((resolved_at IS NULL) = (resolved_by_user_id IS NULL))",
            name="resolution_fields",
        ),
        not_blank("title"),
        not_blank("description"),
        Index("ix_qc_issues_booking_id_status", "booking_id", "status"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column()
    booking_id: Mapped[uuid.UUID] = mapped_column()
    qc_inspection_id: Mapped[uuid.UUID] = mapped_column()
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(2000))
    status: Mapped[QcIssueStatus] = mapped_column(
        enum_type(QcIssueStatus, "status"),
        default=QcIssueStatus.OPEN,
        server_default=text(f"'{QcIssueStatus.OPEN.value}'"),
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )

"""ORM models of the estimates module (spec 02 §3.11-§3.12, D39-D41).

Tables: `estimates` (one row per version) and `estimate_lines`. Money is PKR in whole rupees
stored as `numeric(12,2)`; totals are cached sums recomputed by the server on every change.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.enums import EstimateLineType, EstimateStatus
from app.shared.orm import (
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
    not_blank,
)


def _sql_list(*values: str) -> str:
    return ", ".join(f"'{value}'" for value in values)


_OPEN_STATUSES = _sql_list(EstimateStatus.DRAFT, EstimateStatus.SUBMITTED, EstimateStatus.SENT)
_SENT_OR_DECIDED = _sql_list(EstimateStatus.SENT, EstimateStatus.APPROVED, EstimateStatus.REJECTED)
_DECIDED = _sql_list(EstimateStatus.APPROVED, EstimateStatus.REJECTED)


class Estimate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One version of a booking's estimate (D39). `SENT`/decided/superseded versions are frozen."""

    __tablename__ = "estimates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "booking_id"], ["bookings.shop_id", "bookings.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("booking_id", "version"),
        UniqueConstraint("shop_id", "id"),  # composite-FK target (D20)
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "parts_total >= 0 AND labour_total >= 0 AND grand_total = parts_total + labour_total",
            name="totals",
        ),
        CheckConstraint(
            "parts_total = trunc(parts_total) AND labour_total = trunc(labour_total)"
            " AND grand_total = trunc(grand_total)",
            name="whole_rupees",
        ),
        CheckConstraint(
            f"status <> '{EstimateStatus.SUBMITTED.value}' OR submitted_at IS NOT NULL",
            name="submitted_fields",
        ),
        CheckConstraint(
            "((sent_at IS NULL) = (sent_by_user_id IS NULL))"
            f" AND (status NOT IN ({_SENT_OR_DECIDED}) OR sent_at IS NOT NULL)",
            name="sent_fields",
        ),
        CheckConstraint(
            f"((status IN ({_DECIDED})) = (decided_at IS NOT NULL))"
            " AND ((decided_at IS NULL) = (decided_by_user_id IS NULL))"
            " AND (customer_note IS NULL OR decided_at IS NOT NULL)",
            name="decision_fields",
        ),
        # Spec 08: at most one version per booking is DRAFT, SUBMITTED or SENT at a time.
        Index(
            "uq_estimates_one_open_version_per_booking",
            "booking_id",
            unique=True,
            postgresql_where=text(f"status IN ({_OPEN_STATUSES})"),
        ),
        # T12 reads "the approved version": never more than one.
        Index(
            "uq_estimates_one_approved_per_booking",
            "booking_id",
            unique=True,
            postgresql_where=text(f"status = '{EstimateStatus.APPROVED.value}'"),
        ),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column()
    booking_id: Mapped[uuid.UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[EstimateStatus] = mapped_column(
        enum_type(EstimateStatus, "status"),
        default=EstimateStatus.DRAFT,
        server_default=text(f"'{EstimateStatus.DRAFT.value}'"),
    )
    parts_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), server_default=text("0")
    )
    labour_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), server_default=text("0")
    )
    grand_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), server_default=text("0")
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    customer_note: Mapped[str | None] = mapped_column(String(500))


class EstimateLine(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A `PART` (from the shop's catalogue) or `LABOUR` line of one estimate version."""

    __tablename__ = "estimate_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "estimate_id"], ["estimates.shop_id", "estimates.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["shop_id", "part_id"], ["parts.shop_id", "parts.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("estimate_id", "position"),
        CheckConstraint("position BETWEEN 1 AND 50", name="position"),
        CheckConstraint(
            f"(line_type = '{EstimateLineType.PART.value}') = (part_id IS NOT NULL)",
            name="part_ref",
        ),
        CheckConstraint(
            f"line_type <> '{EstimateLineType.PART.value}'"
            " OR (quantity = trunc(quantity) AND quantity BETWEEN 1 AND 9999)",
            name="part_quantity",
        ),
        CheckConstraint(
            f"line_type <> '{EstimateLineType.LABOUR.value}' OR quantity BETWEEN 0.01 AND 999.99",
            name="labour_quantity",
        ),
        CheckConstraint("unit_price >= 0", name="unit_price"),
        # Whole rupees, rounded half-up (D41); PostgreSQL round() breaks ties away from zero.
        CheckConstraint("line_total = round(quantity * unit_price)", name="line_total"),
        CheckConstraint(
            "unit_price = trunc(unit_price) AND line_total = trunc(line_total)",
            name="whole_rupees",
        ),
        not_blank("description"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column()
    estimate_id: Mapped[uuid.UUID] = mapped_column()
    position: Mapped[int] = mapped_column(SmallInteger)
    line_type: Mapped[EstimateLineType] = mapped_column(enum_type(EstimateLineType, "line_type"))
    part_id: Mapped[uuid.UUID | None] = mapped_column()
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))

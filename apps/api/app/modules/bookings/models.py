"""ORM models of the bookings module (spec 02 §3.7-§3.10).

Tables: `vehicles`, `bookings`, `booking_services`, `booking_events`. Composite foreign keys
`(shop_id, x_id) -> parent (shop_id, id)` make cross-shop references impossible (D20, spec 02 §4).
`booking_events` is append-only (database trigger, spec 02 §8).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.enums import ActorRole, BookingAction, BookingStatus
from app.shared.orm import (
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
    not_blank,
)


def _sql_list(*values: str) -> str:
    return ", ".join(f"'{value}'" for value in values)


_CANCELLED = BookingStatus.CANCELLED.value
_BEFORE_TECHNICIAN = _sql_list(BookingStatus.PENDING, BookingStatus.CONFIRMED, _CANCELLED)
_BEFORE_PARTS_PERSON = _sql_list(
    BookingStatus.PENDING,
    BookingStatus.CONFIRMED,
    BookingStatus.ASSIGNED,
    BookingStatus.INSPECTING,
    BookingStatus.ESTIMATE_REVIEW,
    BookingStatus.AWAITING_CUSTOMER,
    BookingStatus.ESTIMATE_APPROVED,
    BookingStatus.ESTIMATE_REJECTED,
    _CANCELLED,
)
_WITH_QC_PICKER = _sql_list(
    BookingStatus.QC_IN_PROGRESS, BookingStatus.READY_FOR_PICKUP, BookingStatus.COMPLETED
)
_OPERATIONS = _sql_list(
    BookingAction.EDIT_ESTIMATE,
    BookingAction.START_REPAIR,
    BookingAction.NOTIFY_READY,
    BookingAction.REASSIGN_TECHNICIAN,
    BookingAction.REASSIGN_PARTS_PERSON,
)


class Vehicle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A customer's car (D35): global, not shop-scoped; unique per customer by normalised plate."""

    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "registration_key"),
        # Target of bookings (customer_user_id, vehicle_id): a booking uses its own customer's car.
        UniqueConstraint("owner_user_id", "id"),
        CheckConstraint(
            "registration_key = upper(regexp_replace(registration_number, '[[:space:]-]', '', 'g'))"
            " AND registration_key ~ '^[A-Z0-9]{2,20}$'",
            name="registration_key",
        ),
        CheckConstraint("year BETWEEN 1900 AND 2100", name="year"),
        CheckConstraint("mileage_km IS NULL OR mileage_km BETWEEN 0 AND 2000000", name="mileage"),
        not_blank("registration_number"),
        not_blank("make"),
        not_blank("model"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    registration_number: Mapped[str] = mapped_column(String(20))
    registration_key: Mapped[str] = mapped_column(String(20))
    make: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(60))
    year: Mapped[int] = mapped_column(SmallInteger)
    color: Mapped[str | None] = mapped_column(String(30))
    mileage_km: Mapped[int | None] = mapped_column(Integer)


class Booking(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One service visit moving through the booking state machine (spec 08)."""

    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("shop_id", "id"),  # composite-FK target (D20)
        ForeignKeyConstraint(
            ["customer_user_id", "vehicle_id"],
            ["vehicles.owner_user_id", "vehicles.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["shop_id", "technician_user_id"],
            ["shop_memberships.shop_id", "shop_memberships.user_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["shop_id", "parts_person_user_id"],
            ["shop_memberships.shop_id", "shop_memberships.user_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["shop_id", "qc_inspector_user_id"],
            ["shop_memberships.shop_id", "shop_memberships.user_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("reference ~ '^BF-[0-9A-HJKMNP-TV-Z]{6}$'", name="reference_format"),
        CheckConstraint("slot_end > slot_start", name="slot_order"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "mileage_km IS NULL OR mileage_km BETWEEN 0 AND 2000000", name="mileage_km"
        ),
        CheckConstraint(
            f"((status = '{_CANCELLED}') = (cancelled_at IS NOT NULL))"
            " AND ((cancelled_at IS NULL) = (cancelled_by_user_id IS NULL))"
            " AND (cancel_reason IS NULL OR cancelled_at IS NOT NULL)",
            name="cancellation_fields",
        ),
        CheckConstraint(
            f"(status = '{BookingStatus.COMPLETED.value}') = (completed_at IS NOT NULL)",
            name="completion_fields",
        ),
        CheckConstraint(
            f"technician_user_id IS NOT NULL OR status IN ({_BEFORE_TECHNICIAN})",
            name="technician_required",
        ),
        CheckConstraint(
            f"parts_person_user_id IS NOT NULL OR status IN ({_BEFORE_PARTS_PERSON})",
            name="parts_person_required",
        ),
        CheckConstraint(
            f"(qc_inspector_user_id IS NOT NULL) = (status IN ({_WITH_QC_PICKER}))",
            name="qc_picker",
        ),
        CheckConstraint(
            "qc_inspector_user_id IS NULL OR qc_inspector_user_id <> technician_user_id",
            name="qc_picker_not_technician",
        ),
        Index("ix_bookings_shop_id_status_slot_start", "shop_id", "status", "slot_start"),
        Index("ix_bookings_shop_id_slot_start", "shop_id", "slot_start"),
        Index("ix_bookings_customer_user_id_slot_start", "customer_user_id", "slot_start"),
        Index(
            "ix_bookings_technician_jobs",
            "shop_id",
            "technician_user_id",
            "status",
            postgresql_where=text("technician_user_id IS NOT NULL"),
        ),
        Index(
            "ix_bookings_parts_person_jobs",
            "shop_id",
            "parts_person_user_id",
            "status",
            postgresql_where=text("parts_person_user_id IS NOT NULL"),
        ),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    reference: Mapped[str] = mapped_column(String(9), unique=True)
    customer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column()
    mileage_km: Mapped[int | None] = mapped_column(Integer)
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[BookingStatus] = mapped_column(
        enum_type(BookingStatus, "status"),
        default=BookingStatus.PENDING,
        server_default=text(f"'{BookingStatus.PENDING.value}'"),
    )
    technician_user_id: Mapped[uuid.UUID | None] = mapped_column()
    parts_person_user_id: Mapped[uuid.UUID | None] = mapped_column()
    qc_inspector_user_id: Mapped[uuid.UUID | None] = mapped_column()
    customer_notes: Mapped[str | None] = mapped_column(String(2000))
    inspection_notes: Mapped[str | None] = mapped_column(String(4000))
    repair_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    cancel_reason: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))


class BookingService(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A service selected in the wizard, snapshotted at booking time (D34). Immutable."""

    __tablename__ = "booking_services"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "booking_id"], ["bookings.shop_id", "bookings.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["shop_id", "service_id"], ["services.shop_id", "services.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("booking_id", "service_id"),
        CheckConstraint("base_price_snapshot IS NULL OR base_price_snapshot >= 0", name="price"),
        CheckConstraint(
            "base_price_snapshot IS NULL OR base_price_snapshot = trunc(base_price_snapshot)",
            name="whole_rupees",
        ),
        not_blank("name_snapshot"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column()
    booking_id: Mapped[uuid.UUID] = mapped_column()
    service_id: Mapped[uuid.UUID] = mapped_column()
    name_snapshot: Mapped[str] = mapped_column(String(120))
    base_price_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))


class BookingEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Audit log row for every transition and operation (brief §7.5). Append-only (spec 02 §8)."""

    __tablename__ = "booking_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "booking_id"], ["bookings.shop_id", "bookings.id"], ondelete="RESTRICT"
        ),
        CheckConstraint(
            f"(action = '{BookingAction.CREATE.value}') = (from_status IS NULL)",
            name="create_from",
        ),
        CheckConstraint(
            f"action NOT IN ({_OPERATIONS}) OR from_status = to_status", name="operation_status"
        ),
        CheckConstraint(
            f"actor_user_id IS NOT NULL OR actor_role = '{ActorRole.SYSTEM.value}'", name="actor"
        ),
        CheckConstraint("jsonb_typeof(metadata) = 'object'", name="metadata_object"),
        # Timeline / audit history, read ORDER BY created_at, seq (D79).
        Index("ix_booking_events_booking_id_created_at_seq", "booking_id", "created_at", "seq"),
    )

    # Insert-order tie-breaker (D79): generated by the database, never set by the application.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True, sort_order=-99)
    shop_id: Mapped[uuid.UUID] = mapped_column()
    booking_id: Mapped[uuid.UUID] = mapped_column()
    action: Mapped[BookingAction] = mapped_column(enum_type(BookingAction, "action"))
    from_status: Mapped[BookingStatus | None] = mapped_column(
        enum_type(BookingStatus, "from_status")
    )
    to_status: Mapped[BookingStatus] = mapped_column(enum_type(BookingStatus, "to_status"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    actor_role: Mapped[ActorRole] = mapped_column(enum_type(ActorRole, "actor_role"))
    note: Mapped[str | None] = mapped_column(String(2000))
    # `metadata` is reserved by SQLAlchemy's declarative base, hence the attribute name.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=text("'{}'::jsonb")
    )

"""ORM models of the shops module (spec 02 §3.2-§3.5, §3.22).

Tables: `shops`, `shop_working_hours`, `shop_memberships`, `services`. Cross-module references
(`users`) are declared by table name only (spec 01 rule 2: no cross-module ORM relationships).
"""

import uuid
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    false,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.enums import MembershipRole
from app.shared.orm import TimestampMixin, UUIDPrimaryKeyMixin, enum_type, not_blank

DEFAULT_TIMEZONE = "Asia/Karachi"


class Shop(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant (glossary §1). Its owner is its single `OWNER` membership, not a column."""

    __tablename__ = "shops"
    __table_args__ = (
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
        CheckConstraint(
            "slot_duration_minutes BETWEEN 15 AND 240 AND slot_duration_minutes % 15 = 0",
            name="slot_duration",
        ),
        CheckConstraint("slot_capacity BETWEEN 1 AND 50", name="slot_capacity"),
        CheckConstraint("logo_url IS NULL OR logo_url LIKE 'https://%'", name="logo_url_https"),
        CheckConstraint("rating IS NULL OR rating BETWEEN 0 AND 5", name="rating_range"),
        # D96: a suspension is complete (when, why, by whom) or absent.
        CheckConstraint(
            "((suspended_at IS NULL) = (suspended_reason IS NULL))"
            " AND ((suspended_at IS NULL) = (suspended_by_user_id IS NULL))",
            name="suspension_complete",
        ),
        not_blank("name"),
        not_blank("address"),
        not_blank("city"),
        not_blank("phone"),
        # Public directory (D64): listed shops, optional city filter, ordered by name.
        Index("ix_shops_listed_city_name", "city", "name", postgresql_where=text("is_listed")),
    )

    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    address: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(
        String(64), default=DEFAULT_TIMEZONE, server_default=text(f"'{DEFAULT_TIMEZONE}'")
    )
    slot_duration_minutes: Mapped[int] = mapped_column(
        Integer, default=60, server_default=text("60")
    )
    slot_capacity: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    logo_url: Mapped[str | None] = mapped_column(String(2048))
    rating: Mapped[Decimal | None] = mapped_column(Numeric(2, 1))
    is_listed: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # D96, spec 19 §2: set by a platform admin, cleared on reactivation; nothing else changes.
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_reason: Mapped[str | None] = mapped_column(String(500))
    suspended_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )

    @property
    def is_suspended(self) -> bool:
        """A suspended shop is unlisted publicly and closed to its staff (D96)."""
        return self.suspended_at is not None


class ShopWorkingHours(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Opening hours of one weekday (0 = Monday ... 6 = Sunday), in shop-local time (D37, D38)."""

    __tablename__ = "shop_working_hours"
    __table_args__ = (
        UniqueConstraint("shop_id", "weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday"),
        CheckConstraint(
            "is_closed OR (opens_at IS NOT NULL AND closes_at IS NOT NULL"
            " AND closes_at > opens_at)",
            name="open_times",
        ),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    opens_at: Mapped[time | None] = mapped_column(Time(timezone=False))
    closes_at: Mapped[time | None] = mapped_column(Time(timezone=False))


class ShopMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's single role in one shop (D15). Never deleted: deactivated instead (D19)."""

    __tablename__ = "shop_memberships"
    __table_args__ = (
        # One role per user per shop; also the target of the staff-assignment FKs (spec 02 §4.4).
        UniqueConstraint("shop_id", "user_id"),
        CheckConstraint("role <> 'OWNER' OR is_active", name="owner_active"),
        # At most one OWNER per shop (D15).
        Index(
            "uq_shop_memberships_one_owner_per_shop",
            "shop_id",
            unique=True,
            postgresql_where=text("role = 'OWNER'"),
        ),
        # Shop switcher / "my shops".
        Index("ix_shop_memberships_user_active", "user_id", postgresql_where=text("is_active")),
        # "SAs of the shop" (D26), assignee pickers, QC_REQUESTED recipients.
        Index(
            "ix_shop_memberships_shop_role_active",
            "shop_id",
            "role",
            postgresql_where=text("is_active"),
        ),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    role: Mapped[MembershipRole] = mapped_column(enum_type(MembershipRole, "role"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )


class Service(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An entry of a shop's service catalogue (brief §7.2)."""

    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("shop_id", "id"),  # composite-FK target (D20)
        CheckConstraint("estimated_duration_minutes BETWEEN 5 AND 10080", name="duration"),
        CheckConstraint("base_price IS NULL OR base_price >= 0", name="base_price"),
        CheckConstraint(
            "base_price IS NULL OR base_price = trunc(base_price)", name="whole_rupees"
        ),
        not_blank("name"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(1000))
    estimated_duration_minutes: Mapped[int] = mapped_column(Integer)
    base_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


# Active service names are unique per shop, case-insensitively (-> 409 CONFLICT); the index also
# serves the directory's "has an active service" EXISTS (D64).
Index(
    "uq_services_active_name",
    Service.shop_id,
    func.lower(Service.name),
    unique=True,
    postgresql_where=text("is_active"),
)

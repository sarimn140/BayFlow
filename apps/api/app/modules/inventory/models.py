"""ORM models of the inventory module (spec 02 §3.13-§3.17, D42-D45).

Tables: `parts`, `booking_parts`, `stock_movements` (append-only ledger with signed deltas),
`purchase_orders`, `purchase_order_items`. `parts.on_hand` / `reserved` are the cached balances
of the ledger; available = on_hand - reserved is never stored.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.enums import PurchaseOrderStatus, StockMovementType
from app.shared.orm import (
    CreatedAtMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_type,
    not_blank,
)

_RECEIVE = StockMovementType.RECEIVE.value
_RESERVE = StockMovementType.RESERVE.value
_RELEASE = StockMovementType.RELEASE.value
_CONSUME = StockMovementType.CONSUME.value
_ADJUST = StockMovementType.ADJUST.value


class Part(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An item of one shop's parts catalogue. Inserted with on_hand = reserved = 0 (D44)."""

    __tablename__ = "parts"
    __table_args__ = (
        UniqueConstraint("shop_id", "sku"),
        UniqueConstraint("shop_id", "id"),  # composite-FK target (D20)
        CheckConstraint("on_hand >= 0", name="on_hand_non_negative"),
        CheckConstraint("reserved >= 0", name="reserved_non_negative"),
        CheckConstraint("reserved <= on_hand", name="reserved_lte_on_hand"),
        CheckConstraint("unit_cost >= 0", name="unit_cost"),
        CheckConstraint("unit_cost = trunc(unit_cost)", name="whole_rupees"),
        CheckConstraint("reorder_level >= 0", name="reorder_level"),
        CheckConstraint("sku ~ '^[A-Z0-9][A-Z0-9._/-]{0,39}$'", name="sku_format"),
        not_blank("name"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    sku: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    on_hand: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    reserved: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    reorder_level: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class BookingPart(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Parts a booking needs (from the approved estimate) and how many are reserved / consumed."""

    __tablename__ = "booking_parts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "booking_id"], ["bookings.shop_id", "bookings.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["shop_id", "part_id"], ["parts.shop_id", "parts.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("booking_id", "part_id"),
        CheckConstraint(
            "required_qty > 0 AND reserved_qty >= 0 AND consumed_qty >= 0"
            " AND reserved_qty + consumed_qty <= required_qty",
            name="quantities",
        ),
        CheckConstraint(
            "consumed_qty = 0 OR (consumed_qty = required_qty AND reserved_qty = 0)",
            name="consume_all",
        ),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column()
    booking_id: Mapped[uuid.UUID] = mapped_column()
    part_id: Mapped[uuid.UUID] = mapped_column()
    required_qty: Mapped[int] = mapped_column(Integer)
    reserved_qty: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    consumed_qty: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))


class PurchaseOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An order to a supplier, linked to one booking or none (general restock, D43)."""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "booking_id"], ["bookings.shop_id", "bookings.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("shop_id", "po_number"),
        UniqueConstraint("shop_id", "id"),  # composite-FK target (D20)
        CheckConstraint("po_number ~ '^PO-[0-9A-HJKMNP-TV-Z]{6}$'", name="po_number_format"),
        CheckConstraint(
            f"(status = '{PurchaseOrderStatus.RECEIVED.value}') = (received_at IS NOT NULL)",
            name="received_fields",
        ),
        Index("ix_purchase_orders_shop_id_status_created_at", "shop_id", "status", "created_at"),
        Index(
            "ix_purchase_orders_booking",
            "shop_id",
            "booking_id",
            postgresql_where=text("booking_id IS NOT NULL"),
        ),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="RESTRICT"))
    po_number: Mapped[str] = mapped_column(String(9))
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        enum_type(PurchaseOrderStatus, "status"),
        default=PurchaseOrderStatus.ORDERED,
        server_default=text(f"'{PurchaseOrderStatus.ORDERED.value}'"),
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column()
    supplier_name: Mapped[str | None] = mapped_column(String(120))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PurchaseOrderItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One part line of a purchase order; `received_qty` grows with each receipt (T15)."""

    __tablename__ = "purchase_order_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "purchase_order_id"],
            ["purchase_orders.shop_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["shop_id", "part_id"], ["parts.shop_id", "parts.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("purchase_order_id", "part_id"),
        CheckConstraint(
            "ordered_qty > 0 AND received_qty >= 0 AND received_qty <= ordered_qty",
            name="quantities",
        ),
        CheckConstraint("unit_cost >= 0", name="unit_cost"),
        CheckConstraint("unit_cost = trunc(unit_cost)", name="whole_rupees"),
    )

    shop_id: Mapped[uuid.UUID] = mapped_column()
    purchase_order_id: Mapped[uuid.UUID] = mapped_column()
    part_id: Mapped[uuid.UUID] = mapped_column()
    ordered_qty: Mapped[int] = mapped_column(Integer)
    received_qty: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class StockMovement(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One stock change with signed deltas (D42). Append-only ledger (spec 02 §8)."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["shop_id", "part_id"], ["parts.shop_id", "parts.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["shop_id", "booking_id"], ["bookings.shop_id", "bookings.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["shop_id", "purchase_order_id"],
            ["purchase_orders.shop_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            f"(movement_type = '{_RECEIVE}' AND on_hand_delta = quantity AND reserved_delta = 0)"
            f" OR (movement_type = '{_RESERVE}' AND on_hand_delta = 0"
            " AND reserved_delta = quantity)"
            f" OR (movement_type = '{_RELEASE}' AND on_hand_delta = 0"
            " AND reserved_delta = -quantity)"
            f" OR (movement_type = '{_CONSUME}' AND on_hand_delta = -quantity"
            " AND reserved_delta = -quantity)"
            f" OR (movement_type = '{_ADJUST}' AND abs(on_hand_delta) = quantity"
            " AND reserved_delta = 0)",
            name="deltas",
        ),
        CheckConstraint(
            f"(movement_type IN ('{_RESERVE}', '{_RELEASE}', '{_CONSUME}')"
            " AND booking_id IS NOT NULL)"
            f" OR (movement_type = '{_RECEIVE}' AND booking_id IS NULL"
            " AND purchase_order_id IS NOT NULL)"
            f" OR (movement_type = '{_ADJUST}' AND booking_id IS NULL"
            " AND purchase_order_id IS NULL AND note IS NOT NULL)",
            name="links",
        ),
        # A part's history and running balance, read ORDER BY created_at, seq (D79).
        Index("ix_stock_movements_part_id_created_at_seq", "part_id", "created_at", "seq"),
    )

    # Insert-order tie-breaker (D79): generated by the database, never set by the application.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True, sort_order=-99)
    shop_id: Mapped[uuid.UUID] = mapped_column()
    part_id: Mapped[uuid.UUID] = mapped_column()
    movement_type: Mapped[StockMovementType] = mapped_column(
        enum_type(StockMovementType, "movement_type")
    )
    quantity: Mapped[int] = mapped_column(Integer)
    on_hand_delta: Mapped[int] = mapped_column(Integer)
    reserved_delta: Mapped[int] = mapped_column(Integer)
    booking_id: Mapped[uuid.UUID | None] = mapped_column()
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column()
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    note: Mapped[str | None] = mapped_column(String(500))

"""SQL for the inventory module's tables (spec 02 §3.13-§3.17, §7; D20, D30, D42, D79).

Every method on shop-owned data takes a keyword-only `shop_id` (D20). Locking reads follow D30:
a purchase order by key, then parts by ascending id in **one** statement
(`… WHERE shop_id = :shop_id AND id IN (:ids) ORDER BY id FOR UPDATE`; PostgreSQL sorts before it
locks, spec 02 §7.1), always with `populate_existing` so a row that waited for its lock is re-read.
`StockMovementRepository` has no update or delete: the ledger is append-only (spec 02 §8).
Every change to a row goes with `app.shared.orm.touch(row, now)`, so `updated_at` is the action's
instant (D63).
"""

from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, case, func, select

from app.modules.inventory.models import (
    BookingPart,
    Part,
    PurchaseOrder,
    PurchaseOrderItem,
    StockMovement,
)
from app.shared.enums import PurchaseOrderStatus
from app.shared.repository import ShopScopedRepository

_OPEN_STATUSES = (PurchaseOrderStatus.ORDERED, PurchaseOrderStatus.PARTIALLY_RECEIVED)

AVAILABLE = Part.on_hand - Part.reserved
"""`available` in SQL (never stored)."""

STOCK_STATE = case(
    (AVAILABLE <= 0, "OUT"),
    (Part.reorder_level >= AVAILABLE, "LOW"),
    else_="OK",
)
"""D45 in SQL, the same rule as `domain.stock.stock_state` (OUT wins over LOW)."""

_PART_SORTS: dict[str, Any] = {
    "sku": Part.sku,
    "name": Part.name,
    "available": AVAILABLE,
}


def like_pattern(text: str) -> str:
    """A case-insensitive substring pattern with `%`, `_` and the escape character escaped."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@dataclass(frozen=True, slots=True)
class PartFilters:
    """`GET …/parts` filters (spec 03 §4.10); `sort` is one of `schemas.PartSort`."""

    q: str | None = None
    stock_states: frozenset[str] = frozenset()
    include_inactive: bool = False
    sort: str = "sku"


@dataclass(frozen=True, slots=True)
class ItemTotals:
    item_count: int
    ordered_qty: int
    received_qty: int
    total_cost: Decimal


@dataclass(frozen=True, slots=True)
class StockTotals:
    parts_count: int
    low_stock_count: int
    out_of_stock_count: int
    stock_value: Decimal


class PartRepository(ShopScopedRepository):
    async def get(self, *, shop_id: UUID, part_id: UUID) -> Part | None:
        statement = (
            select(Part)
            .where(Part.shop_id == shop_id, Part.id == part_id)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_many(self, *, shop_id: UUID, part_ids: Collection[UUID]) -> dict[UUID, Part]:
        if not part_ids:
            return {}
        statement = (
            select(Part)
            .where(Part.shop_id == shop_id, Part.id.in_(sorted(part_ids)))
            .execution_options(populate_existing=True)
        )
        parts = (await self.session.execute(statement)).scalars().all()
        return {part.id: part for part in parts}

    async def lock(self, *, shop_id: UUID, part_ids: Collection[UUID]) -> dict[UUID, Part]:
        """`SELECT … FOR UPDATE` on the parts, in ascending id order (D30). Unknown ids or
        another shop's ids are simply absent."""
        if not part_ids:
            return {}
        statement = (
            select(Part)
            .where(Part.shop_id == shop_id, Part.id.in_(sorted(part_ids)))
            .order_by(Part.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        parts = (await self.session.execute(statement)).scalars().all()
        return {part.id: part for part in parts}

    async def sku_exists(
        self, *, shop_id: UUID, sku: str, exclude_part_id: UUID | None = None
    ) -> bool:
        conditions = [Part.shop_id == shop_id, Part.sku == sku]
        if exclude_part_id is not None:
            conditions.append(Part.id != exclude_part_id)
        statement = select(select(Part.id).where(*conditions).exists())
        return bool((await self.session.execute(statement)).scalar_one())

    async def list_page(
        self, *, shop_id: UUID, filters: PartFilters, limit: int, offset: int
    ) -> tuple[list[Part], int]:
        conditions: list[ColumnElement[bool]] = [Part.shop_id == shop_id]
        if not filters.include_inactive:
            conditions.append(Part.is_active.is_(True))
        if filters.q:
            pattern = like_pattern(filters.q)
            conditions.append(
                Part.sku.ilike(pattern, escape="\\") | Part.name.ilike(pattern, escape="\\")
            )
        if filters.stock_states:
            conditions.append(STOCK_STATE.in_(sorted(filters.stock_states)))
        descending = filters.sort.startswith("-")
        key = _PART_SORTS[filters.sort.removeprefix("-")]
        order = (key.desc(), Part.id.desc()) if descending else (key.asc(), Part.id.asc())
        statement = select(Part).where(*conditions).order_by(*order).limit(limit).offset(offset)
        parts = list((await self.session.execute(statement)).scalars().all())
        count = select(func.count()).select_from(Part).where(*conditions)
        total = int((await self.session.execute(count)).scalar_one())
        return parts, total

    async def on_order(self, *, shop_id: UUID, part_ids: Collection[UUID]) -> dict[UUID, int]:
        """Σ `ordered_qty - received_qty` over the items of the shop's open POs, per part."""
        if not part_ids:
            return {}
        outstanding = func.sum(PurchaseOrderItem.ordered_qty - PurchaseOrderItem.received_qty)
        statement = (
            select(PurchaseOrderItem.part_id, outstanding)
            .join(
                PurchaseOrder,
                and_(
                    PurchaseOrder.id == PurchaseOrderItem.purchase_order_id,
                    PurchaseOrder.shop_id == PurchaseOrderItem.shop_id,
                ),
            )
            .where(
                PurchaseOrderItem.shop_id == shop_id,
                PurchaseOrderItem.part_id.in_(sorted(part_ids)),
                PurchaseOrder.status.in_(_OPEN_STATUSES),
            )
            .group_by(PurchaseOrderItem.part_id)
        )
        rows = (await self.session.execute(statement)).all()
        return {part_id: int(total) for part_id, total in rows}

    async def stock_totals(self, *, shop_id: UUID) -> StockTotals:
        """Owner overview figures over **active** parts (`modules/reporting.md`)."""
        active = Part.is_active.is_(True)
        statement = select(
            func.count().filter(active),
            func.count().filter(active, Part.reorder_level >= AVAILABLE),
            func.count().filter(active, AVAILABLE <= 0),
            func.coalesce(func.sum(Part.on_hand * Part.unit_cost).filter(active), 0),
        ).where(Part.shop_id == shop_id)
        parts_count, low, out, value = (await self.session.execute(statement)).one()
        return StockTotals(int(parts_count), int(low), int(out), Decimal(value))

    async def low_stock(self, *, shop_id: UUID, limit: int) -> list[Part]:
        """Active `LOW` / `OUT` parts: `OUT` first, then by available, then by SKU."""
        statement = (
            select(Part)
            .where(
                Part.shop_id == shop_id,
                Part.is_active.is_(True),
                Part.reorder_level >= AVAILABLE,
            )
            .order_by((AVAILABLE <= 0).desc(), AVAILABLE.asc(), Part.sku.asc(), Part.id.asc())
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def count_low_stock(self, *, shop_ids: Collection[UUID]) -> dict[UUID, int]:
        """Active `LOW` + `OUT` parts per shop; shops without any are absent."""
        if not shop_ids:
            return {}
        statement = (
            select(Part.shop_id, func.count())
            .where(
                Part.shop_id.in_(sorted(shop_ids)),
                Part.is_active.is_(True),
                Part.reorder_level >= AVAILABLE,
            )
            .group_by(Part.shop_id)
        )
        rows = (await self.session.execute(statement)).all()
        return {shop_id: int(count) for shop_id, count in rows}


class StockMovementRepository(ShopScopedRepository):
    """The append-only ledger: `add` (inherited) and reads only (spec 02 §8)."""

    async def list_for_part(
        self, *, shop_id: UUID, part_id: UUID, limit: int, offset: int
    ) -> tuple[list[StockMovement], int]:
        """Newest first by `(created_at, seq)` descending (D79)."""
        conditions = (StockMovement.shop_id == shop_id, StockMovement.part_id == part_id)
        statement = (
            select(StockMovement)
            .where(*conditions)
            .order_by(StockMovement.created_at.desc(), StockMovement.seq.desc())
            .limit(limit)
            .offset(offset)
        )
        movements = list((await self.session.execute(statement)).scalars().all())
        count = select(func.count()).select_from(StockMovement).where(*conditions)
        total = int((await self.session.execute(count)).scalar_one())
        return movements, total


class BookingPartRepository(ShopScopedRepository):
    async def list_for_booking(self, *, shop_id: UUID, booking_id: UUID) -> list[BookingPart]:
        """The booking's rows, re-read (the caller holds the booking lock)."""
        return await self.list_for_bookings(shop_id=shop_id, booking_ids=[booking_id])

    async def list_for_bookings(
        self, *, shop_id: UUID, booking_ids: Collection[UUID]
    ) -> list[BookingPart]:
        if not booking_ids:
            return []
        statement = (
            select(BookingPart)
            .where(BookingPart.shop_id == shop_id, BookingPart.booking_id.in_(sorted(booking_ids)))
            .order_by(BookingPart.booking_id, BookingPart.part_id)
            .execution_options(populate_existing=True)
        )
        return list((await self.session.execute(statement)).scalars().all())


class PurchaseOrderRepository(ShopScopedRepository):
    async def get(self, *, shop_id: UUID, po_id: UUID) -> PurchaseOrder | None:
        statement = (
            select(PurchaseOrder)
            .where(PurchaseOrder.shop_id == shop_id, PurchaseOrder.id == po_id)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_for_update(self, *, shop_id: UUID, po_id: UUID) -> PurchaseOrder | None:
        """Lock 2 of a receipt (after the booking, before the parts; D30). Key only."""
        statement = (
            select(PurchaseOrder)
            .where(PurchaseOrder.shop_id == shop_id, PurchaseOrder.id == po_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_many(
        self, *, shop_id: UUID, po_ids: Collection[UUID]
    ) -> dict[UUID, PurchaseOrder]:
        if not po_ids:
            return {}
        statement = select(PurchaseOrder).where(
            PurchaseOrder.shop_id == shop_id, PurchaseOrder.id.in_(sorted(po_ids))
        )
        orders = (await self.session.execute(statement)).scalars().all()
        return {order.id: order for order in orders}

    async def find_id_by_po_number(self, *, shop_id: UUID, po_number: str) -> UUID | None:
        """The PO of this shop with this number (`uq_purchase_orders_shop_id_po_number`)."""
        statement = select(PurchaseOrder.id).where(
            PurchaseOrder.shop_id == shop_id, PurchaseOrder.po_number == po_number
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_page(
        self,
        *,
        shop_id: UUID,
        statuses: Collection[PurchaseOrderStatus],
        booking_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[PurchaseOrder], int]:
        """Open POs first, then newest.

        `ORDER BY (status = 'RECEIVED'), created_at DESC, id DESC` (spec 03 §4.10).
        """
        conditions: list[ColumnElement[bool]] = [PurchaseOrder.shop_id == shop_id]
        if statuses:
            conditions.append(PurchaseOrder.status.in_(sorted(statuses)))
        if booking_id is not None:
            conditions.append(PurchaseOrder.booking_id == booking_id)
        statement = (
            select(PurchaseOrder)
            .where(*conditions)
            .order_by(
                (PurchaseOrder.status == PurchaseOrderStatus.RECEIVED).asc(),
                PurchaseOrder.created_at.desc(),
                PurchaseOrder.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        orders = list((await self.session.execute(statement)).scalars().all())
        count = select(func.count()).select_from(PurchaseOrder).where(*conditions)
        total = int((await self.session.execute(count)).scalar_one())
        return orders, total

    async def list_for_bookings(
        self, *, shop_id: UUID, booking_ids: Collection[UUID]
    ) -> list[PurchaseOrder]:
        """POs linked to these bookings, oldest first (`ix_purchase_orders_booking`)."""
        if not booking_ids:
            return []
        statement = (
            select(PurchaseOrder)
            .where(
                PurchaseOrder.shop_id == shop_id,
                PurchaseOrder.booking_id.in_(sorted(booking_ids)),
            )
            .order_by(PurchaseOrder.created_at.asc(), PurchaseOrder.id.asc())
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def items_with_parts(
        self, *, shop_id: UUID, po_ids: Collection[UUID]
    ) -> list[tuple[PurchaseOrderItem, Part]]:
        """Items (re-read) with their parts, per PO by part SKU."""
        if not po_ids:
            return []
        statement = (
            select(PurchaseOrderItem, Part)
            .join(
                Part,
                and_(
                    Part.id == PurchaseOrderItem.part_id, Part.shop_id == PurchaseOrderItem.shop_id
                ),
            )
            .where(
                PurchaseOrderItem.shop_id == shop_id,
                PurchaseOrderItem.purchase_order_id.in_(sorted(po_ids)),
            )
            .order_by(PurchaseOrderItem.purchase_order_id, Part.sku, PurchaseOrderItem.id)
            .execution_options(populate_existing=True)
        )
        rows = (await self.session.execute(statement)).all()
        return [(item, part) for item, part in rows]

    async def item_totals(
        self, *, shop_id: UUID, po_ids: Collection[UUID]
    ) -> dict[UUID, ItemTotals]:
        """Per PO: item count, Σ ordered, Σ received and Σ `ordered_qty * unit_cost`."""
        if not po_ids:
            return {}
        statement = (
            select(
                PurchaseOrderItem.purchase_order_id,
                func.count(),
                func.sum(PurchaseOrderItem.ordered_qty),
                func.sum(PurchaseOrderItem.received_qty),
                func.sum(PurchaseOrderItem.ordered_qty * PurchaseOrderItem.unit_cost),
            )
            .where(
                PurchaseOrderItem.shop_id == shop_id,
                PurchaseOrderItem.purchase_order_id.in_(sorted(po_ids)),
            )
            .group_by(PurchaseOrderItem.purchase_order_id)
        )
        rows = (await self.session.execute(statement)).all()
        return {
            po_id: ItemTotals(int(count), int(ordered), int(received), Decimal(cost))
            for po_id, count, ordered, received, cost in rows
        }

    async def count_open(self, *, shop_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(PurchaseOrder)
            .where(PurchaseOrder.shop_id == shop_id, PurchaseOrder.status.in_(_OPEN_STATUSES))
        )
        return int((await self.session.execute(statement)).scalar_one())

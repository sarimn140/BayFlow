"""Use cases of the inventory module (`modules/inventory.md` "Public service interface").

- **HTTP use cases** (top-level, each commits once): the parts catalogue, stock adjustments (D82),
  the movement ledger, purchase orders and their receipt. Routes gate roles with `require_roles`;
  every use case re-asserts the D44 role here as well, so direct callers (the seed) cannot bypass
  it.
- **Booking-action side effects** (nested, never commit): T12-T16 and T22 of spec 08, called by
  `bookings.service` inside its transaction while it holds the booking row lock (D30).
- **Reads for other modules**: estimates (live part stock, D40), bookings (booking parts and
  summaries), reporting (stock summary, low-stock counts).
- **The D86 read port** `BookingRefReader`: inventory never imports bookings; bookings registers
  its implementation with `register_booking_ref_reader()` at start-up (its `register_ports()`,
  D89). A read that involves a booking while no reader is registered raises `RuntimeError`: a
  mis-wired app fails loud instead of answering "no bookings" (spec 01 rule 3). Reads without a
  booking id (general POs, adjustments) never touch the port.

Writes follow D30's lock order (booking, held by the caller → purchase order → parts by ascending
id) and D63: a top-level use case reads `utcnow()` once, after its locks; nested functions use the
caller's `now`. Every stock change writes exactly one `stock_movements` row per part with signed
deltas, together with the `parts` balance it changes, under the part's row lock (D42, D79).
"""

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    Conflict,
    Forbidden,
    InsufficientStock,
    InternalError,
    NotFound,
    ValidationFailed,
)
from app.modules.identity import service as identity_service
from app.modules.inventory.domain.po_numbers import is_po_number, new_po_number
from app.modules.inventory.domain.stock import (
    BookingPartLine,
    OrderedItem,
    OrderPartsResult,
    PartBalance,
    PartQty,
    ReceiptLine,
    ReceiptReservation,
    adjusted_on_hand,
    all_fully_reserved,
    available,
    count_available,
    duplicate_positions,
    field_error,
    movement_deltas,
    order_quantities,
    plan_consumption,
    plan_full_reservation,
    plan_order,
    plan_receipt,
    plan_receipt_reservation,
    plan_release,
    purchase_order_status,
    receipt_on_hand_errors,
    shortage,
    stock_state,
    sum_by_part,
)
from app.modules.inventory.events import PurchaseOrderReceived, PurchaseOrderReceiving
from app.modules.inventory.models import (
    BookingPart,
    Part,
    PurchaseOrder,
    PurchaseOrderItem,
    StockMovement,
)
from app.modules.inventory.repository import (
    BookingPartRepository,
    ItemTotals,
    PartFilters,
    PartRepository,
    PurchaseOrderRepository,
    StockMovementRepository,
)
from app.modules.inventory.schemas import (
    MAX_ADJUSTMENT,
    MAX_REASON_LENGTH,
    BookingPartRead,
    BookingPartsRead,
    BookingRef,
    PartCreate,
    PartRead,
    PartRef,
    PartSort,
    PartsSummary,
    PartStockRef,
    PartUpdate,
    PurchaseOrderCreate,
    PurchaseOrderItemRead,
    PurchaseOrderRead,
    PurchaseOrderReceive,
    PurchaseOrderReceiveRead,
    PurchaseOrderRef,
    PurchaseOrderSummary,
    StockAdjustmentRead,
    StockMovementBookingRef,
    StockMovementPurchaseOrderRef,
    StockMovementRead,
    StockSummary,
    UserRef,
)
from app.shared.auth import ShopContext
from app.shared.clock import utcnow
from app.shared.enums import (
    BookingStatus,
    MembershipRole,
    PurchaseOrderStatus,
    StockMovementType,
    StockState,
)
from app.shared.money import MAX_AMOUNT
from app.shared.orm import touch
from app.shared.pagination import Page, PageParams
from app.shared.repository import constraint_name
from app.shared.uow import UnitOfWork

__all__ = [
    "CATALOGUE_EDITORS",
    "LEDGER_READERS",
    "PART_READERS",
    "STOCK_OPERATORS",
    "BookingRefData",
    "BookingRefReader",
    "OrderPartsResult",
    "PartQty",
    "ReceiptReservation",
    "StockState",
    "adjust_stock",
    "booking_ref_reader",
    "consume_reservations",
    "count_low_stock",
    "create_booking_parts",
    "create_part",
    "create_purchase_order",
    "find_purchase_order_id",
    "get_booking_parts",
    "get_booking_parts_summary",
    "get_parts_for_estimate",
    "get_purchase_order",
    "get_stock_summary",
    "list_part_movements",
    "list_parts",
    "list_purchase_orders",
    "order_missing_parts",
    "receive_purchase_order",
    "register_booking_ref_reader",
    "release_reservations",
    "reserve_outstanding",
    "reserve_received_for_booking",
    "update_part",
]

# --- Roles (D16, D44; spec 04 RBAC B; the capabilities of D66) ----------------------------------

PART_READERS: tuple[MembershipRole, ...] = (
    MembershipRole.OWNER,
    MembershipRole.SERVICE_ADVISOR,
    MembershipRole.TECHNICIAN,
    MembershipRole.PARTS_PERSON,
)
"""Parts list with stock: the Owner reads it, SA and technician use it as the part picker."""
CATALOGUE_EDITORS: tuple[MembershipRole, ...] = (
    MembershipRole.OWNER,
    MembershipRole.PARTS_PERSON,
)
"""`parts.manage`: create and edit parts (never their stock)."""
STOCK_OPERATORS: tuple[MembershipRole, ...] = (MembershipRole.PARTS_PERSON,)
"""`stock.manage`: adjustments, general purchase orders and receipts."""
LEDGER_READERS: tuple[MembershipRole, ...] = (MembershipRole.OWNER, MembershipRole.PARTS_PERSON)
"""Purchase-order list and detail, and the movement ledger (the Owner reads only)."""

LOW_STOCK_LIMIT = 5
MAX_PO_NUMBER_ATTEMPTS = 5
PO_NUMBER_CONSTRAINT = "uq_purchase_orders_shop_id_po_number"
SKU_CONSTRAINT = "uq_parts_shop_id_sku"
UNKNOWN_USER_NAME = "Unknown user"
_CENTS = Decimal("0.01")
_NO_ITEMS = ItemTotals(item_count=0, ordered_qty=0, received_qty=0, total_cost=Decimal(0))

po_number_factory: Callable[[], str] = new_po_number
"""Draws random PO numbers; tests replace it to force a collision (INV-33)."""


def _require_role(ctx: ShopContext, allowed: Collection[MembershipRole], action: str) -> None:
    if ctx.role not in allowed:
        raise Forbidden(f"Your role in this shop cannot {action}.")


# --- The booking-reference read port (D86) ------------------------------------------------------


class BookingRefData(Protocol):
    """Structural: any object with these read-only attributes (bookings' `get_booking_refs`)."""

    @property
    def id(self) -> UUID: ...

    @property
    def reference(self) -> str: ...

    @property
    def status(self) -> BookingStatus: ...

    @property
    def version(self) -> int: ...


class BookingRefReader(Protocol):
    """Reads `BookingRef` data for booking ids of one shop, on the caller's session."""

    async def __call__(
        self, session: AsyncSession, *, shop_id: UUID, booking_ids: Collection[UUID]
    ) -> Mapping[UUID, BookingRefData]: ...


@dataclass(slots=True)
class _BookingRefPort:
    reader: BookingRefReader | None = None


_booking_refs = _BookingRefPort()

UNREGISTERED_READER_MESSAGE = (
    "no BookingRefReader is registered: bookings.service.register_ports() must run first (D86, D89)"
)


def register_booking_ref_reader(reader: BookingRefReader | None) -> None:
    """Install the bookings implementation (`bookings.service.register_ports()`, run by
    `create_app()` and the seed's start-up, D86, D89); `None` removes it (tests)."""
    _booking_refs.reader = reader


def booking_ref_reader() -> BookingRefReader | None:
    """The registered reader, if any."""
    return _booking_refs.reader


async def _read_booking_refs(
    session: AsyncSession, *, shop_id: UUID, booking_ids: Iterable[UUID | None]
) -> Mapping[UUID, BookingRefData]:
    """`BookingRef` data through the port. With no booking id there is nothing to read; with one
    and no registered reader the app is mis-wired: fail loud (spec 01 rule 3), never pretend the
    bookings do not exist."""
    ids = sorted({booking_id for booking_id in booking_ids if booking_id is not None})
    if not ids:
        return {}
    reader = _booking_refs.reader
    if reader is None:
        raise RuntimeError(UNREGISTERED_READER_MESSAGE)
    return await reader(session, shop_id=shop_id, booking_ids=ids)


def _booking_ref(data: BookingRefData | None) -> BookingRef | None:
    if data is None:
        return None
    return BookingRef(
        id=data.id, reference=data.reference, status=data.status, version=data.version
    )


# --- Read assembly ------------------------------------------------------------------------------


async def _user_refs(session: AsyncSession, user_ids: Iterable[UUID]) -> dict[UUID, UserRef]:
    """`UserRef`s in one identity look-up (names of any status: deactivated staff keep theirs)."""
    ids = set(user_ids)
    if not ids:
        return {}
    users = await identity_service.get_users_by_ids(session, ids)
    return {
        user_id: UserRef(
            user_id=user_id,
            full_name=users[user_id].full_name if user_id in users else UNKNOWN_USER_NAME,
        )
        for user_id in ids
    }


def _part_read(part: Part, on_order: int) -> PartRead:
    available_qty = available(part.on_hand, part.reserved)
    return PartRead(
        id=part.id,
        sku=part.sku,
        name=part.name,
        unit_cost=part.unit_cost,
        is_active=part.is_active,
        on_hand=part.on_hand,
        reserved=part.reserved,
        available=available_qty,
        reorder_level=part.reorder_level,
        stock_state=stock_state(available_qty, part.reorder_level),
        on_order=on_order,
        created_at=part.created_at,
        updated_at=part.updated_at,
    )


def _part_stock_ref(part: Part, *, include_stock: bool) -> PartStockRef:
    available_qty = available(part.on_hand, part.reserved)
    return PartStockRef(
        id=part.id,
        sku=part.sku,
        name=part.name,
        unit_cost=part.unit_cost,
        is_active=part.is_active,
        on_hand=part.on_hand if include_stock else None,
        reserved=part.reserved if include_stock else None,
        available=available_qty if include_stock else None,
        reorder_level=part.reorder_level if include_stock else None,
        stock_state=stock_state(available_qty, part.reorder_level) if include_stock else None,
    )


async def _part_reads(
    session: AsyncSession, shop_id: UUID, parts: Sequence[Part]
) -> list[PartRead]:
    on_order = await PartRepository(session).on_order(
        shop_id=shop_id, part_ids=[part.id for part in parts]
    )
    return [_part_read(part, on_order.get(part.id, 0)) for part in parts]


async def _movement_reads(
    session: AsyncSession, shop_id: UUID, movements: Sequence[StockMovement]
) -> list[StockMovementRead]:
    """A fixed number of queries whatever the page size: actors, bookings, PO numbers."""
    users = await _user_refs(session, (movement.actor_user_id for movement in movements))
    bookings = await _read_booking_refs(
        session, shop_id=shop_id, booking_ids=(movement.booking_id for movement in movements)
    )
    orders = await PurchaseOrderRepository(session).get_many(
        shop_id=shop_id,
        po_ids={m.purchase_order_id for m in movements if m.purchase_order_id is not None},
    )
    reads: list[StockMovementRead] = []
    for movement in movements:
        booking = bookings.get(movement.booking_id) if movement.booking_id else None
        order = orders.get(movement.purchase_order_id) if movement.purchase_order_id else None
        reads.append(
            StockMovementRead(
                id=movement.id,
                part_id=movement.part_id,
                movement_type=movement.movement_type,
                quantity=movement.quantity,
                on_hand_delta=movement.on_hand_delta,
                reserved_delta=movement.reserved_delta,
                booking=(
                    StockMovementBookingRef(id=booking.id, reference=booking.reference)
                    if booking is not None
                    else None
                ),
                purchase_order=(
                    StockMovementPurchaseOrderRef(id=order.id, po_number=order.po_number)
                    if order is not None
                    else None
                ),
                actor=users[movement.actor_user_id],
                note=movement.note,
                created_at=movement.created_at,
            )
        )
    return reads


def _po_summary(
    order: PurchaseOrder,
    totals: ItemTotals,
    users: Mapping[UUID, UserRef],
    bookings: Mapping[UUID, BookingRefData],
) -> PurchaseOrderSummary:
    return PurchaseOrderSummary(
        id=order.id,
        po_number=order.po_number,
        status=order.status,
        supplier_name=order.supplier_name,
        booking=_booking_ref(bookings.get(order.booking_id)) if order.booking_id else None,
        item_count=totals.item_count,
        ordered_qty_total=totals.ordered_qty,
        received_qty_total=totals.received_qty,
        total_cost=totals.total_cost,
        created_by=users[order.created_by_user_id],
        created_at=order.created_at,
        received_at=order.received_at,
    )


async def _po_summaries(
    session: AsyncSession, shop_id: UUID, orders: Sequence[PurchaseOrder]
) -> list[PurchaseOrderSummary]:
    totals = await PurchaseOrderRepository(session).item_totals(
        shop_id=shop_id, po_ids=[order.id for order in orders]
    )
    users = await _user_refs(session, (order.created_by_user_id for order in orders))
    bookings = await _read_booking_refs(
        session, shop_id=shop_id, booking_ids=(order.booking_id for order in orders)
    )
    return [
        _po_summary(order, totals.get(order.id, _NO_ITEMS), users, bookings) for order in orders
    ]


async def _po_detail(
    session: AsyncSession, shop_id: UUID, order: PurchaseOrder
) -> PurchaseOrderRead:
    rows = await PurchaseOrderRepository(session).items_with_parts(
        shop_id=shop_id, po_ids=[order.id]
    )
    items = [
        PurchaseOrderItemRead(
            id=item.id,
            part=PartRef(id=part.id, sku=part.sku, name=part.name),
            ordered_qty=item.ordered_qty,
            received_qty=item.received_qty,
            outstanding_qty=item.ordered_qty - item.received_qty,
            unit_cost=item.unit_cost,
            line_cost=item.unit_cost * item.ordered_qty,
        )
        for item, part in rows
    ]
    totals = ItemTotals(
        item_count=len(items),
        ordered_qty=sum(item.ordered_qty for item in items),
        received_qty=sum(item.received_qty for item in items),
        total_cost=sum((item.line_cost for item in items), Decimal(0)),
    )
    users = await _user_refs(session, [order.created_by_user_id])
    bookings = await _read_booking_refs(session, shop_id=shop_id, booking_ids=[order.booking_id])
    summary = _po_summary(order, totals, users, bookings)
    return PurchaseOrderRead(**dict(summary), items=items, updated_at=order.updated_at)


# --- Writes shared by several use cases ---------------------------------------------------------


def _line(row: BookingPart) -> BookingPartLine:
    return BookingPartLine(
        part_id=row.part_id,
        required_qty=row.required_qty,
        reserved_qty=row.reserved_qty,
        consumed_qty=row.consumed_qty,
    )


def _balances(parts: Mapping[UUID, Part]) -> dict[UUID, PartBalance]:
    return {
        part_id: PartBalance(part_id=part_id, on_hand=part.on_hand, reserved=part.reserved)
        for part_id, part in parts.items()
    }


@dataclass(frozen=True, slots=True)
class _Ledger:
    """What the movements of one action share: shop, actor, instant and links (D42, D63)."""

    shop_id: UUID
    actor_user_id: UUID
    now: datetime
    booking_id: UUID | None = None
    purchase_order_id: UUID | None = None

    def write(
        self, session: AsyncSession, part: Part, movement_type: StockMovementType, quantity: int
    ) -> None:
        """Append one ledger row and apply its signed deltas to the (locked) part balance."""
        on_hand_delta, reserved_delta = movement_deltas(movement_type, quantity)
        session.add(
            StockMovement(
                shop_id=self.shop_id,
                part_id=part.id,
                movement_type=movement_type,
                quantity=quantity,
                on_hand_delta=on_hand_delta,
                reserved_delta=reserved_delta,
                booking_id=self.booking_id,
                purchase_order_id=self.purchase_order_id,
                actor_user_id=self.actor_user_id,
                created_at=self.now,
            )
        )
        part.on_hand += on_hand_delta
        part.reserved += reserved_delta
        touch(part, self.now)

    def reserve(
        self,
        session: AsyncSession,
        rows: Mapping[UUID, BookingPart],
        parts: Mapping[UUID, Part],
        reserve: Iterable[PartQty],
    ) -> None:
        """`RESERVE` movements: `parts.reserved` and `booking_parts.reserved_qty` up together."""
        for item in reserve:
            self.write(session, parts[item.part_id], StockMovementType.RESERVE, item.qty)
            row = rows[item.part_id]
            row.reserved_qty += item.qty
            touch(row, self.now)


@dataclass(frozen=True, slots=True)
class _PoLine:
    part_id: UUID
    quantity: int
    unit_cost: Decimal


@dataclass(frozen=True, slots=True)
class _NewPurchaseOrder:
    shop_id: UUID
    booking_id: UUID | None
    supplier_name: str | None
    created_by_user_id: UUID
    now: datetime


def _check_po_amounts(lines: Sequence[_PoLine], fields: Sequence[str]) -> None:
    """Every line cost and the PO total must fit `numeric(12,2)` (Money's limit), else 422 — never
    a database error or an invalid response. `fields` names each line's field in the request."""
    too_large = {
        field
        for line, field in zip(lines, fields, strict=True)
        if line.unit_cost * line.quantity > MAX_AMOUNT
    }
    errors = [
        field_error(field, "value_error", "The amount is too large.")
        for field in dict.fromkeys(fields)  # request order, each field once
        if field in too_large
    ]
    total = sum((line.unit_cost * line.quantity for line in lines), Decimal(0))
    if not errors and total > MAX_AMOUNT:
        errors.append(field_error("items", "value_error", "The purchase-order total is too large."))
    if errors:
        raise ValidationFailed(errors=errors)


async def _insert_purchase_order(
    session: AsyncSession,
    new: _NewPurchaseOrder,
    lines: Sequence[_PoLine],
    po_number: str | None,
) -> PurchaseOrder:
    """Insert an `ORDERED` PO with a fresh `PO-XXXXXX` (or the seed's fixed number) and its items.

    The PO insert runs in a SAVEPOINT and draws a new number on
    `uq_purchase_orders_shop_id_po_number`, up to `MAX_PO_NUMBER_ATTEMPTS` times (spec 02 §7.6);
    rolling back to the savepoint keeps the outer transaction and the locks it holds.
    """
    if po_number is not None and not is_po_number(po_number):
        msg = f"{po_number!r} is not a PO-XXXXXX number"
        raise ValueError(msg)
    order_id = uuid4()
    for _ in range(1 if po_number is not None else MAX_PO_NUMBER_ATTEMPTS):
        order = PurchaseOrder(
            id=order_id,
            shop_id=new.shop_id,
            po_number=po_number or po_number_factory(),
            status=PurchaseOrderStatus.ORDERED,
            booking_id=new.booking_id,
            supplier_name=new.supplier_name,
            created_by_user_id=new.created_by_user_id,
            received_at=None,
            created_at=new.now,
            updated_at=new.now,
        )
        try:
            async with session.begin_nested():
                session.add(order)
                await session.flush()  # only the PO: begin_nested() flushed the rest
        except IntegrityError as exc:
            if constraint_name(exc) != PO_NUMBER_CONSTRAINT:
                raise
            continue
        session.add_all(
            PurchaseOrderItem(
                shop_id=new.shop_id,
                purchase_order_id=order.id,
                part_id=line.part_id,
                ordered_qty=line.quantity,
                received_qty=0,
                unit_cost=line.unit_cost,
                created_at=new.now,
                updated_at=new.now,
            )
            for line in lines
        )
        await session.flush()
        return order
    if po_number is not None:
        raise Conflict(f"Purchase order {po_number} already exists in this shop.")
    raise InternalError("Could not allocate a purchase-order number. Please try again.")


def _reject_duplicates(values: Sequence[UUID], field: str, message: str) -> None:
    """Distinct ids in a request list (spec 03): `items.N.<field>` `duplicate`, 422."""
    repeated = duplicate_positions(values)
    if repeated:
        raise ValidationFailed(
            errors=[
                field_error(f"items.{index}.{field}", "duplicate", message) for index in repeated
            ]
        )


def _duplicate_sku(sku: str) -> Conflict:
    return Conflict(f"A part with SKU {sku} already exists in this shop.")


async def _flush_part(session: AsyncSession, sku: str) -> None:
    """Flush a catalogue write; a concurrent duplicate SKU (the unique backstop) is 409."""
    try:
        await session.flush()
    except IntegrityError as exc:
        if constraint_name(exc) == SKU_CONSTRAINT:
            raise _duplicate_sku(sku) from exc
        raise


# --- HTTP use cases: parts catalogue (D44, D45) -------------------------------------------------


async def list_parts(  # noqa: PLR0913 - the spec'd query parameters (spec 03 §4.10)
    session: AsyncSession,
    ctx: ShopContext,
    *,
    q: str | None,
    stock_states: Collection[StockState],
    include_inactive: bool,
    sort: PartSort,
    page: PageParams,
) -> Page[PartRead]:
    """`GET …/parts`: the inventory table with `available`, `stock_state` and `on_order`."""
    _require_role(ctx, PART_READERS, "view parts")
    filters = PartFilters(
        q=(q.strip() or None) if q else None,
        stock_states=frozenset(state.value for state in stock_states),
        include_inactive=include_inactive,
        sort=sort,
    )
    parts, total = await PartRepository(session).list_page(
        shop_id=ctx.shop_id, filters=filters, limit=page.limit, offset=page.offset
    )
    return Page.build(await _part_reads(session, ctx.shop_id, parts), total=total, params=page)


async def create_part(uow: UnitOfWork, ctx: ShopContext, data: PartCreate) -> PartRead:
    """`POST …/parts`: a new part always starts at `on_hand = reserved = 0` (D44)."""
    _require_role(ctx, CATALOGUE_EDITORS, "create parts")
    repo = PartRepository(uow.session)
    if await repo.sku_exists(shop_id=ctx.shop_id, sku=data.sku):
        raise _duplicate_sku(data.sku)
    now = utcnow()
    part = repo.add(
        Part(
            shop_id=ctx.shop_id,
            sku=data.sku,
            name=data.name,
            unit_cost=data.unit_cost,
            on_hand=0,
            reserved=0,
            reorder_level=data.reorder_level,
            is_active=data.is_active,
            created_at=now,
            updated_at=now,
        )
    )
    await _flush_part(uow.session, data.sku)
    result = _part_read(part, on_order=0)
    await uow.commit()
    return result


async def update_part(
    uow: UnitOfWork, ctx: ShopContext, part_id: UUID, data: PartUpdate
) -> PartRead:
    """`PATCH …/parts/{part_id}`: catalogue fields only; estimate lines and PO items keep their
    own prices and names. Locks the part row (spec 02 §7.2)."""
    _require_role(ctx, CATALOGUE_EDITORS, "edit parts")
    repo = PartRepository(uow.session)
    part = (await repo.lock(shop_id=ctx.shop_id, part_ids=[part_id])).get(part_id)
    if part is None:
        raise NotFound
    if (
        data.sku is not None
        and data.sku != part.sku
        and await repo.sku_exists(shop_id=ctx.shop_id, sku=data.sku, exclude_part_id=part_id)
    ):
        raise _duplicate_sku(data.sku)
    now = utcnow()
    if data.sku is not None:
        part.sku = data.sku
    if data.name is not None:
        part.name = data.name
    if data.unit_cost is not None:
        part.unit_cost = data.unit_cost
    if data.reorder_level is not None:
        part.reorder_level = data.reorder_level
    if data.is_active is not None:
        part.is_active = data.is_active
    touch(part, now)
    await _flush_part(uow.session, part.sku)
    [result] = await _part_reads(uow.session, ctx.shop_id, [part])
    await uow.commit()
    return result


# --- HTTP use cases: adjustments and the ledger (D42, D79, D82) ----------------------------------


def _check_adjustment_input(quantity_delta: int, reason: str) -> str:
    """The schema's rules again, for direct callers such as the seed; returns the trimmed note."""
    note = reason.strip()
    errors = []
    if quantity_delta == 0 or abs(quantity_delta) > MAX_ADJUSTMENT:
        errors.append(
            field_error(
                "quantity_delta",
                "value_error",
                f"Enter a non-zero change between -{MAX_ADJUSTMENT} and {MAX_ADJUSTMENT}.",
            )
        )
    if not note or len(note) > MAX_REASON_LENGTH:
        errors.append(
            field_error(
                "reason", "value_error", f"Give a reason of 1-{MAX_REASON_LENGTH} characters."
            )
        )
    if errors:
        raise ValidationFailed(errors=errors)
    return note


async def adjust_stock(
    uow: UnitOfWork, ctx: ShopContext, *, part_id: UUID, quantity_delta: int, reason: str
) -> StockAdjustmentRead:
    """`POST …/parts/{part_id}/adjustments`: one `ADJUST` movement under the part lock (D82).

    Opening stock and count corrections. Below `reserved` or below 0 → 409 `INSUFFICIENT_STOCK`
    and nothing changes (INV-25). Parts Person only (D44). Inactive parts can be adjusted.
    """
    _require_role(ctx, STOCK_OPERATORS, "adjust stock")
    note = _check_adjustment_input(quantity_delta, reason)
    session = uow.session
    locked = await PartRepository(session).lock(shop_id=ctx.shop_id, part_ids=[part_id])
    part = locked.get(part_id)
    if part is None:
        raise NotFound
    now = utcnow()
    part.on_hand = adjusted_on_hand(
        on_hand=part.on_hand, reserved=part.reserved, quantity_delta=quantity_delta
    )
    touch(part, now)
    movement = StockMovement(
        shop_id=ctx.shop_id,
        part_id=part.id,
        movement_type=StockMovementType.ADJUST,
        quantity=abs(quantity_delta),
        on_hand_delta=quantity_delta,
        reserved_delta=0,
        booking_id=None,
        purchase_order_id=None,
        actor_user_id=ctx.user.id,
        note=note,
        created_at=now,
    )
    session.add(movement)
    await session.flush()
    [part_read] = await _part_reads(session, ctx.shop_id, [part])
    [movement_read] = await _movement_reads(session, ctx.shop_id, [movement])
    result = StockAdjustmentRead(part=part_read, movement=movement_read)
    await uow.commit()
    return result


async def list_part_movements(
    session: AsyncSession, ctx: ShopContext, part_id: UUID, page: PageParams
) -> Page[StockMovementRead]:
    """`GET …/parts/{part_id}/movements` (P1): the part's ledger, newest first (D79)."""
    _require_role(ctx, LEDGER_READERS, "view the stock ledger")
    if await PartRepository(session).get(shop_id=ctx.shop_id, part_id=part_id) is None:
        raise NotFound
    movements, total = await StockMovementRepository(session).list_for_part(
        shop_id=ctx.shop_id, part_id=part_id, limit=page.limit, offset=page.offset
    )
    items = await _movement_reads(session, ctx.shop_id, movements)
    return Page.build(items, total=total, params=page)


# --- HTTP use cases: purchase orders (D43) ------------------------------------------------------


async def list_purchase_orders(
    session: AsyncSession,
    ctx: ShopContext,
    *,
    statuses: Collection[PurchaseOrderStatus],
    booking_id: UUID | None,
    page: PageParams,
) -> Page[PurchaseOrderSummary]:
    """`GET …/purchase-orders`: open POs first, then newest."""
    _require_role(ctx, LEDGER_READERS, "view purchase orders")
    orders, total = await PurchaseOrderRepository(session).list_page(
        shop_id=ctx.shop_id,
        statuses=statuses,
        booking_id=booking_id,
        limit=page.limit,
        offset=page.offset,
    )
    items = await _po_summaries(session, ctx.shop_id, orders)
    return Page.build(items, total=total, params=page)


async def get_purchase_order(
    session: AsyncSession, ctx: ShopContext, po_id: UUID
) -> PurchaseOrderRead:
    """`GET …/purchase-orders/{po_id}`."""
    _require_role(ctx, LEDGER_READERS, "view purchase orders")
    order = await PurchaseOrderRepository(session).get(shop_id=ctx.shop_id, po_id=po_id)
    if order is None:
        raise NotFound
    return await _po_detail(session, ctx.shop_id, order)


async def create_purchase_order(
    uow: UnitOfWork,
    ctx: ShopContext,
    data: PurchaseOrderCreate,
    *,
    po_number: str | None = None,
) -> PurchaseOrderRead:
    """`POST …/purchase-orders`: a general restock PO (`ORDERED`, no booking, D43).

    Items reference distinct **active** parts of this shop (`invalid_reference`, `duplicate`);
    `unit_cost` defaults to the part's cost. `po_number` is internal: only the seed passes it
    (`PO-SEED01`, `PO-SEED02`); it is absent from every HTTP schema. No row is locked.
    """
    _require_role(ctx, STOCK_OPERATORS, "create purchase orders")
    _reject_duplicates(
        [item.part_id for item in data.items], "part_id", "Each part can be ordered only once."
    )
    session = uow.session
    parts = await PartRepository(session).get_many(
        shop_id=ctx.shop_id, part_ids={item.part_id for item in data.items}
    )
    invalid = [
        field_error(
            f"items.{index}.part_id", "invalid_reference", "Choose an active part of this shop."
        )
        for index, item in enumerate(data.items)
        if item.part_id not in parts or not parts[item.part_id].is_active
    ]
    if invalid:
        raise ValidationFailed(errors=invalid)
    lines = [
        _PoLine(
            part_id=item.part_id,
            quantity=item.quantity,
            unit_cost=parts[item.part_id].unit_cost if item.unit_cost is None else item.unit_cost,
        )
        for item in data.items
    ]
    _check_po_amounts(lines, [f"items.{index}.quantity" for index in range(len(lines))])
    new = _NewPurchaseOrder(
        shop_id=ctx.shop_id,
        booking_id=None,
        supplier_name=data.supplier_name,
        created_by_user_id=ctx.user.id,
        now=utcnow(),
    )
    order = await _insert_purchase_order(session, new, lines, po_number)
    result = await _po_detail(session, ctx.shop_id, order)
    await uow.commit()
    return result


async def _lock_linked_booking(
    uow: UnitOfWork, ctx: ShopContext, order: PurchaseOrder
) -> BookingStatus | None:
    """Receipt step 2: let bookings lock the linked booking first (D30, D43), then return its
    status *before* the receipt (`None` for a general PO or an unknown booking).

    The status is copied out now: a reader may hand back a live object (an ORM row in the
    session's identity map) that the `PurchaseOrderReceived` handlers later move to
    `PARTS_READY`, so holding on to the object would compare the booking with itself.

    `PurchaseOrderReceiving.occurred_at` is read here, before any lock, because the event must run
    before inventory locks anything. It is informational only: no row is ever written with it;
    every write of the receipt uses the single instant read after the locks (D63).
    """
    if order.booking_id is None:
        return None
    await uow.publish(
        PurchaseOrderReceiving(
            shop_id=ctx.shop_id,
            purchase_order_id=order.id,
            booking_id=order.booking_id,
            actor_user_id=ctx.user.id,
            occurred_at=utcnow(),
        )
    )
    refs = await _read_booking_refs(
        uow.session, shop_id=ctx.shop_id, booking_ids=[order.booking_id]
    )
    before = refs.get(order.booking_id)
    return BookingStatus(before.status) if before is not None else None


async def _record_receipt(
    session: AsyncSession,
    ledger: _Ledger,
    order: PurchaseOrder,
    data: PurchaseOrderReceive,
) -> tuple[PartQty, ...]:
    """Receipt steps 4-6 under the PO lock: validate, lock the parts, write, derive the status."""
    rows = await PurchaseOrderRepository(session).items_with_parts(
        shop_id=ledger.shop_id, po_ids=[order.id]
    )
    items = {item.id: item for item, _ in rows}
    plan = plan_receipt(
        order.status,
        [
            OrderedItem(
                item_id=item.id,
                part_id=item.part_id,
                ordered_qty=item.ordered_qty,
                received_qty=item.received_qty,
            )
            for item in items.values()
        ],
        [
            ReceiptLine(
                item_id=line.item_id,
                quantity=line.quantity,
                expected_received_qty=line.expected_received_qty,
            )
            for line in data.items
        ],
    )
    parts = await PartRepository(session).lock(
        shop_id=ledger.shop_id, part_ids={received.part_id for received in plan}
    )
    positions = {line.item_id: index for index, line in enumerate(data.items)}
    errors = receipt_on_hand_errors(plan, positions, _balances(parts))
    if errors:
        raise ValidationFailed(errors=errors)
    for received in plan:
        ledger.write(session, parts[received.part_id], StockMovementType.RECEIVE, received.quantity)
        item = items[received.item_id]
        item.received_qty += received.quantity
        touch(item, ledger.now)
    order.status = purchase_order_status(
        (item.ordered_qty, item.received_qty) for item in items.values()
    )
    if order.status == PurchaseOrderStatus.RECEIVED:
        order.received_at = ledger.now
    touch(order, ledger.now)
    await session.flush()
    return sum_by_part(PartQty(received.part_id, received.quantity) for received in plan)


async def receive_purchase_order(
    uow: UnitOfWork, ctx: ShopContext, po_id: UUID, data: PurchaseOrderReceive
) -> PurchaseOrderReceiveRead:
    """`POST …/purchase-orders/{po_id}/receive` (spec 03 §5.3; `modules/inventory.md` steps 1-9).

    1. Read the PO header unlocked (`booking_id` never changes after insert); 404 if absent.
    2. Linked PO: publish `PurchaseOrderReceiving` (bookings locks the booking), then snapshot
       the booking's status.
    3. Lock the PO, then read `now` once: every row this receipt writes (and the handlers write
       through `PurchaseOrderReceived.occurred_at`) carries that instant (D63).
    4-6. Validate in spec order, lock the received parts (ascending), write `RECEIVE` movements
       and item quantities, derive the PO status.
    7. Publish `PurchaseOrderReceived` (bookings may reserve and apply `RECEIVE_PARTS`).
    8. Build the response: `receive_parts_applied` = the booking moved `PARTS_ORDERED` →
       `PARTS_READY` in this transaction. 9. Commit. Any Parts Person of the shop may receive.
    """
    _require_role(ctx, STOCK_OPERATORS, "receive purchase orders")
    _reject_duplicates(
        [line.item_id for line in data.items],
        "item_id",
        "Each item can be received only once per request.",
    )
    orders = PurchaseOrderRepository(uow.session)
    header = await orders.get(shop_id=ctx.shop_id, po_id=po_id)
    if header is None:
        raise NotFound
    status_before = await _lock_linked_booking(uow, ctx, header)
    order = await orders.get_for_update(shop_id=ctx.shop_id, po_id=po_id)
    if order is None:  # pragma: no cover - purchase orders are never deleted
        raise NotFound
    ledger = _Ledger(
        shop_id=ctx.shop_id, actor_user_id=ctx.user.id, now=utcnow(), purchase_order_id=po_id
    )
    received = await _record_receipt(uow.session, ledger, order, data)
    await uow.publish(
        PurchaseOrderReceived(
            shop_id=ctx.shop_id,
            purchase_order_id=po_id,
            po_number=order.po_number,
            booking_id=order.booking_id,
            received=received,
            actor_user_id=ctx.user.id,
            occurred_at=ledger.now,
        )
    )
    detail = await _po_detail(uow.session, ctx.shop_id, order)
    applied = (
        status_before == BookingStatus.PARTS_ORDERED
        and detail.booking is not None
        and detail.booking.status == BookingStatus.PARTS_READY
    )
    result = PurchaseOrderReceiveRead(purchase_order=detail, receive_parts_applied=applied)
    await uow.commit()
    return result


# --- Booking-action side effects (spec 08 T12-T16, T22; nested, never commit) -------------------


async def _booking_rows(
    session: AsyncSession, *, shop_id: UUID, booking_id: UUID
) -> dict[UUID, BookingPart]:
    rows = await BookingPartRepository(session).list_for_booking(
        shop_id=shop_id, booking_id=booking_id
    )
    return {row.part_id: row for row in rows}


async def create_booking_parts(
    uow: UnitOfWork,
    *,
    shop_id: UUID,
    booking_id: UUID,
    requirements: Sequence[PartQty],
    now: datetime,
) -> None:
    """T12: one `booking_parts` row per part of the approved estimate, quantities summed.

    No stock change and no part lock; zero requirements give zero rows (labour-only job, D31).
    """
    merged = sum_by_part(requirements)
    if any(item.qty <= 0 for item in merged):
        msg = "booking part requirements must be positive"
        raise ValueError(msg)
    uow.session.add_all(
        BookingPart(
            shop_id=shop_id,
            booking_id=booking_id,
            part_id=item.part_id,
            required_qty=item.qty,
            reserved_qty=0,
            consumed_qty=0,
            created_at=now,
            updated_at=now,
        )
        for item in merged
    )
    await uow.session.flush()


async def order_missing_parts(  # noqa: PLR0913 - the spec'd signature (modules/inventory.md)
    uow: UnitOfWork,
    *,
    shop_id: UUID,
    booking_id: UUID,
    actor_user_id: UUID,
    items: Sequence[PartQty] | None,
    supplier_name: str | None,
    now: datetime,
) -> OrderPartsResult:
    """T13: reserve what is available now and order the shortages on a booking-linked PO.

    Nothing short (incl. zero rows) → 409 `CONFLICT`, nothing written (INV-03). `items` given →
    they must cover exactly the short parts with at least the shortage (422, INV-04, INV-27).
    Inactive parts can still be ordered here: the approved estimate needs them (D44).
    """
    session = uow.session
    rows = await _booking_rows(session, shop_id=shop_id, booking_id=booking_id)
    parts = await PartRepository(session).lock(shop_id=shop_id, part_ids=rows.keys())
    plan = plan_order([_line(row) for row in rows.values()], _balances(parts))
    if not plan.shortages:
        raise Conflict("All parts are available — use mark-parts-ready.")
    quantities = order_quantities(plan.shortages, items)
    lines = [
        _PoLine(part_id=item.part_id, quantity=item.qty, unit_cost=parts[item.part_id].unit_cost)
        for item in quantities
    ]
    positions = {item.part_id: index for index, item in enumerate(items or ())}
    _check_po_amounts(
        lines,
        [
            f"items.{positions[line.part_id]}.quantity" if line.part_id in positions else "items"
            for line in lines
        ],
    )
    ledger = _Ledger(shop_id=shop_id, actor_user_id=actor_user_id, now=now, booking_id=booking_id)
    ledger.reserve(session, rows, parts, plan.reserve)
    supplier = supplier_name.strip() if supplier_name else ""
    new = _NewPurchaseOrder(
        shop_id=shop_id,
        booking_id=booking_id,
        supplier_name=supplier or None,
        created_by_user_id=actor_user_id,
        now=now,
    )
    order = await _insert_purchase_order(session, new, lines, po_number=None)
    return OrderPartsResult(
        purchase_order_id=order.id, po_number=order.po_number, reserved=plan.reserve
    )


async def reserve_outstanding(
    uow: UnitOfWork,
    *,
    shop_id: UUID,
    booking_id: UUID,
    actor_user_id: UUID,
    now: datetime,
) -> tuple[PartQty, ...]:
    """T14: reserve every outstanding quantity, all or nothing (409 `INSUFFICIENT_STOCK`, INV-10).

    Zero rows pass trivially (D31); works from `PARTS_ORDERED` too (D43).
    """
    session = uow.session
    rows = await _booking_rows(session, shop_id=shop_id, booking_id=booking_id)
    parts = await PartRepository(session).lock(shop_id=shop_id, part_ids=rows.keys())
    plan = plan_full_reservation([_line(row) for row in rows.values()], _balances(parts))
    if plan.short:
        missing = ", ".join(
            f"{parts[item.part_id].sku} {parts[item.part_id].name} (short {item.qty})"
            for item in plan.short
        )
        raise InsufficientStock(f"Not enough stock to reserve: {missing}.")
    ledger = _Ledger(shop_id=shop_id, actor_user_id=actor_user_id, now=now, booking_id=booking_id)
    ledger.reserve(session, rows, parts, plan.reserve)
    await session.flush()
    return plan.reserve


async def reserve_received_for_booking(  # noqa: PLR0913 - the spec'd signature (modules/inventory.md)
    uow: UnitOfWork,
    *,
    shop_id: UUID,
    booking_id: UUID,
    purchase_order_id: UUID,
    received: Sequence[PartQty],
    actor_user_id: UUID,
    now: datetime,
) -> ReceiptReservation:
    """T15, called by the bookings receipt handler while the booking is `PARTS_ORDERED`.

    The caller guarantees that status (inventory cannot read bookings, D86). For each received
    part with a booking part: `RESERVE min(received, outstanding)` carrying the PO id; the excess
    stays general stock. The received parts are already locked by the receipt (re-locking them is
    a no-op for this transaction). Returns what was reserved and whether every booking part is now
    fully reserved.
    """
    session = uow.session
    rows = await _booking_rows(session, shop_id=shop_id, booking_id=booking_id)
    part_ids = {item.part_id for item in received if item.qty > 0} & rows.keys()
    parts = await PartRepository(session).lock(shop_id=shop_id, part_ids=part_ids)
    lines = [_line(row) for part_id, row in rows.items() if part_id in parts]
    reserve = plan_receipt_reservation(lines, _balances(parts), received)
    ledger = _Ledger(
        shop_id=shop_id,
        actor_user_id=actor_user_id,
        now=now,
        booking_id=booking_id,
        purchase_order_id=purchase_order_id,
    )
    ledger.reserve(session, rows, parts, reserve)
    await session.flush()
    return ReceiptReservation(
        reserved=reserve, all_reserved=all_fully_reserved(_line(row) for row in rows.values())
    )


async def consume_reservations(
    uow: UnitOfWork,
    *,
    shop_id: UUID,
    booking_id: UUID,
    actor_user_id: UUID,
    now: datetime,
) -> tuple[PartQty, ...]:
    """T16 allocate: one `CONSUME` of `required_qty` per row (on hand and reserved both drop).

    Any row not fully reserved → 409 `INSUFFICIENT_STOCK` (INV-12). Zero rows pass (D31).
    """
    session = uow.session
    rows = await _booking_rows(session, shop_id=shop_id, booking_id=booking_id)
    parts = await PartRepository(session).lock(shop_id=shop_id, part_ids=rows.keys())
    consumed = plan_consumption([_line(row) for row in rows.values()], _balances(parts))
    ledger = _Ledger(shop_id=shop_id, actor_user_id=actor_user_id, now=now, booking_id=booking_id)
    for item in consumed:
        ledger.write(session, parts[item.part_id], StockMovementType.CONSUME, item.qty)
        row = rows[item.part_id]
        row.consumed_qty = row.required_qty
        row.reserved_qty = 0
        touch(row, now)
    await session.flush()
    return consumed


async def release_reservations(
    uow: UnitOfWork,
    *,
    shop_id: UUID,
    booking_id: UUID,
    actor_user_id: UUID,
    now: datetime,
) -> tuple[PartQty, ...]:
    """T22 cancel: one `RELEASE` per reserved row. Linked POs stay open; their later receipts
    arrive as general stock (D24, INV-09). The actor may be the customer."""
    session = uow.session
    all_rows = await _booking_rows(session, shop_id=shop_id, booking_id=booking_id)
    rows = {part_id: row for part_id, row in all_rows.items() if row.reserved_qty > 0}
    parts = await PartRepository(session).lock(shop_id=shop_id, part_ids=rows.keys())
    released = plan_release([_line(row) for row in rows.values()])
    ledger = _Ledger(shop_id=shop_id, actor_user_id=actor_user_id, now=now, booking_id=booking_id)
    for item in released:
        ledger.write(session, parts[item.part_id], StockMovementType.RELEASE, item.qty)
        row = rows[item.part_id]
        row.reserved_qty -= item.qty
        touch(row, now)
    await session.flush()
    return released


# --- Reads for other modules --------------------------------------------------------------------


async def get_parts_for_estimate(
    session: AsyncSession,
    *,
    shop_id: UUID,
    part_ids: Collection[UUID],
    include_stock: bool = True,
) -> dict[UUID, PartStockRef]:
    """Estimates (D40): parts with live stock; unknown or other-shop ids are absent.

    Inactive parts are included (the caller decides); `include_stock=False` nulls the stock
    fields for QC callers (spec 04 §B).
    """
    parts = await PartRepository(session).get_many(shop_id=shop_id, part_ids=set(part_ids))
    return {
        part_id: _part_stock_ref(part, include_stock=include_stock)
        for part_id, part in parts.items()
    }


async def get_booking_parts(
    session: AsyncSession, *, shop_id: UUID, booking_id: UUID
) -> BookingPartsRead:
    """Bookings' `GET …/bookings/{booking_id}/parts` (after D21 and the QC 403)."""
    rows = await BookingPartRepository(session).list_for_booking(
        shop_id=shop_id, booking_id=booking_id
    )
    parts = await PartRepository(session).get_many(
        shop_id=shop_id, part_ids={row.part_id for row in rows}
    )
    balances = _balances(parts)
    lines = [_line(row) for row in rows]
    items = sorted(
        (
            BookingPartRead(
                part=_part_stock_ref(parts[line.part_id], include_stock=True),
                required_qty=line.required_qty,
                reserved_qty=line.reserved_qty,
                consumed_qty=line.consumed_qty,
                outstanding_qty=line.outstanding,
                shortage_qty=shortage(line.outstanding, balances[line.part_id].available),
            )
            for line in lines
        ),
        key=lambda item: (item.part.sku, item.part.id),
    )
    counts = count_available(lines, balances)
    orders = PurchaseOrderRepository(session)
    linked = await orders.list_for_bookings(shop_id=shop_id, booking_ids=[booking_id])
    totals = await orders.item_totals(shop_id=shop_id, po_ids=[order.id for order in linked])
    return BookingPartsRead(
        booking_id=booking_id,
        all_available=counts.all_available,
        required_count=counts.required_count,
        available_count=counts.available_count,
        items=items,
        purchase_orders=[
            PurchaseOrderRef(
                id=order.id,
                po_number=order.po_number,
                status=order.status,
                ordered_qty_total=totals.get(order.id, _NO_ITEMS).ordered_qty,
                received_qty_total=totals.get(order.id, _NO_ITEMS).received_qty,
            )
            for order in linked
        ],
    )


async def get_booking_parts_summary(
    session: AsyncSession, *, shop_id: UUID, booking_ids: Collection[UUID]
) -> dict[UUID, PartsSummary]:
    """`parts_summary` for many bookings in two queries (API-11); one entry per id, zero rows →
    `{0, 0, 0, true}` (D31)."""
    ids = set(booking_ids)
    rows = await BookingPartRepository(session).list_for_bookings(shop_id=shop_id, booking_ids=ids)
    parts = await PartRepository(session).get_many(
        shop_id=shop_id, part_ids={row.part_id for row in rows}
    )
    balances = _balances(parts)
    lines_by_booking: dict[UUID, list[BookingPartLine]] = {booking_id: [] for booking_id in ids}
    for row in rows:
        lines_by_booking[row.booking_id].append(_line(row))
    summaries: dict[UUID, PartsSummary] = {}
    for booking_id, lines in lines_by_booking.items():
        counts = count_available(lines, balances)
        summaries[booking_id] = PartsSummary(
            required_count=counts.required_count,
            available_count=counts.available_count,
            shortage_count=counts.shortage_count,
            all_available=counts.all_available,
        )
    return summaries


async def find_purchase_order_id(
    session: AsyncSession, *, shop_id: UUID, po_number: str
) -> UUID | None:
    """The id of this shop's PO numbered `po_number`, or `None` (another shop's number included).

    For the seed (spec 11): it keys its general POs by `(shop_id, po_number)` (`PO-SEED01`,
    `PO-SEED02`) to stay idempotent, and goes through services only (D51).
    """
    return await PurchaseOrderRepository(session).find_id_by_po_number(
        shop_id=shop_id, po_number=po_number
    )


async def get_stock_summary(session: AsyncSession, *, shop_id: UUID) -> StockSummary:
    """Reporting's inventory block over **active** parts (`modules/reporting.md`)."""
    parts = PartRepository(session)
    totals = await parts.stock_totals(shop_id=shop_id)
    low = await parts.low_stock(shop_id=shop_id, limit=LOW_STOCK_LIMIT)
    return StockSummary(
        parts_count=totals.parts_count,
        low_stock_count=totals.low_stock_count,
        out_of_stock_count=totals.out_of_stock_count,
        stock_value=totals.stock_value.quantize(_CENTS),
        open_purchase_orders=await PurchaseOrderRepository(session).count_open(shop_id=shop_id),
        low_stock=await _part_reads(session, shop_id, low),
    )


async def count_low_stock(session: AsyncSession, *, shop_ids: Collection[UUID]) -> dict[UUID, int]:
    """P1, owner multi-shop summary: active `LOW` + `OUT` parts per shop (0 when none)."""
    ids = set(shop_ids)
    counts = await PartRepository(session).count_low_stock(shop_ids=ids)
    return {shop_id: counts.get(shop_id, 0) for shop_id in ids}

"""Stock maths and stock plans (spec 02 §6, D42-D45, D82; `modules/inventory.md` "Domain rules").

Pure Python: no I/O, no clock, no framework. The service loads rows (under their row locks),
turns them into the small values below, asks a plan function what to write, and only then writes.
Every guard raises before anything is written, so a 409/422 never leaves a half-applied plan
(`modules/inventory.md` "Concurrency and transactions").

Derived quantities (never stored):

- available    = on_hand - reserved
- stock_state  = OUT when available = 0, else LOW when available <= reorder_level, else OK (D45)
- outstanding  = required_qty - reserved_qty - consumed_qty           (per booking part)
- shortage     = max(0, outstanding - available)
"""

from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from app.core.errors import (
    ConcurrentUpdate,
    Conflict,
    FieldError,
    InsufficientStock,
    ValidationFailed,
)
from app.shared.enums import PurchaseOrderStatus, StockMovementType, StockState

MAX_ON_HAND = 2_147_483_647
"""`parts.on_hand` is a PostgreSQL `integer`: a write above this would be a database error."""

OPEN_PURCHASE_ORDER_STATUSES: frozenset[PurchaseOrderStatus] = frozenset(
    {PurchaseOrderStatus.ORDERED, PurchaseOrderStatus.PARTIALLY_RECEIVED}
)


# --- Values -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PartQty:
    """A quantity of one part: requirements, reservations, receipts, consumption, releases."""

    part_id: UUID
    qty: int

    def as_json(self) -> dict[str, str | int]:
        """The `{part_id, qty}` shape of booking-event metadata (spec 08 "metadata examples")."""
        return {"part_id": str(self.part_id), "qty": self.qty}


@dataclass(frozen=True, slots=True)
class PartBalance:
    """A part's cached ledger balances, read under the part's row lock."""

    part_id: UUID
    on_hand: int
    reserved: int

    @property
    def available(self) -> int:
        return available(self.on_hand, self.reserved)


@dataclass(frozen=True, slots=True)
class BookingPartLine:
    """One `booking_parts` row: what a booking needs of one part and what it holds."""

    part_id: UUID
    required_qty: int
    reserved_qty: int
    consumed_qty: int

    @property
    def outstanding(self) -> int:
        return outstanding(self.required_qty, self.reserved_qty, self.consumed_qty)

    @property
    def fully_reserved(self) -> bool:
        """`reserved_qty + consumed_qty = required_qty` (spec 08 T15)."""
        return self.outstanding == 0


@dataclass(frozen=True, slots=True)
class OrderPartsResult:
    """What `order_missing_parts` did, for the `ORDER_PARTS` event metadata (spec 08)."""

    purchase_order_id: UUID
    po_number: str
    reserved: tuple[PartQty, ...]


@dataclass(frozen=True, slots=True)
class ReceiptReservation:
    """What a receipt reserved for its booking, and whether every booking part is now fully
    reserved (bookings then applies `RECEIVE_PARTS`, else publishes `BookingPartsChanged`)."""

    reserved: tuple[PartQty, ...]
    all_reserved: bool


# --- Quantities ---------------------------------------------------------------------------------


def available(on_hand: int, reserved: int) -> int:
    """`on_hand - reserved` (glossary §1); never negative while the CHECKs hold."""
    return on_hand - reserved


def stock_state(available_qty: int, reorder_level: int) -> StockState:
    """D45: OUT when nothing is available (OUT wins over LOW), LOW at or below the reorder level."""
    if available_qty <= 0:
        return StockState.OUT
    if available_qty <= reorder_level:
        return StockState.LOW
    return StockState.OK


def outstanding(required_qty: int, reserved_qty: int, consumed_qty: int) -> int:
    """What a booking part still needs reserved: `required - reserved - consumed`."""
    return required_qty - reserved_qty - consumed_qty


def shortage(outstanding_qty: int, available_qty: int) -> int:
    """`max(0, outstanding - available)`: brief §7.6 "required parts compared to stock"."""
    return max(0, outstanding_qty - available_qty)


def is_line_available(line: BookingPartLine, balance: PartBalance) -> bool:
    """A booking part counts as available when nothing is outstanding or stock covers it now."""
    return line.outstanding == 0 or line.outstanding <= balance.available


@dataclass(frozen=True, slots=True)
class PartsCounts:
    """`PartsSummary` / `BookingPartsRead` counts over a booking's `booking_parts` rows."""

    required_count: int
    available_count: int

    @property
    def shortage_count(self) -> int:
        return self.required_count - self.available_count

    @property
    def all_available(self) -> bool:
        """True for zero rows: a labour-only job passes the parts steps (D31)."""
        return self.available_count == self.required_count


def count_available(
    lines: Sequence[BookingPartLine], balances: Mapping[UUID, PartBalance]
) -> PartsCounts:
    available_count = sum(1 for line in lines if is_line_available(line, balances[line.part_id]))
    return PartsCounts(required_count=len(lines), available_count=available_count)


def sum_by_part(quantities: Iterable[PartQty]) -> tuple[PartQty, ...]:
    """Merge quantities per part (T12 sums the approved estimate's lines per part), by part id."""
    totals: dict[UUID, int] = {}
    for item in quantities:
        totals[item.part_id] = totals.get(item.part_id, 0) + item.qty
    return tuple(PartQty(part_id, qty) for part_id, qty in sorted(totals.items()))


def _by_part(quantities: Iterable[PartQty]) -> tuple[PartQty, ...]:
    """Positive quantities only, ordered by part id (deterministic metadata and lock order)."""
    return tuple(sorted((item for item in quantities if item.qty > 0), key=lambda i: i.part_id))


def field_error(field: str, code: str, message: str) -> FieldError:
    return FieldError(field=field, message=message, code=code)


def duplicate_positions[T: Hashable](values: Sequence[T]) -> list[int]:
    """Indexes of every repeated value after its first occurrence (field code `duplicate`)."""
    seen: set[T] = set()
    repeated: list[int] = []
    for index, value in enumerate(values):
        if value in seen:
            repeated.append(index)
        seen.add(value)
    return repeated


# --- T13 order-parts ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrderPlan:
    """T13: reserve what is available now; what is still outstanding is the shortage."""

    reserve: tuple[PartQty, ...]
    shortages: tuple[PartQty, ...]


def plan_order(lines: Sequence[BookingPartLine], balances: Mapping[UUID, PartBalance]) -> OrderPlan:
    reserve: list[PartQty] = []
    shortages: list[PartQty] = []
    for line in lines:
        reservable = min(balances[line.part_id].available, line.outstanding)
        reserve.append(PartQty(line.part_id, reservable))
        shortages.append(PartQty(line.part_id, line.outstanding - reservable))
    return OrderPlan(reserve=_by_part(reserve), shortages=_by_part(shortages))


def order_quantities(
    shortages: Sequence[PartQty], items: Sequence[PartQty] | None
) -> tuple[PartQty, ...]:
    """The PO lines of T13 (spec 03 §5.2 `order-parts`).

    `items` omitted → exactly the shortages. `items` given → every short part must be listed
    (`items` `missing_shortage`), only short parts may be listed (`items.N.part_id` `not_short`),
    each part once (`items.N.part_id` `duplicate`) with `quantity >= shortage`
    (`items.N.quantity` `below_shortage`). All violations are reported together (INV-27).
    """
    if items is None:
        return _by_part(shortages)
    short = {item.part_id: item.qty for item in shortages}
    errors: list[FieldError] = []
    repeated = set(duplicate_positions([item.part_id for item in items]))
    for index, item in enumerate(items):
        if index in repeated:
            errors.append(
                field_error(
                    f"items.{index}.part_id", "duplicate", "Each part can be ordered only once."
                )
            )
        elif item.part_id not in short:
            errors.append(
                field_error(
                    f"items.{index}.part_id",
                    "not_short",
                    "This part is not short for this booking; order only the missing parts.",
                )
            )
        elif item.qty < short[item.part_id]:
            errors.append(
                field_error(
                    f"items.{index}.quantity",
                    "below_shortage",
                    f"Order at least {short[item.part_id]} to cover the shortage.",
                )
            )
    listed = {item.part_id for item in items}
    if any(part_id not in listed for part_id in short):
        errors.append(
            field_error(
                "items", "missing_shortage", "Every missing part must be on the purchase order."
            )
        )
    if errors:
        raise ValidationFailed(errors=errors)
    return _by_part(items)


# --- T14 mark-parts-ready, T15 receipt reservation, T16 allocate, T22 release ---------------------


@dataclass(frozen=True, slots=True)
class ReservationPlan:
    """T14: reserve every outstanding quantity, unless some part cannot be covered (`short`)."""

    reserve: tuple[PartQty, ...]
    short: tuple[PartQty, ...]


def plan_full_reservation(
    lines: Sequence[BookingPartLine], balances: Mapping[UUID, PartBalance]
) -> ReservationPlan:
    reserve = [PartQty(line.part_id, line.outstanding) for line in lines]
    short = [
        PartQty(line.part_id, shortage(line.outstanding, balances[line.part_id].available))
        for line in lines
    ]
    return ReservationPlan(reserve=_by_part(reserve), short=_by_part(short))


def plan_receipt_reservation(
    lines: Sequence[BookingPartLine],
    balances: Mapping[UUID, PartBalance],
    received: Iterable[PartQty],
) -> tuple[PartQty, ...]:
    """T15: per received part with a booking part, reserve `min(received, outstanding)`.

    The excess stays general stock. Capped by what is available, which the receipt itself
    just raised by at least the received quantity.
    """
    by_part = {line.part_id: line for line in lines}
    reserve: list[PartQty] = []
    for item in sum_by_part(received):
        line = by_part.get(item.part_id)
        if line is None:
            continue
        reserve.append(
            PartQty(
                item.part_id,
                min(item.qty, line.outstanding, balances[item.part_id].available),
            )
        )
    return _by_part(reserve)


def plan_consumption(
    lines: Sequence[BookingPartLine], balances: Mapping[UUID, PartBalance]
) -> tuple[PartQty, ...]:
    """T16: consume `required_qty` of every row, which must be fully reserved (INV-12)."""
    incomplete = [line for line in lines if line.reserved_qty != line.required_qty]
    if incomplete:
        raise InsufficientStock(
            "Some parts of this job are not fully reserved yet; reserve them before allocating."
        )
    for line in lines:
        balance = balances[line.part_id]
        if balance.reserved < line.required_qty or balance.on_hand < line.required_qty:
            raise InsufficientStock("The reserved stock for this job is no longer on hand.")
    return _by_part(PartQty(line.part_id, line.required_qty) for line in lines)


def plan_release(lines: Sequence[BookingPartLine]) -> tuple[PartQty, ...]:
    """T22: release every reservation of the booking (cancellation)."""
    return _by_part(PartQty(line.part_id, line.reserved_qty) for line in lines)


def all_fully_reserved(lines: Iterable[BookingPartLine]) -> bool:
    return all(line.fully_reserved for line in lines)


# --- Adjustments (D82) --------------------------------------------------------------------------


def adjusted_on_hand(*, on_hand: int, reserved: int, quantity_delta: int) -> int:
    """The new `on_hand` of an `ADJUST`, or 409 `INSUFFICIENT_STOCK` below `reserved` / below 0."""
    new_on_hand = on_hand + quantity_delta
    if new_on_hand < reserved:
        lowest = reserved - on_hand
        raise InsufficientStock(
            f"This adjustment would leave {new_on_hand} on hand, but {reserved} are reserved for"
            f" jobs (on hand {on_hand}, reserved {reserved}); the lowest allowed change is"
            f" {lowest}."
        )
    if new_on_hand > MAX_ON_HAND:
        raise ValidationFailed(
            errors=[
                field_error(
                    "quantity_delta",
                    "value_error",
                    f"Stock on hand cannot exceed {MAX_ON_HAND}.",
                )
            ]
        )
    return new_on_hand


# --- Purchase orders (D43) ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrderedItem:
    """A purchase-order item as a receipt sees it (read under the PO row lock)."""

    item_id: UUID
    part_id: UUID
    ordered_qty: int
    received_qty: int

    @property
    def outstanding(self) -> int:
        return self.ordered_qty - self.received_qty


@dataclass(frozen=True, slots=True)
class ReceiptLine:
    """One line of a receipt request."""

    item_id: UUID
    quantity: int
    expected_received_qty: int | None = None


@dataclass(frozen=True, slots=True)
class ReceiptPart:
    """What a validated receipt does to one item."""

    item_id: UUID
    part_id: UUID
    quantity: int


def purchase_order_status(quantities: Iterable[tuple[int, int]]) -> PurchaseOrderStatus:
    """Spec 02 §6 from `(ordered_qty, received_qty)` per item: all complete → RECEIVED, nothing
    received → ORDERED, otherwise PARTIALLY_RECEIVED."""
    pairs = list(quantities)
    if pairs and all(received >= ordered for ordered, received in pairs):
        return PurchaseOrderStatus.RECEIVED
    if all(received == 0 for _, received in pairs):
        return PurchaseOrderStatus.ORDERED
    return PurchaseOrderStatus.PARTIALLY_RECEIVED


def plan_receipt(
    status: PurchaseOrderStatus,
    items: Sequence[OrderedItem],
    lines: Sequence[ReceiptLine],
) -> tuple[ReceiptPart, ...]:
    """Validate a receipt in the order of `modules/inventory.md` step 4, then plan it.

    1. PO already RECEIVED → 409 `CONFLICT`;
    2. an `item_id` not on this PO → 422 `items.N.item_id` `invalid_reference`;
    3. `expected_received_qty` given and different from the stored `received_qty` → 409
       `CONCURRENT_UPDATE` (a duplicated or concurrent receipt, INV-07, INV-28);
    4. `quantity` above the item's outstanding → 422 `items.N.quantity` `exceeds_outstanding`;
    5. every quantity 0 → 422 `items` `nothing_to_receive`.
    """
    if status == PurchaseOrderStatus.RECEIVED:
        raise Conflict("This purchase order has already been received in full.")
    by_id = {item.item_id: item for item in items}
    unknown = [
        field_error(
            f"items.{index}.item_id",
            "invalid_reference",
            "This item is not part of this purchase order.",
        )
        for index, line in enumerate(lines)
        if line.item_id not in by_id
    ]
    if unknown:
        raise ValidationFailed(errors=unknown)
    for line in lines:
        item = by_id[line.item_id]
        if line.expected_received_qty is not None and line.expected_received_qty != (
            item.received_qty
        ):
            raise ConcurrentUpdate(
                f"This purchase order changed meanwhile: {item.received_qty} of"
                f" {item.ordered_qty} already received, not {line.expected_received_qty}."
                " Reload it and try again."
            )
    too_many = [
        field_error(
            f"items.{index}.quantity",
            "exceeds_outstanding",
            f"Only {by_id[line.item_id].outstanding} still to receive for this item.",
        )
        for index, line in enumerate(lines)
        if line.quantity > by_id[line.item_id].outstanding
    ]
    if too_many:
        raise ValidationFailed(errors=too_many)
    if all(line.quantity == 0 for line in lines):
        raise ValidationFailed(
            errors=[field_error("items", "nothing_to_receive", "Enter a quantity to receive.")]
        )
    return tuple(
        ReceiptPart(
            item_id=line.item_id, part_id=by_id[line.item_id].part_id, quantity=line.quantity
        )
        for line in lines
        if line.quantity > 0
    )


def receipt_on_hand_errors(
    parts: Sequence[ReceiptPart],
    positions: Mapping[UUID, int],
    balances: Mapping[UUID, PartBalance],
) -> list[FieldError]:
    """`items.N.quantity` errors for receipts that would push `on_hand` past `MAX_ON_HAND`."""
    return [
        field_error(
            f"items.{positions[part.item_id]}.quantity",
            "value_error",
            f"Stock on hand cannot exceed {MAX_ON_HAND}.",
        )
        for part in parts
        if balances[part.part_id].on_hand + part.quantity > MAX_ON_HAND
    ]


# --- The ledger (D42, D79; DI-1...DI-3, INV-26) -------------------------------------------------

_DELTA_SIGNS: Mapping[StockMovementType, tuple[int, int]] = {
    StockMovementType.RECEIVE: (1, 0),
    StockMovementType.RESERVE: (0, 1),
    StockMovementType.RELEASE: (0, -1),
    StockMovementType.CONSUME: (-1, -1),
}


def movement_deltas(movement_type: StockMovementType, quantity: int) -> tuple[int, int]:
    """Signed `(on_hand_delta, reserved_delta)` of a movement (`ck_stock_movements_deltas`).

    `ADJUST` carries its own signed delta (`on_hand_delta = d`, `quantity = |d|`), so it is not
    derived from a quantity here.
    """
    if quantity <= 0:
        msg = "a stock movement quantity is always positive"
        raise ValueError(msg)
    if movement_type not in _DELTA_SIGNS:
        msg = f"{movement_type} has a signed delta of its own"
        raise ValueError(msg)
    on_hand_sign, reserved_sign = _DELTA_SIGNS[movement_type]
    return on_hand_sign * quantity, reserved_sign * quantity


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One `stock_movements` row, as the order-free ledger checks see it."""

    part_id: UUID
    movement_type: StockMovementType
    quantity: int
    on_hand_delta: int
    reserved_delta: int
    booking_id: UUID | None = None


def ledger_balances(entries: Iterable[LedgerEntry]) -> dict[UUID, tuple[int, int]]:
    """DI-1: per part `(Σ on_hand_delta, Σ reserved_delta)` — sums, so row order never matters."""
    totals: dict[UUID, tuple[int, int]] = {}
    for entry in entries:
        on_hand, reserved = totals.get(entry.part_id, (0, 0))
        totals[entry.part_id] = (on_hand + entry.on_hand_delta, reserved + entry.reserved_delta)
    return totals


_RESERVED_SIGN: Mapping[StockMovementType, int] = {
    StockMovementType.RESERVE: 1,
    StockMovementType.RELEASE: -1,
    StockMovementType.CONSUME: -1,
}


def booking_ledger(entries: Iterable[LedgerEntry]) -> dict[tuple[UUID, UUID], tuple[int, int]]:
    """DI-3: per (booking, part) `(Σ RESERVE - Σ RELEASE - Σ CONSUME, Σ CONSUME)`."""
    totals: dict[tuple[UUID, UUID], tuple[int, int]] = {}
    for entry in entries:
        if entry.booking_id is None or entry.movement_type not in _RESERVED_SIGN:
            continue
        key = (entry.booking_id, entry.part_id)
        reserved, consumed = totals.get(key, (0, 0))
        reserved += _RESERVED_SIGN[entry.movement_type] * entry.quantity
        if entry.movement_type == StockMovementType.CONSUME:
            consumed += entry.quantity
        totals[key] = (reserved, consumed)
    return totals


def running_balances(entries: Iterable[LedgerEntry]) -> list[tuple[int, int]]:
    """A part's `(on_hand, reserved)` after each entry, in the order given (`created_at, seq`)."""
    on_hand = reserved = 0
    balances: list[tuple[int, int]] = []
    for entry in entries:
        on_hand += entry.on_hand_delta
        reserved += entry.reserved_delta
        balances.append((on_hand, reserved))
    return balances

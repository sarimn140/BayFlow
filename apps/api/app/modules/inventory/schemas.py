"""Request and response schemas of the inventory module (spec 03 §3.4, §3.5, §4.10, §5.3).

Requests forbid unknown fields (`extra="forbid"`, mass-assignment defence, SEC-17): the catalogue
schemas have no stock fields, so a part always starts at `on_hand = reserved = 0` (D44), and a
general purchase order has no `booking_id` (booking-linked POs come only from `order-parts`, D43).
Stock quantities are JSON integers (glossary §9), validated strictly; money is `Money` (whole
rupees, D41); timestamps are `Timestamp` (UTC with `Z`).
"""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.modules.identity.schemas import UserRef
from app.shared.enums import BookingStatus, PurchaseOrderStatus, StockMovementType, StockState
from app.shared.money import Money
from app.shared.timestamps import Timestamp

SKU_PATTERN = r"^[A-Z0-9][A-Z0-9._/-]{0,39}$"
MAX_REORDER_LEVEL = 100_000
MAX_ADJUSTMENT = 100_000
MAX_ORDER_QUANTITY = 10_000
MAX_PURCHASE_ORDER_ITEMS = 50
MAX_SEARCH_LENGTH = 100
MAX_REASON_LENGTH = 500  # stock_movements.note varchar(500)

PartSort = Literal["sku", "-sku", "name", "-name", "available", "-available"]
"""`GET …/parts?sort=`: ascending, or descending with `-` (spec 03 §4.10). Default `sku`."""


def _normalise_sku(value: object) -> object:
    """SKUs are trimmed and upper-cased before the format check (`modules/inventory.md`)."""
    return value.strip().upper() if isinstance(value, str) else value


def _not_null(value: object) -> object:
    if value is None:
        msg = "This field cannot be null."
        raise ValueError(msg)
    return value


def _not_zero(value: int) -> int:
    if value == 0:
        msg = "The quantity change must not be zero."
        raise ValueError(msg)
    return value


Sku = Annotated[
    str,
    StringConstraints(min_length=1, max_length=40, pattern=SKU_PATTERN),
    BeforeValidator(_normalise_sku),
    Field(examples=["IGN-COIL-01"]),
]
PartName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
SupplierName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
Reason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_REASON_LENGTH)
]
ReorderLevel = Annotated[int, Field(strict=True, ge=0, le=MAX_REORDER_LEVEL)]
OrderQuantity = Annotated[int, Field(strict=True, ge=1, le=MAX_ORDER_QUANTITY)]
ReceiveQuantity = Annotated[int, Field(strict=True, ge=0, le=MAX_ORDER_QUANTITY)]
QuantityDelta = Annotated[
    int,
    Field(strict=True, ge=-MAX_ADJUSTMENT, le=MAX_ADJUSTMENT, examples=[10]),
    AfterValidator(_not_zero),
]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- References ---------------------------------------------------------------------------------


class BookingRef(BaseModel):
    """A booking as a purchase order shows it (spec 03 §3.1; data from the D86 read port)."""

    id: UUID
    reference: str
    status: BookingStatus
    version: int


class PartRef(BaseModel):
    id: UUID
    sku: str
    name: str


class PartStockRef(BaseModel):
    """A part with live stock (D40); the stock fields are null for QC callers (spec 04 §B)."""

    id: UUID
    sku: str
    name: str
    unit_cost: Money
    is_active: bool
    on_hand: int | None
    reserved: int | None
    available: int | None
    reorder_level: int | None
    stock_state: StockState | None


class PurchaseOrderRef(BaseModel):
    id: UUID
    po_number: str
    status: PurchaseOrderStatus
    ordered_qty_total: int
    received_qty_total: int


# --- Parts catalogue (D44, D45) -----------------------------------------------------------------


class PartCreate(_Request):
    """`POST …/parts`. No stock field: a new part starts at `on_hand = 0` (D44)."""

    sku: Sku
    name: PartName
    unit_cost: Money
    reorder_level: ReorderLevel = 0
    is_active: bool = True


class PartUpdate(_Request):
    """`PATCH …/parts/{part_id}`: at least one field; omitted = unchanged. No stock fields."""

    sku: Annotated[Sku | None, AfterValidator(_not_null)] = None
    name: Annotated[PartName | None, AfterValidator(_not_null)] = None
    unit_cost: Annotated[Money | None, AfterValidator(_not_null)] = None
    reorder_level: Annotated[ReorderLevel | None, AfterValidator(_not_null)] = None
    is_active: Annotated[bool | None, AfterValidator(_not_null)] = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "PartUpdate":
        if not self.model_fields_set:
            msg = "Send at least one field to change."
            raise ValueError(msg)
        return self


class PartRead(BaseModel):
    """A catalogue part with its computed stock figures (spec 03 §3.5)."""

    id: UUID
    sku: str
    name: str
    unit_cost: Money
    is_active: bool
    on_hand: int
    reserved: int
    available: int
    reorder_level: int
    stock_state: StockState
    on_order: int = Field(description="Outstanding quantity on open purchase orders.")
    created_at: Timestamp
    updated_at: Timestamp


# --- The ledger and adjustments (D42, D79, D82) -------------------------------------------------


class StockAdjustmentCreate(_Request):
    """`POST …/parts/{part_id}/adjustments`: opening stock and count corrections (D82)."""

    quantity_delta: QuantityDelta
    reason: Reason


class StockMovementBookingRef(BaseModel):
    id: UUID
    reference: str


class StockMovementPurchaseOrderRef(BaseModel):
    id: UUID
    po_number: str


class StockMovementRead(BaseModel):
    """One ledger row with signed deltas (D42)."""

    id: UUID
    part_id: UUID
    movement_type: StockMovementType
    quantity: int
    on_hand_delta: int
    reserved_delta: int
    booking: StockMovementBookingRef | None
    purchase_order: StockMovementPurchaseOrderRef | None
    actor: UserRef
    note: str | None
    created_at: Timestamp


class StockAdjustmentRead(BaseModel):
    part: PartRead
    movement: StockMovementRead


# --- Booking parts (spec 08 T12-T16, T22) -------------------------------------------------------


class BookingPartRead(BaseModel):
    part: PartStockRef
    required_qty: int
    reserved_qty: int
    consumed_qty: int
    outstanding_qty: int
    shortage_qty: int


class BookingPartsRead(BaseModel):
    """Required vs reserved vs available for one booking, plus its linked POs (brief §7.6)."""

    booking_id: UUID
    all_available: bool
    required_count: int
    available_count: int
    items: list[BookingPartRead]
    purchase_orders: list[PurchaseOrderRef]


class PartsSummary(BaseModel):
    """`parts_summary` of booking lists and details; `{0, 0, 0, true}` for zero rows (D31)."""

    required_count: int
    available_count: int
    shortage_count: int
    all_available: bool


# --- Purchase orders (D43) ----------------------------------------------------------------------


class PurchaseOrderItemCreate(_Request):
    part_id: UUID
    quantity: OrderQuantity
    unit_cost: Money | None = None


class PurchaseOrderCreate(_Request):
    """`POST …/purchase-orders`: a general restock (no booking, D43)."""

    supplier_name: SupplierName | None = None
    items: Annotated[
        list[PurchaseOrderItemCreate], Field(min_length=1, max_length=MAX_PURCHASE_ORDER_ITEMS)
    ]


class PurchaseOrderReceiveItem(_Request):
    item_id: UUID
    quantity: ReceiveQuantity
    expected_received_qty: Annotated[int, Field(strict=True, ge=0)] | None = Field(
        default=None,
        description=(
            "The item's `received_qty` the client rendered; a mismatch is 409 CONCURRENT_UPDATE."
        ),
    )


class PurchaseOrderReceive(_Request):
    """`POST …/purchase-orders/{po_id}/receive` (spec 03 §5.3)."""

    items: Annotated[
        list[PurchaseOrderReceiveItem], Field(min_length=1, max_length=MAX_PURCHASE_ORDER_ITEMS)
    ]


class PurchaseOrderItemRead(BaseModel):
    id: UUID
    part: PartRef
    ordered_qty: int
    received_qty: int
    outstanding_qty: int
    unit_cost: Money
    line_cost: Money


class PurchaseOrderSummary(BaseModel):
    """A PO in lists; `booking` null = general restock (spec 03 §3.5)."""

    id: UUID
    po_number: str
    status: PurchaseOrderStatus
    supplier_name: str | None
    booking: BookingRef | None
    item_count: int
    ordered_qty_total: int
    received_qty_total: int
    total_cost: Money
    created_by: UserRef
    created_at: Timestamp
    received_at: Timestamp | None


class PurchaseOrderRead(PurchaseOrderSummary):
    items: list[PurchaseOrderItemRead]
    updated_at: Timestamp


class PurchaseOrderReceiveRead(BaseModel):
    """`receive_parts_applied` is true when this receipt moved the booking to `PARTS_READY`."""

    purchase_order: PurchaseOrderRead
    receive_parts_applied: bool


# --- Internal (reporting) -----------------------------------------------------------------------


class StockSummary(BaseModel):
    """The owner overview's inventory block (spec 03 §3.7; active parts only)."""

    model_config = ConfigDict(frozen=True)

    parts_count: int
    low_stock_count: int
    out_of_stock_count: int
    stock_value: Decimal
    open_purchase_orders: int
    low_stock: list[PartRead]


__all__ = [
    "MAX_ADJUSTMENT",
    "MAX_REASON_LENGTH",
    "MAX_SEARCH_LENGTH",
    "BookingPartRead",
    "BookingPartsRead",
    "BookingRef",
    "PartCreate",
    "PartRead",
    "PartRef",
    "PartSort",
    "PartStockRef",
    "PartUpdate",
    "PartsSummary",
    "PurchaseOrderCreate",
    "PurchaseOrderItemCreate",
    "PurchaseOrderItemRead",
    "PurchaseOrderRead",
    "PurchaseOrderReceive",
    "PurchaseOrderReceiveItem",
    "PurchaseOrderReceiveRead",
    "PurchaseOrderRef",
    "PurchaseOrderSummary",
    "StockAdjustmentCreate",
    "StockAdjustmentRead",
    "StockMovementBookingRef",
    "StockMovementPurchaseOrderRef",
    "StockMovementRead",
    "StockState",
    "StockSummary",
    "UserRef",
]

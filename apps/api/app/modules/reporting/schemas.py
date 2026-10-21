"""Response schemas of the reporting module (spec 03 §3.7; `modules/reporting.md`).

`OverviewRead` (P0, `GET /api/v1/shops/{shop_id}/overview`) and `OwnerSummaryRead` (P1,
`GET /api/v1/me/owner-summary`). Every nested object is a named class, so the OpenAPI components
and the generated TypeScript types keep stable names: `OverviewShop`, `OverviewStatusCount`,
`OverviewToday`, `OverviewTeamMember`, `OverviewInventory`, `OverviewSetup`, `OwnerShopRef` and
`OwnerShopSummary`; `low_stock` reuses inventory's `PartRead`. Both routes take no body and no
query parameters, so there are no request schemas.

`stock_value` is `MoneyTotal`: `Money`'s wire form (whole rupees as a decimal string with two
places, D41) without `Money`'s `numeric(12,2)` request bound. It sums on hand * unit cost over
every active part, which can exceed the 10 integer digits that one stored amount may hold, and
the overview must still answer.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, PlainSerializer

from app.modules.inventory.schemas import PartRead
from app.modules.reporting.domain.kpis import LOW_STOCK_PREVIEW_SIZE, STATUS_ORDER
from app.shared.enums import BookingStatus, MembershipRole
from app.shared.money import CENTS, format_money, is_whole_rupees


def _whole_rupees(value: Decimal) -> Decimal:
    if not is_whole_rupees(value):
        msg = "Amounts must be whole rupees (no paisa)."
        raise ValueError(msg)
    return value.quantize(CENTS)


MoneyTotal = Annotated[
    Decimal,
    Field(ge=0, examples=["286400.00"]),
    AfterValidator(_whole_rupees),
    PlainSerializer(format_money, return_type=str, when_used="json"),
]
"""A non-negative whole-rupee total of any size; JSON output is a 2-decimal string like `Money`."""


# --- Overview (P0) -------------------------------------------------------------------------------


class OverviewShop(BaseModel):
    """The shop the overview describes."""

    id: uuid.UUID
    slug: str
    name: str
    city: str
    is_listed: bool


class OverviewStatusCount(BaseModel):
    """How many of the shop's bookings are in one status now."""

    status: BookingStatus
    count: int


class OverviewToday(BaseModel):
    """The shop-local day of the request, in the shop's time zone (D38)."""

    date: dt.date = Field(description="The shop-local date (YYYY-MM-DD).")
    bookings: int = Field(description="Bookings not cancelled whose slot starts today.")
    ready_for_pickup: int = Field(
        description="Bookings currently ready for pick-up, whatever their date."
    )
    completed: int = Field(description="Bookings completed today.")


class OverviewTeamMember(BaseModel):
    """One membership of the shop (the `OWNER` row and inactive members included)."""

    membership_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    role: MembershipRole
    is_active: bool
    open_jobs: int = Field(
        description=(
            "Bookings not ready for pick-up, completed or cancelled where the member is the "
            "technician, the parts person or the current QC picker."
        )
    )


class OverviewInventory(BaseModel):
    """Stock figures over the shop's active parts (D45)."""

    parts_count: int = Field(description="Active parts.")
    low_stock_count: int = Field(description="Active parts that are LOW or OUT.")
    out_of_stock_count: int = Field(description="Active parts with nothing available.")
    stock_value: MoneyTotal = Field(description="Sum of on hand * unit cost over active parts.")
    open_purchase_orders: int = Field(description="Purchase orders ORDERED or PARTIALLY_RECEIVED.")


class OverviewSetup(BaseModel):
    """The setup checklist of a new shop (O-01)."""

    has_services: bool = Field(description="At least one active service.")
    has_team: bool = Field(description="At least one active non-owner member.")
    has_parts: bool = Field(description="At least one active part.")
    is_listed: bool = Field(description="The shop is listed in the public directory.")


class OverviewRead(BaseModel):
    """`GET /api/v1/shops/{shop_id}/overview`: brief §7.4 Owner — bookings by status, team list,
    inventory summary — plus today's figures and the setup checklist."""

    shop: OverviewShop
    status_counts: list[OverviewStatusCount] = Field(
        min_length=len(STATUS_ORDER),
        max_length=len(STATUS_ORDER),
        description="Every booking status in glossary §3 order, zeros included.",
    )
    today: OverviewToday
    team: list[OverviewTeamMember] = Field(
        description="Every membership, ordered by role (glossary §2.1), then name."
    )
    inventory: OverviewInventory
    low_stock: list[PartRead] = Field(
        max_length=LOW_STOCK_PREVIEW_SIZE,
        description="Up to 5 active LOW or OUT parts: OUT first, then by available, then by SKU.",
    )
    setup: OverviewSetup


# --- Owner multi-shop summary (P1) ---------------------------------------------------------------


class OwnerShopRef(BaseModel):
    """A shop the caller owns."""

    id: uuid.UUID
    slug: str
    name: str
    city: str


class OwnerShopSummary(BaseModel):
    """One owned shop at a glance (O-07)."""

    shop: OwnerShopRef
    today_bookings: int = Field(
        description="Bookings not cancelled whose slot starts today in the shop's time zone."
    )
    needs_sa_action: int = Field(
        description=(
            "Bookings in PENDING, CONFIRMED, ESTIMATE_REVIEW, ESTIMATE_APPROVED, "
            "ESTIMATE_REJECTED or READY_FOR_PICKUP."
        )
    )
    in_progress: int = Field(description="Bookings in every other status that is not final.")
    ready_for_pickup: int = Field(
        description="Bookings currently READY_FOR_PICKUP (also in needs_sa_action)."
    )
    low_stock_count: int = Field(description="Active parts that are LOW or OUT.")


class OwnerSummaryRead(BaseModel):
    """`GET /api/v1/me/owner-summary`: one row per shop the caller owns that is not suspended
    (D99), by shop name; `items: []` for anyone who owns no such shop."""

    items: list[OwnerShopSummary]

"""HTTP routes of the inventory module (spec 03 §4.10, §5.3; D44, D80, D89).

One `shop_scoped_router()` (tenant check at router level, D20): a non-member gets 404 on every
route. Roles are gated with `require_roles` (403 `FORBIDDEN`), and the services check them again.
Each endpoint calls exactly one service function; operation ids are `inventory_<function name>`.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.database import DbSession
from app.core.error_handlers import problem_responses
from app.modules.inventory import service
from app.modules.inventory.schemas import (
    MAX_SEARCH_LENGTH,
    PartCreate,
    PartRead,
    PartSort,
    PartUpdate,
    PurchaseOrderCreate,
    PurchaseOrderRead,
    PurchaseOrderReceive,
    PurchaseOrderReceiveRead,
    PurchaseOrderSummary,
    StockAdjustmentCreate,
    StockAdjustmentRead,
    StockMovementRead,
    StockState,
)
from app.shared.auth import ShopContext, require_roles, shop_scoped_router
from app.shared.enums import PurchaseOrderStatus
from app.shared.pagination import Page, PageParamsDep
from app.shared.uow import UowDep

router = shop_scoped_router(tags=["inventory"])

PartReader = Annotated[ShopContext, Depends(require_roles(*service.PART_READERS))]
CatalogueEditor = Annotated[ShopContext, Depends(require_roles(*service.CATALOGUE_EDITORS))]
StockOperator = Annotated[ShopContext, Depends(require_roles(*service.STOCK_OPERATORS))]
LedgerReader = Annotated[ShopContext, Depends(require_roles(*service.LEDGER_READERS))]


# --- Parts catalogue -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PartListQuery:
    q: str | None
    stock_states: list[StockState]
    include_inactive: bool
    sort: PartSort


def part_list_query(
    q: Annotated[
        str | None,
        Query(max_length=MAX_SEARCH_LENGTH, description="Case-insensitive search in SKU and name."),
    ] = None,
    stock_state: Annotated[
        list[StockState] | None, Query(description="Repeatable: OK, LOW, OUT (D45).")
    ] = None,
    include_inactive: Annotated[bool, Query(description="Include deactivated parts.")] = False,
    sort: Annotated[PartSort, Query(description="`sku`, `name` or `available`; `-` = desc.")] = (
        "sku"
    ),
) -> PartListQuery:
    """The `GET …/parts` query parameters (spec 03 §4.10)."""
    return PartListQuery(
        q=q, stock_states=stock_state or [], include_inactive=include_inactive, sort=sort
    )


@router.get("/parts", responses=problem_responses(401, 403, 404, 422))
async def list_parts(
    ctx: PartReader,
    session: DbSession,
    page: PageParamsDep,
    query: Annotated[PartListQuery, Depends(part_list_query)],
) -> Page[PartRead]:
    """Parts with on hand, reserved, available, stock state and quantity on order (brief §7.4).

    Owner, Service Advisor and Technician read it (part picker); QC inspectors get 403.
    """
    return await service.list_parts(
        session,
        ctx,
        q=query.q,
        stock_states=query.stock_states,
        include_inactive=query.include_inactive,
        sort=query.sort,
        page=page,
    )


@router.post(
    "/parts",
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def create_part(ctx: CatalogueEditor, uow: UowDep, body: PartCreate) -> PartRead:
    """Add a part to the catalogue (Owner, Parts Person). It starts at `on_hand = 0` (D44)."""
    return await service.create_part(uow, ctx, body)


@router.patch("/parts/{part_id}", responses=problem_responses(401, 403, 404, 409, 422))
async def update_part(
    ctx: CatalogueEditor, uow: UowDep, part_id: UUID, body: PartUpdate
) -> PartRead:
    """Edit catalogue fields (never stock quantities); deactivate with `is_active: false`."""
    return await service.update_part(uow, ctx, part_id, body)


@router.post(
    "/parts/{part_id}/adjustments",
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def adjust_stock(
    ctx: StockOperator, uow: UowDep, part_id: UUID, body: StockAdjustmentCreate
) -> StockAdjustmentRead:
    """Opening stock or a count correction: one `ADJUST` movement (Parts Person only, D82).

    409 `INSUFFICIENT_STOCK` when on hand would drop below what is reserved, or below zero.
    """
    return await service.adjust_stock(
        uow, ctx, part_id=part_id, quantity_delta=body.quantity_delta, reason=body.reason
    )


@router.get("/parts/{part_id}/movements", responses=problem_responses(401, 403, 404, 422))
async def list_part_movements(
    ctx: LedgerReader, session: DbSession, part_id: UUID, page: PageParamsDep
) -> Page[StockMovementRead]:
    """The part's stock ledger, newest first (Owner, Parts Person)."""
    return await service.list_part_movements(session, ctx, part_id, page)


# --- Purchase orders -----------------------------------------------------------------------------


@router.get("/purchase-orders", responses=problem_responses(401, 403, 404, 422))
async def list_purchase_orders(
    ctx: LedgerReader,
    session: DbSession,
    page: PageParamsDep,
    statuses: Annotated[
        list[PurchaseOrderStatus] | None,
        Query(alias="status", description="Repeatable: ORDERED, PARTIALLY_RECEIVED, RECEIVED."),
    ] = None,
    booking_id: Annotated[UUID | None, Query(description="Only POs linked to this booking.")] = (
        None
    ),
) -> Page[PurchaseOrderSummary]:
    """Purchase orders, open ones first, then newest (Owner reads, Parts Person)."""
    return await service.list_purchase_orders(
        session, ctx, statuses=statuses or [], booking_id=booking_id, page=page
    )


@router.post(
    "/purchase-orders",
    status_code=status.HTTP_201_CREATED,
    responses=problem_responses(401, 403, 404, 422),
)
async def create_purchase_order(
    ctx: StockOperator, uow: UowDep, body: PurchaseOrderCreate
) -> PurchaseOrderRead:
    """A general restock order (Parts Person). Booking-linked POs come from `order-parts`."""
    return await service.create_purchase_order(uow, ctx, body)


@router.get("/purchase-orders/{po_id}", responses=problem_responses(401, 403, 404, 422))
async def get_purchase_order(
    ctx: LedgerReader, session: DbSession, po_id: UUID
) -> PurchaseOrderRead:
    """One purchase order with its items (Owner reads, Parts Person)."""
    return await service.get_purchase_order(session, ctx, po_id)


@router.post(
    "/purchase-orders/{po_id}/receive", responses=problem_responses(401, 403, 404, 409, 422)
)
async def receive_purchase_order(
    ctx: StockOperator, uow: UowDep, po_id: UUID, body: PurchaseOrderReceive
) -> PurchaseOrderReceiveRead:
    """Receive delivered quantities (any Parts Person). Stock goes up; for a linked booking in
    `PARTS_ORDERED` it is reserved first and may fire `RECEIVE_PARTS` (spec 03 §5.3)."""
    return await service.receive_purchase_order(uow, ctx, po_id, body)


routers: tuple[APIRouter, ...] = (router,)

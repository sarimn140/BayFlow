"""Every inventory HTTP use case re-checks the D44 role itself (`modules/inventory.md`): the seed
calls services directly, so a route's `require_roles` alone would not protect them.

Each case calls one use case directly with every role its route refuses, using arguments that
succeed for an allowed role (checked last). Removing that use case's `_require_role` therefore
makes its case fail, and the set of cases must equal the router's operations.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.core.errors import Forbidden
from app.modules.identity.models import User
from app.modules.inventory import service as inventory_service
from app.modules.inventory.models import Part, PurchaseOrder, PurchaseOrderItem, StockMovement
from app.modules.inventory.schemas import (
    PartCreate,
    PartUpdate,
    PurchaseOrderCreate,
    PurchaseOrderReceive,
)
from app.shared.auth import ShopContext
from app.shared.enums import MembershipRole
from app.shared.event_bus import EventBus
from app.shared.pagination import PageParams
from app.shared.uow import UnitOfWork
from tests.modules.inventory.support import Team, World, bearer, new_part, shop_context, url

pytestmark = pytest.mark.db

OWNER = MembershipRole.OWNER
SA = MembershipRole.SERVICE_ADVISOR
TECH = MembershipRole.TECHNICIAN
PP = MembershipRole.PARTS_PERSON
QC = MembershipRole.QC_INSPECTOR


@dataclass(frozen=True)
class Ids:
    part_id: UUID
    po_id: UUID
    item_id: UUID


Call = Callable[[AsyncSession, ShopContext, Ids], Awaitable[object]]


def uow(session: AsyncSession) -> UnitOfWork:
    return UnitOfWork(session, EventBus())


# One call per HTTP use case, with arguments that work for an allowed role.
CALLS: dict[str, Call] = {
    "list_parts": lambda s, ctx, ids: inventory_service.list_parts(
        s,
        ctx,
        q=None,
        stock_states=[],
        include_inactive=False,
        sort="sku",
        page=PageParams(),
    ),
    "create_part": lambda s, ctx, ids: inventory_service.create_part(
        uow(s), ctx, PartCreate.model_validate({"sku": "NEW-1", "name": "New", "unit_cost": 100})
    ),
    "update_part": lambda s, ctx, ids: inventory_service.update_part(
        uow(s), ctx, ids.part_id, PartUpdate.model_validate({"name": "Renamed"})
    ),
    "adjust_stock": lambda s, ctx, ids: inventory_service.adjust_stock(
        uow(s), ctx, part_id=ids.part_id, quantity_delta=1, reason="Count"
    ),
    "list_part_movements": lambda s, ctx, ids: inventory_service.list_part_movements(
        s, ctx, ids.part_id, PageParams()
    ),
    "list_purchase_orders": lambda s, ctx, ids: inventory_service.list_purchase_orders(
        s, ctx, statuses=[], booking_id=None, page=PageParams()
    ),
    "get_purchase_order": lambda s, ctx, ids: inventory_service.get_purchase_order(
        s, ctx, ids.po_id
    ),
    "create_purchase_order": lambda s, ctx, ids: inventory_service.create_purchase_order(
        uow(s),
        ctx,
        PurchaseOrderCreate.model_validate({"items": [{"part_id": ids.part_id, "quantity": 1}]}),
    ),
    "receive_purchase_order": lambda s, ctx, ids: inventory_service.receive_purchase_order(
        uow(s),
        ctx,
        ids.po_id,
        PurchaseOrderReceive.model_validate({"items": [{"item_id": ids.item_id, "quantity": 1}]}),
    ),
}

# Spec 04 RBAC B / spec 03 §4.10: the roles each route admits.
ALLOWED: dict[str, set[MembershipRole]] = {
    "list_parts": {OWNER, SA, TECH, PP},
    "create_part": {OWNER, PP},
    "update_part": {OWNER, PP},
    "adjust_stock": {PP},
    "list_part_movements": {OWNER, PP},
    "list_purchase_orders": {OWNER, PP},
    "get_purchase_order": {OWNER, PP},
    "create_purchase_order": {PP},
    "receive_purchase_order": {PP},
}


def member(team: Team, role: MembershipRole) -> User:
    users = {OWNER: team.owner, SA: team.advisor, TECH: team.technician, PP: team.parts}
    return users.get(role, team.qc)


async def make_ids(api: httpx.AsyncClient, team: Team) -> Ids:
    part = await new_part(api, team, "ROLE-PART", stock=5)
    order = await api.post(
        url(team.id, "/purchase-orders"),
        json={"items": [{"part_id": part["id"], "quantity": 5}]},
        headers=bearer(team.parts),
    )
    assert order.status_code == 201, order.text
    return Ids(
        part_id=UUID(part["id"]),
        po_id=UUID(order.json()["id"]),
        item_id=UUID(order.json()["items"][0]["id"]),
    )


async def state(db: Database) -> tuple[Any, ...]:
    """Everything a forbidden call could have changed."""
    async with db.sessionmaker() as session:
        parts = (await session.execute(select(Part.sku, Part.name, Part.on_hand))).all()
        movements = (
            await session.execute(select(func.count()).select_from(StockMovement))
        ).scalar_one()
        orders = (
            await session.execute(select(func.count()).select_from(PurchaseOrder))
        ).scalar_one()
        received = (
            await session.execute(select(func.sum(PurchaseOrderItem.received_qty)))
        ).scalar_one()
    return sorted(parts), movements, orders, received


async def test_every_http_use_case_has_a_role_case(api: httpx.AsyncClient) -> None:
    document = (await api.get("/openapi.json")).json()
    operations = {
        operation["operationId"].removeprefix("inventory_")
        for operations in document["paths"].values()
        for operation in operations.values()
        if operation.get("tags") == ["inventory"]
    }
    assert operations == set(CALLS) == set(ALLOWED)


@pytest.mark.parametrize("use_case", sorted(CALLS))
async def test_every_use_case_rechecks_the_role_for_direct_callers(
    api: httpx.AsyncClient, world: World, db: Database, use_case: str
) -> None:
    ids = await make_ids(api, world.a)
    before = await state(db)
    refused = sorted(set(MembershipRole) - ALLOWED[use_case])
    assert refused, use_case
    for role in refused:
        ctx = shop_context(world.a, member(world.a, role), role)
        async with db.sessionmaker() as session:
            with pytest.raises(Forbidden):
                await CALLS[use_case](session, ctx, ids)
    assert await state(db) == before
    allowed = shop_context(world.a, world.a.parts, PP)  # the same call works for an allowed role
    async with db.sessionmaker() as session:
        assert await CALLS[use_case](session, allowed, ids) is not None

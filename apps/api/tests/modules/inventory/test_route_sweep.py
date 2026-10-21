"""Every inventory operation, enumerated from the generated OpenAPI document (spec 12 §3.4: never
`app.routes`): SEC-02 (cross-tenant 404 both ways), SEC-04 (401), SEC-06 (the RBAC B role matrix,
spec 04: QC inspectors have no inventory access at all) and API-13 (`Cache-Control: no-store`).
A new inventory route fails `test_the_matrix_covers_every_inventory_operation` until it is added
to `ALLOWED`."""

from itertools import count
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.shared.enums import MembershipRole
from tests.modules.inventory.support import (
    Team,
    World,
    assert_problem,
    bearer,
    new_part,
)

pytestmark = [pytest.mark.db, pytest.mark.slow]

OWNER = MembershipRole.OWNER
SA = MembershipRole.SERVICE_ADVISOR
TECH = MembershipRole.TECHNICIAN
PP = MembershipRole.PARTS_PERSON
QC = MembershipRole.QC_INSPECTOR

ALLOWED: dict[tuple[str, str], set[MembershipRole]] = {
    ("get", "/parts"): {OWNER, SA, TECH, PP},
    ("post", "/parts"): {OWNER, PP},
    ("patch", "/parts/{part_id}"): {OWNER, PP},
    ("post", "/parts/{part_id}/adjustments"): {PP},
    ("get", "/parts/{part_id}/movements"): {OWNER, PP},
    ("get", "/purchase-orders"): {OWNER, PP},
    ("post", "/purchase-orders"): {PP},
    ("get", "/purchase-orders/{po_id}"): {OWNER, PP},
    ("post", "/purchase-orders/{po_id}/receive"): {PP},
}
PREFIX = "/api/v1/shops/{shop_id}"
_sku = count(1)


async def inventory_operations(api: httpx.AsyncClient) -> list[tuple[str, str]]:
    document = (await api.get("/openapi.json")).json()
    return sorted(
        (method, path.removeprefix(PREFIX))
        for path, operations in document["paths"].items()
        for method, operation in operations.items()
        if operation.get("tags") == ["inventory"]
    )


def members(team: Team) -> dict[MembershipRole, Any]:
    return {OWNER: team.owner, SA: team.advisor, TECH: team.technician, PP: team.parts, QC: team.qc}


async def resources(api: httpx.AsyncClient, team: Team) -> dict[str, str]:
    part = await new_part(api, team, f"SWEEP-{next(_sku)}", stock=5)
    order = await api.post(
        f"/api/v1/shops/{team.id}/purchase-orders",
        json={"items": [{"part_id": part["id"], "quantity": 1000}]},
        headers=bearer(team.parts),
    )
    assert order.status_code == 201, order.text
    return {
        "part_id": part["id"],
        "po_id": order.json()["id"],
        "item_id": order.json()["items"][0]["id"],
    }


def request_for(
    method: str, path: str, shop_id: object, ids: dict[str, str]
) -> tuple[str, str, dict[str, Any] | None]:
    """A schema-valid request for the operation (403/404 must never hide behind a 422)."""
    url = f"/api/v1/shops/{shop_id}" + path.format(**ids)
    bodies: dict[tuple[str, str], dict[str, Any]] = {
        ("post", "/parts"): {"sku": f"NEW-{next(_sku)}", "name": "Swept", "unit_cost": "100"},
        ("patch", "/parts/{part_id}"): {"name": "Renamed"},
        ("post", "/parts/{part_id}/adjustments"): {"quantity_delta": 1, "reason": "Sweep"},
        ("post", "/purchase-orders"): {"items": [{"part_id": ids["part_id"], "quantity": 1}]},
        ("post", "/purchase-orders/{po_id}/receive"): {
            "items": [{"item_id": ids["item_id"], "quantity": 1}]
        },
    }
    return method, url, bodies.get((method, path))


async def call(
    api: httpx.AsyncClient, request: tuple[str, str, dict[str, Any] | None], headers: dict[str, str]
) -> httpx.Response:
    method, url, body = request
    return await api.request(method.upper(), url, json=body, headers=headers)


async def test_the_matrix_covers_every_inventory_operation(api: httpx.AsyncClient) -> None:
    assert await inventory_operations(api) == sorted(ALLOWED)
    document = (await api.get("/openapi.json")).json()
    operation_ids = sorted(
        operation["operationId"]
        for path, operations in document["paths"].items()
        for operation in operations.values()
        if operation.get("tags") == ["inventory"]
    )
    assert operation_ids == [
        "inventory_adjust_stock",
        "inventory_create_part",
        "inventory_create_purchase_order",
        "inventory_get_purchase_order",
        "inventory_list_part_movements",
        "inventory_list_parts",
        "inventory_list_purchase_orders",
        "inventory_receive_purchase_order",
        "inventory_update_part",
    ]


async def test_sec04_every_operation_needs_credentials(
    api: httpx.AsyncClient, world: World
) -> None:
    ids = await resources(api, world.a)
    for method, path in await inventory_operations(api):
        response = await call(api, request_for(method, path, world.a.id, ids), {})
        assert_problem(response, 401, "UNAUTHENTICATED")
        assert response.headers["cache-control"] == "no-store"


async def test_sec06_role_matrix(api: httpx.AsyncClient, world: World) -> None:
    ids = await resources(api, world.a)
    for method, path in await inventory_operations(api):
        for role, user in members(world.a).items():
            response = await call(api, request_for(method, path, world.a.id, ids), bearer(user))
            if role in ALLOWED[(method, path)]:
                assert response.status_code in {200, 201}, (method, path, role, response.text)
            else:
                assert_problem(response, 403, "FORBIDDEN")
            assert response.headers["cache-control"] == "no-store"  # API-13


async def test_sec02_cross_tenant_access_is_404_both_ways(
    api: httpx.AsyncClient, world: World
) -> None:
    mine, theirs = await resources(api, world.a), await resources(api, world.b)
    for method, path in await inventory_operations(api):
        # Shop B's Parts Person (allowed everywhere) on Shop A's routes: not a member → 404.
        foreign_shop = request_for(method, path, world.a.id, mine)
        assert_problem(await call(api, foreign_shop, bearer(world.b.parts)), 404, "NOT_FOUND")
        # Shop A's own routes with Shop B's resource ids (when the path names a resource).
        if "{" in path:
            foreign_ids = {**mine, "part_id": theirs["part_id"], "po_id": theirs["po_id"]}
            if path.endswith("/receive"):
                foreign_ids["item_id"] = theirs["item_id"]
            response = await call(
                api, request_for(method, path, world.a.id, foreign_ids), bearer(world.a.parts)
            )
            assert_problem(response, 404, "NOT_FOUND")
        # An unknown shop id and a deactivated membership look exactly the same.
        unknown = request_for(method, path, uuid4(), mine)
        assert_problem(await call(api, unknown, bearer(world.a.parts)), 404, "NOT_FOUND")
        former = await call(
            api, request_for(method, path, world.a.id, mine), bearer(world.a.former_parts)
        )
        assert_problem(former, 404, "NOT_FOUND")

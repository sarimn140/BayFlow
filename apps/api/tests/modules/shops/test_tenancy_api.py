"""Tenant isolation and the management matrix on shop routes (D20, D80; spec 04 RBAC A).

Covers SEC-01 (shop routes), SEC-02 (route sweep from the generated OpenAPI document, every
module's `/api/v1/shops/{shop_id}/…` operations), SEC-03, SEC-04 and SEC-05.
"""

import re
import uuid
from typing import Any

import httpx
import pytest

from app.core.database import Database
from app.shared.enums import MembershipRole
from tests.assertions import assert_problem
from tests.modules.identity.builders import bearer, make_user, unique_email
from tests.modules.shops.builders import ShopCtx, add_member, make_services, make_shop, week

pytestmark = pytest.mark.db

SHOP_PREFIX = "/api/v1/shops/{shop_id}"
NOT_FOUND_DETAIL = "The requested resource was not found."


def shop_operations(schema: dict[str, Any]) -> list[tuple[str, str]]:
    """Every `(method, path template)` under `/api/v1/shops/{shop_id}` (spec 12 §3.4: the
    generated document, never `app.routes`)."""
    return [
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        if path == SHOP_PREFIX or path.startswith(f"{SHOP_PREFIX}/")
        for method in operations
    ]


def fill(path: str, shop_id: uuid.UUID) -> str:
    """Put the shop id in and a random UUID in every other path parameter."""
    filled = path.replace("{shop_id}", str(shop_id))
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), filled)


async def test_sec02_every_shop_route_is_404_for_another_tenant(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    shop_a = await make_shop(db)
    shop_b = await make_shop(db)
    bilal = await add_member(db, shop_a, MembershipRole.SERVICE_ADVISOR)
    schema = (await db_client.get("/openapi.json")).json()
    operations = shop_operations(schema)
    shops_operations = {
        ("GET", SHOP_PREFIX),
        ("PATCH", SHOP_PREFIX),
        ("PUT", f"{SHOP_PREFIX}/working-hours"),
        ("GET", f"{SHOP_PREFIX}/members"),
        ("POST", f"{SHOP_PREFIX}/members"),
        ("PATCH", f"{SHOP_PREFIX}/members/{{membership_id}}"),
        ("GET", f"{SHOP_PREFIX}/services"),
        ("POST", f"{SHOP_PREFIX}/services"),
        ("PATCH", f"{SHOP_PREFIX}/services/{{service_id}}"),
    }
    assert shops_operations <= set(operations)
    for caller in (bilal.id, shop_a.owner.id):
        for method, path in operations:
            response = await db_client.request(
                method, fill(path, shop_b.id), json={}, headers=bearer(caller)
            )
            problem = assert_problem(response, 404, "NOT_FOUND")  # never 2xx, 403 or 422
            assert problem["detail"] == NOT_FOUND_DETAIL, (method, path)


async def test_sec01_sec02_own_shop_with_another_shops_resource_ids_is_404(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    shop_a = await make_shop(db)
    shop_b = await make_shop(db)
    member_b = await add_member(db, shop_b, MembershipRole.TECHNICIAN)
    (service_b,) = await make_services(db, shop_b, ["Shop B service"])
    headers = bearer(shop_a.owner.id)
    base = f"/api/v1/shops/{shop_a.id}"
    member = await db_client.patch(
        f"{base}/members/{member_b.membership_id}", json={"is_active": False}, headers=headers
    )
    service = await db_client.patch(
        f"{base}/services/{service_b.id}", json={"name": "Hijacked"}, headers=headers
    )
    unknown = await db_client.patch(
        f"{base}/services/{uuid.uuid4()}", json={"name": "Hijacked"}, headers=headers
    )
    bodies = [assert_problem(r, 404, "NOT_FOUND") for r in (member, service, unknown)]
    assert {body["detail"] for body in bodies} == {NOT_FOUND_DETAIL}
    shop_b_members = await db_client.get(
        f"/api/v1/shops/{shop_b.id}/members", headers=bearer(shop_b.owner.id)
    )
    assert all(item["is_active"] for item in shop_b_members.json()["items"])  # untouched


async def test_sec03_non_members_get_404_identical_to_an_unknown_shop(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    shop_a = await make_shop(db)
    ayesha = await make_user(db)  # a customer: no membership
    other_owner = (await make_shop(db)).owner
    responses = [
        await db_client.get(f"/api/v1/shops/{shop_a.id}", headers=bearer(ayesha.id)),
        await db_client.get(f"/api/v1/shops/{shop_a.id}/services", headers=bearer(other_owner.id)),
        await db_client.get(f"/api/v1/shops/{uuid.uuid4()}", headers=bearer(ayesha.id)),
    ]
    bodies = [assert_problem(response, 404, "NOT_FOUND") for response in responses]
    assert {body["detail"] for body in bodies} == {NOT_FOUND_DETAIL}
    for body in bodies:
        body.pop("instance")
    assert bodies[0] == bodies[1] == bodies[2]


async def test_sec04_protected_shop_routes_need_a_valid_session(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    url = f"/api/v1/shops/{ctx.id}"
    assert_problem(await db_client.get(url), 401, "UNAUTHENTICATED")
    garbage = await db_client.get(url, headers={"Authorization": "Bearer garbage"})
    assert_problem(garbage, 401, "UNAUTHENTICATED")
    no_body = await db_client.patch(url, json={})
    assert_problem(no_body, 401, "UNAUTHENTICATED")  # 401 before membership and schema


async def test_sec05_the_management_matrix(db_client: httpx.AsyncClient, db: Database) -> None:
    ctx: ShopCtx = await make_shop(db)
    (service,) = await make_services(db, ctx, ["Oil change"])
    target = await add_member(db, ctx, MembershipRole.QC_INSPECTOR)
    base = f"/api/v1/shops/{ctx.id}"
    calls: list[tuple[str, str, dict[str, Any]]] = [
        ("PATCH", base, {"slot_capacity": 3}),
        ("PUT", f"{base}/working-hours", {"working_hours": week()}),
        (
            "POST",
            f"{base}/members",
            {"email": unique_email(), "full_name": "X", "role": "TECHNICIAN", "password": "x" * 12},
        ),
        ("PATCH", f"{base}/members/{target.membership_id}", {"is_active": False}),
        ("POST", f"{base}/services", {"name": "Brakes", "estimated_duration_minutes": 60}),
        ("PATCH", f"{base}/services/{service.id}", {"name": "Oil and filter"}),
    ]
    for role in (
        MembershipRole.SERVICE_ADVISOR,
        MembershipRole.TECHNICIAN,
        MembershipRole.PARTS_PERSON,
        MembershipRole.QC_INSPECTOR,
    ):
        member = await add_member(db, ctx, role)
        for method, path, body in calls:
            response = await db_client.request(method, path, json=body, headers=bearer(member.id))
            assert_problem(response, 403, "FORBIDDEN")
        schema_invalid = await db_client.patch(base, json={"slug": "x"}, headers=bearer(member.id))
        assert_problem(schema_invalid, 403, "FORBIDDEN")  # the role check runs before the body
    for method, path, body in calls:
        response = await db_client.request(method, path, json=body, headers=bearer(ctx.owner.id))
        assert response.status_code in {200, 201}, (method, path, response.text)

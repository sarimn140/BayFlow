"""Access to the reporting routes, enumerated from the generated OpenAPI document (spec 12 §3.4:
never `app.routes`).

- The contract: operation ids, tag, documented problem responses, no body and no query parameters.
- SEC-02: every shop-scoped reporting operation is 404 for every member of another shop (active or
  not, whatever the role) and for an unknown shop id: never 2xx, 403 or 422.
- SEC-03: non-members — a customer, another shop's owner — get the same 404 as an unknown shop.
- The route's own guard (`require_roles(OWNER)`) answers 403 before the service runs; the
  service's re-check is tested on its own in `tests/unit/reporting/test_service.py`.
- 401 without valid credentials (no token, garbage, expired, a WebSocket ticket, another scheme,
  a deactivated user), 422 for a malformed `shop_id`, 405 for other methods, 404 for a trailing
  slash, and the cookie session.
- API-13: every response of every reporting operation — success and error — is `no-store`.
"""

from datetime import timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import update

from app.core.database import Database
from app.core.security import issue_token
from app.modules.identity.models import User
from app.modules.reporting import service as reporting_service
from app.shared.auth import ShopContext
from app.shared.clock import utcnow
from app.shared.enums import MembershipRole
from tests.assertions import assert_problem
from tests.modules.reporting.support import SUMMARY_URL, World, bearer, overview_url

pytestmark = pytest.mark.db

OVERVIEW = ("get", "/api/v1/shops/{shop_id}/overview")
SUMMARY = ("get", "/api/v1/me/owner-summary")
SHOP_PREFIX = "/api/v1/shops/{shop_id}/"
NOT_FOUND_DETAIL = "The requested resource was not found."


async def reporting_operations(api: httpx.AsyncClient) -> dict[tuple[str, str], dict[str, Any]]:
    document = (await api.get("/openapi.json")).json()
    return {
        (method, path): operation
        for path, operations in document["paths"].items()
        for method, operation in operations.items()
        if "reporting" in operation.get("tags", [])
    }


def members_of(world: World) -> list[User]:
    a = world.a
    return [a.owner, a.advisor, a.technician, a.technician_2, a.parts, a.qc, a.qc_2, a.former]


async def test_the_contract_in_the_openapi_document(api: httpx.AsyncClient) -> None:
    operations = await reporting_operations(api)
    assert {key: operation["operationId"] for key, operation in operations.items()} == {
        OVERVIEW: "reporting_get_overview",
        SUMMARY: "reporting_get_owner_summary",
    }
    for operation in operations.values():
        assert operation["tags"] == ["reporting"]
        assert "requestBody" not in operation
        assert all(parameter["in"] == "path" for parameter in operation.get("parameters", []))
    overview, summary = operations[OVERVIEW], operations[SUMMARY]
    assert [parameter["name"] for parameter in overview["parameters"]] == ["shop_id"]
    assert "parameters" not in summary
    assert sorted(overview["responses"]) == ["200", "401", "403", "404", "422"]
    assert sorted(summary["responses"]) == ["200", "401"]
    for status in ("401", "403", "404"):
        assert overview["responses"][status]["content"] == {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}
        }
    assert overview["responses"]["422"]["content"] == {
        "application/problem+json": {"schema": {"$ref": "#/components/schemas/ValidationProblem"}}
    }
    for operation, schema in ((overview, "OverviewRead"), (summary, "OwnerSummaryRead")):
        assert operation["responses"]["200"]["content"] == {
            "application/json": {"schema": {"$ref": f"#/components/schemas/{schema}"}}
        }


async def test_the_nested_objects_have_stable_component_names(api: httpx.AsyncClient) -> None:
    schemas = (await api.get("/openapi.json")).json()["components"]["schemas"]
    expected = {
        "OverviewRead",
        "OverviewShop",
        "OverviewStatusCount",
        "OverviewToday",
        "OverviewTeamMember",
        "OverviewInventory",
        "OverviewSetup",
        "OwnerShopRef",
        "OwnerShopSummary",
        "OwnerSummaryRead",
    }
    assert expected <= set(schemas)
    overview = schemas["OverviewRead"]["properties"]
    assert overview["low_stock"]["items"] == {"$ref": "#/components/schemas/PartRead"}
    assert overview["status_counts"]["minItems"] == overview["status_counts"]["maxItems"] == 17
    assert overview["low_stock"]["maxItems"] == 5
    # `stock_value` is documented exactly like every `Money` response field: a string.
    stock_value = schemas["OverviewInventory"]["properties"]["stock_value"]
    unit_cost = schemas["PartRead"]["properties"]["unit_cost"]
    assert stock_value["type"] == unit_cost["type"] == "string"
    assert schemas["OverviewToday"]["properties"]["date"] == {
        "type": "string",
        "format": "date",
        "title": "Date",
        "description": "The shop-local date (YYYY-MM-DD).",
    }


async def test_sec02_another_tenants_members_get_404_on_every_shop_route(
    api: httpx.AsyncClient, world: World
) -> None:
    operations = [key for key in await reporting_operations(api) if key[1].startswith(SHOP_PREFIX)]
    assert operations == [OVERVIEW]
    for method, path in operations:
        for shop_id in (world.b.id, uuid4()):
            for user in members_of(world):  # every role of Shop A, the deactivated one too
                response = await api.request(
                    method.upper(), path.format(shop_id=shop_id), json={}, headers=bearer(user)
                )
                body = assert_problem(response, 404, "NOT_FOUND")
                assert body["detail"] == NOT_FOUND_DETAIL
                assert response.headers["cache-control"] == "no-store"


async def test_sec03_non_members_get_the_unknown_shop_404(
    api: httpx.AsyncClient, world: World
) -> None:
    unknown = await api.get(overview_url(uuid4()), headers=bearer(world.a.owner))
    reference = assert_problem(unknown, 404, "NOT_FOUND")
    for outsider in (world.customer, world.b.owner):
        response = await api.get(overview_url(world.a.id), headers=bearer(outsider))
        body = assert_problem(response, 404, "NOT_FOUND")
        assert {**body, "instance": None} == {**reference, "instance": None}


async def test_the_route_guard_answers_403_before_the_service_runs(
    api: httpx.AsyncClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    reached: list[MembershipRole] = []

    async def spy(session: object, ctx: ShopContext) -> Any:
        reached.append(ctx.role)
        raise AssertionError("the overview service must not run for this caller")

    monkeypatch.setattr(reporting_service, "get_owner_overview", spy)
    a = world.a
    for user in (a.advisor, a.technician, a.parts, a.qc):
        response = await api.get(overview_url(a.id), headers=bearer(user))
        assert_problem(response, 403, "FORBIDDEN")
    assert reached == []


def _credentials(user: User) -> dict[str, dict[str, str]]:
    now = utcnow()
    return {
        "none": {},
        "garbage token": {"Authorization": "Bearer not-a-jwt"},
        "expired token": {
            "Authorization": f"Bearer {issue_token(user.id, 'session', now - timedelta(days=8))}"
        },
        "websocket ticket": {"Authorization": f"Bearer {issue_token(user.id, 'ws', now)}"},
        "basic scheme": {"Authorization": "Basic dXNlcjpwYXNz"},
    }


async def test_401_without_valid_credentials(api: httpx.AsyncClient, world: World) -> None:
    for url in (overview_url(world.a.id), SUMMARY_URL):
        for label, headers in _credentials(world.a.owner).items():
            response = await api.get(url, headers=headers)
            assert_problem(response, 401, "UNAUTHENTICATED")
            assert response.headers["www-authenticate"] == "Bearer", label
            assert response.headers["cache-control"] == "no-store", label


async def test_401_for_a_deactivated_user(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    headers = bearer(world.a.owner)
    async with db.sessionmaker() as session:
        await session.execute(
            update(User).where(User.id == world.a.owner.id).values(is_active=False)
        )
        await session.commit()
    for url in (overview_url(world.a.id), SUMMARY_URL):
        assert_problem(await api.get(url, headers=headers), 401, "UNAUTHENTICATED")


async def test_422_for_a_malformed_shop_id(api: httpx.AsyncClient, world: World) -> None:
    response = await api.get(overview_url("not-a-uuid"), headers=bearer(world.a.owner))
    body = assert_problem(response, 422, "VALIDATION_ERROR")
    # The only offending field is the path's shop id. (Every role-gated shop route repeats it
    # today: `require_roles` re-resolves `require_shop_member`, and FastAPI caches a dependency
    # only when it succeeds; so the set, not the list, is asserted.)
    assert body["errors"]
    assert {(error["field"], error["code"]) for error in body["errors"]} == {
        ("path.shop_id", "uuid_parsing")
    }
    assert response.headers["cache-control"] == "no-store"
    # Authentication comes first: without a token the same request is a 401.
    assert_problem(await api.get(overview_url("not-a-uuid")), 401, "UNAUTHENTICATED")


async def test_405_for_other_methods_and_404_for_a_trailing_slash(
    api: httpx.AsyncClient, world: World
) -> None:
    headers = bearer(world.a.owner)
    for url in (overview_url(world.a.id), SUMMARY_URL):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            response = await api.request(method, url, json={}, headers=headers)
            assert_problem(response, 405, "METHOD_NOT_ALLOWED")
            assert "GET" in response.headers["allow"]
            assert response.headers["cache-control"] == "no-store"
        trailing = await api.get(f"{url}/", headers=headers)
        assert_problem(trailing, 404, "NOT_FOUND")


async def test_the_cookie_session_works_too(api: httpx.AsyncClient, world: World) -> None:
    api.cookies.set("bf_session", issue_token(world.a.owner.id, "session", utcnow()))
    overview = await api.get(overview_url(world.a.id))
    summary = await api.get(SUMMARY_URL)
    assert overview.status_code == summary.status_code == 200
    assert overview.json()["shop"]["id"] == str(world.a.id)
    assert [item["shop"]["id"] for item in summary.json()["items"]] == [str(world.a.id)]


async def test_a_query_parameter_cannot_switch_the_shop(
    api: httpx.AsyncClient, world: World
) -> None:
    response = await api.get(
        overview_url(world.a.id), params={"shop_id": str(world.b.id)}, headers=bearer(world.a.owner)
    )
    assert response.status_code == 200
    assert response.json()["shop"]["id"] == str(world.a.id)


async def test_api13_every_reporting_response_is_no_store(
    api: httpx.AsyncClient, world: World
) -> None:
    """One success and every error kind per operation of the generated document (D61)."""
    a = world.a
    calls = {
        OVERVIEW: [
            (overview_url(a.id), bearer(a.owner), 200),
            (overview_url(a.id), {}, 401),
            (overview_url(a.id), bearer(a.advisor), 403),
            (overview_url(world.b.id), bearer(a.owner), 404),
            (overview_url("x"), bearer(a.owner), 422),
        ],
        SUMMARY: [
            (SUMMARY_URL, bearer(a.owner), 200),
            (SUMMARY_URL, bearer(world.customer), 200),
            (SUMMARY_URL, {}, 401),
        ],
    }
    assert set(await reporting_operations(api)) == set(calls)
    for requests in calls.values():
        for url, headers, status in requests:
            response = await api.get(url, headers=headers)
            assert response.status_code == status, (url, response.text)
            assert response.headers["cache-control"] == "no-store", url

"""`GET /api/v1/shops/{shop_id}/qc/checklist` — `qc_get_checklist` (spec 03 §4.11).

QC-12 (every role gets the five items in D46 order with spec 03 labels; non-members 404), and on
this route: SEC-03 (non-members 404), SEC-04 (401 without a token), API-01 (problem+json), API-05
(a bounded list is `{items}`), API-13 (`Cache-Control: no-store`), the operation id and tag
(spec 03 §1.11) and the documented problem responses.
"""

import uuid

import httpx
import pytest
from sqlalchemy import update

from app.core.security import issue_token
from app.modules.identity.models import User
from app.modules.shops.models import ShopMembership
from app.shared.clock import utcnow
from tests.modules.qc.support import QcWorld

PATH = "/api/v1/shops/{shop_id}/qc/checklist"
EXPECTED_ITEMS = [
    {"key": "road_test", "label": "Road test"},
    {"key": "no_warning_lights", "label": "No warning lights"},
    {"key": "no_leaks", "label": "No leaks"},
    {"key": "fluid_levels", "label": "Fluid levels OK"},
    {"key": "complaint_resolved", "label": "Customer complaint resolved"},
]
NOT_FOUND_DETAIL = "The requested resource was not found."


def url(shop_id: object) -> str:
    return PATH.format(shop_id=shop_id)


def bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(user.id, 'session', utcnow())}"}


def assert_problem(response: httpx.Response, status: int, code: str) -> dict[str, object]:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"] == "about:blank"
    assert body["instance"] == response.request.url.path
    return dict(body)


@pytest.mark.db
@pytest.mark.parametrize(
    "member", ["owner", "advisor", "technician", "parts", "inspector", "inspector_2"]
)
async def test_qc12_every_role_reads_the_checklist_in_d46_order(
    db_client: httpx.AsyncClient, world: QcWorld, member: str
) -> None:
    response = await db_client.get(url(world.a.id), headers=bearer(getattr(world.a, member)))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"  # API-13 (D61)
    assert response.json() == {"items": EXPECTED_ITEMS}  # API-05: a bounded list, no paging


@pytest.mark.db
async def test_qc12_the_cookie_session_works_too(
    db_client: httpx.AsyncClient, world: QcWorld
) -> None:
    db_client.cookies.set("bf_session", issue_token(world.a.inspector.id, "session", utcnow()))
    response = await db_client.get(url(world.a.id))
    assert response.status_code == 200
    assert response.json()["items"][0] == {"key": "road_test", "label": "Road test"}


@pytest.mark.db
@pytest.mark.parametrize(
    ("who", "shop"),
    [
        ("customer", "a"),  # a customer has no membership (SEC-03)
        ("b.inspector", "a"),  # another tenant's QC inspector (SEC-01 shape)
        ("a.owner", "b"),  # the owner of shop A on shop B
        ("a.inspector", "unknown"),  # a shop that does not exist
    ],
)
async def test_qc12_everyone_outside_an_active_membership_gets_404(
    db_client: httpx.AsyncClient, world: QcWorld, who: str, shop: str
) -> None:
    user = world.customer if who == "customer" else getattr(getattr(world, who[0]), who[2:])
    shop_id = uuid.uuid4() if shop == "unknown" else getattr(world, shop).id
    response = await db_client.get(url(shop_id), headers=bearer(user))
    body = assert_problem(response, 404, "NOT_FOUND")
    assert body["detail"] == NOT_FOUND_DETAIL


@pytest.mark.db
async def test_qc12_a_deactivated_member_gets_404_with_the_same_token(
    db_client: httpx.AsyncClient, world: QcWorld
) -> None:
    headers = bearer(world.a.inspector_2)
    assert (await db_client.get(url(world.a.id), headers=headers)).status_code == 200
    async with world.db.sessionmaker() as session:
        await session.execute(
            update(ShopMembership)
            .where(
                ShopMembership.shop_id == world.a.id,
                ShopMembership.user_id == world.a.inspector_2.id,
            )
            .values(is_active=False)
        )
        await session.commit()
    assert_problem(await db_client.get(url(world.a.id), headers=headers), 404, "NOT_FOUND")


@pytest.mark.db
async def test_the_checklist_needs_a_session(db_client: httpx.AsyncClient, world: QcWorld) -> None:
    response = await db_client.get(url(world.a.id))
    assert_problem(response, 401, "UNAUTHENTICATED")
    assert response.headers["www-authenticate"] == "Bearer"
    garbage = await db_client.get(url(world.a.id), headers={"Authorization": "Bearer nope"})
    assert_problem(garbage, 401, "UNAUTHENTICATED")


@pytest.mark.db
async def test_a_malformed_shop_id_is_422_at_its_path(
    db_client: httpx.AsyncClient, world: QcWorld
) -> None:
    response = await db_client.get(url("not-a-uuid"), headers=bearer(world.a.inspector))
    body = assert_problem(response, 422, "VALIDATION_ERROR")
    assert [(error["field"], error["code"]) for error in body["errors"]] == [  # type: ignore[attr-defined]
        ("path.shop_id", "uuid_parsing")
    ]


@pytest.mark.db
async def test_other_methods_are_405(db_client: httpx.AsyncClient, world: QcWorld) -> None:
    response = await db_client.post(url(world.a.id), headers=bearer(world.a.inspector), json={})
    assert_problem(response, 405, "METHOD_NOT_ALLOWED")
    assert response.headers["allow"] == "GET"


@pytest.mark.db
async def test_a_trailing_slash_is_not_redirected(
    db_client: httpx.AsyncClient, world: QcWorld
) -> None:
    response = await db_client.get(url(world.a.id) + "/", headers=bearer(world.a.inspector))
    assert_problem(response, 404, "NOT_FOUND")


# --- OpenAPI contract (spec 03 §1.11, §3.6, §3.9) -------------------------------------------------


async def test_openapi_documents_qc_get_checklist(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    operation = schema["paths"][PATH]["get"]
    assert operation["operationId"] == "qc_get_checklist"
    assert operation["tags"] == ["qc"]
    assert [parameter["name"] for parameter in operation["parameters"]] == ["shop_id"]
    assert "requestBody" not in operation

    ok = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/ItemList_QcChecklistTemplateItem_"}
    for status, model in (("401", "Problem"), ("404", "Problem"), ("422", "ValidationProblem")):
        content = operation["responses"][status]["content"]
        assert list(content) == ["application/problem+json"]
        assert content["application/problem+json"]["schema"] == {
            "$ref": f"#/components/schemas/{model}"
        }

    components = schema["components"]["schemas"]
    envelope = components["ItemList_QcChecklistTemplateItem_"]
    assert envelope["required"] == ["items"]
    assert envelope["properties"]["items"]["items"] == {
        "$ref": "#/components/schemas/QcChecklistTemplateItem"
    }
    item = components["QcChecklistTemplateItem"]
    assert set(item["required"]) == {"key", "label"}
    assert item["properties"]["key"] == {"$ref": "#/components/schemas/QcChecklistKey"}
    assert components["QcChecklistKey"]["enum"] == [
        "road_test",
        "no_warning_lights",
        "no_leaks",
        "fluid_levels",
        "complaint_resolved",
    ]


async def test_qc_serves_exactly_one_route(client: httpx.AsyncClient) -> None:
    """Spec 03 §1.11: qc serves only the checklist; QC reads and actions are bookings routes."""
    schema = (await client.get("/openapi.json")).json()
    qc_operations = [
        operation["operationId"]
        for operations in schema["paths"].values()
        for operation in operations.values()
        if operation.get("tags") == ["qc"]
    ]
    assert qc_operations == ["qc_get_checklist"]

"""`GET /api/v1/me` and the capability guards (D66, D81; SEC-46, SHP-09, SHP-10)."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

import app.modules.shops.service as shops_service_module
from app.core.database import Database
from app.modules.shops.domain.capabilities import Capability
from app.shared.enums import MembershipRole
from tests.assertions import assert_problem
from tests.conftest import make_settings
from tests.modules.identity.builders import bearer, make_user, unique_email
from tests.modules.shops.builders import (
    ShopCtx,
    add_member,
    make_services,
    make_shop,
    set_member_active,
    week,
)

pytestmark = pytest.mark.db

ME = "/api/v1/me"


async def me(client: httpx.AsyncClient, user_id: object) -> dict[str, Any]:
    response = await client.get(ME, headers=bearer(user_id))  # type: ignore[arg-type]
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_sec46_me_for_an_owner_of_two_shops_staff_and_a_customer(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    fatima = await make_user(db, full_name="Fatima Raza")
    raza = await make_shop(db, owner=fatima, name="Raza Auto Works")
    lahore = await make_shop(db, owner=fatima, name="Lahore Auto Care")
    bilal = await add_member(db, lahore, MembershipRole.SERVICE_ADVISOR, full_name="Bilal")
    usman = await add_member(db, lahore, MembershipRole.PARTS_PERSON, full_name="Usman")
    ayesha = await make_user(db, full_name="Ayesha Khan", phone="+923000000101")

    owner_view = await me(db_client, fatima.id)
    assert {key: owner_view[key] for key in ("id", "email", "full_name", "phone")} == {
        "id": str(fatima.id),
        "email": fatima.email,
        "full_name": "Fatima Raza",
        "phone": None,
    }
    assert [(m["shop_name"], m["shop_slug"], m["role"]) for m in owner_view["memberships"]] == [
        ("Lahore Auto Care", "lahore-auto-care", "OWNER"),  # sorted by shop name
        ("Raza Auto Works", "raza-auto-works", "OWNER"),
    ]
    assert {m["shop_id"] for m in owner_view["memberships"]} == {str(lahore.id), str(raza.id)}
    owner_capabilities = ["parts.manage", "services.manage", "shop.manage", "team.manage"]
    assert all(m["capabilities"] == owner_capabilities for m in owner_view["memberships"])
    assert set(owner_view["memberships"][0]) == {
        "membership_id",
        "shop_id",
        "shop_name",
        "shop_slug",
        "shop_suspended",  # D96, spec 19 §2
        "role",
        "capabilities",
    }
    assert owner_view["is_platform_admin"] is False  # D94, spec 19 §4
    assert not any(m["shop_suspended"] for m in owner_view["memberships"])

    bilal_view = await me(db_client, bilal.id)
    assert [(m["role"], m["capabilities"]) for m in bilal_view["memberships"]] == [
        ("SERVICE_ADVISOR", [])  # no core capability; tasks.manage only with calling
    ]
    assert bilal_view["memberships"][0]["membership_id"] == str(bilal.membership_id)
    usman_view = await me(db_client, usman.id)
    assert usman_view["memberships"][0]["capabilities"] == ["parts.manage", "stock.manage"]
    ayesha_view = await me(db_client, ayesha.id)
    assert (ayesha_view["memberships"], ayesha_view["phone"]) == ([], "+923000000101")
    assert "password_hash" not in ayesha_view
    assert "is_active" not in ayesha_view

    hours = await db_client.put(
        f"/api/v1/shops/{lahore.id}/working-hours",
        json={"working_hours": week()},
        headers=bearer(bilal.id),
    )
    assert_problem(hours, 403, "FORBIDDEN")  # capabilities are hints; the route decides (D66)


async def test_shp09_me_lists_active_memberships_only_sorted_case_insensitively(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    worker = await make_user(db)
    shops = [
        await make_shop(db, name=name) for name in ("beta Motors", "Alpha Garage", "Gamma Works")
    ]
    memberships = [
        await add_member(db, ctx, MembershipRole.TECHNICIAN, user=worker) for ctx in shops
    ]
    await set_member_active(db, shops[2], memberships[2].membership_id, active=False)
    view = await me(db_client, worker.id)
    assert [m["shop_name"] for m in view["memberships"]] == ["Alpha Garage", "beta Motors"]


async def test_shp09_tasks_manage_appears_only_while_calling_is_enabled(
    db_client: httpx.AsyncClient, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = await make_shop(db)
    advisor = await add_member(db, ctx, MembershipRole.SERVICE_ADVISOR)
    technician = await add_member(db, ctx, MembershipRole.TECHNICIAN)
    calling = make_settings(
        call_provider_url="wss://calls.bayflow.test",
        call_provider_api_key="key",
        call_provider_api_secret="secret-value",
    )
    assert calling.calling_enabled
    monkeypatch.setattr(shops_service_module, "get_settings", lambda: calling)
    assert (await me(db_client, ctx.owner.id))["memberships"][0]["capabilities"] == [
        "parts.manage",
        "services.manage",
        "shop.manage",
        "tasks.manage",
        "team.manage",
    ]
    assert (await me(db_client, advisor.id))["memberships"][0]["capabilities"] == ["tasks.manage"]
    assert (await me(db_client, technician.id))["memberships"][0]["capabilities"] == []


async def test_me_needs_an_active_session(db_client: httpx.AsyncClient, db: Database) -> None:
    assert_problem(await db_client.get(ME), 401, "UNAUTHENTICATED")
    disabled = await make_user(db, active=False)
    assert_problem(await db_client.get(ME, headers=bearer(disabled.id)), 401, "UNAUTHENTICATED")
    assert_problem(
        await db_client.get(ME, headers={"Authorization": "Bearer nope"}), 401, "UNAUTHENTICATED"
    )


# --- SHP-10: every capability-guarded route agrees with /me ---------------------------------------


Request = tuple[str, str, Callable[[], dict[str, Any]]]


async def guarded_requests(db: Database, ctx: ShopCtx) -> dict[Capability, list[Request]]:
    (service,) = await make_services(db, ctx, ["Guarded service"])
    target = await add_member(db, ctx, MembershipRole.QC_INSPECTOR)
    base = f"/api/v1/shops/{ctx.id}"
    return {
        Capability.SHOP_MANAGE: [
            ("PATCH", base, lambda: {"slot_capacity": 3}),
            ("PUT", f"{base}/working-hours", lambda: {"working_hours": week()}),
        ],
        Capability.TEAM_MANAGE: [
            (
                "POST",
                f"{base}/members",
                lambda: {
                    "email": unique_email(),
                    "full_name": "Guarded Member",
                    "role": "TECHNICIAN",
                    "password": "Guarded-Pass-2026",
                },
            ),
            ("PATCH", f"{base}/members/{target.membership_id}", lambda: {"is_active": True}),
        ],
        Capability.SERVICES_MANAGE: [
            (
                "POST",
                f"{base}/services",
                lambda: {"name": unique_email("svc"), "estimated_duration_minutes": 30},
            ),
            ("PATCH", f"{base}/services/{service.id}", lambda: {"estimated_duration_minutes": 45}),
        ],
    }


async def test_shp10_route_guards_and_capabilities_agree(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    requests = await guarded_requests(db, ctx)
    callers = {MembershipRole.OWNER: ctx.owner.id}
    for role in MembershipRole:
        if role is not MembershipRole.OWNER:
            callers[role] = (await add_member(db, ctx, role)).id
    checked = 0
    for role, user_id in callers.items():
        view = await me(db_client, user_id)
        capabilities = set(view["memberships"][0]["capabilities"])
        for capability, calls in requests.items():
            for method, path, body in calls:
                response = await db_client.request(
                    method, path, json=body(), headers=bearer(user_id)
                )
                allowed = capability.value in capabilities
                assert (response.status_code != 403) is allowed, (role, method, path)
                assert response.status_code < 400 or not allowed, response.text
                checked += 1
    assert checked == 5 * 6

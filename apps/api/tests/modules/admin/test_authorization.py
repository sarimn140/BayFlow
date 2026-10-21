"""Who may call the admin API (spec 19 §4, §9 "Authorization"; D94).

Every E-61…E-75 route is 401 without credentials and 403 `FORBIDDEN` for every shop role (the
Owner included) and for customers; a refused request changes nothing and writes no audit row. The
routes are enumerated from the generated OpenAPI document (spec 12 §3.4 "Route enumeration rule").
"""

import uuid
from typing import Any

import httpx
import pytest

from app.core.database import Database
from app.modules.identity.schemas import UserRecord
from app.shared.enums import BookingStatus
from tests.assertions import assert_problem
from tests.modules.admin.support import ADMIN, audit_rows, make_admin
from tests.modules.bookings.support import Desk, World, drive_booking_to
from tests.modules.identity.builders import bearer

EXPECTED_OPERATIONS = {
    ("GET", f"{ADMIN}/overview"): "admin_get_overview",
    ("GET", f"{ADMIN}/shops"): "admin_list_shops",
    ("GET", f"{ADMIN}/shops/{{shop_id}}"): "admin_get_shop",
    ("POST", f"{ADMIN}/shops/{{shop_id}}/suspend"): "admin_suspend_shop",
    ("POST", f"{ADMIN}/shops/{{shop_id}}/reactivate"): "admin_reactivate_shop",
    ("GET", f"{ADMIN}/users"): "admin_list_users",
    ("GET", f"{ADMIN}/users/{{user_id}}"): "admin_get_user",
    ("POST", f"{ADMIN}/users/{{user_id}}/deactivate"): "admin_deactivate_user",
    ("POST", f"{ADMIN}/users/{{user_id}}/reactivate"): "admin_reactivate_user",
    ("POST", f"{ADMIN}/users/{{user_id}}/grant-platform-admin"): "admin_grant_platform_admin",
    ("POST", f"{ADMIN}/users/{{user_id}}/revoke-platform-admin"): "admin_revoke_platform_admin",
    ("GET", f"{ADMIN}/bookings"): "admin_list_bookings",
    ("GET", f"{ADMIN}/bookings/{{booking_id}}"): "admin_get_booking",
    ("GET", f"{ADMIN}/audit-events"): "admin_list_audit_events",
    ("GET", f"{ADMIN}/audit-events/export"): "admin_export_audit_events",
}


def admin_operations(schema: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (method.upper(), path): operation
        for path, methods in schema["paths"].items()
        for method, operation in methods.items()
        if path.startswith(ADMIN)
    }


async def test_the_admin_api_is_e61_to_e75_tagged_admin(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    operations = admin_operations(schema)
    assert set(operations) == set(EXPECTED_OPERATIONS)
    for key, operation_id in EXPECTED_OPERATIONS.items():
        assert operations[key]["operationId"] == operation_id
        assert operations[key]["tags"] == ["admin"]
        problems = operations[key]["responses"]
        for status in ("401", "403"):
            assert problems[status]["content"]["application/problem+json"], (key, status)
    export = operations[("GET", f"{ADMIN}/audit-events/export")]["responses"]["200"]
    assert "text/csv" in export["content"]


def _concrete(path: str, values: dict[str, str]) -> str:
    for name, value in values.items():
        path = path.replace(f"{{{name}}}", value)
    return path


async def _call(
    api: httpx.AsyncClient, method: str, path: str, headers: dict[str, str]
) -> httpx.Response:
    if method == "POST":
        return await api.post(path, headers=headers, json={"reason": "Checking the access rules"})
    return await api.get(path, headers=headers)


@pytest.mark.slow
async def test_every_admin_route_refuses_anonymous_staff_and_customers(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.CONFIRMED)
    other_admin = await make_admin(db, full_name="Ali Raza")
    schema = (await desk.api.get("/openapi.json")).json()
    values = {
        "shop_id": str(world.shop_id),
        "user_id": str(other_admin.id),
        "booking_id": journey.id,
    }
    callers = {
        "owner": world.owner.id,
        "service advisor": world.advisor.id,
        "technician": world.technician.id,
        "parts person": world.parts.id,
        "qc inspector": world.qc.id,
        "other shop's advisor": world.other_advisor.id,
        "customer": journey.customer.user_id,
    }
    rows_before = len(await audit_rows(desk.world.db))
    for method, template in EXPECTED_OPERATIONS:
        path = _concrete(template, values)
        anonymous = await _call(desk.api, method, path, {})
        body = assert_problem(anonymous, 401, "UNAUTHENTICATED")
        assert anonymous.headers["www-authenticate"] == "Bearer", body
        for who, user_id in callers.items():
            refused = await _call(desk.api, method, path, bearer(user_id))
            problem = assert_problem(refused, 403, "FORBIDDEN")
            assert problem["detail"] == "This area is for BayFlow platform admins.", (who, path)
    assert len(await audit_rows(desk.world.db)) == rows_before  # refused calls write nothing
    shop = await desk.get(world.owner.id, desk.shop_path())
    assert shop["id"] == str(world.shop_id)  # still open to its Owner: nothing was suspended
    me = await desk.get(other_admin.id, "/api/v1/me")
    assert me["is_platform_admin"] is True  # nothing was revoked
    assert "/api/v1/admin/overview" in {path for _, path in admin_operations(schema)}


async def test_an_admin_reaches_every_read_route(
    desk: Desk, world: World, admin: UserRecord
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.PENDING)
    headers = bearer(admin.id)
    for path in (
        "/overview",
        "/shops",
        f"/shops/{world.shop_id}",
        "/users",
        f"/users/{admin.id}",
        "/bookings",
        f"/bookings/{journey.id}",
        "/audit-events",
        "/audit-events/export",
    ):
        response = await desk.api.get(f"{ADMIN}{path}", headers=headers)
        assert response.status_code == 200, (path, response.text)


async def test_admin_access_follows_the_flag_at_every_request(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    """D9/D94: the flag is re-read per request — a revoked admin is refused at the next request,
    a deactivated one is 401 everywhere; `/me` reports the flag."""
    ali = await make_admin(db, full_name="Ali Raza")
    assert (await desk.api.get(f"{ADMIN}/overview", headers=bearer(ali.id))).status_code == 200
    assert (await desk.get(ali.id, "/api/v1/me"))["is_platform_admin"] is True
    revoked = await desk.api.post(
        f"{ADMIN}/users/{ali.id}/revoke-platform-admin", headers=bearer(admin.id)
    )
    assert revoked.status_code == 200, revoked.text
    assert_problem(
        await desk.api.get(f"{ADMIN}/overview", headers=bearer(ali.id)), 403, "FORBIDDEN"
    )
    assert (await desk.get(ali.id, "/api/v1/me"))["is_platform_admin"] is False
    granted = await desk.api.post(
        f"{ADMIN}/users/{ali.id}/grant-platform-admin", headers=bearer(admin.id)
    )
    assert granted.status_code == 200, granted.text
    deactivated = await desk.api.post(
        f"{ADMIN}/users/{ali.id}/deactivate",
        headers=bearer(admin.id),
        json={"reason": "Left the company"},
    )
    assert deactivated.status_code == 200, deactivated.text
    assert_problem(
        await desk.api.get(f"{ADMIN}/overview", headers=bearer(ali.id)), 401, "UNAUTHENTICATED"
    )


async def test_unknown_ids_are_404(desk: Desk, admin: UserRecord) -> None:
    unknown = str(uuid.uuid4())
    headers = bearer(admin.id)
    for method, path in (
        ("GET", f"/shops/{unknown}"),
        ("POST", f"/shops/{unknown}/suspend"),
        ("POST", f"/shops/{unknown}/reactivate"),
        ("GET", f"/users/{unknown}"),
        ("POST", f"/users/{unknown}/deactivate"),
        ("POST", f"/users/{unknown}/reactivate"),
        ("POST", f"/users/{unknown}/grant-platform-admin"),
        ("POST", f"/users/{unknown}/revoke-platform-admin"),
        ("GET", f"/bookings/{unknown}"),
    ):
        response = await _call(desk.api, method, f"{ADMIN}{path}", headers)
        assert_problem(response, 404, "NOT_FOUND")
    assert await audit_rows(desk.world.db) == []  # a 404 view is not recorded


# --- Cross-site requests (D98; spec 04 threat 8) --------------------------------------------------

CROSS_SITE_DETAIL = "Admin requests must come from the BayFlow app."


async def test_cross_site_requests_are_refused_before_anything_runs(
    desk: Desk, world: World, admin: UserRecord
) -> None:
    """`SameSite=Lax` lets a cross-site top-level GET carry the cookie, and E-67, E-73 and E-75
    write audit rows on GET: a browser request from another site (or a sibling subdomain) is 403
    and writes nothing."""
    journey = await drive_booking_to(desk, BookingStatus.PENDING)
    customer = journey.customer.user_id
    requests = (
        ("GET", f"{ADMIN}/users/{customer}"),
        ("GET", f"{ADMIN}/bookings/{journey.id}"),
        ("GET", f"{ADMIN}/audit-events/export"),
        ("GET", f"{ADMIN}/overview"),
        ("POST", f"{ADMIN}/shops/{world.shop_id}/suspend"),
        ("POST", f"{ADMIN}/users/{customer}/deactivate"),
    )
    rows_before = len(await audit_rows(desk.world.db))  # the booking's own rows
    for site in ("cross-site", "same-site", "Cross-Site", ""):
        for method, path in requests:
            headers = {**bearer(admin.id), "Sec-Fetch-Site": site}
            refused = await _call(desk.api, method, path, headers)
            problem = assert_problem(refused, 403, "FORBIDDEN")
            assert problem["detail"] == CROSS_SITE_DETAIL, (site, path)
        anonymous = await _call(desk.api, "GET", f"{ADMIN}/overview", {"Sec-Fetch-Site": site})
        assert_problem(anonymous, 403, "FORBIDDEN")  # refused before authentication
    assert len(await audit_rows(desk.world.db)) == rows_before  # refused calls write nothing
    shop = await desk.get(world.owner.id, desk.shop_path())
    assert shop["id"] == str(world.shop_id)  # not suspended
    me = await desk.get(customer, "/api/v1/me")
    assert me["id"] == str(customer)  # not deactivated: the session still works


async def test_same_origin_typed_and_headerless_requests_pass(
    desk: Desk, world: World, admin: UserRecord
) -> None:
    """Our own pages (`same-origin`, through the Vercel rewrite), a URL typed in the address bar
    (`none`) and clients that send no Fetch Metadata (curl, Swagger, tests) reach the API."""
    journey = await drive_booking_to(desk, BookingStatus.PENDING)
    customer = journey.customer.user_id
    before = {row.id for row in await audit_rows(desk.world.db)}  # the booking's own rows
    for site in ("same-origin", "none", None):
        headers = bearer(admin.id) | ({} if site is None else {"Sec-Fetch-Site": site})
        viewed = await desk.api.get(f"{ADMIN}/users/{customer}", headers=headers)
        assert viewed.status_code == 200, (site, viewed.text)
    suspend = await desk.api.post(
        f"{ADMIN}/shops/{world.shop_id}/suspend",
        headers={**bearer(admin.id), "Sec-Fetch-Site": "same-origin"},
        json={"reason": "Checking the access rules"},
    )
    assert suspend.status_code == 200, suspend.text
    reactivate = await desk.api.post(
        f"{ADMIN}/shops/{world.shop_id}/reactivate",
        headers={**bearer(admin.id), "Sec-Fetch-Site": "none"},
    )
    assert reactivate.status_code == 200, reactivate.text
    rows = [row for row in await audit_rows(desk.world.db) if row.id not in before]
    assert sorted(row.action for row in rows) == [
        "admin.user_viewed",
        "admin.user_viewed",
        "admin.user_viewed",
        "shop.reactivated",
        "shop.suspended",
    ]

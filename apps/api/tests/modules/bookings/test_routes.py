"""The bookings routes as the generated OpenAPI document lists them (spec 12 §3.4: never
`app.routes`).

BK-42 (the generated action routes: 22 staff slugs, 4 customer slugs, one request body per route,
operation IDs `bookings_<slug>` / `bookings_my_<slug>`), API-10's unknown slugs, SEC-02 (every
booking route answers another tenant's booking with the same 404), SEC-04 (401 without a session,
except the wizard) and D61 (`Cache-Control: no-store`).
"""

import uuid
from typing import Any

import httpx
import pytest

from app.core.database import Database
from app.modules.bookings import schemas
from app.modules.bookings.domain.state_machine import RULES
from app.modules.bookings.domain.timeline import customer_route_actions, staff_route_actions
from app.shared.enums import BookingStatus
from tests.modules.bookings.support import (
    Desk,
    World,
    drive_booking_to,
    full_checklist,
    labour_lines,
    new_customer,
    problem,
)
from tests.modules.identity.builders import bearer

pytestmark = pytest.mark.db

STAFF_ACTION = "/api/v1/shops/{shop_id}/bookings/{booking_id}/actions/"
CUSTOMER_ACTION = "/api/v1/me/bookings/{booking_id}/actions/"
NOT_FOUND = "The requested resource was not found."

READS = {
    "bookings_list_my_bookings": ("get", "/api/v1/me/bookings"),
    "bookings_get_my_booking": ("get", "/api/v1/me/bookings/{booking_id}"),
    "bookings_list_my_booking_events": ("get", "/api/v1/me/bookings/{booking_id}/events"),
    "bookings_list_my_booking_estimates": ("get", "/api/v1/me/bookings/{booking_id}/estimates"),
    "bookings_list_my_vehicles": ("get", "/api/v1/me/vehicles"),
    "bookings_list_shop_bookings": ("get", "/api/v1/shops/{shop_id}/bookings"),
    "bookings_get_status_counts": ("get", "/api/v1/shops/{shop_id}/bookings/status-counts"),
    "bookings_get_shop_booking": ("get", "/api/v1/shops/{shop_id}/bookings/{booking_id}"),
    "bookings_list_booking_events": (
        "get",
        "/api/v1/shops/{shop_id}/bookings/{booking_id}/events",
    ),
    "bookings_list_booking_estimates": (
        "get",
        "/api/v1/shops/{shop_id}/bookings/{booking_id}/estimates",
    ),
    "bookings_get_booking_parts": ("get", "/api/v1/shops/{shop_id}/bookings/{booking_id}/parts"),
    "bookings_list_booking_qc_inspections": (
        "get",
        "/api/v1/shops/{shop_id}/bookings/{booking_id}/qc-inspections",
    ),
    "bookings_create_booking": ("post", "/api/v1/bookings"),
    "bookings_edit_estimate": ("put", "/api/v1/shops/{shop_id}/bookings/{booking_id}/estimate"),
}


def pascal(slug: str) -> str:
    return "".join(part.capitalize() for part in slug.split("-"))


def expected_operations() -> dict[str, tuple[str, str]]:
    operations = dict(READS)
    for action in staff_route_actions():
        slug = RULES[action].slug
        operations["bookings_" + slug.replace("-", "_")] = ("post", STAFF_ACTION + slug)
    for action in customer_route_actions():
        slug = RULES[action].slug
        operations["bookings_my_" + slug.replace("-", "_")] = ("post", CUSTOMER_ACTION + slug)
    return operations


async def bookings_operations(api: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    """`operationId` → `{method, path, operation}` of every operation tagged `bookings`."""
    document = (await api.get("/openapi.json")).json()
    found: dict[str, dict[str, Any]] = {}
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            if operation.get("tags") == ["bookings"]:
                assert operation["operationId"] not in found
                found[operation["operationId"]] = {
                    "method": method,
                    "path": path,
                    "operation": operation,
                }
    return found


def schema_name(reference: dict[str, Any]) -> str:
    return str(reference["$ref"]).rsplit("/", 1)[-1]


# --- BK-42, API-10 --------------------------------------------------------------------------------


async def test_bk42_the_api_lists_exactly_the_generated_bookings_operations(
    db_client: httpx.AsyncClient,
) -> None:
    found = await bookings_operations(db_client)
    expected = expected_operations()
    assert {name: (op["method"], op["path"]) for name, op in found.items()} == expected
    assert len(expected) == 40
    staff = {
        op["path"].removeprefix(STAFF_ACTION) for op in found.values() if STAFF_ACTION in op["path"]
    }
    customer = {
        op["path"].removeprefix(CUSTOMER_ACTION)
        for op in found.values()
        if op["path"].startswith(CUSTOMER_ACTION)
    }
    assert len(staff) == 22
    assert customer == {"approve-estimate", "reject-estimate", "complete", "cancel"}
    listable = {rule.slug for rule in RULES.values() if rule.listable}
    assert staff | customer | {"edit-estimate"} <= listable
    for name, op in found.items():
        operation = op["operation"]
        if "/actions/" not in op["path"]:
            continue
        slug = op["path"].rsplit("/", 1)[-1]
        customer_family = op["path"].startswith(CUSTOMER_ACTION)
        body_name = (
            "CustomerCancelRequest"
            if customer_family and slug == "cancel"
            else (pascal(slug) + "Request")
        )
        body = operation["requestBody"]
        assert schema_name(body["content"]["application/json"]["schema"]) == body_name, name
        model = getattr(schemas, body_name)
        has_required = any(field.is_required() for field in model.model_fields.values())
        assert body.get("required", False) is has_required, name  # optional bodies may be omitted
        response = operation["responses"]["200"]["content"]["application/json"]["schema"]
        detail = "CustomerBookingDetail" if customer_family else "BookingDetail"
        assert schema_name(response) == detail, name
        assert {"401", "404", "409", "422"} <= set(operation["responses"]), name


async def test_api10_slugs_outside_a_family_are_404(desk: Desk, world: World) -> None:
    journey = await drive_booking_to(desk, BookingStatus.INSPECTING)
    for slug in ("edit-estimate", "create", "receive-parts", "approve-estimate", "nope"):
        response = await desk.act_raw(world.advisor.id, journey.id, slug)
        assert problem(response, 404, "NOT_FOUND")["detail"] == NOT_FOUND, slug
    for slug in ("confirm", "pick-qc", "edit-estimate", "notify-ready"):
        response = await desk.api.post(
            desk.my_path(journey.id, f"/actions/{slug}"), json={}, headers=journey.customer.headers
        )
        problem(response, 404, "NOT_FOUND")
    counts = await desk.get(world.advisor.id, desk.shop_path("/bookings/status-counts"))
    assert counts["total"] == 1  # `status-counts` is never taken for a booking id


# --- SEC-02, SEC-04, D61: the sweep ---------------------------------------------------------------


def body_for(name: str, world: World) -> dict[str, Any] | None:
    """A body that passes the schema, so the request reaches the visibility check (spec 03
    §1.4: 422 comes before the booking 404)."""
    bodies: dict[str, dict[str, Any]] = {
        "bookings_decline": {"reason": "Bay closed"},
        "bookings_cancel": {"reason": "Bay closed"},
        "bookings_assign_technician": {"technician_user_id": str(world.technician.id)},
        "bookings_reassign_technician": {"technician_user_id": str(world.technician2.id)},
        "bookings_assign_parts_person": {"parts_person_user_id": str(world.parts.id)},
        "bookings_reassign_parts_person": {"parts_person_user_id": str(world.parts2.id)},
        "bookings_pass_qc": {"checklist": full_checklist()},
        "bookings_fail_qc": {"issue_title": "Leak", "issue_description": "Seal leaks."},
        "bookings_edit_estimate": {"lines": labour_lines()},
        "bookings_my_approve_estimate": {"estimate_id": str(uuid.uuid4())},
        "bookings_my_reject_estimate": {"estimate_id": str(uuid.uuid4())},
    }
    if name in bodies:
        return bodies[name]
    method, _ = expected_operations()[name]
    return {} if method != "get" else None


async def call(
    api: httpx.AsyncClient,
    op: dict[str, Any],
    *,
    shop_id: uuid.UUID,
    booking_id: str,
    body: dict[str, Any] | None,
    headers: dict[str, str],
) -> httpx.Response:
    path = op["path"].format(shop_id=shop_id, booking_id=booking_id)
    return await api.request(op["method"].upper(), path, json=body, headers=headers)


async def test_sec02_sec04_every_booking_route_hides_other_tenants_and_needs_a_session(
    desk: Desk, world: World, db: Database
) -> None:
    ours = await drive_booking_to(desk, BookingStatus.ASSIGNED)
    elsewhere = desk.booking_body(shop_id=world.other.id, services=world.other_services)
    stranger = await new_customer(db, full_name="Shop B customer")
    created = await desk.wizard(elsewhere, headers=stranger.headers)
    theirs = created.json()["booking"]["id"]
    found = await bookings_operations(desk.api)
    bilal = bearer(world.advisor.id)
    checked = 0
    for name, op in sorted(found.items()):
        body = body_for(name, world)
        anonymous = await call(
            desk.api, op, shop_id=world.shop_id, booking_id=ours.id, body=body, headers={}
        )
        assert anonymous.headers.get("cache-control") == "no-store", name
        if name == "bookings_create_booking":
            problem(anonymous, 422, "VALIDATION_ERROR")  # anonymous callers may book
            continue
        problem(anonymous, 401, "UNAUTHENTICATED")
        if op["path"].startswith("/api/v1/me/"):
            if "{booking_id}" not in op["path"]:
                continue
            # Shop A's booking, asked for by shop B's customer: the customer family's 404.
            response = await call(
                desk.api,
                op,
                shop_id=world.shop_id,
                booking_id=ours.id,
                body=body,
                headers=stranger.headers,
            )
            assert problem(response, 404, "NOT_FOUND")["detail"] == NOT_FOUND, name
            checked += 1
            continue
        # Shop B's path: Bilal is no member there.
        response = await call(
            desk.api, op, shop_id=world.other.id, booking_id=theirs, body=body, headers=bilal
        )
        assert problem(response, 404, "NOT_FOUND")["detail"] == NOT_FOUND, name
        if "{booking_id}" in op["path"]:
            # Shop B's booking under shop A's path: the booking 404 (SEC-02).
            response = await call(
                desk.api, op, shop_id=world.shop_id, booking_id=theirs, body=body, headers=bilal
            )
            assert problem(response, 404, "NOT_FOUND")["detail"] == NOT_FOUND, name
            assert response.headers.get("cache-control") == "no-store"
        checked += 1
    assert checked == 37  # all 40 but the wizard and the two /me lists without a booking id
    detail = await desk.get(
        world.other_advisor.id, desk.booking_path(theirs, shop_id=world.other.id)
    )
    assert detail["status"] == "PENDING"  # nothing in the sweep touched it

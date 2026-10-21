"""Every surface of a suspended shop (spec 19 §2, §9 "Suspension"; D96).

Public routes treat it as unlisted (404, absent from lists and cities, no booking); every staff
route answers 403 `SHOP_SUSPENDED` to every member, the Owner included, before any role check,
while non-members keep their 404; `/me` flags it; the customer keeps reading their bookings and may
still `cancel`, every other customer action is 403 `SHOP_SUSPENDED`. Reactivation restores it all,
and nothing was deleted or changed in between.
"""

from typing import Any

import httpx

from app.core.database import Database
from app.modules.identity.schemas import UserRecord
from app.shared.enums import BookingStatus
from tests.assertions import assert_problem
from tests.modules.admin.support import ADMIN, REASON, admin_post
from tests.modules.bookings.support import (
    THURSDAY_0900,
    Desk,
    World,
    booking_row,
    drive_booking_to,
    new_customer,
)
from tests.modules.identity.builders import bearer
from tests.modules.shops.builders import make_shop

SUSPENDED_DETAIL = "This shop is suspended. Contact BayFlow support."
SLUG = "lahore-auto-care"


async def suspend(desk: Desk, admin: UserRecord, world: World) -> None:
    await admin_post(desk.api, admin, f"/shops/{world.shop_id}/suspend", {"reason": REASON})


async def reactivate(desk: Desk, admin: UserRecord, world: World) -> None:
    await admin_post(desk.api, admin, f"/shops/{world.shop_id}/reactivate")


async def public_slugs(desk: Desk, **params: Any) -> list[str]:
    response = await desk.api.get("/api/v1/public/shops", params=params)
    assert response.status_code == 200, response.text
    return [item["slug"] for item in response.json()["items"]]


async def test_public_surfaces_treat_a_suspended_shop_as_unlisted(
    desk: Desk, world: World, admin: UserRecord
) -> None:
    assert SLUG in await public_slugs(desk)
    await suspend(desk, admin, world)

    assert SLUG not in await public_slugs(desk)
    assert await public_slugs(desk, q="Lahore") == []
    cities = (await desk.api.get("/api/v1/public/cities")).json()["items"]
    assert cities == ["Karachi"]  # Lahore Auto Care was the only Lahore shop
    assert_problem(await desk.api.get(f"/api/v1/public/shops/{SLUG}"), 404, "NOT_FOUND")
    availability = await desk.api.get(
        f"/api/v1/public/shops/{SLUG}/availability", params={"date": "2026-10-15"}
    )
    assert_problem(availability, 404, "NOT_FOUND")
    anonymous = desk.booking_body()
    anonymous["customer"] = {
        "full_name": "Ahmed",
        "email": "ahmed.suspended@bayflow.test",
        "password": "test-password-1234",
    }
    assert_problem(
        await desk.wizard(anonymous, headers={"X-Real-IP": "2001:db8::51"}), 404, "NOT_FOUND"
    )
    customer = await new_customer(desk.world.db)
    signed_in = await desk.wizard(desk.booking_body(), headers=customer.headers)
    assert_problem(signed_in, 404, "NOT_FOUND")

    await reactivate(desk, admin, world)
    assert SLUG in await public_slugs(desk)
    assert (await desk.api.get(f"/api/v1/public/shops/{SLUG}")).status_code == 200
    restored = await desk.wizard(desk.booking_body(), headers=customer.headers)
    assert restored.status_code == 201, restored.text


async def test_every_member_gets_shop_suspended_before_any_role_check(
    desk: Desk, world: World, admin: UserRecord
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.ASSIGNED)
    await suspend(desk, admin, world)
    owner, advisor, technician = world.owner.id, world.advisor.id, world.technician.id
    refused = [
        ("GET", desk.shop_path(), owner),
        ("PATCH", desk.shop_path(), owner),  # Owner-only route: still 403 SHOP_SUSPENDED
        ("GET", desk.shop_path("/members"), owner),
        ("GET", desk.shop_path("/members"), technician),  # wrong role: suspension first
        ("GET", desk.shop_path("/overview"), owner),  # reporting
        ("GET", desk.shop_path("/parts"), world.parts.id),  # inventory
        ("GET", desk.shop_path("/qc/checklist"), world.qc.id),  # qc
        ("GET", desk.shop_path("/bookings"), advisor),
        ("GET", desk.booking_path(journey.id), technician),
        ("POST", desk.booking_path(journey.id, "/actions/start-inspection"), technician),
        ("POST", desk.booking_path(journey.id, "/actions/cancel"), advisor),
    ]
    bodies = {"GET": None, "PATCH": {"name": "Renamed"}, "POST": {}}
    for method, path, user_id in refused:
        response = await desk.api.request(
            method, path, headers=bearer(user_id), json=bodies[method]
        )
        body = assert_problem(response, 403, "SHOP_SUSPENDED")
        assert body["detail"] == SUSPENDED_DETAIL, (method, path)
    # Non-members keep their 404: the suspension is visible only to the shop's own team.
    outsider = await desk.api.get(desk.shop_path(), headers=bearer(world.other_advisor.id))
    assert_problem(outsider, 404, "NOT_FOUND")
    booking = await booking_row(desk.world.db, journey.id)
    assert booking.status == BookingStatus.ASSIGNED  # nothing moved

    await reactivate(desk, admin, world)
    assert (await desk.api.get(desk.shop_path(), headers=bearer(owner))).status_code == 200
    started = await desk.act(world.technician, journey.id, "start-inspection")
    assert started["status"] == "INSPECTING"


async def test_me_flags_the_suspended_shop(desk: Desk, world: World, admin: UserRecord) -> None:
    def flags(me: dict[str, Any]) -> dict[str, bool]:
        return {item["shop_name"]: item["shop_suspended"] for item in me["memberships"]}

    me = await desk.get(world.owner.id, "/api/v1/me")
    assert flags(me) == {"Lahore Auto Care": False}
    await suspend(desk, admin, world)
    assert flags(await desk.get(world.owner.id, "/api/v1/me")) == {"Lahore Auto Care": True}
    assert flags(await desk.get(world.advisor.id, "/api/v1/me")) == {"Lahore Auto Care": True}
    other = await desk.get(world.other_advisor.id, "/api/v1/me")
    assert flags(other) == {"Clifton Car Clinic": False}
    await reactivate(desk, admin, world)
    assert flags(await desk.get(world.owner.id, "/api/v1/me")) == {"Lahore Auto Care": False}


async def test_the_owner_summary_leaves_a_suspended_shop_out(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    """D99: `GET /me/owner-summary` lists only the Owner's open shops; `/me` keeps the suspended
    membership with `shop_suspended: true`, which is where the web shows the suspension."""
    second = await make_shop(db, owner=world.owner, name="Gulberg Tyre Point")

    async def summary_names() -> list[str]:
        summary = await desk.get(world.owner.id, "/api/v1/me/owner-summary")
        return [item["shop"]["name"] for item in summary["items"]]

    assert await summary_names() == ["Gulberg Tyre Point", "Lahore Auto Care"]
    await suspend(desk, admin, world)
    assert await summary_names() == ["Gulberg Tyre Point"]
    me = await desk.get(world.owner.id, "/api/v1/me")
    assert {item["shop_name"]: item["shop_suspended"] for item in me["memberships"]} == {
        "Gulberg Tyre Point": False,
        "Lahore Auto Care": True,
    }
    await admin_post(desk.api, admin, f"/shops/{second.id}/suspend", {"reason": REASON})
    assert await summary_names() == []
    await reactivate(desk, admin, world)
    assert await summary_names() == ["Lahore Auto Care"]


async def test_customers_keep_reading_and_may_only_cancel(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    awaiting = await drive_booking_to(desk, BookingStatus.AWAITING_CUSTOMER)
    customer = awaiting.customer
    ready = await drive_booking_to(desk, BookingStatus.READY_FOR_PICKUP, customer=customer)
    pending = await drive_booking_to(desk, BookingStatus.PENDING, customer=customer)
    assert "approve-estimate" in (await desk.my_detail(customer, awaiting.id))["allowed_actions"]
    await suspend(desk, admin, world)

    listing = await desk.get(customer.user_id, "/api/v1/me/bookings")
    assert listing["total"] == 3
    for item in listing["items"]:
        assert set(item["allowed_actions"]) <= {"cancel"}
    detail = await desk.my_detail(customer, awaiting.id)
    assert detail["allowed_actions"] == ["cancel"]
    assert (await desk.my_detail(customer, ready.id))["allowed_actions"] == []
    events = await desk.get(customer.user_id, desk.my_path(awaiting.id, "/events"))
    assert events["items"]

    estimate_id = awaiting.booking["estimate_summary"]["estimate_id"]
    approve = await desk.api.post(
        desk.my_path(awaiting.id, "/actions/approve-estimate"),
        headers=customer.headers,
        json={"estimate_id": estimate_id},
    )
    assert assert_problem(approve, 403, "SHOP_SUSPENDED")["detail"] == SUSPENDED_DETAIL
    complete = await desk.api.post(
        desk.my_path(ready.id, "/actions/complete"), headers=customer.headers, json={}
    )
    assert_problem(complete, 403, "SHOP_SUSPENDED")
    cancelled = await desk.my_act(customer, pending.id, "cancel", {"reason": "The shop closed"})
    assert cancelled["status"] == "CANCELLED"  # never stuck at a closed shop
    unchanged = await booking_row(db, awaiting.id)
    assert unchanged.status == BookingStatus.AWAITING_CUSTOMER

    await reactivate(desk, admin, world)
    approved = await desk.my_act(
        customer, awaiting.id, "approve-estimate", {"estimate_id": estimate_id}
    )
    assert approved["status"] == "ESTIMATE_APPROVED"
    done = await desk.my_act(customer, ready.id, "complete")
    assert done["status"] == "COMPLETED"


async def test_suspension_changes_no_tenant_data(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.CONFIRMED, slot=THURSDAY_0900)
    before = await booking_row(db, journey.id)
    team_before = await desk.get(world.owner.id, desk.shop_path("/members"), limit=100)
    await suspend(desk, admin, world)
    await reactivate(desk, admin, world)
    after = await booking_row(db, journey.id)
    assert (after.status, after.version, after.updated_at) == (
        before.status,
        before.version,
        before.updated_at,
    )
    team_after = await desk.get(world.owner.id, desk.shop_path("/members"), limit=100)
    assert team_after == team_before
    shop = await desk.get(world.owner.id, desk.shop_path())
    assert shop["is_listed"] is True
    response = await desk.api.get(f"{ADMIN}/shops/{world.shop_id}", headers=bearer(admin.id))
    assert response.json()["suspension"] is None


async def test_every_route_that_can_answer_403_documents_it(client: httpx.AsyncClient) -> None:
    """The OpenAPI document lists 403 wherever it can now happen: every shop-scoped route
    (`SHOP_SUSPENDED`, D96), every customer action but `cancel` (`SHOP_SUSPENDED`), and every admin
    route (not an admin, or a cross-site request, D98). The routes come from the generated
    document (spec 12 §3.4 "Route enumeration rule")."""
    schema = (await client.get("/openapi.json")).json()
    checked = 0
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            scoped = path.startswith("/api/v1/shops/{shop_id}")
            admin = path.startswith(ADMIN)
            customer_action = path.startswith("/api/v1/me/bookings/{booking_id}/actions/")
            if customer_action and path.endswith("/cancel"):
                assert "403" not in operation["responses"], path  # cancel stays open
                continue
            if not (scoped or admin or customer_action):
                continue
            problem = operation["responses"].get("403", {})
            assert "application/problem+json" in problem.get("content", {}), (method, path)
            checked += 1
    assert checked > 60  # the whole staff API, the admin API and the customer actions

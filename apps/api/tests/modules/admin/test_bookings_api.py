"""Bookings in the admin console: E-72, E-73 (spec 19 §4; D21, D94).

Read-only and cross-tenant: no `allowed_actions`, the customer's contact and the parts summary
always shown, every event of the timeline; E-73 is recorded as `admin.booking_viewed` in the
booking's shop. The staff and customer reads keep their D21 predicate untouched.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.database import Database
from app.modules.identity.schemas import UserRecord
from app.shared.clock import SimulatedClock
from app.shared.enums import BookingStatus
from tests.assertions import assert_problem
from tests.modules.admin.support import ADMIN, admin_get, audit_rows
from tests.modules.bookings.support import (
    FRIDAY_1000,
    THURSDAY_0900,
    Desk,
    World,
    booking_row,
    drive_booking_to,
    next_client_ip,
)
from tests.modules.identity.builders import TEST_PASSWORD, bearer, unique_email
from tests.modules.shops.builders import ShopCtx, make_services, make_shop

SUMMARY_KEYS = {
    "id",
    "reference",
    "shop",
    "status",
    "version",
    "slot_start",
    "slot_end",
    "customer",
    "vehicle",
    "service_names",
    "created_at",
    "updated_at",
}


async def book_at(
    desk: Desk, shop: ShopCtx, services: list[Any], slot: datetime, *, name: str = "Sana"
) -> dict[str, Any]:
    """A booking at any shop by a new customer (the wizard, D32 case B)."""
    body = desk.booking_body(shop_id=shop.id, services=services, slot=slot, registration="ISB-42")
    body["customer"] = {
        "full_name": name,
        "email": unique_email("guest"),
        "password": TEST_PASSWORD,
    }
    response = await desk.wizard(body, headers={"X-Real-IP": next_client_ip()})
    assert response.status_code == 201, response.text
    booking: dict[str, Any] = response.json()["booking"]
    return booking


def refs(page: dict[str, Any]) -> list[str]:
    return [item["reference"] for item in page["items"]]


async def test_e72_lists_every_tenants_bookings_read_only(
    desk: Desk, world: World, admin: UserRecord
) -> None:
    lahore = await drive_booking_to(desk, BookingStatus.CONFIRMED, slot=THURSDAY_0900)
    clifton = await book_at(desk, world.other, world.other_services, FRIDAY_1000)
    page = await admin_get(desk.api, admin, "/bookings")
    assert page["total"] == 2
    assert refs(page) == [clifton["reference"], lahore.reference]  # latest slot first
    for item in page["items"]:
        assert set(item) == SUMMARY_KEYS  # no allowed_actions: read-only
    item = page["items"][1]
    assert item["shop"]["name"] == "Lahore Auto Care"
    assert item["customer"]["email"] == lahore.customer.email
    assert (item["vehicle"]["registration_number"], item["status"]) == ("LEA-1234", "CONFIRMED")
    assert await audit_rows(desk.world.db, action="admin.booking_viewed") == []  # lists are not


async def test_e72_filters_and_sorts(
    desk: Desk, world: World, db: Database, admin: UserRecord, clock: SimulatedClock
) -> None:
    pacific = await make_shop(
        db, name="Pacific Auto", timezone="America/Los_Angeles", city="Los Angeles"
    )
    pacific_services = await make_services(db, pacific, ("Tune-up",))
    thursday = await drive_booking_to(
        desk, BookingStatus.PENDING, slot=THURSDAY_0900, registration="LEA-1234"
    )
    friday = await drive_booking_to(
        desk, BookingStatus.CONFIRMED, slot=FRIDAY_1000, registration="KHI 777", full_name="Bilqis"
    )
    clock.advance(timedelta(minutes=1))  # the newest booking, for `-created_at`
    # Thursday 15 Oct, 17:00 in Los Angeles = Friday 16 Oct, 05:00 in Karachi.
    los_angeles = await book_at(
        desk, pacific, pacific_services, datetime(2026, 10, 16, 0, 0, tzinfo=UTC), name="Lena"
    )

    async def get(**params: Any) -> list[str]:
        return refs(await admin_get(desk.api, admin, "/bookings", **params))

    assert await get(q=thursday.reference) == [thursday.reference]
    assert await get(q=thursday.reference.removeprefix("BF-").lower()) == [thursday.reference]
    assert await get(q="khi777") == [friday.reference]  # plate, normalised
    assert await get(q="bilqis") == [friday.reference]  # customer name
    assert await get(q=thursday.customer.email) == [thursday.reference]  # customer e-mail
    assert await get(shop_id=str(pacific.id)) == [los_angeles["reference"]]
    assert set(await get(status=["PENDING", "CONFIRMED"])) == {
        thursday.reference,
        friday.reference,
        los_angeles["reference"],
    }
    assert await get(status="CONFIRMED") == [friday.reference]
    # Slot dates are read in each shop's own zone (D38).
    assert set(await get(date_from="2026-10-15", date_to="2026-10-15")) == {
        thursday.reference,
        los_angeles["reference"],
    }
    assert await get(date_from="2026-10-16") == [friday.reference]
    assert set(await get(date_to="2026-10-15")) == {thursday.reference, los_angeles["reference"]}
    assert await get(date_from="2026-10-15", shop_id=str(world.shop_id), sort="slot_start") == [
        thursday.reference,
        friday.reference,
    ]
    newest_first = await get(sort="-created_at")
    assert newest_first[0] == los_angeles["reference"]
    inverted = await desk.api.get(
        f"{ADMIN}/bookings",
        headers=bearer(admin.id),
        params={"date_from": "2026-10-16", "date_to": "2026-10-15"},
    )
    body = assert_problem(inverted, 422, "VALIDATION_ERROR")
    assert [(e["field"], e["code"]) for e in body["errors"]] == [("query.date_to", "invalid_range")]
    for bad in ({"status": "LOST"}, {"sort": "-updated_at"}, {"shop_id": "nope"}):
        response = await desk.api.get(f"{ADMIN}/bookings", headers=bearer(admin.id), params=bad)
        assert_problem(response, 422, "VALIDATION_ERROR")


async def test_e73_reads_any_booking_read_only_and_is_recorded(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.PARTS_ORDERED)
    before = await booking_row(db, journey.id)
    detail = await admin_get(desk.api, admin, f"/bookings/{journey.id}")
    assert "allowed_actions" not in detail
    assert detail["shop"]["name"] == "Lahore Auto Care"
    assert detail["customer"]["email"] == journey.customer.email  # contact always shown
    assert detail["parts_summary"] is not None  # stock data shown too
    assert [event["action"] for event in detail["events"]] == [
        "CREATE",
        "CONFIRM",
        "ASSIGN_TECHNICIAN",
        "START_INSPECTION",
        "SUBMIT_ESTIMATE",
        "SEND_ESTIMATE",
        "APPROVE_ESTIMATE",
        "ASSIGN_PARTS_PERSON",
        "ORDER_PARTS",
    ]
    assert detail["last_event"]["action"] == "ORDER_PARTS"
    after = await booking_row(db, journey.id)
    assert (after.version, after.updated_at) == (before.version, before.updated_at)
    (viewed,) = await audit_rows(db, action="admin.booking_viewed")
    assert (viewed.shop_id, viewed.target_type, viewed.target_id, viewed.target_label) == (
        world.shop_id,
        "BOOKING",
        before.id,
        journey.reference,
    )
    assert viewed.summary == (
        f"Areeba Hashmi viewed booking {journey.reference} at Lahore Auto Care."
    )


async def test_admin_reads_never_widen_the_staff_and_customer_predicates(
    desk: Desk, world: World, admin: UserRecord
) -> None:
    journey = await drive_booking_to(desk, BookingStatus.ASSIGNED)
    staff = await desk.detail(world.advisor, journey.id)
    assert "allowed_actions" in staff
    outsider = await desk.api.get(
        desk.booking_path(journey.id, shop_id=world.other.id),
        headers=bearer(world.other_advisor.id),
    )
    assert_problem(outsider, 404, "NOT_FOUND")
    stranger = await desk.api.get(
        desk.booking_path(journey.id), headers=bearer(world.technician2.id)
    )
    assert_problem(stranger, 404, "NOT_FOUND")  # D21: not the assigned technician
    as_customer = await desk.api.get(desk.my_path(journey.id), headers=bearer(admin.id))
    assert_problem(as_customer, 404, "NOT_FOUND")  # the admin is not the booking's customer

"""The read side (spec 03 §3.3, §4.7, §4.8; `modules/bookings.md` §7.10).

BK-17 (customer dashboard), BK-18 (staff filters and pagination), BK-19 / BK-31 (timeline order
with one shared instant), BK-35 (`status_changed_at` ignores operations), API-06
(`allowed_actions` everywhere), the search (`q` by reference, plate and name; `%`/`_` literal),
shop-local date filters, sorts, status counts, `last_event`, `cancelled_by`, my vehicles, and the
422s of malformed query and path parameters.
"""

import itertools
import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.core.database import Database
from app.modules.bookings.models import BookingEvent
from app.shared.clock import SimulatedClock
from app.shared.enums import BookingStatus
from tests.modules.bookings.support import (
    FRIDAY_1000,
    THURSDAY_0900,
    Desk,
    Journey,
    World,
    drive_booking_to,
    field_codes,
    full_checklist,
    labour_lines,
    new_customer,
    problem,
    vehicle,
)
from tests.modules.identity.builders import bearer

pytestmark = pytest.mark.db

S = BookingStatus
ALL_STATUSES = [status.value for status in BookingStatus]


def ids(page: dict[str, Any]) -> list[str]:
    return [item["id"] for item in page["items"]]


# --- BK-18: filters and pagination ----------------------------------------------------------------


async def test_bk18_the_staff_list_filters_by_statuses_and_paginates(
    desk: Desk, world: World
) -> None:
    pending = [(await desk.book()).id for _ in range(3)]
    confirmed = (await drive_booking_to(desk, S.CONFIRMED)).id
    declined = (await drive_booking_to(desk, S.CANCELLED)).id
    bilal = world.advisor.id
    path = desk.shop_path("/bookings")
    everything = await desk.get(bilal, path, limit=100)
    assert everything["total"] == 5
    assert (everything["limit"], everything["offset"]) == (100, 0)
    assert set(ids(await desk.get(bilal, path, status="PENDING"))) == set(pending)
    both = await desk.get(bilal, path, status=["PENDING", "CANCELLED"])
    assert set(ids(both)) == {*pending, declined}
    assert ids(await desk.get(bilal, path, status=["CONFIRMED", "CONFIRMED"])) == [confirmed]
    assert (await desk.get(bilal, path, status="COMPLETED"))["items"] == []
    pages = [await desk.get(bilal, path, limit=2, offset=offset) for offset in (0, 2, 4)]
    assert [len(page["items"]) for page in pages] == [2, 2, 1]
    assert {page["total"] for page in pages} == {5}
    assert [item for page in pages for item in ids(page)] == ids(everything)  # stable order
    beyond = await desk.get(bilal, path, offset=50)
    assert (beyond["items"], beyond["total"]) == ([], 5)
    for params in ({"status": "SHIPPED"}, {"limit": 0}, {"limit": 101}, {"offset": -1}):
        response = await desk.api.get(path, params=params, headers=bearer(bilal))
        body = problem(response, 422, "VALIDATION_ERROR")
        assert any(name.startswith("query.") for name, _ in field_codes(body)), body


async def test_the_default_sort_is_most_recently_updated_first(
    desk: Desk, world: World, clock: SimulatedClock
) -> None:
    first = await desk.book()
    clock.advance(timedelta(minutes=1))
    second = await desk.book()
    clock.advance(timedelta(minutes=1))
    path = desk.shop_path("/bookings")
    assert ids(await desk.get(world.advisor.id, path)) == [second.id, first.id]
    await desk.act(world.advisor, first.id, "confirm")  # touches updated_at
    assert ids(await desk.get(world.advisor.id, path)) == [first.id, second.id]
    assert ids(await desk.get(world.advisor.id, path, sort="updated_at")) == [second.id, first.id]


async def test_every_sort_key_orders_the_list_with_the_id_as_tie_breaker(
    desk: Desk, world: World, clock: SimulatedClock
) -> None:
    late = await desk.book(slot=THURSDAY_0900 + timedelta(hours=8))  # created first, slot last
    clock.advance(timedelta(minutes=1))
    early = await desk.book(slot=THURSDAY_0900)
    clock.advance(timedelta(minutes=1))
    middle = await desk.book(slot=THURSDAY_0900 + timedelta(hours=4))
    clock.advance(timedelta(minutes=1))
    await desk.act(world.advisor, late.id, "confirm")  # the latest status change and update
    bilal = world.advisor.id
    path = desk.shop_path("/bookings")
    expected = {
        "slot_start": [early.id, middle.id, late.id],
        "-slot_start": [late.id, middle.id, early.id],
        "created_at": [late.id, early.id, middle.id],
        "-created_at": [middle.id, early.id, late.id],
        "updated_at": [early.id, middle.id, late.id],
        "-updated_at": [late.id, middle.id, early.id],
        "status_changed_at": [early.id, middle.id, late.id],
        "-status_changed_at": [late.id, middle.id, early.id],
    }
    for sort, order in expected.items():
        assert ids(await desk.get(bilal, path, sort=sort)) == order, sort
    problem(
        await desk.api.get(path, params={"sort": "reference"}, headers=bearer(bilal)),
        422,
        "VALIDATION_ERROR",
    )
    clock.advance(timedelta(minutes=1))
    twins = [await desk.book(slot=FRIDAY_1000) for _ in range(3)]  # one instant, one slot
    tied = [
        item
        for item in ids(await desk.get(bilal, path, sort="slot_start"))
        if item in {twin.id for twin in twins}
    ]
    assert tied == sorted(twin.id for twin in twins)  # tie-breaker: id ascending


# --- Search (q) -----------------------------------------------------------------------------------


async def test_q_matches_the_reference_the_plate_or_the_customer_name(
    desk: Desk, world: World
) -> None:
    ahmed = await desk.book(full_name="Ahmed Raza", registration="LEA-1234")
    sana = await desk.book(full_name="Sana Malik", registration="KHI 9876")
    bilal = world.advisor.id
    path = desk.shop_path("/bookings")

    async def found(q: str) -> set[str]:
        return set(ids(await desk.get(bilal, path, q=q, limit=100)))

    code = ahmed.reference.removeprefix("BF-")
    assert await found(ahmed.reference) == {ahmed.id}
    assert await found(ahmed.reference.lower()) == {ahmed.id}
    assert await found(code) == {ahmed.id}
    assert await found(code[1:4].lower()) >= {ahmed.id}
    for plate in ("LEA-1234", "lea 1234", "lea1234", " 1234 ", "a-12"):
        assert await found(plate) == {ahmed.id}, plate
    assert await found("khi-98") == {sana.id}
    assert await found("ahmed") == {ahmed.id}
    assert await found("SANA MAL") == {sana.id}
    assert await found("  ") == {ahmed.id, sana.id}  # blank = no search
    for nothing in ("%", "_", "nobody", "BF-ZZZZZZ", "\\"):
        assert await found(nothing) == set(), nothing
    assert await found("a" * 100) == set()
    too_long = await desk.api.get(path, params={"q": "a" * 101}, headers=bearer(bilal))
    assert ("query.q", "string_too_long") in field_codes(problem(too_long, 422, "VALIDATION_ERROR"))
    nul = await desk.api.get(path, params={"q": "LEA\x001234"}, headers=bearer(bilal))
    problem(nul, 422, "VALIDATION_ERROR")  # text PostgreSQL cannot hold: 422, never 500


async def test_q_is_anded_with_visibility_and_the_other_filters(desk: Desk, world: World) -> None:
    mine = await drive_booking_to(desk, S.ASSIGNED, full_name="Ahmed Raza")
    theirs = await drive_booking_to(desk, S.CONFIRMED, full_name="Ahmed Khan")
    path = desk.shop_path("/bookings")
    assert set(ids(await desk.get(world.advisor.id, path, q="ahmed"))) == {mine.id, theirs.id}
    assert ids(await desk.get(world.technician.id, path, q="ahmed")) == [mine.id]
    assert ids(await desk.get(world.advisor.id, path, q="ahmed", status="CONFIRMED")) == [theirs.id]


# --- Shop-local dates -----------------------------------------------------------------------------


async def test_date_filters_are_inclusive_shop_local_days(desk: Desk, world: World) -> None:
    thursday_last = await desk.book(slot=THURSDAY_0900 + timedelta(hours=8))  # 17:00 local
    friday = await desk.book(slot=FRIDAY_1000)
    saturday = await desk.book(slot=THURSDAY_0900 + timedelta(days=2))
    next_thursday = await desk.book(slot=THURSDAY_0900 + timedelta(weeks=1))
    bilal = world.advisor.id
    path = desk.shop_path("/bookings")

    async def between(**dates: str) -> set[str]:
        return set(ids(await desk.get(bilal, path, limit=100, **dates)))

    everything = {thursday_last.id, friday.id, saturday.id, next_thursday.id}
    assert await between(date_from="2026-10-16") == {friday.id, saturday.id, next_thursday.id}
    assert await between(date_to="2026-10-15") == {thursday_last.id}  # 12:00Z, same local day
    assert await between(date_from="2026-10-16", date_to="2026-10-16") == {friday.id}
    assert await between(date_from="2026-10-18", date_to="2026-10-21") == set()
    assert await between(date_from="0001-01-01", date_to="9999-12-31") == everything
    assert await between(date_from="9999-12-31") == set()
    assert await between(date_to="0001-01-01") == set()
    reversed_range = await desk.api.get(
        path, params={"date_from": "2026-10-17", "date_to": "2026-10-16"}, headers=bearer(bilal)
    )
    body = problem(reversed_range, 422, "VALIDATION_ERROR")
    assert field_codes(body) == [("query.date_to", "invalid_range")]
    for bad in ("2026-13-01", "2026-10-16T00:00:00", "16-10-2026", "2026-02-30", ""):
        response = await desk.api.get(path, params={"date_from": bad}, headers=bearer(bilal))
        problem(response, 422, "VALIDATION_ERROR")


# --- Assignee filters -----------------------------------------------------------------------------


async def test_assignee_filters_narrow_the_advisors_list(desk: Desk, world: World) -> None:
    imran_job = await drive_booking_to(desk, S.PARTS_PENDING)  # Imran, Usman
    hamza_job = await drive_booking_to(desk, S.ASSIGNED)
    reassign = {"technician_user_id": str(world.technician2.id)}
    await desk.act(world.advisor, hamza_job.id, "reassign-technician", reassign)
    unassigned = await desk.book()
    bilal = world.advisor.id
    path = desk.shop_path("/bookings")
    assert ids(await desk.get(bilal, path, technician_user_id=str(world.technician.id))) == [
        imran_job.id
    ]
    assert ids(await desk.get(bilal, path, technician_user_id=str(world.technician2.id))) == [
        hamza_job.id
    ]
    assert ids(await desk.get(bilal, path, parts_person_user_id=str(world.parts.id))) == [
        imran_job.id
    ]
    assert ids(await desk.get(bilal, path, parts_person_user_id=str(world.parts2.id))) == []
    assert ids(await desk.get(bilal, path, technician_user_id=str(uuid.uuid4()))) == []
    assert unassigned.id in ids(await desk.get(bilal, path))
    response = await desk.api.get(
        path, params={"technician_user_id": "imran"}, headers=bearer(bilal)
    )
    problem(response, 422, "VALIDATION_ERROR")


# --- Status counts --------------------------------------------------------------------------------


async def test_status_counts_list_all_17_statuses_in_glossary_order(
    desk: Desk, world: World
) -> None:
    await desk.book()
    await desk.book()
    await drive_booking_to(desk, S.INSPECTING)
    await drive_booking_to(desk, S.CANCELLED)
    counts = await desk.get(world.owner.id, desk.shop_path("/bookings/status-counts"))
    assert [item["status"] for item in counts["items"]] == ALL_STATUSES
    by_status = {item["status"]: item["count"] for item in counts["items"]}
    assert by_status == dict.fromkeys(ALL_STATUSES, 0) | {
        "PENDING": 2,
        "INSPECTING": 1,
        "CANCELLED": 1,
    }
    assert counts["total"] == 4
    technician = await desk.get(world.technician.id, desk.shop_path("/bookings/status-counts"))
    assert technician["total"] == 1
    assert {item["status"]: item["count"] for item in technician["items"]}["INSPECTING"] == 1
    other = await desk.get(
        world.other_advisor.id, desk.shop_path("/bookings/status-counts", shop_id=world.other.id)
    )
    assert other["total"] == 0
    assert len(other["items"]) == 17


# --- BK-19 / BK-31: the timeline ------------------------------------------------------------------


async def test_bk19_bk31_the_timeline_follows_insert_order_with_one_shared_instant(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.COMPLETED)  # the frozen clock: one created_at
    staff = (await desk.get(world.advisor.id, desk.booking_path(journey.id, "/events")))["items"]
    assert [event["action"] for event in staff] == [
        "CREATE",
        "CONFIRM",
        "ASSIGN_TECHNICIAN",
        "START_INSPECTION",
        "SUBMIT_ESTIMATE",
        "SEND_ESTIMATE",
        "APPROVE_ESTIMATE",
        "ASSIGN_PARTS_PERSON",
        "ORDER_PARTS",
        "RECEIVE_PARTS",
        "ALLOCATE_PARTS",
        "SEND_TO_QC",
        "PICK_QC",
        "PASS_QC",
        "COMPLETE",
    ]
    assert len({event["created_at"] for event in staff}) == 1
    assert all(event["created_at"].endswith("Z") for event in staff)
    for previous, event in itertools.pairwise(staff):
        assert event["from_status"] == previous["to_status"]
    for event in staff:
        assert set(event) == {
            "id",
            "action",
            "from_status",
            "to_status",
            "actor",
            "actor_role",
            "note",
            "metadata",
            "created_at",
        }  # `seq` is never exposed
    roles = [(event["action"], event["actor_role"], event["actor"]["full_name"]) for event in staff]
    assert roles[0] == ("CREATE", "CUSTOMER", "Ahmed")
    assert roles[1] == ("CONFIRM", "SERVICE_ADVISOR", "Bilal")
    assert roles[9] == ("RECEIVE_PARTS", "PARTS_PERSON", "Usman")
    assert roles[13] == ("PASS_QC", "QC_INSPECTOR", "Sara")
    async with db.sessionmaker() as session:
        rows = (
            await session.execute(
                select(BookingEvent.id, BookingEvent.seq)
                .where(BookingEvent.booking_id == uuid.UUID(journey.id))
                .order_by(BookingEvent.seq)
            )
        ).all()
    assert [str(row.id) for row in rows] == [event["id"] for event in staff]
    assert [row.seq for row in rows] == sorted({row.seq for row in rows})  # strictly increasing
    customer = (await desk.get(journey.customer.user_id, desk.my_path(journey.id, "/events")))[
        "items"
    ]
    assert [event["id"] for event in customer] == [event["id"] for event in staff]


# --- BK-35: status_changed_at ignores operations --------------------------------------------------


async def test_bk35_status_changed_at_ignores_operations_and_draft_saves(  # noqa: PLR0915
    desk: Desk, world: World, clock: SimulatedClock
) -> None:
    journey = await drive_booking_to(desk, S.INSPECTING, labour_only=True)

    async def changed_at() -> str:
        staff = await desk.detail(world.advisor, journey.id)
        customer = await desk.my_detail(journey.customer, journey.id)
        listed = await desk.get(world.advisor.id, desk.shop_path("/bookings"))
        (item,) = listed["items"]
        mine = await desk.get(journey.customer.user_id, "/api/v1/me/bookings")
        (my_item,) = mine["items"]
        values = {
            staff["status_changed_at"],
            customer["status_changed_at"],
            item["status_changed_at"],
            my_item["status_changed_at"],
        }
        assert len(values) == 1, values
        return str(staff["status_changed_at"])

    inspecting_since = await changed_at()
    clock.advance(timedelta(minutes=1))
    edit = await desk.edit(world.technician, journey.id, labour_lines(), inspection_notes="Worn")
    assert edit["created_new_version"] is False
    assert await changed_at() == inspecting_since  # an in-place draft save
    clock.advance(timedelta(minutes=1))
    await desk.act(world.technician, journey.id, "submit-estimate")
    review_since = await changed_at()
    assert review_since > inspecting_since
    clock.advance(timedelta(minutes=1))
    edit = await desk.edit(world.advisor, journey.id, labour_lines("2600"))
    assert edit["created_new_version"] is True  # EDIT_ESTIMATE: an event, same status
    assert await changed_at() == review_since
    clock.advance(timedelta(minutes=1))
    await desk.act(world.advisor, journey.id, "send-estimate")
    clock.advance(timedelta(minutes=1))
    estimate_id = (await desk.my_detail(journey.customer, journey.id))["estimate"]["id"]
    await desk.my_act(
        journey.customer, journey.id, "approve-estimate", {"estimate_id": estimate_id}
    )
    clock.advance(timedelta(minutes=1))
    body = {"parts_person_user_id": str(world.parts.id)}
    await desk.act(world.advisor, journey.id, "assign-parts-person", body)
    clock.advance(timedelta(minutes=1))
    await desk.act(world.parts, journey.id, "mark-parts-ready")  # zero parts (D31)
    clock.advance(timedelta(minutes=1))
    await desk.act(world.parts, journey.id, "allocate-parts")
    repair_since = await changed_at()
    clock.advance(timedelta(minutes=1))
    started = await desk.act(world.technician, journey.id, "start-repair")
    assert started["repair_started_at"] == started["updated_at"] != repair_since
    reassign = {"technician_user_id": str(world.technician2.id)}
    await desk.act(world.advisor, journey.id, "reassign-technician", reassign)
    assert await changed_at() == repair_since
    clock.advance(timedelta(minutes=1))
    await desk.act(world.technician2, journey.id, "send-to-qc")
    await desk.act(world.qc, journey.id, "pick-qc")
    clock.advance(timedelta(minutes=1))
    passed = await desk.act(world.qc, journey.id, "pass-qc", {"checklist": full_checklist()})
    ready_since = passed["status_changed_at"]
    clock.advance(timedelta(minutes=1))
    notified = await desk.act(world.advisor, journey.id, "notify-ready")
    assert notified["ready_notified_at"] == notified["updated_at"]
    assert notified["status_changed_at"] == ready_since == await changed_at()


# --- BK-17, API-06: the customer dashboard and allowed_actions everywhere -------------------------


async def test_bk17_the_customer_dashboard_lists_own_bookings_at_every_shop(
    desk: Desk, world: World, db: Database, clock: SimulatedClock
) -> None:
    customer = await new_customer(db)
    done = await drive_booking_to(desk, S.COMPLETED, customer=customer, slot=THURSDAY_0900)
    clock.advance(timedelta(minutes=1))
    awaiting = await drive_booking_to(
        desk, S.AWAITING_CUSTOMER, customer=customer, slot=THURSDAY_0900 + timedelta(weeks=1)
    )
    clock.advance(timedelta(minutes=1))
    cancelled = await drive_booking_to(
        desk, S.CANCELLED, customer=customer, slot=THURSDAY_0900 + timedelta(days=1)
    )
    clock.advance(timedelta(minutes=1))
    body = desk.booking_body(
        shop_id=world.other.id, services=world.other_services, slot=FRIDAY_1000 + timedelta(days=1)
    )
    elsewhere = (await desk.wizard(body, headers=customer.headers)).json()["booking"]["id"]
    await drive_booking_to(desk, S.CONFIRMED)  # someone else's booking
    path = "/api/v1/me/bookings"
    me = customer.user_id
    everything = await desk.get(me, path)
    by_slot_descending = [awaiting.id, elsewhere, cancelled.id, done.id]
    assert ids(everything) == by_slot_descending
    assert ids(await desk.get(me, path, active="true")) == [elsewhere, awaiting.id]
    assert ids(await desk.get(me, path, active="false")) == [cancelled.id, done.id]
    assert ids(await desk.get(me, path, sort="slot_start")) == by_slot_descending[::-1]
    assert ids(await desk.get(me, path, sort="-updated_at")) == [
        elsewhere,
        cancelled.id,
        awaiting.id,
        done.id,
    ]
    assert ids(await desk.get(me, path, limit=1, offset=1)) == [elsewhere]
    problem(
        await desk.api.get(path, params={"sort": "created_at"}, headers=customer.headers),
        422,
        "VALIDATION_ERROR",
    )
    problem(
        await desk.api.get(path, params={"active": "maybe"}, headers=customer.headers),
        422,
        "VALIDATION_ERROR",
    )
    items = {item["id"]: item for item in everything["items"]}
    assert items[awaiting.id]["allowed_actions"] == [
        "approve-estimate",
        "reject-estimate",
        "cancel",
    ]
    assert items[awaiting.id]["estimate_summary"]["status"] == "SENT"
    assert items[done.id]["allowed_actions"] == []
    assert items[cancelled.id]["allowed_actions"] == []
    assert items[elsewhere]["allowed_actions"] == ["cancel"]
    assert items[elsewhere]["estimate_summary"] is None
    assert items[elsewhere]["shop"]["name"] == "Clifton Car Clinic"
    assert set(items[elsewhere]["shop"]) == {"id", "slug", "name", "city", "phone", "timezone"}
    assert items[elsewhere]["service_names"] == ["Brake check"]
    assert items[done.id]["vehicle"] == {
        "registration_number": "LEA-1234",
        "make": "Honda",
        "model": "Civic",
        "year": 2016,
    }
    assert "technician" not in items[done.id]
    detail = await desk.my_detail(customer, elsewhere)
    assert detail["shop"]["address"] == "Plot 12, Main Boulevard, Gulberg III"


async def test_api06_every_booking_response_carries_allowed_actions(
    desk: Desk, world: World
) -> None:
    journey = await desk.book()
    assert journey.booking["allowed_actions"] == ["cancel"]  # the wizard's 201
    confirmed = await desk.act(world.advisor, journey.id, "confirm")
    assert confirmed["allowed_actions"] == ["assign-technician", "cancel"]
    staff_item = (await desk.get(world.advisor.id, desk.shop_path("/bookings")))["items"][0]
    assert staff_item["allowed_actions"] == confirmed["allowed_actions"]
    technician_view = await drive_booking_to(desk, S.ASSIGNED)
    assert (await desk.detail(world.technician, technician_view.id))["allowed_actions"] == [
        "start-inspection"
    ]
    assert (await desk.detail(world.owner, technician_view.id))["allowed_actions"] == [
        "cancel",
        "reassign-technician",
    ]
    cancelled = await desk.my_act(journey.customer, journey.id, "cancel")
    assert cancelled["allowed_actions"] == []
    assert (await desk.detail(world.advisor, journey.id))["allowed_actions"] == []
    customer_item = (await desk.get(journey.customer.user_id, "/api/v1/me/bookings"))["items"][0]
    assert customer_item["allowed_actions"] == []


# --- last_event, cancelled_by, the detail's own fields --------------------------------------------


async def test_the_staff_detail_shows_who_cancelled_and_the_last_event(
    desk: Desk, world: World
) -> None:
    by_customer = await drive_booking_to(desk, S.CONFIRMED)
    await desk.my_act(by_customer.customer, by_customer.id, "cancel", {"reason": "Car sold"})
    detail = await desk.detail(world.advisor, by_customer.id)
    assert detail["cancelled_by"] == {
        "user_id": str(by_customer.customer.user_id),
        "full_name": "Ahmed",
    }
    assert detail["cancel_reason"] == "Car sold"
    assert detail["cancelled_at"] == detail["updated_at"]
    last = detail["last_event"]
    assert (last["action"], last["actor_role"], last["note"], last["metadata"]) == (
        "CANCEL",
        "CUSTOMER",
        "Car sold",
        {"released": []},
    )
    assert last["actor"]["user_id"] == str(by_customer.customer.user_id)
    mine = await desk.my_detail(by_customer.customer, by_customer.id)
    assert (mine["cancelled_by_customer"], mine["cancel_reason"]) == (True, "Car sold")
    by_staff = await drive_booking_to(desk, S.CANCELLED)  # declined by Bilal
    detail = await desk.detail(world.owner, by_staff.id)
    assert detail["cancelled_by"] == {"user_id": str(world.advisor.id), "full_name": "Bilal"}
    assert detail["last_event"]["action"] == "DECLINE"
    open_booking = await desk.book()
    detail = await desk.detail(world.advisor, open_booking.id)
    assert (detail["cancelled_by"], detail["cancelled_at"], detail["cancel_reason"]) == (
        None,
        None,
        None,
    )
    assert (await desk.my_detail(open_booking.customer, open_booking.id))[
        "cancelled_by_customer"
    ] is None


async def test_the_staff_detail_carries_the_booking_snapshot(desk: Desk, world: World) -> None:
    journey = await desk.book(
        customer_notes="Engine light on since Monday",
        vehicle=vehicle("LEA-1234", mileage_km=84000, color="Silver"),
    )
    detail = await desk.detail(world.advisor, journey.id)
    assert detail["customer_notes"] == "Engine light on since Monday"
    assert detail["mileage_km"] == 84000
    assert [service["name"] for service in detail["services"]] == [
        "Check engine light",
        "Oil change",
    ]
    assert {service["base_price"] for service in detail["services"]} == {"2000.00"}
    assert detail["vehicle"]["registration_number"] == "LEA-1234"
    assert (detail["vehicle"]["mileage_km"], detail["vehicle"]["color"]) == (84000, "Silver")
    assert (detail["qc_round"], detail["open_qc_issues_count"]) == (0, 0)
    assert (detail["technician"], detail["parts_person"], detail["qc_inspector"]) == (
        None,
        None,
        None,
    )
    assert (detail["estimate_summary"], detail["parts_summary"]) == (None, None)
    assert detail["inspection_notes"] is None
    assert detail["version"] == 1
    assert detail["slot_end"] > detail["slot_start"]
    for field in ("slot_start", "slot_end", "created_at", "updated_at", "status_changed_at"):
        assert detail[field].endswith("Z"), field


# --- My vehicles (P1) -----------------------------------------------------------------------------


async def test_my_vehicles_lists_the_callers_cars_most_recently_updated_first(
    desk: Desk, world: World, db: Database, clock: SimulatedClock
) -> None:
    customer = await new_customer(db)
    await desk.book(customer, registration="LEA-1234")
    clock.advance(timedelta(minutes=1))
    await desk.book(customer, registration="KHI-5678")
    clock.advance(timedelta(minutes=1))
    await desk.book(customer, registration="lea 1234")  # the same car (D35)
    stranger = await new_customer(db, full_name="Zainab")
    await desk.book(stranger, registration="LEA-1234")  # the same plate, another owner
    cars = (await desk.get(customer.user_id, "/api/v1/me/vehicles"))["items"]
    assert [car["registration_number"] for car in cars] == ["lea 1234", "KHI-5678"]
    assert set(cars[0]) == {
        "id",
        "registration_number",
        "make",
        "model",
        "year",
        "color",
        "mileage_km",
        "created_at",
        "updated_at",
    }
    assert cars[0]["updated_at"] > cars[0]["created_at"]
    theirs = (await desk.get(stranger.user_id, "/api/v1/me/vehicles"))["items"]
    assert len(theirs) == 1
    assert theirs[0]["id"] not in {car["id"] for car in cars}
    response = await desk.api.get("/api/v1/me/vehicles")
    problem(response, 401, "UNAUTHENTICATED")


# --- Malformed parameters and unauthenticated callers ---------------------------------------------


async def test_malformed_ids_are_422_and_missing_sessions_401(desk: Desk, world: World) -> None:
    journey: Journey = await desk.book()
    headers = bearer(world.advisor.id)
    for path in (
        desk.booking_path("not-a-uuid"),
        desk.booking_path("not-a-uuid", "/events"),
        desk.booking_path("not-a-uuid", "/actions/confirm"),
        desk.my_path("not-a-uuid"),
    ):
        method = "POST" if path.endswith("confirm") else "GET"
        response = await desk.api.request(method, path, json={}, headers=headers)
        problem(response, 422, "VALIDATION_ERROR")
    for path in (
        desk.shop_path("/bookings"),
        desk.booking_path(journey.id),
        desk.shop_path("/bookings/status-counts"),
        "/api/v1/me/bookings",
        desk.my_path(journey.id),
    ):
        problem(await desk.api.get(path), 401, "UNAUTHENTICATED")
    customer_headers = journey.customer.headers  # not a member of the shop: 404, never 403
    for path in (desk.shop_path("/bookings"), desk.booking_path(journey.id)):
        problem(await desk.api.get(path, headers=customer_headers), 404, "NOT_FOUND")

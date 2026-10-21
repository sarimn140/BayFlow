"""Who sees what (D21; spec 04 RBAC C and §C; `modules/bookings.md` §7.5, §9).

SEC-01, SEC-08…SEC-12, SM-05, SM-17, BK-36, BK-37, BK-40 (DB half: the SQL predicate of lists and
counts and the item routes agree with `can_view` for every role, status and assignment), QC-07,
QC-16, identical 404 bodies, and the audience rules: the customer's contact data only for the
Owner and SAs, no stock data for QC inspectors, and no staff names, internal notes, metadata or
unsent estimate versions for customers.
"""

import itertools
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.core.database import Database
from app.modules.bookings.domain.references import new_booking_reference
from app.modules.bookings.domain.visibility import can_view
from app.modules.bookings.models import Booking, Vehicle
from app.modules.qc.models import QcInspection
from app.shared.clock import SimulatedClock
from app.shared.enums import BookingStatus, MembershipRole, QcResult
from tests.modules.bookings.conftest import InvariantCheck
from tests.modules.bookings.support import (
    FRIDAY_1000,
    Desk,
    World,
    drive_booking_to,
    full_checklist,
    labour_lines,
    new_customer,
    problem,
)
from tests.modules.identity.builders import bearer
from tests.modules.shops.builders import add_member

pytestmark = pytest.mark.db

S = BookingStatus
NOT_FOUND_DETAIL = "The requested resource was not found."
BOOKING_READS = ("", "/events", "/estimates", "/parts", "/qc-inspections")


def comparable(body: dict[str, Any]) -> dict[str, Any]:
    """A problem body without `instance` (the request path, which differs by design)."""
    return {key: value for key, value in body.items() if key != "instance"}


def assert_identical_404s(responses: list[httpx.Response]) -> None:
    bodies = [comparable(problem(response, 404, "NOT_FOUND")) for response in responses]
    assert bodies[0]["detail"] == NOT_FOUND_DETAIL
    assert all(body == bodies[0] for body in bodies), bodies


async def every_staff_route(
    desk: Desk, user_id: uuid.UUID, booking_id: str
) -> list[httpx.Response]:
    """Every staff booking route a caller could try on one booking."""
    headers = bearer(user_id)
    responses = [
        await desk.api.get(desk.booking_path(booking_id, path), headers=headers)
        for path in BOOKING_READS
    ]
    responses.append(
        await desk.api.put(
            desk.booking_path(booking_id, "/estimate"),
            json={"lines": labour_lines()},
            headers=headers,
        )
    )
    responses.extend(
        [
            await desk.act_raw(user_id, booking_id, slug)
            for slug in (
                "confirm",
                "start-inspection",
                "submit-estimate",
                "start-repair",
                "send-to-qc",
                "order-parts",
                "mark-parts-ready",
                "allocate-parts",
                "pick-qc",
            )
        ]
    )
    return responses


# --- SEC-01 / SM-05: other tenants ----------------------------------------------------------------


async def test_sec01_sm05_shop_b_bookings_are_identical_404s_for_shop_a_staff(
    desk: Desk, world: World, db: Database
) -> None:
    body = desk.booking_body(shop_id=world.other.id, services=world.other_services)
    customer = await new_customer(db)
    created = await desk.wizard(body, headers=customer.headers)
    assert created.status_code == 201, created.text
    shop_b_booking = created.json()["booking"]["id"]
    imran_job = await drive_booking_to(desk, S.INSPECTING)
    bilal = world.advisor.id
    responses = await every_staff_route(desk, bilal, shop_b_booking)  # under shop A's path
    responses += [
        await desk.api.get(desk.booking_path(str(uuid.uuid4())), headers=bearer(bilal)),
        await desk.api.get(
            desk.shop_path("/bookings", shop_id=world.other.id), headers=bearer(bilal)
        ),
        await desk.api.get(
            desk.booking_path(shop_b_booking, shop_id=world.other.id), headers=bearer(bilal)
        ),
        # A booking of shop A that this technician may not see: the very same body (D21).
        await desk.api.get(desk.booking_path(imran_job.id), headers=bearer(world.technician2.id)),
    ]
    assert_identical_404s(responses)
    listing = await desk.get(bilal, desk.shop_path("/bookings"))
    assert [item["id"] for item in listing["items"]] == [imran_job.id]
    other_listing = await desk.get(
        world.other_advisor.id, desk.shop_path("/bookings", shop_id=world.other.id)
    )
    assert [item["id"] for item in other_listing["items"]] == [shop_b_booking]
    counts = await desk.get(bilal, desk.shop_path("/bookings/status-counts"))
    assert counts["total"] == 1


# --- SEC-08, SEC-09: technicians and parts persons see their own jobs only ------------------------


async def test_sec08_a_technician_never_sees_another_technicians_booking(
    desk: Desk, world: World
) -> None:
    imran_job = await drive_booking_to(desk, S.INSPECTING)
    hamza = world.technician2.id
    responses = await every_staff_route(desk, hamza, imran_job.id)
    assert_identical_404s(responses)  # 404, never NOT_ASSIGNED (spec 04)
    assert (await desk.get(hamza, desk.shop_path("/bookings")))["total"] == 0
    assert (await desk.get(hamza, desk.shop_path("/bookings/status-counts")))["total"] == 0
    narrowed = await desk.get(
        hamza, desk.shop_path("/bookings"), technician_user_id=str(world.technician.id)
    )
    assert narrowed["total"] == 0  # a filter narrows, never widens
    mine = await desk.get(world.technician.id, desk.shop_path("/bookings"))
    assert [item["id"] for item in mine["items"]] == [imran_job.id]
    detail = await desk.detail(world.technician, imran_job.id)
    assert detail["allowed_actions"] == ["edit-estimate", "submit-estimate"]


async def test_sec09_a_parts_person_never_sees_another_parts_persons_booking(
    desk: Desk, world: World
) -> None:
    usman_job = await drive_booking_to(desk, S.PARTS_ORDERED)
    kashif = world.parts2.id
    assert_identical_404s(await every_staff_route(desk, kashif, usman_job.id))
    assert (await desk.get(kashif, desk.shop_path("/bookings")))["total"] == 0
    narrowed = await desk.get(
        kashif, desk.shop_path("/bookings"), parts_person_user_id=str(world.parts.id)
    )
    assert narrowed["total"] == 0
    mine = await desk.get(world.parts.id, desk.shop_path("/bookings"))
    assert [item["id"] for item in mine["items"]] == [usman_job.id]
    before_parts = await drive_booking_to(desk, S.ESTIMATE_APPROVED)
    await desk.get(world.parts.id, desk.booking_path(before_parts.id), expect=404)


# --- SEC-10, QC-04, QC-07, QC-16: the QC queue ----------------------------------------------------


async def test_sec10_qc07_qc16_qc_inspectors_see_the_queue_and_what_they_inspected(
    desk: Desk, world: World, db: Database, clock: SimulatedClock
) -> None:
    waiting = await drive_booking_to(desk, S.QC_PENDING)
    clock.advance(timedelta(minutes=5))
    picked = await drive_booking_to(desk, S.QC_IN_PROGRESS)  # Sara picked it
    clock.advance(timedelta(minutes=5))
    passed = await drive_booking_to(desk, S.READY_FOR_PICKUP)  # Sara picked and passed it
    in_repair = await drive_booking_to(desk, S.IN_REPAIR)
    queue = {"status": ["QC_PENDING", "QC_IN_PROGRESS"], "sort": "status_changed_at"}
    for inspector in (world.qc, world.qc2):
        page = await desk.get(inspector.id, desk.shop_path("/bookings"), **queue)
        assert [item["id"] for item in page["items"]] == [waiting.id, picked.id]
    sara = await desk.get(world.qc.id, desk.shop_path("/bookings"))
    hina = await desk.get(world.qc2.id, desk.shop_path("/bookings"))
    assert {item["id"] for item in sara["items"]} == {waiting.id, picked.id, passed.id}
    assert {item["id"] for item in hina["items"]} == {waiting.id, picked.id}
    # QC-16: after the job left QC, the inspector who inspected it still sees it and its history.
    history = await desk.get(world.qc.id, desk.booking_path(passed.id, "/qc-inspections"))
    assert [item["result"] for item in history["items"]] == ["PASS"]
    assert (await desk.detail(world.qc, passed.id))["status"] == "READY_FOR_PICKUP"
    assert_identical_404s(
        [
            *[
                await desk.api.get(desk.booking_path(passed.id, path), headers=bearer(world.qc2.id))
                for path in BOOKING_READS
            ],
            await desk.api.get(desk.booking_path(in_repair.id), headers=bearer(world.qc.id)),
        ]
    )
    # QC-04: only the picker passes or fails.
    not_picker = world.qc2.id
    pass_body = {"checklist": full_checklist()}
    problem(await desk.act_raw(not_picker, picked.id, "pass-qc", pass_body), 403, "NOT_ASSIGNED")
    fail_body = {"issue_title": "Loose clamp", "issue_description": "Hose clamp is loose."}
    problem(await desk.act_raw(not_picker, picked.id, "fail-qc", fail_body), 403, "NOT_ASSIGNED")
    # QC-07: another shop's QC inspector sees none of it.
    stranger = await add_member(db, world.other, MembershipRole.QC_INSPECTOR, full_name="Nida")
    their_queue = await desk.get(
        stranger.id, desk.shop_path("/bookings", shop_id=world.other.id), **queue
    )
    assert their_queue["total"] == 0
    assert_identical_404s(
        [
            await desk.api.get(desk.booking_path(waiting.id), headers=bearer(stranger.id)),
            await desk.api.get(
                desk.booking_path(waiting.id, shop_id=world.other.id), headers=bearer(stranger.id)
            ),
            await desk.act_raw(stranger.id, waiting.id, "pick-qc", shop_id=world.other.id),
        ]
    )


# --- SEC-11, SM-17, SEC-12, BK-36: customers ------------------------------------------------------


async def test_sec11_sm17_a_customer_never_reaches_another_customers_booking(
    desk: Desk, world: World, db: Database
) -> None:
    journey = await drive_booking_to(desk, S.AWAITING_CUSTOMER)
    zainab = await new_customer(db, full_name="Zainab")
    decision = {"estimate_id": journey.booking["estimate_summary"]["estimate_id"]}
    attempts: list[tuple[str, str, dict[str, Any] | None]] = [
        ("GET", desk.my_path(journey.id), None),
        ("GET", desk.my_path(journey.id, "/events"), None),
        ("GET", desk.my_path(journey.id, "/estimates"), None),
        ("GET", desk.my_path(str(uuid.uuid4())), None),
        ("POST", desk.my_path(journey.id, "/actions/approve-estimate"), decision),
        ("POST", desk.my_path(journey.id, "/actions/reject-estimate"), decision),
        ("POST", desk.my_path(journey.id, "/actions/complete"), {}),
        ("POST", desk.my_path(journey.id, "/actions/cancel"), {}),
    ]
    responses = [
        await desk.api.request(method, path, json=body, headers=zainab.headers)
        for method, path, body in attempts
    ]
    # Staff of that very shop are customers on /me routes: not their booking → the same 404.
    responses.append(await desk.api.get(desk.my_path(journey.id), headers=bearer(world.advisor.id)))
    assert_identical_404s(responses)
    assert (await desk.get(zainab.user_id, "/api/v1/me/bookings"))["total"] == 0
    assert (await desk.get(zainab.user_id, "/api/v1/me/vehicles"))["items"] == []
    owner_view = await desk.my_detail(journey.customer, journey.id)
    assert (owner_view["status"], owner_view["version"]) == ("AWAITING_CUSTOMER", 6)


async def test_sec12_bk36_customers_see_no_drafts_notes_staff_or_metadata(
    desk: Desk, world: World
) -> None:
    journey = await desk.book()
    customer = journey.customer
    await desk.act(world.advisor, journey.id, "confirm", {"note": "VIP - waive the diagnostics"})
    body = {"technician_user_id": str(world.technician.id)}
    await desk.act(world.advisor, journey.id, "assign-technician", body)
    await desk.act(world.technician, journey.id, "start-inspection")
    await desk.edit(world.technician, journey.id, labour_lines(), inspection_notes="Coil is weak")
    assert (await desk.my_detail(customer, journey.id))["estimate"] is None  # DRAFT
    await desk.act(world.technician, journey.id, "submit-estimate")
    assert (await desk.my_detail(customer, journey.id))["estimate"] is None  # SUBMITTED
    await desk.edit(world.advisor, journey.id, labour_lines("2500"))  # v2 DRAFT: EDIT_ESTIMATE
    await desk.act(world.advisor, journey.id, "send-estimate")
    sent = (await desk.my_detail(customer, journey.id))["estimate"]
    assert (sent["version"], sent["status"], sent["grand_total"]) == (2, "SENT", "2500.00")
    reject = {"estimate_id": sent["id"], "reason": "Too expensive"}
    await desk.my_act(customer, journey.id, "reject-estimate", reject)
    await desk.act(world.advisor, journey.id, "revise-estimate")  # v3 DRAFT
    detail = await desk.my_detail(customer, journey.id)
    assert (detail["estimate"]["version"], detail["estimate"]["status"]) == (2, "REJECTED")
    assert detail["estimate"]["customer_note"] == "Too expensive"
    assert detail["estimate_revision_in_progress"] is True
    staff_only = {"inspection_notes", "technician", "parts_person", "qc_inspector", "customer"}
    assert not staff_only & detail.keys()
    assert "Coil is weak" not in str(detail)
    assert set(detail["estimate"]["lines"][0]) == {
        "id",
        "position",
        "line_type",
        "description",
        "quantity",
        "unit_price",
        "line_total",
    }
    versions = await desk.get(customer.user_id, desk.my_path(journey.id, "/estimates"))
    assert [(item["version"], item["status"]) for item in versions["items"]] == [(2, "REJECTED")]
    timeline = (await desk.get(customer.user_id, desk.my_path(journey.id, "/events")))["items"]
    assert [event["action"] for event in timeline] == [
        "CREATE",
        "CONFIRM",
        "ASSIGN_TECHNICIAN",
        "START_INSPECTION",
        "SUBMIT_ESTIMATE",
        "SEND_ESTIMATE",  # EDIT_ESTIMATE is staff-only
        "REJECT_ESTIMATE",
        "REVISE_ESTIMATE",
    ]
    for event in timeline:
        assert set(event) == {
            "id",
            "action",
            "from_status",
            "to_status",
            "by_customer",
            "note",
            "created_at",
        }
    notes = {event["action"]: event["note"] for event in timeline}
    assert notes == dict.fromkeys(notes) | {"REJECT_ESTIMATE": "Too expensive"}
    by_customer = {event["action"] for event in timeline if event["by_customer"]}
    assert by_customer == {"CREATE", "REJECT_ESTIMATE"}
    staff = (await desk.get(world.advisor.id, desk.booking_path(journey.id, "/events")))["items"]
    assert staff[1]["note"] == "VIP - waive the diagnostics"
    assert "EDIT_ESTIMATE" in [event["action"] for event in staff]


async def test_bk36_qc_issues_repair_notes_and_reassignments_stay_staff_only(
    desk: Desk, world: World
) -> None:
    journey = await drive_booking_to(desk, S.QC_IN_PROGRESS)
    fail = {"issue_title": "Oil leak at filter", "issue_description": "The seal leaks."}
    await desk.act(world.qc, journey.id, "fail-qc", fail)
    reassign = {"technician_user_id": str(world.technician2.id)}
    await desk.act(world.advisor, journey.id, "reassign-technician", reassign)
    await desk.act(world.technician2, journey.id, "send-to-qc", {"repair_notes": "Seal replaced"})
    path = desk.my_path(journey.id, "/events")
    timeline = (await desk.get(journey.customer.user_id, path))["items"]
    failed, resent = timeline[-2], timeline[-1]
    assert (failed["action"], failed["from_status"], failed["to_status"], failed["note"]) == (
        "FAIL_QC",
        "QC_IN_PROGRESS",
        "IN_REPAIR",
        None,  # the issue title is staff-only (D92)
    )
    assert (resent["action"], resent["note"]) == ("SEND_TO_QC", None)
    assert "REASSIGN_TECHNICIAN" not in [event["action"] for event in timeline]
    assert "Oil leak" not in str(timeline)
    assert "Seal replaced" not in str(timeline)
    staff = (await desk.get(world.advisor.id, desk.booking_path(journey.id, "/events")))["items"]
    assert [event["action"] for event in staff[-3:]] == [
        "FAIL_QC",
        "REASSIGN_TECHNICIAN",
        "SEND_TO_QC",
    ]
    assert [event["note"] for event in staff[-3:]] == ["Oil leak at filter", None, "Seal replaced"]
    cancelled = await drive_booking_to(desk, S.CONFIRMED)
    await desk.act(world.advisor, cancelled.id, "cancel", {"reason": "Workshop flooded"})
    path = desk.my_path(cancelled.id, "/events")
    last = (await desk.get(cancelled.customer.user_id, path))["items"][-1]
    assert (last["action"], last["note"], last["by_customer"]) == (
        "CANCEL",
        "Workshop flooded",
        False,
    )
    detail = await desk.my_detail(cancelled.customer, cancelled.id)
    assert (detail["cancelled_by_customer"], detail["cancel_reason"]) == (False, "Workshop flooded")


# --- Audience data on staff responses (spec 04 §C) ------------------------------------------------


async def test_the_customers_contact_data_is_for_the_owner_and_advisors_only(
    desk: Desk, world: World, db: Database
) -> None:
    customer = await new_customer(db, phone="+923001234567")
    journey = await drive_booking_to(desk, S.QC_IN_PROGRESS, customer=customer)
    for user_id, sees_contact in (
        (world.owner.id, True),
        (world.advisor.id, True),
        (world.technician.id, False),
        (world.parts.id, False),
        (world.qc.id, False),
    ):
        detail = await desk.get(user_id, desk.booking_path(journey.id))
        contact = (detail["customer"]["email"], detail["customer"]["phone"])
        assert contact == ((customer.email, "+923001234567") if sees_contact else (None, None))
        assert detail["customer"]["full_name"] == customer.full_name
        listing = await desk.get(user_id, desk.shop_path("/bookings"))
        (item,) = [row for row in listing["items"] if row["id"] == journey.id]
        assert item["customer"] == {"user_id": str(customer.user_id), "full_name": "Ayesha Khan"}


async def test_bk37_qc_inspectors_get_no_stock_data(desk: Desk, world: World) -> None:
    journey = await drive_booking_to(desk, S.QC_PENDING)
    sara = world.qc.id
    problem(
        await desk.api.get(desk.booking_path(journey.id, "/parts"), headers=bearer(sara)),
        403,
        "FORBIDDEN",
    )
    hidden = await drive_booking_to(desk, S.PARTS_READY)
    assert_identical_404s(
        [await desk.api.get(desk.booking_path(hidden.id, "/parts"), headers=bearer(sara))]
    )
    assert (await desk.get(sara, desk.booking_path(journey.id)))["parts_summary"] is None
    listing = await desk.get(sara, desk.shop_path("/bookings"))
    assert [item["parts_summary"] for item in listing["items"]] == [None]
    estimates = await desk.get(sara, desk.booking_path(journey.id, "/estimates"))
    part_lines = [line for line in estimates["items"][0]["lines"] if line["part"] is not None]
    assert len(part_lines) == 3
    stock_fields = ("on_hand", "reserved", "available", "reorder_level", "stock_state")
    for line in part_lines:
        assert {line["part"][name] for name in stock_fields} == {None}
    full = {"required_count": 3, "available_count": 3, "shortage_count": 0, "all_available": True}
    assert (await desk.detail(world.owner, journey.id))["parts_summary"] == full
    assert (await desk.detail(world.technician, journey.id))["parts_summary"] == full
    path = desk.booking_path(journey.id, "/estimates")
    owner_lines = (await desk.get(world.owner.id, path))["items"][0]["lines"]
    assert all(line["part"]["on_hand"] is not None for line in owner_lines if line["part"])
    technician = await desk.get(world.technician.id, desk.booking_path(journey.id, "/parts"))
    assert len(technician["items"]) == 3
    await desk.get(world.technician2.id, desk.booking_path(journey.id, "/parts"), expect=404)


# --- BK-40 (DB half): the SQL predicate and the item routes agree with can_view -------------------

REQUIRES_TECHNICIAN = frozenset(set(BookingStatus) - {S.PENDING, S.CONFIRMED, S.CANCELLED})
REQUIRES_PARTS_PERSON = frozenset(
    {
        S.PARTS_PENDING,
        S.PARTS_ORDERED,
        S.PARTS_READY,
        S.IN_REPAIR,
        S.QC_PENDING,
        S.QC_IN_PROGRESS,
        S.READY_FOR_PICKUP,
        S.COMPLETED,
    }
)
WITH_PICKER = frozenset({S.QC_IN_PROGRESS, S.READY_FOR_PICKUP, S.COMPLETED})


async def insert_every_combination(world: World, db: Database) -> list[dict[str, Any]]:
    """One booking row per (status, technician, parts person, picker, inspected-by-Sara)
    combination the database's CHECKs allow. Rows are written directly on purpose: this proves
    the predicate itself (spec 12 §3.3), including assignments no action sequence produces."""
    customer = await new_customer(db)
    imran, hamza = world.technician.id, world.technician2.id
    usman, kashif = world.parts.id, world.parts2.id
    sara, hina = world.qc.id, world.qc2.id
    combos: list[dict[str, Any]] = []
    async with db.sessionmaker() as session:
        car = Vehicle(
            owner_user_id=customer.user_id,
            registration_number="LEA-1234",
            registration_key="LEA1234",
            make="Honda",
            model="Civic",
            year=2016,
        )
        session.add(car)
        await session.flush()
        for status in BookingStatus:
            technicians = [imran, hamza] if status in REQUIRES_TECHNICIAN else [None, imran]
            parts_people = [usman, kashif] if status in REQUIRES_PARTS_PERSON else [None, usman]
            pickers = [sara, hina] if status in WITH_PICKER else [None]
            for technician, parts, picker, inspected in itertools.product(
                technicians, parts_people, pickers, [False, True]
            ):
                terminal: dict[str, Any] = {}
                if status == S.CANCELLED:
                    terminal = {
                        "cancelled_at": FRIDAY_1000,
                        "cancelled_by_user_id": customer.user_id,
                    }
                elif status == S.COMPLETED:
                    terminal = {"completed_at": FRIDAY_1000}
                booking = Booking(
                    shop_id=world.shop_id,
                    reference=new_booking_reference(),
                    customer_user_id=customer.user_id,
                    vehicle_id=car.id,
                    slot_start=FRIDAY_1000,
                    slot_end=FRIDAY_1000 + timedelta(hours=1),
                    status=status,
                    technician_user_id=technician,
                    parts_person_user_id=parts,
                    qc_inspector_user_id=picker,
                    **terminal,
                )
                session.add(booking)
                await session.flush()
                if inspected:
                    session.add(
                        QcInspection(
                            shop_id=world.shop_id,
                            booking_id=booking.id,
                            inspector_user_id=sara,
                            picked_at=datetime(2026, 10, 13, 4, tzinfo=UTC),
                            completed_at=datetime(2026, 10, 13, 5, tzinfo=UTC),
                            result=QcResult.FAIL,
                        )
                    )
                combos.append(
                    {
                        "id": str(booking.id),
                        "status": status,
                        "technician": technician,
                        "parts": parts,
                        "inspected_by": {sara} if inspected else set(),
                    }
                )
        await session.commit()
    return combos


def visible_to(user_id: uuid.UUID, role: MembershipRole, combo: dict[str, Any]) -> bool:
    return can_view(
        role,
        is_technician=combo["technician"] == user_id,
        is_parts_person=combo["parts"] == user_id,
        status=combo["status"],
        has_inspected=user_id in combo["inspected_by"],
    )


async def listed_ids(desk: Desk, user_id: uuid.UUID) -> list[str]:
    seen: list[str] = []
    offset = 0
    while True:
        page = await desk.get(user_id, desk.shop_path("/bookings"), limit=100, offset=offset)
        seen += [item["id"] for item in page["items"]]
        offset += 100
        if offset >= page["total"]:
            assert len(seen) == page["total"]
            return seen


@pytest.mark.slow
async def test_bk40_lists_counts_and_item_routes_agree_with_can_view(
    desk: Desk, world: World, db: Database, invariants: InvariantCheck
) -> None:
    invariants.enabled = False  # direct rows: no events, no slot counters (by design)
    combos = await insert_every_combination(world, db)
    assert len(combos) == 160
    callers = [
        (world.owner.id, MembershipRole.OWNER),
        (world.advisor.id, MembershipRole.SERVICE_ADVISOR),
        (world.technician.id, MembershipRole.TECHNICIAN),
        (world.technician2.id, MembershipRole.TECHNICIAN),
        (world.parts.id, MembershipRole.PARTS_PERSON),
        (world.parts2.id, MembershipRole.PARTS_PERSON),
        (world.qc.id, MembershipRole.QC_INSPECTOR),
        (world.qc2.id, MembershipRole.QC_INSPECTOR),
    ]
    for user_id, role in callers:
        expected = {combo["id"] for combo in combos if visible_to(user_id, role, combo)}
        listed = await listed_ids(desk, user_id)
        assert len(listed) == len(set(listed)), role  # no duplicates across pages
        assert set(listed) == expected, role
        counts = await desk.get(user_id, desk.shop_path("/bookings/status-counts"))
        assert counts["total"] == len(expected), role
        by_status = {item["status"]: item["count"] for item in counts["items"]}
        assert by_status == {
            status.value: sum(
                1 for combo in combos if combo["id"] in expected and combo["status"] == status
            )
            for status in BookingStatus
        }, role
    for user_id, role in callers[2:]:  # item routes evaluate can_view on the row (§7.5)
        for combo in combos:
            response = await desk.api.get(desk.booking_path(combo["id"]), headers=bearer(user_id))
            expected_status = 200 if visible_to(user_id, role, combo) else 404
            assert response.status_code == expected_status, (role, combo, response.text)

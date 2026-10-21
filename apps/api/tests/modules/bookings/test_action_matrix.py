"""SEC-07, the booking-action matrix (spec 12 §3.4; spec 04 RBAC D): every slug, every caller and
every status, against an oracle written independently from spec 08 and glossary §10.

One booking is driven to each of the 17 statuses. A cast of eleven callers — the booking's
customer, another customer, the Owner, the SA, the assigned technician and another one, the
assigned parts person and another one, the QC inspector who picked it and another one, and an SA
of shop B — calls every slug through its own endpoint family (`edit-estimate` through
`PUT …/estimate`). The check order is the oracle's: route in the family? (404) → member? (404) →
visible? (404) → role (403 `FORBIDDEN`) → assignment (403 `NOT_ASSIGNED`) → status (409
`INVALID_TRANSITION`, `ALREADY_PICKED` for `pick-qc` while `QC_IN_PROGRESS`, `ESTIMATE_LOCKED`
for the estimate editor). Every predicted rejection is sent and must match status and code; every
predicted "allowed" must be in that caller's `allowed_actions` and is not executed. Afterwards no
booking and no event changed. The same run checks SM-19's API half (each visible caller's
`allowed_actions` is exactly the allowed set) and BK-34 (list item = detail).
"""

import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from app.core.database import Database
from app.shared.enums import BookingStatus
from tests.modules.bookings.support import (
    Customer,
    Desk,
    Journey,
    World,
    booking_row,
    count_rows,
    drive_booking_to,
    full_checklist,
    new_customer,
)
from tests.modules.identity.builders import bearer

pytestmark = [pytest.mark.db, pytest.mark.slow]

S = BookingStatus
SA_O = frozenset({"OWNER", "SERVICE_ADVISOR"})
TECH = frozenset({"TECHNICIAN"})
PP = frozenset({"PARTS_PERSON"})
QC = frozenset({"QC_INSPECTOR"})
CUSTOMER = frozenset({"CUSTOMER"})
CANCELLABLE = frozenset(
    {
        S.PENDING,
        S.CONFIRMED,
        S.ASSIGNED,
        S.INSPECTING,
        S.ESTIMATE_REVIEW,
        S.AWAITING_CUSTOMER,
        S.ESTIMATE_APPROVED,
        S.ESTIMATE_REJECTED,
        S.PARTS_PENDING,
        S.PARTS_ORDERED,
        S.PARTS_READY,
    }
)


@dataclass(frozen=True)
class Spec:
    """One row of spec 08's tables: source statuses, actor roles, the role its guard binds."""

    sources: frozenset[BookingStatus]
    actors: frozenset[str]
    guard: str | None = None


SPEC: dict[str, Spec] = {
    "confirm": Spec(frozenset({S.PENDING}), SA_O),
    "decline": Spec(frozenset({S.PENDING}), SA_O),
    "assign-technician": Spec(frozenset({S.CONFIRMED}), SA_O),
    "start-inspection": Spec(frozenset({S.ASSIGNED}), TECH, "TECHNICIAN"),
    "edit-estimate": Spec(frozenset({S.INSPECTING, S.ESTIMATE_REVIEW}), TECH | SA_O, "TECHNICIAN"),
    "submit-estimate": Spec(frozenset({S.INSPECTING}), TECH, "TECHNICIAN"),
    "send-estimate": Spec(frozenset({S.ESTIMATE_REVIEW}), SA_O),
    "approve-estimate": Spec(frozenset({S.AWAITING_CUSTOMER}), CUSTOMER, "CUSTOMER"),
    "reject-estimate": Spec(frozenset({S.AWAITING_CUSTOMER}), CUSTOMER, "CUSTOMER"),
    "revise-estimate": Spec(frozenset({S.ESTIMATE_REJECTED}), SA_O),
    "return-to-technician": Spec(frozenset({S.ESTIMATE_REJECTED}), SA_O),
    "assign-parts-person": Spec(frozenset({S.ESTIMATE_APPROVED}), SA_O),
    "order-parts": Spec(frozenset({S.PARTS_PENDING}), PP, "PARTS_PERSON"),
    "mark-parts-ready": Spec(frozenset({S.PARTS_PENDING, S.PARTS_ORDERED}), PP, "PARTS_PERSON"),
    "allocate-parts": Spec(frozenset({S.PARTS_READY}), PP, "PARTS_PERSON"),
    "start-repair": Spec(frozenset({S.IN_REPAIR}), TECH, "TECHNICIAN"),
    "send-to-qc": Spec(frozenset({S.IN_REPAIR}), TECH, "TECHNICIAN"),
    "pick-qc": Spec(frozenset({S.QC_PENDING}), QC),
    "pass-qc": Spec(frozenset({S.QC_IN_PROGRESS}), QC, "QC_INSPECTOR"),
    "fail-qc": Spec(frozenset({S.QC_IN_PROGRESS}), QC, "QC_INSPECTOR"),
    "notify-ready": Spec(frozenset({S.READY_FOR_PICKUP}), SA_O),
    "complete": Spec(frozenset({S.READY_FOR_PICKUP}), SA_O | CUSTOMER, "CUSTOMER"),
    "cancel": Spec(CANCELLABLE, SA_O | CUSTOMER, "CUSTOMER"),
    "reassign-technician": Spec(frozenset({S.ASSIGNED, S.INSPECTING, S.IN_REPAIR}), SA_O),
    "reassign-parts-person": Spec(
        frozenset({S.PARTS_PENDING, S.PARTS_ORDERED, S.PARTS_READY}), SA_O
    ),
}
EDIT_ACTORS = {S.INSPECTING: TECH, S.ESTIMATE_REVIEW: SA_O}
CUSTOMER_ROUTES = frozenset({"approve-estimate", "reject-estimate", "complete", "cancel"})
STAFF_ROUTES = frozenset(SPEC) - {"approve-estimate", "reject-estimate"}  # edit = PUT …/estimate
TERMINAL = frozenset({S.COMPLETED, S.CANCELLED})

TECHNICIAN_FROM = frozenset(set(BookingStatus) - {S.PENDING, S.CONFIRMED, S.CANCELLED})
PARTS_FROM = frozenset(
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
PICKED = frozenset({S.QC_IN_PROGRESS, S.READY_FOR_PICKUP, S.COMPLETED})  # Sara picked these


@dataclass(frozen=True)
class Caller:
    name: str
    role: str  # CUSTOMER or a membership role
    user_id: uuid.UUID
    own_booking: bool = False  # customers: is it their booking?
    member_of_a: bool = True  # staff: an active member of shop A?
    assignment: str | None = None  # technician / parts / picker: which column they hold


Outcome = tuple[int, str] | str  # (status, code) or "allowed"


def visible(caller: Caller, status: BookingStatus) -> bool:
    """D21, written from spec 04's table for this cast."""
    if caller.role == "CUSTOMER":
        return caller.own_booking
    if caller.role in SA_O:
        return True
    if caller.role == "TECHNICIAN":
        return caller.assignment == "technician" and status in TECHNICIAN_FROM
    if caller.role == "PARTS_PERSON":
        return caller.assignment == "parts" and status in PARTS_FROM
    in_queue = status in {S.QC_PENDING, S.QC_IN_PROGRESS}
    return in_queue or (caller.assignment == "picker" and status in PICKED)


def holds_guard(caller: Caller, status: BookingStatus, guard: str) -> bool:
    if guard == "CUSTOMER":
        return caller.own_booking
    if guard == "TECHNICIAN":
        return caller.assignment == "technician" and status in TECHNICIAN_FROM
    if guard == "PARTS_PERSON":
        return caller.assignment == "parts" and status in PARTS_FROM
    return caller.assignment == "picker" and status in PICKED  # QC_PICKER


def oracle(caller: Caller, status: BookingStatus, slug: str) -> Outcome:  # noqa: PLR0911
    spec = SPEC[slug]
    routes = CUSTOMER_ROUTES if caller.role == "CUSTOMER" else STAFF_ROUTES
    if slug not in routes or not caller.member_of_a or not visible(caller, status):
        return (404, "NOT_FOUND")
    if caller.role not in spec.actors:
        return (403, "FORBIDDEN")
    if spec.guard == caller.role and not holds_guard(caller, status, spec.guard):
        return (403, "NOT_ASSIGNED")
    actors_now = EDIT_ACTORS.get(status, frozenset()) if slug == "edit-estimate" else spec.actors
    if status in TERMINAL or status not in spec.sources or caller.role not in actors_now:
        if slug == "pick-qc" and status == S.QC_IN_PROGRESS:
            return (409, "ALREADY_PICKED")
        if slug == "edit-estimate":
            return (409, "ESTIMATE_LOCKED")
        return (409, "INVALID_TRANSITION")
    return "allowed"


def body_for(world: World, slug: str, *, customer: bool) -> dict[str, Any]:
    """Schema-valid bodies, so no 422 can hide a 403 or 404 (spec 03 §1.4)."""
    bodies: dict[str, dict[str, Any]] = {
        "decline": {"reason": "Matrix"},
        "cancel": {} if customer else {"reason": "Matrix"},
        "assign-technician": {"technician_user_id": str(world.technician2.id)},
        "reassign-technician": {"technician_user_id": str(world.technician2.id)},
        "assign-parts-person": {"parts_person_user_id": str(world.parts2.id)},
        "reassign-parts-person": {"parts_person_user_id": str(world.parts2.id)},
        "approve-estimate": {"estimate_id": str(uuid.uuid4())},
        "reject-estimate": {"estimate_id": str(uuid.uuid4())},
        "pass-qc": {"checklist": full_checklist()},
        "fail-qc": {"issue_title": "Matrix", "issue_description": "Matrix probe."},
        "edit-estimate": {
            "lines": [
                {"line_type": "LABOUR", "description": "Probe", "quantity": "1", "unit_price": "1"}
            ]
        },
    }
    return bodies.get(slug, {})


async def send(desk: Desk, caller: Caller, journey: Journey, slug: str) -> httpx.Response:
    headers = bearer(caller.user_id)
    body = body_for(desk.world, slug, customer=caller.role == "CUSTOMER")
    if caller.role == "CUSTOMER":
        if slug == "edit-estimate":
            return await desk.api.put(
                desk.my_path(journey.id, "/estimate"), json=body, headers=headers
            )
        return await desk.api.post(
            desk.my_path(journey.id, f"/actions/{slug}"), json=body, headers=headers
        )
    if slug == "edit-estimate":
        return await desk.api.put(
            desk.booking_path(journey.id, "/estimate"), json=body, headers=headers
        )
    return await desk.api.post(
        desk.booking_path(journey.id, f"/actions/{slug}"), json=body, headers=headers
    )


def cast(world: World, journey: Journey, other_customer: Customer) -> list[Caller]:
    return [
        Caller("customer", "CUSTOMER", journey.customer.user_id, own_booking=True),
        Caller("other customer", "CUSTOMER", other_customer.user_id),
        Caller("owner", "OWNER", world.owner.id),
        Caller("advisor", "SERVICE_ADVISOR", world.advisor.id),
        Caller("technician", "TECHNICIAN", world.technician.id, assignment="technician"),
        Caller("other technician", "TECHNICIAN", world.technician2.id),
        Caller("parts person", "PARTS_PERSON", world.parts.id, assignment="parts"),
        Caller("other parts person", "PARTS_PERSON", world.parts2.id),
        Caller("qc picker", "QC_INSPECTOR", world.qc.id, assignment="picker"),
        Caller("other qc", "QC_INSPECTOR", world.qc2.id),
        Caller("shop B advisor", "SERVICE_ADVISOR", world.other_advisor.id, member_of_a=False),
    ]


async def visible_allowed_actions(
    desk: Desk, caller: Caller, journey: Journey
) -> tuple[list[str], list[str]]:
    """`allowed_actions` from the caller's detail and from the caller's list item (BK-34)."""
    if caller.role == "CUSTOMER":
        detail = await desk.get(caller.user_id, desk.my_path(journey.id))
        listing = await desk.get(caller.user_id, "/api/v1/me/bookings", limit=100)
    else:
        detail = await desk.get(caller.user_id, desk.booking_path(journey.id))
        listing = await desk.get(caller.user_id, desk.shop_path("/bookings"), limit=100)
    (item,) = [row for row in listing["items"] if row["id"] == journey.id]
    return detail["allowed_actions"], item["allowed_actions"]


async def test_sec07_sm19_bk34_the_booking_action_matrix(
    desk: Desk, world: World, db: Database
) -> None:
    journeys = {status: await drive_booking_to(desk, status) for status in BookingStatus}
    other_customer = await new_customer(db, full_name="Omar")
    versions = {s: (await booking_row(db, j.id)).version for s, j in journeys.items()}
    events_before = await count_rows(db, "booking_events")
    mismatches: list[str] = []
    checked = 0
    for status, journey in journeys.items():
        for caller in cast(world, journey, other_customer):
            allowed: list[str] = []
            for slug in SPEC:
                expected = oracle(caller, status, slug)
                if expected == "allowed":
                    allowed.append(slug)
                    continue
                response = await send(desk, caller, journey, slug)
                checked += 1
                code = response.json().get("code") if response.status_code >= 400 else None
                if (response.status_code, code) != expected:
                    mismatches.append(
                        f"{status} {caller.name} {slug}: expected {expected}, "
                        f"got {response.status_code} {code}"
                    )
            if caller.member_of_a and visible(caller, status):
                detail, item = await visible_allowed_actions(desk, caller, journey)
                expected_list = [slug for slug in SPEC if slug in allowed]
                if detail != expected_list:
                    mismatches.append(
                        f"{status} {caller.name} allowed: {detail} != {expected_list}"
                    )
                if item != detail:
                    mismatches.append(f"{status} {caller.name} list {item} != detail {detail}")
    assert not mismatches, "\n".join(mismatches)
    assert checked > 3000
    assert {s: (await booking_row(db, j.id)).version for s, j in journeys.items()} == versions
    assert await count_rows(db, "booking_events") == events_before


def test_the_oracle_agrees_with_the_spec_tables_on_known_cells() -> None:
    """A few hand-checked cells of spec 04 RBAC D, so the oracle itself is trustworthy."""
    owner = Caller("owner", "OWNER", uuid.uuid4())
    sara = Caller("sara", "QC_INSPECTOR", uuid.uuid4(), assignment="picker")
    hina = Caller("hina", "QC_INSPECTOR", uuid.uuid4())
    imran = Caller("imran", "TECHNICIAN", uuid.uuid4(), assignment="technician")
    ahmed = Caller("ahmed", "CUSTOMER", uuid.uuid4(), own_booking=True)
    assert oracle(owner, S.QC_PENDING, "pick-qc") == (403, "FORBIDDEN")  # SM-16
    assert oracle(owner, S.INSPECTING, "edit-estimate") == (409, "ESTIMATE_LOCKED")  # EST-11
    assert oracle(hina, S.QC_IN_PROGRESS, "pass-qc") == (403, "NOT_ASSIGNED")  # SEC-10
    assert oracle(hina, S.QC_IN_PROGRESS, "pick-qc") == (409, "ALREADY_PICKED")
    assert oracle(sara, S.QC_IN_PROGRESS, "pass-qc") == "allowed"
    assert oracle(hina, S.IN_REPAIR, "pick-qc") == (404, "NOT_FOUND")
    assert oracle(imran, S.ASSIGNED, "confirm") == (403, "FORBIDDEN")
    assert oracle(ahmed, S.PENDING, "confirm") == (404, "NOT_FOUND")  # no customer route
    assert oracle(ahmed, S.IN_REPAIR, "cancel") == (409, "INVALID_TRANSITION")
    assert oracle(ahmed, S.READY_FOR_PICKUP, "complete") == "allowed"

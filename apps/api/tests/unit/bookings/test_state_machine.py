"""Domain tests for the booking state machine (spec 08 SM-01...SM-20, spec 12 section 3.2).

Every expectation below is a second, independent transcription of spec 08 (transition
table T01-T22, operations O1-O5, assignment guards, check order, `allowed_actions`) and of
glossary section 4. Nothing is derived from `RULES`: the two statements of the spec must
agree. Pure Python, no database, no conftest fixtures.
"""

import itertools
import re
from dataclasses import FrozenInstanceError, dataclass

import pytest

from app.modules.bookings.domain.state_machine import (
    ACTION_TO_SLUG,
    CANCELLABLE_STATUSES,
    GUARD_ROLE,
    RULES,
    SLUG_TO_ACTION,
    TERMINAL_STATUSES,
    ActorContext,
    Denial,
    Guard,
    Rule,
    TransitionDenied,
    allowed_actions,
    check,
    next_status,
)
from app.shared.enums import ActorRole, BookingAction, BookingStatus

# Short aliases keep the hand-written tables readable.
A = BookingAction
S = BookingStatus
R = ActorRole

ROLE_ORDER = list(R)

# ActorContext flags behind spec 08's assignment guards.
TECH = "is_assigned_technician"  # ASSIGNED_TECHNICIAN
PARTS = "is_assigned_parts_person"  # ASSIGNED_PARTS_PERSON
PICKER = "is_qc_picker"  # QC_PICKER
OWN = "is_booking_customer"  # BOOKING_CUSTOMER
BOOKING_TECH = "is_booking_technician"  # D47: the QC picker is never the booking's technician
FLAGS = (TECH, PARTS, PICKER, OWN, BOOKING_TECH)

# Every assignment held, so no guard can fail; D47 is not triggered.
ALL_ASSIGNMENTS = {TECH: True, PARTS: True, PICKER: True, OWN: True}

CUSTOMER = frozenset({R.CUSTOMER})
SA_OWNER = frozenset({R.SERVICE_ADVISOR, R.OWNER})  # "SA, Owner" (D16)
TECHNICIAN = frozenset({R.TECHNICIAN})
PARTS_PERSON = frozenset({R.PARTS_PERSON})
QC_INSPECTOR = frozenset({R.QC_INSPECTOR})

# Glossary section 3: the 11 cancellable statuses, "before IN_REPAIR".
CANCELLABLE = (
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
)


@dataclass(frozen=True)
class Permission:
    """One spec 08 row: `actors` may perform `action` from `sources`, holding `guard`."""

    ref: str
    action: BookingAction
    sources: tuple[BookingStatus, ...]
    actors: frozenset[ActorRole]
    guard: str | None = None


# Who may act, and from where (spec 08 transition and operation tables, glossary section 4).
# T21, T22 and O1 have two rows each because their actors are guarded differently.
PERMISSIONS = (
    Permission("T01", A.CREATE, (), CUSTOMER),
    Permission("T02", A.CONFIRM, (S.PENDING,), SA_OWNER),
    Permission("T03", A.DECLINE, (S.PENDING,), SA_OWNER),
    Permission("T04", A.ASSIGN_TECHNICIAN, (S.CONFIRMED,), SA_OWNER),
    Permission("T05", A.START_INSPECTION, (S.ASSIGNED,), TECHNICIAN, TECH),
    Permission("T06", A.SUBMIT_ESTIMATE, (S.INSPECTING,), TECHNICIAN, TECH),
    Permission("T07", A.SEND_ESTIMATE, (S.ESTIMATE_REVIEW,), SA_OWNER),
    Permission("T08", A.APPROVE_ESTIMATE, (S.AWAITING_CUSTOMER,), CUSTOMER, OWN),
    Permission("T09", A.REJECT_ESTIMATE, (S.AWAITING_CUSTOMER,), CUSTOMER, OWN),
    Permission("T10", A.REVISE_ESTIMATE, (S.ESTIMATE_REJECTED,), SA_OWNER),
    Permission("T11", A.RETURN_TO_TECHNICIAN, (S.ESTIMATE_REJECTED,), SA_OWNER),
    Permission("T12", A.ASSIGN_PARTS_PERSON, (S.ESTIMATE_APPROVED,), SA_OWNER),
    Permission("T13", A.ORDER_PARTS, (S.PARTS_PENDING,), PARTS_PERSON, PARTS),
    Permission("T14", A.MARK_PARTS_READY, (S.PARTS_PENDING, S.PARTS_ORDERED), PARTS_PERSON, PARTS),
    Permission("T15", A.RECEIVE_PARTS, (S.PARTS_ORDERED,), PARTS_PERSON),
    Permission("T16", A.ALLOCATE_PARTS, (S.PARTS_READY,), PARTS_PERSON, PARTS),
    Permission("T17", A.SEND_TO_QC, (S.IN_REPAIR,), TECHNICIAN, TECH),
    Permission("T18", A.PICK_QC, (S.QC_PENDING,), QC_INSPECTOR),
    Permission("T19", A.PASS_QC, (S.QC_IN_PROGRESS,), QC_INSPECTOR, PICKER),
    Permission("T20", A.FAIL_QC, (S.QC_IN_PROGRESS,), QC_INSPECTOR, PICKER),
    Permission("T21", A.COMPLETE, (S.READY_FOR_PICKUP,), SA_OWNER),
    Permission("T21", A.COMPLETE, (S.READY_FOR_PICKUP,), CUSTOMER, OWN),
    Permission("T22", A.CANCEL, CANCELLABLE, SA_OWNER),
    Permission("T22", A.CANCEL, CANCELLABLE, CUSTOMER, OWN),
    Permission("O1", A.EDIT_ESTIMATE, (S.INSPECTING,), TECHNICIAN, TECH),
    Permission("O1", A.EDIT_ESTIMATE, (S.ESTIMATE_REVIEW,), SA_OWNER),
    Permission("O2", A.START_REPAIR, (S.IN_REPAIR,), TECHNICIAN, TECH),
    Permission("O3", A.NOTIFY_READY, (S.READY_FOR_PICKUP,), SA_OWNER),
    Permission("O4", A.REASSIGN_TECHNICIAN, (S.ASSIGNED, S.INSPECTING, S.IN_REPAIR), SA_OWNER),
    Permission(
        "O5", A.REASSIGN_PARTS_PERSON, (S.PARTS_PENDING, S.PARTS_ORDERED, S.PARTS_READY), SA_OWNER
    ),
)

# Golden transition list: (action, from, to) read straight off spec 08's tables and state
# diagram. None as "from" is CREATE's "-"; None as "to" marks an operation (O1-O5).
GOLDEN_TRANSITIONS = {
    (A.CREATE, None, S.PENDING),
    (A.CONFIRM, S.PENDING, S.CONFIRMED),
    (A.DECLINE, S.PENDING, S.CANCELLED),
    (A.ASSIGN_TECHNICIAN, S.CONFIRMED, S.ASSIGNED),
    (A.START_INSPECTION, S.ASSIGNED, S.INSPECTING),
    (A.SUBMIT_ESTIMATE, S.INSPECTING, S.ESTIMATE_REVIEW),
    (A.SEND_ESTIMATE, S.ESTIMATE_REVIEW, S.AWAITING_CUSTOMER),
    (A.APPROVE_ESTIMATE, S.AWAITING_CUSTOMER, S.ESTIMATE_APPROVED),
    (A.REJECT_ESTIMATE, S.AWAITING_CUSTOMER, S.ESTIMATE_REJECTED),
    (A.REVISE_ESTIMATE, S.ESTIMATE_REJECTED, S.ESTIMATE_REVIEW),
    (A.RETURN_TO_TECHNICIAN, S.ESTIMATE_REJECTED, S.INSPECTING),
    (A.ASSIGN_PARTS_PERSON, S.ESTIMATE_APPROVED, S.PARTS_PENDING),
    (A.ORDER_PARTS, S.PARTS_PENDING, S.PARTS_ORDERED),
    (A.MARK_PARTS_READY, S.PARTS_PENDING, S.PARTS_READY),
    (A.MARK_PARTS_READY, S.PARTS_ORDERED, S.PARTS_READY),
    (A.RECEIVE_PARTS, S.PARTS_ORDERED, S.PARTS_READY),
    (A.ALLOCATE_PARTS, S.PARTS_READY, S.IN_REPAIR),
    (A.SEND_TO_QC, S.IN_REPAIR, S.QC_PENDING),
    (A.PICK_QC, S.QC_PENDING, S.QC_IN_PROGRESS),
    (A.PASS_QC, S.QC_IN_PROGRESS, S.READY_FOR_PICKUP),
    (A.FAIL_QC, S.QC_IN_PROGRESS, S.IN_REPAIR),
    (A.COMPLETE, S.READY_FOR_PICKUP, S.COMPLETED),
    (A.CANCEL, S.PENDING, S.CANCELLED),
    (A.CANCEL, S.CONFIRMED, S.CANCELLED),
    (A.CANCEL, S.ASSIGNED, S.CANCELLED),
    (A.CANCEL, S.INSPECTING, S.CANCELLED),
    (A.CANCEL, S.ESTIMATE_REVIEW, S.CANCELLED),
    (A.CANCEL, S.AWAITING_CUSTOMER, S.CANCELLED),
    (A.CANCEL, S.ESTIMATE_APPROVED, S.CANCELLED),
    (A.CANCEL, S.ESTIMATE_REJECTED, S.CANCELLED),
    (A.CANCEL, S.PARTS_PENDING, S.CANCELLED),
    (A.CANCEL, S.PARTS_ORDERED, S.CANCELLED),
    (A.CANCEL, S.PARTS_READY, S.CANCELLED),
    (A.EDIT_ESTIMATE, S.INSPECTING, None),
    (A.EDIT_ESTIMATE, S.ESTIMATE_REVIEW, None),
    (A.START_REPAIR, S.IN_REPAIR, None),
    (A.NOTIFY_READY, S.READY_FOR_PICKUP, None),
    (A.REASSIGN_TECHNICIAN, S.ASSIGNED, None),
    (A.REASSIGN_TECHNICIAN, S.INSPECTING, None),
    (A.REASSIGN_TECHNICIAN, S.IN_REPAIR, None),
    (A.REASSIGN_PARTS_PERSON, S.PARTS_PENDING, None),
    (A.REASSIGN_PARTS_PERSON, S.PARTS_ORDERED, None),
    (A.REASSIGN_PARTS_PERSON, S.PARTS_READY, None),
}

# Glossary section 4 slugs, in its table order. CREATE and RECEIVE_PARTS have none.
GLOSSARY_SLUGS = {
    A.CONFIRM: "confirm",
    A.DECLINE: "decline",
    A.ASSIGN_TECHNICIAN: "assign-technician",
    A.START_INSPECTION: "start-inspection",
    A.EDIT_ESTIMATE: "edit-estimate",
    A.SUBMIT_ESTIMATE: "submit-estimate",
    A.SEND_ESTIMATE: "send-estimate",
    A.APPROVE_ESTIMATE: "approve-estimate",
    A.REJECT_ESTIMATE: "reject-estimate",
    A.REVISE_ESTIMATE: "revise-estimate",
    A.RETURN_TO_TECHNICIAN: "return-to-technician",
    A.ASSIGN_PARTS_PERSON: "assign-parts-person",
    A.ORDER_PARTS: "order-parts",
    A.MARK_PARTS_READY: "mark-parts-ready",
    A.ALLOCATE_PARTS: "allocate-parts",
    A.START_REPAIR: "start-repair",
    A.SEND_TO_QC: "send-to-qc",
    A.PICK_QC: "pick-qc",
    A.PASS_QC: "pass-qc",
    A.FAIL_QC: "fail-qc",
    A.NOTIFY_READY: "notify-ready",
    A.COMPLETE: "complete",
    A.CANCEL: "cancel",
    A.REASSIGN_TECHNICIAN: "reassign-technician",
    A.REASSIGN_PARTS_PERSON: "reassign-parts-person",
}

# SM-16 / D16: SA actions (the Owner may do all of them) and technician, parts and QC
# actions (the Owner may do none). The rest are customer-only: CREATE, APPROVE, REJECT.
SA_ACTIONS = (
    A.CONFIRM,
    A.DECLINE,
    A.ASSIGN_TECHNICIAN,
    A.EDIT_ESTIMATE,
    A.SEND_ESTIMATE,
    A.REVISE_ESTIMATE,
    A.RETURN_TO_TECHNICIAN,
    A.ASSIGN_PARTS_PERSON,
    A.NOTIFY_READY,
    A.COMPLETE,
    A.CANCEL,
    A.REASSIGN_TECHNICIAN,
    A.REASSIGN_PARTS_PERSON,
)
TECH_PARTS_QC_ACTIONS = (
    A.START_INSPECTION,
    A.SUBMIT_ESTIMATE,
    A.START_REPAIR,
    A.SEND_TO_QC,
    A.ORDER_PARTS,
    A.MARK_PARTS_READY,
    A.RECEIVE_PARTS,
    A.ALLOCATE_PARTS,
    A.PICK_QC,
    A.PASS_QC,
    A.FAIL_QC,
)

# SM-19 golden table: the slugs each caller sees in each status, in glossary section 4
# order. Callers hold their assignment (see ASSIGNED_CALLER); a role not listed sees [].
GOLDEN_ALLOWED: dict[BookingStatus, dict[ActorRole, list[str]]] = {
    S.PENDING: {
        R.CUSTOMER: ["cancel"],
        R.OWNER: ["confirm", "decline", "cancel"],
        R.SERVICE_ADVISOR: ["confirm", "decline", "cancel"],
    },
    S.CONFIRMED: {
        R.CUSTOMER: ["cancel"],
        R.OWNER: ["assign-technician", "cancel"],
        R.SERVICE_ADVISOR: ["assign-technician", "cancel"],
    },
    S.ASSIGNED: {
        R.CUSTOMER: ["cancel"],
        R.OWNER: ["cancel", "reassign-technician"],
        R.SERVICE_ADVISOR: ["cancel", "reassign-technician"],
        R.TECHNICIAN: ["start-inspection"],
    },
    S.INSPECTING: {
        R.CUSTOMER: ["cancel"],
        R.OWNER: ["cancel", "reassign-technician"],
        R.SERVICE_ADVISOR: ["cancel", "reassign-technician"],
        R.TECHNICIAN: ["edit-estimate", "submit-estimate"],
    },
    S.ESTIMATE_REVIEW: {
        R.CUSTOMER: ["cancel"],
        R.OWNER: ["edit-estimate", "send-estimate", "cancel"],
        R.SERVICE_ADVISOR: ["edit-estimate", "send-estimate", "cancel"],
    },
    S.AWAITING_CUSTOMER: {
        R.CUSTOMER: ["approve-estimate", "reject-estimate", "cancel"],
        R.OWNER: ["cancel"],
        R.SERVICE_ADVISOR: ["cancel"],
    },
    S.ESTIMATE_APPROVED: {
        R.CUSTOMER: ["cancel"],
        R.OWNER: ["assign-parts-person", "cancel"],
        R.SERVICE_ADVISOR: ["assign-parts-person", "cancel"],
    },
    S.ESTIMATE_REJECTED: {
        R.CUSTOMER: ["cancel"],
        R.OWNER: ["revise-estimate", "return-to-technician", "cancel"],
        R.SERVICE_ADVISOR: ["revise-estimate", "return-to-technician", "cancel"],
    },
    S.PARTS_PENDING: {
        R.CUSTOMER: ["cancel"],
        R.OWNER: ["cancel", "reassign-parts-person"],
        R.SERVICE_ADVISOR: ["cancel", "reassign-parts-person"],
        R.PARTS_PERSON: ["order-parts", "mark-parts-ready"],
    },
    S.PARTS_ORDERED: {
        R.CUSTOMER: ["cancel"],
        R.OWNER: ["cancel", "reassign-parts-person"],
        R.SERVICE_ADVISOR: ["cancel", "reassign-parts-person"],
        R.PARTS_PERSON: ["mark-parts-ready"],
    },
    S.PARTS_READY: {
        R.CUSTOMER: ["cancel"],
        R.OWNER: ["cancel", "reassign-parts-person"],
        R.SERVICE_ADVISOR: ["cancel", "reassign-parts-person"],
        R.PARTS_PERSON: ["allocate-parts"],
    },
    S.IN_REPAIR: {
        R.OWNER: ["reassign-technician"],
        R.SERVICE_ADVISOR: ["reassign-technician"],
        R.TECHNICIAN: ["start-repair", "send-to-qc"],
    },
    S.QC_PENDING: {
        R.QC_INSPECTOR: ["pick-qc"],
    },
    S.QC_IN_PROGRESS: {
        R.QC_INSPECTOR: ["pass-qc", "fail-qc"],
    },
    S.READY_FOR_PICKUP: {
        R.CUSTOMER: ["complete"],
        R.OWNER: ["notify-ready", "complete"],
        R.SERVICE_ADVISOR: ["notify-ready", "complete"],
    },
    S.COMPLETED: {},
    S.CANCELLED: {},
}

# The callers of the golden table: the booking's own customer, its assigned technician
# (who is also the booking's technician), its assigned parts person and the QC picker.
ASSIGNED_CALLER = {
    R.CUSTOMER: ActorContext(role=R.CUSTOMER, is_booking_customer=True),
    R.OWNER: ActorContext(role=R.OWNER),
    R.SERVICE_ADVISOR: ActorContext(role=R.SERVICE_ADVISOR),
    R.TECHNICIAN: ActorContext(
        role=R.TECHNICIAN, is_assigned_technician=True, is_booking_technician=True
    ),
    R.PARTS_PERSON: ActorContext(role=R.PARTS_PERSON, is_assigned_parts_person=True),
    R.QC_INSPECTOR: ActorContext(role=R.QC_INSPECTOR, is_qc_picker=True),
    R.SYSTEM: ActorContext(role=R.SYSTEM),
}

# Every role with every combination of flags (7 x 32 callers).
ALL_CALLERS = [
    ActorContext(role=role, **dict(zip(FLAGS, bits, strict=True)))
    for role in R
    for bits in itertools.product((False, True), repeat=len(FLAGS))
]


def ordered(roles: frozenset[ActorRole]) -> list[ActorRole]:
    return sorted(roles, key=ROLE_ORDER.index)


def verdict(action: BookingAction, status: BookingStatus, caller: ActorContext) -> Denial | None:
    """The outcome of `check()` as data: None when allowed, otherwise the denial code."""
    try:
        check(action, status, caller)
    except TransitionDenied as denied:
        return denied.code
    return None


# Oracles derived from the hand-written PERMISSIONS above (never from RULES).
ALLOWED = {
    (permission.action, status, role)
    for permission in PERMISSIONS
    for status in permission.sources
    for role in permission.actors
}
ACTORS = {
    action: frozenset(role for p in PERMISSIONS if p.action == action for role in p.actors)
    for action in A
}
TARGET = {(action, source): target for action, source, target in GOLDEN_TRANSITIONS}

SM01_CASES = [
    pytest.param(action, status, role, id=f"{action}-from-{status}-by-{role}")
    for action, status in itertools.product(A, S)
    for role in ordered(ACTORS[action])
    if (action, status, role) not in ALLOWED
]
SM02_CASES = [
    pytest.param(p.action, status, role, p.guard, id=f"{p.ref}-{p.action}-from-{status}-by-{role}")
    for p in PERMISSIONS
    for status in p.sources
    for role in ordered(p.actors)
]
SM03_CASES = [
    pytest.param(action, role, id=f"{action}-by-{role}")
    for action in A
    for role in R
    if role not in ACTORS[action]
]
SM04_CASES = [
    pytest.param(p.action, role, p.guard, id=f"{p.ref}-{p.action}-by-{role}-without-{p.guard}")
    for p in PERMISSIONS
    if p.guard is not None
    for role in ordered(p.actors)
]


def test_rules_cover_every_action_once_in_glossary_order() -> None:
    assert list(RULES) == list(A)
    assert all(rule.action == action for action, rule in RULES.items())


def test_golden_transition_list() -> None:
    triples = {
        (rule.action, source, rule.to_status)
        for rule in RULES.values()
        for source in rule.from_statuses
    }
    creations = {
        (rule.action, None, rule.to_status) for rule in RULES.values() if not rule.from_statuses
    }
    assert triples | creations == GOLDEN_TRANSITIONS
    # The permission table used by SM-01...SM-04 covers exactly the same (action, from) pairs.
    sources = {(p.action, status) for p in PERMISSIONS for status in p.sources}
    assert sources == {(action, source) for action, source, _ in GOLDEN_TRANSITIONS if source}


def test_slugs_match_glossary_section_4() -> None:
    assert dict(ACTION_TO_SLUG) == GLOSSARY_SLUGS
    assert dict(SLUG_TO_ACTION) == {slug: action for action, slug in GLOSSARY_SLUGS.items()}
    assert {action: rule.slug for action, rule in RULES.items()} == {
        **GLOSSARY_SLUGS,
        A.CREATE: None,
        A.RECEIVE_PARTS: None,
    }


def test_generated_cases_are_exhaustive() -> None:
    """SM-01 + SM-02 cover every (status, action, actor) triple; SM-03 every wrong role."""
    actor_pairs = sum(len(ACTORS[action]) for action in A)
    assert actor_pairs == 43
    assert len(SM02_CASES) == 81
    assert len(SM01_CASES) + len(SM02_CASES) == len(S) * actor_pairs
    assert len(SM03_CASES) + actor_pairs == len(A) * len(R)


@pytest.mark.parametrize(("action", "status", "role"), SM01_CASES)
def test_sm01_pair_outside_the_table_is_an_invalid_transition(
    action: BookingAction, status: BookingStatus, role: ActorRole
) -> None:
    caller = ActorContext(role=role, **ALL_ASSIGNMENTS)  # right role, every guard passes
    first_wins = (action, status) == (A.PICK_QC, S.QC_IN_PROGRESS)
    expected = Denial.ALREADY_PICKED if first_wins else Denial.INVALID_TRANSITION
    assert verdict(action, status, caller) is expected


@pytest.mark.parametrize(("action", "status", "role", "flag"), SM02_CASES)
def test_sm02_allowed_action_succeeds_and_yields_the_next_status(
    action: BookingAction, status: BookingStatus, role: ActorRole, flag: str | None
) -> None:
    # Only the assignment the row asks for, so other actors are shown to be unguarded.
    caller = ActorContext(role=role, **({flag: True} if flag else {}))
    rule = check(action, status, caller)
    assert rule is RULES[action]
    expected = TARGET[(action, status)]
    assert next_status(rule, status) == (status if expected is None else expected)


@pytest.mark.parametrize(("action", "role"), SM03_CASES)
def test_sm03_wrong_role_is_forbidden_in_every_status(
    action: BookingAction, role: ActorRole
) -> None:
    caller = ActorContext(role=role, **ALL_ASSIGNMENTS)
    outcome = {status: verdict(action, status, caller) for status in S}
    assert outcome == dict.fromkeys(S, Denial.FORBIDDEN)


@pytest.mark.parametrize(("action", "role", "flag"), SM04_CASES)
def test_sm04_right_role_without_the_assignment_is_not_assigned(
    action: BookingAction, role: ActorRole, flag: str
) -> None:
    # Every other assignment is held, and the check runs before the status check.
    caller = ActorContext(role=role, **{**ALL_ASSIGNMENTS, flag: False})
    outcome = {status: verdict(action, status, caller) for status in S}
    assert outcome == dict.fromkeys(S, Denial.NOT_ASSIGNED)


@pytest.mark.parametrize("action", SA_ACTIONS)
def test_sm16_owner_can_perform_every_sa_action(action: BookingAction) -> None:
    owner = ActorContext(role=R.OWNER)
    advisor = ActorContext(role=R.SERVICE_ADVISOR)
    assert any(verdict(action, status, advisor) is None for status in S)
    assert {s: verdict(action, s, owner) for s in S} == {s: verdict(action, s, advisor) for s in S}


@pytest.mark.parametrize("action", TECH_PARTS_QC_ACTIONS)
def test_sm16_owner_cannot_perform_technician_parts_or_qc_actions(action: BookingAction) -> None:
    owner = ActorContext(role=R.OWNER, **ALL_ASSIGNMENTS)
    outcome = {status: verdict(action, status, owner) for status in S}
    assert outcome == dict.fromkeys(S, Denial.FORBIDDEN)


def test_sm16_owner_cannot_edit_the_estimate_while_the_technician_inspects() -> None:
    # O1's technician half: the Owner (an EDIT_ESTIMATE actor) is refused by status; the
    # estimate endpoint reports it as 409 ESTIMATE_LOCKED (EST-11).
    owner = ActorContext(role=R.OWNER, **ALL_ASSIGNMENTS)
    assert verdict(A.EDIT_ESTIMATE, S.INSPECTING, owner) is Denial.INVALID_TRANSITION


def test_sm16_owner_sees_exactly_the_sa_actions() -> None:
    advisor = ActorContext(role=R.SERVICE_ADVISOR)
    for owner in (caller for caller in ALL_CALLERS if caller.role == R.OWNER):
        assert {s: allowed_actions(s, owner) for s in S} == {
            s: allowed_actions(s, advisor) for s in S
        }


@pytest.mark.parametrize("role", list(R))
@pytest.mark.parametrize("status", list(S))
def test_sm19_allowed_actions_golden_table(status: BookingStatus, role: ActorRole) -> None:
    assert allowed_actions(status, ASSIGNED_CALLER[role]) == GOLDEN_ALLOWED[status].get(role, [])


@pytest.mark.parametrize("role", [R.CUSTOMER, R.TECHNICIAN, R.PARTS_PERSON, R.QC_INSPECTOR])
@pytest.mark.parametrize("status", list(S))
def test_sm19_allowed_actions_without_the_assignment(
    status: BookingStatus, role: ActorRole
) -> None:
    # Another customer, another technician or parts person, a QC inspector who did not pick:
    # only the unguarded pick-qc remains.
    expected = ["pick-qc"] if (status, role) == (S.QC_PENDING, R.QC_INSPECTOR) else []
    assert allowed_actions(status, ActorContext(role=role)) == expected


def test_allowed_actions_lists_exactly_what_check_accepts() -> None:
    for status, caller in itertools.product(S, ALL_CALLERS):
        accepted = [
            slug
            for action, slug in GLOSSARY_SLUGS.items()
            if verdict(action, status, caller) is None
        ]
        assert allowed_actions(status, caller) == accepted, (status, caller)


def test_customers_only_ever_see_the_four_customer_slugs() -> None:
    seen = {
        slug
        for status in S
        for caller in ALL_CALLERS
        if caller.role == R.CUSTOMER
        for slug in allowed_actions(status, caller)
    }
    assert seen == {"approve-estimate", "reject-estimate", "cancel", "complete"}


def test_create_and_receive_parts_are_never_listed() -> None:
    for action in (A.CREATE, A.RECEIVE_PARTS):
        assert RULES[action].slug is None
        assert RULES[action].listable is False
    listed = {
        slug for status in S for caller in ALL_CALLERS for slug in allowed_actions(status, caller)
    }
    assert listed == set(GLOSSARY_SLUGS.values())


def test_check_order_is_role_then_assignment_then_status() -> None:
    assigned = ActorContext(role=R.TECHNICIAN, is_assigned_technician=True)
    other_technician = ActorContext(role=R.TECHNICIAN)
    # The role comes first: a technician never confirms, assigned or not.
    assert verdict(A.CONFIRM, S.PENDING, assigned) is Denial.FORBIDDEN
    # The assignment comes before the status: the wrong technician, in the wrong status.
    assert verdict(A.START_INSPECTION, S.PENDING, other_technician) is Denial.NOT_ASSIGNED
    # The status comes last.
    assert verdict(A.START_INSPECTION, S.PENDING, assigned) is Denial.INVALID_TRANSITION
    assert verdict(A.START_INSPECTION, S.ASSIGNED, assigned) is None


@pytest.mark.parametrize("is_picker", [False, True])
def test_pick_qc_on_a_job_already_in_progress_is_already_picked(is_picker: bool) -> None:
    inspector = ActorContext(role=R.QC_INSPECTOR, is_qc_picker=is_picker)
    assert verdict(A.PICK_QC, S.QC_IN_PROGRESS, inspector) is Denial.ALREADY_PICKED
    assert verdict(A.PICK_QC, S.READY_FOR_PICKUP, inspector) is Denial.INVALID_TRANSITION


def test_qc08_booking_technician_can_never_pick_its_qc() -> None:
    # D47: unreachable through the API (one role per membership), so it is unit-tested.
    inspector = ActorContext(role=R.QC_INSPECTOR, is_booking_technician=True)
    outcome = {status: verdict(A.PICK_QC, status, inspector) for status in S}
    assert outcome == dict.fromkeys(S, Denial.FORBIDDEN)
    assert allowed_actions(S.QC_PENDING, inspector) == []
    other_inspector = ActorContext(role=R.QC_INSPECTOR)
    assert verdict(A.PICK_QC, S.QC_PENDING, other_inspector) is None


def test_o1_edit_estimate_belongs_to_the_technician_then_the_desk() -> None:
    technician = ActorContext(role=R.TECHNICIAN, is_assigned_technician=True)
    advisor = ActorContext(role=R.SERVICE_ADVISOR)
    assert verdict(A.EDIT_ESTIMATE, S.INSPECTING, technician) is None
    assert verdict(A.EDIT_ESTIMATE, S.ESTIMATE_REVIEW, advisor) is None
    # Outside its own status each actor is refused by status (EST-11: ESTIMATE_LOCKED).
    assert verdict(A.EDIT_ESTIMATE, S.ESTIMATE_REVIEW, technician) is Denial.INVALID_TRANSITION
    assert verdict(A.EDIT_ESTIMATE, S.INSPECTING, advisor) is Denial.INVALID_TRANSITION
    assert verdict(A.EDIT_ESTIMATE, S.AWAITING_CUSTOMER, advisor) is Denial.INVALID_TRANSITION
    assert verdict(A.EDIT_ESTIMATE, S.INSPECTING, ActorContext(role=R.TECHNICIAN)) is (
        Denial.NOT_ASSIGNED
    )


@pytest.mark.parametrize(
    ("action", "status"), [(A.COMPLETE, S.READY_FOR_PICKUP), (A.CANCEL, S.PENDING)]
)
def test_customer_guard_binds_only_the_customer(
    action: BookingAction, status: BookingStatus
) -> None:
    assert verdict(action, status, ActorContext(role=R.SERVICE_ADVISOR)) is None
    assert verdict(action, status, ActorContext(role=R.OWNER)) is None
    assert verdict(action, status, ActorContext(role=R.CUSTOMER)) is Denial.NOT_ASSIGNED
    assert verdict(action, status, ActorContext(role=R.CUSTOMER, is_booking_customer=True)) is None


def test_cancel_is_accepted_from_exactly_the_11_cancellable_statuses() -> None:
    assert len(CANCELLABLE) == 11
    assert set(CANCELLABLE) == CANCELLABLE_STATUSES
    for caller in (
        ActorContext(role=R.SERVICE_ADVISOR),
        ActorContext(role=R.OWNER),
        ActorContext(role=R.CUSTOMER, is_booking_customer=True),
    ):
        accepted = {status for status in S if verdict(A.CANCEL, status, caller) is None}
        assert accepted == set(CANCELLABLE), caller.role


@pytest.mark.parametrize("status", [S.COMPLETED, S.CANCELLED])
def test_terminal_statuses_accept_no_action(status: BookingStatus) -> None:
    assert status in TERMINAL_STATUSES
    for action, role in itertools.product(A, R):
        caller = ActorContext(role=role, **ALL_ASSIGNMENTS)
        expected = Denial.INVALID_TRANSITION if role in ACTORS[action] else Denial.FORBIDDEN
        assert verdict(action, status, caller) is expected, (action, role)
    assert all(allowed_actions(status, caller) == [] for caller in ALL_CALLERS)


def test_terminal_statuses_are_completed_and_cancelled() -> None:
    assert {S.COMPLETED, S.CANCELLED} == TERMINAL_STATUSES


def test_next_status_refuses_a_status_the_rule_does_not_accept() -> None:
    with pytest.raises(TransitionDenied) as excinfo:
        next_status(RULES[A.CONFIRM], S.CONFIRMED)
    assert excinfo.value.code is Denial.INVALID_TRANSITION
    # CREATE has no source status; the service reads its target status from the rule.
    with pytest.raises(TransitionDenied):
        next_status(RULES[A.CREATE], S.PENDING)
    assert RULES[A.CREATE].to_status is S.PENDING


def test_denials_use_the_glossary_error_codes() -> None:
    codes = {"FORBIDDEN", "NOT_ASSIGNED", "INVALID_TRANSITION", "ALREADY_PICKED"}
    assert {denial.value for denial in Denial} == codes
    with pytest.raises(TransitionDenied) as excinfo:
        check(A.CONFIRM, S.COMPLETED, ActorContext(role=R.SERVICE_ADVISOR))
    assert excinfo.value.code is Denial.INVALID_TRANSITION
    assert str(excinfo.value) == excinfo.value.message
    assert "'confirm'" in excinfo.value.message


def test_each_guard_binds_one_role_and_reads_its_own_flag() -> None:
    expected = {
        Guard.ASSIGNED_TECHNICIAN: (R.TECHNICIAN, TECH),
        Guard.ASSIGNED_PARTS_PERSON: (R.PARTS_PERSON, PARTS),
        Guard.QC_PICKER: (R.QC_INSPECTOR, PICKER),
        Guard.BOOKING_CUSTOMER: (R.CUSTOMER, OWN),
    }
    assert dict(GUARD_ROLE) == {guard: role for guard, (role, _) in expected.items()}
    for guard, (role, flag) in expected.items():
        assert ActorContext(role=role, **{flag: True}).satisfies(guard)
        assert not ActorContext(role=role, **{**ALL_ASSIGNMENTS, flag: False}).satisfies(guard)


VALID_RULE = {
    "action": A.CONFIRM,
    "slug": "confirm",
    "from_statuses": frozenset({S.PENDING}),
    "to_status": S.CONFIRMED,
    "actors": SA_OWNER,
}


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"slug": None}, "a listable rule needs a slug"),
        ({"from_statuses": frozenset({S.COMPLETED})}, "terminal statuses accept no action"),
        ({"guard": Guard.QC_PICKER}, "the guard constrains a role that is not an actor"),
        (
            {"actors_by_status": {S.CONFIRMED: SA_OWNER}},
            "actors_by_status names a status outside from_statuses",
        ),
        (
            {"actors_by_status": {S.PENDING: CUSTOMER}},
            "actors_by_status names a role outside actors",
        ),
    ],
)
def test_rule_rejects_an_inconsistent_definition(change: dict[str, object], problem: str) -> None:
    with pytest.raises(ValueError, match=re.escape(problem)):
        Rule(**{**VALID_RULE, **change})  # type: ignore[arg-type]


def test_rules_are_immutable_and_hashable() -> None:
    rule = RULES[A.EDIT_ESTIMATE]
    with pytest.raises(FrozenInstanceError):
        rule.guard = None  # type: ignore[misc]
    with pytest.raises(TypeError):
        rule.actors_by_status[S.PENDING] = SA_OWNER  # type: ignore[index]
    assert len(set(RULES.values())) == len(A)

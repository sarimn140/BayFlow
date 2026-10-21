"""Booking state machine: the single declarative rule table (spec 08).

Pure Python (spec 01 domain layer): no FastAPI, SQLAlchemy, database, clock or other
I/O, and no business side effects. The bookings service loads and locks the booking,
describes the caller with an `ActorContext`, calls `check()`, and then runs the side
effects of spec 08 "How an action is executed". `allowed_actions()` feeds the
`allowed_actions` field of every booking response, so the UI never re-derives a rule
(D48).

Sources: `.claude/specs/08-booking-state-machine.md` (transitions T01-T22, operations
O1-O5, assignment guards, check order, `allowed_actions`, error mapping), glossary
sections 3, 4 and 10, and decisions D16, D21-D31 and D47.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from app.shared.enums import ActorRole, BookingAction, BookingStatus

__all__ = [
    "ACTION_TO_SLUG",
    "CANCELLABLE_STATUSES",
    "GUARD_ROLE",
    "RULES",
    "SA_OR_OWNER",
    "SLUG_TO_ACTION",
    "TERMINAL_STATUSES",
    "ActorContext",
    "Denial",
    "Guard",
    "Rule",
    "TransitionDenied",
    "allowed_actions",
    "check",
    "next_status",
]


class Guard(StrEnum):
    """Assignment guards (spec 08 "Assignment guards").

    Each guard compares one booking column with the caller and constrains only the actor
    role named in `GUARD_ROLE`; the other actors of the same rule are not subject to it.
    """

    ASSIGNED_TECHNICIAN = "ASSIGNED_TECHNICIAN"
    ASSIGNED_PARTS_PERSON = "ASSIGNED_PARTS_PERSON"
    QC_PICKER = "QC_PICKER"
    BOOKING_CUSTOMER = "BOOKING_CUSTOMER"


GUARD_ROLE: Final[Mapping[Guard, ActorRole]] = MappingProxyType(
    {
        Guard.ASSIGNED_TECHNICIAN: ActorRole.TECHNICIAN,  # bookings.technician_user_id
        Guard.ASSIGNED_PARTS_PERSON: ActorRole.PARTS_PERSON,  # bookings.parts_person_user_id
        Guard.QC_PICKER: ActorRole.QC_INSPECTOR,  # bookings.qc_inspector_user_id
        Guard.BOOKING_CUSTOMER: ActorRole.CUSTOMER,  # bookings.customer_user_id
    }
)
"""The one actor role each guard constrains. For example COMPLETE and CANCEL check
BOOKING_CUSTOMER for the customer only, never for the SA or Owner (spec 08 T21, T22)."""

SA_OR_OWNER: Final = frozenset({ActorRole.SERVICE_ADVISOR, ActorRole.OWNER})
""""SA, Owner" in spec 08: the Owner performs every Service Advisor booking action and no
technician, parts or QC action (D16)."""

_CUSTOMER: Final = frozenset({ActorRole.CUSTOMER})
_TECHNICIAN: Final = frozenset({ActorRole.TECHNICIAN})
_PARTS_PERSON: Final = frozenset({ActorRole.PARTS_PERSON})
_QC_INSPECTOR: Final = frozenset({ActorRole.QC_INSPECTOR})

TERMINAL_STATUSES: Final = frozenset({BookingStatus.COMPLETED, BookingStatus.CANCELLED})
"""Statuses that accept no action at all (spec 08 principle 7)."""

CANCELLABLE_STATUSES: Final = frozenset(
    {
        BookingStatus.PENDING,
        BookingStatus.CONFIRMED,
        BookingStatus.ASSIGNED,
        BookingStatus.INSPECTING,
        BookingStatus.ESTIMATE_REVIEW,
        BookingStatus.AWAITING_CUSTOMER,
        BookingStatus.ESTIMATE_APPROVED,
        BookingStatus.ESTIMATE_REJECTED,
        BookingStatus.PARTS_PENDING,
        BookingStatus.PARTS_ORDERED,
        BookingStatus.PARTS_READY,
    }
)
"""The 11 statuses CANCEL is accepted from: every status before IN_REPAIR (glossary
section 3, D24)."""


def _no_overrides() -> Mapping[BookingStatus, frozenset[ActorRole]]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True, kw_only=True)
class Rule:
    """One action's row of spec 08's transition (T01-T22) or operation (O1-O5) table.

    Attributes:
        action: The action this rule governs.
        slug: The `.../actions/{slug}` path segment and `allowed_actions` entry (glossary
            section 4); None for CREATE and RECEIVE_PARTS, which have their own endpoints.
        from_statuses: Statuses the action is accepted from (empty for CREATE).
        to_status: Status after the action; None for an operation, which keeps the status.
        actors: Every actor role that may perform the action.
        guard: The assignment guard; it constrains only the role `GUARD_ROLE[guard]`.
        listable: Whether `allowed_actions` may list the action; False for CREATE and
            RECEIVE_PARTS, which are never invoked through `/actions/`.
        actors_by_status: Narrows `actors` for individual statuses. Only EDIT_ESTIMATE
            uses it (O1): the technician edits in INSPECTING, the SA or Owner in
            ESTIMATE_REVIEW.
    """

    action: BookingAction
    slug: str | None
    from_statuses: frozenset[BookingStatus]
    to_status: BookingStatus | None
    actors: frozenset[ActorRole]
    guard: Guard | None = None
    listable: bool = True
    actors_by_status: Mapping[BookingStatus, frozenset[ActorRole]] = field(
        default_factory=_no_overrides, hash=False
    )

    def __post_init__(self) -> None:
        # Freeze a caller-supplied dict so that a rule is immutable all the way down.
        object.__setattr__(self, "actors_by_status", MappingProxyType(dict(self.actors_by_status)))
        problems = [message for broken, message in self._invariants() if broken]
        if problems:
            raise ValueError(f"Invalid rule for {self.action}: {'; '.join(problems)}")

    def _invariants(self) -> tuple[tuple[bool, str], ...]:
        narrowed_actors = frozenset[ActorRole]().union(*self.actors_by_status.values())
        return (
            (self.listable and self.slug is None, "a listable rule needs a slug"),
            (
                not self.from_statuses.isdisjoint(TERMINAL_STATUSES),
                "terminal statuses accept no action",
            ),
            (
                self.guard is not None and GUARD_ROLE[self.guard] not in self.actors,
                "the guard constrains a role that is not an actor",
            ),
            (
                not self.actors_by_status.keys() <= self.from_statuses,
                "actors_by_status names a status outside from_statuses",
            ),
            (
                not narrowed_actors <= self.actors,
                "actors_by_status names a role outside actors",
            ),
        )

    def actors_in(self, status: BookingStatus) -> frozenset[ActorRole]:
        """The roles that may perform the action while the booking is in `status`."""
        if status not in self.from_statuses:
            return frozenset()
        return self.actors_by_status.get(status, self.actors)

    def guard_for(self, role: ActorRole) -> Guard | None:
        """The assignment guard a caller acting as `role` must pass (None: none)."""
        if self.guard is not None and GUARD_ROLE[self.guard] == role:
            return self.guard
        return None


@dataclass(frozen=True, slots=True, kw_only=True)
class ActorContext:
    """The caller, relative to one booking (spec 08 "Who is the actor?").

    The service builds it from the locked booking row. `role` is decided by the endpoint
    family: CUSTOMER on `/api/v1/me/...`, the caller's membership role on
    `/api/v1/shops/{shop_id}/...`. Each flag says whether a booking column holds the
    caller's user id:

    - `is_assigned_technician`: `technician_user_id` (guard ASSIGNED_TECHNICIAN);
    - `is_assigned_parts_person`: `parts_person_user_id` (guard ASSIGNED_PARTS_PERSON);
    - `is_qc_picker`: `qc_inspector_user_id` (guard QC_PICKER);
    - `is_booking_customer`: `customer_user_id` (guard BOOKING_CUSTOMER);
    - `is_booking_technician`: `technician_user_id` again, whatever the caller's role:
      the QC picker may never be the booking's technician (D47).
    """

    role: ActorRole
    is_assigned_technician: bool = False
    is_assigned_parts_person: bool = False
    is_qc_picker: bool = False
    is_booking_customer: bool = False
    is_booking_technician: bool = False

    def satisfies(self, guard: Guard) -> bool:
        """Whether the caller holds the assignment that `guard` asks for."""
        held = {
            Guard.ASSIGNED_TECHNICIAN: self.is_assigned_technician,
            Guard.ASSIGNED_PARTS_PERSON: self.is_assigned_parts_person,
            Guard.QC_PICKER: self.is_qc_picker,
            Guard.BOOKING_CUSTOMER: self.is_booking_customer,
        }
        return held[guard]


class Denial(StrEnum):
    """Why an action was refused. Values are glossary section 10 error codes."""

    FORBIDDEN = "FORBIDDEN"  # 403: the role may not perform the action (incl. D47)
    NOT_ASSIGNED = "NOT_ASSIGNED"  # 403: right role, not the assignee, picker or customer
    INVALID_TRANSITION = "INVALID_TRANSITION"  # 409: not allowed from the current status
    ALREADY_PICKED = "ALREADY_PICKED"  # 409: another QC inspector picked the job first


class TransitionDenied(Exception):  # noqa: N818 (public name agreed with the bookings service)
    """Raised by `check()`; the service maps `code` to the HTTP error with the same code."""

    def __init__(self, code: Denial, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# One rule per BookingAction, in glossary section 4 order. Comments give spec 08 row IDs.
_RULE_TABLE: Final[tuple[Rule, ...]] = (
    # T01: the booking wizard, POST /api/v1/bookings.
    Rule(
        action=BookingAction.CREATE,
        slug=None,
        from_statuses=frozenset(),
        to_status=BookingStatus.PENDING,
        actors=_CUSTOMER,
        listable=False,
    ),
    # T02
    Rule(
        action=BookingAction.CONFIRM,
        slug="confirm",
        from_statuses=frozenset({BookingStatus.PENDING}),
        to_status=BookingStatus.CONFIRMED,
        actors=SA_OR_OWNER,
    ),
    # T03
    Rule(
        action=BookingAction.DECLINE,
        slug="decline",
        from_statuses=frozenset({BookingStatus.PENDING}),
        to_status=BookingStatus.CANCELLED,
        actors=SA_OR_OWNER,
    ),
    # T04
    Rule(
        action=BookingAction.ASSIGN_TECHNICIAN,
        slug="assign-technician",
        from_statuses=frozenset({BookingStatus.CONFIRMED}),
        to_status=BookingStatus.ASSIGNED,
        actors=SA_OR_OWNER,
    ),
    # T05
    Rule(
        action=BookingAction.START_INSPECTION,
        slug="start-inspection",
        from_statuses=frozenset({BookingStatus.ASSIGNED}),
        to_status=BookingStatus.INSPECTING,
        actors=_TECHNICIAN,
        guard=Guard.ASSIGNED_TECHNICIAN,
    ),
    # O1: listed as edit-estimate, performed with PUT .../estimate. The assigned technician
    # edits while INSPECTING, the SA or Owner while ESTIMATE_REVIEW.
    Rule(
        action=BookingAction.EDIT_ESTIMATE,
        slug="edit-estimate",
        from_statuses=frozenset({BookingStatus.INSPECTING, BookingStatus.ESTIMATE_REVIEW}),
        to_status=None,
        actors=_TECHNICIAN | SA_OR_OWNER,
        guard=Guard.ASSIGNED_TECHNICIAN,
        actors_by_status={
            BookingStatus.INSPECTING: _TECHNICIAN,
            BookingStatus.ESTIMATE_REVIEW: SA_OR_OWNER,
        },
    ),
    # T06
    Rule(
        action=BookingAction.SUBMIT_ESTIMATE,
        slug="submit-estimate",
        from_statuses=frozenset({BookingStatus.INSPECTING}),
        to_status=BookingStatus.ESTIMATE_REVIEW,
        actors=_TECHNICIAN,
        guard=Guard.ASSIGNED_TECHNICIAN,
    ),
    # T07
    Rule(
        action=BookingAction.SEND_ESTIMATE,
        slug="send-estimate",
        from_statuses=frozenset({BookingStatus.ESTIMATE_REVIEW}),
        to_status=BookingStatus.AWAITING_CUSTOMER,
        actors=SA_OR_OWNER,
    ),
    # T08 (customer endpoint)
    Rule(
        action=BookingAction.APPROVE_ESTIMATE,
        slug="approve-estimate",
        from_statuses=frozenset({BookingStatus.AWAITING_CUSTOMER}),
        to_status=BookingStatus.ESTIMATE_APPROVED,
        actors=_CUSTOMER,
        guard=Guard.BOOKING_CUSTOMER,
    ),
    # T09 (customer endpoint)
    Rule(
        action=BookingAction.REJECT_ESTIMATE,
        slug="reject-estimate",
        from_statuses=frozenset({BookingStatus.AWAITING_CUSTOMER}),
        to_status=BookingStatus.ESTIMATE_REJECTED,
        actors=_CUSTOMER,
        guard=Guard.BOOKING_CUSTOMER,
    ),
    # T10
    Rule(
        action=BookingAction.REVISE_ESTIMATE,
        slug="revise-estimate",
        from_statuses=frozenset({BookingStatus.ESTIMATE_REJECTED}),
        to_status=BookingStatus.ESTIMATE_REVIEW,
        actors=SA_OR_OWNER,
    ),
    # T11
    Rule(
        action=BookingAction.RETURN_TO_TECHNICIAN,
        slug="return-to-technician",
        from_statuses=frozenset({BookingStatus.ESTIMATE_REJECTED}),
        to_status=BookingStatus.INSPECTING,
        actors=SA_OR_OWNER,
    ),
    # T12
    Rule(
        action=BookingAction.ASSIGN_PARTS_PERSON,
        slug="assign-parts-person",
        from_statuses=frozenset({BookingStatus.ESTIMATE_APPROVED}),
        to_status=BookingStatus.PARTS_PENDING,
        actors=SA_OR_OWNER,
    ),
    # T13
    Rule(
        action=BookingAction.ORDER_PARTS,
        slug="order-parts",
        from_statuses=frozenset({BookingStatus.PARTS_PENDING}),
        to_status=BookingStatus.PARTS_ORDERED,
        actors=_PARTS_PERSON,
        guard=Guard.ASSIGNED_PARTS_PERSON,
    ),
    # T14
    Rule(
        action=BookingAction.MARK_PARTS_READY,
        slug="mark-parts-ready",
        from_statuses=frozenset({BookingStatus.PARTS_PENDING, BookingStatus.PARTS_ORDERED}),
        to_status=BookingStatus.PARTS_READY,
        actors=_PARTS_PERSON,
        guard=Guard.ASSIGNED_PARTS_PERSON,
    ),
    # T15: fired by POST .../purchase-orders/{po_id}/receive; any active parts person.
    Rule(
        action=BookingAction.RECEIVE_PARTS,
        slug=None,
        from_statuses=frozenset({BookingStatus.PARTS_ORDERED}),
        to_status=BookingStatus.PARTS_READY,
        actors=_PARTS_PERSON,
        listable=False,
    ),
    # T16
    Rule(
        action=BookingAction.ALLOCATE_PARTS,
        slug="allocate-parts",
        from_statuses=frozenset({BookingStatus.PARTS_READY}),
        to_status=BookingStatus.IN_REPAIR,
        actors=_PARTS_PERSON,
        guard=Guard.ASSIGNED_PARTS_PERSON,
    ),
    # O2
    Rule(
        action=BookingAction.START_REPAIR,
        slug="start-repair",
        from_statuses=frozenset({BookingStatus.IN_REPAIR}),
        to_status=None,
        actors=_TECHNICIAN,
        guard=Guard.ASSIGNED_TECHNICIAN,
    ),
    # T17
    Rule(
        action=BookingAction.SEND_TO_QC,
        slug="send-to-qc",
        from_statuses=frozenset({BookingStatus.IN_REPAIR}),
        to_status=BookingStatus.QC_PENDING,
        actors=_TECHNICIAN,
        guard=Guard.ASSIGNED_TECHNICIAN,
    ),
    # T18: any active QC inspector; first pick wins; never the booking's technician (D47).
    Rule(
        action=BookingAction.PICK_QC,
        slug="pick-qc",
        from_statuses=frozenset({BookingStatus.QC_PENDING}),
        to_status=BookingStatus.QC_IN_PROGRESS,
        actors=_QC_INSPECTOR,
    ),
    # T19
    Rule(
        action=BookingAction.PASS_QC,
        slug="pass-qc",
        from_statuses=frozenset({BookingStatus.QC_IN_PROGRESS}),
        to_status=BookingStatus.READY_FOR_PICKUP,
        actors=_QC_INSPECTOR,
        guard=Guard.QC_PICKER,
    ),
    # T20
    Rule(
        action=BookingAction.FAIL_QC,
        slug="fail-qc",
        from_statuses=frozenset({BookingStatus.QC_IN_PROGRESS}),
        to_status=BookingStatus.IN_REPAIR,
        actors=_QC_INSPECTOR,
        guard=Guard.QC_PICKER,
    ),
    # O3
    Rule(
        action=BookingAction.NOTIFY_READY,
        slug="notify-ready",
        from_statuses=frozenset({BookingStatus.READY_FOR_PICKUP}),
        to_status=None,
        actors=SA_OR_OWNER,
    ),
    # T21: staff or customer endpoint; the guard binds the customer only (D28).
    Rule(
        action=BookingAction.COMPLETE,
        slug="complete",
        from_statuses=frozenset({BookingStatus.READY_FOR_PICKUP}),
        to_status=BookingStatus.COMPLETED,
        actors=SA_OR_OWNER | _CUSTOMER,
        guard=Guard.BOOKING_CUSTOMER,
    ),
    # T22: staff or customer endpoint; the guard binds the customer only (D24).
    Rule(
        action=BookingAction.CANCEL,
        slug="cancel",
        from_statuses=CANCELLABLE_STATUSES,
        to_status=BookingStatus.CANCELLED,
        actors=SA_OR_OWNER | _CUSTOMER,
        guard=Guard.BOOKING_CUSTOMER,
    ),
    # O4, a P1 extra (D36)
    Rule(
        action=BookingAction.REASSIGN_TECHNICIAN,
        slug="reassign-technician",
        from_statuses=frozenset(
            {BookingStatus.ASSIGNED, BookingStatus.INSPECTING, BookingStatus.IN_REPAIR}
        ),
        to_status=None,
        actors=SA_OR_OWNER,
    ),
    # O5, a P1 extra (D36)
    Rule(
        action=BookingAction.REASSIGN_PARTS_PERSON,
        slug="reassign-parts-person",
        from_statuses=frozenset(
            {BookingStatus.PARTS_PENDING, BookingStatus.PARTS_ORDERED, BookingStatus.PARTS_READY}
        ),
        to_status=None,
        actors=SA_OR_OWNER,
    ),
)

RULES: Final[Mapping[BookingAction, Rule]] = MappingProxyType(
    {rule.action: rule for rule in _RULE_TABLE}
)
"""Every `BookingAction` and its rule: the one source of truth (spec 08 principle 1)."""

ACTION_TO_SLUG: Final[Mapping[BookingAction, str]] = MappingProxyType(
    {rule.action: rule.slug for rule in _RULE_TABLE if rule.slug is not None}
)
"""Glossary section 4 slugs of the 25 actions that have one. `edit-estimate` is listed in
`allowed_actions` but performed with PUT .../estimate (O1), so the `/actions/{slug}`
router must not dispatch it."""

SLUG_TO_ACTION: Final[Mapping[str, BookingAction]] = MappingProxyType(
    {slug: action for action, slug in ACTION_TO_SLUG.items()}
)
"""The inverse of `ACTION_TO_SLUG`."""

_LISTED: Final[tuple[tuple[str, Rule], ...]] = tuple(
    (ACTION_TO_SLUG[action], RULES[action]) for action in BookingAction if RULES[action].listable
)
"""(slug, rule) of every listable action, in `BookingAction` (glossary section 4) order."""

_GUARD_HOLDER: Final[Mapping[Guard, str]] = MappingProxyType(
    {
        Guard.ASSIGNED_TECHNICIAN: "the booking's assigned technician",
        Guard.ASSIGNED_PARTS_PERSON: "the booking's assigned parts person",
        Guard.QC_PICKER: "the QC inspector who picked this job",
        Guard.BOOKING_CUSTOMER: "the booking's customer",
    }
)


def _invalid_transition(rule: Rule, status: BookingStatus) -> TransitionDenied:
    name = rule.slug or rule.action.value
    return TransitionDenied(
        Denial.INVALID_TRANSITION, f"'{name}' is not allowed while the booking is {status}."
    )


def _denial(rule: Rule, status: BookingStatus, ctx: ActorContext) -> TransitionDenied | None:
    """Spec 08 check order for one rule; None means `ctx` may perform it right now."""
    name = rule.slug or rule.action.value
    # 1. Role -> 403 FORBIDDEN. D47: the booking's technician never picks its own QC.
    if ctx.role not in rule.actors:
        return TransitionDenied(Denial.FORBIDDEN, f"The {ctx.role} role may not perform '{name}'.")
    if rule.action == BookingAction.PICK_QC and ctx.is_booking_technician:
        return TransitionDenied(
            Denial.FORBIDDEN, "The booking's technician may not perform its quality check."
        )
    # 2. Assignment -> 403 NOT_ASSIGNED, for the role the guard binds.
    guard = rule.guard_for(ctx.role)
    if guard is not None and not ctx.satisfies(guard):
        return TransitionDenied(
            Denial.NOT_ASSIGNED, f"Only {_GUARD_HOLDER[guard]} may perform '{name}'."
        )
    # 3. Status -> 409. Terminal statuses accept nothing; PICK_QC is first-wins (T18).
    if status in TERMINAL_STATUSES or ctx.role not in rule.actors_in(status):
        if rule.action == BookingAction.PICK_QC and status == BookingStatus.QC_IN_PROGRESS:
            return TransitionDenied(
                Denial.ALREADY_PICKED, "Another QC inspector has already picked this job."
            )
        return _invalid_transition(rule, status)
    return None


def check(action: BookingAction, status: BookingStatus, ctx: ActorContext) -> Rule:
    """Return the rule for `action` if `ctx` may perform it now; else raise `TransitionDenied`.

    Check order (spec 08 steps 5-7, glossary section 10): role (FORBIDDEN, including the
    D47 picker rule) -> assignment guard (NOT_ASSIGNED) -> status (INVALID_TRANSITION, or
    ALREADY_PICKED for PICK_QC on QC_IN_PROGRESS). Visibility (404), `expected_version`
    and data guards (stock, checklist, payload) are the service's job.
    """
    rule = RULES[action]
    denial = _denial(rule, status, ctx)
    if denial is not None:
        raise denial
    return rule


def next_status(rule: Rule, current: BookingStatus) -> BookingStatus:
    """The booking's status after `rule` is applied from `current`.

    An operation keeps `current`. A status the rule does not accept raises
    INVALID_TRANSITION, so a rule can never be applied from the wrong status; CREATE has
    no source status, so the service uses `RULES[BookingAction.CREATE].to_status`.
    """
    if current not in rule.from_statuses:
        raise _invalid_transition(rule, current)
    return current if rule.to_status is None else rule.to_status


def allowed_actions(status: BookingStatus, ctx: ActorContext) -> list[str]:
    """The slugs `ctx` may perform on a booking in `status` (spec 08 `allowed_actions`).

    A slug is listed exactly when `check()` would accept its action: the rule is listable,
    the role may act from `status` and the assignment guard passes. Data guards (stock,
    checklist, empty estimate) are not evaluated. The order is stable: `BookingAction`
    declaration order, which is the glossary section 4 table order.
    """
    return [slug for slug, rule in _LISTED if _denial(rule, status, ctx) is None]

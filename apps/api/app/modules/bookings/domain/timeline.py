"""Timelines, the customer's view of them and the action-route families (spec 03 §3.3, §5.1;
`modules/bookings.md` §7.8, §7.10). Pure.

- `is_status_change`: the rule behind `status_changed_at` (the `CREATE` event counts; operations
  such as `start-repair`, `notify-ready` or an estimate edit never do).
- The customer projection of a timeline: `EDIT_ESTIMATE`, `REASSIGN_TECHNICIAN` and
  `REASSIGN_PARTS_PERSON` are omitted; a note is shown only for `DECLINE`, `CANCEL` and
  `REJECT_ESTIMATE` (customer-facing reasons); actor names, roles and metadata never appear.
- `UNROUTED_SLUGS`: slugs hidden from `allowed_actions` until their routes exist. The P1
  `reassign-*` routes ship with this module, so it is empty; it stays as the switch for any future
  slug (spec 03 §3.3: a listed slug always has a route).
- The two endpoint families (D48, spec 03 §5.1), generated from spec 08's rule table: the staff
  family serves every listable action one of whose actors is staff, except `edit-estimate` (the
  `PUT …/estimate` route); the customer family serves every listable action of the customer.
"""

from collections.abc import Iterable
from typing import Final

from app.modules.bookings.domain.state_machine import ACTION_TO_SLUG, RULES
from app.shared.enums import ActorRole, BookingAction, BookingStatus

__all__ = [
    "CUSTOMER_HIDDEN_ACTIONS",
    "CUSTOMER_NOTE_ACTIONS",
    "NOT_ROUTED_AS_ACTION",
    "UNROUTED_SLUGS",
    "customer_note",
    "customer_route_actions",
    "is_customer_visible",
    "is_status_change",
    "routed",
    "staff_route_actions",
]

CUSTOMER_HIDDEN_ACTIONS: Final = frozenset(
    {
        BookingAction.EDIT_ESTIMATE,
        BookingAction.REASSIGN_TECHNICIAN,
        BookingAction.REASSIGN_PARTS_PERSON,
    }
)
"""Events a customer's timeline never shows (spec 03 §3.3)."""

CUSTOMER_NOTE_ACTIONS: Final = frozenset(
    {BookingAction.DECLINE, BookingAction.CANCEL, BookingAction.REJECT_ESTIMATE}
)
"""The only events whose note (a customer-facing reason) a customer sees (spec 04 §C)."""

UNROUTED_SLUGS: Final[frozenset[str]] = frozenset()
"""Slugs left out of `allowed_actions` because their route does not exist yet (none today)."""

NOT_ROUTED_AS_ACTION: Final = frozenset({BookingAction.EDIT_ESTIMATE})
"""Listed in `allowed_actions` but performed with `PUT …/estimate`, never `/actions/{slug}`."""

_STAFF_ROLES: Final = frozenset(ActorRole) - {ActorRole.CUSTOMER, ActorRole.SYSTEM}


def is_status_change(from_status: BookingStatus | None, to_status: BookingStatus) -> bool:
    """An event that moved the booking: `CREATE` (no source status) or a real transition."""
    return from_status is None or from_status != to_status


def is_customer_visible(action: BookingAction) -> bool:
    """Whether the customer's timeline shows events of `action`."""
    return action not in CUSTOMER_HIDDEN_ACTIONS


def customer_note(action: BookingAction, note: str | None) -> str | None:
    """The note a customer may read: only a decline, cancel or reject reason."""
    return note if action in CUSTOMER_NOTE_ACTIONS else None


def routed(slugs: Iterable[str]) -> list[str]:
    """`allowed_actions` without the slugs that have no route yet (order kept)."""
    return [slug for slug in slugs if slug not in UNROUTED_SLUGS]


def _route_slug_is_open(action: BookingAction) -> bool:
    return ACTION_TO_SLUG[action] not in UNROUTED_SLUGS


def staff_route_actions() -> tuple[BookingAction, ...]:
    """Actions with a staff `POST …/bookings/{booking_id}/actions/{slug}` route, in glossary §4
    order: every listable rule one of whose actors is staff, except `edit-estimate`."""
    return tuple(
        action
        for action in BookingAction
        if RULES[action].listable
        and action not in NOT_ROUTED_AS_ACTION
        and not RULES[action].actors.isdisjoint(_STAFF_ROLES)
        and _route_slug_is_open(action)
    )


def customer_route_actions() -> tuple[BookingAction, ...]:
    """Actions with a customer `POST /api/v1/me/bookings/{booking_id}/actions/{slug}` route."""
    return tuple(
        action
        for action in BookingAction
        if RULES[action].listable
        and ActorRole.CUSTOMER in RULES[action].actors
        and _route_slug_is_open(action)
    )

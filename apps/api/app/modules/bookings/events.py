"""Events the bookings module publishes (glossary §7.1, spec 01 events, `modules/bookings.md` §8).

Both are published inside the action's transaction (spec 08 step 13). The notifications module
subscribes to them: it writes the notification rows in the same transaction and queues the
after-commit pushes (`notification.created`, `booking.updated`) and e-mails (D14, D26, D90).

This file is a fixed contract shared by the bookings and notifications modules: change a field
only together with both modules, spec 01's event catalogue and `modules/bookings.md` §8.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.shared.enums import ActorRole, BookingAction, BookingStatus
from app.shared.event_bus import Event


@dataclass(frozen=True, slots=True, kw_only=True)
class BookingActionApplied(Event):
    """A transition or operation was applied, including `CREATE`, `RECEIVE_PARTS` and an
    `EDIT_ESTIMATE` that created a new estimate version (`modules/bookings.md` §7.4 step 13).

    The assignee fields hold the values **after** the action. `occurred_at` is the action's single
    clock instant (D63), equal to the `booking_events.created_at` of the event row it reports.
    """

    shop_id: UUID
    booking_id: UUID
    reference: str
    action: BookingAction
    from_status: BookingStatus | None  # None only for CREATE
    to_status: BookingStatus  # equals from_status for an operation
    version: int  # the booking's version after the action
    actor_user_id: UUID | None  # None only when actor_role is SYSTEM
    actor_role: ActorRole
    customer_user_id: UUID
    technician_user_id: UUID | None
    parts_person_user_id: UUID | None
    qc_inspector_user_id: UUID | None
    note: str | None
    metadata: Mapping[str, Any] = field(default_factory=dict)  # the event row's metadata (JSON)


@dataclass(frozen=True, slots=True, kw_only=True)
class BookingPartsChanged(Event):
    """A booking's parts state changed without a booking event (D83): a purchase-order receipt
    reserved stock for a `PARTS_ORDERED` booking without completing it. `status` and `version`
    are unchanged; notifications pushes `booking.updated` to the booking's viewers and writes no
    row (`modules/bookings.md` §7.7)."""

    shop_id: UUID
    booking_id: UUID
    status: BookingStatus
    version: int

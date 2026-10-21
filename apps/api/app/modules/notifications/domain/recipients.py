"""The notification trigger table and the recipient rules (pure; `modules/notifications.md`).

The trigger table is glossary §6 / spec 08's "Notifications" column: which `BookingAction` fires
which `NotificationType`, and to whom, in the table's order. `CANCEL` splits on the actor: a
customer's cancel goes to the staff working on the booking, anyone else's to the customer.

Recipient rules (D9, D26, D91):
1. "SAs of the shop" = the active Service Advisors; with none, the shop's Owner (as `OWNER`).
2. Named staff (the technician and parts person **after** the action) only while they are still
   active members of the shop, so a deactivated assignee (D19) gets nothing.
3. QC inspectors = every active one; none → nobody (no fallback).
4. The customer always (customers are global: no membership check).
5. One row per user and action: a user who qualifies twice keeps the first role in the table's
   order. The actor is never excluded (D91).
6. `SYSTEM` is never a recipient.

The service reads the live facts (`RecipientFacts`) and this module decides; it imports nothing but
the shared enums.
"""

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from app.shared.enums import ActorRole, BookingAction, NotificationType


class Audience(StrEnum):
    """A recipient group of the trigger table."""

    SHOP_ADVISORS = "SHOP_ADVISORS"  # "SAs of the shop" (Owner fallback, D26)
    CUSTOMER = "CUSTOMER"  # the booking's customer
    TECHNICIAN = "TECHNICIAN"  # the booking's technician after the action
    PARTS_PERSON = "PARTS_PERSON"  # the booking's parts person after the action
    QC_INSPECTORS = "QC_INSPECTORS"  # every active QC inspector (no fallback)


@dataclass(frozen=True, slots=True)
class Trigger:
    """One row of the trigger table: the type and its audiences, in the table's order."""

    type: NotificationType
    audiences: tuple[Audience, ...]


_SAS = (Audience.SHOP_ADVISORS,)
_CUSTOMER = (Audience.CUSTOMER,)
_TECHNICIAN = (Audience.TECHNICIAN,)

TRIGGERS: Mapping[BookingAction, Trigger] = MappingProxyType(
    {
        BookingAction.CREATE: Trigger(NotificationType.BOOKING_CREATED, _SAS),
        BookingAction.CONFIRM: Trigger(NotificationType.BOOKING_CONFIRMED, _CUSTOMER),
        BookingAction.ASSIGN_TECHNICIAN: Trigger(NotificationType.TECHNICIAN_ASSIGNED, _TECHNICIAN),
        BookingAction.REASSIGN_TECHNICIAN: Trigger(
            NotificationType.TECHNICIAN_ASSIGNED, _TECHNICIAN
        ),
        BookingAction.SUBMIT_ESTIMATE: Trigger(NotificationType.ESTIMATE_SUBMITTED, _SAS),
        BookingAction.SEND_ESTIMATE: Trigger(NotificationType.ESTIMATE_SENT, _CUSTOMER),
        BookingAction.APPROVE_ESTIMATE: Trigger(NotificationType.ESTIMATE_APPROVED, _SAS),
        BookingAction.REJECT_ESTIMATE: Trigger(NotificationType.ESTIMATE_REJECTED, _SAS),
        BookingAction.RETURN_TO_TECHNICIAN: Trigger(
            NotificationType.ESTIMATE_RETURNED, _TECHNICIAN
        ),
        BookingAction.ASSIGN_PARTS_PERSON: Trigger(
            NotificationType.PARTS_NEEDED, (Audience.PARTS_PERSON,)
        ),
        BookingAction.REASSIGN_PARTS_PERSON: Trigger(
            NotificationType.PARTS_NEEDED, (Audience.PARTS_PERSON,)
        ),
        BookingAction.ALLOCATE_PARTS: Trigger(NotificationType.PARTS_READY, _TECHNICIAN),
        BookingAction.SEND_TO_QC: Trigger(NotificationType.QC_REQUESTED, (Audience.QC_INSPECTORS,)),
        BookingAction.FAIL_QC: Trigger(NotificationType.QC_FAILED, _TECHNICIAN),
        BookingAction.PASS_QC: Trigger(NotificationType.QC_PASSED, _SAS),
        BookingAction.NOTIFY_READY: Trigger(NotificationType.VEHICLE_READY, _CUSTOMER),
        BookingAction.DECLINE: Trigger(NotificationType.BOOKING_CANCELLED, _CUSTOMER),
    }
)
"""Every action with a notification except `CANCEL` (see `trigger_for`)."""

CUSTOMER_CANCEL = Trigger(
    NotificationType.BOOKING_CANCELLED,
    (Audience.SHOP_ADVISORS, Audience.TECHNICIAN, Audience.PARTS_PERSON),
)
"""`CANCEL` by the customer: SAs of the shop + the assigned technician + parts person."""

STAFF_CANCEL = Trigger(NotificationType.BOOKING_CANCELLED, _CUSTOMER)
"""`CANCEL` by an SA or the Owner (anyone but the customer): the customer."""

AUDIENCE_ROLE: Mapping[Audience, ActorRole] = MappingProxyType(
    {
        Audience.SHOP_ADVISORS: ActorRole.SERVICE_ADVISOR,
        Audience.CUSTOMER: ActorRole.CUSTOMER,
        Audience.TECHNICIAN: ActorRole.TECHNICIAN,
        Audience.PARTS_PERSON: ActorRole.PARTS_PERSON,
        Audience.QC_INSPECTORS: ActorRole.QC_INSPECTOR,
    }
)
"""The `recipient_role` of each audience (the SA fallback to the Owner uses `OWNER`)."""

EMAILED_TYPES: frozenset[NotificationType] = frozenset(
    {NotificationType.ESTIMATE_SENT, NotificationType.VEHICLE_READY}
)
"""The only types that are also e-mailed, and only to the customer (D26)."""


def trigger_for(action: BookingAction, actor_role: ActorRole) -> Trigger | None:
    """The trigger table row for an action, or None when the action notifies nobody."""
    if action == BookingAction.CANCEL:
        return CUSTOMER_CANCEL if actor_role == ActorRole.CUSTOMER else STAFF_CANCEL
    return TRIGGERS.get(action)


@dataclass(frozen=True, slots=True)
class Recipient:
    """One notification row's addressee and the role it is notified as (D67)."""

    user_id: UUID
    role: ActorRole


@dataclass(frozen=True, slots=True, kw_only=True)
class RecipientFacts:
    """The live facts one action's recipients are resolved from.

    The assignee ids are the event's (the state after the action); the id lists come from the
    database: only what the trigger's audiences need is read.
    """

    customer_user_id: UUID
    technician_user_id: UUID | None = None
    parts_person_user_id: UUID | None = None
    service_advisor_ids: Sequence[UUID] = ()  # active SAs (membership and account)
    owner_user_id: UUID | None = None  # read only when there is no active SA
    qc_inspector_ids: Sequence[UUID] = ()  # active QC inspectors
    active_member_ids: Collection[UUID] = frozenset()  # every active member of the shop


def named_staff_ids(
    trigger: Trigger, *, technician_user_id: UUID | None, parts_person_user_id: UUID | None
) -> set[UUID]:
    """The assignees the trigger names, whose active membership must be checked (D9)."""
    named: set[UUID] = set()
    if Audience.TECHNICIAN in trigger.audiences and technician_user_id is not None:
        named.add(technician_user_id)
    if Audience.PARTS_PERSON in trigger.audiences and parts_person_user_id is not None:
        named.add(parts_person_user_id)
    return named


def _shop_advisors(facts: RecipientFacts) -> list[Recipient]:
    """Rule 1 (D26): the active SAs, else the Owner as `OWNER`."""
    if facts.service_advisor_ids:
        return [
            Recipient(user_id, ActorRole.SERVICE_ADVISOR) for user_id in facts.service_advisor_ids
        ]
    if facts.owner_user_id is not None:
        return [Recipient(facts.owner_user_id, ActorRole.OWNER)]
    return []


def _named(assignee: UUID | None, role: ActorRole, facts: RecipientFacts) -> list[Recipient]:
    """Rule 2 (D9): a named assignee only while still an active member of the shop."""
    if assignee is None or assignee not in facts.active_member_ids:
        return []
    return [Recipient(assignee, role)]


def _members_of(audience: Audience, facts: RecipientFacts) -> Iterable[Recipient]:
    role = AUDIENCE_ROLE[audience]
    if audience == Audience.SHOP_ADVISORS:
        return _shop_advisors(facts)
    if audience == Audience.CUSTOMER:
        return [Recipient(facts.customer_user_id, role)]
    if audience == Audience.QC_INSPECTORS:
        return [Recipient(user_id, role) for user_id in facts.qc_inspector_ids]
    if audience == Audience.TECHNICIAN:
        return _named(facts.technician_user_id, role, facts)
    return _named(facts.parts_person_user_id, role, facts)


def resolve_recipients(trigger: Trigger, facts: RecipientFacts) -> list[Recipient]:
    """The recipients of one action, in the table's order, one per user (D91)."""
    recipients: list[Recipient] = []
    seen: set[UUID] = set()
    for audience in trigger.audiences:
        for recipient in _members_of(audience, facts):
            if recipient.role == ActorRole.SYSTEM or recipient.user_id in seen:
                continue
            seen.add(recipient.user_id)
            recipients.append(recipient)
    return recipients

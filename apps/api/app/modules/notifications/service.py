"""Use cases of the notifications module (`modules/notifications.md`).

- Row creation (nested; called by this module's handler inside the publisher's transaction; never
  commits): `create_for_booking_action` — the trigger table, the recipient rules (D9, D26, D91),
  the texts and the links (D67), one `INSERT … VALUES …` with `created_at = occurred_at` (D63).
- The bell (spec 03 §4.12): `list_for_user`, `count_unread` (reads); `mark_read`, `mark_all_read`
  (top-level, commit; idempotent).
- The realtime ticket (D70): `issue_ws_ticket` — a 60-second `typ = ws` JWT, no server state.
- Seed support (spec 11 "Notifications after seeding"): `list_for_bookings`, `mark_read_bulk`.

Nobody calls this module to send something: notifications follow events (spec 01 rule 4). Lower
modules are read through their services only; bookings facts through `get_booking_refs` (D86).
"""

import logging
import uuid
from collections import defaultdict
from collections.abc import Collection, Sequence
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.security import WS_TICKET_LIFETIME_SECONDS, issue_token
from app.modules.bookings import service as bookings_service
from app.modules.bookings.events import BookingActionApplied
from app.modules.identity import service as identity_service
from app.modules.notifications.domain.links import link_for
from app.modules.notifications.domain.messages import (
    MessageContext,
    clean_note,
    compose,
    estimate_version,
    format_pkr,
    truncate,
)
from app.modules.notifications.domain.recipients import (
    Audience,
    Recipient,
    RecipientFacts,
    Trigger,
    named_staff_ids,
    resolve_recipients,
    trigger_for,
)
from app.modules.notifications.models import Notification
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import (
    NewNotification,
    NotificationRead,
    NotificationRecord,
    RealtimeTicketRead,
)
from app.modules.shops import service as shops_service
from app.shared.clock import utcnow
from app.shared.enums import ActorRole, MembershipRole, NotificationType
from app.shared.pagination import Page, PageParams
from app.shared.uow import UnitOfWork

if TYPE_CHECKING:  # the calls package is optional (spec 01 rule 6)
    from app.modules.calls.events import AiTaskCreated, CallStateChanged

logger = logging.getLogger(__name__)

ALL_MEMBERSHIP_ROLES = tuple(MembershipRole)


# --- Row creation (inside the action's transaction) ---------------------------------------------


async def _owner_or_none(session: AsyncSession, *, shop_id: uuid.UUID) -> uuid.UUID | None:
    """The D26 fallback. Every shop has exactly one Owner (D15); should that ever be broken, the
    action still succeeds without the row instead of failing on a notification."""
    try:
        return await shops_service.get_owner_user_id(session, shop_id=shop_id)
    except NotFound:
        logger.error("notifications.shop_without_owner", extra={"shop_id": str(shop_id)})
        return None


async def _recipient_facts(
    session: AsyncSession, event: BookingActionApplied, trigger: Trigger
) -> RecipientFacts:
    """Read only the live facts the trigger's audiences need (D9: memberships at action time)."""
    advisors: list[uuid.UUID] = []
    owner: uuid.UUID | None = None
    if Audience.SHOP_ADVISORS in trigger.audiences:
        advisors = await shops_service.list_active_member_ids(
            session, shop_id=event.shop_id, roles=[MembershipRole.SERVICE_ADVISOR]
        )
        if not advisors:
            owner = await _owner_or_none(session, shop_id=event.shop_id)
    inspectors: list[uuid.UUID] = []
    if Audience.QC_INSPECTORS in trigger.audiences:
        inspectors = await shops_service.list_active_member_ids(
            session, shop_id=event.shop_id, roles=[MembershipRole.QC_INSPECTOR]
        )
    active_members: frozenset[uuid.UUID] = frozenset()
    named = named_staff_ids(
        trigger,
        technician_user_id=event.technician_user_id,
        parts_person_user_id=event.parts_person_user_id,
    )
    if named:
        active_members = frozenset(
            await shops_service.list_active_member_ids(
                session, shop_id=event.shop_id, roles=ALL_MEMBERSHIP_ROLES
            )
        )
    return RecipientFacts(
        customer_user_id=event.customer_user_id,
        technician_user_id=event.technician_user_id,
        parts_person_user_id=event.parts_person_user_id,
        service_advisor_ids=advisors,
        owner_user_id=owner,
        qc_inspector_ids=inspectors,
        active_member_ids=active_members,
    )


async def _message_context(session: AsyncSession, event: BookingActionApplied) -> MessageContext:
    """Names (shop, actor, customer), the estimate version and total, and the note."""
    briefs = await shops_service.get_shop_briefs(session, shop_ids=[event.shop_id])
    shop = briefs.get(event.shop_id)
    wanted = {event.customer_user_id}
    if event.actor_user_id is not None:
        wanted.add(event.actor_user_id)
    users = await identity_service.get_users_by_ids(session, wanted)
    actor = users.get(event.actor_user_id) if event.actor_user_id is not None else None
    customer = users.get(event.customer_user_id)
    metadata = event.metadata or {}
    return MessageContext(
        reference=event.reference,
        shop_name=shop.name if shop is not None else None,
        actor_name=actor.full_name if actor is not None else None,
        actor_role=event.actor_role,
        customer_name=customer.full_name if customer is not None else None,
        version=estimate_version(metadata.get("version")),
        total=format_pkr(metadata.get("grand_total")),
        note=clean_note(event.note),
    )


def _new_row(
    event: BookingActionApplied, trigger: Trigger, recipient: Recipient, context: MessageContext
) -> NewNotification:
    title, body = compose(trigger.type, recipient.role, context)
    return NewNotification(
        id=uuid.uuid4(),
        recipient_user_id=recipient.user_id,
        recipient_role=recipient.role,
        shop_id=event.shop_id,
        booking_id=event.booking_id,
        type=trigger.type,
        title=title,
        body=body,
        link=link_for(
            recipient.role, trigger.type, shop_id=event.shop_id, booking_id=event.booking_id
        ),
        created_at=event.occurred_at,
    )


async def create_for_booking_action(
    uow: UnitOfWork, event: BookingActionApplied
) -> list[NotificationRecord]:
    """Write the rows the action fires (glossary §6), in the caller's transaction; never commits.

    Returns them in recipient order (empty when the action has no type or no recipient). Any
    failure raises and rolls the whole action back (NOT-07).
    """
    trigger = trigger_for(event.action, event.actor_role)
    if trigger is None:
        return []
    session = uow.session
    recipients = resolve_recipients(trigger, await _recipient_facts(session, event, trigger))
    if not recipients:
        return []
    context = await _message_context(session, event)
    rows = [_new_row(event, trigger, recipient, context) for recipient in recipients]
    await NotificationRepository(session).insert_many(rows)
    return [
        NotificationRecord(
            id=row.id,
            type=row.type,
            title=row.title,
            body=row.body,
            recipient_role=row.recipient_role,
            link=row.link,
            shop_id=row.shop_id,
            shop_name=context.shop_name,
            booking_id=row.booking_id,
            booking_reference=event.reference,
            read_at=None,
            created_at=row.created_at,
            recipient_user_id=row.recipient_user_id,
        )
        for row in rows
    ]


# --- Reads --------------------------------------------------------------------------------------


async def _shop_names(session: AsyncSession, rows: Sequence[Notification]) -> dict[uuid.UUID, str]:
    shop_ids = {row.shop_id for row in rows if row.shop_id is not None}
    if not shop_ids:
        return {}
    briefs = await shops_service.get_shop_briefs(session, shop_ids=shop_ids)
    return {shop_id: brief.name for shop_id, brief in briefs.items()}


async def _booking_references(
    session: AsyncSession, rows: Sequence[Notification]
) -> dict[uuid.UUID, str]:
    """Booking references by id: one `get_booking_refs` call per shop on the page (D86)."""
    by_shop: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for row in rows:
        if row.shop_id is not None and row.booking_id is not None:
            by_shop[row.shop_id].add(row.booking_id)
    references: dict[uuid.UUID, str] = {}
    for shop_id, booking_ids in by_shop.items():
        refs = await bookings_service.get_booking_refs(
            session, shop_id=shop_id, booking_ids=booking_ids
        )
        references.update({booking_id: ref.reference for booking_id, ref in refs.items()})
    return references


async def _records(session: AsyncSession, rows: Sequence[Notification]) -> list[NotificationRecord]:
    shop_names = await _shop_names(session, rows)
    references = await _booking_references(session, rows)
    return [
        NotificationRecord(
            id=row.id,
            type=row.type,
            title=row.title,
            body=row.body,
            recipient_role=row.recipient_role,
            link=row.link,
            shop_id=row.shop_id,
            shop_name=shop_names.get(row.shop_id) if row.shop_id is not None else None,
            booking_id=row.booking_id,
            booking_reference=(
                references.get(row.booking_id) if row.booking_id is not None else None
            ),
            read_at=row.read_at,
            created_at=row.created_at,
            recipient_user_id=row.recipient_user_id,
        )
        for row in rows
    ]


async def list_for_user(
    session: AsyncSession, *, user_id: uuid.UUID, unread_only: bool, page: PageParams
) -> Page[NotificationRead]:
    """`GET /api/v1/me/notifications`: the caller's rows across all shops and roles, newest first
    (`created_at DESC, id DESC`), paginated; `unread_only` keeps the unread ones."""
    repository = NotificationRepository(session)
    total = await repository.count_for_recipient(user_id=user_id, unread_only=unread_only)
    rows: list[Notification] = []
    if total > page.offset:
        rows = await repository.page_for_recipient(
            user_id=user_id, unread_only=unread_only, limit=page.limit, offset=page.offset
        )
    records = await _records(session, rows)
    return Page.build([record.to_read() for record in records], total=total, params=page)


async def count_unread(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """The bell badge: the caller's unread rows (`ix_notifications_unread`)."""
    return await NotificationRepository(session).count_for_recipient(
        user_id=user_id, unread_only=True
    )


async def list_for_bookings(
    session: AsyncSession, *, shop_id: uuid.UUID, booking_ids: Collection[uuid.UUID]
) -> list[NotificationRecord]:
    """Seed support: every row about these bookings of `shop_id`, oldest first (`created_at`, `id`),
    with the addressee, so the seed can keep the latest one per (recipient, booking) unread."""
    rows = await NotificationRepository(session).list_for_bookings(
        shop_id=shop_id, booking_ids=set(booking_ids)
    )
    return await _records(session, rows)


# --- Writes (top-level: commit) -------------------------------------------------------------


async def mark_read(uow: UnitOfWork, *, user_id: uuid.UUID, notification_id: uuid.UUID) -> None:
    """`POST …/{notification_id}/read`: idempotent (an already-read row keeps its `read_at`);
    404 `NOT_FOUND` for an unknown id and for another user's (identical, SEC-34)."""
    repository = NotificationRepository(uow.session)
    changed = await repository.mark_read(
        user_id=user_id, notification_ids=[notification_id], now=utcnow()
    )
    if not changed and not await repository.exists_for_recipient(
        user_id=user_id, notification_id=notification_id
    ):
        raise NotFound
    await uow.commit()


async def mark_all_read(uow: UnitOfWork, *, user_id: uuid.UUID) -> int:
    """`POST …/read-all`: every unread row of the caller, one instant (D63). Returns the count."""
    changed = await NotificationRepository(uow.session).mark_read(
        user_id=user_id, notification_ids=None, now=utcnow()
    )
    await uow.commit()
    return changed


async def mark_read_bulk(
    uow: UnitOfWork, *, user_id: uuid.UUID, notification_ids: Collection[uuid.UUID]
) -> int:
    """Seed support: mark these rows of `user_id` read (`read_at` = the clock, D63). Ids that are
    not that user's, unknown or already read are ignored. Commits; returns the rows changed."""
    changed = await NotificationRepository(uow.session).mark_read(
        user_id=user_id, notification_ids=set(notification_ids), now=utcnow()
    )
    await uow.commit()
    return changed


# --- Realtime ticket (D70) --------------------------------------------------------------------


def issue_ws_ticket(user_id: uuid.UUID) -> RealtimeTicketRead:
    """A JWT with exactly `sub`, `iat`, `exp = iat + 60` and `typ = "ws"`, on the app clock (D63).

    It is good only for the WebSocket handshake (a `ws` token is refused as a session, 401) and
    creates no server state (Tier 1: reusable within its 60 s, D70)."""
    return RealtimeTicketRead(
        ticket=issue_token(user_id, "ws", utcnow()), expires_in=WS_TICKET_LIFETIME_SECONDS
    )


# --- P2: calls (spec 05 §3.8, §6.3; `modules/notifications.md` "Call handlers") ------------------


async def _insert_records(
    session: AsyncSession, rows: Sequence[NewNotification], *, reference: str | None
) -> list[NotificationRecord]:
    if not rows:
        return []
    await NotificationRepository(session).insert_many(rows)
    shops = await shops_service.get_shop_briefs(session, shop_ids={row.shop_id for row in rows})
    return [
        NotificationRecord(
            id=row.id,
            type=row.type,
            title=row.title,
            body=row.body,
            recipient_role=row.recipient_role,
            link=row.link,
            shop_id=row.shop_id,
            shop_name=shops[row.shop_id].name if row.shop_id in shops else None,
            booking_id=row.booking_id,
            booking_reference=reference,
            read_at=None,
            created_at=row.created_at,
            recipient_user_id=row.recipient_user_id,
        )
        for row in rows
    ]


async def _shop_advisor_recipients(
    session: AsyncSession, shop_id: uuid.UUID
) -> list[tuple[uuid.UUID, ActorRole]]:
    """D26 "SAs of the shop": the active SAs, else the Owner."""
    advisors = await shops_service.list_active_member_ids(
        session, shop_id=shop_id, roles=[MembershipRole.SERVICE_ADVISOR]
    )
    if advisors:
        return [(user_id, ActorRole.SERVICE_ADVISOR) for user_id in advisors]
    owner = await _owner_or_none(session, shop_id=shop_id)
    return [(owner, ActorRole.OWNER)] if owner is not None else []


def _first_name(full_name: str | None) -> str:
    parts = (full_name or "").split(maxsplit=1)
    return parts[0] if parts else "A customer"


async def create_for_call_event(
    uow: UnitOfWork, event: "CallStateChanged"
) -> list[NotificationRecord]:
    """`CALL_MISSED` when a ringing call becomes `MISSED` (C3, C4, C5): customer → shop to the SAs
    of the shop, shop → customer to the customer. In the call's transaction; never commits."""
    from app.shared.enums import AiLegStatus, CallDirection, CallStatus  # noqa: PLC0415

    if event.previous_status is not CallStatus.RINGING or event.status is not CallStatus.MISSED:
        return []
    session = uow.session
    refs = await bookings_service.get_booking_refs(
        session, shop_id=event.shop_id, booking_ids=[event.booking_id]
    )
    ref = refs.get(event.booking_id)
    reference = ref.reference if ref is not None else ""
    if event.direction is CallDirection.CUSTOMER_TO_SHOP:
        customer = await identity_service.get_user(session, event.customer_user_id)
        first = _first_name(customer.full_name if customer else None)
        title = truncate(f"Missed call from {first} ({reference})", 160)
        body = f"{first} called about {reference} and no advisor answered."
        if event.ai_status is not AiLegStatus.NONE:
            body = f"{first} called about {reference} — answered by the AI Front Desk."
        recipients = await _shop_advisor_recipients(session, event.shop_id)
    else:
        briefs = await shops_service.get_shop_briefs(session, shop_ids=[event.shop_id])
        shop_name = briefs[event.shop_id].name if event.shop_id in briefs else "The shop"
        title = truncate(f"Missed call from {shop_name}", 160)
        body = f"{shop_name} tried to call you about {reference}."
        recipients = [(event.customer_user_id, ActorRole.CUSTOMER)]
    rows = [
        NewNotification(
            id=uuid.uuid4(),
            recipient_user_id=user_id,
            recipient_role=role,
            shop_id=event.shop_id,
            booking_id=event.booking_id,
            type=NotificationType.CALL_MISSED,
            title=title,
            body=body,
            link=link_for(
                role,
                NotificationType.CALL_MISSED,
                shop_id=event.shop_id,
                booking_id=event.booking_id,
            ),
            created_at=event.occurred_at,
        )
        for user_id, role in recipients
    ]
    return await _insert_records(session, rows, reference=reference or None)


async def create_for_ai_task(uow: UnitOfWork, event: "AiTaskCreated") -> list[NotificationRecord]:
    """`AI_TASK_CREATED` for the SAs of the shop (link: the AI calls & tasks panel)."""
    title = truncate(f"AI task: {event.title}", 160)
    body = f"Urgent · {event.booking_reference}" if event.is_urgent else event.booking_reference
    rows = [
        NewNotification(
            id=uuid.uuid4(),
            recipient_user_id=user_id,
            recipient_role=role,
            shop_id=event.shop_id,
            booking_id=event.booking_id,
            type=NotificationType.AI_TASK_CREATED,
            title=title,
            body=body,
            link=link_for(
                role,
                NotificationType.AI_TASK_CREATED,
                shop_id=event.shop_id,
                booking_id=event.booking_id,
            ),
            created_at=event.occurred_at,
        )
        for user_id, role in await _shop_advisor_recipients(uow.session, event.shop_id)
    ]
    return await _insert_records(uow.session, rows, reference=event.booking_reference)

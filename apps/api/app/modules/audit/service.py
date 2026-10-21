"""Use cases of the audit module (spec 19 §3, §4; D95, D97).

- **Write** (nested: the publisher's transaction, never a commit): `record` inserts one row with
  the request's IP, user agent and request id (`app.core.request_context`; all `None` in scripts
  and the seed). The `record_*` functions turn each event of the catalogue (spec 19 §3.3) into its
  row — category, action, a one-sentence summary with names resolved through the identity and
  shops services, actor and actor role, shop, target and metadata (never a password, token or
  hash). `handlers.py` calls them for every subscribed event; the admin module calls the three
  `record_*` functions of its own catalogue entries (E-67, E-73, E-75). Modules below never
  import this one: the row follows their events (spec 19 §3.2).
- **Read**: `list_events` (E-74), `latest_events` (the trails of E-61, E-63, E-67) and
  `export_events`, an async iterator over at most `EXPORT_MAX_ROWS` rows, newest first, read in
  keyset batches (E-75).

The table is append-only: nothing here updates or deletes a row (spec 02 §8).
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import current_request_context
from app.modules.audit.domain.catalogue import (
    AUDIT_EXPORTED,
    BOOKING_VIEWED,
    CUSTOMER_CREATED,
    LOGGED_OUT,
    LOGIN_FAILED,
    LOGIN_RATE_LIMITED,
    LOGIN_SUCCEEDED,
    MEMBERSHIP_ADDED,
    MEMBERSHIP_DEACTIVATED,
    MEMBERSHIP_REACTIVATED,
    MEMBERSHIP_ROLE_CHANGED,
    OWNER_REGISTERED,
    PLATFORM_ADMIN_GRANTED,
    PLATFORM_ADMIN_REVOKED,
    ROLE_LABELS,
    SHOP_CREATED,
    SHOP_REACTIVATED,
    SHOP_SUSPENDED,
    SHOP_UPDATED,
    SUMMARY_MAX_LENGTH,
    SYSTEM_NAME,
    UNKNOWN_NAME,
    USER_DEACTIVATED,
    USER_REACTIVATED,
    USER_VIEWED,
    WORKING_HOURS_REPLACED,
    booking_action_name,
    booking_summary,
    category_of,
    changed_fields,
    cut,
    label,
    summary,
)
from app.modules.audit.models import AuditEvent
from app.modules.audit.repository import AuditEventRepository
from app.modules.audit.schemas import AuditEntry, AuditEventRead, AuditFilters, AuditSort
from app.modules.bookings.events import BookingActionApplied
from app.modules.identity import service as identity_service
from app.modules.identity.events import (
    CustomerAccountCreated,
    LoggedOut,
    LoginFailed,
    LoginRateLimited,
    LoginSucceeded,
    OwnerRegistered,
    PlatformAdminChanged,
    UserActiveChanged,
)
from app.modules.identity.schemas import UserRecord
from app.modules.shops import service as shops_service
from app.modules.shops.events import (
    MembershipActiveChanged,
    MembershipAdded,
    MembershipRoleChanged,
    ShopCreated,
    ShopSuspensionChanged,
    ShopUpdated,
    WorkingHoursReplaced,
)
from app.shared.enums import AuditActorRole, AuditCategory, AuditTargetType
from app.shared.pagination import Page, PageParams
from app.shared.uow import UnitOfWork

EXPORT_MAX_ROWS: Final = 10_000
"""E-75 exports at most this many rows, newest first (spec 19 §4)."""
EXPORT_BATCH_SIZE: Final = 1_000
UNKNOWN_SHOP: Final = "an unknown shop"


# --- Writing ------------------------------------------------------------------------------------


async def record(uow: UnitOfWork, entry: AuditEntry) -> UUID:
    """Insert one audit row in the caller's transaction (nested; never commits), stamped with the
    current request context, and flush it so a database error fails the action that caused it."""
    context = current_request_context()
    row = AuditEventRepository(uow.session).add(
        AuditEvent(
            occurred_at=entry.occurred_at,
            category=entry.category,
            action=entry.action,
            summary=cut(entry.summary, SUMMARY_MAX_LENGTH),
            actor_user_id=entry.actor_user_id,
            actor_role=entry.actor_role,
            shop_id=entry.shop_id,
            target_type=entry.target_type,
            target_id=entry.target_id,
            target_label=label(entry.target_label),
            metadata_=dict(entry.metadata),
            ip=context.ip,
            user_agent=context.user_agent,
            request_id=context.request_id,
        )
    )
    await uow.session.flush()
    return row.id


async def _users(session: AsyncSession, *user_ids: UUID | None) -> dict[UUID, UserRecord]:
    ids = {user_id for user_id in user_ids if user_id is not None}
    return await identity_service.get_users_by_ids(session, ids) if ids else {}


def _name(users: Mapping[UUID, UserRecord], user_id: UUID | None) -> str:
    """A person's name for a summary; no user is the system (scripts, the seed, D60)."""
    if user_id is None:
        return SYSTEM_NAME
    user = users.get(user_id)
    return UNKNOWN_NAME if user is None else user.full_name


def _email(users: Mapping[UUID, UserRecord], user_id: UUID) -> str | None:
    user = users.get(user_id)
    return None if user is None else user.email


async def _shop_name(session: AsyncSession, shop_id: UUID) -> str:
    brief = (await shops_service.get_shop_briefs(session, shop_ids=[shop_id])).get(shop_id)
    return UNKNOWN_SHOP if brief is None else brief.name


def _admin_role(actor_user_id: UUID | None) -> AuditActorRole:
    """An account lever is pulled by a platform admin, or by the system (seed, bootstrap)."""
    return AuditActorRole.SYSTEM if actor_user_id is None else AuditActorRole.PLATFORM_ADMIN


async def _about_user(  # noqa: PLR0913 - the parts of a user-targeted row
    uow: UnitOfWork,
    *,
    occurred_at: datetime,
    action: str,
    template: str,
    user_id: UUID,
    actor_user_id: UUID | None,
    actor_role: AuditActorRole | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """A row about an account (`USER` target, labelled with its e-mail); no shop."""
    users = await _users(uow.session, user_id, actor_user_id)
    await record(
        uow,
        AuditEntry(
            occurred_at=occurred_at,
            action=action,
            category=category_of(action),
            summary=summary(
                template, actor=_name(users, actor_user_id), target=_name(users, user_id)
            ),
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type=AuditTargetType.USER,
            target_id=user_id,
            target_label=_email(users, user_id),
            metadata=metadata or {},
        ),
    )


async def record_login_succeeded(uow: UnitOfWork, event: LoginSucceeded) -> None:
    await _about_user(
        uow,
        occurred_at=event.occurred_at,
        action=LOGIN_SUCCEEDED,
        template="{actor} signed in.",
        user_id=event.user_id,
        actor_user_id=event.user_id,
        actor_role=None,
    )


async def _failed_sign_in(
    uow: UnitOfWork, *, occurred_at: datetime, action: str, email: str
) -> None:
    """An anonymous attempt: the typed e-mail (normalised) in the summary and `metadata.email`."""
    template = (
        "Failed sign-in for {email}."
        if action == LOGIN_FAILED
        else "Sign-in for {email} blocked after too many failed attempts."
    )
    await record(
        uow,
        AuditEntry(
            occurred_at=occurred_at,
            action=action,
            category=AuditCategory.AUTH,
            summary=summary(template, email=email),
            actor_role=AuditActorRole.ANONYMOUS,
            metadata={"email": email},
        ),
    )


async def record_login_failed(uow: UnitOfWork, event: LoginFailed) -> None:
    await _failed_sign_in(
        uow, occurred_at=event.occurred_at, action=LOGIN_FAILED, email=event.email
    )


async def record_login_rate_limited(uow: UnitOfWork, event: LoginRateLimited) -> None:
    await _failed_sign_in(
        uow, occurred_at=event.occurred_at, action=LOGIN_RATE_LIMITED, email=event.email
    )


async def record_logged_out(uow: UnitOfWork, event: LoggedOut) -> None:
    await _about_user(
        uow,
        occurred_at=event.occurred_at,
        action=LOGGED_OUT,
        template="{actor} signed out.",
        user_id=event.user_id,
        actor_user_id=event.user_id,
        actor_role=None,
    )


async def record_owner_registered(uow: UnitOfWork, event: OwnerRegistered) -> None:
    await _about_user(
        uow,
        occurred_at=event.occurred_at,
        action=OWNER_REGISTERED,
        template="{actor} registered an owner account.",
        user_id=event.user_id,
        actor_user_id=event.user_id,
        actor_role=None,
    )


async def record_customer_created(uow: UnitOfWork, event: CustomerAccountCreated) -> None:
    await _about_user(
        uow,
        occurred_at=event.occurred_at,
        action=CUSTOMER_CREATED,
        template="{actor} created a customer account while booking.",
        user_id=event.user_id,
        actor_user_id=event.user_id,
        actor_role=AuditActorRole.CUSTOMER,
    )


async def record_user_active_changed(uow: UnitOfWork, event: UserActiveChanged) -> None:
    metadata = {} if event.is_active or event.reason is None else {"reason": event.reason}
    await _about_user(
        uow,
        occurred_at=event.occurred_at,
        action=USER_REACTIVATED if event.is_active else USER_DEACTIVATED,
        template=(
            "{actor} reactivated the account of {target}."
            if event.is_active
            else "{actor} deactivated the account of {target}."
        ),
        user_id=event.user_id,
        actor_user_id=event.actor_user_id,
        actor_role=_admin_role(event.actor_user_id),
        metadata=metadata,
    )


async def record_platform_admin_changed(uow: UnitOfWork, event: PlatformAdminChanged) -> None:
    await _about_user(
        uow,
        occurred_at=event.occurred_at,
        action=PLATFORM_ADMIN_GRANTED if event.is_platform_admin else PLATFORM_ADMIN_REVOKED,
        template=(
            "{actor} granted platform admin access to {target}."
            if event.is_platform_admin
            else "{actor} revoked platform admin access from {target}."
        ),
        user_id=event.user_id,
        actor_user_id=event.actor_user_id,
        actor_role=_admin_role(event.actor_user_id),
    )


async def _about_shop(  # noqa: PLR0913 - the parts of a shop-targeted row
    uow: UnitOfWork,
    *,
    occurred_at: datetime,
    action: str,
    template: str,
    shop_id: UUID,
    actor_user_id: UUID,
    actor_role: AuditActorRole,
    metadata: dict[str, Any] | None = None,
) -> None:
    """A row about a shop (`SHOP` target, labelled with its name), in that shop."""
    users = await _users(uow.session, actor_user_id)
    shop = await _shop_name(uow.session, shop_id)
    fields = changed_fields((metadata or {}).get("changes", {}))
    await record(
        uow,
        AuditEntry(
            occurred_at=occurred_at,
            action=action,
            category=category_of(action),
            summary=summary(template, actor=_name(users, actor_user_id), shop=shop, fields=fields),
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            shop_id=shop_id,
            target_type=AuditTargetType.SHOP,
            target_id=shop_id,
            target_label=shop,
            metadata=metadata or {},
        ),
    )


async def record_shop_created(uow: UnitOfWork, event: ShopCreated) -> None:
    await _about_shop(
        uow,
        occurred_at=event.occurred_at,
        action=SHOP_CREATED,
        template="{actor} created {shop}.",
        shop_id=event.shop_id,
        actor_user_id=event.actor_user_id,
        actor_role=AuditActorRole.OWNER,
    )


async def record_shop_updated(uow: UnitOfWork, event: ShopUpdated) -> None:
    changes = {field: dict(change) for field, change in event.changes.items()}
    await _about_shop(
        uow,
        occurred_at=event.occurred_at,
        action=SHOP_UPDATED,
        template="{actor} updated {shop} ({fields}).",
        shop_id=event.shop_id,
        actor_user_id=event.actor_user_id,
        actor_role=AuditActorRole.OWNER,
        metadata={"changes": changes},
    )


async def record_working_hours_replaced(uow: UnitOfWork, event: WorkingHoursReplaced) -> None:
    await _about_shop(
        uow,
        occurred_at=event.occurred_at,
        action=WORKING_HOURS_REPLACED,
        template="{actor} changed the working hours of {shop}.",
        shop_id=event.shop_id,
        actor_user_id=event.actor_user_id,
        actor_role=AuditActorRole.OWNER,
    )


async def record_shop_suspension_changed(uow: UnitOfWork, event: ShopSuspensionChanged) -> None:
    metadata = {"reason": event.reason} if event.suspended and event.reason is not None else {}
    await _about_shop(
        uow,
        occurred_at=event.occurred_at,
        action=SHOP_SUSPENDED if event.suspended else SHOP_REACTIVATED,
        template="{actor} suspended {shop}." if event.suspended else "{actor} reactivated {shop}.",
        shop_id=event.shop_id,
        actor_user_id=event.actor_user_id,
        actor_role=AuditActorRole.PLATFORM_ADMIN,
        metadata=metadata,
    )


async def _about_membership(  # noqa: PLR0913 - the parts of a membership-targeted row
    uow: UnitOfWork,
    *,
    occurred_at: datetime,
    action: str,
    template: str,
    shop_id: UUID,
    membership_id: UUID,
    member_user_id: UUID,
    actor_user_id: UUID,
    metadata: dict[str, Any] | None = None,
    **words: str,
) -> None:
    """A row about a membership (`MEMBERSHIP` target, labelled with the member's e-mail), in its
    shop, done by the shop's Owner (D18, D19)."""
    users = await _users(uow.session, actor_user_id, member_user_id)
    shop = await _shop_name(uow.session, shop_id)
    await record(
        uow,
        AuditEntry(
            occurred_at=occurred_at,
            action=action,
            category=category_of(action),
            summary=summary(
                template,
                actor=_name(users, actor_user_id),
                member=_name(users, member_user_id),
                shop=shop,
                **words,
            ),
            actor_user_id=actor_user_id,
            actor_role=AuditActorRole.OWNER,
            shop_id=shop_id,
            target_type=AuditTargetType.MEMBERSHIP,
            target_id=membership_id,
            target_label=_email(users, member_user_id),
            metadata=metadata or {},
        ),
    )


async def record_membership_added(uow: UnitOfWork, event: MembershipAdded) -> None:
    member = await _users(uow.session, event.user_id)
    await _about_membership(
        uow,
        occurred_at=event.occurred_at,
        action=MEMBERSHIP_ADDED,
        template="{actor} added {member} to {shop} as {role}.",
        shop_id=event.shop_id,
        membership_id=event.membership_id,
        member_user_id=event.user_id,
        actor_user_id=event.actor_user_id,
        metadata={"role": event.role.value, "member_email": _email(member, event.user_id)},
        role=ROLE_LABELS[event.role],
    )


async def record_membership_role_changed(uow: UnitOfWork, event: MembershipRoleChanged) -> None:
    await _about_membership(
        uow,
        occurred_at=event.occurred_at,
        action=MEMBERSHIP_ROLE_CHANGED,
        template="{actor} changed the role of {member} at {shop} from {from_role} to {to_role}.",
        shop_id=event.shop_id,
        membership_id=event.membership_id,
        member_user_id=event.user_id,
        actor_user_id=event.actor_user_id,
        metadata={"from": event.from_role.value, "to": event.to_role.value},
        from_role=ROLE_LABELS[event.from_role],
        to_role=ROLE_LABELS[event.to_role],
    )


async def record_membership_active_changed(uow: UnitOfWork, event: MembershipActiveChanged) -> None:
    await _about_membership(
        uow,
        occurred_at=event.occurred_at,
        action=MEMBERSHIP_REACTIVATED if event.is_active else MEMBERSHIP_DEACTIVATED,
        template=(
            "{actor} reactivated {member} at {shop}."
            if event.is_active
            else "{actor} deactivated {member} at {shop}."
        ),
        shop_id=event.shop_id,
        membership_id=event.membership_id,
        member_user_id=event.user_id,
        actor_user_id=event.actor_user_id,
    )


async def record_booking_action(uow: UnitOfWork, event: BookingActionApplied) -> None:
    """`booking.<action>` for every transition and operation (spec 19 §3.2): the actor (or
    `SYSTEM`), the booking labelled with its reference, `{from_status, to_status, version}` plus
    the event's `note` when set. `booking_events` stays the booking's own history (D22)."""
    users = await _users(uow.session, event.actor_user_id)
    shop = await _shop_name(uow.session, event.shop_id)
    metadata: dict[str, Any] = {
        "from_status": None if event.from_status is None else event.from_status.value,
        "to_status": event.to_status.value,
        "version": event.version,
    }
    if event.note:
        metadata["note"] = event.note
    await record(
        uow,
        AuditEntry(
            occurred_at=event.occurred_at,
            action=booking_action_name(event.action),
            category=AuditCategory.BOOKING,
            summary=booking_summary(
                _name(users, event.actor_user_id), event.action, event.reference, shop
            ),
            actor_user_id=event.actor_user_id,
            actor_role=AuditActorRole(event.actor_role.value),
            shop_id=event.shop_id,
            target_type=AuditTargetType.BOOKING,
            target_id=event.booking_id,
            target_label=event.reference,
            metadata=metadata,
        ),
    )


# --- The admin module's own catalogue entries (spec 19 §3.3 `ADMIN`) ---------------------------


async def record_user_viewed(
    uow: UnitOfWork, *, admin_user_id: UUID, user_id: UUID, occurred_at: datetime
) -> None:
    """E-67: a platform admin opened a person's detail (A-05)."""
    await _about_user(
        uow,
        occurred_at=occurred_at,
        action=USER_VIEWED,
        template="{actor} viewed the account of {target}.",
        user_id=user_id,
        actor_user_id=admin_user_id,
        actor_role=AuditActorRole.PLATFORM_ADMIN,
    )


async def record_booking_viewed(
    uow: UnitOfWork,
    *,
    admin_user_id: UUID,
    booking_id: UUID,
    shop_id: UUID,
    reference: str,
    occurred_at: datetime,
) -> None:
    """E-73: a platform admin opened a booking (A-07); the row belongs to the booking's shop."""
    users = await _users(uow.session, admin_user_id)
    shop = await _shop_name(uow.session, shop_id)
    await record(
        uow,
        AuditEntry(
            occurred_at=occurred_at,
            action=BOOKING_VIEWED,
            category=AuditCategory.ADMIN,
            summary=summary(
                "{actor} viewed booking {reference} at {shop}.",
                actor=_name(users, admin_user_id),
                reference=reference,
                shop=shop,
            ),
            actor_user_id=admin_user_id,
            actor_role=AuditActorRole.PLATFORM_ADMIN,
            shop_id=shop_id,
            target_type=AuditTargetType.BOOKING,
            target_id=booking_id,
            target_label=reference,
        ),
    )


async def record_audit_exported(
    uow: UnitOfWork,
    *,
    admin_user_id: UUID,
    filters: AuditFilters,
    rows: int,
    occurred_at: datetime,
) -> None:
    """E-75: a platform admin exported the audit log; `{filters, rows}` (spec 19 §3.3)."""
    users = await _users(uow.session, admin_user_id)
    await record(
        uow,
        AuditEntry(
            occurred_at=occurred_at,
            action=AUDIT_EXPORTED,
            category=AuditCategory.ADMIN,
            summary=summary(
                "{actor} exported {rows} audit events.",
                actor=_name(users, admin_user_id),
                rows=rows,
            ),
            actor_user_id=admin_user_id,
            actor_role=AuditActorRole.PLATFORM_ADMIN,
            metadata={"filters": filters.as_metadata(), "rows": rows},
        ),
    )


# --- Reading ------------------------------------------------------------------------------------


async def _reads(session: AsyncSession, rows: Sequence[AuditEvent]) -> list[AuditEventRead]:
    """Rows on the wire with today's actor and shop names (one query each, whatever the size)."""
    users = await _users(session, *(row.actor_user_id for row in rows))
    shop_ids = {row.shop_id for row in rows if row.shop_id is not None}
    shops = await shops_service.get_shop_briefs(session, shop_ids=shop_ids) if shop_ids else {}
    return [
        AuditEventRead(
            id=row.id,
            occurred_at=row.occurred_at,
            category=row.category,
            action=row.action,
            summary=row.summary,
            actor_user_id=row.actor_user_id,
            actor_name=(
                None
                if row.actor_user_id is None or row.actor_user_id not in users
                else users[row.actor_user_id].full_name
            ),
            actor_role=row.actor_role,
            shop_id=row.shop_id,
            shop_name=(
                None if row.shop_id is None or row.shop_id not in shops else shops[row.shop_id].name
            ),
            target_type=row.target_type,
            target_id=row.target_id,
            target_label=row.target_label,
            metadata=dict(row.metadata_),
            ip=None if row.ip is None else str(row.ip),
            user_agent=row.user_agent,
            request_id=row.request_id,
        )
        for row in rows
    ]


async def list_events(
    session: AsyncSession, *, filters: AuditFilters, sort: AuditSort, page: PageParams
) -> Page[AuditEventRead]:
    """E-74: one page of the audit log (every filter of spec 19 §4), newest first by default."""
    rows, total = await AuditEventRepository(session).page(
        filters, sort=sort, limit=page.limit, offset=page.offset
    )
    return Page.build(await _reads(session, rows), total=total, params=page)


async def latest_events(
    session: AsyncSession, *, filters: AuditFilters, limit: int = 10
) -> list[AuditEventRead]:
    """The `limit` newest rows matching `filters` (the trails of E-61, E-63 and E-67)."""
    rows = await AuditEventRepository(session).newest(filters, limit=limit)
    return await _reads(session, rows)


async def export_events(
    session: AsyncSession, *, filters: AuditFilters, limit: int = EXPORT_MAX_ROWS
) -> AsyncIterator[AuditEventRead]:
    """E-75: at most `limit` rows matching `filters`, newest first, read in keyset batches of
    `EXPORT_BATCH_SIZE` (no `OFFSET` scan however deep the export goes)."""
    repository = AuditEventRepository(session)
    remaining = max(0, min(limit, EXPORT_MAX_ROWS))
    before: tuple[datetime, UUID] | None = None
    while remaining > 0:
        size = min(EXPORT_BATCH_SIZE, remaining)
        rows = await repository.newest(filters, limit=size, before=before)
        for item in await _reads(session, rows):
            yield item
        remaining -= len(rows)
        if len(rows) < size:
            return
        before = (rows[-1].occurred_at, rows[-1].id)

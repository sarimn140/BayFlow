"""Use cases of the admin module (spec 19 §4, E-61…E-75; D94-D97).

The admin module owns no table: every use case composes the read and write ports of identity,
shops, bookings and audit (D97, spec 19 §6). The routes are behind `require_platform_admin`; the
lower modules re-check the actor themselves (defence in depth).

- Reads: `get_overview` (E-61), `list_shops` / `get_shop` (E-62, E-63), `list_users` (E-66),
  `list_bookings` (E-72), `list_audit_events` (E-74).
- Reads that are audited (spec 19 §1 "Accountability"): `view_user` (E-67, `admin.user_viewed`),
  `view_booking` (E-73, `admin.booking_viewed`), `export_audit_events` (E-75,
  `admin.audit_exported`) — each commits its audit row.
- Levers (top-level, one commit each): `suspend_shop` / `reactivate_shop` (E-64, E-65),
  `deactivate_user` / `reactivate_user` (E-68, E-69), `grant_platform_admin` /
  `revoke_platform_admin` (E-70, E-71). Their audit rows come from the lower modules' events.

"Today", "the last 7 / 30 days" and the 14-day series are local dates in the shops' default time
zone `Asia/Karachi` (D38), read from the one clock (D63). Booking counts count bookings by when
they were placed (`created_at`).
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FieldError, NotFound, ValidationFailed
from app.modules.admin.domain.csv_export import csv_lines
from app.modules.admin.domain.periods import last_days
from app.modules.admin.domain.phases import counts_by_phase
from app.modules.admin.schemas import (
    AdminBookingDetail,
    AdminBookingFilters,
    AdminBookingSort,
    AdminBookingSummary,
    AdminMemberRead,
    AdminMembershipRead,
    AdminShopDetail,
    AdminShopRef,
    AdminShopRow,
    AdminShopSort,
    AdminShopStatus,
    AdminUserDetail,
    AdminUserKind,
    AdminUserRef,
    AdminUserRow,
    AdminUserStatus,
    AuditEventRead,
    AuditFilters,
    AuditSort,
    BookingCounts,
    CustomerBookings,
    DayCount,
    PhaseCount,
    PlatformOverviewRead,
    RoleMembers,
    ShopCounts,
    ShopSuspensionRead,
    TopShop,
    UserAdminSort,
    UserCounts,
)
from app.modules.audit import service as audit_service
from app.modules.bookings import service as bookings_service
from app.modules.bookings.domain.state_machine import TERMINAL_STATUSES
from app.modules.identity import service as identity_service
from app.modules.identity.schemas import UserAdminQuery, UserAdminRecord, UserRecord
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import (
    AdminMembershipRecord,
    AdminShopQuery,
    AdminShopRecord,
    ShopBrief,
    ShopSuspension,
)
from app.shared.auth import CurrentUser
from app.shared.clock import utcnow
from app.shared.enums import MembershipRole
from app.shared.pagination import Page, PageParams
from app.shared.uow import UnitOfWork

PLATFORM_TIMEZONE: Final = "Asia/Karachi"
"""The shops' default time zone (D38): the platform's "today"."""
WINDOW_DAYS: Final = 30
SERIES_DAYS: Final = 14
WEEK_DAYS: Final = 7
TOP_SHOPS: Final = 5
LATEST: Final = 10
LATEST_PAGE: Final = PageParams(limit=LATEST, offset=0)
PERIOD_ORDER: Final = "`from` must be earlier than `to`."

EXPORT_COLUMNS: Final = (
    "occurred_at",
    "category",
    "action",
    "summary",
    "actor_user_id",
    "actor_name",
    "actor_role",
    "shop_id",
    "shop_name",
    "target_type",
    "target_id",
    "target_label",
    "metadata",
    "ip",
    "user_agent",
    "request_id",
)


def _window(now: datetime) -> tuple[datetime, datetime]:
    """The last 30 local days as a half-open UTC window."""
    _, bounds = last_days(now, ZoneInfo(PLATFORM_TIMEZONE), WINDOW_DAYS)
    return bounds[0], bounds[-1]


def _shop_ref(shop: ShopBrief | AdminShopRecord) -> AdminShopRef:
    return AdminShopRef(id=shop.id, slug=shop.slug, name=shop.name)


def _user_ref(user: UserRecord) -> AdminUserRef:
    return AdminUserRef(user_id=user.id, full_name=user.full_name, email=user.email)


def _suspension(
    suspension: ShopSuspension | None, users: Mapping[UUID, UserRecord]
) -> ShopSuspensionRead | None:
    if suspension is None:
        return None
    by = users.get(suspension.suspended_by_user_id)
    return ShopSuspensionRead(
        at=suspension.suspended_at,
        reason=suspension.reason,
        by=None if by is None else _user_ref(by),
    )


# --- E-61 ----------------------------------------------------------------------------------------


async def get_overview(session: AsyncSession) -> PlatformOverviewRead:
    """E-61: shops, accounts and bookings across every tenant, the 14-day series, the top 5 shops
    of the last 30 days and the 10 newest audit events (spec 19 §4)."""
    now = utcnow()
    today, bounds = last_days(now, ZoneInfo(PLATFORM_TIMEZONE), WINDOW_DAYS)
    since = bounds[0]  # the first instant of the oldest of the last 30 local days
    shops = await shops_service.count_shops(session, since=since)
    users = await identity_service.count_users(session, since=since)
    staff = await shops_service.count_staff_users(session)
    stats = await bookings_service.platform_booking_stats(
        session, day_bounds=bounds, top_shops=TOP_SHOPS
    )
    per_day = stats.created_per_day
    zone = ZoneInfo(PLATFORM_TIMEZONE)
    open_counts = {
        status: count
        for status, count in stats.by_status.items()
        if status not in TERMINAL_STATUSES
    }
    briefs = await shops_service.get_shop_briefs(
        session, shop_ids=[shop_id for shop_id, _ in stats.top_shops]
    )
    series_start = len(per_day) - SERIES_DAYS
    return PlatformOverviewRead(
        generated_at=now,
        timezone=PLATFORM_TIMEZONE,
        today=today,
        shops=ShopCounts(
            total=shops.total,
            active=shops.active,
            suspended=shops.suspended,
            listed=shops.listed,
            new_30d=shops.created_since,
        ),
        users=UserCounts(
            total=users.total,
            customers=users.total - staff,
            staff=staff,
            platform_admins=users.platform_admins,
            inactive=users.inactive,
            new_30d=users.created_since,
        ),
        bookings=BookingCounts(
            today=per_day[-1],
            last_7_days=sum(per_day[-WEEK_DAYS:]),
            last_30_days=sum(per_day),
            open=sum(open_counts.values()),
            completed_30d=stats.completed,
            cancelled_30d=stats.cancelled,
            open_by_phase=[
                PhaseCount(phase=phase, count=count)
                for phase, count in counts_by_phase(open_counts)
            ],
        ),
        bookings_per_day=[
            DayCount(date=bounds[index].astimezone(zone).date(), count=count)
            for index, count in enumerate(per_day)
            if index >= series_start
        ],
        top_shops=[
            TopShop(shop=_shop_ref(briefs[shop_id]), bookings_30d=count)
            for shop_id, count in stats.top_shops
            if shop_id in briefs
        ],
        latest_audit_events=await audit_service.latest_events(
            session, filters=AuditFilters(), limit=LATEST
        ),
    )


# --- E-62 - E-65 ---------------------------------------------------------------------------------


def _shop_query(
    *, q: str | None, status: AdminShopStatus | None, listed: bool | None, city: str | None
) -> AdminShopQuery:
    suspended = None if status is None else status == AdminShopStatus.SUSPENDED
    return AdminShopQuery(q=q, suspended=suspended, listed=listed, city=city)


async def _shop_rows(
    session: AsyncSession, records: Sequence[AdminShopRecord], counts: Mapping[UUID, int]
) -> list[AdminShopRow]:
    suspenders = {
        record.suspension.suspended_by_user_id
        for record in records
        if record.suspension is not None
    }
    users = await identity_service.get_users_by_ids(session, suspenders)
    return [
        AdminShopRow(
            shop=_shop_ref(record),
            city=record.city,
            created_at=record.created_at,
            is_listed=record.is_listed,
            suspension=_suspension(record.suspension, users),
            owners=[
                AdminUserRef(user_id=owner.user_id, full_name=owner.full_name, email=owner.email)
                for owner in record.owners
            ],
            active_members=record.active_members,
            bookings_30d=counts.get(record.id, 0),
        )
        for record in records
    ]


async def list_shops(  # noqa: PLR0913 - E-62's filters, sort and page
    session: AsyncSession,
    *,
    q: str | None,
    status: AdminShopStatus | None,
    listed: bool | None,
    city: str | None,
    sort: AdminShopSort,
    page: PageParams,
) -> Page[AdminShopRow]:
    """E-62: every tenant, suspended ones included. `-bookings_30d` ranks the matching shops by
    the bookings placed in the last 30 local days (ties by name), the other sorts are SQL's."""
    query = _shop_query(q=q, status=status, listed=listed, city=city)
    start, end = _window(utcnow())
    if sort == "-bookings_30d":
        ids = await shops_service.list_shop_ids_for_admin(session, query)
        counts = await bookings_service.count_created_by_shop(
            session, start=start, end=end, shop_ids=ids
        )
        ranked = sorted(range(len(ids)), key=lambda index: (-counts[ids[index]], index))
        window = [ids[index] for index in ranked[page.offset : page.offset + page.limit]]
        records = await shops_service.get_admin_shop_records(session, shop_ids=window)
        total = len(ids)
    else:
        records, total = await shops_service.list_shops_for_admin(
            session, query, sort=sort, page=page
        )
        counts = await bookings_service.count_created_by_shop(
            session, start=start, end=end, shop_ids=[record.id for record in records]
        )
    return Page.build(await _shop_rows(session, records, counts), total=total, params=page)


async def _members_by_role(
    session: AsyncSession, shop_id: UUID
) -> tuple[list[RoleMembers], dict[UUID, UserRecord]]:
    team = await shops_service.list_team(session, shop_id=shop_id)
    users = await identity_service.get_users_by_ids(session, {member.user_id for member in team})
    by_role: dict[MembershipRole, list[AdminMemberRead]] = {role: [] for role in MembershipRole}
    for member in team:
        user = users.get(member.user_id)
        if user is None:  # pragma: no cover - the membership FK guarantees the account
            continue
        by_role[member.role].append(
            AdminMemberRead(
                membership_id=member.membership_id,
                user_id=member.user_id,
                full_name=user.full_name,
                email=user.email,
                is_active=member.is_active,
            )
        )
    return [RoleMembers(role=role, members=members) for role, members in by_role.items()], users


async def _shop_detail(session: AsyncSession, shop_id: UUID) -> AdminShopDetail:
    """E-63's body: unknown shop → 404."""
    profile = await shops_service.get_shop(session, shop_id=shop_id)
    records = await shops_service.get_admin_shop_records(session, shop_ids=[shop_id])
    if not records:  # pragma: no cover - `get_shop` already answered 404
        raise NotFound
    record = records[0]
    members, users = await _members_by_role(session, shop_id)
    if record.suspension is not None and record.suspension.suspended_by_user_id not in users:
        users |= await identity_service.get_users_by_ids(
            session, [record.suspension.suspended_by_user_id]
        )
    by_status = await bookings_service.count_by_status(session, shop_id=shop_id)
    latest = await bookings_service.list_admin_bookings(
        session,
        filters=AdminBookingFilters(shop_id=shop_id),
        sort="-created_at",
        page=LATEST_PAGE,
    )
    return AdminShopDetail(
        shop=profile,
        suspension=_suspension(record.suspension, users),
        owners=[
            AdminUserRef(user_id=owner.user_id, full_name=owner.full_name, email=owner.email)
            for owner in record.owners
        ],
        members_by_role=members,
        booking_counts_by_phase=[
            PhaseCount(phase=phase, count=count) for phase, count in counts_by_phase(by_status)
        ],
        latest_bookings=latest.items,
        latest_audit_events=await audit_service.latest_events(
            session, filters=AuditFilters(shop_id=shop_id), limit=LATEST
        ),
    )


async def get_shop(session: AsyncSession, *, shop_id: UUID) -> AdminShopDetail:
    """E-63."""
    return await _shop_detail(session, shop_id)


async def suspend_shop(
    uow: UnitOfWork, admin: CurrentUser, *, shop_id: UUID, reason: str
) -> AdminShopDetail:
    """E-64 (D96): already suspended → 409; the shop row is locked, so a concurrent second admin
    gets the 409 (spec 19 §7). Answers E-63's body."""
    await shops_service.suspend_shop(uow, shop_id=shop_id, actor_user_id=admin.id, reason=reason)
    await uow.commit()
    return await _shop_detail(uow.session, shop_id)


async def reactivate_shop(uow: UnitOfWork, admin: CurrentUser, *, shop_id: UUID) -> AdminShopDetail:
    """E-65 (D96): not suspended → 409. Answers E-63's body."""
    await shops_service.reactivate_shop(uow, shop_id=shop_id, actor_user_id=admin.id)
    await uow.commit()
    return await _shop_detail(uow.session, shop_id)


# --- E-66 - E-71 ---------------------------------------------------------------------------------


def _membership_read(record: AdminMembershipRecord) -> AdminMembershipRead:
    return AdminMembershipRead(
        membership_id=record.membership_id,
        shop=_shop_ref(record.shop),
        role=record.role,
        is_active=record.is_active,
    )


def _user_row(user: UserAdminRecord, memberships: Sequence[AdminMembershipRecord]) -> AdminUserRow:
    return AdminUserRow(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        is_active=user.is_active,
        is_platform_admin=user.is_platform_admin,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        memberships=[_membership_read(record) for record in memberships],
    )


async def list_users(
    session: AsyncSession,
    *,
    q: str | None,
    kind: AdminUserKind | None,
    status: AdminUserStatus | None,
    sort: UserAdminSort,
    page: PageParams,
) -> Page[AdminUserRow]:
    """E-66: every account. `kind` asks shops who holds an active membership (identity never
    reads memberships, D81), then filters the accounts by those ids."""
    only_ids = excluded_ids = None
    if kind in {AdminUserKind.STAFF, AdminUserKind.CUSTOMER}:
        staff = await shops_service.list_staff_user_ids(session)
        if kind == AdminUserKind.STAFF:
            only_ids = staff
        else:
            excluded_ids = staff
    users, total = await identity_service.list_users_for_admin(
        session,
        UserAdminQuery(
            q=q,
            is_active=None if status is None else status == AdminUserStatus.ACTIVE,
            is_platform_admin=True if kind == AdminUserKind.PLATFORM_ADMIN else None,
            only_ids=only_ids,
            excluded_ids=excluded_ids,
            sort=sort,
            limit=page.limit,
            offset=page.offset,
        ),
    )
    memberships = await shops_service.list_memberships_everywhere(
        session, user_ids=[user.id for user in users]
    )
    rows = [_user_row(user, memberships.get(user.id, [])) for user in users]
    return Page.build(rows, total=total, params=page)


async def _user_detail(session: AsyncSession, user_id: UUID) -> AdminUserDetail:
    """E-67's body: unknown account → 404."""
    user = await identity_service.get_user_for_admin(session, user_id)
    if user is None:
        raise NotFound
    memberships = await shops_service.list_memberships_everywhere(session, user_ids=[user_id])
    bookings = await bookings_service.list_admin_bookings(
        session,
        filters=AdminBookingFilters(customer_user_id=user_id),
        sort="-created_at",
        page=LATEST_PAGE,
    )
    return AdminUserDetail(
        user=_user_row(user, memberships.get(user_id, [])),
        bookings_as_customer=CustomerBookings(count=bookings.total, latest=bookings.items),
        latest_audit_events=await audit_service.latest_events(
            session, filters=AuditFilters(involving_user_id=user_id), limit=LATEST
        ),
    )


async def view_user(uow: UnitOfWork, admin: CurrentUser, *, user_id: UUID) -> AdminUserDetail:
    """E-67: the detail, then `admin.user_viewed` committed (spec 19 §1 "Accountability"); the
    view is not part of the trail it shows."""
    detail = await _user_detail(uow.session, user_id)
    await audit_service.record_user_viewed(
        uow, admin_user_id=admin.id, user_id=user_id, occurred_at=utcnow()
    )
    await uow.commit()
    return detail


async def deactivate_user(
    uow: UnitOfWork, admin: CurrentUser, *, user_id: UUID, reason: str
) -> AdminUserDetail:
    """E-68: yourself → 403, the last active admin → 409, already inactive → 409; the account's
    tokens stop working at its next request (D9)."""
    await identity_service.change_user_active(
        uow, actor_user_id=admin.id, user_id=user_id, is_active=False, reason=reason
    )
    await uow.commit()
    return await _user_detail(uow.session, user_id)


async def reactivate_user(uow: UnitOfWork, admin: CurrentUser, *, user_id: UUID) -> AdminUserDetail:
    """E-69: already active → 409."""
    await identity_service.change_user_active(
        uow, actor_user_id=admin.id, user_id=user_id, is_active=True
    )
    await uow.commit()
    return await _user_detail(uow.session, user_id)


async def grant_platform_admin(
    uow: UnitOfWork, admin: CurrentUser, *, user_id: UUID
) -> AdminUserDetail:
    """E-70: an inactive account → 422 on `path.user_id`; already an admin → 409."""
    await identity_service.change_platform_admin(
        uow, actor_user_id=admin.id, user_id=user_id, is_platform_admin=True
    )
    await uow.commit()
    return await _user_detail(uow.session, user_id)


async def revoke_platform_admin(
    uow: UnitOfWork, admin: CurrentUser, *, user_id: UUID
) -> AdminUserDetail:
    """E-71: yourself → 403, the last active admin → 409, not an admin → 409."""
    await identity_service.change_platform_admin(
        uow, actor_user_id=admin.id, user_id=user_id, is_platform_admin=False
    )
    await uow.commit()
    return await _user_detail(uow.session, user_id)


# --- E-72, E-73 ----------------------------------------------------------------------------------


async def list_bookings(
    session: AsyncSession,
    *,
    filters: AdminBookingFilters,
    sort: AdminBookingSort,
    page: PageParams,
) -> Page[AdminBookingSummary]:
    """E-72: every tenant's bookings (read-only, no `allowed_actions`)."""
    return await bookings_service.list_admin_bookings(
        session, filters=filters, sort=sort, page=page
    )


async def view_booking(
    uow: UnitOfWork, admin: CurrentUser, *, booking_id: UUID
) -> AdminBookingDetail:
    """E-73: the read-only staff projection with its events, then `admin.booking_viewed`
    committed in the booking's shop (spec 19 §1 "Accountability")."""
    detail = await bookings_service.get_admin_booking(uow.session, booking_id=booking_id)
    await audit_service.record_booking_viewed(
        uow,
        admin_user_id=admin.id,
        booking_id=detail.id,
        shop_id=detail.shop_id,
        reference=detail.reference,
        occurred_at=utcnow(),
    )
    await uow.commit()
    return detail


# --- E-74, E-75 ----------------------------------------------------------------------------------


def _check_period(filters: AuditFilters) -> None:
    if (
        filters.occurred_from is not None
        and filters.occurred_to is not None
        and filters.occurred_from >= filters.occurred_to
    ):
        raise ValidationFailed(
            errors=[FieldError(field="query.to", code="invalid_range", message=PERIOD_ORDER)]
        )


async def list_audit_events(
    session: AsyncSession, *, filters: AuditFilters, sort: AuditSort, page: PageParams
) -> Page[AuditEventRead]:
    """E-74: the audit log with every filter of spec 19 §4."""
    _check_period(filters)
    return await audit_service.list_events(session, filters=filters, sort=sort, page=page)


@dataclass(frozen=True, slots=True)
class AuditExport:
    """E-75's file: its name, its CSV lines (header first) and how many data rows it holds."""

    filename: str
    lines: tuple[str, ...]
    rows: int


def _cells(event: AuditEventRead) -> list[str]:
    """One export row in `EXPORT_COLUMNS` order: wire values (timestamps in UTC with `Z`), `None`
    as an empty cell, the metadata as compact JSON."""
    data = event.model_dump(mode="json")
    cells = []
    for column in EXPORT_COLUMNS:
        value = data[column]
        if column == "metadata":
            cells.append(
                json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )
        else:
            cells.append("" if value is None else str(value))
    return cells


async def export_audit_events(
    uow: UnitOfWork, admin: CurrentUser, *, filters: AuditFilters
) -> AuditExport:
    """E-75: at most 10 000 rows matching `filters`, newest first, as RFC 4180 CSV (UTF-8, header
    row, formula prefixes neutralised). The rows are read first, then `admin.audit_exported` with
    `{filters, rows}` is committed, so the export never contains its own audit row."""
    _check_period(filters)
    now = utcnow()
    events = [event async for event in audit_service.export_events(uow.session, filters=filters)]
    lines = tuple(csv_lines(EXPORT_COLUMNS, (_cells(event) for event in events)))
    await audit_service.record_audit_exported(
        uow, admin_user_id=admin.id, filters=filters, rows=len(events), occurred_at=now
    )
    await uow.commit()
    return AuditExport(
        filename=f"bayflow-audit-{now:%Y%m%dT%H%M%SZ}.csv", lines=lines, rows=len(events)
    )

"""Use cases and look-ups of the shops module (`modules/shops.md` §5).

- Use cases (top-level, each commits once): `create_shop`, `update_shop` (D37 grid-change guard),
  `replace_working_hours`, `add_member`, `update_member`, `create_service`, `update_service`, and
  the internal, seed-only `set_rating` (D56). Reads behind routes: `get_shop`, `list_members`,
  `list_services`, `list_public_shops`, `list_public_cities`, `get_public_shop`, `get_me`.
- Look-ups for other modules (nested reads, never commit): `get_active_membership` (used by
  `app.shared.auth`, D9/D20), `list_memberships_for_user`, `get_listed_shop`, `get_bookable_shop`,
  `get_shop_briefs`, `get_schedule_config`, `snapshot_services`, `require_eligible_member`,
  `list_active_member_ids`, `get_owner_user_id`, `get_member_refs`, `list_team`,
  `get_setup_flags`, P2 `get_shop_profile`.
- The D86 read port `ShopActivityReader` (`register_activity_reader`) for the bookings facts that
  shops responses show (`has_future_bookings`, `open_jobs`); unregistered, it raises.
- Platform admin (spec 19, D94-D96): the nested levers `suspend_shop` / `reactivate_shop` (the
  admin use case commits), the read port `get_shop_suspension` (used by `app.shared.auth` and the
  bookings customer actions), and the cross-tenant reads `list_shops_for_admin`,
  `list_shop_ids_for_admin`, `get_admin_shop_records`, `count_shops`, `count_staff_users`,
  `list_staff_user_ids`, `list_memberships_everywhere`, `get_shop_timezones`.

A suspended shop is treated exactly like an unlisted one by the public reads and booking creation
(404, D96). Every change publishes its audit event (`events.py`, spec 19 §3.3) inside its
transaction and only when something really changed. Owner-only writes re-check the actor's role
here too (no active membership → 404, another role → 403), so the seed's direct calls are
validated exactly like HTTP calls; the suspension levers re-check the platform admin flag the same
way. Every timestamp of a use case is one clock instant, read after its row lock (D63). This
service never imports `app.shared.auth` (spec 01 rule 8) and never imports bookings (rule 3).
"""

import logging
import uuid
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from limits import RateLimitItem
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    Conflict,
    FieldError,
    Forbidden,
    MemberNotEligible,
    NotFound,
    RateLimited,
    Unauthenticated,
    ValidationFailed,
)
from app.core.security import (
    MEMBER_CREATION_LIMIT,
    SHOP_CREATION_LIMIT,
    account_limiter,
    retry_after_seconds,
)
from app.modules.identity import service as identity_service
from app.modules.identity.schemas import UserRecord, to_user_read
from app.modules.shops.domain.capabilities import (
    ROLE_ORDER,
    SA_VISIBLE_ROLES,
    TEAM_VIEW_ROLES,
    capabilities_for,
)
from app.modules.shops.domain.grid import (
    ScheduleConfig,
    WorkingDay,
    hours_fit_grid,
    normalised_week,
    week_problems,
)
from app.modules.shops.domain.slugs import free_slug_candidates, slugify
from app.modules.shops.events import (
    GRID_FIELDS,
    FieldValue,
    MembershipActiveChanged,
    MembershipAdded,
    MembershipRoleChanged,
    ShopCreated,
    ShopGridChanging,
    ShopSuspensionChanged,
    ShopUpdated,
    WorkingHoursReplaced,
)
from app.modules.shops.models import Service, Shop, ShopMembership, ShopWorkingHours
from app.modules.shops.repository import (
    MembershipRepository,
    ServiceRepository,
    ShopRepository,
    WorkingHoursRepository,
)
from app.modules.shops.schemas import (
    AdminMembershipRecord,
    AdminShopQuery,
    AdminShopRecord,
    AdminShopSqlSort,
    MemberCreate,
    MemberCreatedRead,
    MemberRead,
    MemberRef,
    MembershipRead,
    MembershipRecord,
    MemberUpdate,
    MeRead,
    ServiceBrief,
    ServiceCreate,
    ServiceRead,
    ServiceSnapshot,
    ServiceUpdate,
    SetupFlags,
    ShopBrief,
    ShopCreate,
    ShopPublicDetail,
    ShopPublicSummary,
    ShopRead,
    ShopStats,
    ShopSuspension,
    ShopUpdate,
    TeamMember,
    UserContact,
    WorkingHoursRead,
    WorkingHoursUpdate,
    WorkingHoursWrite,
    format_wall_clock,
)
from app.shared.clock import utcnow
from app.shared.enums import MembershipRole
from app.shared.orm import touch
from app.shared.pagination import Page, PageParams
from app.shared.uow import UnitOfWork

logger = logging.getLogger(__name__)

SHOP_CREATION_SCOPE = "shop-create"  # limiter key ("shop-create", <user_id>), D69
MEMBER_CREATION_SCOPE = "member-create"  # limiter key ("member-create", <shop_id>), D69
SLUG_ATTEMPTS = 6  # the first free candidate plus at most 5 retries after lost races (§7.3)

ROLE_LABELS: Mapping[MembershipRole, str] = {
    MembershipRole.OWNER: "Owner",
    MembershipRole.SERVICE_ADVISOR: "Service Advisor",
    MembershipRole.TECHNICIAN: "Technician",
    MembershipRole.PARTS_PERSON: "Parts Person",
    MembershipRole.QC_INSPECTOR: "QC Inspector",
}

ALREADY_A_MEMBER = "Already a member of this shop — change the role or reactivate instead."
OWNER_MEMBERSHIP_IS_FIXED = "The owner's membership cannot be changed or deactivated."
DUPLICATE_SERVICE_NAME = "This shop already has an active service with this name."
HOURS_NOT_ON_NEW_GRID = (
    "The working hours do not lie on the new slot grid. Move them first, then change the slot "
    "duration."
)
SUSPENSION_REASON_MIN_LENGTH = 5
SUSPENSION_REASON_MAX_LENGTH = 500
ALREADY_SUSPENDED = "This shop is already suspended."
NOT_SUSPENDED = "This shop is not suspended."


# --- D86 read port: bookings facts shown on shops responses -------------------------------------


class ShopActivityReader(Protocol):
    """Bookings facts that shops shows without importing bookings (D86, `modules/shops.md` §5.3).

    Implemented by `bookings.service.shop_activity_reader` and registered at start-up by
    `create_app()` (and the seed) through `register_activity_reader`.
    """

    async def has_future_bookings(
        self, session: AsyncSession, *, shop_id: uuid.UUID, now: datetime
    ) -> bool:
        """A booking with `slot_start > now` that is not `CANCELLED` exists."""
        ...

    async def count_open_jobs(
        self, session: AsyncSession, *, shop_id: uuid.UUID, user_ids: Collection[uuid.UUID]
    ) -> Mapping[uuid.UUID, int]:
        """Per user: bookings not `READY_FOR_PICKUP`/`COMPLETED`/`CANCELLED` where the user is the
        technician, the parts person or the current QC picker (absent = 0)."""
        ...


UNREGISTERED_READER_MESSAGE = (
    "no ShopActivityReader is registered: bookings.service.register_ports() must run first "
    "(D86, D89)"
)


@dataclass(slots=True)
class _Ports:
    activity_reader: ShopActivityReader | None = None


_ports = _Ports()


def register_activity_reader(reader: ShopActivityReader | None) -> ShopActivityReader | None:
    """Install the bookings implementation of the port (D86; `bookings.service.register_ports()`
    through `create_app()`'s `wire_modules()`, D89, and the seed). `None` unregisters it.

    Returns the reader it replaced, so a test can restore it afterwards.
    """
    previous, _ports.activity_reader = _ports.activity_reader, reader
    return previous


def get_activity_reader() -> ShopActivityReader:
    """The registered reader. Unregistered → `RuntimeError`: fail loudly in a mis-wired app or
    test, never silently report "no bookings" (`modules/shops.md` §5.3, spec 01 rule 3)."""
    reader = _ports.activity_reader
    if reader is None:
        raise RuntimeError(UNREGISTERED_READER_MESSAGE)
    return reader


# --- Helpers --------------------------------------------------------------------------------------


def _rate_limit(item: RateLimitItem, *identifiers: str) -> None:
    """Count one attempt; 429 `RATE_LIMITED` with `Retry-After` once the window is full (D69)."""
    if not account_limiter().hit(item, *identifiers):
        retry_after = retry_after_seconds(item, *identifiers)
        raise RateLimited(
            f"Too many attempts. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


async def _require_owner(
    session: AsyncSession, *, shop_id: uuid.UUID, actor_user_id: uuid.UUID
) -> None:
    """Defence in depth behind the route guard (D16, D20): 404 for a non-member, 403 for a member
    whose role is not `OWNER`."""
    membership = await MembershipRepository(session).get_active(
        shop_id=shop_id, user_id=actor_user_id
    )
    if membership is None:
        raise NotFound
    if membership.role != MembershipRole.OWNER:
        raise Forbidden


def _validated_week(
    entries: Sequence[WorkingHoursWrite], step_minutes: int
) -> tuple[WorkingDay, ...]:
    """The 7 days of a submitted week, or 422 with one error per broken rule (§7.1)."""
    days = [entry.to_working_day() for entry in entries]
    problems = week_problems(days, step_minutes)
    if problems:
        raise ValidationFailed(
            errors=[
                FieldError(field=problem.path, code=problem.code, message=problem.message)
                for problem in problems
            ]
        )
    return normalised_week(days)


def _day_of(row: ShopWorkingHours) -> WorkingDay:
    return WorkingDay(
        weekday=row.weekday,
        is_closed=row.is_closed,
        opens_at=row.opens_at,
        closes_at=row.closes_at,
    )


def _week_of(rows: Iterable[ShopWorkingHours]) -> tuple[WorkingDay, ...]:
    return normalised_week([_day_of(row) for row in rows])


def _working_hours_read(rows: Iterable[ShopWorkingHours]) -> list[WorkingHoursRead]:
    return [
        WorkingHoursRead(
            weekday=day.weekday,
            is_closed=day.is_closed,
            opens_at=format_wall_clock(day.opens_at),
            closes_at=format_wall_clock(day.closes_at),
        )
        for day in _week_of(rows)
    ]


def _rating(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _shop_read(
    shop: Shop, rows: Iterable[ShopWorkingHours], *, has_future_bookings: bool
) -> ShopRead:
    return ShopRead(
        id=shop.id,
        slug=shop.slug,
        name=shop.name,
        address=shop.address,
        city=shop.city,
        phone=shop.phone,
        timezone=shop.timezone,
        slot_duration_minutes=shop.slot_duration_minutes,
        slot_capacity=shop.slot_capacity,
        logo_url=shop.logo_url,
        rating=_rating(shop.rating),
        is_listed=shop.is_listed,
        has_future_bookings=has_future_bookings,
        working_hours=_working_hours_read(rows),
        created_at=shop.created_at,
        updated_at=shop.updated_at,
    )


def _member_read(membership: ShopMembership, user: UserRecord, open_jobs: int) -> MemberRead:
    return MemberRead(
        membership_id=membership.id,
        user=to_user_read(user),
        role=membership.role,
        is_active=membership.is_active,
        open_jobs=open_jobs,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


def _changes(record: object, data: ShopUpdate | ServiceUpdate) -> dict[str, object]:
    """The fields sent in a PATCH whose value differs from the stored one (§7.4 step 3)."""
    return {
        field: getattr(data, field)
        for field in sorted(data.model_fields_set)
        if getattr(record, field) != getattr(data, field)
    }


def _json_value(value: object) -> FieldValue:
    """A `ShopUpdate` value as JSON: str, int, bool or None (anything else as its text)."""
    if value is None or isinstance(value, str | int | bool):
        return value
    return str(value)


def _field_changes(shop: Shop, changes: Mapping[str, object]) -> dict[str, dict[str, FieldValue]]:
    """`{field: {"from": stored, "to": new}}` of the changed fields only (spec 19 §3.3)."""
    return {
        field: {"from": _json_value(getattr(shop, field)), "to": _json_value(value)}
        for field, value in changes.items()
    }


async def _load_shop(session: AsyncSession, shop_id: uuid.UUID) -> Shop:
    shop = await ShopRepository(session).get(shop_id=shop_id)
    if shop is None:
        raise NotFound
    return shop


async def _lock_shop(session: AsyncSession, shop_id: uuid.UUID) -> Shop:
    """The shop row `FOR UPDATE`: the first lock of grid and working-hours changes (D37)."""
    shop = await ShopRepository(session).get_for_update(shop_id=shop_id)
    if shop is None:
        raise NotFound
    return shop


# --- Shops ----------------------------------------------------------------------------------------


async def create_shop(uow: UnitOfWork, *, actor_user_id: uuid.UUID, data: ShopCreate) -> ShopRead:
    """`POST /api/v1/shops` (D17): any user creates a shop and becomes its `OWNER`.

    One transaction inserts the shop (slug from the name, `-2`, `-3` … on a clash), its 7
    working-hours rows and the caller's `OWNER` membership; other memberships are untouched.
    """
    _rate_limit(SHOP_CREATION_LIMIT, SHOP_CREATION_SCOPE, str(actor_user_id))
    week = _validated_week(data.working_hours, data.slot_duration_minutes)
    session = uow.session
    if await identity_service.get_active_user(session, actor_user_id) is None:
        raise Unauthenticated
    now = utcnow()
    shops = ShopRepository(session)
    base = slugify(data.name)
    shop = Shop(
        name=data.name,
        address=data.address,
        city=data.city,
        phone=data.phone,
        timezone=data.timezone,
        slot_duration_minutes=data.slot_duration_minutes,
        slot_capacity=data.slot_capacity,
        logo_url=data.logo_url,
        rating=None,
        is_listed=data.is_listed,
        created_at=now,
        updated_at=now,
    )
    candidates = free_slug_candidates(base, await shops.taken_slugs(base))
    await shops.add_with_slug(shop, candidates, attempts=SLUG_ATTEMPTS)
    rows = WorkingHoursRepository(session).add_week(shop_id=shop.id, days=week, now=now)
    MembershipRepository(session).add(
        ShopMembership(
            shop_id=shop.id,
            user_id=actor_user_id,
            role=MembershipRole.OWNER,
            is_active=True,
            created_by_user_id=actor_user_id,
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()  # the audit row references the shop (FK), so the shop is written first
    await uow.publish(ShopCreated(shop_id=shop.id, actor_user_id=actor_user_id, occurred_at=now))
    await uow.commit()
    logger.info("shops.shop_created", extra={"shop_id": str(shop.id)})
    return _shop_read(shop, rows, has_future_bookings=False)


async def get_shop(session: AsyncSession, *, shop_id: uuid.UUID) -> ShopRead:
    """`GET /api/v1/shops/{shop_id}` (the membership was checked by the route dependency)."""
    shop = await _load_shop(session, shop_id)
    rows = await WorkingHoursRepository(session).list_for_shop(shop_id=shop_id)
    has_future = await get_activity_reader().has_future_bookings(
        session, shop_id=shop_id, now=utcnow()
    )
    return _shop_read(shop, rows, has_future_bookings=has_future)


async def update_shop(
    uow: UnitOfWork, *, shop_id: uuid.UUID, actor_user_id: uuid.UUID, data: ShopUpdate
) -> ShopRead:
    """`PATCH /api/v1/shops/{shop_id}` with the D37 grid-change guard (§7.4).

    The shop row is locked first. When `slot_duration_minutes` or `timezone` really changes,
    `ShopGridChanging` is published before anything is written: the bookings handler answers 409
    `CONFLICT` while future non-cancelled bookings exist, which rolls the whole change back. A new
    duration must also keep the current working hours on its grid (422 `hours_not_on_grid`).
    """
    session = uow.session
    await _require_owner(session, shop_id=shop_id, actor_user_id=actor_user_id)
    shop = await _lock_shop(session, shop_id)
    now = utcnow()
    changes = _changes(shop, data)
    rows = await WorkingHoursRepository(session).list_for_shop(shop_id=shop_id)
    grid_changes = tuple(field for field in GRID_FIELDS if field in changes)
    if grid_changes:
        await uow.publish(
            ShopGridChanging(
                shop_id=shop_id,
                changed_fields=grid_changes,
                actor_user_id=actor_user_id,
                occurred_at=now,
            )
        )
        new_step = changes.get("slot_duration_minutes")
        if isinstance(new_step, int) and not hours_fit_grid(_week_of(rows), new_step):
            raise ValidationFailed(
                errors=[
                    FieldError(
                        field="slot_duration_minutes",
                        code="hours_not_on_grid",
                        message=HOURS_NOT_ON_NEW_GRID,
                    )
                ]
            )
    diff = _field_changes(shop, changes)
    for field, value in changes.items():
        setattr(shop, field, value)
    if changes:
        touch(shop, now)
        await uow.publish(
            ShopUpdated(shop_id=shop_id, actor_user_id=actor_user_id, changes=diff, occurred_at=now)
        )
    # Read before the commit: a missing port must fail the request, never a committed change.
    has_future = await get_activity_reader().has_future_bookings(session, shop_id=shop_id, now=now)
    await uow.commit()
    return _shop_read(shop, rows, has_future_bookings=has_future)


async def replace_working_hours(
    uow: UnitOfWork, *, shop_id: uuid.UUID, actor_user_id: uuid.UUID, data: WorkingHoursUpdate
) -> ShopRead:
    """`PUT /api/v1/shops/{shop_id}/working-hours` (§7.5): always allowed; idempotent.

    The shop row lock serialises with booking creation's `FOR SHARE` (D37), so a booking is
    validated entirely against the old hours or entirely against the new ones. Bookings already
    placed outside the new hours are kept; their slots are simply no longer offered.
    """
    session = uow.session
    await _require_owner(session, shop_id=shop_id, actor_user_id=actor_user_id)
    shop = await _lock_shop(session, shop_id)
    week = _validated_week(data.working_hours, shop.slot_duration_minutes)
    now = utcnow()
    hours = WorkingHoursRepository(session)
    rows = {row.weekday: row for row in await hours.list_for_shop(shop_id=shop_id)}
    changed = False
    for day in week:
        row = rows.get(day.weekday)
        if row is None:  # a shop missing a weekday row (never created by this service)
            rows[day.weekday] = hours.add_week(shop_id=shop_id, days=[day], now=now)[0]
            changed = True
        elif (row.is_closed, row.opens_at, row.closes_at) != (
            day.is_closed,
            day.opens_at,
            day.closes_at,
        ):
            row.is_closed, row.opens_at, row.closes_at = day.is_closed, day.opens_at, day.closes_at
            touch(row, now)
            changed = True
    if changed:
        touch(shop, now)
        await uow.publish(
            WorkingHoursReplaced(shop_id=shop_id, actor_user_id=actor_user_id, occurred_at=now)
        )
    has_future = await get_activity_reader().has_future_bookings(session, shop_id=shop_id, now=now)
    await uow.commit()
    return _shop_read(shop, rows.values(), has_future_bookings=has_future)


async def set_rating(uow: UnitOfWork, *, shop_id: uuid.UUID, rating: Decimal | None) -> None:
    """Internal, seed only (D56): the placeholder rating, 0-5 with one decimal; null = "New"."""
    if rating is not None and not (
        Decimal(0) <= rating <= Decimal(5) and rating == rating.quantize(Decimal("0.1"))
    ):
        raise ValidationFailed(
            errors=[
                FieldError(
                    field="rating",
                    code="value_error",
                    message="A rating is 0 to 5 with at most one decimal.",
                )
            ]
        )
    shop = await _load_shop(uow.session, shop_id)
    now = utcnow()
    if shop.rating != rating:
        shop.rating = rating
        touch(shop, now)
    await uow.commit()


# --- Team -----------------------------------------------------------------------------------------


async def list_members(
    session: AsyncSession,
    *,
    shop_id: uuid.UUID,
    caller_role: MembershipRole,
    roles: Collection[MembershipRole] | None,
    is_active: bool | None,
    page: PageParams,
) -> Page[MemberRead]:
    """`GET …/members` (§7.6): the Owner sees every membership (inactive and `OWNER` included); a
    Service Advisor only active technicians and parts persons with an active account (the assign
    pickers), filters intersecting that set. Ordered by role (glossary order), name, id."""
    if caller_role not in TEAM_VIEW_ROLES:
        raise Forbidden
    role_filter = set(roles) if roles else None
    sa_view = caller_role == MembershipRole.SERVICE_ADVISOR
    if sa_view:
        role_filter = (
            set(SA_VISIBLE_ROLES) if role_filter is None else role_filter & SA_VISIBLE_ROLES
        )
        if is_active is False or not role_filter:
            return Page.build([], total=0, params=page)
        is_active = True
    memberships = await MembershipRepository(session).list_for_shop(
        shop_id=shop_id, roles=role_filter, is_active=is_active
    )
    users = await identity_service.get_users_by_ids(session, [m.user_id for m in memberships])
    visible = [
        membership
        for membership in memberships
        if membership.user_id in users and (not sa_view or users[membership.user_id].is_active)
    ]
    visible.sort(
        key=lambda m: (ROLE_ORDER[m.role], users[m.user_id].full_name.lower(), m.id),
    )
    window = visible[page.offset : page.offset + page.limit]
    open_jobs = await get_activity_reader().count_open_jobs(
        session, shop_id=shop_id, user_ids=[m.user_id for m in window]
    )
    items = [_member_read(m, users[m.user_id], open_jobs.get(m.user_id, 0)) for m in window]
    return Page.build(items, total=len(visible), params=page)


async def add_member(
    uow: UnitOfWork, *, shop_id: uuid.UUID, actor_user_id: uuid.UUID, data: MemberCreate
) -> MemberCreatedRead:
    """`POST …/members` (§7.6, D18): staff are only ever added by the shop's Owner.

    Existing e-mail → only a membership (the account's password, name and phone are never
    modified; a supplied password is ignored). New e-mail → the account (with the Owner's
    password) and the membership, in one transaction. Any existing membership here → 409.
    """
    session = uow.session
    await _require_owner(session, shop_id=shop_id, actor_user_id=actor_user_id)
    _rate_limit(MEMBER_CREATION_LIMIT, MEMBER_CREATION_SCOPE, str(shop_id))
    now = utcnow()
    memberships = MembershipRepository(session)
    user = await identity_service.find_user_by_email(session, data.email)
    account_created = user is None
    if user is not None:
        if await memberships.get_for_user(shop_id=shop_id, user_id=user.id) is not None:
            raise Conflict(ALREADY_A_MEMBER)
    elif data.password is None:
        raise ValidationFailed(
            errors=[
                FieldError(
                    field="password",
                    code="missing",
                    message="A new account needs an initial password (12 to 128 characters).",
                )
            ]
        )
    else:
        # Argon2 runs here; this use case holds no row lock (§11).
        user = await identity_service.create_user(
            uow,
            email=data.email,
            full_name=data.full_name,
            password=data.password,
            phone=data.phone,
            now=now,
        )
    membership = memberships.add(
        ShopMembership(
            shop_id=shop_id,
            user_id=user.id,
            role=data.role.membership_role,
            is_active=True,
            created_by_user_id=actor_user_id,
            created_at=now,
            updated_at=now,
        )
    )
    # A concurrent add of the same person fails on `uq_shop_memberships_shop_id_user_id` → 409.
    await session.flush()
    await uow.publish(
        MembershipAdded(
            shop_id=shop_id,
            membership_id=membership.id,
            user_id=user.id,
            role=membership.role,
            actor_user_id=actor_user_id,
            occurred_at=now,
        )
    )
    await uow.commit()
    logger.info(
        "shops.member_added",
        extra={"shop_id": str(shop_id), "membership_id": str(membership.id)},
    )
    member = _member_read(membership, user, open_jobs=0)  # a new membership has no assignments
    return MemberCreatedRead(**member.model_dump(), account_created=account_created)


async def update_member(
    uow: UnitOfWork,
    *,
    shop_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    membership_id: uuid.UUID,
    data: MemberUpdate,
) -> MemberRead:
    """`PATCH …/members/{membership_id}` (§7.6, D19): change the role, deactivate or reactivate.

    Another shop's membership is invisible (404). The `OWNER` membership → 403 `FORBIDDEN`, whoever
    asks and whatever the body. Effective on the member's next request (D9); bookings assigned to
    the member stay assigned.
    """
    session = uow.session
    await _require_owner(session, shop_id=shop_id, actor_user_id=actor_user_id)
    membership = await MembershipRepository(session).get_for_update(
        shop_id=shop_id, membership_id=membership_id
    )
    if membership is None:
        raise NotFound
    if membership.role == MembershipRole.OWNER:
        raise Forbidden(OWNER_MEMBERSHIP_IS_FIXED)
    now = utcnow()
    events: list[MembershipRoleChanged | MembershipActiveChanged] = []
    if data.role is not None and membership.role != data.role.membership_role:
        events.append(
            MembershipRoleChanged(
                shop_id=shop_id,
                membership_id=membership.id,
                user_id=membership.user_id,
                from_role=membership.role,
                to_role=data.role.membership_role,
                actor_user_id=actor_user_id,
                occurred_at=now,
            )
        )
        membership.role = data.role.membership_role
    if data.is_active is not None and membership.is_active != data.is_active:
        events.append(
            MembershipActiveChanged(
                shop_id=shop_id,
                membership_id=membership.id,
                user_id=membership.user_id,
                is_active=data.is_active,
                actor_user_id=actor_user_id,
                occurred_at=now,
            )
        )
        membership.is_active = data.is_active
    changed = bool(events)
    if changed:
        touch(membership, now)
    for event in events:
        await uow.publish(event)
    user = await identity_service.get_user(session, membership.user_id)
    if user is None:  # pragma: no cover - the FK guarantees the account exists
        raise NotFound
    open_jobs = await get_activity_reader().count_open_jobs(
        session, shop_id=shop_id, user_ids=[membership.user_id]
    )
    await uow.commit()
    if changed:
        logger.info(
            "shops.member_updated",
            extra={"shop_id": str(shop_id), "membership_id": str(membership.id)},
        )
    return _member_read(membership, user, open_jobs.get(membership.user_id, 0))


# --- Service catalogue ----------------------------------------------------------------------------


async def list_services(
    session: AsyncSession, *, shop_id: uuid.UUID, include_inactive: bool, page: PageParams
) -> Page[ServiceRead]:
    """`GET …/services`: by name (case-insensitive), then id."""
    services = ServiceRepository(session)
    rows = await services.page(
        shop_id=shop_id, include_inactive=include_inactive, limit=page.limit, offset=page.offset
    )
    total = await services.count(shop_id=shop_id, include_inactive=include_inactive)
    return Page.build(
        [ServiceRead.model_validate(service) for service in rows], total=total, params=page
    )


async def create_service(
    uow: UnitOfWork, *, shop_id: uuid.UUID, actor_user_id: uuid.UUID, data: ServiceCreate
) -> ServiceRead:
    """`POST …/services` (§7.7): a duplicate active name (case-insensitive) → 409 `CONFLICT`."""
    session = uow.session
    await _require_owner(session, shop_id=shop_id, actor_user_id=actor_user_id)
    services = ServiceRepository(session)
    if data.is_active and await services.active_name_taken(shop_id=shop_id, name=data.name):
        raise Conflict(DUPLICATE_SERVICE_NAME)
    now = utcnow()
    service = services.add(
        Service(
            shop_id=shop_id,
            name=data.name,
            description=data.description,
            estimated_duration_minutes=data.estimated_duration_minutes,
            base_price=data.base_price,
            is_active=data.is_active,
            created_at=now,
            updated_at=now,
        )
    )
    # Backstop for a concurrent insert: `uq_services_active_name` → 409 CONFLICT (spec 02 §7.5).
    await uow.commit()
    return ServiceRead.model_validate(service)


async def update_service(
    uow: UnitOfWork,
    *,
    shop_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    service_id: uuid.UUID,
    data: ServiceUpdate,
) -> ServiceRead:
    """`PATCH …/services/{service_id}` (§7.7): another shop's service → 404; renaming or
    reactivating into an active duplicate → 409. Existing bookings keep their snapshots (D34)."""
    session = uow.session
    await _require_owner(session, shop_id=shop_id, actor_user_id=actor_user_id)
    services = ServiceRepository(session)
    service = await services.get_for_update(shop_id=shop_id, service_id=service_id)
    if service is None:
        raise NotFound
    now = utcnow()
    changes = _changes(service, data)
    name = changes.get("name", service.name)
    becomes_active = changes.get("is_active", service.is_active)
    if (
        becomes_active
        and ("name" in changes or "is_active" in changes)
        and isinstance(name, str)
        and await services.active_name_taken(shop_id=shop_id, name=name, exclude_id=service.id)
    ):
        raise Conflict(DUPLICATE_SERVICE_NAME)
    for field, value in changes.items():
        setattr(service, field, value)
    if changes:
        touch(service, now)
    await uow.commit()
    return ServiceRead.model_validate(service)


# --- Public directory (D64, D68) ------------------------------------------------------------------


async def list_public_shops(
    session: AsyncSession, *, q: str | None, city: str | None, page: PageParams
) -> Page[ShopPublicSummary]:
    """`GET /api/v1/public/shops`: listed shops with at least one active service, by name."""
    query = (q or "").strip() or None
    city_filter = (city or "").strip() or None
    shops = ShopRepository(session)
    rows = await shops.directory_page(
        q=query, city=city_filter, limit=page.limit, offset=page.offset
    )
    total = await shops.directory_count(q=query, city=city_filter)
    services = await ServiceRepository(session).active_names_for_shops(
        shop_ids=[shop.id for shop in rows]
    )
    items = []
    for shop in rows:
        offered = services.get(shop.id, [])
        items.append(
            ShopPublicSummary(
                id=shop.id,
                slug=shop.slug,
                name=shop.name,
                city=shop.city,
                logo_url=shop.logo_url,
                rating=_rating(shop.rating),
                services=[ServiceBrief(id=service_id, name=name) for service_id, name in offered],
                services_count=len(offered),
            )
        )
    return Page.build(items, total=total, params=page)


async def list_public_cities(session: AsyncSession) -> list[str]:
    """`GET /api/v1/public/cities`: one spelling per case-insensitive city of the directory."""
    return await ShopRepository(session).directory_cities()


def _publicly_visible(shop: Shop) -> bool:
    """Listed and not suspended: a suspended shop is treated exactly like an unlisted one by the
    directory, the shop page, availability and booking creation (D96, spec 19 §2)."""
    return shop.is_listed and not shop.is_suspended


async def _public_detail(session: AsyncSession, shop: Shop) -> ShopPublicDetail:
    rows = await WorkingHoursRepository(session).list_for_shop(shop_id=shop.id)
    services = [
        ServiceRead.model_validate(service)
        for service in await ServiceRepository(session).list_active(shop_id=shop.id)
    ]
    return ShopPublicDetail(
        id=shop.id,
        slug=shop.slug,
        name=shop.name,
        address=shop.address,
        city=shop.city,
        phone=shop.phone,
        logo_url=shop.logo_url,
        rating=_rating(shop.rating),
        timezone=shop.timezone,
        slot_duration_minutes=shop.slot_duration_minutes,
        working_hours=_working_hours_read(rows),
        services=services,
        is_bookable=bool(services),
    )


async def get_public_shop(session: AsyncSession, *, shop_slug: str) -> ShopPublicDetail:
    """`GET /api/v1/public/shops/{shop_slug}`: an unknown or unlisted slug → 404; a listed shop
    without an active service → 200 with `services: []` and `is_bookable: false` (D64)."""
    shop = await ShopRepository(session).get_by_slug(shop_slug)
    if shop is None or not _publicly_visible(shop):
        raise NotFound
    return await _public_detail(session, shop)


async def get_shop_profile(session: AsyncSession, *, shop_id: uuid.UUID) -> ShopPublicDetail:
    """P2: the public facts of a shop by id, whatever its listing (the AI agent's `GET …/shop`)."""
    return await _public_detail(session, await _load_shop(session, shop_id))


# --- Current user (D66, D81) ----------------------------------------------------------------------


async def get_me(session: AsyncSession, *, user_id: uuid.UUID) -> MeRead:
    """`GET /api/v1/me`: the account plus its **active** memberships, sorted by shop name, each
    with server-computed `capabilities` (D66). `tasks.manage` only while calling is enabled.
    `is_platform_admin` (D94) and each shop's `shop_suspended` (D96) come from spec 19."""
    user = await identity_service.get_active_user(session, user_id)
    if user is None:
        raise Unauthenticated
    tasks_enabled = get_settings().calling_enabled
    memberships = [
        MembershipRead(
            membership_id=membership.id,
            shop_id=shop.id,
            shop_name=shop.name,
            shop_slug=shop.slug,
            shop_suspended=shop.is_suspended,
            role=membership.role,
            capabilities=capabilities_for(membership.role, tasks_enabled=tasks_enabled),
        )
        for membership, shop in await MembershipRepository(session).list_active_for_user(
            user_id=user_id
        )
    ]
    return MeRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        is_platform_admin=user.is_platform_admin,
        memberships=memberships,
    )


# --- Look-ups for other modules (nested reads) ----------------------------------------------------


async def get_active_membership(
    session: AsyncSession, *, shop_id: uuid.UUID, user_id: uuid.UUID
) -> MembershipRecord | None:
    """The user's active membership in the shop, re-read on every request (D9, D20)."""
    membership = await MembershipRepository(session).get_active(shop_id=shop_id, user_id=user_id)
    return MembershipRecord.model_validate(membership) if membership is not None else None


async def list_memberships_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    roles: Collection[MembershipRole] | None = None,
) -> list[MembershipRecord]:
    """The user's active memberships (optionally only these roles), sorted by shop name."""
    rows = await MembershipRepository(session).list_active_for_user(user_id=user_id, roles=roles)
    return [MembershipRecord.model_validate(membership) for membership, _ in rows]


async def get_listed_shop(session: AsyncSession, *, shop_slug: str) -> ShopBrief | None:
    """A shop by slug if it is listed and not suspended (availability, spec 03 §4.5, D96)."""
    shop = await ShopRepository(session).get_by_slug(shop_slug)
    if shop is None or not _publicly_visible(shop):
        return None
    return ShopBrief.model_validate(shop)


async def get_bookable_shop(session: AsyncSession, *, shop_id: uuid.UUID) -> ShopBrief | None:
    """A shop that accepts bookings: listed, not suspended **and** at least one active service
    (D64, D96)."""
    shop = await ShopRepository(session).get(shop_id=shop_id)
    if shop is None or not _publicly_visible(shop):
        return None
    if not await ServiceRepository(session).has_active(shop_id=shop_id):
        return None
    return ShopBrief.model_validate(shop)


async def get_shop_briefs(
    session: AsyncSession, *, shop_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, ShopBrief]:
    """Shop facts by id, whatever the listing state, in one query (unknown ids are absent)."""
    shops = await ShopRepository(session).get_many(shop_ids=set(shop_ids))
    return {shop.id: ShopBrief.model_validate(shop) for shop in shops}


async def get_schedule_config(
    session: AsyncSession, *, shop_id: uuid.UUID, for_share: bool = False
) -> ScheduleConfig:
    """The slot settings and the 7 working days of a shop (D37).

    `for_share=True` reads the shop row `SELECT … FOR SHARE` (booking creation's first lock): a
    concurrent grid change waits for the booking, or the booking sees the new grid (CON-05). The
    hours rows need no lock because every writer holds the shop row `FOR UPDATE` first.
    """
    shops = ShopRepository(session)
    shop = await (shops.get_for_share(shop_id=shop_id) if for_share else shops.get(shop_id=shop_id))
    if shop is None:
        raise NotFound
    rows = await WorkingHoursRepository(session).list_for_shop(shop_id=shop_id)
    return ScheduleConfig(
        shop_id=shop.id,
        timezone=shop.timezone,
        slot_duration_minutes=shop.slot_duration_minutes,
        slot_capacity=shop.slot_capacity,
        days=_week_of(rows),
    )


async def snapshot_services(
    session: AsyncSession, *, shop_id: uuid.UUID, service_ids: Sequence[uuid.UUID]
) -> list[ServiceSnapshot]:
    """Name and base price of each selected service, in request order (D34).

    Every id must be an active service of this shop; all bad ids are reported at once as 422
    `service_ids.N` `invalid_reference` (unknown, inactive and other shops' ids look the same).
    """
    rows = await ServiceRepository(session).get_many(shop_id=shop_id, service_ids=set(service_ids))
    active = {service.id: service for service in rows if service.is_active}
    errors = [
        FieldError(
            field=f"service_ids.{index}",
            code="invalid_reference",
            message="This service is not offered by the shop.",
        )
        for index, service_id in enumerate(service_ids)
        if service_id not in active
    ]
    if errors:
        raise ValidationFailed(errors=errors)
    return [
        ServiceSnapshot(
            service_id=service_id,
            name=active[service_id].name,
            base_price=active[service_id].base_price,
        )
        for service_id in service_ids
    ]


async def require_eligible_member(
    session: AsyncSession,
    *,
    shop_id: uuid.UUID,
    user_id: uuid.UUID,
    role: MembershipRole,
    field: str,
) -> MemberRef:
    """An assignee must have an active membership with exactly `role` here and an active account;
    otherwise 422 `MEMBER_NOT_ELIGIBLE` with one `invalid_reference` error on `field` (BK-21)."""
    membership = await MembershipRepository(session).get_active(shop_id=shop_id, user_id=user_id)
    user = None
    if membership is not None and membership.role == role:
        user = await identity_service.get_active_user(session, user_id)
    if user is None:
        raise MemberNotEligible(
            errors=[
                FieldError(
                    field=field,
                    code="invalid_reference",
                    message=f"Choose an active {ROLE_LABELS[role]} of this shop.",
                )
            ]
        )
    return MemberRef(user_id=user.id, full_name=user.full_name, is_active=True)


async def list_active_member_ids(
    session: AsyncSession, *, shop_id: uuid.UUID, roles: Collection[MembershipRole]
) -> list[uuid.UUID]:
    """Users with an active membership in one of `roles` **and** an active account, sorted by id
    (D26 "SAs of the shop", `QC_REQUESTED` recipients, booking viewers)."""
    if not roles:
        return []
    memberships = await MembershipRepository(session).list_for_shop(
        shop_id=shop_id, roles=set(roles), is_active=True
    )
    users = await identity_service.get_users_by_ids(session, [m.user_id for m in memberships])
    return sorted(
        membership.user_id
        for membership in memberships
        if membership.user_id in users and users[membership.user_id].is_active
    )


async def get_owner_user_id(session: AsyncSession, *, shop_id: uuid.UUID) -> uuid.UUID:
    """The user holding the shop's single `OWNER` membership (D15, D26 fallback)."""
    owner_id = await MembershipRepository(session).owner_user_id(shop_id=shop_id)
    if owner_id is None:
        raise NotFound
    return owner_id


async def get_member_refs(
    session: AsyncSession, *, shop_id: uuid.UUID, user_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, MemberRef]:
    """`MemberRef`s of these users in this shop, any status (`is_active` = the membership, so a
    deactivated assignee shows a warning, D19). Users without a membership here are absent."""
    memberships = await MembershipRepository(session).list_for_users(
        shop_id=shop_id, user_ids=set(user_ids)
    )
    users = await identity_service.get_users_by_ids(session, [m.user_id for m in memberships])
    return {
        membership.user_id: MemberRef(
            user_id=membership.user_id,
            full_name=users[membership.user_id].full_name,
            is_active=membership.is_active,
        )
        for membership in memberships
        if membership.user_id in users
    }


async def list_team(session: AsyncSession, *, shop_id: uuid.UUID) -> list[TeamMember]:
    """Every membership of the shop, active or not, with the member's name (reporting overview),
    ordered like the members list (role, name, id)."""
    memberships = await MembershipRepository(session).list_for_shop(shop_id=shop_id)
    users = await identity_service.get_users_by_ids(session, [m.user_id for m in memberships])
    team = [
        TeamMember(
            membership_id=membership.id,
            user_id=membership.user_id,
            full_name=users[membership.user_id].full_name,
            role=membership.role,
            is_active=membership.is_active,
        )
        for membership in memberships
        if membership.user_id in users
    ]
    team.sort(
        key=lambda member: (ROLE_ORDER[member.role], member.full_name.lower(), member.membership_id)
    )
    return team


async def get_setup_flags(session: AsyncSession, *, shop_id: uuid.UUID) -> SetupFlags:
    """Reporting overview `setup`: active services, an active non-owner member, listing."""
    shop = await _load_shop(session, shop_id)
    return SetupFlags(
        has_services=await ServiceRepository(session).has_active(shop_id=shop_id),
        has_team=await MembershipRepository(session).has_active_staff(shop_id=shop_id),
        is_listed=shop.is_listed,
    )


# --- Platform admin: suspension (D96, spec 19 §2) and cross-tenant reads (spec 19 §4) ----------


def _suspension(shop: Shop) -> ShopSuspension | None:
    if (
        shop.suspended_at is None
        or shop.suspended_reason is None
        or shop.suspended_by_user_id is None
    ):
        return None
    return ShopSuspension(
        suspended_at=shop.suspended_at,
        reason=shop.suspended_reason,
        suspended_by_user_id=shop.suspended_by_user_id,
    )


async def get_shop_suspension(
    session: AsyncSession, *, shop_id: uuid.UUID
) -> ShopSuspension | None:
    """The read port behind 403 `SHOP_SUSPENDED` (spec 19 §6): the shop's suspension, or None
    when it is not suspended (or unknown). Re-read on every call, like the membership (D9)."""
    shop = await ShopRepository(session).get(shop_id=shop_id)
    return None if shop is None else _suspension(shop)


async def _require_platform_admin(session: AsyncSession, actor_user_id: uuid.UUID) -> None:
    """Defence in depth behind the admin routes (D94): only an active platform admin may suspend
    or reactivate a shop (403), whoever calls the service. The actor's row is locked `FOR SHARE`
    first (`identity.lock_acting_platform_admin`), so an admin revoked or deactivated by a
    concurrent request cannot act: the revoke waits for this commit, or committed first and this
    re-read refuses (spec 19 §1). User row before shop row, always."""
    await identity_service.lock_acting_platform_admin(session, actor_user_id=actor_user_id)


def _suspension_reason(reason: str) -> str:
    text = reason.strip()
    if not SUSPENSION_REASON_MIN_LENGTH <= len(text) <= SUSPENSION_REASON_MAX_LENGTH:
        message = (
            f"Give a reason of {SUSPENSION_REASON_MIN_LENGTH} to "
            f"{SUSPENSION_REASON_MAX_LENGTH} characters."
        )
        raise ValidationFailed(
            errors=[FieldError(field="reason", code="value_error", message=message)]
        )
    return text


async def suspend_shop(
    uow: UnitOfWork, *, shop_id: uuid.UUID, actor_user_id: uuid.UUID, reason: str
) -> None:
    """E-64 (nested; the admin use case commits): suspend a shop with a reason of 5-500 characters.

    The shop row is locked `FOR UPDATE`, so two admins acting at once queue and the second gets 409
    (spec 19 §7). Unknown → 404; already suspended → 409 `CONFLICT`. Nothing else changes:
    bookings, stock and memberships stay as they are (D96). Publishes `ShopSuspensionChanged`.
    """
    text = _suspension_reason(reason)
    session = uow.session
    await _require_platform_admin(session, actor_user_id)
    shop = await _lock_shop(session, shop_id)
    now = utcnow()
    if shop.is_suspended:
        raise Conflict(ALREADY_SUSPENDED)
    shop.suspended_at = now
    shop.suspended_reason = text
    shop.suspended_by_user_id = actor_user_id
    touch(shop, now)
    await uow.publish(
        ShopSuspensionChanged(
            shop_id=shop_id,
            actor_user_id=actor_user_id,
            suspended=True,
            reason=text,
            occurred_at=now,
        )
    )


async def reactivate_shop(uow: UnitOfWork, *, shop_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
    """E-65 (nested; the admin use case commits): lift a suspension; everything resumes (D96).
    Unknown → 404; not suspended → 409 `CONFLICT`. Publishes `ShopSuspensionChanged`."""
    session = uow.session
    await _require_platform_admin(session, actor_user_id)
    shop = await _lock_shop(session, shop_id)
    now = utcnow()
    if not shop.is_suspended:
        raise Conflict(NOT_SUSPENDED)
    shop.suspended_at = None
    shop.suspended_reason = None
    shop.suspended_by_user_id = None
    touch(shop, now)
    await uow.publish(
        ShopSuspensionChanged(
            shop_id=shop_id, actor_user_id=actor_user_id, suspended=False, occurred_at=now
        )
    )


async def _owner_ids_for(session: AsyncSession, query: AdminShopQuery) -> list[uuid.UUID]:
    """The users whose e-mail contains `q` (E-62 searches the owner's e-mail through identity)."""
    text = (query.q or "").strip()
    if not text:
        return []
    return await identity_service.find_user_ids_by_email(session, q=text)


async def _admin_records(session: AsyncSession, shops: Sequence[Shop]) -> list[AdminShopRecord]:
    """Owners (name, e-mail) and active member counts of these shops, one query each."""
    ids = [shop.id for shop in shops]
    memberships = MembershipRepository(session)
    owners = await memberships.owners_of(shop_ids=ids)
    counts = await memberships.active_counts(shop_ids=ids)
    users = await identity_service.get_users_by_ids(session, set(owners.values()))
    records = []
    for shop in shops:
        owner = users.get(owners[shop.id]) if shop.id in owners else None
        records.append(
            AdminShopRecord(
                id=shop.id,
                slug=shop.slug,
                name=shop.name,
                city=shop.city,
                created_at=shop.created_at,
                is_listed=shop.is_listed,
                suspension=_suspension(shop),
                owners=(
                    []
                    if owner is None
                    else [
                        UserContact(user_id=owner.id, full_name=owner.full_name, email=owner.email)
                    ]
                ),
                active_members=counts.get(shop.id, 0),
            )
        )
    return records


async def list_shops_for_admin(
    session: AsyncSession, query: AdminShopQuery, *, sort: AdminShopSqlSort, page: PageParams
) -> tuple[list[AdminShopRecord], int]:
    """E-62 sorted by `-created_at` or `name`: every tenant matching the filters, one page."""
    owner_ids = await _owner_ids_for(session, query)
    shops, total = await ShopRepository(session).admin_page(
        query, owner_ids=owner_ids, sort=sort, limit=page.limit, offset=page.offset
    )
    return await _admin_records(session, shops), total


async def list_shop_ids_for_admin(session: AsyncSession, query: AdminShopQuery) -> list[uuid.UUID]:
    """Every shop matching E-62's filters, by name: the admin ranks them by bookings itself."""
    owner_ids = await _owner_ids_for(session, query)
    return await ShopRepository(session).admin_ids(query, owner_ids=owner_ids)


async def get_admin_shop_records(
    session: AsyncSession, *, shop_ids: Sequence[uuid.UUID]
) -> list[AdminShopRecord]:
    """These shops as E-62 lists them, in the order given (unknown ids are skipped)."""
    by_id = {shop.id: shop for shop in await ShopRepository(session).get_many(shop_ids=shop_ids)}
    return await _admin_records(
        session, [by_id[shop_id] for shop_id in shop_ids if shop_id in by_id]
    )


async def count_shops(session: AsyncSession, *, since: datetime) -> ShopStats:
    """E-61: every shop, not suspended, suspended, `is_listed` set, created since `since`."""
    return await ShopRepository(session).stats(since=since)


async def count_staff_users(session: AsyncSession) -> int:
    """E-61: users with at least one active membership (the staff of E-66's `kind`)."""
    return await MembershipRepository(session).count_active_member_users()


async def list_staff_user_ids(session: AsyncSession) -> frozenset[uuid.UUID]:
    """E-66 `kind`: the users with at least one active membership anywhere."""
    return frozenset(await MembershipRepository(session).active_member_user_ids())


async def list_memberships_everywhere(
    session: AsyncSession, *, user_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, list[AdminMembershipRecord]]:
    """Every membership of these users, active or not, with its shop, by shop name (E-66, E-67)."""
    grouped: dict[uuid.UUID, list[AdminMembershipRecord]] = {}
    rows = await MembershipRepository(session).list_for_users_everywhere(user_ids=user_ids)
    for membership, shop in rows:
        grouped.setdefault(membership.user_id, []).append(
            AdminMembershipRecord(
                membership_id=membership.id,
                shop=ShopBrief.model_validate(shop),
                role=membership.role,
                is_active=membership.is_active,
            )
        )
    return grouped


async def get_shop_timezones(session: AsyncSession) -> dict[uuid.UUID, str]:
    """Every shop's IANA time zone (the admin's shop-local date filters, D38)."""
    return await ShopRepository(session).timezones()

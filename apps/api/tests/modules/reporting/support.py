"""Test support for the reporting module's DB and API tests.

- `Cast` / `make_cast()`: a shop with one member per role, a second technician and QC inspector,
  and a deactivated technician, as ORM rows (`tests.rows`): reporting only reads, so rows are the
  fastest faithful input.
- `booking_rows()` / `add_booking()`: bookings in any status with the columns spec 02's CHECKs
  require (assignees, QC picker, cancellation and completion fields).
- `part_row()`, `service_row()`, `purchase_order_rows()`: catalogue and procurement rows.
- `FAKE_BOOKINGS_READS`: plain-SQL stand-ins for `bookings.service.count_by_status`,
  `count_open_jobs` and `count_day_activity` (signatures pinned in `modules/bookings.md` §5.3),
  installed while the bookings build still raises `NotImplementedError`. They are the executable
  contract reporting relies on; `test_bookings_reads_contract.py` holds the real ones to it.
- `REAL_BOOKINGS_READS`: the real functions, captured at import time (before any monkeypatch).
- HTTP helpers: `bearer()`, `overview_url()`, `SUMMARY_URL`.
"""

import itertools
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.core.security import issue_token
from app.modules.bookings import service as bookings_service
from app.modules.bookings.models import Booking
from app.modules.bookings.service import DayActivity
from app.modules.identity.models import User
from app.modules.inventory.models import Part, PurchaseOrder, PurchaseOrderItem
from app.modules.shops.models import Service, Shop
from app.shared.clock import utcnow
from app.shared.enums import BookingStatus, MembershipRole, PurchaseOrderStatus
from tests.rows import (
    FRIDAY_1000_PKT,
    add_rows,
    make_booking,
    make_membership,
    make_part,
    make_shop,
    make_user,
    make_vehicle,
)

SUMMARY_URL = "/api/v1/me/owner-summary"
KARACHI = "Asia/Karachi"
LONDON = "Europe/London"

# The 17 statuses exactly as glossary §3 lists them (an independent copy of the spec).
GLOSSARY_STATUS_ORDER = [
    "PENDING",
    "CONFIRMED",
    "ASSIGNED",
    "INSPECTING",
    "ESTIMATE_REVIEW",
    "AWAITING_CUSTOMER",
    "ESTIMATE_APPROVED",
    "ESTIMATE_REJECTED",
    "PARTS_PENDING",
    "PARTS_ORDERED",
    "PARTS_READY",
    "IN_REPAIR",
    "QC_PENDING",
    "QC_IN_PROGRESS",
    "READY_FOR_PICKUP",
    "COMPLETED",
    "CANCELLED",
]

_sequence = itertools.count(1)


def overview_url(shop_id: object) -> str:
    return f"/api/v1/shops/{shop_id}/overview"


def bearer(user: User) -> dict[str, str]:
    """`Authorization: Bearer <session token>` stamped with the app clock (spec 12 §4.2)."""
    return {"Authorization": f"Bearer {issue_token(user.id, 'session', utcnow())}"}


# --- Shops and teams ------------------------------------------------------------------------------


@dataclass
class Cast:
    """A shop with its Owner, one SA, two technicians, one Parts Person, two QC inspectors and a
    deactivated technician (D19: inactive memberships stay listed in the overview's team)."""

    shop: Shop
    owner: User
    advisor: User
    technician: User
    technician_2: User
    parts: User
    qc: User
    qc_2: User
    former: User

    @property
    def id(self) -> UUID:
        return self.shop.id

    def members_by_role(self) -> dict[MembershipRole, User]:
        """One active member per role."""
        return {
            MembershipRole.OWNER: self.owner,
            MembershipRole.SERVICE_ADVISOR: self.advisor,
            MembershipRole.TECHNICIAN: self.technician,
            MembershipRole.PARTS_PERSON: self.parts,
            MembershipRole.QC_INSPECTOR: self.qc,
        }


async def make_cast(
    db: Database,
    *,
    owner: User | None = None,
    name: str | None = None,
    timezone: str = KARACHI,
    city: str = "Lahore",
) -> Cast:
    """A shop and its team. `owner` may be an existing user (an owner of several shops)."""
    n = next(_sequence)
    shop_values: dict[str, Any] = {"timezone": timezone, "city": city}
    if name is not None:
        shop_values.update(name=name, slug=f"reporting-shop-{n}")
    shop = make_shop(**shop_values)
    new_owner = owner is None
    owner = owner or make_user(full_name="Fatima Raza")
    advisor = make_user(full_name="Bilal")
    technician = make_user(full_name="Imran")
    technician_2 = make_user(full_name="hamza")  # lower case: the order is case-insensitive
    parts = make_user(full_name="Usman")
    qc = make_user(full_name="Sara")
    qc_2 = make_user(full_name="Hina")
    former = make_user(full_name="Zubair")
    users = [advisor, technician, technician_2, parts, qc, qc_2, former]
    await add_rows(
        db.sessionmaker,
        *([owner] if new_owner else []),
        *users,
        shop,
        make_membership(shop, owner, MembershipRole.OWNER),
        make_membership(shop, advisor, MembershipRole.SERVICE_ADVISOR, created_by=owner),
        make_membership(shop, technician, MembershipRole.TECHNICIAN, created_by=owner),
        make_membership(shop, technician_2, MembershipRole.TECHNICIAN, created_by=owner),
        make_membership(shop, parts, MembershipRole.PARTS_PERSON, created_by=owner),
        make_membership(shop, qc, MembershipRole.QC_INSPECTOR, created_by=owner),
        make_membership(shop, qc_2, MembershipRole.QC_INSPECTOR, created_by=owner),
        make_membership(shop, former, MembershipRole.TECHNICIAN, created_by=owner, is_active=False),
    )
    return Cast(shop, owner, advisor, technician, technician_2, parts, qc, qc_2, former)


async def make_owned_shop(
    db: Database, owner: User, *, name: str, timezone: str = KARACHI, city: str = "Lahore"
) -> Shop:
    """A shop whose only member is `owner` (an existing user)."""
    n = next(_sequence)
    shop = make_shop(name=name, slug=f"owned-shop-{n}", timezone=timezone, city=city)
    await add_rows(db.sessionmaker, shop, make_membership(shop, owner, MembershipRole.OWNER))
    return shop


@dataclass
class World:
    a: Cast
    b: Cast
    customer: User  # a global customer account, no membership anywhere


# --- Bookings -------------------------------------------------------------------------------------

_BEFORE_TECHNICIAN = {BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.CANCELLED}
_BEFORE_PARTS_PERSON = _BEFORE_TECHNICIAN | {
    BookingStatus.ASSIGNED,
    BookingStatus.INSPECTING,
    BookingStatus.ESTIMATE_REVIEW,
    BookingStatus.AWAITING_CUSTOMER,
    BookingStatus.ESTIMATE_APPROVED,
    BookingStatus.ESTIMATE_REJECTED,
}
_WITH_QC_PICKER = {
    BookingStatus.QC_IN_PROGRESS,
    BookingStatus.READY_FOR_PICKUP,
    BookingStatus.COMPLETED,
}


def booking_rows(
    cast: Cast,
    customer: User,
    status: BookingStatus,
    **overrides: Any,
) -> list[object]:
    """A vehicle and a booking in `status`, with every column the status requires (spec 02 §3.8
    CHECKs): technician from `ASSIGNED`, parts person from `PARTS_PENDING`, the QC picker in
    `QC_IN_PROGRESS` / `READY_FOR_PICKUP` / `COMPLETED`, `completed_at` iff `COMPLETED`, and the
    cancellation fields iff `CANCELLED`. `overrides` set any booking column."""
    slot_start = overrides.get("slot_start", FRIDAY_1000_PKT)
    values: dict[str, Any] = {"status": status, "slot_start": slot_start}
    if status not in _BEFORE_TECHNICIAN:
        values["technician_user_id"] = cast.technician.id
    if status not in _BEFORE_PARTS_PERSON:
        values["parts_person_user_id"] = cast.parts.id
    if status in _WITH_QC_PICKER:
        values["qc_inspector_user_id"] = cast.qc.id
    if status == BookingStatus.COMPLETED:
        values["completed_at"] = slot_start + timedelta(hours=3)
    if status == BookingStatus.CANCELLED:
        values["cancelled_at"] = slot_start - timedelta(days=1)
        values["cancelled_by_user_id"] = customer.id
    values.update(overrides)
    vehicle = make_vehicle(customer)
    return [vehicle, make_booking(cast.shop, customer, vehicle, **values)]


async def add_booking(
    db: Database, cast: Cast, customer: User, status: BookingStatus, **overrides: Any
) -> Booking:
    rows = booking_rows(cast, customer, status, **overrides)
    await add_rows(db.sessionmaker, *rows)
    booking = rows[1]
    assert isinstance(booking, Booking)
    return booking


async def add_bookings(
    db: Database, cast: Cast, customer: User, statuses: Collection[BookingStatus]
) -> None:
    """One booking per entry of `statuses` (repeats allowed), in one transaction."""
    rows = [row for status in statuses for row in booking_rows(cast, customer, status)]
    await add_rows(db.sessionmaker, *rows)


# --- Catalogue and procurement --------------------------------------------------------------------


def part_row(  # noqa: PLR0913 - one keyword per stock column a test sets
    cast: Cast,
    sku: str,
    *,
    on_hand: int = 0,
    reserved: int = 0,
    reorder_level: int = 0,
    unit_cost: str = "900",
    active: bool = True,
) -> Part:
    return make_part(
        cast.shop,
        sku=sku,
        name=f"Part {sku}",
        on_hand=on_hand,
        reserved=reserved,
        reorder_level=reorder_level,
        unit_cost=Decimal(unit_cost),
        is_active=active,
    )


def service_row(cast: Cast, name: str, *, active: bool = True) -> Service:
    return Service(
        shop_id=cast.id,
        name=name,
        estimated_duration_minutes=60,
        base_price=Decimal("2000"),
        is_active=active,
    )


def purchase_order_rows(
    cast: Cast,
    status: PurchaseOrderStatus,
    items: Collection[tuple[Part, int, int]] = (),
) -> list[object]:
    """A general purchase order in `status` with `(part, ordered, received)` items."""
    order = PurchaseOrder(
        shop_id=cast.id,
        po_number=f"PO-T{next(_sequence):05d}",
        status=status,
        created_by_user_id=cast.parts.id,
        received_at=utcnow() if status == PurchaseOrderStatus.RECEIVED else None,
    )
    lines = [
        PurchaseOrderItem(
            shop_id=cast.id,
            purchase_order_id=order.id,
            part_id=part.id,
            ordered_qty=ordered,
            received_qty=received,
            unit_cost=part.unit_cost,
        )
        for part, ordered, received in items
    ]
    return [order, *lines]


# --- Bookings' three count reads: plain-SQL stand-ins (modules/bookings.md §5.3) ------------------


async def fake_count_by_status(session: AsyncSession, *, shop_id: UUID) -> dict[BookingStatus, int]:
    """Every booking of the shop counted by status; all 17 statuses are keys, zeros included."""
    result = await session.execute(
        text("SELECT status, count(*) FROM bookings WHERE shop_id = :shop_id GROUP BY status"),
        {"shop_id": shop_id},
    )
    counts = dict.fromkeys(BookingStatus, 0)
    for status, count in result.all():
        counts[BookingStatus(status)] = int(count)
    return counts


async def fake_count_open_jobs(
    session: AsyncSession, *, shop_id: UUID, user_ids: Collection[UUID]
) -> dict[UUID, int]:
    """Distinct bookings not `READY_FOR_PICKUP` / `COMPLETED` / `CANCELLED` where the user is the
    technician, the parts person or the current QC picker; every requested id is a key."""
    wanted = set(user_ids)
    counts = dict.fromkeys(wanted, 0)
    result = await session.execute(
        text(
            "SELECT technician_user_id, parts_person_user_id, qc_inspector_user_id"
            " FROM bookings WHERE shop_id = :shop_id"
            " AND status NOT IN ('READY_FOR_PICKUP', 'COMPLETED', 'CANCELLED')"
        ),
        {"shop_id": shop_id},
    )
    for row in result.all():
        for user_id in set(row) & wanted:  # each booking counts once per user
            counts[user_id] += 1
    return counts


async def fake_count_day_activity(
    session: AsyncSession, *, shop_id: UUID, start: datetime, end: datetime
) -> DayActivity:
    """Non-cancelled bookings whose `slot_start` is in `[start, end)`, and bookings whose
    `completed_at` is in `[start, end)`."""
    row = (
        await session.execute(
            text(
                "SELECT"
                " count(*) FILTER (WHERE status <> 'CANCELLED'"
                " AND slot_start >= :start AND slot_start < :end),"
                " count(*) FILTER (WHERE completed_at >= :start AND completed_at < :end)"
                " FROM bookings WHERE shop_id = :shop_id"
            ),
            {"shop_id": shop_id, "start": start, "end": end},
        )
    ).one()
    return DayActivity(bookings=int(row[0]), completed=int(row[1]))


BookingsRead = Callable[..., Awaitable[Any]]

FAKE_BOOKINGS_READS: dict[str, BookingsRead] = {
    "count_by_status": fake_count_by_status,
    "count_open_jobs": fake_count_open_jobs,
    "count_day_activity": fake_count_day_activity,
}

REAL_BOOKINGS_READS: dict[str, BookingsRead] = {
    "count_by_status": bookings_service.count_by_status,
    "count_open_jobs": bookings_service.count_open_jobs,
    "count_day_activity": bookings_service.count_day_activity,
}

_PROBE_START = datetime(2026, 10, 15, 19, 0, tzinfo=UTC)


def _probe_arguments(name: str) -> dict[str, Any]:
    arguments: dict[str, Any] = {"shop_id": uuid4()}
    if name == "count_open_jobs":
        arguments["user_ids"] = [uuid4()]
    if name == "count_day_activity":
        arguments.update(start=_PROBE_START, end=_PROBE_START + timedelta(days=1))
    return arguments


async def is_implemented(name: str, session: AsyncSession) -> bool:
    """False while bookings' real `name` still raises `NotImplementedError` (wave 2 in progress).
    Any other error propagates, so a broken implementation fails the test loudly."""
    try:
        await REAL_BOOKINGS_READS[name](session, **_probe_arguments(name))
    except NotImplementedError:
        return False
    return True

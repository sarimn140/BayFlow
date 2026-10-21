"""SQL for the bookings module's tables: `vehicles`, `bookings`, `booking_services` and
`booking_events` (spec 02 §3.7-§3.10, §7; `modules/bookings.md` §4).

- Every read of shop data is scoped: by `shop_id` (staff), by `customer_user_id` (customer), or by
  `(shop_id, booking_id)` / `(owner_user_id, vehicle_id)` keys that came from such a scoped read
  (D20). There is no "get a booking by id" for user-facing paths; `get_unscoped` serves only the
  push-time viewer look-up, which has nothing but the event's booking id.
- The locking reads are key-only (`id` + `shop_id` or `customer_user_id`, never `status`) and use
  `populate_existing`, so a transaction that waited for the lock sees the committed row and answers
  409, never a misleading 404 (spec 02 §7.3).
- `booking_events` is append-only: this module only ever adds and reads rows (spec 02 §8).
- `status_changed_at` is derived from the events (spec 03 §3.3): the latest event whose
  `from_status` is distinct from its `to_status` (the `CREATE` event counts).
- The platform admin's reads (spec 19 §4 E-61, E-72, D94) are separate, explicitly named queries
  over every tenant (`admin_page`, `created_per_bucket`, `finished_between`, `created_by_shop`).
  They never touch the D21 predicate that staff and customer reads use, and never lock.
"""

import itertools
import uuid
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Label,
    Select,
    UnaryExpression,
    and_,
    distinct,
    exists,
    false,
    func,
    or_,
    select,
    true,
    tuple_,
    union_all,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.modules.bookings.domain.state_machine import TERMINAL_STATUSES
from app.modules.bookings.domain.visibility import QC_QUEUE_STATUSES, SHOP_WIDE_ROLES
from app.modules.bookings.models import Booking, BookingEvent, BookingService, Vehicle
from app.shared.enums import BookingStatus, MembershipRole
from app.shared.repository import Repository, constraint_name

REFERENCE_CONSTRAINT = "uq_bookings_reference"

OPEN_JOB_EXCLUDED_STATUSES: tuple[BookingStatus, ...] = (
    BookingStatus.READY_FOR_PICKUP,
    BookingStatus.COMPLETED,
    BookingStatus.CANCELLED,
)
"""`open_jobs` counts every booking except these (spec 03 §3.2 `MemberRead.open_jobs`)."""

BookingKey = tuple[uuid.UUID, uuid.UUID]
"""`(shop_id, booking_id)`: how children of already-authorised bookings are read (D20)."""


# --- The D21 predicate ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StaffScope:
    """The bookings one staff caller may see in one shop (D21) — the SQL twin of
    `domain.visibility.can_view`. `inspected_ids` is only used for `QC_INSPECTOR`."""

    shop_id: uuid.UUID
    role: MembershipRole
    user_id: uuid.UUID
    inspected_ids: frozenset[uuid.UUID] = frozenset()


def shop_condition(shop_id: uuid.UUID) -> ColumnElement[bool]:
    """Every booking of the shop (reporting's counts, which are not caller-scoped)."""
    return Booking.shop_id == shop_id


def visibility_condition(scope: StaffScope) -> ColumnElement[bool]:
    """`bookings.shop_id = :shop_id` AND the caller's D21 rule (`modules/bookings.md` §7.5)."""
    in_shop = Booking.shop_id == scope.shop_id
    if scope.role in SHOP_WIDE_ROLES:
        return in_shop
    if scope.role == MembershipRole.TECHNICIAN:
        return and_(in_shop, Booking.technician_user_id == scope.user_id)
    if scope.role == MembershipRole.PARTS_PERSON:
        return and_(in_shop, Booking.parts_person_user_id == scope.user_id)
    if scope.role == MembershipRole.QC_INSPECTOR:
        visible: ColumnElement[bool] = Booking.status.in_(sorted(QC_QUEUE_STATUSES))
        if scope.inspected_ids:
            visible = or_(visible, Booking.id.in_(sorted(scope.inspected_ids)))
        return and_(in_shop, visible)
    return false()  # an unknown role sees nothing (fail closed)


def status_changed_at_column() -> Label[datetime]:
    """`status_changed_at` of each selected booking, as a correlated aggregate."""
    return (
        select(func.max(BookingEvent.created_at))
        .where(
            BookingEvent.booking_id == Booking.id,
            BookingEvent.shop_id == Booking.shop_id,
            BookingEvent.from_status.is_distinct_from(BookingEvent.to_status),
        )
        .correlate(Booking)
        .scalar_subquery()
        .label("status_changed_at")
    )


# --- Query values ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StaffListQuery:
    """One page of `GET …/bookings` (spec 03 §4.8), resolved by the service: free text is split
    into its three matches, shop-local dates are UTC bounds (`slot_to` exclusive)."""

    scope: StaffScope
    statuses: tuple[BookingStatus, ...] = ()
    text: str | None = None
    registration: str | None = None
    customer_ids: tuple[uuid.UUID, ...] = ()
    slot_from: datetime | None = None
    slot_to: datetime | None = None
    technician_user_id: uuid.UUID | None = None
    parts_person_user_id: uuid.UUID | None = None
    sort: str = "-updated_at"
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True, slots=True)
class SlotWindow:
    """A half-open UTC window `[start, end)` on `slot_start` for the shops of one time zone
    (`shop_ids` None = every shop); a bound may be open (None)."""

    start: datetime | None
    end: datetime | None
    shop_ids: frozenset[uuid.UUID] | None = None


@dataclass(frozen=True, slots=True)
class AdminListQuery:
    """One page of the platform admin's booking list (E-72): every tenant, no D21 predicate.

    `slot_windows`: the shop-local date filter, one window per time zone (None = no date filter;
    an empty tuple matches nothing)."""

    shop_id: uuid.UUID | None = None
    customer_user_id: uuid.UUID | None = None
    statuses: tuple[BookingStatus, ...] = ()
    text: str | None = None
    registration: str | None = None
    customer_ids: tuple[uuid.UUID, ...] = ()
    slot_windows: tuple[SlotWindow, ...] | None = None
    sort: str = "-slot_start"
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True, slots=True)
class CustomerListQuery:
    """One page of `GET /api/v1/me/bookings`: own bookings at every shop."""

    customer_user_id: uuid.UUID
    active: bool | None
    sort: str
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class BookingRefRow:
    id: uuid.UUID
    reference: str
    status: BookingStatus
    version: int


type BookingRow = tuple[Booking, datetime | None]
"""A booking with its `status_changed_at` (None only for rows written without any event)."""

_SORT_COLUMNS: dict[str, Any] = {
    "slot_start": Booking.slot_start,
    "updated_at": Booking.updated_at,
    "created_at": Booking.created_at,
}


def _order_by(sort: str, changed: Label[datetime]) -> list[UnaryExpression[Any]]:
    """`sort` (`field` or `-field`) then `id`, so every page order is deterministic."""
    name = sort.removeprefix("-")
    column = changed if name == "status_changed_at" else _SORT_COLUMNS[name]
    primary = column.desc() if sort.startswith("-") else column.asc()
    return [primary, Booking.id.asc()]


def _text_match(
    text: str, registration: str | None, customer_ids: Sequence[uuid.UUID]
) -> ColumnElement[bool]:
    """Free text on a booking: the reference contains it, the vehicle's registration key contains
    its normalised form, or the customer is one of `customer_ids` (resolved by identity)."""
    matches: list[ColumnElement[bool]] = [Booking.reference.icontains(text, autoescape=True)]
    if registration:
        matches.append(
            exists().where(
                Vehicle.id == Booking.vehicle_id,
                Vehicle.owner_user_id == Booking.customer_user_id,
                Vehicle.registration_key.contains(registration, autoescape=True),
            )
        )
    if customer_ids:
        matches.append(Booking.customer_user_id.in_(customer_ids))
    return or_(*matches)


def _staff_conditions(query: StaffListQuery) -> list[ColumnElement[bool]]:
    conditions = [visibility_condition(query.scope)]
    if query.statuses:
        conditions.append(Booking.status.in_(query.statuses))
    if query.text is not None:
        conditions.append(_text_match(query.text, query.registration, query.customer_ids))
    if query.slot_from is not None:
        conditions.append(Booking.slot_start >= query.slot_from)
    if query.slot_to is not None:
        conditions.append(Booking.slot_start < query.slot_to)
    if query.technician_user_id is not None:
        conditions.append(Booking.technician_user_id == query.technician_user_id)
    if query.parts_person_user_id is not None:
        conditions.append(Booking.parts_person_user_id == query.parts_person_user_id)
    return conditions


def _window_condition(window: SlotWindow) -> ColumnElement[bool]:
    parts: list[ColumnElement[bool]] = []
    if window.shop_ids is not None:
        parts.append(Booking.shop_id.in_(sorted(window.shop_ids)))
    if window.start is not None:
        parts.append(Booking.slot_start >= window.start)
    if window.end is not None:
        parts.append(Booking.slot_start < window.end)
    return and_(true(), *parts)


def _admin_conditions(query: AdminListQuery) -> list[ColumnElement[bool]]:
    """E-72's filters over every tenant (spec 19 §4): never the D21 predicate."""
    conditions: list[ColumnElement[bool]] = []
    if query.shop_id is not None:
        conditions.append(Booking.shop_id == query.shop_id)
    if query.customer_user_id is not None:
        conditions.append(Booking.customer_user_id == query.customer_user_id)
    if query.statuses:
        conditions.append(Booking.status.in_(query.statuses))
    if query.text is not None:
        conditions.append(_text_match(query.text, query.registration, query.customer_ids))
    if query.slot_windows is not None:
        windows = [_window_condition(window) for window in query.slot_windows]
        conditions.append(or_(*windows) if windows else false())
    return conditions


def _admin_order(sort: str) -> list[UnaryExpression[Any]]:
    """`-slot_start` (default), `slot_start` or `-created_at`, then `id`."""
    name = sort.removeprefix("-")
    column = _SORT_COLUMNS[name]
    primary = column.desc() if sort.startswith("-") else column.asc()
    return [primary, Booking.id.asc()]


def _customer_conditions(query: CustomerListQuery) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Booking.customer_user_id == query.customer_user_id]
    terminal = sorted(TERMINAL_STATUSES)
    if query.active is True:
        conditions.append(Booking.status.not_in(terminal))
    elif query.active is False:
        conditions.append(Booking.status.in_(terminal))
    return conditions


# --- Repositories ---------------------------------------------------------------------------------


class VehicleRepository(Repository):
    """Customers' vehicles (D35): global, keyed by owner; never shop data."""

    async def upsert(  # noqa: PLR0913 - one keyword per vehicles column the wizard writes
        self,
        *,
        owner_user_id: uuid.UUID,
        registration_number: str,
        registration_key: str,
        make: str,
        model: str,
        year: int,
        color: str | None,
        mileage_km: int | None,
        now: datetime,
    ) -> uuid.UUID:
        """`INSERT … ON CONFLICT (owner_user_id, registration_key) DO UPDATE … RETURNING id`: an
        atomic upsert even under concurrency (spec 02 §3.7). Re-booking the same car updates its
        details; omitted `color` / `mileage_km` keep their stored values (§7.2)."""
        values = insert(Vehicle).values(
            id=uuid.uuid4(),
            owner_user_id=owner_user_id,
            registration_number=registration_number,
            registration_key=registration_key,
            make=make,
            model=model,
            year=year,
            color=color,
            mileage_km=mileage_km,
            created_at=now,
            updated_at=now,
        )
        statement = values.on_conflict_do_update(
            index_elements=[Vehicle.owner_user_id, Vehicle.registration_key],
            set_={
                "registration_number": values.excluded.registration_number,
                "make": values.excluded.make,
                "model": values.excluded.model,
                "year": values.excluded.year,
                "color": func.coalesce(values.excluded.color, Vehicle.color),
                "mileage_km": func.coalesce(values.excluded.mileage_km, Vehicle.mileage_km),
                "updated_at": now,
            },
        ).returning(Vehicle.id)
        vehicle_id: uuid.UUID = (await self.session.execute(statement)).scalar_one()
        return vehicle_id

    async def get_many(
        self, *, keys: Collection[tuple[uuid.UUID, uuid.UUID]]
    ) -> dict[uuid.UUID, Vehicle]:
        """Vehicles by `(owner_user_id, vehicle_id)` (a booking's customer and car)."""
        if not keys:
            return {}
        statement = (
            select(Vehicle)
            .where(tuple_(Vehicle.owner_user_id, Vehicle.id).in_(sorted(set(keys))))
            .execution_options(populate_existing=True)
        )
        return {
            vehicle.id: vehicle for vehicle in (await self.session.execute(statement)).scalars()
        }

    async def list_for_owner(self, *, owner_user_id: uuid.UUID) -> list[Vehicle]:
        """The customer's vehicles, most recently updated first (spec 03 §4.7)."""
        statement = (
            select(Vehicle)
            .where(Vehicle.owner_user_id == owner_user_id)
            .order_by(Vehicle.updated_at.desc(), Vehicle.id.asc())
            .execution_options(populate_existing=True)
        )
        return list((await self.session.execute(statement)).scalars())


class BookingRepository(Repository):
    """`bookings` rows. Locking reads are key-only (spec 02 §7.3)."""

    @staticmethod
    def _staff_key(shop_id: uuid.UUID, booking_id: uuid.UUID) -> Select[Booking]:
        return (
            select(Booking)
            .where(Booking.id == booking_id, Booking.shop_id == shop_id)
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def _customer_key(customer_user_id: uuid.UUID, booking_id: uuid.UUID) -> Select[Booking]:
        return (
            select(Booking)
            .where(Booking.id == booking_id, Booking.customer_user_id == customer_user_id)
            .execution_options(populate_existing=True)
        )

    async def get(self, *, shop_id: uuid.UUID, booking_id: uuid.UUID) -> Booking | None:
        result = await self.session.execute(self._staff_key(shop_id, booking_id))
        return result.scalar_one_or_none()

    async def get_for_update(self, *, shop_id: uuid.UUID, booking_id: uuid.UUID) -> Booking | None:
        """Lock 1 of every staff action (D30): `… WHERE id = :id AND shop_id = :shop_id FOR
        UPDATE`, never filtered by `status`."""
        statement = self._staff_key(shop_id, booking_id).with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_for_customer(
        self, *, customer_user_id: uuid.UUID, booking_id: uuid.UUID
    ) -> Booking | None:
        result = await self.session.execute(self._customer_key(customer_user_id, booking_id))
        return result.scalar_one_or_none()

    async def get_for_update_customer(
        self, *, customer_user_id: uuid.UUID, booking_id: uuid.UUID
    ) -> Booking | None:
        """Lock 1 of every customer action: scoped by the caller, never by `status`."""
        statement = self._customer_key(customer_user_id, booking_id).with_for_update()
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def get_unscoped(self, booking_id: uuid.UUID) -> Booking | None:
        """Push-time look-up by id alone (`list_booking_viewer_ids`); never behind a route."""
        statement = (
            select(Booking)
            .where(Booking.id == booking_id)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def insert(self, booking: Booking) -> bool:
        """Insert inside a savepoint; False when the reference is taken (`uq_bookings_reference`).

        Rolling back to the savepoint keeps the outer transaction and the locks it holds, so the
        caller can retry with a new reference (spec 02 §7.6). Any other error propagates.
        """
        try:
            async with self.session.begin_nested():
                self.session.add(booking)
                await self.session.flush()
        except IntegrityError as exc:
            if constraint_name(exc) != REFERENCE_CONSTRAINT:
                raise
            return False
        return True

    async def staff_page(self, query: StaffListQuery) -> tuple[list[BookingRow], int]:
        """One page of the caller's visible bookings with their `status_changed_at`, and the total
        over every page (two statements whatever the page size)."""
        changed = status_changed_at_column()
        conditions = _staff_conditions(query)
        statement = (
            select(Booking, changed)
            .where(*conditions)
            .order_by(*_order_by(query.sort, changed))
            .limit(query.limit)
            .offset(query.offset)
            .execution_options(populate_existing=True)
        )
        rows: list[BookingRow] = [(row[0], row[1]) for row in await self.session.execute(statement)]
        total = await self.session.execute(
            select(func.count()).select_from(Booking).where(*conditions)
        )
        return rows, int(total.scalar_one())

    async def customer_page(self, query: CustomerListQuery) -> tuple[list[BookingRow], int]:
        """One page of the customer's own bookings (every shop) and the total."""
        changed = status_changed_at_column()
        conditions = _customer_conditions(query)
        statement = (
            select(Booking, changed)
            .where(*conditions)
            .order_by(*_order_by(query.sort, changed))
            .limit(query.limit)
            .offset(query.offset)
            .execution_options(populate_existing=True)
        )
        rows: list[BookingRow] = [(row[0], row[1]) for row in await self.session.execute(statement)]
        total = await self.session.execute(
            select(func.count()).select_from(Booking).where(*conditions)
        )
        return rows, int(total.scalar_one())

    async def customer_at_shop(
        self, *, shop_id: uuid.UUID, customer_user_id: uuid.UUID, limit: int
    ) -> list[BookingRow]:
        """P2 (spec 05 §5.3): the customer's bookings at one shop, newest slot first."""
        changed = status_changed_at_column()
        statement = (
            select(Booking, changed)
            .where(Booking.shop_id == shop_id, Booking.customer_user_id == customer_user_id)
            .order_by(Booking.slot_start.desc(), Booking.id.desc())
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        return [(row[0], row[1]) for row in await self.session.execute(statement)]

    async def get_many_at_shop(
        self, *, shop_id: uuid.UUID, booking_ids: Collection[uuid.UUID]
    ) -> list[Booking]:
        """P2: bookings of one shop by id, in one query (unknown ids are absent)."""
        if not booking_ids:
            return []
        statement = select(Booking).where(
            Booking.shop_id == shop_id, Booking.id.in_(set(booking_ids))
        )
        return list((await self.session.scalars(statement)).all())

    async def status_counts(self, *, condition: ColumnElement[bool]) -> dict[BookingStatus, int]:
        """`GROUP BY status` over the rows matching `condition` (absent statuses → absent)."""
        statement = select(Booking.status, func.count()).where(condition).group_by(Booking.status)
        return {BookingStatus(row[0]): int(row[1]) for row in await self.session.execute(statement)}

    async def has_future(self, *, shop_id: uuid.UUID, now: datetime) -> bool:
        """A booking with `slot_start > now` that is not `CANCELLED` (D37); served by
        `ix_bookings_shop_id_slot_start`."""
        statement = select(
            exists().where(
                Booking.shop_id == shop_id,
                Booking.slot_start > now,
                Booking.status != BookingStatus.CANCELLED,
            )
        )
        return bool((await self.session.execute(statement)).scalar_one())

    async def open_job_counts(
        self, *, shop_id: uuid.UUID, user_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Per user: distinct open bookings where they are technician, parts person or current QC
        picker (one statement whatever the number of users)."""
        is_open = and_(
            Booking.shop_id == shop_id, Booking.status.not_in(OPEN_JOB_EXCLUDED_STATUSES)
        )
        assignments = union_all(
            select(
                Booking.technician_user_id.label("user_id"), Booking.id.label("booking_id")
            ).where(is_open, Booking.technician_user_id.in_(user_ids)),
            select(Booking.parts_person_user_id, Booking.id).where(
                is_open, Booking.parts_person_user_id.in_(user_ids)
            ),
            select(Booking.qc_inspector_user_id, Booking.id).where(
                is_open, Booking.qc_inspector_user_id.in_(user_ids)
            ),
        ).subquery()
        statement = select(
            assignments.c.user_id, func.count(distinct(assignments.c.booking_id))
        ).group_by(assignments.c.user_id)
        return {row[0]: int(row[1]) for row in await self.session.execute(statement)}

    async def day_activity(
        self, *, shop_id: uuid.UUID, start: datetime, end: datetime
    ) -> tuple[int, int]:
        """`(bookings, completed)` of the half-open window `[start, end)` in one statement."""
        slot_in_window = and_(Booking.slot_start >= start, Booking.slot_start < end)
        completed_in_window = and_(Booking.completed_at >= start, Booking.completed_at < end)
        statement = select(
            func.count().filter(and_(slot_in_window, Booking.status != BookingStatus.CANCELLED)),
            func.count().filter(completed_in_window),
        ).where(Booking.shop_id == shop_id, or_(slot_in_window, completed_in_window))
        row = (await self.session.execute(statement)).one()
        return int(row[0]), int(row[1])

    # --- Platform admin: every tenant, read-only (spec 19 §4, D94) --------------------------------

    async def admin_page(self, query: AdminListQuery) -> tuple[list[Booking], int]:
        """One page of E-72 and the total over every page (two statements)."""
        conditions = _admin_conditions(query)
        statement = (
            select(Booking)
            .where(*conditions)
            .order_by(*_admin_order(query.sort))
            .limit(query.limit)
            .offset(query.offset)
            .execution_options(populate_existing=True)
        )
        bookings = list((await self.session.execute(statement)).scalars())
        counted = select(func.count()).select_from(Booking).where(*conditions)
        total = (await self.session.execute(counted)).scalar_one()
        return bookings, int(total)

    async def all_status_counts(self) -> dict[BookingStatus, int]:
        """Every tenant's bookings by status (absent statuses → absent)."""
        return await self.status_counts(condition=true())

    async def created_per_bucket(self, bounds: Sequence[datetime]) -> list[int]:
        """Bookings created in each `[bounds[i], bounds[i + 1])` (one statement)."""
        if len(bounds) < 2:  # noqa: PLR2004 - a bucket needs two bounds
            return []
        counts = [
            func.count().filter(Booking.created_at >= start, Booking.created_at < end)
            for start, end in itertools.pairwise(bounds)
        ]
        statement = select(*counts).where(
            Booking.created_at >= bounds[0], Booking.created_at < bounds[-1]
        )
        row = (await self.session.execute(statement)).one()
        return [int(value) for value in row]

    async def finished_between(self, *, start: datetime, end: datetime) -> tuple[int, int]:
        """`(completed, cancelled)`: bookings completed / cancelled in `[start, end)`."""
        completed = and_(Booking.completed_at >= start, Booking.completed_at < end)
        cancelled = and_(Booking.cancelled_at >= start, Booking.cancelled_at < end)
        statement = select(func.count().filter(completed), func.count().filter(cancelled)).where(
            or_(completed, cancelled)
        )
        row = (await self.session.execute(statement)).one()
        return int(row[0]), int(row[1])

    async def created_by_shop(
        self,
        *,
        start: datetime,
        end: datetime,
        shop_ids: Collection[uuid.UUID] | None = None,
        limit: int | None = None,
    ) -> list[tuple[uuid.UUID, int]]:
        """Bookings created in `[start, end)` per shop, most first (then by shop id)."""
        statement = (
            select(Booking.shop_id, func.count())
            .where(Booking.created_at >= start, Booking.created_at < end)
            .group_by(Booking.shop_id)
            .order_by(func.count().desc(), Booking.shop_id)
        )
        if shop_ids is not None:
            statement = statement.where(Booking.shop_id.in_(sorted(set(shop_ids))))
        if limit is not None:
            statement = statement.limit(limit)
        return [(row[0], int(row[1])) for row in await self.session.execute(statement)]

    async def refs(
        self, *, shop_id: uuid.UUID, booking_ids: Collection[uuid.UUID]
    ) -> list[BookingRefRow]:
        """Plain column values (never ORM rows) of the shop's bookings among `booking_ids`."""
        statement = select(Booking.id, Booking.reference, Booking.status, Booking.version).where(
            Booking.shop_id == shop_id, Booking.id.in_(sorted(set(booking_ids)))
        )
        return [
            BookingRefRow(
                id=row[0], reference=row[1], status=BookingStatus(row[2]), version=int(row[3])
            )
            for row in await self.session.execute(statement)
        ]


class BookingServiceRepository(Repository):
    """The services snapshotted at booking time (D34); immutable after insert."""

    async def list_for_bookings(
        self, *, keys: Collection[BookingKey]
    ) -> dict[uuid.UUID, list[BookingService]]:
        """Per booking, its services by name (then service id), one statement for the page."""
        if not keys:
            return {}
        statement = (
            select(BookingService)
            .where(tuple_(BookingService.shop_id, BookingService.booking_id).in_(sorted(set(keys))))
            .order_by(
                BookingService.booking_id,
                BookingService.name_snapshot,
                BookingService.service_id,
            )
        )
        grouped: dict[uuid.UUID, list[BookingService]] = defaultdict(list)
        for row in (await self.session.execute(statement)).scalars():
            grouped[row.booking_id].append(row)
        return dict(grouped)


class BookingEventRepository(Repository):
    """The audit log: add and read only (spec 02 §8)."""

    async def list_for_booking(
        self, *, shop_id: uuid.UUID, booking_id: uuid.UUID
    ) -> list[BookingEvent]:
        """Oldest first by `(created_at, seq)` (D79)."""
        statement = (
            select(BookingEvent)
            .where(BookingEvent.shop_id == shop_id, BookingEvent.booking_id == booking_id)
            .order_by(BookingEvent.created_at, BookingEvent.seq)
        )
        return list((await self.session.execute(statement)).scalars())

    async def latest(self, *, shop_id: uuid.UUID, booking_id: uuid.UUID) -> BookingEvent | None:
        """The booking's last event (`last_event`)."""
        statement = (
            select(BookingEvent)
            .where(BookingEvent.shop_id == shop_id, BookingEvent.booking_id == booking_id)
            .order_by(BookingEvent.created_at.desc(), BookingEvent.seq.desc())
            .limit(1)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def status_changed_at(self, *, keys: Collection[BookingKey]) -> dict[uuid.UUID, datetime]:
        """`status_changed_at` per booking (one aggregate statement)."""
        if not keys:
            return {}
        statement = (
            select(BookingEvent.booking_id, func.max(BookingEvent.created_at))
            .where(
                tuple_(BookingEvent.shop_id, BookingEvent.booking_id).in_(sorted(set(keys))),
                BookingEvent.from_status.is_distinct_from(BookingEvent.to_status),
            )
            .group_by(BookingEvent.booking_id)
        )
        return {row[0]: row[1] for row in await self.session.execute(statement)}

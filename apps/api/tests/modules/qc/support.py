"""Test support for the qc module's DB tests (imported by `conftest.py` and the test files).

`QcWorld` builds two shops with a full cast directly as ORM rows (`tests.rows`, the services of
the lower modules are built in parallel). `BookingsStandIn` plays the part of the bookings
executor around the qc calls (spec 08 T17-T20, "How an action is executed" steps 3-14): it locks
the booking by key, checks its status, reads the action's instant once, calls qc on the same
session, updates the booking exactly as T17-T20 do and commits. The real executor arrives with
the bookings module; until then this is how qc's nested writes run inside a real transaction.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.modules.bookings.models import Booking, Vehicle
from app.modules.identity.models import User
from app.modules.qc import service as qc
from app.modules.qc.models import QcInspection, QcIssue
from app.modules.qc.schemas import FailRecorded, QcChecklistItemWrite
from app.modules.shops.models import Shop
from app.shared.clock import SimulatedClock
from app.shared.enums import BookingStatus, MembershipRole, QcChecklistKey
from app.shared.event_bus import EventBus
from app.shared.uow import UnitOfWork
from tests.rows import add_rows, make_booking, make_membership, make_shop, make_user, make_vehicle

START = datetime(2026, 10, 16, 6, 0, tzinfo=UTC)  # Fri 16 Oct 2026 11:00 PKT


def checklist(
    *,
    failed: Sequence[QcChecklistKey] = (),
    notes: dict[QcChecklistKey, str] | None = None,
    order: Sequence[QcChecklistKey] | None = None,
) -> list[QcChecklistItemWrite]:
    """A complete D46 checklist (every key once); `failed` items are not passed."""
    notes = notes or {}
    return [
        QcChecklistItemWrite(key=key, passed=key not in failed, note=notes.get(key))
        for key in (order or list(QcChecklistKey))
    ]


def uow_for(session: AsyncSession) -> UnitOfWork:
    return UnitOfWork(session, EventBus())


@dataclass
class ShopCast:
    shop: Shop
    owner: User
    advisor: User
    technician: User
    parts: User
    inspector: User
    inspector_2: User

    @property
    def id(self) -> uuid.UUID:
        return self.shop.id


def _cast(names: tuple[str, str, str, str, str, str]) -> tuple[ShopCast, list[object]]:
    owner, advisor, technician, parts, inspector, inspector_2 = (
        make_user(full_name=name) for name in names
    )
    shop = make_shop()
    cast = ShopCast(shop, owner, advisor, technician, parts, inspector, inspector_2)
    memberships = [
        make_membership(shop, owner, MembershipRole.OWNER),
        make_membership(shop, advisor, MembershipRole.SERVICE_ADVISOR, created_by=owner),
        make_membership(shop, technician, MembershipRole.TECHNICIAN, created_by=owner),
        make_membership(shop, parts, MembershipRole.PARTS_PERSON, created_by=owner),
        make_membership(shop, inspector, MembershipRole.QC_INSPECTOR, created_by=owner),
        make_membership(shop, inspector_2, MembershipRole.QC_INSPECTOR, created_by=owner),
    ]
    users: list[object] = [owner, advisor, technician, parts, inspector, inspector_2]
    return cast, [*users, shop, *memberships]


@dataclass
class QcWorld:
    """Lahore Auto Care's QC cast in shop A (Sara and Hina inspect, Imran repairs) and a second
    shop B with its own team, for tenant isolation."""

    db: Database
    clock: SimulatedClock
    a: ShopCast
    b: ShopCast
    customer: User
    vehicle: Vehicle

    @classmethod
    async def build(cls, db: Database, clock: SimulatedClock) -> "QcWorld":
        a, a_rows = _cast(("Fatima Raza", "Bilal", "Imran", "Usman", "Sara", "Hina"))
        b, b_rows = _cast(("Asif Memon", "Kashif", "Naveed", "Rehan", "Saima", "Tariq"))
        customer = make_user(full_name="Ayesha Khan")
        vehicle = make_vehicle(customer)
        await add_rows(db.sessionmaker, *a_rows, *b_rows, customer, vehicle)
        return cls(db, clock, a, b, customer, vehicle)

    async def booking(self, cast: ShopCast) -> Booking:
        """A booking of `cast`'s shop in `IN_REPAIR`, its technician and parts person set."""
        booking = make_booking(
            cast.shop,
            self.customer,
            self.vehicle,
            status=BookingStatus.IN_REPAIR,
            technician_user_id=cast.technician.id,
            parts_person_user_id=cast.parts.id,
        )
        await add_rows(self.db.sessionmaker, booking)
        return booking

    async def reload(self, booking: Booking) -> Booking:
        async with self.db.sessionmaker() as session:
            row = await session.get(Booking, booking.id)
            assert row is not None
            return row

    async def rounds(self, booking: Booking) -> list[QcInspection]:
        async with self.db.sessionmaker() as session:
            statement = (
                select(QcInspection)
                .where(QcInspection.booking_id == booking.id)
                .order_by(QcInspection.picked_at, QcInspection.id)
            )
            return list((await session.execute(statement)).scalars())

    async def issues(self, booking: Booking) -> list[QcIssue]:
        async with self.db.sessionmaker() as session:
            statement = (
                select(QcIssue)
                .where(QcIssue.booking_id == booking.id)
                .order_by(QcIssue.created_at, QcIssue.id)
            )
            return list((await session.execute(statement)).scalars())


class BookingsStandIn:
    """The bookings executor's part around the qc calls (spec 08 T17-T20), for qc's tests."""

    def __init__(self, world: QcWorld) -> None:
        self.world = world
        self.last_now = START

    async def _locked(self, session: AsyncSession, booking: Booking) -> Booking:
        statement = (
            select(Booking)
            .where(Booking.id == booking.id, Booking.shop_id == booking.shop_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await session.execute(statement)).scalar_one()

    def _now(self) -> datetime:
        self.last_now = self.world.clock.now()
        return self.last_now

    @staticmethod
    def _bump(row: Booking, status: BookingStatus, now: datetime) -> None:
        row.status = status
        row.version += 1
        row.updated_at = now

    async def send_to_qc(self, booking: Booking) -> list[uuid.UUID]:
        """T17 by the booking's technician."""
        async with self.world.db.sessionmaker() as session:
            uow = uow_for(session)
            row = await self._locked(session, booking)
            assert row.status == BookingStatus.IN_REPAIR
            assert row.technician_user_id is not None
            now = self._now()
            resolved = await qc.resolve_open_issues(
                uow,
                shop_id=row.shop_id,
                booking_id=row.id,
                resolved_by_user_id=row.technician_user_id,
                now=now,
            )
            row.qc_inspector_user_id = None
            self._bump(row, BookingStatus.QC_PENDING, now)
            await uow.commit()
        return resolved

    async def pick(self, booking: Booking, inspector: User) -> uuid.UUID:
        """T18 by any QC inspector of the shop."""
        async with self.world.db.sessionmaker() as session:
            uow = uow_for(session)
            row = await self._locked(session, booking)
            assert row.status == BookingStatus.QC_PENDING
            now = self._now()
            inspection_id = await qc.open_inspection(
                uow,
                shop_id=row.shop_id,
                booking_id=row.id,
                inspector_user_id=inspector.id,
                now=now,
                booking_technician_user_id=row.technician_user_id,
            )
            row.qc_inspector_user_id = inspector.id
            self._bump(row, BookingStatus.QC_IN_PROGRESS, now)
            await uow.commit()
        return inspection_id

    async def pass_(
        self,
        booking: Booking,
        inspector: User,
        items: Sequence[QcChecklistItemWrite],
        notes: str | None = None,
    ) -> uuid.UUID:
        """T19 by the picker; the picker is kept (D47)."""
        async with self.world.db.sessionmaker() as session:
            uow = uow_for(session)
            row = await self._locked(session, booking)
            assert row.status == BookingStatus.QC_IN_PROGRESS
            now = self._now()
            inspection_id = await qc.record_pass(
                uow,
                shop_id=row.shop_id,
                booking_id=row.id,
                inspector_user_id=inspector.id,
                checklist=items,
                notes=notes,
                now=now,
            )
            self._bump(row, BookingStatus.READY_FOR_PICKUP, now)
            await uow.commit()
        return inspection_id

    async def fail(
        self,
        booking: Booking,
        inspector: User,
        title: str = "Oil leak at filter",
        description: str = "Minor oil leak at the filter seal after the road test.",
        items: Sequence[QcChecklistItemWrite] | None = None,
        notes: str | None = None,
    ) -> FailRecorded:
        """T20 by the picker; back to the same technician, picker cleared (D47)."""
        async with self.world.db.sessionmaker() as session:
            uow = uow_for(session)
            row = await self._locked(session, booking)
            assert row.status == BookingStatus.QC_IN_PROGRESS
            now = self._now()
            recorded = await qc.record_fail(
                uow,
                shop_id=row.shop_id,
                booking_id=row.id,
                inspector_user_id=inspector.id,
                issue_title=title,
                issue_description=description,
                checklist=items,
                notes=notes,
                now=now,
            )
            row.qc_inspector_user_id = None
            self._bump(row, BookingStatus.IN_REPAIR, now)
            await uow.commit()
        return recorded

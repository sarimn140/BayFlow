"""Test support for the notifications module's DB tests.

`World` builds three shops directly as ORM rows (`tests.rows`), like the qc tests do:
- shop A "Lahore Auto Care": Fatima (Owner), two SAs (Bilal, Kashif), two technicians (Imran,
  Hamza), two parts persons (Usman, Rehan), two QC inspectors (Sara, Hina);
- shop B "Clifton Car Clinic": its own full team (tenant isolation);
- shop C "Raza Auto Works": Fatima again as its only member (the D26 Owner fallback).
Customers: Ayesha (a reserved `.test` address) and Ahmed (`ahmed@mail.com`, e-mailable).

Rows are driven by publishing `BookingActionApplied` on a real `UnitOfWork` inside a real
transaction (`publish`), exactly as the bookings executor does at spec 08 step 13; the bookings
executor itself is not needed.
"""

import asyncio
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from starlette.datastructures import State

from app.core.config import Settings
from app.core.database import Database
from app.modules.bookings.events import BookingActionApplied, BookingPartsChanged
from app.modules.bookings.models import Booking, Vehicle
from app.modules.identity.models import User
from app.modules.notifications import handlers
from app.modules.notifications.models import Notification
from app.modules.shops.models import Shop, ShopMembership
from app.shared.enums import ActorRole, BookingAction, BookingStatus, MembershipRole
from app.shared.event_bus import Event, EventBus
from app.shared.uow import UnitOfWork
from tests.conftest import make_settings
from tests.rows import add_rows, make_booking, make_membership, make_shop, make_user, make_vehicle

START = datetime(2026, 10, 14, 4, 0, tzinfo=UTC)  # Wed 14 Oct 2026 09:00 PKT (spec 12 §4.4)


@dataclass
class ShopCast:
    shop: Shop
    owner: User
    advisor: User
    advisor_2: User
    technician: User
    technician_2: User
    parts: User
    parts_2: User
    inspector: User
    inspector_2: User

    @property
    def id(self) -> uuid.UUID:
        return self.shop.id

    @property
    def advisors(self) -> list[User]:
        return sorted([self.advisor, self.advisor_2], key=lambda user: user.id)

    @property
    def inspectors(self) -> list[User]:
        return sorted([self.inspector, self.inspector_2], key=lambda user: user.id)


def _cast(shop: Shop, owner: User, names: Sequence[str]) -> tuple[ShopCast, list[object]]:
    staff = [make_user(full_name=name) for name in names]
    roles = (
        MembershipRole.SERVICE_ADVISOR,
        MembershipRole.SERVICE_ADVISOR,
        MembershipRole.TECHNICIAN,
        MembershipRole.TECHNICIAN,
        MembershipRole.PARTS_PERSON,
        MembershipRole.PARTS_PERSON,
        MembershipRole.QC_INSPECTOR,
        MembershipRole.QC_INSPECTOR,
    )
    memberships = [
        make_membership(shop, user, role, created_by=owner)
        for user, role in zip(staff, roles, strict=True)
    ]
    cast = ShopCast(shop, owner, *staff)
    return cast, [*staff, *memberships]


@dataclass
class World:
    db: Database
    a: ShopCast
    b: ShopCast
    c: Shop  # Raza Auto Works: only Fatima (Owner)
    ayesha: User
    ahmed: User
    vehicles: dict[uuid.UUID, Vehicle] = field(default_factory=dict)

    @classmethod
    async def build(cls, db: Database) -> "World":
        fatima = make_user(full_name="Fatima Raza", email="fatima.owner@bayflow.test")
        asif = make_user(full_name="Asif Memon")
        shop_a = make_shop(name="Lahore Auto Care")
        shop_b = make_shop(name="Clifton Car Clinic", city="Karachi")
        shop_c = make_shop(name="Raza Auto Works")
        a, a_rows = _cast(
            shop_a,
            fatima,
            ("Bilal", "Kashif", "Imran", "Hamza", "Usman", "Rehan", "Sara", "Hina"),
        )
        b, b_rows = _cast(
            shop_b,
            asif,
            ("Zubair", "Nabeel", "Naveed", "Waqas", "Faisal", "Junaid", "Saima", "Tariq"),
        )
        ayesha = make_user(full_name="Ayesha Khan", email="ayesha.customer@bayflow.test")
        ahmed = make_user(full_name="Ahmed", email="ahmed@mail.com")
        vehicles = {ayesha.id: make_vehicle(ayesha), ahmed.id: make_vehicle(ahmed)}
        await add_rows(
            db.sessionmaker,
            fatima,
            asif,
            ayesha,
            ahmed,
            *vehicles.values(),
            shop_a,
            shop_b,
            shop_c,
            make_membership(shop_a, fatima, MembershipRole.OWNER),
            make_membership(shop_b, asif, MembershipRole.OWNER),
            make_membership(shop_c, fatima, MembershipRole.OWNER),
            *a_rows,
            *b_rows,
        )
        return cls(db, a, b, shop_c, ayesha, ahmed, vehicles)

    async def vehicle_for(self, customer: User) -> Vehicle:
        vehicle = self.vehicles.get(customer.id)
        if vehicle is None:
            vehicle = make_vehicle(customer)
            await add_rows(self.db.sessionmaker, vehicle)
            self.vehicles[customer.id] = vehicle
        return vehicle

    async def booking(
        self,
        shop: Shop | ShopCast,
        *,
        customer: User | None = None,
        status: BookingStatus = BookingStatus.IN_REPAIR,
        technician: User | None = None,
        parts: User | None = None,
        picker: User | None = None,
    ) -> Booking:
        """A booking of `shop` in `status` (its CHECKs decide which assignees are needed)."""
        target = shop.shop if isinstance(shop, ShopCast) else shop
        customer = customer or self.ayesha
        booking = make_booking(
            target,
            customer,
            await self.vehicle_for(customer),
            status=status,
            technician_user_id=technician.id if technician else None,
            parts_person_user_id=parts.id if parts else None,
            qc_inspector_user_id=picker.id if picker else None,
        )
        await add_rows(self.db.sessionmaker, booking)
        return booking

    async def job(self, cast: ShopCast, **overrides: Any) -> Booking:
        """A shop booking `IN_REPAIR` with its technician and parts person set."""
        values: dict[str, Any] = {"technician": cast.technician, "parts": cast.parts}
        values.update(overrides)
        return await self.booking(cast, **values)

    async def set_membership_active(self, shop: Shop, user: User, *, active: bool) -> None:
        async with self.db.sessionmaker() as session:
            await session.execute(
                update(ShopMembership)
                .where(ShopMembership.shop_id == shop.id, ShopMembership.user_id == user.id)
                .values(is_active=active)
            )
            await session.commit()

    async def set_membership_role(self, shop: Shop, user: User, role: MembershipRole) -> None:
        async with self.db.sessionmaker() as session:
            await session.execute(
                update(ShopMembership)
                .where(ShopMembership.shop_id == shop.id, ShopMembership.user_id == user.id)
                .values(role=role)
            )
            await session.commit()

    async def set_user_active(self, user: User, *, active: bool) -> None:
        async with self.db.sessionmaker() as session:
            await session.execute(update(User).where(User.id == user.id).values(is_active=active))
            await session.commit()

    async def set_booking(self, booking: Booking, **values: Any) -> None:
        async with self.db.sessionmaker() as session:
            await session.execute(update(Booking).where(Booking.id == booking.id).values(**values))
            await session.commit()

    async def notifications(self, booking: Booking | None = None) -> list[Notification]:
        """Rows (about `booking`, or all), oldest first, then by recipient id."""
        async with self.db.sessionmaker() as session:
            statement = select(Notification).order_by(
                Notification.created_at, Notification.recipient_user_id
            )
            if booking is not None:
                statement = statement.where(Notification.booking_id == booking.id)
            return list((await session.execute(statement)).scalars())


_instants = iter(START + timedelta(minutes=n) for n in range(1, 1_000_000))


def next_instant() -> datetime:
    """A fresh action instant for every event (D63: rows take the event's `occurred_at`)."""
    return next(_instants)


def applied(  # noqa: PLR0913 - mirrors the event's fields
    booking: Booking,
    action: BookingAction,
    *,
    actor: User | None,
    actor_role: ActorRole,
    note: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    occurred_at: datetime | None = None,
    **assignees: uuid.UUID | None,
) -> BookingActionApplied:
    """A `BookingActionApplied` for `booking`, assignees after the action defaulting to the row's
    (override with `technician_user_id=…`, `parts_person_user_id=…`, `qc_inspector_user_id=…`)."""
    values: dict[str, uuid.UUID | None] = {
        "technician_user_id": booking.technician_user_id,
        "parts_person_user_id": booking.parts_person_user_id,
        "qc_inspector_user_id": booking.qc_inspector_user_id,
    }
    values.update(assignees)
    return BookingActionApplied(
        occurred_at=occurred_at or next_instant(),
        shop_id=booking.shop_id,
        booking_id=booking.id,
        reference=booking.reference,
        action=action,
        from_status=None if action == BookingAction.CREATE else booking.status,
        to_status=booking.status,
        version=booking.version + 1,
        actor_user_id=actor.id if actor else None,
        actor_role=actor_role,
        customer_user_id=booking.customer_user_id,
        technician_user_id=values["technician_user_id"],
        parts_person_user_id=values["parts_person_user_id"],
        qc_inspector_user_id=values["qc_inspector_user_id"],
        note=note,
        metadata=dict(metadata or {}),
    )


def parts_changed(booking: Booking) -> BookingPartsChanged:
    return BookingPartsChanged(
        occurred_at=next_instant(),
        shop_id=booking.shop_id,
        booking_id=booking.id,
        status=booking.status,
        version=booking.version,
    )


def notifications_bus() -> EventBus:
    """A bus with this module's subscriptions only (as `wire_modules()` registers them)."""
    bus = EventBus()
    handlers.register(bus)
    return bus


async def publish(
    db: Database,
    *events: Event,
    state: State | None = None,
    bus: EventBus | None = None,
) -> None:
    """Publish the events in one transaction and commit (one booking action)."""
    async with db.sessionmaker() as session:
        uow = UnitOfWork(session, bus or notifications_bus(), app_state=state)
        for event in events:
            await uow.publish(event)
        await uow.commit()


def app_state(db: Database, settings: Settings | None = None) -> State:
    """What `create_app()` + the lifespan put on `app.state` for the handlers (D90)."""
    state = State()
    state.db = db
    state.settings = settings or make_settings()
    return state


def summary(rows: Sequence[Notification]) -> set[tuple[uuid.UUID, ActorRole, str]]:
    return {(row.recipient_user_id, row.recipient_role, row.type) for row in rows}


class FakeSocket:
    """Just enough of a Starlette `WebSocket` for the hub: records frames, can fail or hang."""

    def __init__(self, *, fail: bool = False, hang: bool = False) -> None:
        self.fail = fail
        self.hang = hang
        self.frames: list[str] = []
        self.closed_with: int | None = None

    async def send_text(self, data: str) -> None:
        if self.fail:
            msg = "connection reset"
            raise OSError(msg)
        if self.hang:
            await asyncio.sleep(3600)
        self.frames.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed_with = code

    @property
    def messages(self) -> list[dict[str, Any]]:
        return [json.loads(frame) for frame in self.frames]

    def of_type(self, kind: str) -> list[dict[str, Any]]:
        return [message for message in self.messages if message["type"] == kind]

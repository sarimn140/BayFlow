"""Helpers for the inventory module tests (DB and API).

- `bearer()` / `url()`: call the API as a user (spec 12 §4.2 `as_user`).
- `assert_problem()`: RFC 9457 body with the expected `code` (spec 12 §4.5).
- `assert_ledger_invariants()`: DI-1...DI-3 and the PO status rule (spec 02 §6), from the rows.
- `FakeBookings`: the bookings side of a PO receipt (`modules/bookings.md` §7.7) and the D86
  `BookingRefReader`, written with plain SQL on `bookings`, because the bookings module is built
  later. It doubles as the executable contract bookings must honour.
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.core.security import issue_token
from app.modules.bookings.models import Booking
from app.modules.identity.models import User
from app.modules.inventory import service as inventory_service
from app.modules.inventory.domain.stock import (
    LedgerEntry,
    OrderPartsResult,
    PartQty,
    ReceiptReservation,
    booking_ledger,
    ledger_balances,
    purchase_order_status,
)
from app.modules.inventory.events import PurchaseOrderReceived, PurchaseOrderReceiving
from app.modules.inventory.models import (
    BookingPart,
    Part,
    PurchaseOrder,
    PurchaseOrderItem,
    StockMovement,
)
from app.modules.shops.models import Shop
from app.shared.auth import CurrentUser, ShopContext
from app.shared.clock import utcnow
from app.shared.enums import BookingStatus, MembershipRole, PurchaseOrderStatus
from app.shared.event_bus import EventBus
from app.shared.uow import UnitOfWork
from tests.rows import add_rows, make_booking, make_vehicle

PROBLEM_JSON = "application/problem+json"


@dataclass
class Team:
    """One shop with one member per role (two Parts Persons) and a deactivated Parts Person."""

    shop: Shop
    owner: User
    advisor: User
    technician: User
    parts: User
    parts2: User
    qc: User
    former_parts: User  # membership deactivated (D9 → 404)

    @property
    def id(self) -> UUID:
        return self.shop.id


@dataclass
class World:
    a: Team
    b: Team
    customer: User  # a global customer account without any membership
    outsider: User  # another user, no membership either


def qty(part: dict[str, Any], quantity: int) -> PartQty:
    """A `PartQty` for a part returned by the API."""
    return PartQty(UUID(part["id"]), quantity)


def bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(user.id, 'session', utcnow())}"}


def shop_context(team: Team, user: User, role: MembershipRole) -> ShopContext:
    """The `ShopContext` a route would build, for calling HTTP use cases directly (the seed)."""
    return ShopContext(
        shop_id=team.id,
        user=CurrentUser(id=user.id, email=user.email, full_name=user.full_name),
        membership_id=uuid4(),
        role=role,
    )


def url(shop_id: UUID, path: str = "") -> str:
    return f"/api/v1/shops/{shop_id}{path}"


def assert_problem(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body: dict[str, Any] = response.json()
    assert body["status"] == status
    assert body["code"] == code
    assert {"type", "title", "detail", "instance"} <= body.keys()
    assert "Traceback" not in response.text
    return body


def field_codes(response: httpx.Response) -> list[tuple[str, str]]:
    body = assert_problem(response, 422, "VALIDATION_ERROR")
    return [(error["field"], error["code"]) for error in body["errors"]]


async def new_part(
    api: httpx.AsyncClient, team: Team, sku: str, *, stock: int = 0, **fields: Any
) -> dict[str, Any]:
    """Create a part as the Parts Person, then enter its opening stock with an `ADJUST` (D44)."""
    payload = {"sku": sku, "name": f"Part {sku}", "unit_cost": "900", **fields}
    response = await api.post(url(team.id, "/parts"), json=payload, headers=bearer(team.parts))
    assert response.status_code == 201, response.text
    part: dict[str, Any] = response.json()
    if stock:
        adjusted = await api.post(
            url(team.id, f"/parts/{part['id']}/adjustments"),
            json={"quantity_delta": stock, "reason": "Opening stock"},
            headers=bearer(team.parts),
        )
        assert adjusted.status_code == 201, adjusted.text
        part = adjusted.json()["part"]
    return part


# --- Invariants (spec 02 §6; spec 12 §4.5) -------------------------------------------------------


async def assert_ledger_invariants(db: Database) -> None:
    """DI-1...DI-3 and DI-6 over every row of the test database."""
    async with db.sessionmaker() as session:
        parts = (await session.execute(select(Part))).scalars().all()
        movements = (await session.execute(select(StockMovement))).scalars().all()
        rows = (await session.execute(select(BookingPart))).scalars().all()
        orders = (await session.execute(select(PurchaseOrder))).scalars().all()
        items = (await session.execute(select(PurchaseOrderItem))).scalars().all()
    entries = [
        LedgerEntry(
            part_id=movement.part_id,
            movement_type=movement.movement_type,
            quantity=movement.quantity,
            on_hand_delta=movement.on_hand_delta,
            reserved_delta=movement.reserved_delta,
            booking_id=movement.booking_id,
        )
        for movement in movements
    ]
    balances = ledger_balances(entries)
    for part in parts:
        assert balances.get(part.id, (0, 0)) == (part.on_hand, part.reserved), part.sku  # DI-1
        assert 0 <= part.reserved <= part.on_hand, part.sku
        held = sum(row.reserved_qty for row in rows if row.part_id == part.id)
        assert part.reserved == held, part.sku  # DI-2
    per_booking = booking_ledger(entries)
    row_keys = {(row.booking_id, row.part_id) for row in rows}
    for row in rows:  # DI-3
        assert per_booking.get((row.booking_id, row.part_id), (0, 0)) == (
            row.reserved_qty,
            row.consumed_qty,
        )
    assert all(key in row_keys for key, value in per_booking.items() if value != (0, 0))
    for order in orders:  # DI-6
        quantities = [
            (i.ordered_qty, i.received_qty) for i in items if i.purchase_order_id == order.id
        ]
        assert order.status == purchase_order_status(quantities), order.po_number
        assert (order.status == PurchaseOrderStatus.RECEIVED) == (order.received_at is not None)


async def part_balance(db: Database, part_id: UUID | str) -> tuple[int, int]:
    async with db.sessionmaker() as session:
        part = await session.get(Part, UUID(str(part_id)))
        assert part is not None
        return part.on_hand, part.reserved


async def movements_of(db: Database, part_id: UUID | str) -> list[StockMovement]:
    """A part's ledger in insert order (`created_at, seq`)."""
    async with db.sessionmaker() as session:
        statement = (
            select(StockMovement)
            .where(StockMovement.part_id == UUID(str(part_id)))
            .order_by(StockMovement.created_at, StockMovement.seq)
        )
        return list((await session.execute(statement)).scalars().all())


async def booking_rows(db: Database, booking_id: UUID) -> dict[UUID, BookingPart]:
    async with db.sessionmaker() as session:
        statement = select(BookingPart).where(BookingPart.booking_id == booking_id)
        return {row.part_id: row for row in (await session.execute(statement)).scalars().all()}


async def booking_status(db: Database, booking_id: UUID) -> tuple[BookingStatus, int]:
    async with db.sessionmaker() as session:
        booking = await session.get(Booking, booking_id)
        assert booking is not None
        return booking.status, booking.version


# --- Running nested service functions in their own transaction ------------------------------------


@asynccontextmanager
async def transaction(db: Database, bus: EventBus | None = None) -> AsyncIterator[UnitOfWork]:
    """A unit of work that commits when the block succeeds (as a bookings action would)."""
    async with db.sessionmaker() as session:
        uow = UnitOfWork(session, bus or EventBus())
        yield uow
        await uow.commit()


async def lock_booking(session: AsyncSession, booking_id: UUID) -> None:
    """Lock 1 of every booking action (D30), as the bookings executor takes it."""
    await session.execute(
        text("SELECT id FROM bookings WHERE id = :id FOR UPDATE"), {"id": booking_id}
    )


# --- The bookings side of a receipt (modules/bookings.md §7.7) and the D86 reader ---------------


@dataclass(frozen=True)
class BookingRefRow:
    id: UUID
    reference: str
    status: BookingStatus
    version: int


async def read_booking_refs(
    session: AsyncSession, *, shop_id: UUID, booking_ids: Any
) -> dict[UUID, BookingRefRow]:
    """A `BookingRefReader` (D86) with plain SQL, as `bookings.service.get_booking_refs` does."""
    result = await session.execute(
        text(
            "SELECT id, reference, status, version FROM bookings"
            " WHERE shop_id = :shop_id AND id = ANY(:ids)"
        ),
        {"shop_id": shop_id, "ids": list(booking_ids)},
    )
    return {
        row.id: BookingRefRow(row.id, row.reference, BookingStatus(row.status), row.version)
        for row in result
    }


@contextmanager
def without_booking_reader() -> Iterator[None]:
    """No D86 `BookingRefReader` registered inside the block: a mis-wired app."""
    current = inventory_service.booking_ref_reader()
    inventory_service.register_booking_ref_reader(None)
    try:
        yield
    finally:
        inventory_service.register_booking_ref_reader(current)


@dataclass
class FakeBookings:
    """The receipt handlers of `modules/bookings.md` §7.7 (`on_purchase_order_receiving`,
    `on_purchase_order_received`)."""

    locked: list[UUID] = field(default_factory=list)
    reservations: list[ReceiptReservation] = field(default_factory=list)
    receiving_events: list[PurchaseOrderReceiving] = field(default_factory=list)
    received_events: list[PurchaseOrderReceived] = field(default_factory=list)

    def install(self, bus: EventBus) -> "FakeBookings":
        bus.subscribe(PurchaseOrderReceiving, self.on_receiving)
        bus.subscribe(PurchaseOrderReceived, self.on_received)
        return self

    async def on_receiving(self, event: PurchaseOrderReceiving, uow: UnitOfWork) -> None:
        self.receiving_events.append(event)
        await uow.session.execute(
            text("SELECT id FROM bookings WHERE id = :id AND shop_id = :shop_id FOR UPDATE"),
            {"id": event.booking_id, "shop_id": event.shop_id},
        )
        self.locked.append(event.booking_id)

    async def on_received(self, event: PurchaseOrderReceived, uow: UnitOfWork) -> None:
        self.received_events.append(event)
        if event.booking_id is None:
            return
        status = (
            await uow.session.execute(
                text("SELECT status FROM bookings WHERE id = :id"), {"id": event.booking_id}
            )
        ).scalar_one()
        if status != BookingStatus.PARTS_ORDERED:
            return
        result = await inventory_service.reserve_received_for_booking(
            uow,
            shop_id=event.shop_id,
            booking_id=event.booking_id,
            purchase_order_id=event.purchase_order_id,
            received=event.received,
            actor_user_id=event.actor_user_id,
            now=event.occurred_at,
        )
        self.reservations.append(result)
        if result.all_reserved:  # RECEIVE_PARTS (T15): status and version, as bookings applies it
            await uow.session.execute(
                text(
                    "UPDATE bookings SET status = 'PARTS_READY', version = version + 1,"
                    " updated_at = :now WHERE id = :id"
                ),
                {"id": event.booking_id, "now": event.occurred_at},
            )


# --- Booking rows (the bookings module is built later) -----------------------------------------


_BEFORE_PARTS = {BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.CANCELLED}


async def add_booking(  # noqa: PLR0913 - one keyword per booking column a test sets
    db: Database,
    *,
    shop: Any,
    customer: User,
    technician: User,
    parts_person: User,
    status: BookingStatus,
    cancelled_by: User | None = None,
) -> Booking:
    """A booking row in `status` with the assignees the status requires (spec 02 §3.8 CHECKs)."""
    vehicle = make_vehicle(customer)
    values: dict[str, Any] = {"status": status}
    if status not in _BEFORE_PARTS:
        values.update(technician_user_id=technician.id, parts_person_user_id=parts_person.id)
    if status == BookingStatus.CANCELLED:
        values.update(
            cancelled_at=utcnow() - timedelta(minutes=1),
            cancelled_by_user_id=(cancelled_by or customer).id,
        )
    booking = make_booking(shop, customer, vehicle, **values)
    await add_rows(db.sessionmaker, vehicle, booking)
    return booking


async def set_booking_status(
    db: Database, booking_id: UUID, status: BookingStatus, *, by: User, at: datetime | None = None
) -> None:
    """Move a booking row (e.g. to `CANCELLED`) as bookings would, without inventory effects."""
    async with db.sessionmaker() as session:
        booking = await session.get(Booking, booking_id)
        assert booking is not None
        booking.status = status
        booking.version += 1
        if status == BookingStatus.CANCELLED:
            booking.cancelled_at = at or utcnow()
            booking.cancelled_by_user_id = by.id
        await session.commit()


async def reserve_for_booking(
    db: Database, team: Team, customer: User, parts: dict[str, int]
) -> Booking:
    """A `PARTS_PENDING` booking whose parts (`{part_id: qty}`) are created (T12) and reserved
    (T14) through the inventory services, under the booking lock, as bookings will call them."""
    booking = await add_booking(
        db,
        shop=team.shop,
        customer=customer,
        technician=team.technician,
        parts_person=team.parts,
        status=BookingStatus.PARTS_PENDING,
    )
    requirements = [PartQty(UUID(part_id), qty) for part_id, qty in parts.items()]
    async with transaction(db) as uow:
        await lock_booking(uow.session, booking.id)
        now = utcnow()
        await inventory_service.create_booking_parts(
            uow, shop_id=team.id, booking_id=booking.id, requirements=requirements, now=now
        )
        await inventory_service.reserve_outstanding(
            uow, shop_id=team.id, booking_id=booking.id, actor_user_id=team.parts.id, now=now
        )
    return booking


async def move_booking(session: AsyncSession, booking_id: UUID, status: BookingStatus) -> None:
    """The status change bookings applies after an inventory side effect (version + 1)."""
    await session.execute(
        text("UPDATE bookings SET status = :status, version = version + 1 WHERE id = :id"),
        {"status": status.value, "id": booking_id},
    )


async def order_parts(
    db: Database,
    team: Team,
    customer: User,
    requirements: dict[str, int],
    items: list[PartQty] | None = None,
) -> tuple[Booking, OrderPartsResult]:
    """T12 + T13 as bookings performs them: a `PARTS_PENDING` booking gets its parts, then
    `order-parts` reserves what is available and orders the shortages (→ `PARTS_ORDERED`)."""
    booking = await add_booking(
        db,
        shop=team.shop,
        customer=customer,
        technician=team.technician,
        parts_person=team.parts,
        status=BookingStatus.PARTS_PENDING,
    )
    async with transaction(db) as uow:
        await lock_booking(uow.session, booking.id)
        now = utcnow()
        await inventory_service.create_booking_parts(
            uow,
            shop_id=team.id,
            booking_id=booking.id,
            requirements=[PartQty(UUID(part_id), qty) for part_id, qty in requirements.items()],
            now=now,
        )
        result = await inventory_service.order_missing_parts(
            uow,
            shop_id=team.id,
            booking_id=booking.id,
            actor_user_id=team.parts.id,
            items=items,
            supplier_name="City Auto Parts",
            now=now,
        )
        await move_booking(uow.session, booking.id, BookingStatus.PARTS_ORDERED)
    return booking, result


async def cancel_booking(session: AsyncSession, booking_id: UUID, by: User) -> None:
    """`CANCEL`'s booking columns in one statement (`ck_bookings_cancellation_fields`)."""
    await session.execute(
        text(
            "UPDATE bookings SET status = 'CANCELLED', version = version + 1,"
            " cancelled_at = :now, cancelled_by_user_id = :by WHERE id = :id"
        ),
        {"now": utcnow(), "by": by.id, "id": booking_id},
    )


# --- Booking actions' inventory side effects, one transaction each (under the booking lock) -----


async def parts_pending_booking(db: Database, world: World) -> Any:
    return await add_booking(
        db,
        shop=world.a.shop,
        customer=world.customer,
        technician=world.a.technician,
        parts_person=world.a.parts,
        status=BookingStatus.PARTS_PENDING,
    )


async def assign_parts(
    db: Database, team: Team, booking_id: UUID, requirements: list[PartQty]
) -> None:
    """T12 `assign-parts-person`."""
    async with transaction(db) as uow:
        await lock_booking(uow.session, booking_id)
        await inventory_service.create_booking_parts(
            uow, shop_id=team.id, booking_id=booking_id, requirements=requirements, now=utcnow()
        )


async def order_missing(
    db: Database,
    team: Team,
    booking_id: UUID,
    items: list[PartQty] | None = None,
    supplier_name: str | None = None,
) -> OrderPartsResult:
    """T13 `order-parts`."""
    async with transaction(db) as uow:
        await lock_booking(uow.session, booking_id)
        return await inventory_service.order_missing_parts(
            uow,
            shop_id=team.id,
            booking_id=booking_id,
            actor_user_id=team.parts.id,
            items=items,
            supplier_name=supplier_name,
            now=utcnow(),
        )


async def mark_parts_ready(db: Database, team: Team, booking_id: UUID) -> tuple[PartQty, ...]:
    """T14 `mark-parts-ready`."""
    async with transaction(db) as uow:
        await lock_booking(uow.session, booking_id)
        return await inventory_service.reserve_outstanding(
            uow, shop_id=team.id, booking_id=booking_id, actor_user_id=team.parts.id, now=utcnow()
        )


async def allocate_parts(db: Database, team: Team, booking_id: UUID) -> tuple[PartQty, ...]:
    """T16 `allocate-parts`."""
    async with transaction(db) as uow:
        await lock_booking(uow.session, booking_id)
        return await inventory_service.consume_reservations(
            uow, shop_id=team.id, booking_id=booking_id, actor_user_id=team.parts.id, now=utcnow()
        )


async def cancel_reservations(
    db: Database, team: Team, booking_id: UUID, actor: User
) -> tuple[PartQty, ...]:
    """T22 `cancel` (the actor may be the customer)."""
    async with transaction(db) as uow:
        await lock_booking(uow.session, booking_id)
        return await inventory_service.release_reservations(
            uow, shop_id=team.id, booking_id=booking_id, actor_user_id=actor.id, now=utcnow()
        )

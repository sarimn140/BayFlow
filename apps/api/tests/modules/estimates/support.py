"""Builders and helpers for the estimates service tests (`db`).

The bookings service that normally calls these functions is built later, so the tests play its
part: they open a transaction (optionally locking the booking row first, as every bookings action
does, spec 02 §7.2), call the nested estimates function and commit. Shops, users, bookings and
parts are inserted directly with `tests.rows`; ready-made estimate versions come from
`insert_version`, request lines from `part_line` / `labour_line`, and `assert_estimate_invariants`
checks what spec 12 §4.5 asks of estimates after every step (EST-16, DI-5).
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.modules.bookings.models import Booking
from app.modules.estimates import service
from app.modules.estimates.domain.totals import estimate_totals, line_total
from app.modules.estimates.domain.versions import OPEN_STATUSES
from app.modules.estimates.models import Estimate, EstimateLine
from app.modules.estimates.schemas import EstimateEdit, EstimateLineWrite
from app.modules.inventory.models import Part
from app.shared.enums import BookingStatus, EstimateLineType, EstimateStatus, MembershipRole
from app.shared.event_bus import EventBus
from app.shared.uow import UnitOfWork
from tests.rows import (
    add_rows,
    make_booking,
    make_membership,
    make_part,
    make_shop,
    make_user,
    make_vehicle,
)

T0 = datetime(2026, 10, 16, 5, 0, tzinfo=UTC)  # Friday 10:00 PKT, the worked example's slot

PART = EstimateLineType.PART
LABOUR = EstimateLineType.LABOUR


def at(minutes: int) -> datetime:
    """An action instant `minutes` after T0 (each step of a scenario gets its own)."""
    return T0 + timedelta(minutes=minutes)


@dataclass(frozen=True)
class World:
    """Lahore Auto Care (shop A) with its team, Ahmed's bookings, the worked-example parts, and a
    second tenant (shop B) with its own booking and part."""

    shop_id: uuid.UUID
    other_shop_id: uuid.UUID
    owner_id: uuid.UUID
    sa_id: uuid.UUID
    tech_id: uuid.UUID
    customer_id: uuid.UUID
    booking_id: uuid.UUID
    second_booking_id: uuid.UUID
    foreign_booking_id: uuid.UUID
    coil_id: uuid.UUID
    filter_id: uuid.UUID
    oil_id: uuid.UUID
    retired_id: uuid.UUID
    foreign_part_id: uuid.UUID


async def build_world(db: Database) -> World:
    owner = make_user(full_name="Fatima Raza")
    sa = make_user(full_name="Bilal")
    tech = make_user(full_name="Imran")
    customer = make_user(full_name="Ahmed")
    other_owner = make_user(full_name="Asif Memon")
    shop = make_shop(name="Lahore Auto Care")
    other_shop = make_shop(name="Clifton Car Clinic")
    vehicle = make_vehicle(customer)
    booking = make_booking(shop, customer, vehicle)
    second_booking = make_booking(shop, customer, vehicle)
    foreign_booking = make_booking(other_shop, customer, vehicle)
    coil = make_part(shop, sku="COIL-1", name="Ignition coil", unit_cost=Decimal("6500"))
    oil_filter = make_part(
        shop, sku="FILTER-1", name="Oil filter", unit_cost=Decimal("900"), on_hand=10, reserved=1
    )
    oil = make_part(
        shop,
        sku="OIL-4L",
        name="Engine oil 4 L",
        unit_cost=Decimal("5200"),
        on_hand=8,
        reorder_level=8,
    )
    retired = make_part(
        shop, sku="OLD-1", name="Retired part", unit_cost=Decimal("100"), is_active=False
    )
    foreign_part = make_part(other_shop, sku="COIL-1", name="Their coil", unit_cost=Decimal("1"))
    await add_rows(
        db.sessionmaker,
        owner,
        sa,
        tech,
        customer,
        other_owner,
        shop,
        other_shop,
        make_membership(shop, owner, MembershipRole.OWNER),
        make_membership(shop, sa, MembershipRole.SERVICE_ADVISOR, created_by=owner),
        make_membership(shop, tech, MembershipRole.TECHNICIAN, created_by=owner),
        make_membership(other_shop, other_owner, MembershipRole.OWNER),
        vehicle,
        booking,
        second_booking,
        foreign_booking,
        coil,
        oil_filter,
        oil,
        retired,
        foreign_part,
    )
    return World(
        shop_id=shop.id,
        other_shop_id=other_shop.id,
        owner_id=owner.id,
        sa_id=sa.id,
        tech_id=tech.id,
        customer_id=customer.id,
        booking_id=booking.id,
        second_booking_id=second_booking.id,
        foreign_booking_id=foreign_booking.id,
        coil_id=coil.id,
        filter_id=oil_filter.id,
        oil_id=oil.id,
        retired_id=retired.id,
        foreign_part_id=foreign_part.id,
    )


def new_uow(session: AsyncSession) -> UnitOfWork:
    return UnitOfWork(session, EventBus())


async def lock_booking(session: AsyncSession, booking_id: uuid.UUID) -> None:
    """What every bookings action does first (spec 02 §7.2, §7.3: key-only `FOR UPDATE`)."""
    await session.execute(select(Booking.id).where(Booking.id == booking_id).with_for_update())


async def write[T](
    db: Database,
    action: Callable[..., Awaitable[T]],
    /,
    *,
    lock: uuid.UUID | None = None,
    **arguments: Any,
) -> T:
    """Run one nested estimates write the way bookings will: one transaction, optional booking
    lock first, commit at the end. An exception rolls everything back (the session closes)."""
    async with db.sessionmaker() as session:
        if lock is not None:
            await lock_booking(session, lock)
        uow = new_uow(session)
        result = await action(uow, **arguments)
        await uow.commit()
        return result


async def read[T](db: Database, action: Callable[..., Awaitable[T]], /, **arguments: Any) -> T:
    async with db.sessionmaker() as session:
        return await action(session, **arguments)


@dataclass(frozen=True)
class LineSpec:
    line_type: EstimateLineType
    description: str
    quantity: Decimal
    unit_price: Decimal
    part_id: uuid.UUID | None = None


def part_spec(part_id: uuid.UUID, name: str, unit_price: str, quantity: str = "1") -> LineSpec:
    return LineSpec(PART, name, Decimal(quantity), Decimal(unit_price), part_id)


def labour_spec(description: str, unit_price: str, quantity: str = "1") -> LineSpec:
    return LineSpec(LABOUR, description, Decimal(quantity), Decimal(unit_price))


def worked_example_v1(world: World) -> list[LineSpec]:
    """Imran's v1 (brief §6 step 5): 16,600."""
    return [
        part_spec(world.coil_id, "Ignition coil", "6500"),
        part_spec(world.filter_id, "Oil filter", "900"),
        part_spec(world.oil_id, "Engine oil 4 L", "5200"),
        labour_spec("Diagnosis and repair labour", "4000"),
    ]


async def insert_version(  # noqa: PLR0913 - a test builder with every audit field
    db: Database,
    world: World,
    *,
    version: int,
    status: EstimateStatus,
    lines: Sequence[LineSpec] = (),
    booking_id: uuid.UUID | None = None,
    shop_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
    customer_note: str | None = None,
) -> uuid.UUID:
    """Insert one estimate version with consistent totals and the audit fields its status needs
    (`ck_estimates_*`), bypassing the service (for the inventory-independent functions)."""
    priced = [
        EstimateLine(
            position=index + 1,
            line_type=spec.line_type,
            part_id=spec.part_id,
            description=spec.description,
            quantity=spec.quantity,
            unit_price=spec.unit_price,
            line_total=line_total(spec.quantity, spec.unit_price),
            created_at=at(version),
        )
        for index, spec in enumerate(lines)
    ]
    totals = estimate_totals(priced)
    sent = status in {EstimateStatus.SENT, EstimateStatus.APPROVED, EstimateStatus.REJECTED}
    decided = status in {EstimateStatus.APPROVED, EstimateStatus.REJECTED}
    estimate = Estimate(
        shop_id=shop_id or world.shop_id,
        booking_id=booking_id or world.booking_id,
        version=version,
        status=status,
        parts_total=totals.parts_total,
        labour_total=totals.labour_total,
        grand_total=totals.grand_total,
        created_by_user_id=created_by or world.tech_id,
        submitted_at=at(version) if status != EstimateStatus.DRAFT else None,
        sent_at=at(version) if sent else None,
        sent_by_user_id=world.sa_id if sent else None,
        decided_at=at(version) + timedelta(seconds=30) if decided else None,
        decided_by_user_id=world.customer_id if decided else None,
        customer_note=customer_note if decided else None,
        created_at=at(version),
        updated_at=at(version),
    )
    for line in priced:
        line.shop_id = estimate.shop_id
        line.estimate_id = estimate.id
    await add_rows(db.sessionmaker, estimate, *priced)
    return estimate.id


async def versions_of(db: Database, booking_id: uuid.UUID) -> list[Estimate]:
    async with db.sessionmaker() as session:
        statement = (
            select(Estimate).where(Estimate.booking_id == booking_id).order_by(Estimate.version)
        )
        return list((await session.scalars(statement)).all())


async def lines_of(db: Database, estimate_id: uuid.UUID) -> list[EstimateLine]:
    async with db.sessionmaker() as session:
        statement = (
            select(EstimateLine)
            .where(EstimateLine.estimate_id == estimate_id)
            .order_by(EstimateLine.position)
        )
        return list((await session.scalars(statement)).all())


def line_facts(lines: Sequence[EstimateLine]) -> list[tuple[Any, ...]]:
    """What a copy must preserve exactly (EST-15): everything but the row id and timestamps."""
    return [
        (
            line.position,
            line.line_type,
            line.part_id,
            line.description,
            line.quantity,
            line.unit_price,
            line.line_total,
        )
        for line in lines
    ]


async def set_part(db: Database, part_id: uuid.UUID, **values: Any) -> None:
    """Change a catalogue row directly (rename, deactivate, restock) between two service calls."""
    async with db.sessionmaker() as session:
        part = await session.get(Part, part_id)
        assert part is not None
        for name, value in values.items():
            setattr(part, name, value)
        await session.commit()


# --- Requests and edits ---------------------------------------------------------------------------


def part_line(
    part_id: uuid.UUID, quantity: str = "1", unit_price: str | None = None
) -> EstimateLineWrite:
    body: dict[str, Any] = {"line_type": "PART", "part_id": str(part_id), "quantity": quantity}
    if unit_price is not None:
        body["unit_price"] = unit_price
    return EstimateLineWrite.model_validate(body)


def labour_line(description: str, unit_price: str, quantity: str = "1") -> EstimateLineWrite:
    return EstimateLineWrite.model_validate(
        {
            "line_type": "LABOUR",
            "description": description,
            "quantity": quantity,
            "unit_price": unit_price,
        }
    )


def worked_example_lines(world: World, labour: str = "4000") -> list[EstimateLineWrite]:
    """Brief §6 step 5 (labour 4,000 -> 16,600) or step 6 (labour 3,500 -> 16,100); part prices
    come from the catalogue (D40)."""
    return [
        part_line(world.coil_id),
        part_line(world.filter_id),
        part_line(world.oil_id),
        labour_line("Diagnosis and repair labour", labour),
    ]


async def edit(  # noqa: PLR0913 - mirrors replace_lines' keyword arguments
    db: Database,
    world: World,
    *,
    status: BookingStatus,
    actor: uuid.UUID,
    lines: Sequence[EstimateLineWrite],
    now: datetime,
    booking_id: uuid.UUID | None = None,
    shop_id: uuid.UUID | None = None,
) -> EstimateEdit:
    """`PUT …/estimate` as bookings will run it: booking lock, `replace_lines`, commit."""
    booking = booking_id or world.booking_id
    return await write(
        db,
        service.replace_lines,
        lock=booking,
        shop_id=shop_id or world.shop_id,
        booking_id=booking,
        booking_status=status,
        actor_user_id=actor,
        lines=lines,
        now=now,
    )


# --- Invariants (spec 12 §4.5) --------------------------------------------------------------------


async def assert_estimate_invariants(db: Database, booking_id: uuid.UUID) -> None:
    """EST-16: at most one open version; versions 1..n without gaps; DI-5: cached totals are the
    sums of the lines per type; every line total is quantity x unit price rounded half-up; every
    amount is whole rupees; at most one `APPROVED` version."""
    versions = await versions_of(db, booking_id)
    assert [version.version for version in versions] == list(range(1, len(versions) + 1))
    assert sum(version.status in OPEN_STATUSES for version in versions) <= 1
    assert sum(version.status == EstimateStatus.APPROVED for version in versions) <= 1
    for version in versions:
        lines = await lines_of(db, version.id)
        assert [line.position for line in lines] == list(range(1, len(lines) + 1))
        for line in lines:
            assert line.line_total == line_total(line.quantity, line.unit_price)
            assert line.unit_price == line.unit_price.to_integral_value()
        totals = estimate_totals(lines)
        assert (version.parts_total, version.labour_total, version.grand_total) == (
            totals.parts_total,
            totals.labour_total,
            totals.grand_total,
        )


_APPROVED_ONWARDS = (
    BookingStatus.ESTIMATE_APPROVED,
    BookingStatus.PARTS_PENDING,
    BookingStatus.PARTS_ORDERED,
    BookingStatus.PARTS_READY,
    BookingStatus.IN_REPAIR,
    BookingStatus.QC_PENDING,
    BookingStatus.QC_IN_PROGRESS,
    BookingStatus.READY_FOR_PICKUP,
    BookingStatus.COMPLETED,
)

LATEST_VERSION_BY_BOOKING_STATUS: dict[BookingStatus, frozenset[EstimateStatus | None]] = {
    BookingStatus.PENDING: frozenset({None}),
    BookingStatus.CONFIRMED: frozenset({None}),
    BookingStatus.ASSIGNED: frozenset({None}),
    BookingStatus.INSPECTING: frozenset({EstimateStatus.DRAFT}),
    BookingStatus.ESTIMATE_REVIEW: frozenset({EstimateStatus.SUBMITTED, EstimateStatus.DRAFT}),
    BookingStatus.AWAITING_CUSTOMER: frozenset({EstimateStatus.SENT}),
    BookingStatus.ESTIMATE_REJECTED: frozenset({EstimateStatus.REJECTED}),
    **{status: frozenset({EstimateStatus.APPROVED}) for status in _APPROVED_ONWARDS},
    BookingStatus.CANCELLED: frozenset(
        {None, EstimateStatus.SUPERSEDED, EstimateStatus.APPROVED, EstimateStatus.REJECTED}
    ),
}
"""`modules/estimates.md` §7.1: the booking status <-> latest version table (EST-26)."""


async def assert_latest_matches(
    db: Database, booking_id: uuid.UUID, booking_status: BookingStatus
) -> None:
    """EST-26: after every step, the latest version fits the booking's status (§7.1)."""
    versions = await versions_of(db, booking_id)
    latest = versions[-1].status if versions else None
    assert latest in LATEST_VERSION_BY_BOOKING_STATUS[booking_status], (booking_status, latest)


async def wait_for_lock_waiters(db: Database, count: int, *, attempts: int = 200) -> None:
    """Spec 12 §3.5 lock gate: wait until `count` sessions of this database wait on a lock."""
    query = text(
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE datname = current_database() AND wait_event_type = 'Lock'"
    )
    for _ in range(attempts):
        async with db.engine.connect() as connection:
            waiting = (await connection.execute(query)).scalar_one()
        if waiting >= count:
            return
        await asyncio.sleep(0.05)
    msg = f"{count} lock waiter(s) never appeared"
    raise AssertionError(msg)

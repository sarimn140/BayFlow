"""Fixtures of the inventory module tests: two shops with full teams, an API client whose event bus
holds only what a test subscribes, the D86 booking-reference reader and a stepping clock."""

from collections.abc import Iterator
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI

from app.core.database import Database
from app.modules.inventory import service as inventory_service
from app.shared.clock import SimulatedClock, use_clock
from app.shared.enums import MembershipRole
from app.shared.event_bus import EventBus
from tests.modules.inventory.support import FakeBookings, Team, World, read_booking_refs
from tests.rows import add_rows, make_membership, make_shop, make_user


async def _team(db: Database) -> Team:
    shop = make_shop()
    owner, advisor, technician = make_user(), make_user(), make_user()
    parts, parts2, qc, former = make_user(), make_user(), make_user(), make_user()
    await add_rows(
        db.sessionmaker,
        owner,
        advisor,
        technician,
        parts,
        parts2,
        qc,
        former,
        shop,
        make_membership(shop, owner, MembershipRole.OWNER),
        make_membership(shop, advisor, MembershipRole.SERVICE_ADVISOR, created_by=owner),
        make_membership(shop, technician, MembershipRole.TECHNICIAN, created_by=owner),
        make_membership(shop, parts, MembershipRole.PARTS_PERSON, created_by=owner),
        make_membership(shop, parts2, MembershipRole.PARTS_PERSON, created_by=owner),
        make_membership(shop, qc, MembershipRole.QC_INSPECTOR, created_by=owner),
        make_membership(
            shop, former, MembershipRole.PARTS_PERSON, created_by=owner, is_active=False
        ),
    )
    return Team(shop, owner, advisor, technician, parts, parts2, qc, former)


@pytest.fixture
async def world(db: Database, clock: SimulatedClock) -> World:
    a, b = await _team(db), await _team(db)
    customer, outsider = make_user(full_name="Ahmed"), make_user()
    await add_rows(db.sessionmaker, customer, outsider)
    return World(a=a, b=b, customer=customer, outsider=outsider)


@pytest.fixture
def bus(db_app: FastAPI) -> EventBus:
    """The app's event bus, emptied: only what the test subscribes reacts to inventory events."""
    fresh = EventBus()
    db_app.state.event_bus = fresh
    return fresh


@pytest.fixture
def api(db_client: httpx.AsyncClient, bus: EventBus, booking_refs: None) -> httpx.AsyncClient:
    """The API client; its app's event bus holds only what the test subscribes (`bus`), and the
    D86 `BookingRefReader` is a fake reading the `bookings` rows (`booking_refs`)."""
    return db_client


@pytest.fixture
def bookings(bus: EventBus) -> FakeBookings:
    """The bookings receipt handlers of `modules/bookings.md` §7.7, subscribed to the app bus."""
    return FakeBookings().install(bus)


@pytest.fixture
def booking_refs(db_app: FastAPI) -> Iterator[None]:
    """Register a fake D86 `BookingRefReader` after `create_app()` wired the modules (which may
    register bookings' own reader, D89); the previous registration is restored afterwards."""
    previous = inventory_service.booking_ref_reader()
    inventory_service.register_booking_ref_reader(read_booking_refs)
    yield
    inventory_service.register_booking_ref_reader(previous)


@pytest.fixture
def stepping_clock(clock: SimulatedClock) -> Iterator[SimulatedClock]:
    """A clock that moves one second on every reading (spec 12 §4.4 "stepping"), installed over
    the frozen `clock`: two readings inside one action would differ, so "one action, one instant"
    (D63) becomes a check that can fail."""
    stepping = SimulatedClock(clock.now(), step=timedelta(seconds=1))
    with use_clock(stepping):
        yield stepping

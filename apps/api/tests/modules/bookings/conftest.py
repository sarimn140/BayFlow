"""Fixtures of the bookings tests.

The app under test is the real one (`create_app()` → `wire_modules()`): bookings' own read ports
and event handlers are registered, so shops and inventory talk to the real bookings code (no fake
`ShopActivityReader` here). `published` records what bookings publishes on the app's bus, the
contract with the notifications module; notification rows themselves are not asserted here.

After every test the shared invariants of spec 12 §4.5 must hold (`invariants`, autouse): every
scenario here goes through the real services, so the ledgers, the slot counters, the estimate
versions and the event chains must still add up whatever the test did.
"""

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI

from app.core.database import Database
from app.modules.bookings.events import BookingActionApplied, BookingPartsChanged
from app.shared.clock import SimulatedClock, use_clock
from app.shared.event_bus import Event
from app.shared.uow import UnitOfWork
from tests.assertions import assert_invariants
from tests.modules.bookings.support import Desk, World, build_world
from tests.modules.identity.builders import fast_password_hashing  # noqa: F401 - autouse fixture

WEDNESDAY_0900_PKT = datetime(2026, 10, 14, 4, 0, tzinfo=UTC)


@pytest.fixture
def stepping_clock() -> Iterator[SimulatedClock]:
    """Spec 12 §4.4's stepping clock: every read of "now" is one second later, so each action
    gets its own instant and a second read inside one action would show."""
    simulated = SimulatedClock(WEDNESDAY_0900_PKT, step=timedelta(seconds=1))
    with use_clock(simulated):
        yield simulated


@pytest.fixture
async def world(db: Database, clock: SimulatedClock) -> World:
    """Lahore Auto Care and a second tenant, built through the services (frozen clock)."""
    return await build_world(db)


@pytest.fixture
def desk(db_client: httpx.AsyncClient, world: World) -> Desk:
    return Desk(db_client, world)


@pytest.fixture
def published(db_app: FastAPI) -> list[Event]:
    """Every `BookingActionApplied` / `BookingPartsChanged` published while the test runs, in
    order (recorded inside the publishing transaction, after the notifications handler)."""
    seen: list[Event] = []

    async def record(event: Event, uow: UnitOfWork) -> None:
        seen.append(event)

    bus = db_app.state.event_bus
    bus.subscribe(BookingActionApplied, record)
    bus.subscribe(BookingPartsChanged, record)
    return seen


@dataclass
class InvariantCheck:
    """What the after-test invariant check does; a test that writes rows directly (BK-40's
    predicate proof, spec 12 §3.3) switches it off."""

    enabled: bool = True
    allow_inactive_recipients: bool = False


@pytest.fixture(autouse=True)
async def invariants(db: Database) -> AsyncIterator[InvariantCheck]:
    """Spec 12 §4.5 after every bookings test (before the tables are truncated)."""
    check = InvariantCheck()
    yield check
    if check.enabled:
        async with db.sessionmaker() as session:
            await assert_invariants(
                session, allow_inactive_recipients=check.allow_inactive_recipients
            )

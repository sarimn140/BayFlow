"""Fixtures of the qc module's DB tests (see `support.py`)."""

from collections.abc import Iterator
from datetime import timedelta

import pytest

from app.core.database import Database
from app.shared.clock import SimulatedClock, use_clock
from tests.modules.qc.support import START, BookingsStandIn, QcWorld


@pytest.fixture
def qc_clock() -> Iterator[SimulatedClock]:
    """A stepping clock (spec 12 §4.4): every action gets its own instant, one minute apart."""
    clock = SimulatedClock(START, step=timedelta(minutes=1))
    with use_clock(clock):
        yield clock


@pytest.fixture
async def world(db: Database, qc_clock: SimulatedClock) -> QcWorld:
    return await QcWorld.build(db, qc_clock)


@pytest.fixture
def bookings(world: QcWorld) -> BookingsStandIn:
    return BookingsStandIn(world)

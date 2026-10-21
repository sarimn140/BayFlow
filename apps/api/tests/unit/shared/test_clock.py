"""The single time source (D63, spec 12 §4.4)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.shared import clock as clock_module
from app.shared.clock import (
    Clock,
    SimulatedClock,
    SystemClock,
    get_clock,
    set_clock,
    use_clock,
    utcnow,
)

START = datetime(2026, 10, 14, 4, 0, tzinfo=UTC)


def test_system_clock_is_the_default_and_returns_aware_utc() -> None:
    assert isinstance(get_clock(), SystemClock)
    now = utcnow()
    assert now.tzinfo is UTC
    assert isinstance(SystemClock(), Clock)


def test_simulated_clock_is_frozen_until_moved() -> None:
    simulated = SimulatedClock(START)
    assert simulated.now() == simulated.now() == START
    simulated.advance(timedelta(minutes=30))
    assert simulated.now() == START + timedelta(minutes=30)
    simulated.set(START - timedelta(days=3))  # the seed back-dates sample bookings
    assert simulated.now() == START - timedelta(days=3)


def test_simulated_clock_can_step_on_every_read() -> None:
    stepping = SimulatedClock(START, step=timedelta(seconds=1))
    assert [stepping.now() for _ in range(3)] == [
        START,
        START + timedelta(seconds=1),
        START + timedelta(seconds=2),
    ]


def test_simulated_clock_normalises_offsets_to_utc() -> None:
    karachi = timezone(timedelta(hours=5))
    simulated = SimulatedClock(datetime(2026, 10, 16, 10, 0, tzinfo=karachi))
    assert simulated.now() == datetime(2026, 10, 16, 5, 0, tzinfo=UTC)
    assert simulated.now().tzinfo is UTC


def test_simulated_clock_rejects_naive_times_and_going_backwards_with_advance() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SimulatedClock(START.replace(tzinfo=None))
    simulated = SimulatedClock(START)
    with pytest.raises(ValueError, match="only moves forward"):
        simulated.advance(timedelta(seconds=-1))
    with pytest.raises(ValueError, match="step"):
        SimulatedClock(START, step=timedelta(seconds=-1))


def test_use_clock_installs_and_restores_the_process_clock() -> None:
    simulated = SimulatedClock(START)
    with use_clock(simulated) as installed:
        assert installed is simulated
        assert get_clock() is simulated
        assert utcnow() == START
    assert isinstance(get_clock(), SystemClock)


def test_set_clock_returns_the_previous_clock() -> None:
    previous = set_clock(SimulatedClock(START))
    try:
        assert utcnow() == START
    finally:
        set_clock(previous)
    assert get_clock() is previous


def test_the_clock_fixture_freezes_time(clock: SimulatedClock) -> None:
    assert utcnow() == clock.now() == START
    clock.advance(timedelta(hours=1))
    assert utcnow() == START + timedelta(hours=1)
    assert clock_module.get_clock() is clock

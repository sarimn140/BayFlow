"""The single source of "now" (D63, spec 12 §4.4).

Every application-written timestamp and every "now" check (slot rules, ring deadlines, JWT
`iat`/`exp`) reads `utcnow()`, shorthand for `get_clock().now()`: the process-wide `Clock` is
`SystemClock` in production and a `SimulatedClock` in the seed and in tests. Domain functions never
read the time; they receive `now` as an argument. Ruff's TID251 bans every other way of reading
the time; the only exception is the rate limiters' windows (library-managed system time).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """The current instant as a timezone-aware UTC datetime."""
        ...


def _require_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = "clock times must be timezone-aware"
        raise ValueError(msg)
    return value.astimezone(UTC)


class SystemClock:
    """Wall-clock time (production)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class SimulatedClock:
    """A controllable clock for the seed and tests (spec 12 §4.4).

    Frozen: time stands still until `set()` or `advance()` moves it. Stepping: with `step`, every
    `now()` call returns the current instant and then moves the clock forward by `step`, so each
    action gets its own instant and business timestamps strictly increase.
    """

    def __init__(self, start: datetime, *, step: timedelta | None = None) -> None:
        if step is not None and step < timedelta(0):
            msg = "step must not be negative"
            raise ValueError(msg)
        self._now = _require_aware_utc(start)
        self._step = step

    def now(self) -> datetime:
        current = self._now
        if self._step:
            self._now = current + self._step
        return current

    def set(self, value: datetime) -> None:
        """Jump to `value` (any direction): the seed sets the clock before each scripted step."""
        self._now = _require_aware_utc(value)

    def advance(self, delta: timedelta) -> None:
        """Move forward by `delta` (use `set()` to go back)."""
        if delta < timedelta(0):
            msg = "advance() only moves forward; use set() to go back"
            raise ValueError(msg)
        self._now += delta


_current_clock: Clock = SystemClock()


def get_clock() -> Clock:
    """The process-wide clock (`SystemClock` unless the seed or a test installed another)."""
    return _current_clock


def set_clock(clock: Clock) -> Clock:
    """Install `clock` as the process-wide clock and return the previous one."""
    global _current_clock  # noqa: PLW0603 - the one swappable time source (D63)
    previous = _current_clock
    _current_clock = clock
    return previous


@contextmanager
def use_clock(clock: Clock) -> Iterator[Clock]:
    """Temporarily install `clock` (seed runs, tests); the previous clock is restored after."""
    previous = set_clock(clock)
    try:
        yield clock
    finally:
        set_clock(previous)


def utcnow() -> datetime:
    """Shorthand for `get_clock().now()`: the current instant, timezone-aware UTC (D63)."""
    return _require_aware_utc(get_clock().now())

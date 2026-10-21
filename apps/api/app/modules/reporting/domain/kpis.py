"""Reporting KPIs (`modules/reporting.md`, spec 03 §3.7). Pure: "now" and the time zone are passed
in (D63); no I/O, no framework.

- `STATUS_ORDER`: the 17 booking statuses in glossary §3 order, the order of `status_counts`.
- The status groups of the owner summary and of the overview's KPI tiles: `SA_ACTION_STATUSES`
  (6: the non-terminal statuses whose step owner is the Service Advisor, glossary §3 →
  `needs_sa_action`), `IN_PROGRESS_STATUSES` (9: every other non-terminal status → `in_progress`)
  and `TERMINAL_STATUSES` (2). The three groups partition the 17 statuses.
- `local_day_window(now, tz)`: a shop's "today" (D38) — the local date of `now` in the shop's time
  zone and its half-open UTC window `[start, end)`, from the local midnight of that date to the
  local midnight of the next date. Each midnight is converted on its own (never `start + 24 h`),
  so a DST day of 23 or 25 hours is exact.
"""

import datetime as dt
from collections.abc import Collection, Mapping
from typing import NamedTuple

from app.shared.enums import BookingStatus

STATUS_ORDER: tuple[BookingStatus, ...] = tuple(BookingStatus)
"""Glossary §3 order: `BookingStatus` is declared in that order (D74)."""

SA_ACTION_STATUSES: frozenset[BookingStatus] = frozenset(
    {
        BookingStatus.PENDING,
        BookingStatus.CONFIRMED,
        BookingStatus.ESTIMATE_REVIEW,
        BookingStatus.ESTIMATE_APPROVED,
        BookingStatus.ESTIMATE_REJECTED,
        BookingStatus.READY_FOR_PICKUP,
    }
)
"""`needs_sa_action`: the step owner is the Service Advisor. `READY_FOR_PICKUP` is also reported on
its own as `ready_for_pickup`."""

IN_PROGRESS_STATUSES: frozenset[BookingStatus] = frozenset(
    {
        BookingStatus.ASSIGNED,
        BookingStatus.INSPECTING,
        BookingStatus.AWAITING_CUSTOMER,
        BookingStatus.PARTS_PENDING,
        BookingStatus.PARTS_ORDERED,
        BookingStatus.PARTS_READY,
        BookingStatus.IN_REPAIR,
        BookingStatus.QC_PENDING,
        BookingStatus.QC_IN_PROGRESS,
    }
)
"""`in_progress`: every non-terminal status whose step owner is not the Service Advisor."""

TERMINAL_STATUSES: frozenset[BookingStatus] = frozenset(
    {BookingStatus.COMPLETED, BookingStatus.CANCELLED}
)

LOW_STOCK_PREVIEW_SIZE = 5
"""The overview's `low_stock` lists at most this many parts (spec 03 §3.7)."""


def ordered_status_counts(
    counts: Mapping[BookingStatus, int],
) -> list[tuple[BookingStatus, int]]:
    """Every status in glossary §3 order with its count; a status missing from `counts` is 0."""
    return [(status, counts.get(status, 0)) for status in STATUS_ORDER]


def count_in(counts: Mapping[BookingStatus, int], statuses: Collection[BookingStatus]) -> int:
    """The number of bookings in any of `statuses` (missing statuses count 0)."""
    return sum(counts.get(status, 0) for status in statuses)


class DayWindow(NamedTuple):
    """One shop-local day: its date and its half-open UTC window `[start, end)`."""

    date: dt.date
    start: dt.datetime  # aware UTC: the first instant of `date` in the shop's time zone
    end: dt.datetime  # aware UTC: the first instant of the next date


def local_midnight(day: dt.date, tz: dt.tzinfo) -> dt.datetime:
    """The first instant of the local date `day` in `tz`, as an aware UTC datetime.

    `fold=0` takes the first occurrence when midnight repeats (a fall-back from 01:00 to 00:00);
    when midnight lies in a spring-forward gap (00:00 to 01:00), the offset before the gap maps it
    onto the transition instant, which is exactly when that date begins.
    """
    return dt.datetime.combine(day, dt.time.min, tzinfo=tz).astimezone(dt.UTC)


def local_day_window(now: dt.datetime, tz: dt.tzinfo) -> DayWindow:
    """The shop-local date of `now` and its UTC window `[start, end)` (D38, D63).

    `start` is the local midnight of the date and `end` the local midnight of the next date, both
    converted to UTC. With `Asia/Karachi` (UTC+5, no DST), `now = 2026-10-15T19:30:00Z` is Friday
    16 Oct 2026, 00:30 PKT: `[2026-10-15T19:00:00Z, 2026-10-16T19:00:00Z)`. Consecutive days tile
    the time line without gaps or overlaps, and `start <= now < end`.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        msg = "now must be timezone-aware"
        raise ValueError(msg)
    today = now.astimezone(tz).date()
    return DayWindow(
        date=today,
        start=local_midnight(today, tz),
        end=local_midnight(today + dt.timedelta(days=1), tz),
    )

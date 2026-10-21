"""Slot maths (D37, D38; `modules/scheduling.md` §7). Pure: "now" is always passed in (D63).

Slots are computed, never stored. The grid of a day is anchored at local midnight in the shop's
IANA timezone and steps by `slot_duration_minutes`; the day's working hours select the open grid
slots, and a slot must end by closing time. A slot is offered when it starts strictly after now
and its local date is at most today + 30 (whole local days, matching the wizard calendar).

DST (not used by `Asia/Karachi`, but any IANA zone is accepted): a wall time that does not exist
(spring-forward gap) is skipped; an ambiguous one (fall-back) uses its first occurrence.
"""

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from types import MappingProxyType
from zoneinfo import ZoneInfo

from app.modules.shops.domain.grid import ScheduleConfig, minutes_of

BOOKING_HORIZON_DAYS = 30  # D37: inclusive, in local days


@dataclass(frozen=True, slots=True, order=True)
class GridSlot:
    """A computed slot: aware UTC instants, `slot_end = slot_start + slot_duration_minutes`."""

    slot_start: datetime
    slot_end: datetime


class SlotProblem(StrEnum):
    """Why a requested slot start cannot be booked (glossary §10 `INVALID_SLOT` reason codes)."""

    OFF_GRID = "off_grid"
    IN_PAST = "in_past"
    BEYOND_HORIZON = "beyond_horizon"
    CLOSED_DAY = "closed_day"
    OUTSIDE_HOURS = "outside_hours"


SLOT_PROBLEM_MESSAGES = MappingProxyType(
    {
        SlotProblem.OFF_GRID: "This time is not one of the shop's slot start times.",
        SlotProblem.IN_PAST: "This time slot has already started.",
        SlotProblem.BEYOND_HORIZON: f"Bookings open at most {BOOKING_HORIZON_DAYS} days ahead.",
        SlotProblem.CLOSED_DAY: "The shop is closed on this day.",
        SlotProblem.OUTSIDE_HOURS: "This time is outside the shop's working hours.",
    }
)


def _require_aware(moment: datetime, name: str) -> None:
    if moment.tzinfo is None or moment.utcoffset() is None:
        msg = f"{name} must be timezone-aware"
        raise ValueError(msg)


def bookable_dates(now: datetime, timezone: str) -> tuple[date, date]:
    """The first and last local dates with offered slots: today … today + 30 (D37)."""
    _require_aware(now, "now")
    today = now.astimezone(ZoneInfo(timezone)).date()
    return today, today + timedelta(days=BOOKING_HORIZON_DAYS)


def _wall_time_exists(local: datetime) -> bool:
    """False inside a DST gap: the wall time does not survive a round trip through UTC."""
    round_trip = local.astimezone(UTC).astimezone(local.tzinfo)
    return round_trip.replace(tzinfo=None) == local.replace(tzinfo=None)


def day_slots(config: ScheduleConfig, day: date) -> list[GridSlot]:
    """The open grid slots of one local date, in time order (`modules/scheduling.md` §7.1).

    Grid times are `00:00 + k * step` local; working hours select them and a slot must end by
    closing time. (Shops keeps the hours on the grid; were they not, the first slot would still
    start on the grid.)
    """
    working_day = config.day(day.weekday())
    if working_day.is_closed or working_day.opens_at is None or working_day.closes_at is None:
        return []
    step = config.slot_duration_minutes
    zone = ZoneInfo(config.timezone)
    minute = math.ceil(minutes_of(working_day.opens_at) / step) * step
    closing = minutes_of(working_day.closes_at)
    slots: list[GridSlot] = []
    while minute + step <= closing:
        local = datetime.combine(day, time(minute // 60, minute % 60), tzinfo=zone)  # fold = 0
        if _wall_time_exists(local):
            start = local.astimezone(UTC)
            slots.append(GridSlot(start, start + timedelta(minutes=step)))
        minute += step
    return slots


def is_offered(slot: GridSlot, config: ScheduleConfig, now: datetime) -> bool:
    """Starts strictly after `now` and lies within the 30-day horizon (capacity not included)."""
    _require_aware(now, "now")
    if slot.slot_start <= now:
        return False
    _, last = bookable_dates(now, config.timezone)
    return slot.slot_start.astimezone(ZoneInfo(config.timezone)).date() <= last


def _grid_problem(local: datetime, step_minutes: int) -> SlotProblem | None:
    """Rule 1: the local wall time is `00:00 + k * step` with no seconds."""
    minute = local.hour * 60 + local.minute
    if local.second or local.microsecond or minute % step_minutes:
        return SlotProblem.OFF_GRID
    return None


def _time_problem(local: datetime, slot_start: datetime, now: datetime) -> SlotProblem | None:
    """Rules 2 and 3: after now; local date at most today + 30."""
    if slot_start <= now:
        return SlotProblem.IN_PAST
    if local.date() > now.astimezone(local.tzinfo).date() + timedelta(days=BOOKING_HORIZON_DAYS):
        return SlotProblem.BEYOND_HORIZON
    return None


def _hours_problem(config: ScheduleConfig, local: datetime) -> SlotProblem | None:
    """Rules 4 and 5: an open weekday; starts at or after opening and ends by closing."""
    working_day = config.day(local.weekday())
    if working_day.is_closed or working_day.opens_at is None or working_day.closes_at is None:
        return SlotProblem.CLOSED_DAY
    minute = local.hour * 60 + local.minute
    opens, closes = minutes_of(working_day.opens_at), minutes_of(working_day.closes_at)
    if minute < opens or minute + config.slot_duration_minutes > closes:
        return SlotProblem.OUTSIDE_HOURS
    return None


def _instant_problem(
    config: ScheduleConfig, local: datetime, slot_start: datetime
) -> SlotProblem | None:
    """Rule 6: the instant is one of the day's grid slots (fails only in a DST gap or on the
    second occurrence of an ambiguous wall time)."""
    if all(slot.slot_start != slot_start for slot in day_slots(config, local.date())):
        return SlotProblem.OFF_GRID
    return None


def slot_problem(config: ScheduleConfig, slot_start: datetime, now: datetime) -> SlotProblem | None:
    """The first broken rule of `modules/scheduling.md` §7.4 for a requested start, or None.

    1 off the grid (local wall time not `00:00 + k * step`, or seconds) → 2 not after now → 3 local
    date beyond today + 30 → 4 closed weekday → 5 starts before opening or ends after closing →
    6 not one of the day's grid instants (a DST gap, or the second occurrence of an ambiguous
    wall time) → `off_grid`.
    """
    _require_aware(slot_start, "slot_start")
    _require_aware(now, "now")
    try:
        local = slot_start.astimezone(ZoneInfo(config.timezone))
    except OverflowError:  # an instant at the very edge of the datetime range
        return SlotProblem.IN_PAST if slot_start <= now else SlotProblem.BEYOND_HORIZON
    return (
        _grid_problem(local, config.slot_duration_minutes)
        or _time_problem(local, slot_start, now)
        or _hours_problem(config, local)
        or _instant_problem(config, local, slot_start)
    )


def grid_slot_at(config: ScheduleConfig, slot_start: datetime) -> GridSlot:
    """The slot that starts at a (valid) instant."""
    start = slot_start.astimezone(UTC)
    return GridSlot(start, start + timedelta(minutes=config.slot_duration_minutes))

"""The slot grid of a shop (D37, D38): value objects and the rules for a working week. Pure.

The grid is anchored at local midnight in the shop's IANA timezone and steps by
`slot_duration_minutes`; a shop's 7 working days (Monday = 0, glossary §5) only select which grid
slots are open, so opening and closing times must lie on the grid and a day's last slot ends
exactly at its closing time. Scheduling's slot maths imports these value objects.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import time
from functools import cache
from uuid import UUID
from zoneinfo import available_timezones

DAYS_PER_WEEK = 7
WEEKDAYS = range(DAYS_PER_WEEK)
DEFAULT_TIMEZONE = "Asia/Karachi"  # D38

# Zone keys a system or the tzdata package may list that are not meaningful for a shop.
_EXCLUDED_ZONE_KEYS = frozenset({"Factory", "localtime", "posixrules"})


@dataclass(frozen=True, slots=True)
class WorkingDay:
    """One weekday's hours in shop-local wall-clock time; both times are None when closed."""

    weekday: int  # 0 = Monday … 6 = Sunday (Python's date.weekday())
    is_closed: bool
    opens_at: time | None
    closes_at: time | None

    @classmethod
    def closed(cls, weekday: int) -> "WorkingDay":
        return cls(weekday=weekday, is_closed=True, opens_at=None, closes_at=None)


@dataclass(frozen=True, slots=True)
class ScheduleConfig:
    """Everything the slot maths needs about one shop (D37)."""

    shop_id: UUID
    timezone: str  # IANA name
    slot_duration_minutes: int  # 15-240, a multiple of 15
    slot_capacity: int  # 1-50
    days: tuple[WorkingDay, ...]  # exactly 7, index = weekday

    def day(self, weekday: int) -> WorkingDay:
        return self.days[weekday]


@dataclass(frozen=True, slots=True)
class WeekProblem:
    """One invalid entry of a submitted week, reported as `working_hours.<index>.<field>`."""

    index: int  # position in the submitted list
    field: str  # weekday | opens_at | closes_at
    code: str  # duplicate | missing | not_on_grid | invalid_range
    message: str

    @property
    def path(self) -> str:
        return f"working_hours.{self.index}.{self.field}"


def minutes_of(moment: time) -> int:
    """Minutes since local midnight of a wall-clock time."""
    return moment.hour * 60 + moment.minute


def is_on_grid(moment: time, step_minutes: int) -> bool:
    """D37: `00:00 + k * step` with no seconds (the grid is anchored at local midnight)."""
    return moment.second == 0 and moment.microsecond == 0 and minutes_of(moment) % step_minutes == 0


def _open_day_problems(index: int, day: WorkingDay, step_minutes: int) -> list[WeekProblem]:
    problems: list[WeekProblem] = []
    for field, value in (("opens_at", day.opens_at), ("closes_at", day.closes_at)):
        if value is None:
            problems.append(
                WeekProblem(
                    index, field, "missing", "An open day needs an opening and a closing time."
                )
            )
        elif not is_on_grid(value, step_minutes):
            problems.append(
                WeekProblem(
                    index,
                    field,
                    "not_on_grid",
                    f"Times must lie on the {step_minutes}-minute slot grid counted from midnight.",
                )
            )
    if day.opens_at is not None and day.closes_at is not None and day.closes_at <= day.opens_at:
        problems.append(
            WeekProblem(
                index,
                "closes_at",
                "invalid_range",
                "The closing time must be later than the opening time (overnight hours are not "
                "supported).",
            )
        )
    return problems


def week_problems(days: Sequence[WorkingDay], step_minutes: int) -> list[WeekProblem]:
    """Every rule broken by a submitted week (`modules/shops.md` §7.1), in request order.

    Distinct weekdays (`duplicate`); an open day has both times (`missing`), on the grid
    (`not_on_grid`), closing after opening (`invalid_range`). Times of a closed day are ignored.
    The list length (exactly 7) and the time format are checked by the request schema.
    """
    problems: list[WeekProblem] = []
    seen: set[int] = set()
    for index, day in enumerate(days):
        if day.weekday in seen:
            problems.append(
                WeekProblem(index, "weekday", "duplicate", "This weekday is listed twice.")
            )
        seen.add(day.weekday)
        if not day.is_closed:
            problems.extend(_open_day_problems(index, day, step_minutes))
    return problems


def hours_fit_grid(days: Sequence[WorkingDay], step_minutes: int) -> bool:
    """Whether every opening and closing time of the open days lies on a grid of `step`."""
    return all(
        day.is_closed
        or all(
            moment is not None and is_on_grid(moment, step_minutes)
            for moment in (day.opens_at, day.closes_at)
        )
        for day in days
    )


def normalised_week(days: Sequence[WorkingDay]) -> tuple[WorkingDay, ...]:
    """Seven days indexed by weekday; closed days carry no times; a missing weekday is closed."""
    by_weekday = {day.weekday: day for day in days}
    week: list[WorkingDay] = []
    for weekday in WEEKDAYS:
        day = by_weekday.get(weekday)
        if day is None or day.is_closed:
            week.append(WorkingDay.closed(weekday))
        else:
            week.append(day)
    return tuple(week)


@cache
def _zone_keys() -> frozenset[str]:
    return frozenset(available_timezones()) - _EXCLUDED_ZONE_KEYS


def is_valid_timezone(name: str) -> bool:
    """An IANA zone name the API can compute slots in (D38), e.g. `Asia/Karachi`."""
    return name in _zone_keys()

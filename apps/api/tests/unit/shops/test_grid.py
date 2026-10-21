"""The midnight-anchored grid and the working-week rules (D37; BK-30 and SHP-03, domain halves)."""

import uuid
from datetime import time

import pytest

from app.modules.shops.domain.grid import (
    ScheduleConfig,
    WorkingDay,
    hours_fit_grid,
    is_on_grid,
    is_valid_timezone,
    minutes_of,
    normalised_week,
    week_problems,
)


def open_day(weekday: int, opens: time | None, closes: time | None) -> WorkingDay:
    return WorkingDay(weekday=weekday, is_closed=False, opens_at=opens, closes_at=closes)


def full_week(opens: time = time(9), closes: time = time(18)) -> list[WorkingDay]:
    return [open_day(day, opens, closes) for day in range(6)] + [WorkingDay.closed(6)]


def problems(days: list[WorkingDay], step: int) -> list[tuple[str, str]]:
    return [(problem.path, problem.code) for problem in week_problems(days, step)]


def test_minutes_of() -> None:
    assert minutes_of(time(0)) == 0
    assert minutes_of(time(9, 45)) == 585
    assert minutes_of(time(23, 59)) == 1439


@pytest.mark.parametrize(
    ("moment", "step", "on_grid"),
    [
        (time(9), 45, True),  # 12 x 45 (BK-30)
        (time(18), 45, True),  # 24 x 45
        (time(9, 30), 45, False),
        (time(9, 30), 30, True),
        (time(0), 240, True),
        (time(10, 15), 15, True),
        (time(10, 0, 30), 15, False),  # seconds are never on the grid
    ],
)
def test_bk30_the_grid_is_anchored_at_local_midnight(
    moment: time, step: int, on_grid: bool
) -> None:
    assert is_on_grid(moment, step) is on_grid


def test_a_valid_week_has_no_problems() -> None:
    assert problems(full_week(), 60) == []
    assert problems(full_week(time(9), time(18)), 45) == []


def test_shp03_every_rule_is_reported_with_its_request_index() -> None:
    days = [
        open_day(0, time(9), time(18)),
        open_day(0, time(9), time(18)),  # duplicate weekday
        open_day(2, None, time(18)),  # missing opening
        open_day(3, time(9), None),  # missing closing
        open_day(4, time(9, 30), time(18)),  # off the 60-minute grid
        open_day(5, time(18), time(9)),  # closing before opening
        WorkingDay(weekday=6, is_closed=True, opens_at=time(1, 7), closes_at=None),  # ignored
    ]
    assert problems(days, 60) == [
        ("working_hours.1.weekday", "duplicate"),
        ("working_hours.2.opens_at", "missing"),
        ("working_hours.3.closes_at", "missing"),
        ("working_hours.4.opens_at", "not_on_grid"),
        ("working_hours.5.closes_at", "invalid_range"),
    ]


def test_equal_opening_and_closing_is_an_invalid_range() -> None:
    days = full_week()
    days[0] = open_day(0, time(9), time(9))
    assert problems(days, 60) == [("working_hours.0.closes_at", "invalid_range")]


def test_both_off_grid_times_are_reported() -> None:
    days = full_week()
    days[3] = open_day(3, time(9, 10), time(17, 50))
    assert problems(days, 60) == [
        ("working_hours.3.opens_at", "not_on_grid"),
        ("working_hours.3.closes_at", "not_on_grid"),
    ]


def test_hours_fit_grid() -> None:
    assert hours_fit_grid(full_week(time(9), time(18)), 45)
    assert hours_fit_grid(full_week(time(9), time(18)), 60)
    assert not hours_fit_grid(full_week(time(9, 30), time(18)), 60)
    assert not hours_fit_grid(full_week(time(9), time(18)), 120)  # 540 % 120 != 0
    assert hours_fit_grid(full_week(time(8), time(18)), 120)
    assert hours_fit_grid([WorkingDay.closed(day) for day in range(7)], 240)


def test_normalised_week_indexes_by_weekday_and_closes_missing_days() -> None:
    week = normalised_week(
        [
            open_day(3, time(9), time(17)),
            WorkingDay(weekday=1, is_closed=True, opens_at=time(9), closes_at=time(17)),
        ]
    )
    assert [day.weekday for day in week] == list(range(7))
    assert week[3] == open_day(3, time(9), time(17))
    assert week[1] == WorkingDay.closed(1)  # a closed day carries no times
    assert week[0] == WorkingDay.closed(0)  # a missing weekday is closed


def test_schedule_config_day_lookup() -> None:
    config = ScheduleConfig(
        shop_id=uuid.uuid4(),
        timezone="Asia/Karachi",
        slot_duration_minutes=60,
        slot_capacity=2,
        days=normalised_week(full_week()),
    )
    assert config.day(4).opens_at == time(9)
    assert config.day(6).is_closed


@pytest.mark.parametrize(
    ("name", "valid"),
    [
        ("Asia/Karachi", True),
        ("Europe/London", True),
        ("UTC", True),
        ("asia/karachi", False),
        ("Mars/Olympus", False),
        ("localtime", False),
        ("Factory", False),
        ("", False),
        ("../etc/passwd", False),
    ],
)
def test_is_valid_timezone(name: str, valid: bool) -> None:
    assert is_valid_timezone(name) is valid

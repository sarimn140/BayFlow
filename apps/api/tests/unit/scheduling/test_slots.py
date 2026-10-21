"""Pure slot maths (D37, D38; `modules/scheduling.md` §7).

Covers BK-08 (each `INVALID_SLOT` reason, frozen "now"), BK-11/BK-12 and BK-30 (domain halves),
SCH-01 (DST), SCH-02 (horizon boundary), SCH-03 (a slot starting exactly now) and SCH-07 (reason
precedence).
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.modules.scheduling.domain.slots import (
    BOOKING_HORIZON_DAYS,
    SLOT_PROBLEM_MESSAGES,
    GridSlot,
    SlotProblem,
    bookable_dates,
    day_slots,
    grid_slot_at,
    is_offered,
    slot_problem,
)
from app.modules.shops.domain.grid import ScheduleConfig, WorkingDay, normalised_week

WEDNESDAY_0900_PKT = datetime(2026, 10, 14, 4, 0, tzinfo=UTC)  # spec 12 §4.4
FRIDAY = date(2026, 10, 16)
FRIDAY_1000_PKT = datetime(2026, 10, 16, 5, 0, tzinfo=UTC)  # glossary §9 example
SUNDAY_1000_PKT = datetime(2026, 10, 18, 5, 0, tzinfo=UTC)


def config(
    *,
    opens: time = time(9),
    closes: time = time(18),
    step: int = 60,
    timezone: str = "Asia/Karachi",
    closed: tuple[int, ...] = (6,),
    capacity: int = 2,
) -> ScheduleConfig:
    days = [
        WorkingDay.closed(day)
        if day in closed
        else WorkingDay(weekday=day, is_closed=False, opens_at=opens, closes_at=closes)
        for day in range(7)
    ]
    return ScheduleConfig(
        shop_id=uuid.uuid4(),
        timezone=timezone,
        slot_duration_minutes=step,
        slot_capacity=capacity,
        days=normalised_week(days),
    )


LAHORE_AUTO_CARE = config()


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


# --- The grid of a day --------------------------------------------------------------------------


def test_bk12_lahore_auto_care_friday_grid() -> None:
    slots = day_slots(LAHORE_AUTO_CARE, FRIDAY)
    assert len(slots) == 9  # 09:00 … 17:00 (spec 11)
    assert slots[0] == GridSlot(utc(2026, 10, 16, 4), utc(2026, 10, 16, 5))
    assert slots[1].slot_start == FRIDAY_1000_PKT  # Friday 10:00 PKT = 05:00 Z
    assert slots[-1] == GridSlot(utc(2026, 10, 16, 12), utc(2026, 10, 16, 13))  # ends at 18:00
    assert all(slot.slot_end - slot.slot_start == timedelta(hours=1) for slot in slots)
    assert slots == sorted(slots)


def test_bk30_a_45_minute_grid_from_midnight() -> None:
    slots = day_slots(config(step=45), FRIDAY)
    local = [(slot.slot_start + timedelta(hours=5)).time() for slot in slots]
    assert local[:3] == [time(9), time(9, 45), time(10, 30)]
    assert local[-1] == time(17, 15)  # 17:15 + 45 = 18:00, the closing time
    assert len(slots) == 12


def test_the_last_slot_must_end_by_closing_time() -> None:
    slots = day_slots(config(opens=time(9), closes=time(11), step=45), FRIDAY)
    local = [(slot.slot_start + timedelta(hours=5)).time() for slot in slots]
    assert local == [time(9), time(9, 45)]  # 10:30 would end at 11:15


def test_off_grid_hours_still_produce_grid_slots() -> None:
    """Shops keeps hours on the grid; were they not, slots would still start on it."""
    slots = day_slots(config(opens=time(9, 30), closes=time(12)), FRIDAY)
    local = [(slot.slot_start + timedelta(hours=5)).time() for slot in slots]
    assert local == [time(10), time(11)]


def test_closed_days_have_no_slots() -> None:
    assert day_slots(LAHORE_AUTO_CARE, date(2026, 10, 18)) == []  # Sunday


def test_sch01_dst_spring_forward_skips_the_missing_hour() -> None:
    london = config(opens=time(0), closes=time(4), timezone="Europe/London", closed=())
    slots = day_slots(london, date(2026, 3, 29))  # 01:00 GMT → 02:00 BST
    assert [slot.slot_start for slot in slots] == [
        utc(2026, 3, 29, 0),  # 00:00 GMT
        utc(2026, 3, 29, 1),  # 02:00 BST (01:00 local does not exist)
        utc(2026, 3, 29, 2),  # 03:00 BST
    ]
    assert all(slot.slot_end == slot.slot_start + timedelta(hours=1) for slot in slots)


def test_sch01_dst_fall_back_uses_the_first_occurrence() -> None:
    london = config(opens=time(0), closes=time(4), timezone="Europe/London", closed=())
    slots = day_slots(london, date(2026, 10, 25))  # 02:00 BST → 01:00 GMT
    assert [slot.slot_start for slot in slots] == [
        utc(2026, 10, 24, 23),  # 00:00 BST
        utc(2026, 10, 25, 0),  # 01:00 BST, the first occurrence
        utc(2026, 10, 25, 2),  # 02:00 GMT
        utc(2026, 10, 25, 3),  # 03:00 GMT
    ]
    now = utc(2026, 10, 20)
    assert slot_problem(london, utc(2026, 10, 25, 0), now) is None
    second_occurrence = utc(2026, 10, 25, 1)  # 01:00 GMT: on the wall-clock grid, not a slot
    assert slot_problem(london, second_occurrence, now) is SlotProblem.OFF_GRID


def test_grid_slot_at() -> None:
    assert grid_slot_at(LAHORE_AUTO_CARE, FRIDAY_1000_PKT) == GridSlot(
        FRIDAY_1000_PKT, FRIDAY_1000_PKT + timedelta(hours=1)
    )


# --- Offered slots --------------------------------------------------------------------------------


def test_sch03_a_slot_starting_exactly_now_is_not_offered() -> None:
    now = utc(2026, 10, 14, 4)  # Wednesday 09:00 PKT
    first, second = day_slots(LAHORE_AUTO_CARE, date(2026, 10, 14))[:2]
    assert first.slot_start == now
    assert not is_offered(first, LAHORE_AUTO_CARE, now)
    assert slot_problem(LAHORE_AUTO_CARE, first.slot_start, now) is SlotProblem.IN_PAST
    assert is_offered(second, LAHORE_AUTO_CARE, now)
    assert not is_offered(second, LAHORE_AUTO_CARE, second.slot_start + timedelta(microseconds=1))


def test_sch02_the_horizon_counts_whole_local_days() -> None:
    now = WEDNESDAY_0900_PKT
    first, last = bookable_dates(now, "Asia/Karachi")
    assert (first, last) == (date(2026, 10, 14), date(2026, 11, 13))
    assert last - first == timedelta(days=BOOKING_HORIZON_DAYS)
    last_day = day_slots(LAHORE_AUTO_CARE, last)  # a Friday: open
    assert last_day
    assert is_offered(last_day[-1], LAHORE_AUTO_CARE, now)  # its afternoon too
    assert slot_problem(LAHORE_AUTO_CARE, last_day[-1].slot_start, now) is None
    beyond = day_slots(LAHORE_AUTO_CARE, last + timedelta(days=1))[0]
    assert not is_offered(beyond, LAHORE_AUTO_CARE, now)
    assert slot_problem(LAHORE_AUTO_CARE, beyond.slot_start, now) is SlotProblem.BEYOND_HORIZON


def test_the_horizon_follows_the_shops_local_date() -> None:
    late_evening = utc(2026, 10, 14, 19, 30)  # Thursday 00:30 PKT, still Wednesday in UTC
    assert bookable_dates(late_evening, "Asia/Karachi")[0] == date(2026, 10, 15)
    assert bookable_dates(late_evening, "UTC")[0] == date(2026, 10, 14)


# --- Slot validation (BK-08, SCH-07) --------------------------------------------------------------


@pytest.mark.parametrize(
    ("slot_start", "problem"),
    [
        (FRIDAY_1000_PKT, None),
        (FRIDAY_1000_PKT + timedelta(minutes=30), SlotProblem.OFF_GRID),
        (FRIDAY_1000_PKT + timedelta(seconds=1), SlotProblem.OFF_GRID),
        (FRIDAY_1000_PKT + timedelta(microseconds=1), SlotProblem.OFF_GRID),
        (utc(2026, 10, 13, 5), SlotProblem.IN_PAST),  # Tuesday 10:00 PKT
        (utc(2026, 11, 16, 5), SlotProblem.BEYOND_HORIZON),  # 33 days ahead
        (SUNDAY_1000_PKT, SlotProblem.CLOSED_DAY),
        (utc(2026, 10, 16, 3), SlotProblem.OUTSIDE_HOURS),  # 08:00 PKT, before opening
        (utc(2026, 10, 16, 13), SlotProblem.OUTSIDE_HOURS),  # 18:00 PKT, would end at 19:00
        (utc(2026, 10, 15, 19), SlotProblem.OUTSIDE_HOURS),  # Friday 00:00 PKT (midnight)
    ],
)
def test_bk08_each_invalid_slot_reason(slot_start: datetime, problem: SlotProblem | None) -> None:
    assert slot_problem(LAHORE_AUTO_CARE, slot_start, WEDNESDAY_0900_PKT) is problem


def test_bk08_an_offset_timestamp_is_the_same_instant() -> None:
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    as_pkt = FRIDAY_1000_PKT.astimezone(ZoneInfo("Asia/Karachi"))
    assert slot_problem(LAHORE_AUTO_CARE, as_pkt, WEDNESDAY_0900_PKT) is None


def test_bk08_a_slot_that_would_end_after_closing_is_outside_hours() -> None:
    """Only reachable with a closing time off the grid (legacy data): 16:30 + 90 min > 17:30."""
    shop = config(opens=time(9), closes=time(17, 30), step=90)
    assert slot_problem(shop, utc(2026, 10, 16, 10), WEDNESDAY_0900_PKT) is None  # 15:00 PKT
    assert slot_problem(shop, utc(2026, 10, 16, 11, 30), WEDNESDAY_0900_PKT) is (
        SlotProblem.OUTSIDE_HOURS
    )
    assert [slot.slot_start for slot in day_slots(shop, FRIDAY)][-1] == utc(2026, 10, 16, 10)


@pytest.mark.parametrize(
    ("slot_start", "problem"),
    [
        (utc(2026, 10, 13, 5, 30), SlotProblem.OFF_GRID),  # off-grid AND in the past
        (utc(2026, 10, 11, 5), SlotProblem.IN_PAST),  # past Sunday: in_past before closed_day
        (utc(2026, 11, 22, 5), SlotProblem.BEYOND_HORIZON),  # far Sunday: horizon first
        (utc(2026, 10, 18, 2), SlotProblem.CLOSED_DAY),  # Sunday 07:00: closed before hours
        (utc(2026, 10, 16, 14), SlotProblem.OUTSIDE_HOURS),  # an on-grid time after closing
    ],
)
def test_sch07_reason_precedence(slot_start: datetime, problem: SlotProblem) -> None:
    assert slot_problem(LAHORE_AUTO_CARE, slot_start, WEDNESDAY_0900_PKT) is problem


def test_slot_problems_have_glossary_codes_and_messages() -> None:
    assert [problem.value for problem in SlotProblem] == [
        "off_grid",
        "in_past",
        "beyond_horizon",
        "closed_day",
        "outside_hours",
    ]
    assert set(SLOT_PROBLEM_MESSAGES) == set(SlotProblem)
    assert SLOT_PROBLEM_MESSAGES[SlotProblem.BEYOND_HORIZON] == (
        "Bookings open at most 30 days ahead."
    )


def test_naive_datetimes_are_refused() -> None:
    naive = datetime(2026, 10, 16, 10, 0)  # noqa: DTZ001 - deliberately naive
    with pytest.raises(ValueError, match="timezone-aware"):
        slot_problem(LAHORE_AUTO_CARE, naive, WEDNESDAY_0900_PKT)
    with pytest.raises(ValueError, match="timezone-aware"):
        slot_problem(LAHORE_AUTO_CARE, FRIDAY_1000_PKT, naive)


def test_instants_at_the_edge_of_the_datetime_range() -> None:
    far_future = datetime(9999, 12, 31, 23, tzinfo=UTC)  # + 5 h overflows in Asia/Karachi
    assert slot_problem(LAHORE_AUTO_CARE, far_future, WEDNESDAY_0900_PKT) is (
        SlotProblem.BEYOND_HORIZON
    )
    new_york = config(timezone="America/New_York")
    far_past = datetime(1, 1, 1, 1, tzinfo=UTC)  # minus 5 h underflows
    assert slot_problem(new_york, far_past, WEDNESDAY_0900_PKT) is SlotProblem.IN_PAST

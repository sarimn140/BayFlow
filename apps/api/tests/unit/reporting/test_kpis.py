"""The reporting KPIs (`app/modules/reporting/domain/kpis.py`), pure and DB-free.

- RPT-09 (unit half): the SA, in-progress and terminal groups partition the 17 statuses, and they
  are exactly what glossary §3's "owner of step" column says (an independent copy of the table).
- RPT-04: `status_counts` follows glossary §3 order, zeros included.
- RPT-05 / D38 / D63: the shop-local "today" window — the spec's Karachi case, every bound, `now`
  in any offset, DST days of 23 and 25 hours (London), midnights that repeat (Havana) or do not
  exist (Havana, Santiago), a date that never existed (Apia, 2011), half-hour and 45-minute
  zones, and a sweep over the transition days of many zones proving that consecutive days tile
  the time line: no gap, no overlap, `start <= now < end`.
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.modules.reporting.domain.kpis import (
    IN_PROGRESS_STATUSES,
    LOW_STOCK_PREVIEW_SIZE,
    SA_ACTION_STATUSES,
    STATUS_ORDER,
    TERMINAL_STATUSES,
    DayWindow,
    count_in,
    local_day_window,
    local_midnight,
    ordered_status_counts,
)
from app.shared.enums import BookingStatus

S = BookingStatus
MICROSECOND = timedelta(microseconds=1)
KARACHI, LONDON = ZoneInfo("Asia/Karachi"), ZoneInfo("Europe/London")

# Glossary §3, written out again: (value, owner of the step, terminal).
GLOSSARY_SECTION_3 = [
    ("PENDING", "Service Advisor", False),
    ("CONFIRMED", "Service Advisor", False),
    ("ASSIGNED", "Technician", False),
    ("INSPECTING", "Technician", False),
    ("ESTIMATE_REVIEW", "Service Advisor", False),
    ("AWAITING_CUSTOMER", "Customer", False),
    ("ESTIMATE_APPROVED", "Service Advisor", False),
    ("ESTIMATE_REJECTED", "Service Advisor", False),
    ("PARTS_PENDING", "Parts Person", False),
    ("PARTS_ORDERED", "Parts Person", False),
    ("PARTS_READY", "Parts Person", False),
    ("IN_REPAIR", "Technician", False),
    ("QC_PENDING", "Any QC Inspector", False),
    ("QC_IN_PROGRESS", "QC Inspector (picker)", False),
    ("READY_FOR_PICKUP", "Service Advisor", False),
    ("COMPLETED", "Customer / SA", True),
    ("CANCELLED", "-", True),
]


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


# --- Status groups and order (RPT-09 unit half, RPT-04) -------------------------------------------


def test_rpt09_the_three_groups_partition_the_17_statuses() -> None:
    groups = (SA_ACTION_STATUSES, IN_PROGRESS_STATUSES, TERMINAL_STATUSES)
    assert [len(group) for group in groups] == [6, 9, 2]
    assert SA_ACTION_STATUSES.isdisjoint(IN_PROGRESS_STATUSES)
    assert SA_ACTION_STATUSES.isdisjoint(TERMINAL_STATUSES)
    assert IN_PROGRESS_STATUSES.isdisjoint(TERMINAL_STATUSES)
    assert set(BookingStatus) == SA_ACTION_STATUSES | IN_PROGRESS_STATUSES | TERMINAL_STATUSES
    assert sum(len(group) for group in groups) == len(BookingStatus) == 17


def test_rpt09_the_groups_follow_the_glossary_step_owners() -> None:
    sa = {value for value, owner, final in GLOSSARY_SECTION_3 if owner == "Service Advisor"}
    others = {value for value, owner, final in GLOSSARY_SECTION_3 if not final} - sa
    final = {value for value, _, is_final in GLOSSARY_SECTION_3 if is_final}
    assert {status.value for status in SA_ACTION_STATUSES} == sa
    assert {status.value for status in IN_PROGRESS_STATUSES} == others
    assert {status.value for status in TERMINAL_STATUSES} == final == {"COMPLETED", "CANCELLED"}
    assert S.READY_FOR_PICKUP in SA_ACTION_STATUSES  # also reported on its own


def test_rpt04_status_order_is_glossary_section_3() -> None:
    assert [status.value for status in STATUS_ORDER] == [row[0] for row in GLOSSARY_SECTION_3]
    assert len(set(STATUS_ORDER)) == 17


def test_rpt04_ordered_status_counts_fill_zeros_in_glossary_order() -> None:
    counts = {S.CANCELLED: 2, S.PENDING: 3, S.QC_IN_PROGRESS: 1}
    ordered = ordered_status_counts(counts)
    assert [status for status, _ in ordered] == list(STATUS_ORDER)
    assert dict(ordered) == {**dict.fromkeys(BookingStatus, 0), **counts}
    assert ordered_status_counts({}) == [(status, 0) for status in STATUS_ORDER]


def test_count_in_sums_the_given_statuses_only() -> None:
    counts = {S.PENDING: 2, S.READY_FOR_PICKUP: 1, S.IN_REPAIR: 4, S.COMPLETED: 9}
    assert count_in(counts, SA_ACTION_STATUSES) == 3
    assert count_in(counts, IN_PROGRESS_STATUSES) == 4
    assert count_in(counts, TERMINAL_STATUSES) == 9
    assert count_in(counts, ()) == 0
    assert count_in({}, SA_ACTION_STATUSES) == 0


def test_low_stock_preview_size() -> None:
    assert LOW_STOCK_PREVIEW_SIZE == 5


# --- The shop-local "today" window (RPT-05, D38, D63) ---------------------------------------------


def test_rpt05_the_spec_case_in_asia_karachi() -> None:
    window = local_day_window(utc(2026, 10, 15, 19, 30), KARACHI)
    assert window == DayWindow(date(2026, 10, 16), utc(2026, 10, 15, 19), utc(2026, 10, 16, 19))
    assert window.start.utcoffset() == window.end.utcoffset() == timedelta(0)
    day, start, end = window  # spec: (date, start, end)
    assert (day, start, end) == (window.date, window.start, window.end)


@pytest.mark.parametrize(
    "now",
    [
        utc(2026, 10, 15, 19, 0),  # the first instant of the day
        utc(2026, 10, 16, 18, 59, 59, 999999),  # the last one
        datetime(2026, 10, 16, 0, 30, tzinfo=timezone(timedelta(hours=5))),  # PKT as an offset
        datetime(2026, 10, 15, 12, 0, tzinfo=timezone(timedelta(hours=-7))),  # any offset
        datetime(2026, 10, 16, 12, 0, tzinfo=KARACHI),  # a zoned instant
    ],
)
def test_rpt05_every_instant_of_the_day_gives_the_same_window(now: datetime) -> None:
    assert local_day_window(now, KARACHI) == DayWindow(
        date(2026, 10, 16), utc(2026, 10, 15, 19), utc(2026, 10, 16, 19)
    )


def test_rpt05_the_end_bound_belongs_to_the_next_day() -> None:
    friday = local_day_window(utc(2026, 10, 16, 12), KARACHI)
    saturday = local_day_window(friday.end, KARACHI)
    assert saturday.date == date(2026, 10, 17)
    assert saturday.start == friday.end
    assert local_day_window(friday.start - MICROSECOND, KARACHI).end == friday.start


def test_rpt05_a_naive_now_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        local_day_window(datetime(2026, 10, 16, 12, 0), KARACHI)  # noqa: DTZ001 - on purpose


def test_rpt05_a_fixed_offset_zone_works_too() -> None:
    pkt = timezone(timedelta(hours=5))
    assert local_day_window(utc(2026, 10, 15, 19, 30), pkt) == local_day_window(
        utc(2026, 10, 15, 19, 30), KARACHI
    )


@pytest.mark.parametrize(
    ("zone", "now", "expected"),
    [
        # Europe/London, BST ends 02:00 -> 01:00 on Sun 25 Oct 2026: a 25-hour day.
        (
            "Europe/London",
            utc(2026, 10, 25, 23, 30),  # 23:30 GMT: still the 25th
            (date(2026, 10, 25), utc(2026, 10, 24, 23), utc(2026, 10, 26, 0), 25),
        ),
        # Europe/London, BST starts 01:00 -> 02:00 on Sun 29 Mar 2026: a 23-hour day.
        (
            "Europe/London",
            utc(2026, 3, 29, 22, 59, 59),  # 23:59:59 BST
            (date(2026, 3, 29), utc(2026, 3, 29, 0), utc(2026, 3, 29, 23), 23),
        ),
        # America/Havana falls back 01:00 -> 00:00 on Sun 1 Nov 2026: midnight happens twice;
        # the day starts at its first occurrence.
        (
            "America/Havana",
            utc(2026, 11, 1, 4, 30),  # 00:30 CDT, the first pass
            (date(2026, 11, 1), utc(2026, 11, 1, 4), utc(2026, 11, 2, 5), 25),
        ),
        # America/Havana springs forward 00:00 -> 01:00 on Sun 8 Mar 2026: no midnight at all;
        # the day starts at the jump (01:00 CDT).
        (
            "America/Havana",
            utc(2026, 3, 8, 5, 0),
            (date(2026, 3, 8), utc(2026, 3, 8, 5), utc(2026, 3, 9, 4), 23),
        ),
        # America/Santiago springs forward 00:00 -> 01:00 on Sun 6 Sep 2026.
        (
            "America/Santiago",
            utc(2026, 9, 6, 12),
            (date(2026, 9, 6), utc(2026, 9, 6, 4), utc(2026, 9, 7, 3), 23),
        ),
        # Australia/Lord_Howe moves by half an hour (02:00 -> 01:30 on Sun 5 Apr 2026).
        (
            "Australia/Lord_Howe",
            utc(2026, 4, 5, 3),
            (date(2026, 4, 5), utc(2026, 4, 4, 13), utc(2026, 4, 5, 13, 30), 24.5),
        ),
        # Asia/Kathmandu is UTC+05:45 all year.
        (
            "Asia/Kathmandu",
            utc(2026, 10, 15, 18, 15),  # 00:00 NPT on the 16th
            (date(2026, 10, 16), utc(2026, 10, 15, 18, 15), utc(2026, 10, 16, 18, 15), 24),
        ),
    ],
    ids=[
        "london-25h",
        "london-23h",
        "havana-midnight-twice",
        "havana-no-midnight",
        "santiago-no-midnight",
        "lord-howe-half-hour",
        "kathmandu-0545",
    ],
)
def test_rpt05_dst_and_unusual_offsets(
    zone: str, now: datetime, expected: tuple[date, datetime, datetime, float]
) -> None:
    day, start, end, hours = expected
    window = local_day_window(now, ZoneInfo(zone))
    assert window == DayWindow(day, start, end)
    assert window.end - window.start == timedelta(hours=hours)
    assert window.start <= now < window.end


def test_rpt05_the_day_before_a_date_that_never_existed() -> None:
    """Samoa skipped Friday 30 Dec 2011 (UTC-10 -> UTC+14). Thursday 29 Dec still lasts 24 h and
    ends exactly where Saturday 31 Dec begins."""
    apia = ZoneInfo("Pacific/Apia")
    thursday = local_day_window(utc(2011, 12, 30, 9, 59, 59), apia)
    assert thursday == DayWindow(date(2011, 12, 29), utc(2011, 12, 29, 10), utc(2011, 12, 30, 10))
    saturday = local_day_window(thursday.end, apia)
    assert saturday.date == date(2011, 12, 31)
    assert saturday.start == thursday.end


def test_local_midnight_is_the_first_instant_of_the_date() -> None:
    assert local_midnight(date(2026, 10, 16), KARACHI) == utc(2026, 10, 15, 19)
    assert local_midnight(date(2026, 10, 25), LONDON) == utc(2026, 10, 24, 23)
    assert local_midnight(date(2026, 10, 26), LONDON) == utc(2026, 10, 26, 0)


SWEEP_ZONES = [
    "Asia/Karachi",
    "UTC",
    "Europe/London",
    "Europe/Berlin",
    "America/New_York",
    "America/Havana",
    "America/Santiago",
    "America/Sao_Paulo",
    "Asia/Beirut",
    "Africa/Cairo",
    "Australia/Lord_Howe",
    "Pacific/Chatham",
    "Asia/Kathmandu",
    "Pacific/Apia",
]


def _transition_days(zone: ZoneInfo, first: date, last: date) -> Iterator[date]:
    """Local dates whose UTC offset at local noon differs from the day before or after."""
    day = first
    while day <= last:
        offsets = {
            datetime.combine(day + timedelta(days=shift), datetime.min.time(), tzinfo=zone)
            .replace(hour=12)
            .utcoffset()
            for shift in (-1, 0, 1)
        }
        if len(offsets) > 1:
            yield day
        day += timedelta(days=1)


def _probe_instants(zone: ZoneInfo) -> Iterator[datetime]:
    """Every 15 minutes (and a microsecond either side) across each transition day of 2010-2030,
    plus one instant every 7 h 13 min across 2026."""
    for day in _transition_days(zone, date(2010, 1, 1), date(2030, 12, 31)):
        base = local_midnight(day, zone) - timedelta(hours=2)
        for quarter in range(4 * 30):
            moment = base + timedelta(minutes=15 * quarter)
            yield from (moment - MICROSECOND, moment, moment + MICROSECOND)
    moment = utc(2026, 1, 1)
    while moment < utc(2027, 1, 1):
        yield moment
        moment += timedelta(hours=7, minutes=13)


@pytest.mark.parametrize("name", SWEEP_ZONES)
def test_rpt05_consecutive_days_tile_the_time_line(name: str) -> None:
    zone = ZoneInfo(name)
    for now in _probe_instants(zone):
        window = local_day_window(now, zone)
        assert window.start <= now < window.end, (name, now)
        assert window.date == now.astimezone(zone).date(), (name, now)
        assert window.start.astimezone(zone).date() == window.date, (name, now)
        assert (window.end - MICROSECOND).astimezone(zone).date() == window.date, (name, now)
        assert local_day_window(window.end, zone).start == window.end, (name, now)
        assert local_day_window(window.start - MICROSECOND, zone).end == window.start, (name, now)
        assert timedelta(hours=22) <= window.end - window.start <= timedelta(hours=26), name

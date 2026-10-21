"""The admin module's pure rules (spec 19 §4 E-61, E-63, E-75; D38): CSV quoting and formula
neutralisation, shop-local days, booking phases."""

import csv
import io
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.modules.admin.domain.csv_export import csv_line, csv_lines, neutralise
from app.modules.admin.domain.periods import last_days, local_midnight
from app.modules.admin.domain.phases import PHASE_OF, StatusPhase, counts_by_phase
from app.shared.enums import BookingStatus

KARACHI = ZoneInfo("Asia/Karachi")


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("=1+1", "'=1+1"),
        ("+92 300", "'+92 300"),
        ("-5", "'-5"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\tTab", "'\tTab"),
        ("\rReturn", "'\rReturn"),
        ("Plain text", "Plain text"),
        ("a=b", "a=b"),
        ("", ""),
    ],
)
def test_formula_prefixes_are_neutralised(cell: str, expected: str) -> None:
    assert neutralise(cell) == expected


def test_csv_lines_follow_rfc_4180() -> None:
    line = csv_line(["Comma, here", 'Quote "q"', "Line\nbreak", "plain"])
    assert line == '"Comma, here","Quote ""q""","Line\nbreak",plain\r\n'
    rows = list(
        csv.reader(io.StringIO("".join(csv_lines(["a", "b"], [["=x", "y,z"]])), newline=""))
    )
    assert rows == [["a", "b"], ["'=x", "y,z"]]


def test_the_header_is_never_neutralised() -> None:
    assert next(iter(csv_lines(["-header", "b"], []))) == "-header,b\r\n"


def test_last_days_are_local_midnights_in_utc() -> None:
    now = datetime(2026, 10, 14, 4, 0, tzinfo=UTC)  # 09:00 in Karachi
    today, bounds = last_days(now, KARACHI, 3)
    assert today == date(2026, 10, 14)
    assert bounds == [
        datetime(2026, 10, 11, 19, 0, tzinfo=UTC),
        datetime(2026, 10, 12, 19, 0, tzinfo=UTC),
        datetime(2026, 10, 13, 19, 0, tzinfo=UTC),
        datetime(2026, 10, 14, 19, 0, tzinfo=UTC),
    ]
    late = datetime(2026, 10, 14, 19, 30, tzinfo=UTC)  # 00:30 on 15 Oct in Karachi
    assert last_days(late, KARACHI, 1) == (
        date(2026, 10, 15),
        [datetime(2026, 10, 14, 19, 0, tzinfo=UTC), datetime(2026, 10, 15, 19, 0, tzinfo=UTC)],
    )


def test_local_midnight_handles_dst_days() -> None:
    london = ZoneInfo("Europe/London")  # 25 Oct 2026 is a 25-hour day there
    start = local_midnight(date(2026, 10, 25), london)
    end = local_midnight(date(2026, 10, 26), london)
    assert (end - start).total_seconds() == 25 * 3600


def test_last_days_needs_an_aware_now_and_a_positive_span() -> None:
    with pytest.raises(ValueError, match="aware"):
        last_days(datetime(2026, 10, 14, 4, 0), KARACHI, 1)  # noqa: DTZ001 - the point of the test
    with pytest.raises(ValueError, match="at least 1"):
        last_days(datetime(2026, 10, 14, 4, 0, tzinfo=UTC), KARACHI, 0)


def test_every_status_has_its_glossary_phase() -> None:
    assert set(PHASE_OF) == set(BookingStatus)
    assert PHASE_OF[BookingStatus.READY_FOR_PICKUP] is StatusPhase.HANDOVER
    assert PHASE_OF[BookingStatus.CANCELLED] is StatusPhase.CLOSED
    counts = counts_by_phase({BookingStatus.PENDING: 2, BookingStatus.CONFIRMED: 1})
    assert counts[0] == (StatusPhase.INTAKE, 3)
    assert [phase for phase, _ in counts] == list(StatusPhase)
    assert sum(count for _, count in counts) == 3

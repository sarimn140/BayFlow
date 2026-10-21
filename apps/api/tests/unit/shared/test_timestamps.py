"""Timestamps on the wire: UTC with `Z` (glossary §9, spec 03 §1.5)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, ValidationError

from app.shared.timestamps import Timestamp, format_timestamp

PKT = timezone(timedelta(hours=5))


class Event(BaseModel):
    at: Timestamp


def test_friday_ten_am_karachi_is_serialised_as_utc_z() -> None:
    event = Event(at=datetime(2026, 10, 16, 10, 0, tzinfo=PKT))
    assert event.model_dump_json() == '{"at":"2026-10-16T05:00:00Z"}'
    assert event.at.tzinfo is UTC


def test_milliseconds_only_when_non_zero_and_microseconds_dropped() -> None:
    assert format_timestamp(datetime(2026, 10, 16, 5, 0, 0, 123456, tzinfo=UTC)) == (
        "2026-10-16T05:00:00.123Z"
    )
    assert format_timestamp(datetime(2026, 10, 16, 5, 0, 0, 999, tzinfo=UTC)) == (
        "2026-10-16T05:00:00Z"
    )


def test_requests_must_carry_an_offset() -> None:
    assert Event.model_validate({"at": "2026-10-16T05:00:00Z"}).at == datetime(
        2026, 10, 16, 5, 0, tzinfo=UTC
    )
    assert Event.model_validate({"at": "2026-10-16T10:00:00+05:00"}).at == datetime(
        2026, 10, 16, 5, 0, tzinfo=UTC
    )
    with pytest.raises(ValidationError) as caught:
        Event.model_validate({"at": "2026-10-16T05:00:00"})
    assert caught.value.errors()[0]["type"] == "timezone_aware"

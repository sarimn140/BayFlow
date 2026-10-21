"""Scheduling schemas: the strict availability date and the slot wire format (BK-12, BK-27)."""

import uuid
from datetime import UTC, date, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from app.modules.scheduling.schemas import AvailabilityRead, QueryDate, SlotRead

query_date: TypeAdapter[date] = TypeAdapter(QueryDate)


@pytest.mark.parametrize("value", ["2026-10-16", "2024-02-29"])
def test_valid_dates(value: str) -> None:
    assert query_date.validate_python(value) == date.fromisoformat(value)


@pytest.mark.parametrize(
    "value",
    ["2026-10-16T00:00:00", "1700000000", "16-10-2026", "2026-1-6", "2026-02-30", "", "٢٠٢٦-١٠-١٦"],  # noqa: RUF001
)
def test_anything_but_yyyy_mm_dd_is_refused(value: str) -> None:
    with pytest.raises(ValidationError):
        query_date.validate_python(value)


def test_bk12_bk27_slots_serialise_in_utc_with_z_and_remaining() -> None:
    availability = AvailabilityRead(
        shop_id=uuid.uuid4(),
        date=date(2026, 10, 16),
        timezone="Asia/Karachi",
        slot_duration_minutes=60,
        slots=[
            SlotRead(
                slot_start=datetime(2026, 10, 16, 5, tzinfo=UTC),
                slot_end=datetime(2026, 10, 16, 6, tzinfo=UTC),
                remaining=2,
            )
        ],
    )
    body = availability.model_dump(mode="json")
    assert body["date"] == "2026-10-16"
    assert body["slots"] == [
        {"slot_start": "2026-10-16T05:00:00Z", "slot_end": "2026-10-16T06:00:00Z", "remaining": 2}
    ]
    assert "available" not in body["slots"][0]  # free places are `remaining` (D68)
    start = datetime(2026, 10, 16, 5, tzinfo=UTC)
    with pytest.raises(ValidationError):
        SlotRead(slot_start=start, slot_end=start, remaining=0)  # never 0 or negative

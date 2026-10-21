"""Schemas of the scheduling module (spec 03 §3.2, §4.5; `modules/scheduling.md` §4).

`SlotRead` and `AvailabilityRead` (free places in a slot are called `remaining`, never "available",
D68); `QueryDate`, the strict `YYYY-MM-DD` type of the availability `date` query parameter.
"""

import datetime as dt
import re
import uuid
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from app.shared.timestamps import Timestamp

DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
_DATE = re.compile(DATE_PATTERN)


def _strict_iso_date(value: object) -> object:
    """Only `YYYY-MM-DD` (Pydantic alone would also take a datetime string or a timestamp)."""
    if isinstance(value, str) and not _DATE.fullmatch(value):
        msg = "Use the YYYY-MM-DD format."
        raise ValueError(msg)
    return value


QueryDate = Annotated[dt.date, BeforeValidator(_strict_iso_date)]
"""A calendar date `YYYY-MM-DD` (spec 03 §1.5); for availability it is a date in the shop's
timezone."""


class SlotRead(BaseModel):
    """A bookable slot: timestamps in UTC with `Z`; `remaining` = capacity - booked, at least 1."""

    slot_start: Timestamp
    slot_end: Timestamp
    remaining: int = Field(ge=1)


class AvailabilityRead(BaseModel):
    """The free slots of one shop-local date, ordered by `slot_start` (D37)."""

    shop_id: uuid.UUID
    date: dt.date
    timezone: str
    slot_duration_minutes: int
    slots: list[SlotRead]

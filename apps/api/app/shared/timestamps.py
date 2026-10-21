"""Timestamps on the wire (glossary §9, spec 03 §1.5, D38).

Responses: UTC ISO 8601 with `Z`; milliseconds only when non-zero (`"2026-10-16T05:00:00Z"`,
`"2026-10-16T05:00:00.123Z"`); microseconds are dropped (Pydantic alone would print six digits).
Requests must carry `Z` or an offset: naive values are rejected (422).
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, PlainSerializer


def to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def format_timestamp(value: datetime) -> str:
    """`2026-10-16T05:00:00Z`, or `…:00.123Z` when the milliseconds are not zero."""
    moment = to_utc(value)
    base = moment.strftime("%Y-%m-%dT%H:%M:%S")
    milliseconds = moment.microsecond // 1000
    return f"{base}.{milliseconds:03d}Z" if milliseconds else f"{base}Z"


Timestamp = Annotated[
    AwareDatetime,
    AfterValidator(to_utc),
    PlainSerializer(format_timestamp, return_type=str, when_used="json"),
]
"""A timezone-aware instant, normalised to UTC; serialised as ISO 8601 with `Z`."""

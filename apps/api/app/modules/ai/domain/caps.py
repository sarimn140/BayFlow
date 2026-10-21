"""Per-shop usage caps for text AI (spec 13 principle 5, D103). Windows are UTC days and months.

Soft caps: two calls racing at the limit may both pass; the next one is refused.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Usage:
    today: int
    this_month: int


def day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def month_start(now: datetime) -> datetime:
    return day_start(now).replace(day=1)


def cap_reached(usage: Usage, *, daily_cap: int, monthly_cap: int) -> bool:
    return usage.today >= daily_cap or usage.this_month >= monthly_cap

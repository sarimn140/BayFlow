"""Shop-local days for the platform overview (spec 19 §4 E-61; D38, D63). Pure: "now" and the
time zone are passed in.

"The last N days" is the N local dates ending today, as N + 1 local midnights converted to UTC:
`bounds[0]` is the first instant of the oldest date and `bounds[-1]` the first instant of
tomorrow. Each midnight is converted on its own, so a DST day of 23 or 25 hours stays exact.
"""

import datetime as dt


def local_midnight(day: dt.date, zone: dt.tzinfo) -> dt.datetime:
    """The first instant of the local date `day` in `zone`, as an aware UTC datetime."""
    return dt.datetime.combine(day, dt.time.min, tzinfo=zone).astimezone(dt.UTC)


def last_days(now: dt.datetime, zone: dt.tzinfo, days: int) -> tuple[dt.date, list[dt.datetime]]:
    """Today's local date and the `days + 1` UTC bounds of the last `days` local dates."""
    if now.tzinfo is None or now.utcoffset() is None:
        msg = "now must be timezone-aware"
        raise ValueError(msg)
    if days < 1:
        msg = "days must be at least 1"
        raise ValueError(msg)
    today = now.astimezone(zone).date()
    first = today - dt.timedelta(days=days - 1)
    bounds = [local_midnight(first + dt.timedelta(days=offset), zone) for offset in range(days + 1)]
    return today, bounds

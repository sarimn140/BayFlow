"""Pure rules of the call lifecycle (spec 05 §3, `modules/calls.md` "Domain rules").

No I/O and no clock: callers pass `now`. The service locks the `call_logs` row, asks these
functions, then writes.
"""

import math
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from app.shared.enums import AiLegStatus, CallDirection, CallStatus, MissedReason


@dataclass(frozen=True, slots=True)
class AiLeg:
    """The `ai_*` timestamps of a call; `AiLegStatus` is derived from them, never stored."""

    dispatched_at: datetime | None
    answered_at: datetime | None
    ended_at: datetime | None
    error: str | None


def ai_leg_status(leg: AiLeg) -> AiLegStatus:
    if leg.dispatched_at is None:
        return AiLegStatus.NONE
    if leg.ended_at is not None:
        return AiLegStatus.FAILED if leg.error else AiLegStatus.ENDED
    if leg.answered_at is None:
        return AiLegStatus.CONNECTING
    return AiLegStatus.ACTIVE


def ai_leg_open(leg: AiLeg) -> bool:
    return leg.dispatched_at is not None and leg.ended_at is None


def ring_set(
    *,
    eligible: Iterable[uuid.UUID],
    online: Iterable[uuid.UUID],
    busy: Iterable[uuid.UUID],
    caller: uuid.UUID,
) -> list[uuid.UUID]:
    """§3.3: eligible callees with an open socket, minus anyone in a connected call and the caller.

    Sorted, so `rung_user_ids` is deterministic."""
    excluded = set(busy) | {caller}
    online_set = set(online)
    return sorted(user for user in set(eligible) if user in online_set and user not in excluded)


def every_rung_declined(rung: Iterable[uuid.UUID], declined: Iterable[uuid.UUID]) -> bool:
    """C3 ends the call only when the rung set is non-empty and fully declined (D77)."""
    rung_set = set(rung)
    return bool(rung_set) and rung_set <= set(declined)


def dispatches_ai(direction: CallDirection, reason: MissedReason) -> bool:
    """A1 follows a C2S call missed by timeout or by every rung callee declining; never C5."""
    return direction is CallDirection.CUSTOMER_TO_SHOP and reason in {
        MissedReason.NO_ANSWER,
        MissedReason.DECLINED,
    }


def seconds_between(start: datetime, end: datetime) -> int:
    return max(0, round((end - start).total_seconds()))


@dataclass(frozen=True, slots=True)
class UsageRow:
    """What the monthly cap counts for one call (§11.3)."""

    status: CallStatus
    started_at: datetime
    answered_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    ai_duration_seconds: int | None


def participant_minutes(rows: Iterable[UsageRow], *, now: datetime) -> int:
    """Ringing seconds x 1 (the caller alone) + talk x 2 + AI leg x 2, rounded up to minutes.

    Assumes the self-hosted agent counts as a participant (spec 05 §11.1)."""
    seconds = 0
    for row in rows:
        ring_end = row.answered_at or row.ended_at or now
        seconds += seconds_between(row.started_at, ring_end)
        seconds += 2 * (row.duration_seconds or 0)
        seconds += 2 * (row.ai_duration_seconds or 0)
    return math.ceil(seconds / 60)

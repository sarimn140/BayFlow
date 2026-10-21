"""Domain events of the calls module (spec 01 catalogue, `modules/calls.md` "Events").

Published inside the call's transaction; the notifications module writes `CALL_MISSED` /
`AI_TASK_CREATED` rows in the same transaction and pushes after the commit.
"""

import uuid
from dataclasses import dataclass, field

from app.shared.enums import AiLegStatus, CallDirection, CallStatus, MissedReason, TaskKind
from app.shared.event_bus import Event


@dataclass(frozen=True, slots=True, kw_only=True)
class CallStateChanged(Event):
    """C1-C6 and the AI-leg changes A1-A4 (A1 shares one event with its C3/C4)."""

    shop_id: uuid.UUID
    call_id: uuid.UUID
    booking_id: uuid.UUID
    direction: CallDirection
    previous_status: CallStatus | None
    status: CallStatus
    missed_reason: MissedReason | None
    ai_status: AiLegStatus
    caller_user_id: uuid.UUID
    customer_user_id: uuid.UUID
    answered_by_user_id: uuid.UUID | None
    rung_user_ids: tuple[uuid.UUID, ...] = field(default=())


@dataclass(frozen=True, slots=True, kw_only=True)
class AiTaskCreated(Event):
    """A new task (never an update of an existing one)."""

    shop_id: uuid.UUID
    task_id: uuid.UUID
    call_id: uuid.UUID
    booking_id: uuid.UUID
    booking_reference: str
    kind: TaskKind
    title: str
    is_urgent: bool

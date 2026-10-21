"""Request and response models of the calls module (spec 05 §5.3, §6.3, §8.3; spec 03 §3.8).

No call or task object ever carries a phone number or an e-mail address (brief §8.1, CALL-14).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.shared.enums import (
    AiLegStatus,
    CallDirection,
    CallIntent,
    CallStatus,
    IdentityMethod,
    MissedReason,
    Sentiment,
    TaskKind,
    TaskStatus,
)
from app.shared.money import Money
from app.shared.timestamps import Timestamp

Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


# --- Public views (spec 05 §8.3) -----------------------------------------------------------------


class Party(BaseModel):
    user_id: uuid.UUID
    display_name: str


class AiLegRead(BaseModel):
    status: AiLegStatus
    answered_at: Timestamp | None
    ended_at: Timestamp | None
    duration_seconds: int | None


class CallRead(BaseModel):
    id: uuid.UUID
    shop_id: uuid.UUID
    shop_name: str
    booking_id: uuid.UUID
    booking_reference: str
    vehicle_label: str
    direction: CallDirection
    status: CallStatus
    missed_reason: MissedReason | None
    caller: Party
    callee_label: str = Field(description="The shop's name (C2S) or the customer's name (S2C).")
    answered_by: Party | None
    rung_count: int
    started_at: Timestamp
    ring_deadline: Timestamp
    answered_at: Timestamp | None
    ended_at: Timestamp | None
    duration_seconds: int | None
    ai: AiLegRead | None


class StaffCallRead(CallRead):
    """Staff lists and detail add these (D21)."""

    has_summary: bool
    open_task_count: int


class CallConnection(BaseModel):
    url: str
    room: str
    token: str = Field(description="A LiveKit join token for this user and room (2-minute TTL).")
    identity: str
    expires_at: Timestamp


class CallStartRead(BaseModel):
    call: CallRead
    connection: CallConnection


class TranscriptEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: Literal["customer", "assistant", "tool_call", "tool_result"]
    text: Annotated[str, StringConstraints(max_length=8000)] = ""
    at: datetime | None = None
    tool: Annotated[str, StringConstraints(max_length=64)] | None = None
    interrupted: bool | None = None
    is_error: bool | None = None


class SummaryRead(BaseModel):
    intent: str
    intent_category: CallIntent
    details: str
    sentiment: Sentiment
    is_urgent: bool
    language: str
    is_fallback: bool
    transcript: list[TranscriptEntry]
    created_at: Timestamp


class TaskSummary(BaseModel):
    intent: str
    intent_category: CallIntent
    sentiment: Sentiment
    is_fallback: bool


class TaskRead(BaseModel):
    id: uuid.UUID
    shop_id: uuid.UUID
    booking_id: uuid.UUID | None
    booking_reference: str | None
    call_id: uuid.UUID | None
    customer: Party | None
    kind: TaskKind
    title: str
    description: str | None
    is_urgent: bool
    status: TaskStatus
    metadata: dict[str, Any]
    created_at: Timestamp
    done_at: Timestamp | None
    done_by: Party | None
    done_note: str | None
    summary: TaskSummary | None


class CallDetailRead(StaffCallRead):
    identity_method: IdentityMethod | None
    summary: SummaryRead | None
    tasks: list[TaskRead]


class TaskMarkDone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Note | None = None


# --- Internal (agent) contracts (spec 05 §5.3, §6.3) ---------------------------------------------


class AgentShopBrief(BaseModel):
    name: str
    city: str
    timezone: str


class SessionStartRead(BaseModel):
    shop: AgentShopBrief
    max_ai_seconds: int


class VerifyCallerRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")  # ids the agent might add are ignored (§5.1)

    name: ShortText | None = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=254)] | None = None
    booking_reference: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None
    ) = None

    @model_validator(mode="after")
    def _at_least_one(self) -> Self:
        if not any((self.name, self.phone, self.email, self.booking_reference)):
            msg = "give at least one of name, phone, email or booking_reference"
            raise ValueError(msg)
        return self


class VerifyCallerRead(BaseModel):
    verified: bool
    method: IdentityMethod | None
    attempts_left: int
    locked: bool
    first_name: str | None = None
    call_booking_reference: str | None = None


class AgentHours(BaseModel):
    weekday: str
    open: str | None
    close: str | None


class AgentShopRead(BaseModel):
    name: str
    city: str
    address: str
    phone: str
    working_hours: list[AgentHours]
    services: list[str]


class AgentEstimateBrief(BaseModel):
    version: int
    status: str
    grand_total: Money
    currency: Literal["PKR"] = "PKR"


class AgentBookingItem(BaseModel):
    reference: str
    vehicle: str
    status: str
    status_label: str
    appointment_local: str
    is_call_booking: bool


class AgentBookingList(BaseModel):
    items: list[AgentBookingItem]
    total: int


class AgentBookingRead(AgentBookingItem):
    services: list[str]
    is_ready_for_pickup: bool
    customer_actions: list[str]
    last_update_local: str
    estimate: AgentEstimateBrief | None


class AgentEstimateLine(BaseModel):
    type: str
    description: str
    quantity: Decimal
    line_total: Money


class AgentEstimateRead(BaseModel):
    reference: str
    has_estimate: bool
    version: int | None = None
    status: str | None = None
    lines: list[AgentEstimateLine] = Field(default_factory=list)
    parts_total: Money | None = None
    labour_total: Money | None = None
    grand_total: Money | None = None
    currency: Literal["PKR"] = "PKR"
    revision_in_progress: bool = False


class AgentSlot(BaseModel):
    start: Timestamp
    start_local: str


class AgentSlotsRead(BaseModel):
    timezone: str
    slots: list[AgentSlot]


class AgentTaskCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal[TaskKind.CALLBACK, TaskKind.RESCHEDULE_REQUEST, TaskKind.ESCALATION]
    booking_reference: Annotated[str, StringConstraints(max_length=20)] | None = None
    topic: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None
    description: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None
    ) = None
    preferred_starts: Annotated[list[datetime], Field(max_length=3)] | None = None
    safety_concern: bool = False


class AgentTaskRead(BaseModel):
    task_id: uuid.UUID
    created: bool


class AgentEndRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class AgentSummaryIn(BaseModel):
    """The agent's summary; validated by the API's own limits (§6.3 step 4)."""

    intent: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    intent_category: CallIntent
    details: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    sentiment: Sentiment
    follow_up_task_title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
    ]
    urgent: bool
    language: Literal["en", "ur", "mixed"]


class SummaryPost(BaseModel):
    model_config = ConfigDict(extra="ignore")

    transcript: list[TranscriptEntry] = Field(default_factory=list)
    summary: dict[str, Any] | None = None
    summary_error: Annotated[str, StringConstraints(max_length=500)] | None = None
    model: Annotated[str, StringConstraints(max_length=64)] | None = None


class SummaryStored(BaseModel):
    summary_id: uuid.UUID
    is_fallback: bool
    task_ids: list[uuid.UUID]

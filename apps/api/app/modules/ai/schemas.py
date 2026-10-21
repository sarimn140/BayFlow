"""Request and response models of the ai module (modules/ai.md "Endpoints", D103)."""

import json
import uuid
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.modules.identity.schemas import UserRef
from app.shared.enums import AiDraftStatus, AiFeature, AiSubjectType
from app.shared.timestamps import Timestamp

MAX_PAYLOAD_BYTES = 64 * 1024

DecisionNote = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class AiDraftRead(BaseModel):
    """An AI draft and, once decided, who decided what (AI-41, AI-42)."""

    id: uuid.UUID
    feature: AiFeature
    status: AiDraftStatus
    subject_type: AiSubjectType
    subject_id: uuid.UUID
    payload: dict[str, Any] = Field(description="The model's output, exactly as generated.")
    final_payload: dict[str, Any] | None = Field(
        description="What the person accepted: the payload, or their edit (`EDITED`)."
    )
    requested_by: UserRef
    decided_by: UserRef | None
    decided_at: Timestamp | None
    decision_note: str | None
    created_at: Timestamp


class AiDraftAccept(BaseModel):
    """`POST …/ai/drafts/{draft_id}/accept`: omit `final_payload` to accept the draft as is."""

    model_config = ConfigDict(extra="forbid")

    final_payload: dict[str, Any] | None = None
    note: DecisionNote | None = None

    @field_validator("final_payload")
    @classmethod
    def _bounded(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None and len(json.dumps(value).encode()) > MAX_PAYLOAD_BYTES:
            msg = f"final_payload must be at most {MAX_PAYLOAD_BYTES // 1024} KiB of JSON"
            raise ValueError(msg)
        return value


class AiDraftReject(BaseModel):
    """`POST …/ai/drafts/{draft_id}/reject`."""

    model_config = ConfigDict(extra="forbid")

    note: DecisionNote | None = None


class AiUsageRead(BaseModel):
    """`GET …/ai/usage`: what AI costs this shop, against its caps (spec 13 principle 5)."""

    configured: bool = Field(description="A text-AI provider is configured (a key is set).")
    provider: str
    model: str
    enabled_features: list[AiFeature]
    calls_today: int = Field(ge=0)
    calls_this_month: int = Field(ge=0)
    daily_cap: int = Field(ge=0)
    monthly_cap: int = Field(ge=0)

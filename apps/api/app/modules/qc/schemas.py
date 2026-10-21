"""Schemas of the qc module (spec 03 §3.6; `modules/qc.md` "Files").

Wire schemas (spec 03 §3.6): `QcChecklistTemplateItem`, `QcChecklistItemWrite` (request),
`QcChecklistItemRead`, `QcIssueRead`, `QcInspectionRead`. Bounded lists use the shared envelope
`app.shared.pagination.ItemList` (spec 03 §3.1). Actors are identity's `UserRef` (spec 03 §3.1),
defined once for every module.

Request field types for the bookings action bodies `PassQcRequest` / `FailQcRequest` (spec 03
§5.2), so the limits live next to the columns they protect: `QcChecklistWrite`, `QcNotes`,
`QcIssueTitle`, `QcIssueDescription`. Text is trimmed and blank optional text becomes `null`
(spec 03 §1.5); every request model forbids unknown fields (`extra="forbid"`, SEC-17).

Internal values, never on the wire: `QcSummary`, `FailRecorded`.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StringConstraints

from app.modules.identity.schemas import UserRef
from app.modules.qc.domain.checklist import CHECKLIST, ITEM_NOTE_MAX_LENGTH
from app.modules.qc.domain.rules import (
    ISSUE_DESCRIPTION_MAX_LENGTH,
    ISSUE_TITLE_MAX_LENGTH,
    NOTES_MAX_LENGTH,
)
from app.modules.qc.domain.rules import qc_round as derive_qc_round
from app.shared.enums import BookingStatus, QcChecklistKey, QcIssueStatus, QcResult
from app.shared.timestamps import Timestamp

# Arrays are bounded by the schemas (spec 03 §1.10). A checklist is exactly 5 items; up to 20 are
# accepted so that a repeated key is still answered with `checklist_incomplete` (spec 03 §3.6).
CHECKLIST_MAX_ITEMS = 20


def _blank_to_none(value: str | None) -> str | None:
    """After trimming, an empty optional text means "no value" (spec 03 §1.5)."""
    return value or None


# --- Request field types (embedded by bookings' PassQcRequest / FailQcRequest) --------------------

QcItemNote = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=ITEM_NOTE_MAX_LENGTH)]
    | None,
    AfterValidator(_blank_to_none),
]
"""A checklist item's note: optional, trimmed, at most 500 characters."""

QcNotes = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=NOTES_MAX_LENGTH)] | None,
    AfterValidator(_blank_to_none),
]
"""The inspection's free-text notes (`pass-qc` / `fail-qc` `notes`): optional, at most 2000."""

QcIssueTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ISSUE_TITLE_MAX_LENGTH)
]
"""`fail-qc` `issue_title`: required, trimmed, 1-120 characters."""

QcIssueDescription = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=ISSUE_DESCRIPTION_MAX_LENGTH),
]
"""`fail-qc` `issue_description`: required, trimmed, 1-2000 characters."""


class QcChecklistItemWrite(BaseModel):
    """One checklist item sent with `pass-qc` / `fail-qc` (request, spec 03 §3.6).

    `key` is typed `QcChecklistKey`, so an unknown key is a 422 `enum` at `checklist.N.key`
    before any service runs. `passed` must be a JSON boolean: the record says the inspector
    ticked (or did not tick) the item, so `1` or `"yes"` is refused (`bool_type`).
    """

    model_config = ConfigDict(extra="forbid")

    key: QcChecklistKey
    passed: StrictBool
    note: QcItemNote = None


QcChecklistWrite = Annotated[
    list[QcChecklistItemWrite],
    Field(
        max_length=CHECKLIST_MAX_ITEMS,
        description=(
            "The default checklist (D46): each of the five keys exactly once, in any order. "
            "A missing or repeated key is 422 `checklist_incomplete` (field `checklist`)."
        ),
    ),
]
"""The `checklist` field of `pass-qc` (required) and `fail-qc` (optional)."""


# --- Responses ------------------------------------------------------------------------------------


class QcChecklistTemplateItem(BaseModel):
    """One item of the default checklist, in D46 order (spec 03 §3.6)."""

    key: QcChecklistKey
    label: str


class QcChecklistItemRead(BaseModel):
    """A stored checklist item: the label as it was when the round was recorded (D46)."""

    key: QcChecklistKey
    label: str
    passed: bool
    note: str | None


class QcIssueRead(BaseModel):
    """An issue raised by a failed round; `RESOLVED` by the next `send-to-qc` (D47)."""

    id: uuid.UUID
    qc_inspection_id: uuid.UUID
    title: str
    description: str
    status: QcIssueStatus
    created_by: UserRef
    created_at: Timestamp
    resolved_at: Timestamp | None
    resolved_by: UserRef | None


class QcInspectionRead(BaseModel):
    """One QC round of a booking (spec 03 §3.6); `result` is `null` while in progress."""

    id: uuid.UUID
    round: Annotated[
        int, Field(ge=1, description="1-based position of the round, by (picked_at, id).")
    ]
    inspector: UserRef
    picked_at: Timestamp
    completed_at: Timestamp | None
    result: QcResult | None
    checklist: list[QcChecklistItemRead] | None
    notes: str | None
    issues: list[QcIssueRead]


def checklist_template() -> list[QcChecklistTemplateItem]:
    """The D46 template as wire items, in order."""
    return [QcChecklistTemplateItem(key=item.key, label=item.label) for item in CHECKLIST]


# --- Internal values (never on the wire) ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class QcSummary:
    """QC facts of one booking for its summary and detail (`get_qc_summaries`).

    `inspections` = its `qc_inspections` rows (rounds, any result); `open_issues` = its `OPEN`
    issues (spec 03 §3.3 `open_qc_issues_count`).
    """

    inspections: int
    open_issues: int

    def qc_round(self, status: BookingStatus) -> int:
        """Spec 03 §3.3 `qc_round` for a booking in `status`."""
        return derive_qc_round(self.inspections, status)


@dataclass(frozen=True, slots=True)
class FailRecorded:
    """What `record_fail` wrote: the `FAIL_QC` event metadata (spec 08)."""

    qc_inspection_id: uuid.UUID
    qc_issue_id: uuid.UUID

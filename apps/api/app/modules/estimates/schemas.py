"""Schemas of the estimates module (spec 03 §3.4, §5.3; `modules/estimates.md` §4, §7.4).

Requests: `EstimateUpdate` and `EstimateLineWrite` (the body of `PUT …/estimate`, served by
bookings). Responses: the staff view of a version (`EstimateRead`, whose part lines carry
inventory's `PartStockRef` with live stock, D40), the `PUT …/estimate` response
(`EstimateEditRead`), the customer projection (`CustomerEstimateRead`: no SKU, no stock, visible
statuses only) and the summary used in booking lists. Internal: the values the service hands
back to bookings (`EstimateSnapshot`, `EstimateEdit`, `CustomerEstimateView`). Actors are
identity's `UserRef`. Money is `Money` (whole rupees, `"16100.00"` on the wire); an estimate
line's `quantity` is `Quantity` (`"1.50"` on the wire); timestamps are `Timestamp` (UTC, `Z`).
"""

from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StrictInt,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

from app.modules.estimates.domain.lines import (
    MAX_LINES,
    MIN_LINES,
    NUL_NOT_ALLOWED,
    PART_QUANTITY_MAX,
    LineInput,
    check_line_shape,
    contains_nul,
)
from app.modules.estimates.domain.totals import CENTS
from app.modules.estimates.domain.versions import CUSTOMER_VISIBLE_STATUSES
from app.modules.identity.schemas import UserRef
from app.modules.inventory.schemas import PartStockRef
from app.shared.enums import EstimateLineType, EstimateStatus
from app.shared.money import Money, format_decimal, format_money
from app.shared.timestamps import Timestamp

INSPECTION_NOTES_MAX_LENGTH = 4000


def _two_places(value: Decimal) -> Decimal:
    return value.quantize(CENTS)


def _format_quantity(value: Decimal) -> str:
    return format_decimal(value, 2)


Quantity = Annotated[
    Decimal,
    Field(gt=0, le=PART_QUANTITY_MAX, decimal_places=2, examples=["1.00"]),
    AfterValidator(_two_places),
    PlainSerializer(_format_quantity, return_type=str, when_used="json"),
]
"""An estimate-line quantity: a string or number with at most two decimals in requests, a
two-place decimal string in responses (`"1.00"`, `"1.50"`; glossary §9). Booleans, NaN and
infinities are rejected. The per-type ranges (`PART` 1-9 999 whole, `LABOUR` 0.01-999.99) are
checked by `EstimateLineWrite`."""


def _customer_visible(status: EstimateStatus) -> EstimateStatus:
    if status not in CUSTOMER_VISIBLE_STATUSES:
        msg = "customers only ever see SENT, APPROVED or REJECTED estimate versions"
        raise ValueError(msg)
    return status


CustomerVisibleStatus = Annotated[EstimateStatus, AfterValidator(_customer_visible)]
"""`SENT`, `APPROVED` or `REJECTED`: building a customer projection of any other version fails
loudly instead of leaking a draft (D39, SEC-12)."""


def _blank_to_none(value: str | None) -> str | None:
    """After trimming, an empty optional text means "no value" (spec 03 §1.5)."""
    return value or None


InspectionNotes = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=INSPECTION_NOTES_MAX_LENGTH)]
    | None,
    AfterValidator(_blank_to_none),
]
"""The technician's inspection notes: optional, trimmed, at most 4000 characters; blank (`"   "`,
`"\\xa0"`) is `None`, the same as leaving the field out."""


def _event_ref(estimate_id: UUID, version: int) -> dict[str, object]:
    return {"estimate_id": str(estimate_id), "version": version}


def _event_metadata(estimate_id: UUID, version: int, grand_total: Decimal) -> dict[str, object]:
    return {**_event_ref(estimate_id, version), "grand_total": format_money(grand_total)}


# --- Requests (spec 03 §5.3) ----------------------------------------------------------------------


class EstimateLineWrite(BaseModel):
    """One line of `PUT …/estimate`: a catalogue `PART` or a free-text `LABOUR` line (D40).

    `PART`: `part_id` (an active part of this shop, checked by the service), whole `quantity`
    1-9 999, optional whole-rupee `unit_price` (defaults to the part's `unit_cost`); no
    `description` (the server stores the catalogue name). `LABOUR`: `description` 1-255 (trimmed),
    `quantity` 0.01-999.99, required `unit_price`; no `part_id`. Client totals are refused
    (`extra_forbidden`). Every broken rule of the line is reported on its own field with the
    spec 03 §2.3 code (`missing`, `not_allowed`, `not_whole_rupees`, `value_error`, …).
    """

    model_config = ConfigDict(extra="forbid")

    line_type: EstimateLineType
    part_id: UUID | None = None
    description: str | None = None
    quantity: Quantity
    unit_price: Money | None = None

    @field_validator("description")
    @classmethod
    def _trim_description(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def _check_line_type_rules(self) -> Self:
        problems = check_line_shape(self.to_line_input())
        if problems:
            details: list[InitErrorDetails] = [
                {
                    "type": PydanticCustomError(problem.code, problem.message),
                    "loc": (problem.field,),
                    "input": getattr(self, problem.field),
                }
                for problem in problems
            ]
            # Raised from a model validator, the errors keep their own field and the line's
            # position: the 422 names `lines.N.part_id`, not just `lines.N`.
            raise ValidationError.from_exception_data(type(self).__name__, details)
        return self

    def to_line_input(self) -> LineInput:
        return LineInput(
            line_type=self.line_type,
            part_id=self.part_id,
            description=self.description,
            quantity=self.quantity,
            unit_price=self.unit_price,
        )


class EstimateUpdate(BaseModel):
    """Body of `PUT /api/v1/shops/{shop_id}/bookings/{booking_id}/estimate` (O1).

    `lines` is the full new list in display order (1-50). `inspection_notes` (≤ 4000, trimmed,
    blank -> `None`) and `expected_version` are consumed by bookings: the notes are the
    technician's, saved on the booking while `INSPECTING` (D40); the version check is D30's.
    """

    model_config = ConfigDict(extra="forbid")

    lines: list[EstimateLineWrite] = Field(min_length=MIN_LINES, max_length=MAX_LINES)
    inspection_notes: InspectionNotes = None
    expected_version: StrictInt | None = Field(default=None, ge=1)  # strict, like the action bodies

    @field_validator("inspection_notes")
    @classmethod
    def _no_nul_in_notes(cls, value: str | None) -> str | None:
        if value is not None and contains_nul(value):
            raise ValueError(NUL_NOT_ALLOWED)
        return value


# --- Responses (spec 03 §3.3-§3.4) ----------------------------------------------------------------


class EstimateSummary(BaseModel):
    """`estimate_summary` of booking lists and details: staff get the latest version, customers
    the latest `SENT`, `APPROVED` or `REJECTED` one (D39)."""

    estimate_id: UUID
    version: int
    status: EstimateStatus
    grand_total: Money
    line_count: int


class EstimateLineRead(BaseModel):
    """A line as staff see it. `part` is the catalogue part with **live** stock, read when the
    response is built (D40, EST-18): its stock fields are null for QC inspectors (spec 04 §B) and
    `part` is null on `LABOUR` lines. On `PART` lines `description` is the catalogue name copied
    when the line was saved, so a frozen version never changes when the catalogue does (EST-23)."""

    id: UUID
    position: int
    line_type: EstimateLineType
    part: PartStockRef | None
    description: str
    quantity: Quantity
    unit_price: Money
    line_total: Money


class EstimateRead(BaseModel):
    """One estimate version, staff view (`GET …/estimates`; spec 03 §3.4)."""

    id: UUID
    booking_id: UUID
    version: int
    status: EstimateStatus
    lines: list[EstimateLineRead]
    parts_total: Money
    labour_total: Money
    grand_total: Money
    created_by: UserRef
    created_at: Timestamp
    submitted_at: Timestamp | None
    sent_at: Timestamp | None
    sent_by: UserRef | None
    decided_at: Timestamp | None
    decided_by: UserRef | None
    customer_note: str | None


class EstimateEdit(BaseModel):
    """What `replace_lines` returns to bookings: the edited version (with live stock) and whether
    the save created it (`created_new_version` -> one `EDIT_ESTIMATE` event and a booking version
    bump; a plain draft save writes no event, D30)."""

    model_config = ConfigDict(frozen=True)

    estimate: EstimateRead
    created_new_version: bool

    def event_metadata(self) -> dict[str, object]:
        """`EDIT_ESTIMATE` event metadata (spec 03 §5.3):
        `{"estimate_id": "<uuid>", "version": 2, "grand_total": "16100.00"}`."""
        return _event_metadata(self.estimate.id, self.estimate.version, self.estimate.grand_total)


class EstimateEditRead(EstimateRead):
    """`PUT …/estimate` response (spec 03 §5.3): the editable version with live part stock, the
    booking's `version` after the save (for the next `expected_version`) and
    `created_new_version`."""

    booking_version: int
    created_new_version: bool

    @classmethod
    def from_edit(cls, edit: EstimateEdit, *, booking_version: int) -> Self:
        return cls.model_validate(
            {
                **edit.estimate.model_dump(),
                "booking_version": booking_version,
                "created_new_version": edit.created_new_version,
            }
        )


class CustomerEstimateLineRead(BaseModel):
    """A line as the customer sees it: no SKU, no stock (spec 04 §C)."""

    id: UUID
    position: int
    line_type: EstimateLineType
    description: str
    quantity: Quantity
    unit_price: Money
    line_total: Money


class CustomerEstimateRead(BaseModel):
    """A customer-visible version (`SENT`, `APPROVED` or `REJECTED` only; D39)."""

    id: UUID
    version: int
    status: CustomerVisibleStatus
    lines: list[CustomerEstimateLineRead]
    parts_total: Money
    labour_total: Money
    grand_total: Money
    sent_at: Timestamp
    decided_at: Timestamp | None
    customer_note: str | None


# --- Internal values returned to bookings ---------------------------------------------------------


class EstimateSnapshot(BaseModel):
    """The version an action created or changed (`modules/estimates.md` §5), from which bookings
    builds the booking event's metadata (spec 08; `modules/bookings.md` §7.6)."""

    model_config = ConfigDict(frozen=True)

    estimate_id: UUID
    version: int
    status: EstimateStatus
    grand_total: Money

    def event_metadata(self) -> dict[str, object]:
        """`SUBMIT_ESTIMATE`, `SEND_ESTIMATE`, `APPROVE_ESTIMATE`, `REJECT_ESTIMATE`:
        `{"estimate_id": "<uuid>", "version": 2, "grand_total": "16100.00"}` (JSON values)."""
        return _event_metadata(self.estimate_id, self.version, self.grand_total)

    def event_ref(self) -> dict[str, object]:
        """`START_INSPECTION`, `REVISE_ESTIMATE`, `RETURN_TO_TECHNICIAN`:
        `{"estimate_id": "<uuid>", "version": 3}` (JSON values)."""
        return _event_ref(self.estimate_id, self.version)


class CustomerEstimateView(BaseModel):
    """What the customer's booking detail shows (§7.7): the latest visible version, and whether
    the shop is preparing a newer one (`estimate_revision_in_progress`)."""

    model_config = ConfigDict(frozen=True)

    estimate: CustomerEstimateRead | None
    revision_in_progress: bool

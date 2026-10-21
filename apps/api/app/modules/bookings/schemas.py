"""Request and response schemas of the bookings module (spec 03 §3.3, §4.6-§4.8, §5).

Requests forbid unknown fields (`extra="forbid"`): `status`, `customer_user_id`, `reference` or
`version` can never be smuggled into a booking (SEC-17), and a booking action body carries only
its own fields plus the optional `expected_version` (D30). Text is trimmed; blank optional text is
`null` (spec 03 §1.5). E-mails use the project `Email` type (D62), phones `Phone`, passwords the
D10 `Password` type, timestamps `Timestamp` (aware input, UTC `Z` output), money `Money`.

Responses follow the audiences of spec 04 §C: staff schemas (`BookingSummary`, `BookingDetail`,
`BookingEventRead`) and customer schemas (`CustomerBookingSummary`, `CustomerBookingDetail`,
`CustomerBookingEventRead`), which never carry staff names, internal notes, event metadata, stock
data or unsent estimate versions. Every staff and customer booking response carries the caller's
`allowed_actions`. The platform admin's cross-tenant projections (`AdminBookingSummary`,
`AdminBookingDetail`, spec 19 E-72/E-73) are read-only and carry none (D94).

The booking-scoped reads of other modules' data (spec 03 §1.11) are served by this module with
those modules' wire schemas, re-exported here for the router: `EstimateRead`, `EstimateUpdate`,
`EstimateEditRead`, `CustomerEstimateRead`, `BookingPartsRead`, `QcInspectionRead`, `QueryDate`.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Annotated, Any, Final, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

from app.core.security import Password
from app.modules.bookings.domain.vehicles import is_valid_registration_key, registration_key
from app.modules.estimates.schemas import (
    CustomerEstimateRead,
    EstimateEditRead,
    EstimateRead,
    EstimateSummary,
    EstimateUpdate,
    InspectionNotes,
)
from app.modules.identity.schemas import FullName, SessionToken, UserRef
from app.modules.inventory.schemas import (
    MAX_PURCHASE_ORDER_ITEMS,
    BookingPartsRead,
    OrderQuantity,
    PartsSummary,
    SupplierName,
)
from app.modules.qc.schemas import (
    QcChecklistWrite,
    QcInspectionRead,
    QcIssueDescription,
    QcIssueTitle,
    QcNotes,
)
from app.modules.scheduling.schemas import QueryDate
from app.modules.shops.schemas import MemberRef
from app.shared.email import Email
from app.shared.enums import ActorRole, BookingAction, BookingStatus
from app.shared.money import Money
from app.shared.phone import Phone
from app.shared.timestamps import Timestamp

__all__ = [
    "CUSTOMER_ACTION_REQUESTS",
    "SEARCH_MAX_LENGTH",
    "STAFF_ACTION_REQUESTS",
    "ActionRequest",
    "AdminBookingDetail",
    "AdminBookingFilters",
    "AdminBookingSort",
    "AdminBookingSummary",
    "AllocatePartsRequest",
    "ApproveEstimateRequest",
    "AssignPartsPersonRequest",
    "AssignTechnicianRequest",
    "BookingActionSlug",
    "BookingCreate",
    "BookingCreatedRead",
    "BookingCustomer",
    "BookingDetail",
    "BookingEventRead",
    "BookingPartsRead",
    "BookingServiceRead",
    "BookingShopRead",
    "BookingShopRef",
    "BookingSort",
    "BookingSummary",
    "CancelRequest",
    "CompleteRequest",
    "ConfirmRequest",
    "CustomerBookingDetail",
    "CustomerBookingEventRead",
    "CustomerBookingSort",
    "CustomerBookingSummary",
    "CustomerCancelRequest",
    "CustomerEstimateRead",
    "CustomerWrite",
    "DeclineRequest",
    "EstimateEditRead",
    "EstimateRead",
    "EstimateUpdate",
    "FailQcRequest",
    "MarkPartsReadyRequest",
    "NotifyReadyRequest",
    "OrderPartsItem",
    "OrderPartsRequest",
    "PassQcRequest",
    "PickQcRequest",
    "QcInspectionRead",
    "QueryDate",
    "ReassignPartsPersonRequest",
    "ReassignTechnicianRequest",
    "RejectEstimateRequest",
    "ReturnToTechnicianRequest",
    "ReviseEstimateRequest",
    "SendEstimateRequest",
    "SendToQcRequest",
    "StaffBookingFilters",
    "StartInspectionRequest",
    "StartRepairRequest",
    "StatusCount",
    "StatusCountsRead",
    "SubmitEstimateRequest",
    "VehicleBrief",
    "VehicleRead",
    "VehicleWrite",
]

REASON_MAX_LENGTH: Final = 500
NOTE_MAX_LENGTH: Final = 500
REPAIR_NOTES_MAX_LENGTH: Final = 2000
CUSTOMER_NOTES_MAX_LENGTH: Final = 2000
MAX_SERVICES_PER_BOOKING: Final = 10
SEARCH_MAX_LENGTH: Final = 100
YEAR_MIN: Final = 1900
YEAR_MAX: Final = 2100  # the static bound of `ck_vehicles_year`; the service also caps at Y+1
MILEAGE_MAX: Final = 2_000_000
REGISTRATION_MESSAGE: Final = (
    "Enter 2 to 20 letters and digits; spaces and hyphens are allowed (e.g. LEA-1234)."
)


def _blank_to_none(value: str | None) -> str | None:
    """After trimming, an empty optional text means "no value" (spec 03 §1.5)."""
    return value or None


ReasonText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX_LENGTH)
]
"""A required reason (decline, staff cancel): trimmed, 1-500 characters (T03, T22)."""

OptionalReason = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=REASON_MAX_LENGTH)] | None,
    AfterValidator(_blank_to_none),
]
"""An optional reason (customer cancel, reject): trimmed, at most 500 characters, blank → null."""

OptionalNote = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=NOTE_MAX_LENGTH)] | None,
    AfterValidator(_blank_to_none),
]
"""An optional staff note (confirm, return-to-technician): at most 500 characters, blank → null."""

RepairNotes = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=REPAIR_NOTES_MAX_LENGTH)]
    | None,
    AfterValidator(_blank_to_none),
]
"""`send-to-qc` notes, stored as the event note: at most 2000 characters, blank → null."""

CustomerNotes = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=CUSTOMER_NOTES_MAX_LENGTH)]
    | None,
    AfterValidator(_blank_to_none),
]
"""The wizard's free text (`bookings.customer_notes`): at most 2000 characters, blank → null."""

VehicleColor = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)] | None,
    AfterValidator(_blank_to_none),
]

ExpectedVersion = Annotated[int, Field(strict=True, ge=1)]
"""A JSON integer ≥ 1 (booleans and strings are refused)."""


def _check_registration(value: str) -> str:
    if not is_valid_registration_key(registration_key(value)):
        raise PydanticCustomError("value_error", REGISTRATION_MESSAGE)
    return value


RegistrationNumber = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=20),
    AfterValidator(_check_registration),
    Field(examples=["LEA-1234"]),
]
"""As typed and trimmed (`vehicles.registration_number`); its key must match `^[A-Z0-9]{2,20}$`
(`ck_vehicles_registration_key`), so only ASCII letters, digits, whitespace and hyphens pass."""


def _duplicate_errors(name: str, values: list[UUID], message: str) -> list[InitErrorDetails]:
    """`<name>.N` / `duplicate` for every repeated value after its first occurrence."""
    seen: set[UUID] = set()
    details: list[InitErrorDetails] = []
    for index, value in enumerate(values):
        if value in seen:
            details.append(
                {
                    "type": PydanticCustomError("duplicate", message),
                    "loc": (name, index),
                    "input": str(value),
                }
            )
        seen.add(value)
    return details


# --- Wire enums -----------------------------------------------------------------------------------


class BookingActionSlug(StrEnum):
    """The 25 lower-kebab action slugs of glossary §4 (spec 03 §3.9): the item type of
    `allowed_actions`. `CREATE` and `RECEIVE_PARTS` have no slug (their own endpoints)."""

    CONFIRM = "confirm"
    DECLINE = "decline"
    ASSIGN_TECHNICIAN = "assign-technician"
    START_INSPECTION = "start-inspection"
    EDIT_ESTIMATE = "edit-estimate"
    SUBMIT_ESTIMATE = "submit-estimate"
    SEND_ESTIMATE = "send-estimate"
    APPROVE_ESTIMATE = "approve-estimate"
    REJECT_ESTIMATE = "reject-estimate"
    REVISE_ESTIMATE = "revise-estimate"
    RETURN_TO_TECHNICIAN = "return-to-technician"
    ASSIGN_PARTS_PERSON = "assign-parts-person"
    ORDER_PARTS = "order-parts"
    MARK_PARTS_READY = "mark-parts-ready"
    ALLOCATE_PARTS = "allocate-parts"
    START_REPAIR = "start-repair"
    SEND_TO_QC = "send-to-qc"
    PICK_QC = "pick-qc"
    PASS_QC = "pass-qc"  # noqa: S105 - an action slug, not a password
    FAIL_QC = "fail-qc"
    NOTIFY_READY = "notify-ready"
    COMPLETE = "complete"
    CANCEL = "cancel"
    REASSIGN_TECHNICIAN = "reassign-technician"
    REASSIGN_PARTS_PERSON = "reassign-parts-person"


BookingSort = Literal[
    "slot_start",
    "-slot_start",
    "updated_at",
    "-updated_at",
    "status_changed_at",
    "-status_changed_at",
    "created_at",
    "-created_at",
]
"""`GET …/bookings?sort=` (spec 03 §4.8): ascending, or descending with `-`; default `-updated_at`;
the tie-breaker is always `id`."""

CustomerBookingSort = Literal["slot_start", "-slot_start", "-updated_at"]
"""`GET /api/v1/me/bookings?sort=`: default `slot_start` with `active=true`, else `-slot_start`."""


# --- Wizard (spec 03 §4.6, D32-D35, D65) ----------------------------------------------------------


class CustomerWrite(BaseModel):
    """The wizard's account fields. Optional in the schema: anonymous callers must send
    `full_name`, `email` and `password` (422 `customer.<field>` `missing`, checked by the
    service); with a session only `phone` is used, to fill an empty `users.phone` (D33)."""

    model_config = ConfigDict(extra="forbid")

    full_name: FullName | None = None
    email: Email | None = None
    password: Password | None = None
    phone: Phone | None = None


class VehicleWrite(BaseModel):
    """The customer's car (D35). `year` is 1900-2100 here; the service also refuses a year later
    than next year (422 `vehicle.year`). `mileage_km` is snapshotted on the booking (D65)."""

    model_config = ConfigDict(extra="forbid")

    registration_number: RegistrationNumber
    make: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    year: Annotated[int, Field(strict=True, ge=YEAR_MIN, le=YEAR_MAX)]
    color: VehicleColor = None
    mileage_km: Annotated[int, Field(strict=True, ge=0, le=MILEAGE_MAX)] | None = None

    @property
    def registration_key(self) -> str:
        """The normalised key the vehicle is matched on (`lea 1234` = `LEA-1234`)."""
        return registration_key(self.registration_number)


class BookingCreate(BaseModel):
    """`POST /api/v1/bookings` (T01). `shop_id` only selects where to book (D20)."""

    model_config = ConfigDict(extra="forbid")

    shop_id: UUID
    service_ids: Annotated[list[UUID], Field(min_length=1, max_length=MAX_SERVICES_PER_BOOKING)]
    slot_start: Timestamp = Field(description="A slot start of the shop's grid (UTC, `Z`).")
    customer_notes: CustomerNotes = None
    customer: CustomerWrite | None = None
    vehicle: VehicleWrite

    @model_validator(mode="after")
    def _distinct_services(self) -> Self:
        details = _duplicate_errors(
            "service_ids", self.service_ids, "Each service can be selected only once."
        )
        if details:
            raise ValidationError.from_exception_data(type(self).__name__, details)
        return self


# --- Booking action bodies (spec 03 §5.2) ---------------------------------------------------------


class ActionRequest(BaseModel):
    """What every booking action body accepts: `expected_version`, the booking `version` the
    client rendered (a mismatch is 409 `CONCURRENT_UPDATE`, checked after the status, D30)."""

    model_config = ConfigDict(extra="forbid")

    expected_version: ExpectedVersion | None = Field(
        default=None, description="The booking `version` the client rendered (D30)."
    )


class ConfirmRequest(ActionRequest):
    """`confirm` (T02); `note` is a staff-only event note."""

    note: OptionalNote = None


class DeclineRequest(ActionRequest):
    """`decline` (T03): the reason is required and shown to the customer."""

    reason: ReasonText


class AssignTechnicianRequest(ActionRequest):
    """`assign-technician` (T04): an active `TECHNICIAN` member of this shop."""

    technician_user_id: UUID


class StartInspectionRequest(ActionRequest):
    """`start-inspection` (T05)."""


class SubmitEstimateRequest(ActionRequest):
    """`submit-estimate` (T06): `inspection_notes` replace the booking's when sent."""

    inspection_notes: InspectionNotes = None


class SendEstimateRequest(ActionRequest):
    """`send-estimate` (T07)."""


class ApproveEstimateRequest(ActionRequest):
    """`approve-estimate` (T08, customer route): the current `SENT` version."""

    estimate_id: UUID


class RejectEstimateRequest(ActionRequest):
    """`reject-estimate` (T09, customer route): optional reason, shown to the shop."""

    estimate_id: UUID
    reason: OptionalReason = None


class ReviseEstimateRequest(ActionRequest):
    """`revise-estimate` (T10)."""


class ReturnToTechnicianRequest(ActionRequest):
    """`return-to-technician` (T11): `note` is shown to the technician."""

    note: OptionalNote = None


class AssignPartsPersonRequest(ActionRequest):
    """`assign-parts-person` (T12): an active `PARTS_PERSON` member of this shop."""

    parts_person_user_id: UUID


class OrderPartsItem(BaseModel):
    """One purchase-order line of `order-parts`."""

    model_config = ConfigDict(extra="forbid")

    part_id: UUID
    quantity: OrderQuantity


class OrderPartsRequest(ActionRequest):
    """`order-parts` (T13): `items` omitted → exactly the shortages; given → every short part,
    each once, at least its shortage (422 `missing_shortage` / `below_shortage` / `not_short`)."""

    supplier_name: SupplierName | None = None
    items: (
        Annotated[list[OrderPartsItem], Field(min_length=1, max_length=MAX_PURCHASE_ORDER_ITEMS)]
        | None
    ) = None

    @model_validator(mode="after")
    def _distinct_parts(self) -> Self:
        if self.items is None:
            return self
        details = _duplicate_errors(
            "items", [item.part_id for item in self.items], "Each part can be ordered only once."
        )
        for detail in details:  # the repeated value is the line's part_id
            detail["loc"] = (*detail["loc"], "part_id")
        if details:
            raise ValidationError.from_exception_data(type(self).__name__, details)
        return self


class MarkPartsReadyRequest(ActionRequest):
    """`mark-parts-ready` (T14)."""


class AllocatePartsRequest(ActionRequest):
    """`allocate-parts` (T16)."""


class StartRepairRequest(ActionRequest):
    """`start-repair` (O2)."""


class SendToQcRequest(ActionRequest):
    """`send-to-qc` (T17): `repair_notes` become the event note."""

    repair_notes: RepairNotes = None


class PickQcRequest(ActionRequest):
    """`pick-qc` (T18)."""


class PassQcRequest(ActionRequest):
    """`pass-qc` (T19): the D46 checklist, every item passed."""

    checklist: QcChecklistWrite
    notes: QcNotes = None


class FailQcRequest(ActionRequest):
    """`fail-qc` (T20): the issue; a checklist, when sent, carries each key once."""

    issue_title: QcIssueTitle
    issue_description: QcIssueDescription
    checklist: QcChecklistWrite | None = None
    notes: QcNotes = None


class NotifyReadyRequest(ActionRequest):
    """`notify-ready` (O3); repeatable (send `expected_version` to avoid duplicates)."""


class CompleteRequest(ActionRequest):
    """`complete` (T21), staff and customer routes."""


class CancelRequest(ActionRequest):
    """Staff `cancel` (T22): the reason is required and shown to the customer."""

    reason: ReasonText


class CustomerCancelRequest(ActionRequest):
    """Customer `cancel` (T22): the reason is optional."""

    reason: OptionalReason = None


class ReassignTechnicianRequest(ActionRequest):
    """`reassign-technician` (O4): an eligible technician other than the current one."""

    technician_user_id: UUID


class ReassignPartsPersonRequest(ActionRequest):
    """`reassign-parts-person` (O5): an eligible parts person other than the current one."""

    parts_person_user_id: UUID


STAFF_ACTION_REQUESTS: Final[dict[BookingAction, type[ActionRequest]]] = {
    BookingAction.CONFIRM: ConfirmRequest,
    BookingAction.DECLINE: DeclineRequest,
    BookingAction.ASSIGN_TECHNICIAN: AssignTechnicianRequest,
    BookingAction.START_INSPECTION: StartInspectionRequest,
    BookingAction.SUBMIT_ESTIMATE: SubmitEstimateRequest,
    BookingAction.SEND_ESTIMATE: SendEstimateRequest,
    BookingAction.REVISE_ESTIMATE: ReviseEstimateRequest,
    BookingAction.RETURN_TO_TECHNICIAN: ReturnToTechnicianRequest,
    BookingAction.ASSIGN_PARTS_PERSON: AssignPartsPersonRequest,
    BookingAction.ORDER_PARTS: OrderPartsRequest,
    BookingAction.MARK_PARTS_READY: MarkPartsReadyRequest,
    BookingAction.ALLOCATE_PARTS: AllocatePartsRequest,
    BookingAction.START_REPAIR: StartRepairRequest,
    BookingAction.SEND_TO_QC: SendToQcRequest,
    BookingAction.PICK_QC: PickQcRequest,
    BookingAction.PASS_QC: PassQcRequest,
    BookingAction.FAIL_QC: FailQcRequest,
    BookingAction.NOTIFY_READY: NotifyReadyRequest,
    BookingAction.COMPLETE: CompleteRequest,
    BookingAction.CANCEL: CancelRequest,
    BookingAction.REASSIGN_TECHNICIAN: ReassignTechnicianRequest,
    BookingAction.REASSIGN_PARTS_PERSON: ReassignPartsPersonRequest,
}
"""The body of each staff `POST …/actions/{slug}` route (`<PascalCaseSlug>Request`)."""

CUSTOMER_ACTION_REQUESTS: Final[dict[BookingAction, type[ActionRequest]]] = {
    BookingAction.APPROVE_ESTIMATE: ApproveEstimateRequest,
    BookingAction.REJECT_ESTIMATE: RejectEstimateRequest,
    BookingAction.COMPLETE: CompleteRequest,
    BookingAction.CANCEL: CustomerCancelRequest,
}
"""The body of each customer `POST /api/v1/me/bookings/{booking_id}/actions/{slug}` route."""


# --- Staff list filters ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StaffBookingFilters:
    """`GET …/bookings` filters (spec 03 §4.8). They narrow the caller's D21 set, never widen it.

    `q` matches the reference (with or without `BF-`), the vehicle's registration (normalised like
    the registration key) or the customer's name; `date_from` / `date_to` are inclusive
    shop-local dates on `slot_start`.
    """

    statuses: tuple[BookingStatus, ...] = ()
    q: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    technician_user_id: UUID | None = None
    parts_person_user_id: UUID | None = None


AdminBookingSort = Literal["-slot_start", "slot_start", "-created_at"]
"""E-72's sorts (spec 19 §4): latest slot first (default), earliest slot, newest booking first."""


@dataclass(frozen=True, slots=True)
class AdminBookingFilters:
    """The platform admin's booking filters across every tenant (spec 19 §4 E-72; D94).

    `q` matches the reference (with or without `BF-`), the plate (normalised) or the customer's
    name or e-mail; `date_from` / `date_to` are inclusive slot dates in each shop's own time zone
    (D38); `customer_user_id` lists one person's bookings (E-67).
    """

    q: str | None = None
    shop_id: UUID | None = None
    statuses: tuple[BookingStatus, ...] = ()
    date_from: date | None = None
    date_to: date | None = None
    customer_user_id: UUID | None = None


# --- Responses (spec 03 §3.3) ---------------------------------------------------------------------


class VehicleRead(BaseModel):
    """The vehicle as stored now (D35)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    registration_number: str
    make: str
    model: str
    year: int
    color: str | None
    mileage_km: int | None
    created_at: Timestamp
    updated_at: Timestamp


class VehicleBrief(BaseModel):
    """The vehicle in list items."""

    registration_number: str
    make: str
    model: str
    year: int


class BookingServiceRead(BaseModel):
    """A service as snapshotted at booking time (D34)."""

    service_id: UUID
    name: str
    base_price: Money | None


class BookingCustomer(BaseModel):
    """The customer on the staff detail: `email` and `phone` are `null` unless the caller is the
    shop's `OWNER` or a `SERVICE_ADVISOR` (spec 04 §C)."""

    user_id: UUID
    full_name: str
    email: str | None
    phone: str | None


class BookingShopRef(BaseModel):
    """The shop on a customer's list item."""

    id: UUID
    slug: str
    name: str
    city: str
    phone: str
    timezone: str


class BookingShopRead(BookingShopRef):
    """The shop on a customer's booking detail."""

    address: str


class BookingEventRead(BaseModel):
    """One audit-log row as staff see it: actor, role, note and metadata (spec 08)."""

    id: UUID
    action: BookingAction
    from_status: BookingStatus | None
    to_status: BookingStatus
    actor: UserRef | None
    actor_role: ActorRole
    note: str | None
    metadata: dict[str, Any]
    created_at: Timestamp


class CustomerBookingEventRead(BaseModel):
    """One timeline row as the customer sees it (spec 03 §3.3 projection): no actor, role or
    metadata; a note only for a decline, cancel or reject reason."""

    id: UUID
    action: BookingAction
    from_status: BookingStatus | None
    to_status: BookingStatus
    by_customer: bool
    note: str | None
    created_at: Timestamp


class BookingSummary(BaseModel):
    """A staff list item (spec 03 §3.3)."""

    id: UUID
    shop_id: UUID
    reference: str
    status: BookingStatus
    version: int
    slot_start: Timestamp
    slot_end: Timestamp
    status_changed_at: Timestamp
    customer: UserRef
    vehicle: VehicleBrief
    service_names: list[str]
    technician: MemberRef | None
    parts_person: MemberRef | None
    qc_inspector: MemberRef | None
    estimate_summary: EstimateSummary | None
    parts_summary: PartsSummary | None
    open_qc_issues_count: int
    qc_round: int
    repair_started_at: Timestamp | None
    allowed_actions: list[BookingActionSlug]
    created_at: Timestamp
    updated_at: Timestamp


class BookingDetailBase(BaseModel):
    """The staff projection of one booking without `allowed_actions` and timestamps: shared by the
    staff detail and the platform admin's read-only detail (spec 19 E-73)."""

    id: UUID
    shop_id: UUID
    reference: str
    status: BookingStatus
    version: int
    slot_start: Timestamp
    slot_end: Timestamp
    status_changed_at: Timestamp
    customer: BookingCustomer
    vehicle: VehicleRead
    mileage_km: int | None = Field(description="The mileage given at booking time (D65).")
    services: list[BookingServiceRead]
    customer_notes: str | None
    inspection_notes: str | None
    technician: MemberRef | None
    parts_person: MemberRef | None
    qc_inspector: MemberRef | None
    estimate_summary: EstimateSummary | None
    parts_summary: PartsSummary | None
    open_qc_issues_count: int
    qc_round: int
    repair_started_at: Timestamp | None
    ready_notified_at: Timestamp | None
    completed_at: Timestamp | None
    cancelled_at: Timestamp | None
    cancelled_by: UserRef | None
    cancel_reason: str | None
    last_event: BookingEventRead | None


class BookingDetail(BookingDetailBase):
    """The staff detail and every staff action response (spec 03 §3.3)."""

    allowed_actions: list[BookingActionSlug]
    created_at: Timestamp
    updated_at: Timestamp


class AdminBookingDetail(BookingDetailBase):
    """E-73 (spec 19 §4): the staff projection of any tenant's booking with its full timeline.
    Read-only: no `allowed_actions` (no admin edits a tenant's booking, D94); the customer's
    contact details and the parts summary are always shown."""

    created_at: Timestamp
    updated_at: Timestamp
    shop: BookingShopRef
    events: list[BookingEventRead]


class AdminBookingSummary(BaseModel):
    """An E-72 list item (spec 19 §4): any tenant's booking, read-only."""

    id: UUID
    reference: str
    shop: BookingShopRef
    status: BookingStatus
    version: int
    slot_start: Timestamp
    slot_end: Timestamp
    customer: BookingCustomer
    vehicle: VehicleBrief
    service_names: list[str]
    created_at: Timestamp
    updated_at: Timestamp


class CustomerBookingSummary(BaseModel):
    """A customer's list item (spec 03 §3.3)."""

    id: UUID
    reference: str
    status: BookingStatus
    version: int
    slot_start: Timestamp
    slot_end: Timestamp
    status_changed_at: Timestamp
    shop: BookingShopRef
    vehicle: VehicleBrief
    service_names: list[str]
    estimate_summary: EstimateSummary | None
    allowed_actions: list[BookingActionSlug]
    created_at: Timestamp
    updated_at: Timestamp


class BookingLabel(BaseModel):
    """P2 (`modules/bookings.md` §5.3): what call lists show about a booking, batched."""

    model_config = ConfigDict(frozen=True)

    reference: str
    vehicle_label: str = Field(description='e.g. "2016 Honda Civic (LEA-1234)".')
    customer_user_id: UUID


class CustomerBookingDetail(BaseModel):
    """The customer detail and every customer action response (spec 03 §3.3): no staff names,
    internal notes, stock or event metadata (spec 04 §C)."""

    id: UUID
    reference: str
    status: BookingStatus
    version: int
    slot_start: Timestamp
    slot_end: Timestamp
    status_changed_at: Timestamp
    shop: BookingShopRead
    vehicle: VehicleRead
    mileage_km: int | None
    services: list[BookingServiceRead]
    customer_notes: str | None
    estimate: CustomerEstimateRead | None
    estimate_revision_in_progress: bool
    allowed_actions: list[BookingActionSlug]
    ready_notified_at: Timestamp | None
    completed_at: Timestamp | None
    cancelled_at: Timestamp | None
    cancelled_by_customer: bool | None
    cancel_reason: str | None
    created_at: Timestamp
    updated_at: Timestamp


class BookingCreatedRead(SessionToken):
    """`POST /api/v1/bookings` → 201 (D32): the session token (also set as the cookie), whether an
    account was created, and the new booking."""

    account_created: bool
    booking: CustomerBookingDetail


class StatusCount(BaseModel):
    status: BookingStatus
    count: int


class StatusCountsRead(BaseModel):
    """All 17 statuses in glossary §3 order, zeros included, over the caller's D21 scope."""

    items: list[StatusCount]
    total: int

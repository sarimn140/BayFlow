"""Every stored enum in BayFlow, in one place (decision D74).

Member values are exactly the strings stored in the database and sent over the
API. Names and values come from `.claude/specs/18-glossary.md`; change the
glossary (and spec 17) first, then this file.
"""

from enum import IntEnum, StrEnum

# --- Roles (glossary §2) --------------------------------------------------------------------------


class MembershipRole(StrEnum):
    """Role of a user inside one shop (`shop_memberships.role`)."""

    OWNER = "OWNER"
    SERVICE_ADVISOR = "SERVICE_ADVISOR"
    TECHNICIAN = "TECHNICIAN"
    PARTS_PERSON = "PARTS_PERSON"
    QC_INSPECTOR = "QC_INSPECTOR"


STAFF_ROLES: frozenset[MembershipRole] = frozenset(MembershipRole) - {MembershipRole.OWNER}
"""`StaffRole` in the glossary: the roles an owner can assign."""


class ActorRole(StrEnum):
    """Who performed an action (`booking_events.actor_role`, `notifications.recipient_role`)."""

    CUSTOMER = "CUSTOMER"
    OWNER = "OWNER"
    SERVICE_ADVISOR = "SERVICE_ADVISOR"
    TECHNICIAN = "TECHNICIAN"
    PARTS_PERSON = "PARTS_PERSON"
    QC_INSPECTOR = "QC_INSPECTOR"
    SYSTEM = "SYSTEM"


# --- Booking lifecycle (glossary §3, §4; spec 08) -------------------------------------------------


class BookingStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    ASSIGNED = "ASSIGNED"
    INSPECTING = "INSPECTING"
    ESTIMATE_REVIEW = "ESTIMATE_REVIEW"
    AWAITING_CUSTOMER = "AWAITING_CUSTOMER"
    ESTIMATE_APPROVED = "ESTIMATE_APPROVED"
    ESTIMATE_REJECTED = "ESTIMATE_REJECTED"
    PARTS_PENDING = "PARTS_PENDING"
    PARTS_ORDERED = "PARTS_ORDERED"
    PARTS_READY = "PARTS_READY"
    IN_REPAIR = "IN_REPAIR"
    QC_PENDING = "QC_PENDING"
    QC_IN_PROGRESS = "QC_IN_PROGRESS"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class BookingAction(StrEnum):
    """Transitions (change status) and operations (no status change) on a booking."""

    CREATE = "CREATE"
    CONFIRM = "CONFIRM"
    DECLINE = "DECLINE"
    ASSIGN_TECHNICIAN = "ASSIGN_TECHNICIAN"
    START_INSPECTION = "START_INSPECTION"
    EDIT_ESTIMATE = "EDIT_ESTIMATE"
    SUBMIT_ESTIMATE = "SUBMIT_ESTIMATE"
    SEND_ESTIMATE = "SEND_ESTIMATE"
    APPROVE_ESTIMATE = "APPROVE_ESTIMATE"
    REJECT_ESTIMATE = "REJECT_ESTIMATE"
    REVISE_ESTIMATE = "REVISE_ESTIMATE"
    RETURN_TO_TECHNICIAN = "RETURN_TO_TECHNICIAN"
    ASSIGN_PARTS_PERSON = "ASSIGN_PARTS_PERSON"
    ORDER_PARTS = "ORDER_PARTS"
    MARK_PARTS_READY = "MARK_PARTS_READY"
    RECEIVE_PARTS = "RECEIVE_PARTS"
    ALLOCATE_PARTS = "ALLOCATE_PARTS"
    START_REPAIR = "START_REPAIR"
    SEND_TO_QC = "SEND_TO_QC"
    PICK_QC = "PICK_QC"
    PASS_QC = "PASS_QC"
    FAIL_QC = "FAIL_QC"
    NOTIFY_READY = "NOTIFY_READY"
    COMPLETE = "COMPLETE"
    CANCEL = "CANCEL"
    REASSIGN_TECHNICIAN = "REASSIGN_TECHNICIAN"
    REASSIGN_PARTS_PERSON = "REASSIGN_PARTS_PERSON"


# --- Estimates, inventory, QC (glossary §5) -------------------------------------------------------


class EstimateStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    SENT = "SENT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class EstimateLineType(StrEnum):
    PART = "PART"
    LABOUR = "LABOUR"


class StockMovementType(StrEnum):
    RECEIVE = "RECEIVE"
    RESERVE = "RESERVE"
    RELEASE = "RELEASE"
    CONSUME = "CONSUME"
    ADJUST = "ADJUST"


class PurchaseOrderStatus(StrEnum):
    ORDERED = "ORDERED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"


class StockState(StrEnum):
    """Wire enum (spec 03 §3.9, D45): computed from available stock, never stored."""

    OK = "OK"
    LOW = "LOW"
    OUT = "OUT"


class QcResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class QcIssueStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class QcChecklistKey(StrEnum):
    """Keys of the default QC checklist (D46); stored as JSON keys, values are lower-case."""

    ROAD_TEST = "road_test"
    NO_WARNING_LIGHTS = "no_warning_lights"
    NO_LEAKS = "no_leaks"
    FLUID_LEVELS = "fluid_levels"
    COMPLAINT_RESOLVED = "complaint_resolved"


class Weekday(IntEnum):
    """`shop_working_hours.weekday`: ISO order, Monday = 0 (matches `date.weekday()`)."""

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


# --- Notifications (glossary §6) ------------------------------------------------------------------


class NotificationType(StrEnum):
    BOOKING_CREATED = "BOOKING_CREATED"
    BOOKING_CONFIRMED = "BOOKING_CONFIRMED"
    TECHNICIAN_ASSIGNED = "TECHNICIAN_ASSIGNED"
    ESTIMATE_SUBMITTED = "ESTIMATE_SUBMITTED"
    ESTIMATE_SENT = "ESTIMATE_SENT"
    ESTIMATE_APPROVED = "ESTIMATE_APPROVED"
    ESTIMATE_REJECTED = "ESTIMATE_REJECTED"
    ESTIMATE_RETURNED = "ESTIMATE_RETURNED"
    PARTS_NEEDED = "PARTS_NEEDED"
    PARTS_READY = "PARTS_READY"
    QC_REQUESTED = "QC_REQUESTED"
    QC_FAILED = "QC_FAILED"
    QC_PASSED = "QC_PASSED"
    VEHICLE_READY = "VEHICLE_READY"
    BOOKING_CANCELLED = "BOOKING_CANCELLED"
    CALL_MISSED = "CALL_MISSED"  # bonus
    AI_TASK_CREATED = "AI_TASK_CREATED"  # bonus


# --- Platform audit log (spec 19 §3, D95) ----------------------------------------


class AuditCategory(StrEnum):
    """`audit_events.category` (spec 19 §3.1; stored as VARCHAR + CHECK like every enum, D29)."""

    AUTH = "AUTH"
    USER = "USER"
    SHOP = "SHOP"
    MEMBERSHIP = "MEMBERSHIP"
    BOOKING = "BOOKING"
    ADMIN = "ADMIN"


class AuditActorRole(StrEnum):
    """`audit_events.actor_role`: the hat the actor wore (spec 19 §3.1). `PLATFORM_ADMIN` for admin
    actions (D94), a `MembershipRole` for shop actions, `CUSTOMER`, `SYSTEM` (scripts, the seed,
    automatic transitions) or `ANONYMOUS` (failed sign-ins)."""

    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    OWNER = "OWNER"
    SERVICE_ADVISOR = "SERVICE_ADVISOR"
    TECHNICIAN = "TECHNICIAN"
    PARTS_PERSON = "PARTS_PERSON"
    QC_INSPECTOR = "QC_INSPECTOR"
    CUSTOMER = "CUSTOMER"
    SYSTEM = "SYSTEM"
    ANONYMOUS = "ANONYMOUS"


class AuditTargetType(StrEnum):
    """`audit_events.target_type`: what an audit event is about (spec 19 §3.1)."""

    USER = "USER"
    SHOP = "SHOP"
    MEMBERSHIP = "MEMBERSHIP"
    BOOKING = "BOOKING"


# --- Bonus: calling and AI Front Desk (glossary §5, spec 05) --------------------


class CallStatus(StrEnum):
    RINGING = "RINGING"
    CONNECTED = "CONNECTED"
    ENDED = "ENDED"
    MISSED = "MISSED"


class CallDirection(StrEnum):
    CUSTOMER_TO_SHOP = "CUSTOMER_TO_SHOP"
    SHOP_TO_CUSTOMER = "SHOP_TO_CUSTOMER"


class MissedReason(StrEnum):
    NO_ANSWER = "NO_ANSWER"
    DECLINED = "DECLINED"
    CALLER_HUNG_UP = "CALLER_HUNG_UP"


class AiLegStatus(StrEnum):
    """Derived for API responses only; never stored."""

    NONE = "NONE"
    CONNECTING = "CONNECTING"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    FAILED = "FAILED"


class IdentityMethod(StrEnum):
    NAME = "NAME"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    BOOKING_REFERENCE = "BOOKING_REFERENCE"


class CallIntent(StrEnum):
    STATUS_INQUIRY = "STATUS_INQUIRY"
    ESTIMATE_INQUIRY = "ESTIMATE_INQUIRY"
    APPOINTMENT_INQUIRY = "APPOINTMENT_INQUIRY"
    RESCHEDULE_REQUEST = "RESCHEDULE_REQUEST"
    PICKUP_INQUIRY = "PICKUP_INQUIRY"
    CALLBACK_REQUEST = "CALLBACK_REQUEST"
    COMPLAINT = "COMPLAINT"
    SAFETY_CONCERN = "SAFETY_CONCERN"
    OTHER = "OTHER"


class Sentiment(StrEnum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"


class TaskKind(StrEnum):
    CALLBACK = "CALLBACK"
    RESCHEDULE_REQUEST = "RESCHEDULE_REQUEST"
    ESCALATION = "ESCALATION"
    FOLLOW_UP = "FOLLOW_UP"


class TaskStatus(StrEnum):
    OPEN = "OPEN"
    DONE = "DONE"


# --- Text AI (bonus, D103; modules/ai.md) ------------------------------------------------------


class AiFeature(StrEnum):
    ESTIMATE_EXPLAINER = "ESTIMATE_EXPLAINER"  # AI-05
    ESTIMATE_CHECKER = "ESTIMATE_CHECKER"  # AI-14
    VOICE_TO_ESTIMATE = "VOICE_TO_ESTIMATE"  # AI-18
    SYMPTOM_TRIAGE = "SYMPTOM_TRIAGE"  # AI-01
    ASK_YOUR_SHOP = "ASK_YOUR_SHOP"  # AI-33


class AiCallStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    GUARD_BLOCKED = "GUARD_BLOCKED"


class AiDraftStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"


class AiSubjectType(StrEnum):
    BOOKING = "BOOKING"
    ESTIMATE = "ESTIMATE"
    SHOP = "SHOP"

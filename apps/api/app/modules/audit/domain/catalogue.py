"""The audit catalogue (spec 19 §3.3, D95): action names, summary sentences and label rules.

Pure: no I/O, no framework. The service resolves names (users, shops) and passes them in; this
module only words them. Every summary is one human sentence without secrets, cut to the column
size (`audit_events.summary` varchar(300)), and every label to `target_label` (varchar(200)).

Action names are dotted lower snake case (`ck_audit_events_action_format`): `<area>.<event>`, and
`booking.<action>` for every booking transition or operation, e.g. `booking.approve_estimate`.
"""

from collections.abc import Mapping
from typing import Final

from app.shared.enums import AuditCategory, BookingAction, MembershipRole

SUMMARY_MAX_LENGTH: Final = 300
LABEL_MAX_LENGTH: Final = 200
ACTION_MAX_LENGTH: Final = 64
ELLIPSIS: Final = "…"

SYSTEM_NAME: Final = "BayFlow"
"""Who a `SYSTEM` action is attributed to in a summary (scripts, the seed, automatic steps)."""
UNKNOWN_NAME: Final = "An unknown user"

# --- Action names (spec 19 §3.3) ------------------------------------------------------------------

LOGIN_SUCCEEDED: Final = "auth.login_succeeded"
LOGIN_FAILED: Final = "auth.login_failed"
LOGIN_RATE_LIMITED: Final = "auth.login_rate_limited"
LOGGED_OUT: Final = "auth.logged_out"
OWNER_REGISTERED: Final = "auth.owner_registered"
CUSTOMER_CREATED: Final = "user.customer_created"
USER_DEACTIVATED: Final = "user.deactivated"
USER_REACTIVATED: Final = "user.reactivated"
PLATFORM_ADMIN_GRANTED: Final = "user.platform_admin_granted"
PLATFORM_ADMIN_REVOKED: Final = "user.platform_admin_revoked"
SHOP_CREATED: Final = "shop.created"
SHOP_UPDATED: Final = "shop.updated"
WORKING_HOURS_REPLACED: Final = "shop.working_hours_replaced"
SHOP_SUSPENDED: Final = "shop.suspended"
SHOP_REACTIVATED: Final = "shop.reactivated"
MEMBERSHIP_ADDED: Final = "membership.added"
MEMBERSHIP_ROLE_CHANGED: Final = "membership.role_changed"
MEMBERSHIP_DEACTIVATED: Final = "membership.deactivated"
MEMBERSHIP_REACTIVATED: Final = "membership.reactivated"
USER_VIEWED: Final = "admin.user_viewed"
BOOKING_VIEWED: Final = "admin.booking_viewed"
AUDIT_EXPORTED: Final = "admin.audit_exported"


def booking_action_name(action: BookingAction) -> str:
    """`booking.<action>` in lower snake case, e.g. `booking.approve_estimate`."""
    return f"booking.{action.value.lower()}"


def category_of(action_name: str) -> AuditCategory:
    """The category an action name belongs to (its first segment)."""
    return {
        "auth": AuditCategory.AUTH,
        "user": AuditCategory.USER,
        "shop": AuditCategory.SHOP,
        "membership": AuditCategory.MEMBERSHIP,
        "booking": AuditCategory.BOOKING,
        "admin": AuditCategory.ADMIN,
    }[action_name.split(".", 1)[0]]


# --- Words ----------------------------------------------------------------------------------------

ROLE_LABELS: Final[Mapping[MembershipRole, str]] = {
    MembershipRole.OWNER: "Owner",
    MembershipRole.SERVICE_ADVISOR: "Service Advisor",
    MembershipRole.TECHNICIAN: "Technician",
    MembershipRole.PARTS_PERSON: "Parts Person",
    MembershipRole.QC_INSPECTOR: "QC Inspector",
}

BOOKING_PHRASES: Final[Mapping[BookingAction, str]] = {
    BookingAction.CREATE: "booked {reference}",
    BookingAction.CONFIRM: "confirmed {reference}",
    BookingAction.DECLINE: "declined {reference}",
    BookingAction.ASSIGN_TECHNICIAN: "assigned a technician to {reference}",
    BookingAction.START_INSPECTION: "started the inspection of {reference}",
    BookingAction.EDIT_ESTIMATE: "created a new estimate version for {reference}",
    BookingAction.SUBMIT_ESTIMATE: "submitted the estimate of {reference}",
    BookingAction.SEND_ESTIMATE: "sent the estimate of {reference} to the customer",
    BookingAction.APPROVE_ESTIMATE: "approved the estimate of {reference}",
    BookingAction.REJECT_ESTIMATE: "rejected the estimate of {reference}",
    BookingAction.REVISE_ESTIMATE: "reopened the estimate of {reference} for revision",
    BookingAction.RETURN_TO_TECHNICIAN: "returned the estimate of {reference} to the technician",
    BookingAction.ASSIGN_PARTS_PERSON: "assigned a parts person to {reference}",
    BookingAction.ORDER_PARTS: "ordered parts for {reference}",
    BookingAction.MARK_PARTS_READY: "marked the parts of {reference} ready",
    BookingAction.RECEIVE_PARTS: "received the ordered parts of {reference}",
    BookingAction.ALLOCATE_PARTS: "allocated the parts of {reference}",
    BookingAction.START_REPAIR: "started the repair of {reference}",
    BookingAction.SEND_TO_QC: "sent {reference} to quality check",
    BookingAction.PICK_QC: "picked {reference} for quality check",
    BookingAction.PASS_QC: "passed the quality check of {reference}",
    BookingAction.FAIL_QC: "failed the quality check of {reference}",
    BookingAction.NOTIFY_READY: "told the customer that {reference} is ready for pick-up",
    BookingAction.COMPLETE: "completed {reference}",
    BookingAction.CANCEL: "cancelled {reference}",
    BookingAction.REASSIGN_TECHNICIAN: "reassigned the technician of {reference}",
    BookingAction.REASSIGN_PARTS_PERSON: "reassigned the parts person of {reference}",
}
"""What an actor did to a booking, for every `BookingAction` (spec 08)."""


def cut(text: str, limit: int) -> str:
    """`text` on one line, at most `limit` characters (ending in "…" when it was longer)."""
    single_line = " ".join(text.split())
    if len(single_line) <= limit:
        return single_line
    return single_line[: limit - len(ELLIPSIS)].rstrip() + ELLIPSIS


def summary(template: str, **names: object) -> str:
    """One sentence from a template and already resolved names, cut to 300 characters."""
    return cut(template.format(**names), SUMMARY_MAX_LENGTH)


def label(text: str | None) -> str | None:
    """A target label (a reference, a shop name, an e-mail), cut to 200 characters."""
    return None if text is None else cut(text, LABEL_MAX_LENGTH)


def booking_summary(actor: str, action: BookingAction, reference: str, shop: str) -> str:
    """E.g. "Bilal Ahmed approved the estimate of BF-7K2M9Q at Lahore Auto Care." """
    phrase = BOOKING_PHRASES[action].format(reference=reference)
    return summary("{actor} {phrase} at {shop}.", actor=actor, phrase=phrase, shop=shop)


def changed_fields(changes: Mapping[str, object]) -> str:
    """The changed field names for a summary, e.g. "name, slot_capacity"."""
    return ", ".join(sorted(changes)) or "no fields"

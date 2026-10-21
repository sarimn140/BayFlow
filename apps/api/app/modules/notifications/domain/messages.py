"""Notification texts (pure; `modules/notifications.md` "Texts", D41).

English, composed once when the row is written. Placeholders: `{ref}` (the booking reference),
`{shop}` (the shop's name), `{actor}` (the actor's full name), `{customer}` (the customer's full
name), `{version}` and `{total}` (the event metadata's estimate `version` and `grand_total`, shown
as "PKR 16,100", D41) and `{note}` (the event note: the decline, cancel or reject reason, the
return note, or the QC issue title, D92). A note's whitespace runs are collapsed to single spaces.
Titles are cut to 160 and bodies to 1,000 characters with "…" (the column sizes). Bodies are plain
text: the web renders them as text only (spec 04 threat 9).

A missing fact never fails the action: an absent name reads "the shop" / "the customer" /
"a team member", a missing estimate version reads "the estimate", a missing total is left out and
a missing reason reads "none given".
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from types import MappingProxyType

from app.shared.enums import ActorRole, NotificationType

TITLE_MAX_LENGTH = 160  # notifications.title varchar(160)
BODY_MAX_LENGTH = 1000  # notifications.body varchar(1000)
ELLIPSIS = "…"
NO_REASON = "none given"
_SENTENCE_ENDINGS = (".", "!", "?", ELLIPSIS)


@dataclass(frozen=True, slots=True, kw_only=True)
class MessageContext:
    """The facts one action's texts are composed from (the same for every recipient)."""

    reference: str
    shop_name: str | None = None
    actor_name: str | None = None
    actor_role: ActorRole | None = None
    customer_name: str | None = None
    version: int | None = None
    total: str | None = None  # already formatted, e.g. "PKR 16,100"
    note: str | None = None  # already cleaned (`clean_note`)


# --- Values -----------------------------------------------------------------------------------


def clean_note(note: str | None) -> str | None:
    """The note with every whitespace run collapsed to one space; None when nothing is left."""
    if note is None:
        return None
    cleaned = " ".join(note.split())
    return cleaned or None


def _to_decimal(amount: object) -> Decimal | None:
    if isinstance(amount, bool):
        return None
    try:
        if isinstance(amount, Decimal):
            value = amount
        elif isinstance(amount, int):
            value = Decimal(amount)
        elif isinstance(amount, float):
            value = Decimal(repr(amount))
        elif isinstance(amount, str):
            value = Decimal(amount.strip())
        else:
            return None
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def format_pkr(amount: object) -> str | None:
    """`"16100.00"` (or a `Decimal` / an integer) → `"PKR 16,100"`; None when it is not an amount.

    Whole rupees (D41): a fraction would be rounded half-up, though amounts never carry one.
    """
    value = _to_decimal(amount)
    if value is None or value < 0:
        return None
    try:
        rupees = value.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    except InvalidOperation:  # an exponent beyond the decimal context's precision
        return None
    return f"PKR {rupees:,.0f}"


def estimate_version(value: object) -> int | None:
    """The estimate version from event metadata (a positive integer), else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, str) and value.strip().isdecimal():
        value = int(value.strip())
    if isinstance(value, int) and value >= 1:
        return value
    return None


def truncate(text: str, limit: int) -> str:
    """`text` cut to at most `limit` characters, ending in "…" when something was cut."""
    if limit < len(ELLIPSIS):
        msg = "limit must leave room for the ellipsis"
        raise ValueError(msg)
    if len(text) <= limit:
        return text
    return text[: limit - len(ELLIPSIS)] + ELLIPSIS


# --- Placeholders -------------------------------------------------------------------------------


def _shop(context: MessageContext, *, start: bool = False) -> str:
    if context.shop_name:
        return context.shop_name
    return "The shop" if start else "the shop"


def _customer(context: MessageContext, *, start: bool = False) -> str:
    if context.customer_name:
        return context.customer_name
    return "The customer" if start else "the customer"


def _actor(context: MessageContext, *, start: bool = False) -> str:
    if context.actor_name:
        return context.actor_name
    if context.actor_role == ActorRole.SYSTEM:
        return "BayFlow"
    return "A team member" if start else "a team member"


def _estimate(context: MessageContext) -> str:
    return f"estimate v{context.version}" if context.version is not None else "the estimate"


def _in_brackets(total: str | None) -> str:
    return f" ({total})" if total else ""


def _sentence(text: str) -> str:
    """`text` ending in one full stop (none added after "!", "?", "…" or ".")."""
    return text if text.endswith(_SENTENCE_ENDINGS) else f"{text}."


def _reason(note: str | None) -> str:
    return _sentence(f"Reason: {note or NO_REASON}")


def _with_note(sentence: str, note: str | None) -> str:
    return f"{sentence} {note}" if note else sentence


# --- Templates (title, body) ---------------------------------------------------------------------

type _Texts = Callable[[MessageContext], tuple[str, str]]


def _booking_created(c: MessageContext) -> tuple[str, str]:
    return f"New booking {c.reference}", f"{_customer(c, start=True)} booked a visit at {_shop(c)}."


def _booking_confirmed(c: MessageContext) -> tuple[str, str]:
    return f"Booking confirmed — {c.reference}", f"{_shop(c, start=True)} confirmed your booking."


def _technician_assigned(c: MessageContext) -> tuple[str, str]:
    return f"New job {c.reference}", f"{_actor(c, start=True)} assigned this booking to you."


def _estimate_submitted(c: MessageContext) -> tuple[str, str]:
    body = f"{_actor(c, start=True)} submitted {_estimate(c)}{_in_brackets(c.total)}."
    return f"Estimate to review — {c.reference}", body


def _estimate_sent(c: MessageContext) -> tuple[str, str]:
    amount = f": {c.total}" if c.total else ""
    body = f"{_shop(c, start=True)} sent {_estimate(c)}{amount}. Review and approve it in BayFlow."
    return f"Your estimate is ready — {c.reference}", body


def _estimate_approved(c: MessageContext) -> tuple[str, str]:
    body = f"{_customer(c, start=True)} approved {_estimate(c)}{_in_brackets(c.total)}."
    return f"Estimate approved — {c.reference}", body


def _estimate_rejected(c: MessageContext) -> tuple[str, str]:
    body = f"{_customer(c, start=True)} declined {_estimate(c)}. {_reason(c.note)}"
    return f"Estimate declined — {c.reference}", body


def _estimate_returned(c: MessageContext) -> tuple[str, str]:
    body = _with_note(f"{_actor(c, start=True)} returned the estimate to you.", c.note)
    return f"Estimate returned — {c.reference}", body


def _parts_needed(c: MessageContext) -> tuple[str, str]:
    return f"Parts needed — {c.reference}", "Check and reserve the parts for this job."


def _parts_ready(c: MessageContext) -> tuple[str, str]:
    return f"Parts ready — {c.reference}", "The parts are allocated; you can start the repair."


def _qc_requested(c: MessageContext) -> tuple[str, str]:
    return f"QC requested — {c.reference}", "This job is waiting in the QC queue."


def _qc_failed(c: MessageContext) -> tuple[str, str]:
    body = _with_note(f"{_actor(c, start=True)} returned the job with an issue to fix.", c.note)
    return f"QC failed — {c.reference}", body


def _qc_passed(c: MessageContext) -> tuple[str, str]:
    return f"QC passed — {c.reference}", "The vehicle is ready for pick-up. Notify the customer."


def _vehicle_ready(c: MessageContext) -> tuple[str, str]:
    body = f"Booking {c.reference} at {_shop(c)} is ready for pick-up."
    return "Your vehicle is ready for pick-up", body


def _cancelled_to_customer(c: MessageContext) -> tuple[str, str]:
    body = f"{_shop(c, start=True)} cancelled your booking. {_reason(c.note)}"
    return f"Booking cancelled — {c.reference}", body


def _cancelled_to_staff(c: MessageContext) -> tuple[str, str]:
    body = _with_note(f"{_customer(c, start=True)} cancelled the booking.", c.note)
    return f"Booking cancelled — {c.reference}", body


TEXTS: Mapping[NotificationType, _Texts] = MappingProxyType(
    {
        NotificationType.BOOKING_CREATED: _booking_created,
        NotificationType.BOOKING_CONFIRMED: _booking_confirmed,
        NotificationType.TECHNICIAN_ASSIGNED: _technician_assigned,
        NotificationType.ESTIMATE_SUBMITTED: _estimate_submitted,
        NotificationType.ESTIMATE_SENT: _estimate_sent,
        NotificationType.ESTIMATE_APPROVED: _estimate_approved,
        NotificationType.ESTIMATE_REJECTED: _estimate_rejected,
        NotificationType.ESTIMATE_RETURNED: _estimate_returned,
        NotificationType.PARTS_NEEDED: _parts_needed,
        NotificationType.PARTS_READY: _parts_ready,
        NotificationType.QC_REQUESTED: _qc_requested,
        NotificationType.QC_FAILED: _qc_failed,
        NotificationType.QC_PASSED: _qc_passed,
        NotificationType.VEHICLE_READY: _vehicle_ready,
        NotificationType.BOOKING_CANCELLED: _cancelled_to_customer,
    }
)
"""The 15 booking types; `BOOKING_CANCELLED` to staff uses its own body (see `compose`)."""


def compose(
    notification_type: NotificationType, recipient_role: ActorRole, context: MessageContext
) -> tuple[str, str]:
    """`(title, body)` for one recipient, cut to the column sizes.

    Only `BOOKING_CANCELLED` depends on the recipient: the customer reads the shop's reason, staff
    read that the customer cancelled. Raises `ValueError` for a type without a text here.
    """
    if notification_type == NotificationType.BOOKING_CANCELLED and (
        recipient_role != ActorRole.CUSTOMER
    ):
        texts: _Texts = _cancelled_to_staff
    elif notification_type in TEXTS:
        texts = TEXTS[notification_type]
    else:
        msg = f"no booking notification text for {notification_type}"
        raise ValueError(msg)
    title, body = texts(context)
    return truncate(title, TITLE_MAX_LENGTH), truncate(body, BODY_MAX_LENGTH)


def email_text(body: str, link: str, client_url: str) -> str:
    """The plain-text e-mail: the body, then the link on `CLIENT_URL` (never the request's
    `Host`, spec 04)."""
    return f"{body}\n\nOpen in BayFlow: {client_url.rstrip('/')}{link}"

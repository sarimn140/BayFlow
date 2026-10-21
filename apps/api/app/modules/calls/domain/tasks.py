"""Task titles and the fallback summary (spec 05 §6.3, §6.4). Titles are composed by the API from
the database's first name, never from text the model wrote."""

from dataclasses import dataclass
from typing import Final

from app.shared.enums import BookingStatus, CallIntent, Sentiment

MAX_TITLE: Final = 160
MAX_TOPIC: Final = 60
MAX_INTENT: Final = 120
MAX_DETAILS: Final = 4000


def _cut(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def callback_title(first_name: str, topic: str) -> str:
    return _cut(f"Call back {first_name} about {_cut(topic, MAX_TOPIC)}", MAX_TITLE)


def unavailable_callback_title(first_name: str) -> str:
    return _cut(f"Missed call from {first_name} — AI Front Desk unavailable", MAX_TITLE)


def left_early_callback_title(first_name: str) -> str:
    return _cut(
        f"Missed call from {first_name} — caller left before the assistant could help", MAX_TITLE
    )


def reschedule_title(first_name: str, reference: str) -> str:
    return _cut(f"Reschedule request from {first_name} ({reference})", MAX_TITLE)


def escalation_title(first_name: str, reason: str) -> str:
    return _cut(f"URGENT: {first_name} — {reason}", MAX_TITLE)


def follow_up_title(title: str) -> str:
    return _cut(title, MAX_TITLE)


@dataclass(frozen=True, slots=True)
class SummaryFields:
    intent: str
    intent_category: CallIntent
    details: str
    sentiment: Sentiment
    follow_up_task_title: str
    urgent: bool
    language: str
    is_fallback: bool


FALLBACK_SUMMARY: Final = SummaryFields(
    intent="Summary unavailable",
    intent_category=CallIntent.OTHER,
    details="The AI Front Desk could not produce a summary of this call. See the transcript.",
    sentiment=Sentiment.NEUTRAL,
    follow_up_task_title="",
    urgent=False,
    language="en",
    is_fallback=True,
)

# Glossary §3 customer-facing labels: the agent states exactly these (spec 05 §4.3).
CUSTOMER_STATUS_LABELS: Final[dict[BookingStatus, str]] = {
    BookingStatus.PENDING: "Booking received",
    BookingStatus.CONFIRMED: "Booking confirmed",
    BookingStatus.ASSIGNED: "Technician assigned",
    BookingStatus.INSPECTING: "Inspection in progress",
    BookingStatus.ESTIMATE_REVIEW: "Preparing your estimate",
    BookingStatus.AWAITING_CUSTOMER: "Estimate awaiting your approval",
    BookingStatus.ESTIMATE_APPROVED: "Estimate approved",
    BookingStatus.ESTIMATE_REJECTED: "Estimate declined — the shop will follow up",
    BookingStatus.PARTS_PENDING: "Checking parts",
    BookingStatus.PARTS_ORDERED: "Parts ordered",
    BookingStatus.PARTS_READY: "Parts ready",
    BookingStatus.IN_REPAIR: "Repair in progress",
    BookingStatus.QC_PENDING: "Waiting for quality check",
    BookingStatus.QC_IN_PROGRESS: "Quality check in progress",
    BookingStatus.READY_FOR_PICKUP: "Ready for pick-up",
    BookingStatus.COMPLETED: "Completed",
    BookingStatus.CANCELLED: "Cancelled",
}

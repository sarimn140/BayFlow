"""NOT-15: notification texts (`modules/notifications.md` "Texts"): every template with its
placeholders filled from the event, the column cuts (160 / 1,000 with "…"), money as "PKR 16,100"
(D41), and the fallbacks that keep a missing fact from ever failing an action."""

from decimal import Decimal

import pytest

from app.modules.notifications.domain.messages import (
    BODY_MAX_LENGTH,
    TEXTS,
    TITLE_MAX_LENGTH,
    MessageContext,
    clean_note,
    compose,
    email_text,
    estimate_version,
    format_pkr,
    truncate,
)
from app.shared.enums import ActorRole, NotificationType

T = NotificationType
R = ActorRole
REF = "BF-7KQ2MX"

FULL = MessageContext(
    reference=REF,
    shop_name="Lahore Auto Care",
    actor_name="Bilal",
    actor_role=R.SERVICE_ADVISOR,
    customer_name="Ahmed Ali",
    version=2,
    total="PKR 16,100",
    note="Customer asked to wait",
)

# The spec's table, filled in (modules/notifications.md "Texts").
EXPECTED: dict[tuple[NotificationType, ActorRole], tuple[str, str]] = {
    (T.BOOKING_CREATED, R.SERVICE_ADVISOR): (
        f"New booking {REF}",
        "Ahmed Ali booked a visit at Lahore Auto Care.",
    ),
    (T.BOOKING_CONFIRMED, R.CUSTOMER): (
        f"Booking confirmed — {REF}",
        "Lahore Auto Care confirmed your booking.",
    ),
    (T.TECHNICIAN_ASSIGNED, R.TECHNICIAN): (
        f"New job {REF}",
        "Bilal assigned this booking to you.",
    ),
    (T.ESTIMATE_SUBMITTED, R.SERVICE_ADVISOR): (
        f"Estimate to review — {REF}",
        "Bilal submitted estimate v2 (PKR 16,100).",
    ),
    (T.ESTIMATE_SENT, R.CUSTOMER): (
        f"Your estimate is ready — {REF}",
        "Lahore Auto Care sent estimate v2: PKR 16,100. Review and approve it in BayFlow.",
    ),
    (T.ESTIMATE_APPROVED, R.OWNER): (
        f"Estimate approved — {REF}",
        "Ahmed Ali approved estimate v2 (PKR 16,100).",
    ),
    (T.ESTIMATE_REJECTED, R.SERVICE_ADVISOR): (
        f"Estimate declined — {REF}",
        "Ahmed Ali declined estimate v2. Reason: Customer asked to wait.",
    ),
    (T.ESTIMATE_RETURNED, R.TECHNICIAN): (
        f"Estimate returned — {REF}",
        "Bilal returned the estimate to you. Customer asked to wait",
    ),
    (T.PARTS_NEEDED, R.PARTS_PERSON): (
        f"Parts needed — {REF}",
        "Check and reserve the parts for this job.",
    ),
    (T.PARTS_READY, R.TECHNICIAN): (
        f"Parts ready — {REF}",
        "The parts are allocated; you can start the repair.",
    ),
    (T.QC_REQUESTED, R.QC_INSPECTOR): (
        f"QC requested — {REF}",
        "This job is waiting in the QC queue.",
    ),
    (T.QC_FAILED, R.TECHNICIAN): (
        f"QC failed — {REF}",
        "Bilal returned the job with an issue to fix. Customer asked to wait",
    ),
    (T.QC_PASSED, R.SERVICE_ADVISOR): (
        f"QC passed — {REF}",
        "The vehicle is ready for pick-up. Notify the customer.",
    ),
    (T.VEHICLE_READY, R.CUSTOMER): (
        "Your vehicle is ready for pick-up",
        f"Booking {REF} at Lahore Auto Care is ready for pick-up.",
    ),
    (T.BOOKING_CANCELLED, R.CUSTOMER): (
        f"Booking cancelled — {REF}",
        "Lahore Auto Care cancelled your booking. Reason: Customer asked to wait.",
    ),
    (T.BOOKING_CANCELLED, R.SERVICE_ADVISOR): (
        f"Booking cancelled — {REF}",
        "Ahmed Ali cancelled the booking. Customer asked to wait",
    ),
}


def test_every_booking_type_has_a_text() -> None:
    booking_types = set(T) - {T.CALL_MISSED, T.AI_TASK_CREATED}
    assert set(TEXTS) == booking_types
    assert {notification_type for notification_type, _ in EXPECTED} == booking_types


@pytest.mark.parametrize(("key", "texts"), EXPECTED.items(), ids=str)
def test_not15_placeholders_are_filled_from_the_event(
    key: tuple[NotificationType, ActorRole], texts: tuple[str, str]
) -> None:
    notification_type, role = key
    assert compose(notification_type, role, FULL) == texts


@pytest.mark.parametrize(
    "role", [R.SERVICE_ADVISOR, R.OWNER, R.TECHNICIAN, R.PARTS_PERSON, R.QC_INSPECTOR]
)
def test_booking_cancelled_reads_as_the_customers_cancel_for_every_staff_role(
    role: ActorRole,
) -> None:
    assert compose(T.BOOKING_CANCELLED, role, FULL)[1] == (
        "Ahmed Ali cancelled the booking. Customer asked to wait"
    )


@pytest.mark.parametrize("notification_type", [T.CALL_MISSED, T.AI_TASK_CREATED])
def test_bonus_types_have_no_booking_text(notification_type: NotificationType) -> None:
    with pytest.raises(ValueError, match="no booking notification text"):
        compose(notification_type, R.SERVICE_ADVISOR, FULL)


# --- Cuts -----------------------------------------------------------------------------------------


def test_not15_a_2000_character_cancel_reason_is_cut_to_1000_characters() -> None:
    context = MessageContext(reference=REF, shop_name="Lahore Auto Care", note="r" * 2000)
    title, body = compose(T.BOOKING_CANCELLED, R.CUSTOMER, context)
    assert title == f"Booking cancelled — {REF}"
    assert len(body) == BODY_MAX_LENGTH
    assert body.startswith("Lahore Auto Care cancelled your booking. Reason: rrr")
    assert body.endswith("r…")


def test_a_long_title_is_cut_to_160_characters() -> None:
    title, _ = compose(T.BOOKING_CREATED, R.SERVICE_ADVISOR, MessageContext(reference="X" * 400))
    assert len(title) == TITLE_MAX_LENGTH
    assert title.endswith("…")


@pytest.mark.parametrize(
    ("text", "limit", "expected"),
    [
        ("abc", 3, "abc"),
        ("abcd", 3, "ab…"),
        ("", 5, ""),
        ("a" * 1000, 1000, "a" * 1000),
        ("a" * 1001, 1000, "a" * 999 + "…"),
    ],
)
def test_truncate(text: str, limit: int, expected: str) -> None:
    assert truncate(text, limit) == expected


def test_truncate_needs_room_for_the_ellipsis() -> None:
    with pytest.raises(ValueError, match="limit"):
        truncate("abc", 0)


# --- Money and versions (event metadata) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("16100.00", "PKR 16,100"),
        ("16600", "PKR 16,600"),
        (Decimal("900.00"), "PKR 900"),
        (Decimal("1250000"), "PKR 1,250,000"),
        (5200, "PKR 5,200"),
        (0, "PKR 0"),
        ("0.00", "PKR 0"),
        (16100.0, "PKR 16,100"),
        ("2498.50", "PKR 2,499"),  # half-up, never banker's rounding (D41)
        (" 3500 ", "PKR 3,500"),
        ("1e3", "PKR 1,000"),
        ("9999999999.00", "PKR 9,999,999,999"),
        (None, None),
        (True, None),
        ("", None),
        ("abc", None),
        ("NaN", None),
        ("Infinity", None),
        (float("nan"), None),
        ("-1.00", None),
        ("1e100000", None),
        ({"amount": 1}, None),
        ([16100], None),
    ],
)
def test_format_pkr(amount: object, expected: str | None) -> None:
    assert format_pkr(amount) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2, 2),
        (1, 1),
        ("3", 3),
        (" 4 ", 4),
        (2.0, 2),
        (0, None),
        (-1, None),
        (2.5, None),
        (True, None),
        (None, None),
        ("v2", None),
        ("", None),
        ("-2", None),
    ],
)
def test_estimate_version(value: object, expected: int | None) -> None:
    assert estimate_version(value) == expected


# --- Notes and fallbacks --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        (None, None),
        ("", None),
        ("   \n\t ", None),
        ("  Oil leak at filter  ", "Oil leak at filter"),
        ("Line one\nline   two\r\n\tthree", "Line one line two three"),
    ],
)
def test_clean_note(note: str | None, expected: str | None) -> None:
    assert clean_note(note) == expected


@pytest.mark.parametrize(
    ("note", "body"),
    [
        (None, "Ahmed Ali declined estimate v2. Reason: none given."),
        ("Too expensive", "Ahmed Ali declined estimate v2. Reason: Too expensive."),
        ("Too expensive.", "Ahmed Ali declined estimate v2. Reason: Too expensive."),
        ("Too expensive!", "Ahmed Ali declined estimate v2. Reason: Too expensive!"),
        ("Why so high?", "Ahmed Ali declined estimate v2. Reason: Why so high?"),
        ("Hmm…", "Ahmed Ali declined estimate v2. Reason: Hmm…"),
    ],
)
def test_a_reason_ends_in_exactly_one_full_stop(note: str | None, body: str) -> None:
    context = MessageContext(reference=REF, customer_name="Ahmed Ali", version=2, note=note)
    assert compose(T.ESTIMATE_REJECTED, R.SERVICE_ADVISOR, context)[1] == body


def test_optional_notes_leave_no_trailing_space() -> None:
    context = MessageContext(reference=REF, actor_name="Bilal", customer_name="Ahmed Ali")
    assert compose(T.ESTIMATE_RETURNED, R.TECHNICIAN, context)[1] == (
        "Bilal returned the estimate to you."
    )
    assert compose(T.QC_FAILED, R.TECHNICIAN, context)[1] == (
        "Bilal returned the job with an issue to fix."
    )
    assert compose(T.BOOKING_CANCELLED, R.TECHNICIAN, context)[1] == (
        "Ahmed Ali cancelled the booking."
    )
    assert compose(T.BOOKING_CANCELLED, R.CUSTOMER, MessageContext(reference=REF))[1] == (
        "The shop cancelled your booking. Reason: none given."
    )


@pytest.mark.parametrize(
    ("notification_type", "role", "body"),
    [
        (T.BOOKING_CREATED, R.OWNER, "The customer booked a visit at the shop."),
        (T.BOOKING_CONFIRMED, R.CUSTOMER, "The shop confirmed your booking."),
        (T.TECHNICIAN_ASSIGNED, R.TECHNICIAN, "A team member assigned this booking to you."),
        (T.ESTIMATE_SUBMITTED, R.SERVICE_ADVISOR, "A team member submitted the estimate."),
        (
            T.ESTIMATE_SENT,
            R.CUSTOMER,
            "The shop sent the estimate. Review and approve it in BayFlow.",
        ),
        (T.ESTIMATE_APPROVED, R.SERVICE_ADVISOR, "The customer approved the estimate."),
        (
            T.ESTIMATE_REJECTED,
            R.SERVICE_ADVISOR,
            "The customer declined the estimate. Reason: none given.",
        ),
        (T.VEHICLE_READY, R.CUSTOMER, f"Booking {REF} at the shop is ready for pick-up."),
    ],
)
def test_missing_facts_fall_back_to_neutral_words(
    notification_type: NotificationType, role: ActorRole, body: str
) -> None:
    assert compose(notification_type, role, MessageContext(reference=REF))[1] == body


def test_partial_estimate_facts() -> None:
    only_version = MessageContext(reference=REF, shop_name="Lahore Auto Care", version=3)
    only_total = MessageContext(reference=REF, shop_name="Lahore Auto Care", total="PKR 900")
    assert compose(T.ESTIMATE_SENT, R.CUSTOMER, only_version)[1] == (
        "Lahore Auto Care sent estimate v3. Review and approve it in BayFlow."
    )
    assert compose(T.ESTIMATE_SENT, R.CUSTOMER, only_total)[1] == (
        "Lahore Auto Care sent the estimate: PKR 900. Review and approve it in BayFlow."
    )
    assert compose(T.ESTIMATE_APPROVED, R.OWNER, only_total)[1] == (
        "The customer approved the estimate (PKR 900)."
    )


def test_a_system_actor_reads_as_bayflow() -> None:
    context = MessageContext(reference=REF, actor_role=R.SYSTEM)
    assert compose(T.TECHNICIAN_ASSIGNED, R.TECHNICIAN, context)[1] == (
        "BayFlow assigned this booking to you."
    )


def test_names_are_kept_as_written() -> None:
    """Placeholders are never re-cased (a shop called "eAuto" stays "eAuto")."""
    context = MessageContext(reference=REF, shop_name="eAuto Garage", customer_name="de Souza")
    assert (
        compose(T.BOOKING_CONFIRMED, R.CUSTOMER, context)[1]
        == "eAuto Garage confirmed your booking."
    )
    assert (
        compose(T.BOOKING_CREATED, R.OWNER, context)[1]
        == "de Souza booked a visit at eAuto Garage."
    )


# --- E-mail text ----------------------------------------------------------------------------------


@pytest.mark.parametrize("client_url", ["http://localhost:3000", "http://localhost:3000/"])
def test_email_text_links_on_the_client_url(client_url: str) -> None:
    assert email_text("Booking BF-1 is ready.", "/bookings/42", client_url) == (
        "Booking BF-1 is ready.\n\nOpen in BayFlow: http://localhost:3000/bookings/42"
    )

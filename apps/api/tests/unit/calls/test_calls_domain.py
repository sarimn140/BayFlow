"""Pure rules of the calls module: caller matching (§4.2), ring set (§3.3), AI leg status, usage
minutes (§11.3) and task titles (§6.4)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.calls.domain.caller_match import (
    Claim,
    Customer,
    first_name,
    known_references,
    match,
    normalise_reference,
)
from app.modules.calls.domain.lifecycle import (
    AiLeg,
    UsageRow,
    ai_leg_status,
    dispatches_ai,
    every_rung_declined,
    participant_minutes,
    ring_set,
)
from app.modules.calls.domain.tasks import callback_title, escalation_title
from app.shared.enums import AiLegStatus, CallDirection, CallStatus, IdentityMethod, MissedReason

AHMED = Customer(
    full_name="Ahmed Raza",
    email="Ahmed.Raza@Mail.test",
    phone="+923001234567",
    references=known_references(["BF-7K2M9Q"]),
)


@pytest.mark.parametrize(
    ("claim", "method"),
    [
        (Claim(booking_reference="b f 7k2m-9q"), IdentityMethod.BOOKING_REFERENCE),
        (Claim(booking_reference="7K2M9Q"), IdentityMethod.BOOKING_REFERENCE),
        (Claim(email="  ahmed.raza@mail.TEST "), IdentityMethod.EMAIL),
        (Claim(phone="0300 1234567"), IdentityMethod.PHONE),
        (Claim(phone="+92-300-1234567"), IdentityMethod.PHONE),
        (Claim(name="Ahmad"), IdentityMethod.NAME),
        (Claim(name="ahmed raza."), IdentityMethod.NAME),
        (Claim(name="Zainab"), None),
        (Claim(booking_reference="BF-AAAAAA"), None),
        (Claim(phone="12345"), None),
    ],
)
def test_caller_matching(claim: Claim, method: IdentityMethod | None) -> None:
    assert match(claim, AHMED) == method


def test_reference_normalisation_applies_crockford_fixes() -> None:
    assert normalise_reference("bf-7K2M9O") == "BF-7K2M90"
    assert normalise_reference("BF 1IL") == "BF-111"
    assert first_name("Ahmed Raza") == "Ahmed"


def test_ring_set_skips_offline_busy_and_the_caller() -> None:
    a, b, c, d = (uuid.uuid4() for _ in range(4))
    assert ring_set(eligible=[a, b, c], online=[a, b, d], busy=[b], caller=c) == [a]
    assert ring_set(eligible=[a], online=[], busy=[], caller=c) == []


def test_decline_ends_only_a_non_empty_fully_declined_ring_set() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    assert every_rung_declined([a, b], [a, b])
    assert not every_rung_declined([a, b], [a])
    assert not every_rung_declined([], [a])  # D77: nobody rung → only the deadline ends it


def test_ai_is_dispatched_only_for_missed_customer_calls() -> None:
    c2s, s2c = CallDirection.CUSTOMER_TO_SHOP, CallDirection.SHOP_TO_CUSTOMER
    assert dispatches_ai(c2s, MissedReason.NO_ANSWER)
    assert dispatches_ai(c2s, MissedReason.DECLINED)
    assert not dispatches_ai(c2s, MissedReason.CALLER_HUNG_UP)
    assert not dispatches_ai(s2c, MissedReason.NO_ANSWER)


def test_ai_leg_status_is_derived() -> None:
    now = datetime(2026, 10, 16, 5, tzinfo=UTC)
    assert ai_leg_status(AiLeg(None, None, None, None)) is AiLegStatus.NONE
    assert ai_leg_status(AiLeg(now, None, None, None)) is AiLegStatus.CONNECTING
    assert ai_leg_status(AiLeg(now, now, None, None)) is AiLegStatus.ACTIVE
    assert ai_leg_status(AiLeg(now, now, now, None)) is AiLegStatus.ENDED
    assert ai_leg_status(AiLeg(now, None, now, "AGENT_UNAVAILABLE")) is AiLegStatus.FAILED


def test_participant_minutes_count_ringing_once_and_talk_twice() -> None:
    start = datetime(2026, 10, 16, 5, tzinfo=UTC)
    rows = [
        UsageRow(CallStatus.ENDED, start, start + timedelta(seconds=20), None, 180, None),
        UsageRow(CallStatus.MISSED, start, None, start + timedelta(seconds=20), None, 120),
    ]
    # 20 + 360 for the first, 20 + 240 for the AI-answered second: 640 s → 11 minutes
    assert participant_minutes(rows, now=start) == 11


def test_task_titles_are_bounded() -> None:
    assert callback_title("Ahmed", "the estimate") == "Call back Ahmed about the estimate"
    assert len(escalation_title("Ahmed", "x" * 500)) <= 160

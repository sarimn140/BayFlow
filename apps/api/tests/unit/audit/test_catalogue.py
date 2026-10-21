"""The audit catalogue's words (spec 19 §3.3): action names, categories, summaries, labels."""

import re

import pytest

from app.modules.audit.domain import catalogue
from app.modules.audit.domain.catalogue import (
    BOOKING_PHRASES,
    ROLE_LABELS,
    booking_action_name,
    booking_summary,
    category_of,
    changed_fields,
    cut,
    label,
    summary,
)
from app.modules.audit.models import ACTION_PATTERN
from app.shared.enums import AuditCategory, BookingAction, MembershipRole

ACTION_NAMES = [
    value
    for name, value in vars(catalogue).items()
    if name.isupper() and isinstance(value, str) and "." in value and " " not in value
]


def test_every_booking_action_has_a_phrase_and_a_valid_name() -> None:
    assert set(BOOKING_PHRASES) == set(BookingAction)
    for action in BookingAction:
        name = booking_action_name(action)
        assert re.fullmatch(ACTION_PATTERN, name), name
        assert len(name) <= catalogue.ACTION_MAX_LENGTH
        assert category_of(name) is AuditCategory.BOOKING
    assert booking_action_name(BookingAction.APPROVE_ESTIMATE) == "booking.approve_estimate"


def test_the_catalogue_names_follow_the_format_and_their_category() -> None:
    assert len(ACTION_NAMES) == 22  # spec 19 §3.3 without the booking actions
    for name in ACTION_NAMES:
        assert re.fullmatch(ACTION_PATTERN, name), name
        assert category_of(name) is AuditCategory(name.split(".", 1)[0].upper())


def test_roles_have_labels() -> None:
    assert set(ROLE_LABELS) == set(MembershipRole)


def test_booking_summaries_read_as_one_sentence() -> None:
    assert (
        booking_summary(
            "Bilal Ahmed", BookingAction.APPROVE_ESTIMATE, "BF-7K2M9Q", "Lahore Auto Care"
        )
        == "Bilal Ahmed approved the estimate of BF-7K2M9Q at Lahore Auto Care."
    )
    assert booking_summary("BayFlow", BookingAction.CREATE, "BF-0000AB", "X") == (
        "BayFlow booked BF-0000AB at X."
    )


def test_summaries_and_labels_are_cut_to_their_columns() -> None:
    long_name = "N" * 400
    sentence = summary("{actor} suspended {shop}.", actor="Zainab", shop=long_name)
    assert len(sentence) == catalogue.SUMMARY_MAX_LENGTH
    assert sentence.endswith("…")
    assert label("e" * 250) == "e" * 199 + "…"
    assert label(None) is None
    assert cut("two\nlines\tand   spaces", 100) == "two lines and spaces"


@pytest.mark.parametrize("hostile", ["{actor}", "{0}", "{shop.__class__}"])
def test_names_are_never_reinterpreted_as_templates(hostile: str) -> None:
    assert summary("{actor} signed in.", actor=hostile) == f"{hostile} signed in."


def test_changed_fields_are_listed_alphabetically() -> None:
    assert changed_fields({"slot_capacity": {}, "name": {}}) == "name, slot_capacity"
    assert changed_fields({}) == "no fields"

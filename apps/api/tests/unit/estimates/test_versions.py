"""Estimate version rules (D39; `modules/estimates.md` §7.1, §7.2, §7.7): the edit-target table
(EST-11 backstop), the status sets (EST-12, EST-16, EST-17) and what customers are shown (SEC-12,
EST-22, EST-27)."""

from dataclasses import dataclass

import pytest

from app.modules.estimates.domain.versions import (
    COPYABLE_STATUSES,
    CUSTOMER_VISIBLE_STATUSES,
    DECIDABLE_STATUSES,
    FINAL_STATUSES,
    IMMUTABLE_STATUSES,
    IN_PROGRESS_STATUSES,
    OPEN_STATUSES,
    SENDABLE_STATUSES,
    SUBMITTABLE_STATUSES,
    SUPERSEDABLE_STATUSES,
    EditDecision,
    customer_shown,
    edit_target,
    revision_in_progress,
)
from app.shared.enums import BookingStatus, EstimateStatus

DRAFT = EstimateStatus.DRAFT
SUBMITTED = EstimateStatus.SUBMITTED
SENT = EstimateStatus.SENT
APPROVED = EstimateStatus.APPROVED
REJECTED = EstimateStatus.REJECTED
SUPERSEDED = EstimateStatus.SUPERSEDED

EDITABLE = {
    (BookingStatus.INSPECTING, DRAFT): EditDecision.IN_PLACE,
    (BookingStatus.ESTIMATE_REVIEW, SUBMITTED): EditDecision.NEW_VERSION,
    (BookingStatus.ESTIMATE_REVIEW, DRAFT): EditDecision.IN_PLACE,
}


@dataclass(frozen=True)
class V:
    version: int
    status: EstimateStatus


@pytest.mark.parametrize("booking_status", list(BookingStatus))
@pytest.mark.parametrize("latest_status", [None, *EstimateStatus])
def test_est_11_edit_target_table_is_exactly_spec_7_2(
    booking_status: BookingStatus, latest_status: EstimateStatus | None
) -> None:
    """EST-11 / EST-12 backstop: only the three combinations of §7.2 are editable; every other
    (booking status, latest version) pair - including no version at all - is LOCKED."""
    expected = (
        EDITABLE.get((booking_status, latest_status), EditDecision.LOCKED)
        if latest_status is not None
        else EditDecision.LOCKED
    )
    assert edit_target(booking_status, latest_status) is expected


def test_est_12_frozen_versions_are_never_editable_in_any_booking_status() -> None:
    """EST-12: `SENT`, `APPROVED`, `REJECTED`, `SUPERSEDED` are immutable whatever the caller."""
    assert {SENT, APPROVED, REJECTED, SUPERSEDED} == IMMUTABLE_STATUSES
    for booking_status in BookingStatus:
        for status in IMMUTABLE_STATUSES:
            assert edit_target(booking_status, status) is EditDecision.LOCKED


def test_status_sets_match_d39() -> None:
    assert {DRAFT, SUBMITTED, SENT} == OPEN_STATUSES  # EST-16: at most one per booking
    assert {SENT, APPROVED, REJECTED} == CUSTOMER_VISIBLE_STATUSES  # SEC-12
    assert {APPROVED, REJECTED, SUPERSEDED} == FINAL_STATUSES
    assert {DRAFT, SUBMITTED} == IN_PROGRESS_STATUSES
    assert {DRAFT} == SUBMITTABLE_STATUSES  # T06
    assert {SUBMITTED, DRAFT} == SENDABLE_STATUSES  # T07
    assert {SENT} == DECIDABLE_STATUSES  # T08/T09
    assert {REJECTED} == COPYABLE_STATUSES  # T10/T11
    assert SUPERSEDABLE_STATUSES == OPEN_STATUSES  # T22, EST-17: APPROVED/REJECTED stay
    assert OPEN_STATUSES.isdisjoint(FINAL_STATUSES)
    assert set(EstimateStatus) == OPEN_STATUSES | FINAL_STATUSES


def test_sec_12_customer_is_shown_nothing_before_a_version_is_sent() -> None:
    """SEC-12: a technician's DRAFT or a SUBMITTED version is never shown to the customer."""
    for versions in ([], [V(1, DRAFT)], [V(1, SUBMITTED)], [V(1, SUPERSEDED), V(2, DRAFT)]):
        assert customer_shown(versions) is None
        assert revision_in_progress(versions, None) is False


def test_customer_is_shown_the_newest_visible_version() -> None:
    sent_v2 = V(2, SENT)
    assert customer_shown([V(1, SUPERSEDED), sent_v2]) is sent_v2
    rejected_v2, draft_v3 = V(2, REJECTED), V(3, DRAFT)
    assert customer_shown([V(1, SUPERSEDED), rejected_v2, draft_v3]) is rejected_v2
    approved_v3 = V(3, APPROVED)
    history = [V(1, SUPERSEDED), V(2, REJECTED), approved_v3]
    assert customer_shown(history) is approved_v3
    assert customer_shown(list(reversed(history))) is approved_v3  # order of input irrelevant


def test_est_27_a_sent_version_superseded_by_a_cancellation_is_not_shown() -> None:
    """EST-27 (domain half): after T22 the cancelled `SENT` version is `SUPERSEDED` and hidden;
    an earlier rejected version stays visible."""
    assert customer_shown([V(1, SUPERSEDED)]) is None
    rejected = V(1, REJECTED)
    assert customer_shown([rejected, V(2, SUPERSEDED)]) is rejected


@pytest.mark.parametrize(
    ("versions", "expected"),
    [
        ([], False),  # nothing yet
        ([V(1, DRAFT)], False),  # technician drafting: nothing was sent yet
        ([V(1, SUBMITTED)], False),
        ([V(1, SUPERSEDED), V(2, DRAFT)], False),  # SA editing before the first send
        ([V(1, SENT)], False),  # sent, nothing newer
        ([V(1, REJECTED), V(2, DRAFT)], True),  # revise after a rejection
        ([V(1, REJECTED), V(2, SUBMITTED)], True),  # returned to the technician, resubmitted
        ([V(1, REJECTED), V(2, SUPERSEDED), V(3, DRAFT)], True),
        ([V(1, REJECTED), V(2, SENT)], False),  # the revision was sent: it is shown now
        ([V(1, REJECTED), V(2, SUPERSEDED)], False),  # cancelled after a rejection
        ([V(1, SUPERSEDED)], False),  # sent then cancelled
        ([V(1, APPROVED)], False),
    ],
)
def test_est_22_revision_in_progress_truth_table(versions: list[V], expected: bool) -> None:
    """EST-22 (domain half): true only while the customer sees a version and the shop prepares a
    newer `DRAFT` or `SUBMITTED` one; false before anything is sent and after a cancellation."""
    assert revision_in_progress(versions, customer_shown(versions)) is expected

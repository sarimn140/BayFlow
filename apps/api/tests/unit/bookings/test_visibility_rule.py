"""BK-40 (unit half): `can_view` is D21 for every role, status and assignment combination (spec 04
"Booking visibility predicate"). The SQL predicate is compared with it in
`tests/modules/bookings/test_visibility.py`."""

import itertools

import pytest

from app.modules.bookings.domain.visibility import (
    QC_QUEUE_STATUSES,
    can_view,
    needs_inspection_history,
)
from app.shared.enums import BookingStatus, MembershipRole

COMBINATIONS = list(
    itertools.product(MembershipRole, BookingStatus, [False, True], [False, True], [False, True])
)


def d21(
    role: MembershipRole,
    status: BookingStatus,
    *,
    technician: bool,
    parts_person: bool,
    inspected: bool,
) -> bool:
    """D21 written out independently of the module (spec 04's table)."""
    match role:
        case MembershipRole.OWNER | MembershipRole.SERVICE_ADVISOR:
            return True
        case MembershipRole.TECHNICIAN:
            return technician
        case MembershipRole.PARTS_PERSON:
            return parts_person
        case MembershipRole.QC_INSPECTOR:
            return status.value in {"QC_PENDING", "QC_IN_PROGRESS"} or inspected
    raise AssertionError(role)


@pytest.mark.parametrize(
    ("role", "status", "technician", "parts_person", "inspected"), COMBINATIONS
)
def test_bk40_can_view_is_d21(
    role: MembershipRole,
    status: BookingStatus,
    technician: bool,
    parts_person: bool,
    inspected: bool,
) -> None:
    expected = d21(
        role, status, technician=technician, parts_person=parts_person, inspected=inspected
    )
    actual = can_view(
        role,
        is_technician=technician,
        is_parts_person=parts_person,
        status=status,
        has_inspected=inspected,
    )
    assert actual is expected


def test_the_qc_queue_is_pending_and_in_progress() -> None:
    assert frozenset({BookingStatus.QC_PENDING, BookingStatus.QC_IN_PROGRESS}) == QC_QUEUE_STATUSES


@pytest.mark.parametrize(("role", "status"), list(itertools.product(MembershipRole, BookingStatus)))
def test_only_a_qc_inspector_outside_the_queue_needs_the_inspection_history(
    role: MembershipRole, status: BookingStatus
) -> None:
    expected = role == MembershipRole.QC_INSPECTOR and status not in QC_QUEUE_STATUSES
    assert needs_inspection_history(role, status) is expected


def test_an_unknown_role_sees_nothing() -> None:
    sees = can_view(
        "BOOKKEEPER",  # type: ignore[arg-type]
        is_technician=True,
        is_parts_person=True,
        status=BookingStatus.QC_PENDING,
        has_inspected=True,
    )
    assert sees is False

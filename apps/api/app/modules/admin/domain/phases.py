"""Booking phases (glossary §3, §5 `StatusPhase`): the UI grouping of the 17 statuses, never
stored. The admin overview counts open bookings per phase (E-61) and a shop's bookings per phase
(E-63). Pure."""

from collections.abc import Mapping
from enum import StrEnum
from typing import Final

from app.shared.enums import BookingStatus


class StatusPhase(StrEnum):
    """Glossary §5, in glossary order."""

    INTAKE = "INTAKE"
    INSPECTION = "INSPECTION"
    ESTIMATE = "ESTIMATE"
    PARTS = "PARTS"
    REPAIR_QC = "REPAIR_QC"
    HANDOVER = "HANDOVER"
    CLOSED = "CLOSED"


PHASE_OF: Final[Mapping[BookingStatus, StatusPhase]] = {
    BookingStatus.PENDING: StatusPhase.INTAKE,
    BookingStatus.CONFIRMED: StatusPhase.INTAKE,
    BookingStatus.ASSIGNED: StatusPhase.INSPECTION,
    BookingStatus.INSPECTING: StatusPhase.INSPECTION,
    BookingStatus.ESTIMATE_REVIEW: StatusPhase.ESTIMATE,
    BookingStatus.AWAITING_CUSTOMER: StatusPhase.ESTIMATE,
    BookingStatus.ESTIMATE_APPROVED: StatusPhase.ESTIMATE,
    BookingStatus.ESTIMATE_REJECTED: StatusPhase.ESTIMATE,
    BookingStatus.PARTS_PENDING: StatusPhase.PARTS,
    BookingStatus.PARTS_ORDERED: StatusPhase.PARTS,
    BookingStatus.PARTS_READY: StatusPhase.PARTS,
    BookingStatus.IN_REPAIR: StatusPhase.REPAIR_QC,
    BookingStatus.QC_PENDING: StatusPhase.REPAIR_QC,
    BookingStatus.QC_IN_PROGRESS: StatusPhase.REPAIR_QC,
    BookingStatus.READY_FOR_PICKUP: StatusPhase.HANDOVER,
    BookingStatus.COMPLETED: StatusPhase.HANDOVER,
    BookingStatus.CANCELLED: StatusPhase.CLOSED,
}
"""Every status's phase, exactly as the glossary §3 table."""


def counts_by_phase(counts: Mapping[BookingStatus, int]) -> list[tuple[StatusPhase, int]]:
    """Every phase in glossary order with the sum of its statuses' counts (zeros included)."""
    totals = dict.fromkeys(StatusPhase, 0)
    for status, count in counts.items():
        totals[PHASE_OF[status]] += count
    return list(totals.items())

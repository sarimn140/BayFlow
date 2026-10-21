"""Estimate version rules (D39; `modules/estimates.md` §7.1, §7.2, §7.7). Pure.

One `estimates` row per version. At most one version per booking is open (`DRAFT`, `SUBMITTED`,
`SENT`); `SENT`, `APPROVED`, `REJECTED` and `SUPERSEDED` are immutable; customers only ever see
`SENT`, `APPROVED` and `REJECTED`. `edit_target` decides which version an edit touches; the role
half of that rule (technician in `INSPECTING`, SA/Owner in `ESTIMATE_REVIEW`) is the bookings state
machine's, so this table is the backstop that keeps every frozen version frozen.
"""

from collections.abc import Iterable
from enum import StrEnum
from typing import Protocol

from app.shared.enums import BookingStatus, EstimateStatus

OPEN_STATUSES: frozenset[EstimateStatus] = frozenset(
    {EstimateStatus.DRAFT, EstimateStatus.SUBMITTED, EstimateStatus.SENT}
)
"""At most one version per booking (`uq_estimates_one_open_version_per_booking`, EST-16)."""

CUSTOMER_VISIBLE_STATUSES: frozenset[EstimateStatus] = frozenset(
    {EstimateStatus.SENT, EstimateStatus.APPROVED, EstimateStatus.REJECTED}
)
"""The only versions a customer (or the AI agent) ever sees (D39, SEC-12)."""

FINAL_STATUSES: frozenset[EstimateStatus] = frozenset(
    {EstimateStatus.APPROVED, EstimateStatus.REJECTED, EstimateStatus.SUPERSEDED}
)
"""Versions no action ever changes again (cancellation leaves them as they are, T22)."""

IMMUTABLE_STATUSES: frozenset[EstimateStatus] = FINAL_STATUSES | {EstimateStatus.SENT}
"""Versions whose lines and totals are frozen (D39, EST-12). A `SENT` version can still be decided
(T08/T09) or superseded by a cancellation (T22), but never edited."""

IN_PROGRESS_STATUSES: frozenset[EstimateStatus] = frozenset(
    {EstimateStatus.DRAFT, EstimateStatus.SUBMITTED}
)
"""A version the shop is still preparing: newer ones mean "revision in progress" for customers."""

SUBMITTABLE_STATUSES: frozenset[EstimateStatus] = frozenset({EstimateStatus.DRAFT})
"""T06 submits the technician's draft."""

SENDABLE_STATUSES: frozenset[EstimateStatus] = frozenset(
    {EstimateStatus.SUBMITTED, EstimateStatus.DRAFT}
)
"""T07 sends the open version: the technician's `SUBMITTED` one or the desk's `DRAFT`."""

DECIDABLE_STATUSES: frozenset[EstimateStatus] = frozenset({EstimateStatus.SENT})
"""T08/T09: the customer decides only the current `SENT` version."""

COPYABLE_STATUSES: frozenset[EstimateStatus] = frozenset({EstimateStatus.REJECTED})
"""T10/T11 copy the rejected version into a new draft."""

SUPERSEDABLE_STATUSES: frozenset[EstimateStatus] = OPEN_STATUSES
"""T22 turns every open version into `SUPERSEDED`; `APPROVED` / `REJECTED` stay (EST-17)."""


class EditDecision(StrEnum):
    """What a `PUT …/estimate` does with the booking's latest version (§7.2)."""

    IN_PLACE = "IN_PLACE"  # replace the lines of the latest DRAFT
    NEW_VERSION = "NEW_VERSION"  # supersede the SUBMITTED version, edit a new DRAFT v+1
    LOCKED = "LOCKED"  # 409 ESTIMATE_LOCKED


_EDIT_TARGETS: dict[tuple[BookingStatus, EstimateStatus], EditDecision] = {
    (BookingStatus.INSPECTING, EstimateStatus.DRAFT): EditDecision.IN_PLACE,
    (BookingStatus.ESTIMATE_REVIEW, EstimateStatus.SUBMITTED): EditDecision.NEW_VERSION,
    (BookingStatus.ESTIMATE_REVIEW, EstimateStatus.DRAFT): EditDecision.IN_PLACE,
}


def edit_target(
    booking_status: BookingStatus, latest_status: EstimateStatus | None
) -> EditDecision:
    """§7.2: the three editable combinations; every other one (incl. no version yet) is LOCKED."""
    if latest_status is None:
        return EditDecision.LOCKED
    return _EDIT_TARGETS.get((booking_status, latest_status), EditDecision.LOCKED)


class VersionLike(Protocol):
    """The two facts the visibility rules need about a version."""

    @property
    def version(self) -> int: ...

    @property
    def status(self) -> EstimateStatus: ...


def customer_shown[V: VersionLike](versions: Iterable[V]) -> V | None:
    """The customer-visible version with the highest `version`, or None (§7.7)."""
    shown: V | None = None
    for candidate in versions:
        if candidate.status not in CUSTOMER_VISIBLE_STATUSES:
            continue
        if shown is None or candidate.version > shown.version:
            shown = candidate
    return shown


def revision_in_progress(versions: Iterable[VersionLike], shown: VersionLike | None) -> bool:
    """True when the customer sees a version and the shop prepares a newer one (§7.7, EST-22).

    False before the first version is sent (the status label covers that) and after a
    cancellation, which supersedes every open version.
    """
    if shown is None:
        return False
    return any(
        candidate.status in IN_PROGRESS_STATUSES and candidate.version > shown.version
        for candidate in versions
    )

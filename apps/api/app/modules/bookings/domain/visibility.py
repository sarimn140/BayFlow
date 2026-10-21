"""Who may see a booking (D21; spec 04 "Booking visibility predicate"; `modules/bookings.md` §7.5).

Pure. One rule with three uses: the SQL predicate of lists and counts (built by the repository from
the same constants), `can_view` on item routes and actions (evaluated on the loaded or locked row,
because a locking read must stay key-only), and the realtime viewers of `list_booking_viewer_ids`.
A test asserts that `can_view` and the SQL predicate agree for every role, status and assignment.

| Staff role | Visible bookings of the shop |
|---|---|
| `OWNER`, `SERVICE_ADVISOR` | all |
| `TECHNICIAN` | `technician_user_id = me` |
| `PARTS_PERSON` | `parts_person_user_id = me` |
| `QC_INSPECTOR` | `QC_PENDING` / `QC_IN_PROGRESS`, or bookings they inspected before |

Customers see their own bookings (`customer_user_id = me`), on the customer endpoints only.
"""

from typing import Final

from app.shared.enums import BookingStatus, MembershipRole

__all__ = [
    "QC_QUEUE_STATUSES",
    "SHOP_WIDE_ROLES",
    "can_view",
    "needs_inspection_history",
]

QC_QUEUE_STATUSES: Final = frozenset({BookingStatus.QC_PENDING, BookingStatus.QC_IN_PROGRESS})
"""The shared QC queue (brief §7.4): every active QC inspector of the shop sees these bookings."""

SHOP_WIDE_ROLES: Final = frozenset({MembershipRole.OWNER, MembershipRole.SERVICE_ADVISOR})
"""Roles that see every booking of their shop (D16, D21)."""


def can_view(
    role: MembershipRole,
    *,
    is_technician: bool,
    is_parts_person: bool,
    status: BookingStatus,
    has_inspected: bool,
) -> bool:
    """Whether a staff member with `role` may see one booking of their shop (D21).

    `is_technician` / `is_parts_person`: the booking's `technician_user_id` /
    `parts_person_user_id` is the caller. `has_inspected`: the caller picked one of the booking's
    QC rounds before (only consulted for `QC_INSPECTOR`). Unknown roles see nothing (fail closed).
    """
    if role in SHOP_WIDE_ROLES:
        return True
    if role == MembershipRole.TECHNICIAN:
        return is_technician
    if role == MembershipRole.PARTS_PERSON:
        return is_parts_person
    if role == MembershipRole.QC_INSPECTOR:
        return status in QC_QUEUE_STATUSES or has_inspected
    return False


def needs_inspection_history(role: MembershipRole, status: BookingStatus) -> bool:
    """Only a QC inspector looking at a booking outside the queue needs the one extra read of its
    QC history (`qc.has_inspected`) to decide visibility."""
    return role == MembershipRole.QC_INSPECTOR and status not in QC_QUEUE_STATUSES

"""Notification deep links (pure; D67, spec 03 §3.7, spec 09 §4.10).

Each row stores the web path its recipient opens, chosen by `recipient_role`. Links are built only
from ids (UUIDs render as lower-case hex and hyphens), never from input, so every one satisfies
`ck_notifications_link_relative`: it starts with `/`, not `//`, and has no backslash. Opening a
link still runs every route check: a booking the user can no longer see answers 404.
"""

from uuid import UUID

from app.shared.enums import ActorRole, NotificationType

LINK_MAX_LENGTH = 500  # notifications.link varchar(500)


def link_for(
    recipient_role: ActorRole,
    notification_type: NotificationType,
    shop_id: UUID,
    booking_id: UUID | None,
) -> str:
    """The relative web path for this recipient (spec 03 §3.7's table). Callers in this module
    pass the ids by keyword, so the two UUIDs can never be swapped.

    Raises `ValueError` for `SYSTEM` (never a recipient) and for a booking link without a booking.
    """
    if recipient_role == ActorRole.SYSTEM:
        msg = "SYSTEM is never a notification recipient"
        raise ValueError(msg)
    if notification_type == NotificationType.AI_TASK_CREATED:
        return f"/pos/shops/{shop_id}/calls"
    if booking_id is None:
        msg = f"a {notification_type} link needs a booking"
        raise ValueError(msg)
    if recipient_role == ActorRole.CUSTOMER:
        return f"/bookings/{booking_id}"
    surface = _STAFF_SURFACES[recipient_role]
    return f"/pos/shops/{shop_id}/{surface}/{booking_id}"


_STAFF_SURFACES: dict[ActorRole, str] = {
    ActorRole.OWNER: "bookings",
    ActorRole.SERVICE_ADVISOR: "bookings",
    ActorRole.TECHNICIAN: "jobs",
    ActorRole.PARTS_PERSON: "parts",
    ActorRole.QC_INSPECTOR: "qc",
}


def is_relative_link(link: str) -> bool:
    """The `ck_notifications_link_relative` rule (and the web's `next` sanitiser, SEC-39):
    starts with `/`, not `//`, contains no backslash and fits the column."""
    return (
        link.startswith("/")
        and not link.startswith("//")
        and "\\" not in link
        and len(link) <= LINK_MAX_LENGTH
    )

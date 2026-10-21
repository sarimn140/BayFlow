"""Schemas of the notifications module (spec 03 §3.7; `modules/notifications.md`).

Wire schemas: `NotificationRead` (the bell item, D67, also the `notification.created` push data),
`UnreadCountRead` and `RealtimeTicketRead` (D70). Internal: `NotificationRecord` = a
`NotificationRead` plus its `recipient_user_id` (pushes and the seed need the addressee; never a
response), and `NewNotification`, one row to insert.
"""

import uuid
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from app.modules.notifications.domain.links import LINK_MAX_LENGTH
from app.modules.notifications.domain.messages import BODY_MAX_LENGTH, TITLE_MAX_LENGTH
from app.shared.enums import ActorRole, NotificationType
from app.shared.timestamps import Timestamp


class NotificationRead(BaseModel):
    """One notification of the caller (spec 03 §3.7). Title and body are composed by the server
    in English; clients follow `link` and never derive a route themselves (D67)."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    recipient_role: ActorRole = Field(
        description="The role the recipient is notified as (e.g. `CUSTOMER`, `TECHNICIAN`)."
    )
    link: str = Field(description="Relative web path to open for this recipient (D67).")
    shop_id: uuid.UUID | None
    shop_name: str | None
    booking_id: uuid.UUID | None
    booking_reference: str | None
    read_at: Timestamp | None
    created_at: Timestamp


class NotificationRecord(NotificationRead):
    """A notification with its addressee (internal: after-commit pushes and the seed)."""

    recipient_user_id: uuid.UUID

    def to_read(self) -> NotificationRead:
        """The wire `NotificationRead` (drops `recipient_user_id`)."""
        return NotificationRead.model_validate(self.model_dump(exclude={"recipient_user_id"}))


class UnreadCountRead(BaseModel):
    """`GET /api/v1/me/notifications/unread-count` (polled every 15 s, D14)."""

    count: int = Field(ge=0)


class RealtimeTicketRead(BaseModel):
    """`GET /api/v1/realtime/ticket` (D70): a 60-second, handshake-only WebSocket ticket."""

    ticket: str = Field(description="A JWT with `typ` = `ws`; pass it as `?ticket=` to the socket.")
    expires_in: int = Field(description="Seconds the ticket stays valid for a handshake (60).")


class NewNotification(BaseModel):
    """One row to insert (internal). `created_at` is the action's instant (D63)."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    recipient_user_id: uuid.UUID
    recipient_role: ActorRole
    shop_id: uuid.UUID
    booking_id: uuid.UUID | None
    type: NotificationType
    title: Annotated[str, StringConstraints(min_length=1, max_length=TITLE_MAX_LENGTH)]
    body: Annotated[str, StringConstraints(min_length=1, max_length=BODY_MAX_LENGTH)]
    link: Annotated[str, StringConstraints(min_length=1, max_length=LINK_MAX_LENGTH)]
    created_at: AwareDatetime

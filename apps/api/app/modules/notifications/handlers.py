"""Event subscriptions of the notifications module (D89: `register(bus)`; spec 01 "Event bus").

- `BookingActionApplied` (every transition and operation, spec 08 step 13): the rows of the trigger
  table are written **in the publisher's transaction** (they commit or roll back with the action,
  NOT-07); after the commit, `notification.created` goes to each recipient, `booking.updated` to
  the booking's viewers (even when the action has no notification type, spec 03 §6.4), and
  `ESTIMATE_SENT` / `VEHICLE_READY` are e-mailed to the customer (D26).
- `BookingPartsChanged` (D83): no row; after the commit, `booking.updated` to the viewers.

The hub, the e-mail sender and the database are reached only through `uow.app_state` (D90). With
`app_state` None (the seed, scripts, unit tests) the rows are still written but nothing is queued,
so the seed stays quiet (D51, D60). The after-commit work captures the app state and plain data —
never the request session — and opens its own short session when it needs the database. Its
failures are logged (never with an e-mail address) and never reach the request (spec 01 rule 5).
"""

import importlib.util
import logging
from collections.abc import Sequence
from functools import partial
from typing import TYPE_CHECKING
from uuid import UUID

from starlette.datastructures import State

from app.core.database import Database
from app.modules.bookings.events import BookingActionApplied, BookingPartsChanged
from app.modules.identity import service as identity_service
from app.modules.notifications import service
from app.modules.notifications.channels.email import (
    Delivery,
    OutgoingEmail,
    deliver,
    get_email_sender,
    log_skipped,
)
from app.modules.notifications.domain.messages import email_text
from app.modules.notifications.domain.recipients import EMAILED_TYPES
from app.modules.notifications.realtime import (
    CALL_INCOMING,
    CALL_UPDATED,
    TASK_CREATED,
    get_realtime_hub,
)
from app.modules.notifications.schemas import NotificationRecord
from app.shared.enums import ActorRole
from app.shared.event_bus import EventBus
from app.shared.uow import UnitOfWork

if TYPE_CHECKING:  # the calls package is optional (spec 01 rule 6)
    from app.modules.calls.events import AiTaskCreated, CallStateChanged

logger = logging.getLogger(__name__)


def register(bus: EventBus) -> None:
    """Subscribe this module's handlers (called by `app.main.wire_modules()`, after bookings')."""
    bus.subscribe(BookingActionApplied, on_booking_action_applied)
    bus.subscribe(BookingPartsChanged, on_booking_parts_changed)
    if calls_installed():
        register_call_handlers(bus)


def calls_installed() -> bool:
    """The optional calls package exists (spec 01 rule 6; checked on the package itself)."""
    return importlib.util.find_spec("app.modules.calls") is not None


def register_call_handlers(bus: EventBus) -> None:
    """P2: `CallStateChanged` and `AiTaskCreated` (imported here, never at module import)."""
    from app.modules.calls.events import AiTaskCreated, CallStateChanged  # noqa: PLC0415

    bus.subscribe(CallStateChanged, on_call_state_changed)
    bus.subscribe(AiTaskCreated, on_ai_task_created)


async def on_call_state_changed(event: "CallStateChanged", uow: UnitOfWork) -> None:
    rows = await service.create_for_call_event(uow, event)
    state = uow.app_state
    if state is None:
        return
    uow.after_commit(partial(after_call_event, state, event, tuple(rows)))


async def on_ai_task_created(event: "AiTaskCreated", uow: UnitOfWork) -> None:
    rows = await service.create_for_ai_task(uow, event)
    state = uow.app_state
    if state is None:
        return
    uow.after_commit(partial(after_ai_task, state, event.task_id, tuple(rows)))


async def on_booking_action_applied(event: BookingActionApplied, uow: UnitOfWork) -> None:
    rows = await service.create_for_booking_action(uow, event)
    state = uow.app_state
    if state is None:
        return
    uow.after_commit(
        partial(after_booking_action, state, event.shop_id, event.booking_id, tuple(rows))
    )


async def on_booking_parts_changed(event: BookingPartsChanged, uow: UnitOfWork) -> None:
    state = uow.app_state
    if state is None:
        return
    uow.after_commit(partial(push_booking_updated, state, event.shop_id, event.booking_id))


# --- After commit (background tasks; each step guarded) -------------------------------------------


async def push_notifications(state: State, rows: Sequence[NotificationRecord]) -> None:
    try:
        await get_realtime_hub(state).push_notifications(rows)
    except Exception:
        logger.exception("realtime.push_notifications_failed")


async def push_booking_updated(state: State, shop_id: UUID, booking_id: UUID) -> None:
    try:
        await get_realtime_hub(state).push_booking_updated(shop_id, booking_id)
    except Exception:
        logger.exception(
            "realtime.push_booking_updated_failed", extra={"booking_id": str(booking_id)}
        )


async def email_notification(state: State, row: NotificationRecord) -> Delivery:
    """E-mail one row to its recipient (the customer). The address is read now, with its own
    session; the link is built on `CLIENT_URL` (spec 04). Never raises."""
    try:
        sender = get_email_sender(state)
        if sender.provider == "none":
            return log_skipped(row.id, Delivery.SKIPPED_DISABLED)
        database = getattr(state, "db", None)
        if not isinstance(database, Database):
            msg = "the database is not initialised"
            raise RuntimeError(msg)
        async with database.sessionmaker() as session:
            user = await identity_service.get_user(session, row.recipient_user_id)
        if user is None:
            return log_skipped(row.id, Delivery.SKIPPED_NO_ADDRESS)
        email = OutgoingEmail(
            to=user.email,
            subject=row.title,
            text=email_text(row.body, row.link, state.settings.client_url),
            idempotency_key=str(row.id),
        )
    except Exception as exc:
        logger.warning(
            "email.failed", extra={"notification_id": str(row.id), "error": type(exc).__name__}
        )
        return Delivery.FAILED
    return await deliver(sender, email, notification_id=row.id)


def emailed(rows: Sequence[NotificationRecord]) -> list[NotificationRecord]:
    """The rows that are also e-mailed: `ESTIMATE_SENT` / `VEHICLE_READY` to the customer (D26)."""
    return [
        row
        for row in rows
        if row.type in EMAILED_TYPES and row.recipient_role == ActorRole.CUSTOMER
    ]


async def after_booking_action(
    state: State, shop_id: UUID, booking_id: UUID, rows: Sequence[NotificationRecord]
) -> None:
    """Spec 08 step 15, in order: `notification.created`, `booking.updated`, then the e-mails."""
    await push_notifications(state, rows)
    await push_booking_updated(state, shop_id, booking_id)
    for row in emailed(rows):
        await email_notification(state, row)


# --- P2: calls (spec 05 §8.4) -------------------------------------------------------------------


def _database_of(state: State) -> Database:
    database = getattr(state, "db", None)
    if not isinstance(database, Database):
        msg = "the database is not initialised"
        raise RuntimeError(msg)
    return database


async def after_call_event(
    state: State, event: "CallStateChanged", rows: Sequence[NotificationRecord]
) -> None:
    """`call.incoming` to the rung users (C1) or `call.updated` to the caller, the answerer and
    everyone rung; then `notification.created` for any `CALL_MISSED` rows."""
    from app.modules.calls import service as calls_service  # noqa: PLC0415

    try:
        async with _database_of(state).sessionmaker() as session:
            call = await calls_service.get_call_read(session, event.call_id)
        if call is not None:
            data = call.model_dump(mode="json")
            hub = get_realtime_hub(state)
            if event.previous_status is None:
                await hub.send_to_users(event.rung_user_ids, {"type": CALL_INCOMING, "data": data})
            else:
                targets = {event.caller_user_id, *event.rung_user_ids}
                if event.answered_by_user_id is not None:
                    targets.add(event.answered_by_user_id)
                await hub.send_to_users(targets, {"type": CALL_UPDATED, "data": data})
    except Exception:
        logger.exception("realtime.push_call_failed", extra={"call_id": str(event.call_id)})
    await push_notifications(state, rows)


async def after_ai_task(state: State, task_id: UUID, rows: Sequence[NotificationRecord]) -> None:
    """`task.created` (`TaskRead`) to the SAs notified, then `notification.created`."""
    from app.modules.calls import service as calls_service  # noqa: PLC0415

    try:
        async with _database_of(state).sessionmaker() as session:
            task = await calls_service.get_task_read(session, task_id)
        if task is not None:
            await get_realtime_hub(state).send_to_users(
                [row.recipient_user_id for row in rows],
                {"type": TASK_CREATED, "data": task.model_dump(mode="json")},
            )
    except Exception:
        logger.exception("realtime.push_task_failed", extra={"task_id": str(task_id)})
    await push_notifications(state, rows)

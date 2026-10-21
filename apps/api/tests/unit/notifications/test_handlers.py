"""The module's event subscriptions and after-commit callbacks, without a database (D89, D90).

`register(bus)` subscribes exactly `BookingActionApplied` and `BookingPartsChanged`; with
`app_state` None nothing is queued; otherwise one callback per action, which captures the app
state and plain data (never the session) and runs, in order, `notification.created`,
`booking.updated` and the e-mails, each step isolated from the others' failures.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.datastructures import State

from app.modules.bookings.events import BookingActionApplied, BookingPartsChanged
from app.modules.notifications import handlers, service
from app.modules.notifications.channels.email import Delivery
from app.modules.notifications.realtime import RealtimeHub, get_realtime_hub
from app.modules.notifications.schemas import NotificationRecord
from app.shared.enums import ActorRole, BookingAction, BookingStatus, NotificationType
from app.shared.event_bus import EventBus
from app.shared.uow import UnitOfWork
from tests.conftest import make_settings

NOW = datetime(2026, 10, 16, 5, 0, tzinfo=UTC)
SHOP, BOOKING, CUSTOMER = (uuid.uuid4() for _ in range(3))


class FakeSession:
    """The unit of work only needs commit/rollback; the handlers never touch it here."""

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def make_uow(state: State | None) -> UnitOfWork:
    return UnitOfWork(FakeSession(), EventBus(), app_state=state)  # type: ignore[arg-type]


def action_event(action: BookingAction = BookingAction.NOTIFY_READY) -> BookingActionApplied:
    return BookingActionApplied(
        occurred_at=NOW,
        shop_id=SHOP,
        booking_id=BOOKING,
        reference="BF-7KQ2MX",
        action=action,
        from_status=BookingStatus.READY_FOR_PICKUP,
        to_status=BookingStatus.READY_FOR_PICKUP,
        version=7,
        actor_user_id=uuid.uuid4(),
        actor_role=ActorRole.SERVICE_ADVISOR,
        customer_user_id=CUSTOMER,
        technician_user_id=None,
        parts_person_user_id=None,
        qc_inspector_user_id=None,
        note=None,
    )


def record(
    notification_type: NotificationType = NotificationType.VEHICLE_READY,
    role: ActorRole = ActorRole.CUSTOMER,
) -> NotificationRecord:
    return NotificationRecord(
        id=uuid.uuid4(),
        type=notification_type,
        title="t",
        body="b",
        recipient_role=role,
        link="/bookings/x",
        shop_id=SHOP,
        shop_name="Lahore Auto Care",
        booking_id=BOOKING,
        booking_reference="BF-7KQ2MX",
        read_at=None,
        created_at=NOW,
        recipient_user_id=CUSTOMER,
    )


def test_register_subscribes_the_two_booking_events() -> None:
    bus = EventBus()
    handlers.register(bus)
    assert bus.handlers_for(BookingActionApplied) == (handlers.on_booking_action_applied,)
    assert bus.handlers_for(BookingPartsChanged) == (handlers.on_booking_parts_changed,)


@pytest.fixture
def rows(monkeypatch: pytest.MonkeyPatch) -> list[NotificationRecord]:
    """`create_for_booking_action` stubbed: the rows are a DB concern (module DB tests)."""
    created = [record()]

    async def fake_create(uow: UnitOfWork, event: BookingActionApplied) -> list[NotificationRecord]:
        return created

    monkeypatch.setattr(service, "create_for_booking_action", fake_create)
    return created


async def test_without_app_state_rows_are_written_and_nothing_is_queued(
    rows: list[NotificationRecord],
) -> None:
    uow = make_uow(None)
    await handlers.on_booking_action_applied(action_event(), uow)
    await handlers.on_booking_parts_changed(
        BookingPartsChanged(
            occurred_at=NOW,
            shop_id=SHOP,
            booking_id=BOOKING,
            status=BookingStatus.PARTS_ORDERED,
            version=3,
        ),
        uow,
    )
    assert uow._after_commit == []


async def test_with_app_state_one_callback_is_queued_per_event(
    rows: list[NotificationRecord],
) -> None:
    uow = make_uow(State())
    await handlers.on_booking_action_applied(action_event(), uow)
    await handlers.on_booking_action_applied(action_event(BookingAction.START_REPAIR), uow)
    assert len(uow._after_commit) == 2  # also for an action without a type (booking.updated)


async def test_the_callback_runs_the_three_steps_in_order(
    rows: list[NotificationRecord], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []

    async def push_notifications(self: RealtimeHub, pushed: list[NotificationRecord]) -> int:
        calls.append(("notification.created", list(pushed)))
        return 1

    async def push_booking_updated(
        self: RealtimeHub, shop_id: uuid.UUID, booking_id: uuid.UUID
    ) -> int:
        calls.append(("booking.updated", shop_id, booking_id))
        return 1

    async def email(state: State, row: NotificationRecord) -> Delivery:
        calls.append(("email", row.id))
        return Delivery.SENT

    monkeypatch.setattr(RealtimeHub, "push_notifications", push_notifications)
    monkeypatch.setattr(RealtimeHub, "push_booking_updated", push_booking_updated)
    monkeypatch.setattr(handlers, "email_notification", email)
    state = State()
    uow = make_uow(state)

    await handlers.on_booking_action_applied(action_event(), uow)
    [callback] = uow._after_commit
    await callback()

    assert calls == [
        ("notification.created", rows),
        ("booking.updated", SHOP, BOOKING),
        ("email", rows[0].id),
    ]
    assert isinstance(state.realtime_hub, RealtimeHub)  # created on first use (D90)


async def test_a_failing_step_does_not_stop_the_next_ones(
    rows: list[NotificationRecord],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    emailed: list[uuid.UUID] = []

    async def broken(self: RealtimeHub, *args: object) -> int:
        msg = "hub broken"
        raise RuntimeError(msg)

    async def email(state: State, row: NotificationRecord) -> Delivery:
        emailed.append(row.id)
        return Delivery.SENT

    monkeypatch.setattr(RealtimeHub, "push_notifications", broken)
    monkeypatch.setattr(RealtimeHub, "push_booking_updated", broken)
    monkeypatch.setattr(handlers, "email_notification", email)

    await handlers.after_booking_action(State(), SHOP, BOOKING, rows)  # never raises

    assert emailed == [rows[0].id]
    messages = [r.getMessage() for r in caplog.records]
    assert "realtime.push_notifications_failed" in messages
    assert "realtime.push_booking_updated_failed" in messages


async def test_parts_changed_queues_booking_updated_only(monkeypatch: pytest.MonkeyPatch) -> None:
    pushed: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def push_booking_updated(
        self: RealtimeHub, shop_id: uuid.UUID, booking_id: uuid.UUID
    ) -> int:
        pushed.append((shop_id, booking_id))
        return 0

    monkeypatch.setattr(RealtimeHub, "push_booking_updated", push_booking_updated)
    state = State()
    uow = make_uow(state)
    event = BookingPartsChanged(
        occurred_at=NOW,
        shop_id=SHOP,
        booking_id=BOOKING,
        status=BookingStatus.PARTS_ORDERED,
        version=3,
    )

    await handlers.on_booking_parts_changed(event, uow)
    [callback] = uow._after_commit
    await callback()

    assert pushed == [(SHOP, BOOKING)]
    assert get_realtime_hub(state) is state.realtime_hub


def test_only_estimate_sent_and_vehicle_ready_to_the_customer_are_emailed() -> None:
    candidates = [
        record(NotificationType.ESTIMATE_SENT),
        record(NotificationType.VEHICLE_READY),
        record(NotificationType.BOOKING_CONFIRMED),
        record(NotificationType.BOOKING_CANCELLED),
        record(NotificationType.VEHICLE_READY, ActorRole.SERVICE_ADVISOR),
    ]
    assert handlers.emailed(candidates) == candidates[:2]


async def test_email_with_provider_none_reads_nothing(caplog: pytest.LogCaptureFixture) -> None:
    """No database on the state: provider `none` must not even look up the address."""
    state = State()
    state.settings = make_settings()
    row = record()
    assert await handlers.email_notification(state, row) == Delivery.SKIPPED_DISABLED


async def test_email_failures_before_sending_are_logged_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    state = State()
    state.settings = make_settings(email_provider="http", email_api_key="re_key")  # no db
    assert await handlers.email_notification(state, record()) == Delivery.FAILED
    [failure] = [r for r in caplog.records if r.getMessage() == "email.failed"]
    assert failure.error == "RuntimeError"

"""Wire schemas of the notifications module (spec 03 §3.7) and the internal insert payload."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.modules.notifications.schemas import (
    NewNotification,
    NotificationRead,
    NotificationRecord,
    RealtimeTicketRead,
    UnreadCountRead,
)
from app.shared.enums import ActorRole, NotificationType

CREATED = datetime(2026, 10, 16, 5, 0, 0, 123456, tzinfo=UTC)


def record(**overrides: object) -> NotificationRecord:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "type": NotificationType.ESTIMATE_SENT,
        "title": "Your estimate is ready — BF-7KQ2MX",
        "body": "Lahore Auto Care sent estimate v2: PKR 16,100.",
        "recipient_role": ActorRole.CUSTOMER,
        "link": "/bookings/1",
        "shop_id": uuid.uuid4(),
        "shop_name": "Lahore Auto Care",
        "booking_id": uuid.uuid4(),
        "booking_reference": "BF-7KQ2MX",
        "read_at": None,
        "created_at": CREATED,
        "recipient_user_id": uuid.uuid4(),
    }
    values.update(overrides)
    return NotificationRecord.model_validate(values)


def test_notification_read_serialises_in_the_spec_order_with_utc_z_timestamps() -> None:
    read = record(read_at=datetime(2026, 10, 16, 6, 0, tzinfo=UTC)).to_read()
    data = read.model_dump(mode="json")
    assert type(read) is NotificationRead
    assert list(data) == [
        "id",
        "type",
        "title",
        "body",
        "recipient_role",
        "link",
        "shop_id",
        "shop_name",
        "booking_id",
        "booking_reference",
        "read_at",
        "created_at",
    ]
    assert data["created_at"] == "2026-10-16T05:00:00.123Z"
    assert data["read_at"] == "2026-10-16T06:00:00Z"
    assert data["type"] == "ESTIMATE_SENT"
    assert data["recipient_role"] == "CUSTOMER"


def test_a_record_is_a_notification_read_with_its_addressee() -> None:
    row = record()
    assert isinstance(row, NotificationRead)
    assert "recipient_user_id" in row.model_dump()
    assert "recipient_user_id" not in row.to_read().model_dump()


def test_small_read_models() -> None:
    assert UnreadCountRead(count=3).model_dump() == {"count": 3}
    with pytest.raises(ValidationError):
        UnreadCountRead(count=-1)
    assert RealtimeTicketRead(ticket="t", expires_in=60).model_dump() == {
        "ticket": "t",
        "expires_in": 60,
    }


def new(**overrides: object) -> NewNotification:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "recipient_user_id": uuid.uuid4(),
        "recipient_role": ActorRole.TECHNICIAN,
        "shop_id": uuid.uuid4(),
        "booking_id": uuid.uuid4(),
        "type": NotificationType.QC_FAILED,
        "title": "QC failed — BF-7KQ2MX",
        "body": "Sara returned the job with an issue to fix.",
        "link": "/pos/shops/1/jobs/2",
        "created_at": CREATED,
    }
    values.update(overrides)
    return NewNotification.model_validate(values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "x" * 161},
        {"body": "x" * 1001},
        {"link": "/" + "x" * 500},
        {"title": ""},
        {"created_at": datetime(2026, 10, 16, 5, 0)},  # noqa: DTZ001 - a naive instant on purpose
    ],
)
def test_new_notification_guards_the_column_rules(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        new(**overrides)


def test_new_notification_accepts_the_column_maximums() -> None:
    row = new(title="x" * 160, body="y" * 1000, link="/" + "z" * 499)
    assert (len(row.title), len(row.body), len(row.link)) == (160, 1000, 500)

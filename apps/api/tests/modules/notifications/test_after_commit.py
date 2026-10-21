"""After-commit work on PostgreSQL: pushes through the per-app hub (fake sockets) and e-mail.

NOT-08 (`notification.created` to each recipient; `booking.updated` to the booking's viewers, also
for parts changes without a status change, D83; nothing for a rolled-back action), NOT-12 / SEC-33
(hub side: nobody outside D21 at push time), SEC-13 (a deactivated member receives nothing), NOT-18
(`BookingPartsChanged`: no row, `booking.updated` to the viewers; a general restock pushes
nothing), NOT-20 (a failing socket is dropped; the action's HTTP response is unchanged) and NOT-09
(e-mail only for `ESTIMATE_SENT` / `VEHICLE_READY` to the customer through `smtp` / `http`; `none`
and reserved domains never attempted; a provider failure never fails the action; no address in the
logs). Every test here pushes through the D90 path: `UnitOfWork(app_state=state)`.
"""

import json
import logging
import uuid
from datetime import timedelta
from typing import Any, ClassVar

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
from sqlalchemy import update
from starlette.datastructures import State

from app.modules.bookings.events import BookingActionApplied
from app.modules.bookings.models import Booking
from app.modules.identity import service as identity_service
from app.modules.identity.models import User
from app.modules.inventory.events import PurchaseOrderReceived
from app.modules.notifications.channels import email as email_channel
from app.modules.notifications.channels.email import HttpEmailSender, SmtpEmailSender
from app.modules.notifications.realtime import RealtimeHub, get_realtime_hub
from app.modules.qc.models import QcInspection
from app.shared.enums import ActorRole, BookingAction, BookingStatus, QcResult
from app.shared.uow import UnitOfWork, UowDep, drain_after_commit_tasks, pending_after_commit_tasks
from tests.conftest import make_settings
from tests.modules.notifications.support import (
    FakeSocket,
    World,
    app_state,
    applied,
    next_instant,
    notifications_bus,
    parts_changed,
    publish,
)

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("booking_reads")]

A = BookingAction
R = ActorRole
S = BookingStatus


@pytest.fixture
def state(world: World) -> State:
    return app_state(world.db)


@pytest.fixture
def hub(state: State) -> RealtimeHub:
    return get_realtime_hub(state)


def everyone(world: World) -> list[User]:
    a, b = world.a, world.b
    return [
        world.ayesha,
        world.ahmed,
        *(
            getattr(cast, name)
            for cast in (a, b)
            for name in (
                "owner",
                "advisor",
                "advisor_2",
                "technician",
                "technician_2",
                "parts",
                "parts_2",
                "inspector",
                "inspector_2",
            )
        ),
    ]


@pytest.fixture
def sockets(world: World, hub: RealtimeHub) -> dict[uuid.UUID, FakeSocket]:
    """One open (fake) socket per person of the world."""
    connected: dict[uuid.UUID, FakeSocket] = {}
    for user in everyone(world):
        socket = FakeSocket()
        hub.connect(user.id, socket)  # type: ignore[arg-type]
        connected[user.id] = socket
    return connected


async def perform(
    world: World,
    booking: Booking,
    event: BookingActionApplied,
    *,
    state: State | None,
    **booking_values: Any,
) -> None:
    """One booking action: the executor's booking update and the event, in one transaction."""
    async with world.db.sessionmaker() as session:
        uow = UnitOfWork(session, notifications_bus(), app_state=state)
        if booking_values:
            await session.execute(
                update(Booking).where(Booking.id == booking.id).values(**booking_values)
            )
        await uow.publish(event)
        await uow.commit()
    await drain_after_commit_tasks()


def receivers(sockets: dict[uuid.UUID, FakeSocket], kind: str) -> set[uuid.UUID]:
    return {user_id for user_id, socket in sockets.items() if socket.of_type(kind)}


def ids(*users: User) -> set[uuid.UUID]:
    return {user.id for user in users}


# --- NOT-08: what each socket receives ------------------------------------------------------------


async def test_not08_notification_created_reaches_each_recipient_with_the_row(
    world: World, state: State, sockets: dict[uuid.UUID, FakeSocket]
) -> None:
    a = world.a
    booking = await world.job(a)
    event = applied(booking, A.SEND_TO_QC, actor=a.technician, actor_role=R.TECHNICIAN)

    await perform(world, booking, event, state=state, status=S.QC_PENDING, version=2)

    rows = {row.recipient_user_id: row for row in await world.notifications(booking)}
    assert receivers(sockets, "notification.created") == ids(a.inspector, a.inspector_2)
    for inspector in (a.inspector, a.inspector_2):
        [message] = sockets[inspector.id].of_type("notification.created")
        row = rows[inspector.id]
        assert message == {
            "type": "notification.created",
            "data": {
                "id": str(row.id),
                "type": "QC_REQUESTED",
                "title": row.title,
                "body": row.body,
                "recipient_role": "QC_INSPECTOR",
                "link": f"/pos/shops/{a.id}/qc/{booking.id}",
                "shop_id": str(a.id),
                "shop_name": "Lahore Auto Care",
                "booking_id": str(booking.id),
                "booking_reference": booking.reference,
                "read_at": None,
                "created_at": event.occurred_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        }


async def test_not08_booking_updated_reaches_the_viewers_with_the_state_at_push_time(
    world: World, state: State, sockets: dict[uuid.UUID, FakeSocket]
) -> None:
    a = world.a
    booking = await world.job(a)
    event = applied(booking, A.SEND_TO_QC, actor=a.technician, actor_role=R.TECHNICIAN)

    await perform(world, booking, event, state=state, status=S.QC_PENDING, version=2)

    viewers = ids(world.ayesha, a.owner, a.advisor, a.advisor_2, a.technician, a.parts)
    viewers |= ids(a.inspector, a.inspector_2)  # QC_PENDING: the queue sees it
    assert receivers(sockets, "booking.updated") == viewers
    expected = {
        "type": "booking.updated",
        "data": {
            "booking_id": str(booking.id),
            "shop_id": str(a.id),
            "status": "QC_PENDING",
            "version": 2,
        },
    }
    for user_id in viewers:
        assert sockets[user_id].of_type("booking.updated") == [expected]
    # One callback per action, in spec 08 step 15's order: the row first, then the booking.
    assert [message["type"] for message in sockets[a.inspector.id].messages] == [
        "notification.created",
        "booking.updated",
    ]


async def test_not08_an_action_without_a_type_still_pushes_booking_updated(
    world: World, state: State, sockets: dict[uuid.UUID, FakeSocket]
) -> None:
    a = world.a
    booking = await world.job(a)
    event = applied(booking, A.START_REPAIR, actor=a.technician, actor_role=R.TECHNICIAN)

    await perform(world, booking, event, state=state, version=2)

    assert receivers(sockets, "notification.created") == set()
    assert receivers(sockets, "booking.updated") == ids(
        world.ayesha, a.owner, a.advisor, a.advisor_2, a.technician, a.parts
    )


async def test_not07_nothing_is_pushed_for_a_rolled_back_action(
    world: World, state: State, sockets: dict[uuid.UUID, FakeSocket]
) -> None:
    booking = await world.job(world.a)
    async with world.db.sessionmaker() as session:
        uow = UnitOfWork(session, notifications_bus(), app_state=state)
        await uow.publish(applied(booking, A.CANCEL, actor=world.ayesha, actor_role=R.CUSTOMER))
        await uow.rollback()
        assert pending_after_commit_tasks() == 0
    await drain_after_commit_tasks()

    assert all(not socket.frames for socket in sockets.values())
    assert await world.notifications(booking) == []


async def test_not07_nothing_is_pushed_when_a_later_step_fails(
    world: World, state: State, sockets: dict[uuid.UUID, FakeSocket]
) -> None:
    booking = await world.job(world.a)
    bus = notifications_bus()

    async def fails(event: BookingActionApplied, uow: UnitOfWork) -> None:
        msg = "the action failed after the rows"
        raise RuntimeError(msg)

    bus.subscribe(BookingActionApplied, fails)

    async def action() -> None:
        await publish(
            world.db,
            applied(booking, A.NOTIFY_READY, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR),
            state=state,
            bus=bus,
        )

    with pytest.raises(RuntimeError, match="failed after the rows"):
        await action()
    await drain_after_commit_tasks()

    assert all(not socket.frames for socket in sockets.values())
    assert await world.notifications(booking) == []


# --- NOT-12 / SEC-33 / SEC-13: D21 at push time ---------------------------------------------------


async def test_not12_outsiders_receive_nothing(
    world: World, state: State, sockets: dict[uuid.UUID, FakeSocket]
) -> None:
    a, b = world.a, world.b
    booking = await world.job(a)  # IN_REPAIR, Imran and Usman, never inspected
    await perform(
        world,
        booking,
        applied(booking, A.START_REPAIR, actor=a.technician, actor_role=R.TECHNICIAN),
        state=state,
        version=2,
    )

    outsiders = ids(a.technician_2, a.parts_2, a.inspector, a.inspector_2, world.ahmed)
    outsiders |= ids(b.owner, b.advisor, b.advisor_2, b.technician, b.technician_2, b.parts)
    outsiders |= ids(b.parts_2, b.inspector, b.inspector_2)
    reached = receivers(sockets, "booking.updated")
    assert reached == ids(world.ayesha, a.owner, a.advisor, a.advisor_2, a.technician, a.parts)
    assert not reached & outsiders


async def test_not12_an_inspector_who_inspected_keeps_seeing_the_booking(
    world: World, state: State, sockets: dict[uuid.UUID, FakeSocket]
) -> None:
    a = world.a
    booking = await world.job(a)
    async with world.db.sessionmaker() as session:
        moment = next_instant()
        session.add(
            QcInspection(
                shop_id=a.id,
                booking_id=booking.id,
                inspector_user_id=a.inspector_2.id,
                picked_at=moment,
                completed_at=moment + timedelta(minutes=5),
                result=QcResult.FAIL,
            )
        )
        await session.commit()

    await perform(
        world,
        booking,
        applied(booking, A.START_REPAIR, actor=a.technician, actor_role=R.TECHNICIAN),
        state=state,
        version=2,
    )

    reached = receivers(sockets, "booking.updated")
    assert a.inspector_2.id in reached  # inspected it before (D21)
    assert a.inspector.id not in reached  # outside the queue and never inspected it


async def test_sec13_a_deactivated_member_receives_nothing_until_reactivated(
    world: World, state: State, sockets: dict[uuid.UUID, FakeSocket]
) -> None:
    a = world.a
    booking = await world.job(a)
    await world.set_membership_active(a.shop, a.technician, active=False)

    await perform(
        world,
        booking,
        applied(booking, A.ALLOCATE_PARTS, actor=a.parts, actor_role=R.PARTS_PERSON),
        state=state,
        version=2,
    )

    assert not sockets[a.technician.id].frames  # neither a row nor `booking.updated`
    assert a.parts.id in receivers(sockets, "booking.updated")

    await world.set_membership_active(a.shop, a.technician, active=True)  # live state (D9)
    await perform(
        world,
        booking,
        applied(booking, A.START_REPAIR, actor=a.technician, actor_role=R.TECHNICIAN),
        state=state,
        version=3,
    )
    assert [m["type"] for m in sockets[a.technician.id].messages] == ["booking.updated"]


# --- NOT-18 / D83 ---------------------------------------------------------------------------------


async def test_not18_parts_changed_pushes_booking_updated_to_the_viewers_and_writes_no_row(
    world: World, state: State, sockets: dict[uuid.UUID, FakeSocket]
) -> None:
    a = world.a
    booking = await world.booking(a, status=S.PARTS_ORDERED, technician=a.technician, parts=a.parts)

    await publish(world.db, parts_changed(booking), state=state)
    await drain_after_commit_tasks()

    assert await world.notifications() == []
    assert receivers(sockets, "notification.created") == set()
    viewers = ids(world.ayesha, a.owner, a.advisor, a.advisor_2, a.technician, a.parts)
    assert receivers(sockets, "booking.updated") == viewers
    for user_id in viewers:
        assert sockets[user_id].of_type("booking.updated") == [
            {
                "type": "booking.updated",
                "data": {
                    "booking_id": str(booking.id),
                    "shop_id": str(a.id),
                    "status": "PARTS_ORDERED",
                    "version": booking.version,  # unchanged: no booking event (D30)
                },
            }
        ]


async def test_not18_a_general_restock_receipt_pushes_nothing(
    world: World, state: State, sockets: dict[uuid.UUID, FakeSocket]
) -> None:
    receipt = PurchaseOrderReceived(
        occurred_at=next_instant(),
        shop_id=world.a.id,
        purchase_order_id=uuid.uuid4(),
        po_number="PO-REST01",
        booking_id=None,
        received=(),
        actor_user_id=world.a.parts.id,
    )

    await publish(world.db, receipt, state=state)
    await drain_after_commit_tasks()

    assert all(not socket.frames for socket in sockets.values())
    assert await world.notifications() == []


async def test_without_app_state_nothing_is_pushed(
    world: World, sockets: dict[uuid.UUID, FakeSocket]
) -> None:
    booking = await world.job(world.a)

    await publish(world.db, parts_changed(booking), state=None)
    await perform(
        world,
        booking,
        applied(booking, A.SEND_TO_QC, actor=world.a.technician, actor_role=R.TECHNICIAN),
        state=None,
    )

    assert all(not socket.frames for socket in sockets.values())
    assert len(await world.notifications(booking)) == 2  # the rows are still written


async def test_pushes_reach_only_the_hub_of_their_own_app(world: World) -> None:
    """D90: one hub per app; an action reaches the sockets of the app that ran it."""
    first, second = app_state(world.db), app_state(world.db)
    booking = await world.job(world.a)
    socket_one, socket_two = FakeSocket(), FakeSocket()
    get_realtime_hub(first).connect(world.ayesha.id, socket_one)  # type: ignore[arg-type]
    get_realtime_hub(second).connect(world.ayesha.id, socket_two)  # type: ignore[arg-type]

    await perform(
        world,
        booking,
        applied(booking, A.NOTIFY_READY, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR),
        state=first,
    )

    assert [m["type"] for m in socket_one.messages] == ["notification.created", "booking.updated"]
    assert socket_two.frames == []


# --- NOT-20: dead sockets -------------------------------------------------------------------------


async def test_not20_a_failing_socket_is_dropped_and_the_others_still_receive(
    world: World, state: State, hub: RealtimeHub
) -> None:
    a = world.a
    booking = await world.job(a)
    broken, healthy, other_tab = FakeSocket(fail=True), FakeSocket(), FakeSocket()
    hub.connect(a.advisor.id, broken)  # type: ignore[arg-type]
    hub.connect(a.advisor.id, other_tab)  # type: ignore[arg-type]
    hub.connect(a.advisor_2.id, healthy)  # type: ignore[arg-type]

    await perform(
        world,
        booking,
        applied(booking, A.PASS_QC, actor=a.inspector, actor_role=R.QC_INSPECTOR),
        state=state,
        status=S.READY_FOR_PICKUP,
        qc_inspector_user_id=a.inspector.id,
        version=2,
    )

    assert not hub.is_connected(a.advisor.id, broken)  # type: ignore[arg-type]
    assert broken.closed_with == 1011
    assert [m["type"] for m in other_tab.messages] == ["notification.created", "booking.updated"]
    assert [m["type"] for m in healthy.messages] == ["notification.created", "booking.updated"]
    assert len(await world.notifications(booking)) == 2  # the action itself is unaffected


class ProbeAction(BaseModel):
    booking_id: uuid.UUID
    action: BookingAction
    actor_user_id: uuid.UUID
    actor_role: ActorRole
    metadata: dict[str, Any] = {}


probe = APIRouter(prefix="/api/v1/_probe", tags=["test"])


@probe.post("/actions")
async def probe_action(body: ProbeAction, uow: UowDep) -> dict[str, Any]:
    """Stands in for a booking action route: bump the booking, publish, commit, respond."""
    booking = await uow.session.get(Booking, body.booking_id)
    assert booking is not None
    version = booking.version + 1
    await uow.session.execute(
        update(Booking).where(Booking.id == booking.id).values(version=version)
    )
    await uow.publish(
        BookingActionApplied(
            occurred_at=next_instant(),
            shop_id=booking.shop_id,
            booking_id=booking.id,
            reference=booking.reference,
            action=body.action,
            from_status=booking.status,
            to_status=booking.status,
            version=version,
            actor_user_id=body.actor_user_id,
            actor_role=body.actor_role,
            customer_user_id=booking.customer_user_id,
            technician_user_id=booking.technician_user_id,
            parts_person_user_id=booking.parts_person_user_id,
            qc_inspector_user_id=booking.qc_inspector_user_id,
            note=None,
            metadata=body.metadata,
        )
    )
    await uow.commit()
    return {"booking_id": str(booking.id), "version": version}


@pytest.fixture
async def probe_app(db_app: FastAPI) -> FastAPI:
    db_app.include_router(probe)
    return db_app


async def test_not20_the_http_response_is_unchanged_by_a_dead_socket(
    probe_app: FastAPI, db_client: httpx.AsyncClient, world: World
) -> None:
    a = world.a
    booking = await world.job(a)
    hub = get_realtime_hub(probe_app.state)
    broken, healthy = FakeSocket(fail=True), FakeSocket()
    hub.connect(world.ayesha.id, broken)  # type: ignore[arg-type]
    hub.connect(a.advisor.id, healthy)  # type: ignore[arg-type]
    body = {
        "booking_id": str(booking.id),
        "action": "NOTIFY_READY",
        "actor_user_id": str(a.advisor.id),
        "actor_role": "SERVICE_ADVISOR",
    }

    first = await db_client.post("/api/v1/_probe/actions", json=body)
    await drain_after_commit_tasks()
    second = await db_client.post("/api/v1/_probe/actions", json=body)
    await drain_after_commit_tasks()

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json() == {"booking_id": str(booking.id), "version": 2}
    assert second.json() == {"booking_id": str(booking.id), "version": 3}
    assert broken.closed_with == 1011
    assert not hub.is_connected(world.ayesha.id, broken)  # type: ignore[arg-type]
    assert [m["type"] for m in healthy.messages] == ["booking.updated", "booking.updated"]
    assert len(await world.notifications(booking)) == 2  # both VEHICLE_READY rows committed


# --- NOT-09: e-mail -------------------------------------------------------------------------------


class Outbox:
    """An `httpx.MockTransport` standing in for Resend; answers `status` to every request."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json={"id": "re_123"})

    @property
    def bodies(self) -> list[dict[str, Any]]:
        return [json.loads(request.content) for request in self.requests]


def http_state(world: World, outbox: Outbox) -> State:
    settings = make_settings(email_provider="http", email_api_key="re_test_key")
    state = app_state(world.db, settings)
    state.email_sender = HttpEmailSender(
        api_key="re_test_key",
        sender=settings.smtp_from,
        transport=httpx.MockTransport(outbox.handler),
    )
    return state


def assert_no_address_logged(caplog: pytest.LogCaptureFixture, *addresses: str) -> None:
    for record in caplog.records:
        text = record.getMessage() + json.dumps(vars(record), default=str)
        for address in addresses:
            assert address not in text, record


async def test_not09_estimate_sent_and_vehicle_ready_are_emailed_to_the_customer(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    outbox = Outbox()
    state = http_state(world, outbox)
    booking = await world.job(world.a, customer=world.ahmed)
    metadata = {"version": 2, "grand_total": "16100.00"}

    for action in (A.SEND_ESTIMATE, A.NOTIFY_READY, A.CONFIRM, A.PASS_QC):
        await perform(
            world,
            booking,
            applied(
                booking,
                action,
                actor=world.a.advisor,
                actor_role=R.SERVICE_ADVISOR,
                metadata=metadata,
            ),
            state=state,
        )

    rows = {row.type: row for row in await world.notifications(booking)}
    sent, ready = rows["ESTIMATE_SENT"], rows["VEHICLE_READY"]
    assert len(outbox.requests) == 2  # never BOOKING_CONFIRMED or QC_PASSED
    for request, row in zip(outbox.requests, (sent, ready), strict=True):
        assert request.method == "POST"
        assert str(request.url) == "https://api.resend.com/emails"
        assert request.headers["authorization"] == "Bearer re_test_key"
        assert request.headers["idempotency-key"] == str(row.id)
        assert request.headers["content-type"] == "application/json"
        assert json.loads(request.content) == {
            "from": "no-reply@bayflow.test",
            "to": ["ahmed@mail.com"],
            "subject": row.title,
            "text": f"{row.body}\n\nOpen in BayFlow: http://localhost:3000/bookings/{booking.id}",
        }
    assert outbox.bodies[0]["subject"] == f"Your estimate is ready — {booking.reference}"
    assert outbox.bodies[1]["subject"] == "Your vehicle is ready for pick-up"
    sent_logs = [r for r in caplog.records if r.getMessage() == "email.sent"]
    assert [r.notification_id for r in sent_logs] == [str(sent.id), str(ready.id)]
    assert_no_address_logged(caplog, "ahmed@mail.com")


async def test_not09_reserved_domains_are_never_emailed(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    outbox = Outbox()
    state = http_state(world, outbox)
    booking = await world.job(world.a)  # Ayesha: ayesha.customer@bayflow.test

    await perform(
        world,
        booking,
        applied(booking, A.NOTIFY_READY, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR),
        state=state,
    )

    assert outbox.requests == []
    [row] = await world.notifications(booking)
    skipped = [r for r in caplog.records if r.getMessage() == "email.skipped"]
    assert [(r.notification_id, r.reason) for r in skipped] == [(str(row.id), "SKIPPED_RESERVED")]
    assert_no_address_logged(caplog, "ayesha.customer@bayflow.test")


async def test_not09_provider_none_makes_no_attempt(
    world: World, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.INFO)
    state = app_state(world.db)  # EMAIL_PROVIDER=none (the test default)

    def no_network(*args: object, **kwargs: object) -> None:
        pytest.fail("EMAIL_PROVIDER=none must never open a connection")

    monkeypatch.setattr(email_channel.smtplib, "SMTP", no_network)
    monkeypatch.setattr(email_channel.httpx, "AsyncClient", no_network)
    booking = await world.job(world.a, customer=world.ahmed)

    await perform(
        world,
        booking,
        applied(booking, A.NOTIFY_READY, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR),
        state=state,
    )

    [row] = await world.notifications(booking)
    skipped = [r for r in caplog.records if r.getMessage() == "email.skipped"]
    assert [(r.notification_id, r.reason) for r in skipped] == [(str(row.id), "SKIPPED_DISABLED")]
    assert state.email_sender.provider == "none"  # built on first use from state.settings


async def test_not09_a_provider_failure_never_fails_the_action(
    probe_app: FastAPI,
    db_client: httpx.AsyncClient,
    world: World,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    outbox = Outbox(status=500)
    probe_app.state.email_sender = HttpEmailSender(
        api_key="re_test_key",
        sender="no-reply@bayflow.test",
        transport=httpx.MockTransport(outbox.handler),
    )
    booking = await world.job(world.a, customer=world.ahmed)

    response = await db_client.post(
        "/api/v1/_probe/actions",
        json={
            "booking_id": str(booking.id),
            "action": "SEND_ESTIMATE",
            "actor_user_id": str(world.a.advisor.id),
            "actor_role": "SERVICE_ADVISOR",
            "metadata": {"version": 1, "grand_total": "900.00"},
        },
    )
    await drain_after_commit_tasks()

    assert response.status_code == 200
    assert response.json() == {"booking_id": str(booking.id), "version": 2}
    [row] = await world.notifications(booking)  # committed with the action
    assert len(outbox.requests) == 1  # one attempt, no retry
    [failure] = [r for r in caplog.records if r.getMessage() == "email.failed"]
    assert (failure.notification_id, failure.status, failure.error) == (
        str(row.id),
        "500",
        "HTTPStatusError",
    )
    assert_no_address_logged(caplog, "ahmed@mail.com")


class FakeSmtp:
    """Records what `smtplib.SMTP` would have done (the SMTP adapter runs it in a thread)."""

    sessions: ClassVar[list["FakeSmtp"]] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list[str] = []
        self.messages: list[Any] = []
        FakeSmtp.sessions.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *args: object) -> None:
        self.calls.append("quit")

    def starttls(self, **kwargs: object) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login:{user}")

    def send_message(self, message: Any) -> None:
        self.calls.append("send")
        self.messages.append(message)


async def test_not09_smtp_delivers_through_mailpit_style_settings(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeSmtp.sessions = []
    monkeypatch.setattr(email_channel.smtplib, "SMTP", FakeSmtp)
    settings = make_settings(email_provider="smtp", smtp_host="localhost", smtp_port=1025)
    state = app_state(world.db, settings)
    booking = await world.job(world.a, customer=world.ahmed)

    await perform(
        world,
        booking,
        applied(booking, A.NOTIFY_READY, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR),
        state=state,
    )

    assert isinstance(state.email_sender, SmtpEmailSender)
    [session] = FakeSmtp.sessions
    assert (session.host, session.port, session.timeout) == ("localhost", 1025, 10.0)
    assert session.calls == ["send", "quit"]  # no STARTTLS / login without SMTP_USER (Mailpit)
    [message] = session.messages
    [row] = await world.notifications(booking)
    assert message["To"] == "ahmed@mail.com"
    assert message["From"] == "no-reply@bayflow.test"
    assert message["Subject"] == row.title
    assert message.get_content() == (
        f"{row.body}\n\nOpen in BayFlow: http://localhost:3000/bookings/{booking.id}\n"
    )


async def test_e_mail_to_a_vanished_recipient_is_skipped(
    world: World, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The address is read at send time; a recipient that no longer resolves is a logged skip."""
    caplog.set_level(logging.INFO)
    outbox = Outbox()
    state = http_state(world, outbox)

    async def nobody(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(identity_service, "get_user", nobody)
    booking = await world.job(world.a, customer=world.ahmed)

    await perform(
        world,
        booking,
        applied(booking, A.NOTIFY_READY, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR),
        state=state,
    )

    assert outbox.requests == []
    assert [r.reason for r in caplog.records if r.getMessage() == "email.skipped"] == [
        "SKIPPED_NO_ADDRESS"
    ]


async def test_database_unavailable_for_pushes_is_logged_not_raised(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    """After-commit work never reaches the request: a state without a database only logs."""
    state = State()
    state.settings = make_settings()
    socket = FakeSocket()
    get_realtime_hub(state).connect(world.ayesha.id, socket)  # type: ignore[arg-type]
    booking = await world.job(world.a)

    await perform(
        world,
        booking,
        applied(booking, A.NOTIFY_READY, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR),
        state=state,
    )

    assert [m["type"] for m in socket.messages] == ["notification.created"]
    assert "realtime.push_booking_updated_failed" in [r.getMessage() for r in caplog.records]

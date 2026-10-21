"""`WS /api/v1/ws` with Starlette's server-side `TestClient` (spec 12 §4.2; D70, D88).

SEC-33 (valid ticket accepted and the socket outlives it; missing, empty, malformed, tampered,
expired, `typ = session`, foreign-secret, future-`iat` and unknown-user tickets, a foreign `Origin`
and a deactivated user all closed with 1008 before accept — a browser would see 1006), NOT-17
(`ping` → `pong`; other frames, invalid JSON and binary frames ignored, the socket stays open),
NOT-08 / NOT-12 on live sockets (pushes reach the recipients and the booking's viewers only; the
socket of an outsider or a deactivated member stays silent), NOT-18 (`BookingPartsChanged`) and
NOT-07's push side (a rolled-back action pushes nothing).

The app runs in the TestClient's own event loop: every action is performed there too
(`client.portal.call`), so the hub, its locks and the after-commit tasks share one loop. "Nothing
was pushed" is asserted by draining the after-commit tasks, then sending `ping`: the next frame
must be the `pong`.
"""

import uuid
from collections.abc import Awaitable, Callable, Iterator
from datetime import timedelta
from functools import partial
from typing import TYPE_CHECKING, Any

import jwt
import pytest
from fastapi import FastAPI
from sqlalchemy import update
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.core.database import Database
from app.core.security import JWT_ALGORITHM, issue_token
from app.main import create_app
from app.modules.bookings.events import BookingActionApplied, BookingPartsChanged
from app.modules.bookings.models import Booking
from app.modules.identity import service as identity_service
from app.modules.identity.models import User
from app.modules.notifications.realtime import get_realtime_hub
from app.shared.clock import SimulatedClock, utcnow
from app.shared.enums import ActorRole, BookingAction, BookingStatus
from app.shared.event_bus import Event
from app.shared.uow import UnitOfWork, drain_after_commit_tasks
from tests.conftest import TEST_CLIENT_URL
from tests.modules.notifications.support import World, applied, parts_changed

if TYPE_CHECKING:
    from starlette.testclient import TestClient, WebSocketTestSession

pytestmark = [
    pytest.mark.db,
    pytest.mark.usefixtures("booking_reads"),
    # Starlette 1.7's TestClient warns that its httpx usage is deprecated (spec 12 §4.2).
    pytest.mark.filterwarnings("ignore:Using `httpx` with `starlette.testclient`:Warning"),
]

A = BookingAction
R = ActorRole
PONG = {"type": "pong", "data": {}}
POLICY_VIOLATION = 1008


@pytest.fixture
def ws_app(db: Database, settings: Settings) -> FastAPI:
    return create_app(settings, database=db)


@pytest.fixture
def client(ws_app: FastAPI, world: World, clock: SimulatedClock) -> Iterator["TestClient"]:
    # Imported here so the deprecation warning is raised under this module's filter.
    from starlette.testclient import TestClient  # noqa: PLC0415

    with TestClient(ws_app) as test_client:
        yield test_client


def ticket_for(user: User | uuid.UUID) -> str:
    user_id = user.id if isinstance(user, User) else user
    return issue_token(user_id, "ws", utcnow())


def open_socket(
    client: "TestClient", ticket: str | None, headers: dict[str, str] | None = None
) -> "WebSocketTestSession":
    url = "/api/v1/ws" if ticket is None else f"/api/v1/ws?ticket={ticket}"
    return client.websocket_connect(url, headers=headers or {})


def in_app_loop[T](client: "TestClient", call: Callable[[], Awaitable[T]]) -> T:
    """Run `call()` in the TestClient's event loop (the app's), and return its result."""
    assert client.portal is not None
    return client.portal.call(call)


def ping(ws: "WebSocketTestSession") -> None:
    """Round-trip a ping: everything pushed before it has been received by then."""
    ws.send_json({"type": "ping"})
    assert ws.receive_json() == PONG


def run_action(
    client: "TestClient",
    app: FastAPI,
    world: World,
    *events: Event,
    booking: Booking | None = None,
    rollback: bool = False,
    **booking_values: Any,
) -> None:
    """One action in the app's event loop, as a route would run it (D90: `app_state`)."""

    async def action() -> None:
        async with world.db.sessionmaker() as session:
            uow = UnitOfWork(session, app.state.event_bus, app_state=app.state)
            if booking is not None and booking_values:
                await session.execute(
                    update(Booking).where(Booking.id == booking.id).values(**booking_values)
                )
            for event in events:
                await uow.publish(event)
            if rollback:
                await uow.rollback()
            else:
                await uow.commit()
        await drain_after_commit_tasks()

    in_app_loop(client, action)


# --- Handshake (SEC-33) ---------------------------------------------------------------------------


def test_sec33_a_valid_ticket_is_accepted_and_answers_ping(
    client: "TestClient", world: World
) -> None:
    with open_socket(client, ticket_for(world.ayesha)) as ws:
        ping(ws)
        ping(ws)


def test_sec33_a_ticket_from_the_route_opens_the_socket(client: "TestClient", world: World) -> None:
    session = issue_token(world.a.advisor.id, "session", utcnow())
    response = client.get("/api/v1/realtime/ticket", headers={"Authorization": f"Bearer {session}"})
    assert response.status_code == 200

    with open_socket(client, response.json()["ticket"]) as ws:
        ping(ws)


def test_sec33_the_socket_outlives_its_ticket(
    client: "TestClient", world: World, clock: SimulatedClock
) -> None:
    ticket = ticket_for(world.ayesha)
    with open_socket(client, ticket) as ws:
        clock.advance(timedelta(minutes=10))
        ping(ws)
    with pytest.raises(WebSocketDisconnect) as caught, open_socket(client, ticket):
        pass  # but the same ticket no longer opens a new one
    assert caught.value.code == POLICY_VIOLATION


FOREIGN_SECRET = "another-secret-that-is-at-least-32-bytes"


def forged(claims: dict[str, Any]) -> str:
    """A well-formed ticket signed with a key that is not `JWT_SECRET`."""
    return jwt.encode(claims, FOREIGN_SECRET, algorithm=JWT_ALGORITHM)


def rejected_tickets(world: World, clock: SimulatedClock) -> dict[str, str | None]:
    now = int(utcnow().timestamp())
    valid = ticket_for(world.ayesha)
    head, body, signature = valid.split(".")
    tampered_signature = signature[:-2] + ("AA" if not signature.endswith("AA") else "BB")
    return {
        "missing": None,
        "empty": "",
        "garbage": "not-a-ticket",
        "tampered": f"{head}.{body}.{tampered_signature}",
        "session-token": issue_token(world.ayesha.id, "session", utcnow()),
        "foreign-secret": forged(
            {"sub": str(world.ayesha.id), "iat": now, "exp": now + 60, "typ": "ws"}
        ),
        "issued-in-the-future": issue_token(world.ayesha.id, "ws", utcnow() + timedelta(minutes=5)),
        "unknown-user": ticket_for(uuid.uuid4()),
    }


REJECTED = (
    "missing",
    "empty",
    "garbage",
    "tampered",
    "session-token",
    "foreign-secret",
    "issued-in-the-future",
    "unknown-user",
)


@pytest.mark.parametrize("kind", REJECTED)
def test_sec33_a_bad_ticket_is_refused_with_1008_before_accept(
    client: "TestClient", world: World, clock: SimulatedClock, kind: str
) -> None:
    ticket = rejected_tickets(world, clock)[kind]
    with pytest.raises(WebSocketDisconnect) as caught, open_socket(client, ticket):
        pytest.fail("the handshake must not be accepted")
    assert caught.value.code == POLICY_VIOLATION


def test_sec33_an_expired_ticket_is_refused(
    client: "TestClient", world: World, clock: SimulatedClock
) -> None:
    ticket = ticket_for(world.ayesha)
    clock.advance(timedelta(seconds=60))  # exp = iat + 60: expired at exactly 60 s
    with pytest.raises(WebSocketDisconnect) as caught, open_socket(client, ticket):
        pytest.fail("the handshake must not be accepted")
    assert caught.value.code == POLICY_VIOLATION


def test_sec33_a_deactivated_user_is_refused(client: "TestClient", world: World) -> None:
    ticket = ticket_for(world.a.technician)
    in_app_loop(client, partial(world.set_user_active, world.a.technician, active=False))

    with pytest.raises(WebSocketDisconnect) as caught, open_socket(client, ticket):
        pytest.fail("the handshake must not be accepted")
    assert caught.value.code == POLICY_VIOLATION


def test_an_internal_error_during_the_handshake_closes_with_1011(
    client: "TestClient", world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not a policy failure: the database is unreachable. Still closed before accept."""

    async def unreachable(*args: object, **kwargs: object) -> None:
        raise ConnectionRefusedError

    monkeypatch.setattr(identity_service, "get_active_user", unreachable)
    with (
        pytest.raises(WebSocketDisconnect) as caught,
        open_socket(client, ticket_for(world.ayesha)),
    ):
        pytest.fail("the handshake must not be accepted")
    assert caught.value.code == 1011


@pytest.mark.parametrize(
    "origin", ["https://evil.example", "null", "http://localhost:3001", "https://localhost:3000"]
)
def test_sec33_a_foreign_origin_is_refused(client: "TestClient", world: World, origin: str) -> None:
    headers = {"origin": origin}
    with (
        pytest.raises(WebSocketDisconnect) as caught,
        open_socket(client, ticket_for(world.ayesha), headers),
    ):
        pytest.fail("the handshake must not be accepted")
    assert caught.value.code == POLICY_VIOLATION


@pytest.mark.parametrize("origin", [TEST_CLIENT_URL, TEST_CLIENT_URL.upper()])
def test_the_web_origin_is_accepted(client: "TestClient", world: World, origin: str) -> None:
    with open_socket(client, ticket_for(world.ayesha), {"origin": origin}) as ws:
        ping(ws)


# --- Frames (NOT-17) ------------------------------------------------------------------------------


def test_not17_unknown_frames_and_invalid_json_are_ignored(
    client: "TestClient", world: World
) -> None:
    with open_socket(client, ticket_for(world.ayesha)) as ws:
        for frame in (
            '{"type": "subscribe", "channel": "everything"}',
            "not json at all",
            "[1, 2, 3]",
            '"ping"',
            '{"type": "PING"}',
            "{}",
            '{"type": "ping"' + " " * 2000 + "}",  # longer than any ping: not parsed
        ):
            ws.send_text(frame)
        ws.send_bytes(b'{"type": "ping"}')  # binary frames are ignored too
        ping(ws)  # still open; nothing came back for the ignored frames


# --- Pushes on live sockets (NOT-08, NOT-12, SEC-13, NOT-18, NOT-07) ------------------------------


def test_not08_pushes_reach_the_recipient_and_the_viewers_only(
    client: "TestClient", ws_app: FastAPI, world: World
) -> None:
    a = world.a
    booking = in_app_loop(client, partial(world.job, a))
    event = applied(booking, A.NOTIFY_READY, actor=a.advisor, actor_role=R.SERVICE_ADVISOR)

    with (
        open_socket(client, ticket_for(world.ayesha)) as customer,
        open_socket(client, ticket_for(world.ayesha)) as customer_tab,
        open_socket(client, ticket_for(a.advisor)) as advisor,
        open_socket(client, ticket_for(a.technician_2)) as other_technician,
        open_socket(client, ticket_for(world.b.advisor)) as other_shop,
    ):
        for ws in (customer, customer_tab, advisor, other_technician, other_shop):
            ping(ws)  # registered
        run_action(client, ws_app, world, event, booking=booking, version=2)

        for ws in (customer, customer_tab):
            created = ws.receive_json()
            assert created["type"] == "notification.created"
            assert created["data"]["type"] == "VEHICLE_READY"
            assert created["data"]["link"] == f"/bookings/{booking.id}"
            assert ws.receive_json() == {
                "type": "booking.updated",
                "data": {
                    "booking_id": str(booking.id),
                    "shop_id": str(a.id),
                    "status": "IN_REPAIR",
                    "version": 2,
                },
            }
            ping(ws)
        assert advisor.receive_json()["type"] == "booking.updated"
        ping(advisor)
        ping(other_technician)  # NOT-12: not assigned, nothing before the pong
        ping(other_shop)  # another tenant: nothing


def test_not12_sec13_outsiders_and_deactivated_members_stay_silent(
    client: "TestClient", ws_app: FastAPI, world: World
) -> None:
    a = world.a
    booking = in_app_loop(client, partial(world.job, a))

    with (
        open_socket(client, ticket_for(a.technician)) as technician,
        open_socket(client, ticket_for(a.parts_2)) as other_parts,
        open_socket(client, ticket_for(a.inspector)) as inspector,
        open_socket(client, ticket_for(a.parts)) as parts,
    ):
        for ws in (technician, other_parts, inspector, parts):
            ping(ws)
        in_app_loop(
            client, partial(world.set_membership_active, a.shop, a.technician, active=False)
        )
        run_action(
            client,
            ws_app,
            world,
            applied(booking, A.ALLOCATE_PARTS, actor=a.parts, actor_role=R.PARTS_PERSON),
            booking=booking,
            version=2,
        )

        ping(technician)  # SEC-13: deactivated, neither PARTS_READY nor booking.updated
        ping(other_parts)  # not this booking's parts person
        ping(inspector)  # QC inspector outside QC_PENDING / QC_IN_PROGRESS, never inspected it
        assert parts.receive_json()["type"] == "booking.updated"
        ping(parts)


def test_not12_qc_inspectors_see_the_booking_while_it_is_queued(
    client: "TestClient", ws_app: FastAPI, world: World
) -> None:
    a = world.a
    booking = in_app_loop(client, partial(world.job, a))

    with open_socket(client, ticket_for(a.inspector)) as inspector:
        ping(inspector)
        run_action(
            client,
            ws_app,
            world,
            applied(booking, A.SEND_TO_QC, actor=a.technician, actor_role=R.TECHNICIAN),
            booking=booking,
            status=BookingStatus.QC_PENDING,
            version=2,
        )
        assert inspector.receive_json()["data"]["type"] == "QC_REQUESTED"
        assert inspector.receive_json()["data"]["status"] == "QC_PENDING"
        ping(inspector)


def test_not18_parts_changes_push_booking_updated_without_a_row(
    client: "TestClient", ws_app: FastAPI, world: World
) -> None:
    a = world.a
    booking = in_app_loop(
        client,
        partial(
            world.booking,
            a,
            status=BookingStatus.PARTS_ORDERED,
            technician=a.technician,
            parts=a.parts,
        ),
    )
    event: BookingPartsChanged = parts_changed(booking)

    with open_socket(client, ticket_for(a.parts)) as parts:
        ping(parts)
        run_action(client, ws_app, world, event)
        assert parts.receive_json() == {
            "type": "booking.updated",
            "data": {
                "booking_id": str(booking.id),
                "shop_id": str(a.id),
                "status": "PARTS_ORDERED",
                "version": booking.version,
            },
        }
        ping(parts)
    assert in_app_loop(client, world.notifications) == []


def test_not07_a_rolled_back_action_pushes_nothing(
    client: "TestClient", ws_app: FastAPI, world: World
) -> None:
    booking = in_app_loop(client, partial(world.job, world.a))
    event: BookingActionApplied = applied(
        booking, A.CANCEL, actor=world.ayesha, actor_role=R.CUSTOMER
    )

    with open_socket(client, ticket_for(world.a.advisor)) as advisor:
        ping(advisor)
        run_action(client, ws_app, world, event, rollback=True)
        ping(advisor)


def test_a_closed_socket_is_unregistered(
    client: "TestClient", ws_app: FastAPI, world: World
) -> None:
    hub = get_realtime_hub(ws_app.state)
    with open_socket(client, ticket_for(world.ayesha)) as ws:
        ping(ws)
        reached = in_app_loop(
            client, partial(hub.send_to_users, [world.ayesha.id], {"type": "probe", "data": {}})
        )
        assert reached == 1
        assert ws.receive_json() == {"type": "probe", "data": {}}

    reached_after = in_app_loop(
        client, partial(hub.send_to_users, [world.ayesha.id], {"type": "probe", "data": {}})
    )
    assert reached_after == 0

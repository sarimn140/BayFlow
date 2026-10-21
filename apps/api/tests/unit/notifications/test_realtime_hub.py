"""The realtime hub with fake sockets (spec 12 §4.2: "the hub's routing logic is unit-tested with
fake connections"): D90's per-app get-or-create, routing to users and tabs, NOT-20 (a socket whose
send fails or exceeds 5 s is dropped and closed), one frame at a time per socket, the frame
format, the client frame parser and the `Origin` rule (D70)."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.datastructures import State

from app.modules.notifications.realtime import (
    PONG_FRAME,
    RealtimeHub,
    encode,
    get_realtime_hub,
    is_ping,
    origin_allowed,
)
from app.modules.notifications.schemas import NotificationRecord
from app.shared.enums import ActorRole, NotificationType

ALICE, BOB, CAROL = (uuid.uuid4() for _ in range(3))


class Socket:
    """A fake socket: records frames; can fail, hang, or yield mid-send."""

    def __init__(self, *, fail: bool = False, hang: bool = False, slow: bool = False) -> None:
        self.fail, self.hang, self.slow = fail, hang, slow
        self.frames: list[str] = []
        self.closed_with: int | None = None
        self.sends = 0
        self.in_flight = 0
        self.max_in_flight = 0

    async def send_text(self, data: str) -> None:
        self.sends += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.fail:
                msg = "broken pipe"
                raise ConnectionResetError(msg)
            if self.hang:
                await asyncio.sleep(3600)
            if self.slow:
                await asyncio.sleep(0.01)
            self.frames.append(data)
        finally:
            self.in_flight -= 1

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed_with = code

    def messages(self) -> list[dict[str, Any]]:
        return [json.loads(frame) for frame in self.frames]


def hub_with(**sockets: list[Socket]) -> tuple[RealtimeHub, dict[str, uuid.UUID]]:
    users = {"alice": ALICE, "bob": BOB, "carol": CAROL}
    hub = RealtimeHub(State())
    for name, user_sockets in sockets.items():
        for socket in user_sockets:
            hub.connect(users[name], socket)  # type: ignore[arg-type]
    return hub, users


# --- D90: one hub per app -------------------------------------------------------------------------


def test_get_realtime_hub_creates_one_hub_per_app_state() -> None:
    first, second = State(), State()
    hub = get_realtime_hub(first)
    assert first.realtime_hub is hub
    assert get_realtime_hub(first) is hub  # get-or-create
    assert get_realtime_hub(second) is not hub  # another app, another hub


def test_get_realtime_hub_refuses_a_foreign_object() -> None:
    state = State()
    state.realtime_hub = object()
    with pytest.raises(TypeError, match="RealtimeHub"):
        get_realtime_hub(state)


# --- Registry -------------------------------------------------------------------------------------


def test_connect_and_disconnect() -> None:
    tab_1, tab_2 = Socket(), Socket()
    hub, _ = hub_with(alice=[tab_1, tab_2])
    assert hub.is_connected(ALICE, tab_1)  # type: ignore[arg-type]
    hub.disconnect(ALICE, tab_1)  # type: ignore[arg-type]
    hub.disconnect(ALICE, tab_1)  # type: ignore[arg-type]  # idempotent
    hub.disconnect(BOB, tab_1)  # type: ignore[arg-type]  # unknown user: fine
    assert not hub.is_connected(ALICE, tab_1)  # type: ignore[arg-type]
    assert hub.is_connected(ALICE, tab_2)  # type: ignore[arg-type]


# --- Routing --------------------------------------------------------------------------------------


async def test_messages_reach_only_the_targeted_users_on_every_tab() -> None:
    alice_1, alice_2, bob, carol = Socket(), Socket(), Socket(), Socket()
    hub, _ = hub_with(alice=[alice_1, alice_2], bob=[bob], carol=[carol])

    reached = await hub.send_to_users([ALICE, BOB, ALICE, uuid.uuid4()], {"type": "x", "data": {}})

    assert reached == 3
    assert alice_1.frames == alice_2.frames == bob.frames == ['{"type":"x","data":{}}']
    assert carol.frames == []


async def test_nobody_connected_sends_nothing() -> None:
    hub = RealtimeHub(State())
    assert await hub.send_to_users([ALICE], {"type": "x", "data": {}}) == 0


def test_frames_are_compact_utf8_json() -> None:
    frame = encode({"type": "notification.created", "data": {"title": "Booking — Lahore"}})
    assert frame == '{"type":"notification.created","data":{"title":"Booking — Lahore"}}'
    assert json.loads(PONG_FRAME) == {"type": "pong", "data": {}}


# --- NOT-20: dead and slow sockets ----------------------------------------------------------------


async def test_not20_a_failing_socket_is_dropped_closed_and_never_retried() -> None:
    broken, healthy = Socket(fail=True), Socket()
    hub, _ = hub_with(alice=[broken, healthy])

    first = await hub.send_to_users([ALICE], {"type": "a", "data": {}})
    second = await hub.send_to_users([ALICE], {"type": "b", "data": {}})

    assert (first, second) == (1, 1)
    assert broken.closed_with == 1011
    assert broken.sends == 1  # dropped after the first failure
    assert not hub.is_connected(ALICE, broken)  # type: ignore[arg-type]
    assert [m["type"] for m in healthy.messages()] == ["a", "b"]


async def test_not20_a_send_slower_than_the_timeout_drops_the_socket() -> None:
    stuck, healthy = Socket(hang=True), Socket()
    hub, _ = hub_with(alice=[stuck], bob=[healthy])
    hub.send_timeout_seconds = 0.05

    async with asyncio.timeout(2):  # sends run concurrently: one slow socket delays nobody
        reached = await hub.send_to_users([ALICE, BOB], {"type": "x", "data": {}})

    assert reached == 1
    assert healthy.frames
    assert not hub.is_connected(ALICE, stuck)  # type: ignore[arg-type]
    assert stuck.closed_with == 1011


def test_the_send_timeout_is_five_seconds() -> None:
    assert RealtimeHub.send_timeout_seconds == 5.0


async def test_one_frame_at_a_time_per_socket() -> None:
    socket = Socket(slow=True)
    hub, _ = hub_with(alice=[socket])

    await asyncio.gather(
        *(hub.send_to_users([ALICE], {"type": "x", "data": {"n": n}}) for n in range(5))
    )

    assert socket.max_in_flight == 1
    assert sorted(m["data"]["n"] for m in socket.messages()) == [0, 1, 2, 3, 4]


async def test_a_socket_that_fails_after_its_user_left_is_just_forgotten() -> None:
    socket = Socket(fail=True)
    hub, _ = hub_with(alice=[socket])
    hub.disconnect(ALICE, socket)  # type: ignore[arg-type]
    assert await hub.send_to_users([ALICE], {"type": "x", "data": {}}) == 0
    assert socket.sends == 0


# --- Pushes ---------------------------------------------------------------------------------------


def record(recipient: uuid.UUID) -> NotificationRecord:
    return NotificationRecord(
        id=uuid.uuid4(),
        type=NotificationType.VEHICLE_READY,
        title="Your vehicle is ready for pick-up",
        body="Booking BF-7KQ2MX at Lahore Auto Care is ready for pick-up.",
        recipient_role=ActorRole.CUSTOMER,
        link="/bookings/42",
        shop_id=uuid.uuid4(),
        shop_name="Lahore Auto Care",
        booking_id=uuid.uuid4(),
        booking_reference="BF-7KQ2MX",
        read_at=None,
        created_at=datetime(2026, 10, 16, 5, 0, tzinfo=UTC),
        recipient_user_id=recipient,
    )


async def test_push_notifications_sends_each_row_to_its_recipient_only() -> None:
    alice, bob, carol = Socket(), Socket(), Socket()
    hub, _ = hub_with(alice=[alice], bob=[bob], carol=[carol])
    rows = [record(ALICE), record(BOB)]

    assert await hub.push_notifications(rows) == 2

    for socket, row in ((alice, rows[0]), (bob, rows[1])):
        [message] = socket.messages()
        assert message["type"] == "notification.created"
        assert message["data"] == row.to_read().model_dump(mode="json")
        assert "recipient_user_id" not in message["data"]
        assert message["data"]["created_at"] == "2026-10-16T05:00:00Z"
    assert carol.frames == []


async def test_push_notifications_without_rows_or_sockets_is_a_no_op() -> None:
    hub, _ = hub_with(alice=[Socket()])
    assert await hub.push_notifications([]) == 0
    assert await RealtimeHub(State()).push_notifications([record(ALICE)]) == 0


async def test_push_booking_updated_reads_nothing_while_nobody_is_connected() -> None:
    """The state has no database: any read would raise."""
    assert await RealtimeHub(State()).push_booking_updated(uuid.uuid4(), uuid.uuid4()) == 0


async def test_push_booking_updated_needs_the_app_database() -> None:
    hub, _ = hub_with(alice=[Socket()])
    with pytest.raises(RuntimeError, match="database"):
        await hub.push_booking_updated(uuid.uuid4(), uuid.uuid4())


# --- Serving one socket ---------------------------------------------------------------------------


class ServedSocket(Socket):
    """A fake socket for `serve()`: client frames come from a queue."""

    def __init__(self, *frames: dict[str, Any]) -> None:
        super().__init__()
        self.incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        for frame in frames:
            self.incoming.put_nowait(frame)
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def receive(self) -> dict[str, Any]:
        return await self.incoming.get()


async def test_serve_answers_pings_ignores_the_rest_and_unregisters_on_disconnect() -> None:
    hub = RealtimeHub(State())
    socket = ServedSocket(
        {"type": "websocket.receive", "text": '{"type": "ping"}'},
        {"type": "websocket.receive", "text": "garbage"},
        {"type": "websocket.receive", "bytes": b'{"type": "ping"}'},
        {"type": "websocket.receive", "text": '{"type": "ping", "extra": 1}'},
        {"type": "websocket.disconnect", "code": 1000},
    )

    await hub.serve(ALICE, socket)  # type: ignore[arg-type]

    assert socket.accepted
    assert socket.frames == [PONG_FRAME, PONG_FRAME]
    assert not hub.is_connected(ALICE, socket)  # type: ignore[arg-type]


async def test_serve_gives_up_quietly_when_the_client_leaves_during_accept() -> None:
    class Vanished(ServedSocket):
        async def accept(self) -> None:
            raise ConnectionResetError

    hub = RealtimeHub(State())
    socket = Vanished()
    await hub.serve(ALICE, socket)  # type: ignore[arg-type]
    assert not hub.is_connected(ALICE, socket)  # type: ignore[arg-type]


async def test_serve_stops_when_the_pong_cannot_be_sent() -> None:
    hub = RealtimeHub(State())
    socket = ServedSocket({"type": "websocket.receive", "text": '{"type": "ping"}'})
    socket.fail = True

    async with asyncio.timeout(2):
        await hub.serve(ALICE, socket)  # type: ignore[arg-type]

    assert socket.closed_with == 1011
    assert not hub.is_connected(ALICE, socket)  # type: ignore[arg-type]


# --- Client frames and the Origin rule ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "ping"),
    [
        ('{"type": "ping"}', True),
        ('{"type":"ping","data":{}}', True),
        ('{"type": "pong"}', False),
        ('{"type": "PING"}', False),
        ('"ping"', False),
        ("ping", False),
        ("[]", False),
        ("{}", False),
        ("", False),
        (None, False),
        ('{"type": "ping"}' + " " * 2000, False),  # longer than any ping: never parsed
        ('{"type": "ping"', False),
    ],
)
def test_is_ping(text: str | None, ping: bool) -> None:
    assert is_ping(text) is ping


@pytest.mark.parametrize(
    ("origins", "allowed"),
    [
        ([], True),  # no Origin header (scripts, tests): the ticket still applies
        (["http://localhost:3000"], True),
        (["HTTP://LOCALHOST:3000"], True),
        (["http://localhost:3000/"], True),
        (["http://localhost:3000", "http://localhost:3000"], True),
        (["https://evil.example"], False),
        (["null"], False),
        ([""], False),
        (["http://localhost:3001"], False),
        (["https://localhost:3000"], False),
        (["http://localhost:3000", "https://evil.example"], False),
        (["http://localhost:3000.evil.example"], False),
    ],
)
def test_origin_must_be_the_client_url(origins: list[str], allowed: bool) -> None:
    assert origin_allowed(origins, "http://localhost:3000") is allowed

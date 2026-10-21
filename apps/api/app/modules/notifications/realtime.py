"""The in-memory realtime hub and the `/api/v1/ws` socket (P1; D14, D70, D88, D90; spec 03 §6).

**One hub per app** (D90): `get_realtime_hub(state)` creates it on first use and stores it at
`app.state.realtime_hub`; the WebSocket route and the after-commit callbacks (through
`uow.app_state`) reach it the same way. Nothing lives at module level, so every app instance (tests
build several in one process) has its own hub. One API replica (D14): the registry is per process.

**Handshake** (`serve_websocket`, before `accept()`, in this order): an `Origin` header, when
present, must be `CLIENT_URL`; the `ticket` query value must decode as a `typ = ws` JWT that has
not expired by the app clock (D63, D70); the user must exist and be active (D9). Any failure closes
with 1008 before accept (browsers see 1006; spec 03 §6.2); an internal error closes with 1011. The
ticket is never logged (`app.core.logging` redacts uvicorn's handshake line, SEC-38).

**After accept** the socket is registered under its user (several tabs allowed) and outlives its
60-second ticket. Client frames: `{"type": "ping"}` → `{"type": "pong", "data": {}}`; anything
else (other types, invalid JSON, binary frames) is ignored and the socket stays open.

**Sends** are JSON text frames `{"type", "data"}`, serialised once per message, one send at a time
per socket, each within 5 s. A socket whose send fails or times out is dropped from the registry
and closed (1011), so its client reconnects with a new ticket; no message is replayed (spec 03
§6.5). Sends iterate over a copy of the registry, which is only mutated on the event loop.
"""

import asyncio
import contextlib
import importlib.util
import json
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from functools import partial
from typing import Any
from uuid import UUID

from starlette import status
from starlette.datastructures import State
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.core.config import Settings
from app.core.database import Database
from app.core.errors import Unauthenticated
from app.core.security import decode_token
from app.modules.bookings import service as bookings_service
from app.modules.identity import service as identity_service
from app.modules.notifications.schemas import NotificationRecord
from app.shared.clock import utcnow

logger = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = 5.0
CLOSE_TIMEOUT_SECONDS = 1.0
MAX_CLIENT_FRAME_LENGTH = 1024
"""Client frames longer than this are ignored unparsed (a ping is 16 characters)."""

NOTIFICATION_CREATED = "notification.created"
BOOKING_UPDATED = "booking.updated"
CALL_INCOMING = "call.incoming"  # P2, glossary §11
CALL_UPDATED = "call.updated"
TASK_CREATED = "task.created"


def encode(message: Mapping[str, Any]) -> str:
    """One compact JSON text frame (UTF-8, not ASCII-escaped)."""
    return json.dumps(message, separators=(",", ":"), ensure_ascii=False)


PONG_FRAME = encode({"type": "pong", "data": {}})


def is_ping(text: str | None) -> bool:
    """True for a JSON object whose `type` is `"ping"`; anything else is ignored (spec 03 §6.3)."""
    if text is None or len(text) > MAX_CLIENT_FRAME_LENGTH:
        return False
    try:
        frame = json.loads(text)
    except ValueError:
        return False
    return isinstance(frame, dict) and frame.get("type") == "ping"


def origin_allowed(origins: Sequence[str], client_url: str) -> bool:
    """D70 / spec 04: no `Origin` header is fine (non-browser clients still need a ticket); every
    `Origin` sent must be `CLIENT_URL` (scheme and host compared case-insensitively)."""
    expected = client_url.strip().rstrip("/").lower()
    return all(origin.strip().rstrip("/").lower() == expected for origin in origins)


def _database(state: State) -> Database:
    database = getattr(state, "db", None)
    if not isinstance(database, Database):
        msg = "the database is not initialised: the application lifespan has not run"
        raise RuntimeError(msg)
    return database


def _settings(state: State) -> Settings:
    settings = getattr(state, "settings", None)
    if not isinstance(settings, Settings):
        msg = "app.state.settings is not set: build the app with create_app()"
        raise RuntimeError(msg)
    return settings


async def _close_quietly(websocket: WebSocket, code: int) -> None:
    """Best-effort close (the peer may already be gone); never raises, never hangs."""
    with contextlib.suppress(Exception):
        async with asyncio.timeout(CLOSE_TIMEOUT_SECONDS):
            await websocket.close(code=code)


type ConnectHook = Callable[[UUID], Awaitable[None]]


class RealtimeHub:
    """Connected sockets by user id, and the pushes of glossary §11 (one instance per app, D90)."""

    send_timeout_seconds: float = SEND_TIMEOUT_SECONDS

    def __init__(self, state: State) -> None:
        self._state = state
        # user id -> {socket -> its send lock}: one frame at a time per socket.
        self._sockets: dict[UUID, dict[WebSocket, asyncio.Lock]] = {}
        self._connect_hooks: list[ConnectHook] = []

    # --- Presence (the calls module's `Presence` port, spec 05 §3.3) ---------------------------

    def is_online(self, user_id: UUID) -> bool:
        return bool(self._sockets.get(user_id))

    def online_user_ids(self, user_ids: Iterable[UUID]) -> set[UUID]:
        """The given users who hold at least one open socket right now."""
        return {user_id for user_id in user_ids if self._sockets.get(user_id)}

    def add_connect_hook(self, hook: "ConnectHook") -> None:
        """P2: run `hook(user_id)` after a socket of that user is accepted (e.g. re-send ringing
        calls). Hook failures are logged and never close the socket."""
        self._connect_hooks.append(hook)

    async def _run_connect_hooks(self, user_id: UUID) -> None:
        for hook in self._connect_hooks:
            try:
                await hook(user_id)
            except Exception:
                logger.exception("realtime.connect_hook_failed", extra={"user_id": str(user_id)})

    # --- Registry -------------------------------------------------------------------------------

    def connect(self, user_id: UUID, websocket: WebSocket) -> None:
        """Register an accepted socket under its user (a user may hold several, one per tab)."""
        self._sockets.setdefault(user_id, {})[websocket] = asyncio.Lock()

    def disconnect(self, user_id: UUID, websocket: WebSocket) -> None:
        """Forget a socket (idempotent)."""
        sockets = self._sockets.get(user_id)
        if sockets is None:
            return
        sockets.pop(websocket, None)
        if not sockets:
            del self._sockets[user_id]

    def is_connected(self, user_id: UUID, websocket: WebSocket) -> bool:
        return websocket in self._sockets.get(user_id, {})

    # --- Sends ------------------------------------------------------------------------------------

    async def _deliver(
        self, user_id: UUID, websocket: WebSocket, lock: asyncio.Lock, frame: str
    ) -> bool:
        """Send one frame within the timeout; on any failure drop and close the socket."""
        try:
            async with asyncio.timeout(self.send_timeout_seconds):
                async with lock:
                    await websocket.send_text(frame)
        except Exception as exc:
            logger.info(
                "realtime.socket_dropped",
                extra={"user_id": str(user_id), "error": type(exc).__name__},
            )
            self.disconnect(user_id, websocket)
            await _close_quietly(websocket, status.WS_1011_INTERNAL_ERROR)
            return False
        return True

    async def send_to_users(self, user_ids: Iterable[UUID], message: Mapping[str, Any]) -> int:
        """Send `message` to every open socket of these users, concurrently; returns the number of
        sockets reached. Sockets that fail are dropped; nothing is raised."""
        frame = encode(message)
        targets = [
            (user_id, websocket, lock)
            for user_id in dict.fromkeys(user_ids)
            for websocket, lock in list(self._sockets.get(user_id, {}).items())
        ]
        if not targets:
            return 0
        delivered = await asyncio.gather(
            *(
                self._deliver(user_id, websocket, lock, frame)
                for user_id, websocket, lock in targets
            )
        )
        return sum(delivered)

    async def push_notifications(self, rows: Sequence[NotificationRecord]) -> int:
        """`notification.created` to each row's recipient only; `data` = `NotificationRead`."""
        if not rows or not self._sockets:
            return 0
        sent = await asyncio.gather(
            *(
                self.send_to_users(
                    [row.recipient_user_id],
                    {"type": NOTIFICATION_CREATED, "data": row.to_read().model_dump(mode="json")},
                )
                for row in rows
            )
        )
        return sum(sent)

    async def push_booking_updated(self, shop_id: UUID, booking_id: UUID) -> int:
        """`booking.updated` `{booking_id, shop_id, status, version}` to the users who can see the
        booking now (D21 at push time: `bookings.list_booking_viewer_ids`, active members only).

        Reads its own session from `app.state.db` (D90), closed before sending; nothing is read
        while no socket is open."""
        if not self._sockets:
            return 0
        async with _database(self._state).sessionmaker() as session:
            refs = await bookings_service.get_booking_refs(
                session, shop_id=shop_id, booking_ids=[booking_id]
            )
            ref = refs.get(booking_id)
            if ref is None:
                return 0
            viewer_ids = await bookings_service.list_booking_viewer_ids(
                session, booking_id=booking_id
            )
        data = {
            "booking_id": str(booking_id),
            "shop_id": str(shop_id),
            "status": str(ref.status),
            "version": ref.version,
        }
        return await self.send_to_users(viewer_ids, {"type": BOOKING_UPDATED, "data": data})

    # --- One socket's life ------------------------------------------------------------------------

    async def serve(self, user_id: UUID, websocket: WebSocket) -> None:
        """Accept, register, answer pings until the client leaves, then unregister."""
        try:
            await websocket.accept()
        except (WebSocketDisconnect, RuntimeError, OSError):  # the client left mid-handshake
            return
        self.connect(user_id, websocket)
        await self._run_connect_hooks(user_id)
        try:
            while True:
                try:
                    message = await websocket.receive()
                except (WebSocketDisconnect, RuntimeError):  # closed underneath us
                    return
                if message["type"] == "websocket.disconnect":
                    return
                if is_ping(message.get("text")) and not await self._reply(
                    user_id, websocket, PONG_FRAME
                ):
                    return
        finally:
            self.disconnect(user_id, websocket)

    async def _reply(self, user_id: UUID, websocket: WebSocket, frame: str) -> bool:
        lock = self._sockets.get(user_id, {}).get(websocket)
        if lock is None:  # already dropped by a failed push
            return False
        return await self._deliver(user_id, websocket, lock, frame)


async def resend_ringing_calls(state: State, user_id: UUID) -> None:
    """P2 connect hook (spec 05 §8.4): a socket that (re)connects gets `call.incoming` again for
    every call still ringing that this user may answer."""
    from app.modules.calls import service as calls_service  # noqa: PLC0415 - optional package

    async with _database(state).sessionmaker() as session:
        calls = await calls_service.list_ringing_calls_for_user(session, user_id)
    hub = get_realtime_hub(state)
    for call in calls:
        await hub.send_to_users(
            [user_id], {"type": CALL_INCOMING, "data": call.model_dump(mode="json")}
        )


def get_realtime_hub(state: State) -> RealtimeHub:
    """The app's hub, created on first use at `state.realtime_hub` (D90). There is no `await`
    between the check and the assignment, so one event loop never builds two."""
    hub = getattr(state, "realtime_hub", None)
    if hub is None:
        hub = RealtimeHub(state)
        state.realtime_hub = hub
        if importlib.util.find_spec("app.modules.calls") is not None:  # P2 (spec 05 §8.4)
            hub.add_connect_hook(partial(resend_ringing_calls, state))
    if not isinstance(hub, RealtimeHub):
        msg = "app.state.realtime_hub is not a RealtimeHub"
        raise TypeError(msg)
    return hub


def _log_rejection(reason: str, **fields: str) -> None:
    logger.info("realtime.handshake_rejected", extra={"reason": reason, **fields})


async def authenticate_handshake(websocket: WebSocket) -> UUID | None:
    """The D70 checks in order: `Origin`, ticket, active user. The user id, or None to refuse."""
    state = websocket.app.state
    if not origin_allowed(websocket.headers.getlist("origin"), _settings(state).client_url):
        _log_rejection("origin")
        return None
    ticket = websocket.query_params.get("ticket")
    if not ticket:
        _log_rejection("missing_ticket")
        return None
    try:
        user_id = decode_token(ticket, utcnow(), "ws")
    except Unauthenticated:
        _log_rejection("invalid_ticket")
        return None
    async with _database(state).sessionmaker() as session:
        user = await identity_service.get_active_user(session, user_id)
    if user is None:
        _log_rejection("inactive_user", user_id=str(user_id))
        return None
    return user.id


async def serve_websocket(websocket: WebSocket) -> None:
    """`WS /api/v1/ws?ticket=…`: refuse before accept (1008), or serve the socket until it
    closes."""
    try:
        user_id = await authenticate_handshake(websocket)
    except Exception:
        logger.exception("realtime.handshake_failed")
        await _close_quietly(websocket, status.WS_1011_INTERNAL_ERROR)
        return
    if user_id is None:
        await _close_quietly(websocket, status.WS_1008_POLICY_VIOLATION)
        return
    await get_realtime_hub(websocket.app.state).serve(user_id, websocket)

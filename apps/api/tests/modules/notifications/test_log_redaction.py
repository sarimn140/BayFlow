"""SEC-38 on a real WebSocket handshake (D70; spec 04 "Logging, errors and secrets").

uvicorn logs every WebSocket handshake with its full path **and query string** at INFO on
`uvicorn.error` (`… "WebSocket /api/v1/ws?ticket=…" [accepted]`, or `… 403` when the app closes
before accept). This test serves the real app with uvicorn on 127.0.0.1:4105 (or on any free
port when another test run holds 4105), opens one accepted and one refused socket with the
`websockets` client, and reads what the app's JSON log handler actually wrote:
`ticket=[redacted]`, never the ticket. The server is stopped after the test.
"""

import asyncio
import io
import json
import logging
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta

import pytest
import uvicorn
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from app.core.config import Settings
from app.core.database import Database
from app.core.security import issue_token
from app.main import create_app
from app.shared.clock import SimulatedClock, utcnow
from tests.modules.notifications.support import World

pytestmark = pytest.mark.db

PORT = 4105  # this module's port (wave 2 port plan)
JSON_HANDLER = "bayflow-json"  # app.core.logging's handler on the root logger


@dataclass
class Served:
    port: int
    logs: io.StringIO


def listening_socket() -> socket.socket:
    """127.0.0.1:4105, or a free port when a concurrent test run already holds 4105."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", PORT))
    except OSError:
        sock.bind(("127.0.0.1", 0))
    return sock


@pytest.fixture
async def served(db: Database, settings: Settings) -> AsyncIterator[Served]:
    """The app served by uvicorn; yields its port and what its JSON log handler writes."""
    app = create_app(settings, database=db)  # installs the JSON handler with its filter
    handler = next(h for h in logging.getLogger().handlers if h.get_name() == JSON_HANDLER)
    assert isinstance(handler, logging.StreamHandler)
    buffer = io.StringIO()
    previous = handler.setStream(buffer)
    config = uvicorn.Config(
        app,
        log_config=None,  # keep the app's logging: uvicorn's loggers propagate to its handler
        lifespan="on",
        timeout_graceful_shutdown=5,
    )
    server = uvicorn.Server(config)
    sock = listening_socket()
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(15):
            while not server.started:
                assert not serving.done(), "uvicorn failed to start"
                await asyncio.sleep(0.02)
        yield Served(port=sock.getsockname()[1], logs=buffer)
    finally:
        server.should_exit = True
        await asyncio.wait_for(serving, timeout=15)
        sock.close()
        handler.setStream(previous)


async def test_sec38_tickets_are_redacted_from_uvicorns_handshake_lines(
    served: Served, world: World, clock: SimulatedClock
) -> None:
    ticket = issue_token(world.ayesha.id, "ws", utcnow())
    stale = issue_token(world.ayesha.id, "ws", utcnow() - timedelta(minutes=5))
    url = f"ws://127.0.0.1:{served.port}/api/v1/ws?ticket="

    async with connect(url + ticket) as socket:
        await socket.send(json.dumps({"type": "ping"}))
        assert json.loads(await socket.recv()) == {"type": "pong", "data": {}}
    with pytest.raises(InvalidStatus) as refused:  # closed before accept: HTTP 403 (DEP-04)
        async with connect(url + stale):
            pass
    assert refused.value.response.status_code == 403

    await asyncio.sleep(0.1)  # let the server finish logging the second handshake
    output = served.logs.getvalue()
    messages = [json.loads(line)["msg"] for line in output.splitlines() if line.strip()]
    handshakes = [message for message in messages if '"WebSocket /api/v1/ws' in message]
    assert any(
        message.endswith('"WebSocket /api/v1/ws?ticket=[redacted]" [accepted]')
        for message in handshakes
    ), handshakes
    assert any(
        message.endswith('"WebSocket /api/v1/ws?ticket=[redacted]" 403') for message in handshakes
    ), handshakes
    for secret in (ticket, stale, ticket.split(".")[2], stale.split(".")[2]):
        assert secret not in output
    assert "eyJ" not in output  # no JWT of any kind

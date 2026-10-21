"""Fixtures of the calls tests (spec 05 §14.1).

The real app with calling and the AI Front Desk switched on, LiveKit replaced by `FakeCallMedia`,
and the background sweeper replaced by a no-op (tests call `sweep_once` themselves with the
`SimulatedClock`, D63). Presence comes from fake sockets registered in the real hub, which also
record every push. Ring timers are cancelled after each test.
"""

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.database import Database
from app.modules.calls import service as calls_service
from app.modules.calls import timers
from app.modules.calls.providers.fake import FakeCallMedia
from app.shared.clock import SimulatedClock
from tests.conftest import make_settings
from tests.modules.bookings.support import Desk, World, build_world
from tests.modules.calls.conftest_constants import SERVICE_TOKEN
from tests.modules.calls.support import Online
from tests.modules.identity.builders import fast_password_hashing  # noqa: F401 - autouse fixture


@pytest.fixture
def settings() -> Settings:
    return make_settings(
        call_provider_url="wss://fake.livekit.test",
        call_provider_api_key="key",
        call_provider_api_secret="secret-secret-secret-secret-secret",
        llm_api_key="llm-key",
        agent_service_token=SERVICE_TOKEN,
    )


@pytest.fixture(autouse=True)
def no_background_sweeper(monkeypatch: pytest.MonkeyPatch) -> None:
    async def idle(*_: object) -> None:
        return None

    monkeypatch.setattr(calls_service, "run_sweeper", idle)


@pytest.fixture(autouse=True)
def cancel_ring_timers() -> Iterator[None]:
    yield
    for call_id in list(timers._ring_tasks):
        timers.cancel_ring_timeout(call_id)


@pytest.fixture
def media(db_app: FastAPI) -> FakeCallMedia:
    fake = FakeCallMedia()
    db_app.state.call_media = fake
    return fake


@pytest.fixture
def online(db_app: FastAPI) -> Online:
    return Online(db_app)


@pytest.fixture
async def world(db: Database, clock: SimulatedClock) -> World:
    return await build_world(db)


@pytest.fixture
def desk(db_client: httpx.AsyncClient, world: World) -> Desk:
    return Desk(db_client, world)

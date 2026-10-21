"""Helpers of the calls tests: fake sockets for presence and pushes, paths, and settling."""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI

from app.modules.notifications.realtime import get_realtime_hub
from app.shared.uow import drain_after_commit_tasks
from tests.modules.calls.conftest_constants import SERVICE_TOKEN


@dataclass(eq=False)
class FakeSocket:
    frames: list[dict[str, Any]] = field(default_factory=list)

    async def send_text(self, frame: str) -> None:
        self.frames.append(json.loads(frame))

    def types(self) -> list[str]:
        return [frame["type"] for frame in self.frames]


@dataclass
class Online:
    """Users with an open (fake) socket in the app's hub."""

    app: FastAPI
    sockets: dict[uuid.UUID, FakeSocket] = field(default_factory=dict)

    def add(self, user_id: uuid.UUID) -> FakeSocket:
        socket = FakeSocket()
        get_realtime_hub(self.app.state).connect(user_id, socket)  # type: ignore[arg-type]
        self.sockets[user_id] = socket
        return socket


async def settle() -> None:
    """Let after-commit work (pushes, dispatch) finish."""
    await asyncio.sleep(0)
    await drain_after_commit_tasks()


def agent_headers(call_token: str, *, service_token: str = SERVICE_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {service_token}", "X-Agent-Call-Token": call_token}


def internal(call_id: object, path: str) -> str:
    return f"/api/v1/internal/calls/{call_id}{path}"

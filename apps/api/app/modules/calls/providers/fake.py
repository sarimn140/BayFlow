"""An in-memory `CallMediaGateway` for tests (spec 05 §14.1): records every operation and can be
told to fail. Tokens are opaque strings; webhooks are accepted with the authorization `valid`."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.modules.calls.providers.base import JoinToken, MediaError, MediaEvent, WebhookRejectedError


@dataclass
class FakeCallMedia:
    url: str = "wss://fake.livekit.test"
    rooms: set[str] = field(default_factory=set)
    deleted_rooms: list[str] = field(default_factory=list)
    dispatches: dict[str, dict[str, Any]] = field(default_factory=dict)
    deleted_dispatches: list[str] = field(default_factory=list)
    tokens: list[dict[str, Any]] = field(default_factory=list)
    fail_create_room: bool = False
    fail_dispatch: bool = False

    async def create_room(self, name: str) -> None:
        if self.fail_create_room:
            msg = "create_room failed: quota"
            raise MediaError(msg)
        self.rooms.add(name)

    async def delete_room(self, name: str) -> None:
        self.rooms.discard(name)
        self.deleted_rooms.append(name)

    async def create_dispatch(self, *, room: str, agent_name: str, metadata: str) -> str:
        if self.fail_dispatch:
            msg = "create_dispatch failed: no worker"
            raise MediaError(msg)
        dispatch_id = f"AD_{len(self.dispatches) + 1}"
        self.dispatches[dispatch_id] = {
            "room": room,
            "agent_name": agent_name,
            "metadata": json.loads(metadata),
        }
        return dispatch_id

    async def delete_dispatch(self, *, dispatch_id: str, room: str) -> None:
        self.deleted_dispatches.append(dispatch_id)

    def issue_token(
        self, *, room: str, identity: str, name: str, ttl_seconds: int, now: datetime
    ) -> JoinToken:
        self.tokens.append({"room": room, "identity": identity, "name": name})
        return JoinToken(
            token=f"token:{room}:{identity}", expires_at=now + timedelta(seconds=ttl_seconds)
        )

    def verify_webhook(self, body: str, authorization: str) -> MediaEvent:
        if authorization != "valid":  # the fake's only accepted signature
            msg = "invalid webhook signature"
            raise WebhookRejectedError(msg)
        payload = json.loads(body)
        return MediaEvent(
            event=payload["event"],
            room=payload.get("room", {}).get("name", ""),
            identity=payload.get("participant", {}).get("identity"),
        )

    @property
    def last_dispatch_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = list(self.dispatches.values())[-1]["metadata"]
        return metadata

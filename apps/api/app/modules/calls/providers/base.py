"""The `CallMediaGateway` port (spec 05 §14.1, D90): everything the API asks of LiveKit.

The API owns call state; the gateway only creates and deletes rooms, dispatches the agent, issues
join tokens and verifies webhooks. Failures raise `MediaError`.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class MediaError(Exception):
    """LiveKit failed or refused (unreachable, quota); the message is safe to log."""


class WebhookRejectedError(MediaError):
    """A webhook whose signature or body hash does not verify."""


@dataclass(frozen=True, slots=True)
class JoinToken:
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class MediaEvent:
    """The parts of a LiveKit webhook the calls module acts on (§8.5)."""

    event: str  # participant_left, participant_connection_aborted, room_finished, …
    room: str
    identity: str | None


class CallMediaGateway(Protocol):
    url: str  # the browsers' LiveKit URL (`CallConnection.url`)

    async def create_room(self, name: str) -> None: ...

    async def delete_room(self, name: str) -> None: ...

    async def create_dispatch(self, *, room: str, agent_name: str, metadata: str) -> str: ...

    async def delete_dispatch(self, *, dispatch_id: str, room: str) -> None: ...

    def issue_token(
        self, *, room: str, identity: str, name: str, ttl_seconds: int, now: datetime
    ) -> JoinToken: ...

    def verify_webhook(self, body: str, authorization: str) -> MediaEvent: ...

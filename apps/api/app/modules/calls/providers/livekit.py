"""LiveKit Cloud adapter of the `CallMediaGateway` port (D57, spec 05 §2, §8.3, §8.5).

The `CALL_PROVIDER_*` values are passed explicitly; the SDK's `LIVEKIT_*` defaults are never read
(spec 05 §10). Each server call opens and closes its own client, so no aiohttp session outlives an
event loop.
"""

from datetime import datetime, timedelta

from livekit import api as lk

from app.modules.calls.constants import (
    ROOM_DEPARTURE_TIMEOUT_SECONDS,
    ROOM_EMPTY_TIMEOUT_SECONDS,
    ROOM_MAX_PARTICIPANTS,
)
from app.modules.calls.providers.base import JoinToken, MediaError, MediaEvent, WebhookRejectedError


def _http_url(url: str) -> str:
    """The Server API speaks HTTPS; `CALL_PROVIDER_URL` is the `wss://` URL browsers use."""
    if url.startswith("wss://"):
        return "https://" + url.removeprefix("wss://")
    if url.startswith("ws://"):
        return "http://" + url.removeprefix("ws://")
    return url


class LiveKitGateway:
    def __init__(self, *, url: str, api_key: str, api_secret: str) -> None:
        self.url = url
        self._api_key = api_key
        self._api_secret = api_secret
        self._receiver = lk.WebhookReceiver(lk.TokenVerifier(api_key, api_secret))

    def _client(self) -> lk.LiveKitAPI:
        return lk.LiveKitAPI(_http_url(self.url), self._api_key, self._api_secret)

    async def create_room(self, name: str) -> None:
        client = self._client()
        try:
            await client.room.create_room(
                lk.CreateRoomRequest(
                    name=name,
                    empty_timeout=ROOM_EMPTY_TIMEOUT_SECONDS,
                    departure_timeout=ROOM_DEPARTURE_TIMEOUT_SECONDS,
                    max_participants=ROOM_MAX_PARTICIPANTS,
                )
            )
        except Exception as exc:
            msg = f"create_room failed: {type(exc).__name__}"
            raise MediaError(msg) from exc
        finally:
            await client.aclose()

    async def delete_room(self, name: str) -> None:
        client = self._client()
        try:
            await client.room.delete_room(lk.DeleteRoomRequest(room=name))
        except Exception as exc:
            msg = f"delete_room failed: {type(exc).__name__}"
            raise MediaError(msg) from exc
        finally:
            await client.aclose()

    async def create_dispatch(self, *, room: str, agent_name: str, metadata: str) -> str:
        client = self._client()
        try:
            dispatch = await client.agent_dispatch.create_dispatch(
                lk.CreateAgentDispatchRequest(agent_name=agent_name, room=room, metadata=metadata)
            )
        except Exception as exc:
            msg = f"create_dispatch failed: {type(exc).__name__}"
            raise MediaError(msg) from exc
        finally:
            await client.aclose()
        return str(dispatch.id)

    async def delete_dispatch(self, *, dispatch_id: str, room: str) -> None:
        client = self._client()
        try:
            await client.agent_dispatch.delete_dispatch(dispatch_id, room)
        except Exception as exc:
            msg = f"delete_dispatch failed: {type(exc).__name__}"
            raise MediaError(msg) from exc
        finally:
            await client.aclose()

    def issue_token(
        self, *, room: str, identity: str, name: str, ttl_seconds: int, now: datetime
    ) -> JoinToken:
        """One user, one room, microphone only (spec 05 §8.3, §13)."""
        grants = lk.VideoGrants(
            room_join=True,
            room=room,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=False,
            can_publish_sources=["microphone"],
        )
        ttl = timedelta(seconds=ttl_seconds)
        token = (
            lk.AccessToken(self._api_key, self._api_secret)
            .with_identity(identity)
            .with_name(name)
            .with_ttl(ttl)
            .with_grants(grants)
            .to_jwt()
        )
        return JoinToken(token=token, expires_at=now + ttl)

    def verify_webhook(self, body: str, authorization: str) -> MediaEvent:
        try:
            event = self._receiver.receive(body, authorization)
        except Exception as exc:
            msg = "invalid webhook signature"
            raise WebhookRejectedError(msg) from exc
        return MediaEvent(
            event=event.event,
            room=event.room.name,
            identity=event.participant.identity or None,
        )

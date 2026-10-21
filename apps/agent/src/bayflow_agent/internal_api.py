"""Client of the API's agent routes `/api/v1/internal/calls/{call_id}/…` (spec 05 §5.1, §5.3).

Every request carries the service token and this call's token. The API scopes everything to the
call; this client only maps answers to what the model should be told (§5.5): a 404 for a booking is
`{"found": false}`, everything else that failed becomes a `ToolError` with an instruction.
"""

import asyncio
import logging
from http import HTTPStatus
from typing import Any

import httpx
from livekit.agents.llm import ToolError

logger = logging.getLogger("bayflow_agent.api")

TIMEOUT_SECONDS = 4.0  # §5.5: 4 s timeout, one retry for GET requests

NOT_VERIFIED = (
    "The caller is not verified yet. Ask for their name, phone number, e-mail address or "
    "booking reference and call verify_caller first."
)
CALL_ENDED = "The call has ended. Do not call any more tools."
INVALID = "That request was not accepted (for example, that time is no longer available)."
UNAVAILABLE = (
    "The booking system is not responding. Apologise, say you do not have that information right "
    "now, and offer request_callback."
)


TOOL_ERRORS: dict[int, str] = {
    HTTPStatus.FORBIDDEN: NOT_VERIFIED,
    HTTPStatus.CONFLICT: CALL_ENDED,
    HTTPStatus.UNPROCESSABLE_ENTITY: INVALID,
}


class InternalApiError(Exception):
    """A non-tool call (session, end, summary) failed; `status` is the HTTP status or 0."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class InternalApi:
    def __init__(
        self,
        base_url: str,
        service_token: str,
        call_id: str,
        call_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.call_id = call_id
        self._client = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/api/v1/internal/calls/{call_id}",
            headers={
                "Authorization": f"Bearer {service_token}",
                "X-Agent-Call-Token": call_token,
            },
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _send(
        self, method: str, path: str, *, json: Any = None, params: Any = None
    ) -> httpx.Response:
        attempts = 2 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                return await self._client.request(method, path, json=json, params=params)
            except httpx.HTTPError as exc:
                logger.warning(
                    "internal_api.request_failed",
                    extra={"call_id": self.call_id, "path": path, "error": type(exc).__name__},
                )
                if attempt + 1 == attempts:
                    raise ToolError(UNAVAILABLE) from exc
                await asyncio.sleep(0.2)
        raise ToolError(UNAVAILABLE)  # pragma: no cover - the loop always returns or raises

    async def _tool(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Any = None,
        not_found: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._send(method, path, json=json, params=params)
        if response.status_code in {HTTPStatus.OK, HTTPStatus.CREATED}:
            body: dict[str, Any] = response.json()
            return body
        if response.status_code == HTTPStatus.NOT_FOUND and not_found is not None:
            return not_found
        raise ToolError(TOOL_ERRORS.get(response.status_code, UNAVAILABLE))

    # --- Tools (§5.2) ---

    async def verify_caller(self, **claim: str | None) -> dict[str, Any]:
        body = {key: value for key, value in claim.items() if value}
        return await self._tool("POST", "/verify-caller", json=body)

    async def get_shop(self) -> dict[str, Any]:
        return await self._tool("GET", "/shop")

    async def get_bookings(self) -> dict[str, Any]:
        return await self._tool("GET", "/bookings")

    async def get_booking(self, reference: str) -> dict[str, Any]:
        return await self._tool("GET", f"/bookings/{reference}", not_found={"found": False})

    async def get_estimate(self, reference: str) -> dict[str, Any]:
        return await self._tool(
            "GET", f"/bookings/{reference}/estimate", not_found={"found": False}
        )

    async def get_slots(self, date: str, days: int) -> dict[str, Any]:
        return await self._tool("GET", "/available-slots", params={"date": date, "days": days})

    async def create_task(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._tool("POST", "/tasks", json=body, not_found={"found": False})

    # --- Lifecycle (not tools) ---

    async def start_session(self) -> dict[str, Any]:
        """A2. A 409 means the call no longer waits for the agent: the job should exit."""
        response = await self._send("POST", "/session")
        if response.status_code != HTTPStatus.OK:
            raise InternalApiError(response.status_code, "session refused")
        body: dict[str, Any] = response.json()
        return body

    async def end_call(self, error: str | None = None) -> None:
        """A3 (idempotent on the API side); never raises."""
        try:
            await self._client.post("/end", json={"error": error} if error else {})
        except httpx.HTTPError as exc:
            logger.warning("internal_api.end_failed", extra={"error": type(exc).__name__})

    async def post_summary(self, payload: dict[str, Any]) -> int:
        """A5; retried once on a 5xx or a network error (AG-03). Returns the final status."""
        status = 0
        for _ in range(2):
            try:
                response = await self._client.post("/summary", json=payload, timeout=15.0)
                status = response.status_code
            except httpx.HTTPError:
                status = 0
            if status and status < HTTPStatus.INTERNAL_SERVER_ERROR:  # retry server errors only
                return status
            await asyncio.sleep(0.5)
        return status

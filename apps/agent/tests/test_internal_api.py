"""AG-01: each call hits the right path with both headers; answers map to tool results (§5.5)."""

import json
from typing import Any

import httpx
import pytest
from livekit.agents.llm import ToolError

from bayflow_agent.internal_api import (
    CALL_ENDED,
    INVALID,
    NOT_VERIFIED,
    UNAVAILABLE,
    InternalApi,
    InternalApiError,
)

seen: list[httpx.Request] = []


def api(handler: Any) -> InternalApi:
    seen.clear()

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        result: httpx.Response = handler(request)
        return result

    return InternalApi(
        "http://api.test/", "svc", "call-1", "tok", transport=httpx.MockTransport(record)
    )


async def test_tools_send_both_tokens_to_the_call_path() -> None:
    client = api(lambda request: httpx.Response(200, json={"ok": True}))
    assert await client.get_estimate("BF-7K2M9Q") == {"ok": True}
    [request] = seen
    assert request.url.path == "/api/v1/internal/calls/call-1/bookings/BF-7K2M9Q/estimate"
    assert request.headers["authorization"] == "Bearer svc"
    assert request.headers["x-agent-call-token"] == "tok"


async def test_verify_caller_sends_only_given_fields() -> None:
    client = api(lambda request: httpx.Response(200, json={"verified": True}))
    await client.verify_caller(name="Ahmed", phone=None, email=None, booking_reference=None)
    assert json.loads(seen[0].content) == {"name": "Ahmed"}


async def test_an_unknown_booking_is_found_false() -> None:
    client = api(lambda request: httpx.Response(404, json={"code": "NOT_FOUND"}))
    assert await client.get_booking("BF-AAAAAA") == {"found": False}


@pytest.mark.parametrize(
    ("status", "message"),
    [(403, NOT_VERIFIED), (409, CALL_ENDED), (422, INVALID), (500, UNAVAILABLE)],
)
async def test_failures_become_tool_errors(status: int, message: str) -> None:
    client = api(lambda request: httpx.Response(status, json={}))
    with pytest.raises(ToolError, match=message[:20]):
        await client.get_bookings()


async def test_get_requests_are_retried_once_on_network_errors() -> None:
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"items": []})

    client = api(flaky)
    assert await client.get_bookings() == {"items": []}
    assert calls["n"] == 2


async def test_session_refusal_and_summary_retry() -> None:
    client = api(lambda request: httpx.Response(409, json={"code": "CALL_NOT_ACTIVE"}))
    with pytest.raises(InternalApiError):
        await client.start_session()
    statuses = iter([503, 201])
    retried = api(lambda request: httpx.Response(next(statuses), json={}))
    assert await retried.post_summary({"transcript": []}) == 201
    assert len(seen) == 2

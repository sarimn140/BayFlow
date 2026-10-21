"""The AI Front Desk agent's internal routes (spec 05 §5, §6; §14.1 FD-01 … FD-12).

Each test drives a real customer → shop call to the AI leg (nobody answers, the deadline passes,
the sweeper dispatches the agent) and then talks to the API exactly as the agent does.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import text

from app.core.database import Database
from app.modules.calls import service as calls_service
from app.modules.calls.providers.fake import FakeCallMedia
from app.shared.clock import SimulatedClock, utcnow
from app.shared.enums import BookingStatus
from tests.modules.bookings.support import Desk, Journey, World, drive_booking_to
from tests.modules.calls.support import agent_headers, internal, settle
from tests.modules.identity.builders import bearer


@dataclass
class AiCall:
    call_id: str
    token: str
    journey: Journey

    @property
    def headers(self) -> dict[str, str]:
        return agent_headers(self.token)

    def path(self, suffix: str) -> str:
        return internal(self.call_id, suffix)


async def _ai_call(  # noqa: PLR0913 - the fixtures a dispatched AI leg needs
    desk: Desk,
    api: httpx.AsyncClient,
    app: FastAPI,
    clock: SimulatedClock,
    media: FakeCallMedia,
    *,
    status: BookingStatus = BookingStatus.PENDING,
    session: bool = True,
) -> AiCall:
    journey = await drive_booking_to(desk, status)
    started = await api.post(
        f"/api/v1/me/bookings/{journey.id}/calls", headers=journey.customer.headers
    )
    assert started.status_code == 201, started.text
    clock.advance(timedelta(seconds=20))
    await calls_service.sweep_once(app.state, utcnow())
    await settle()
    metadata = media.last_dispatch_metadata
    call = AiCall(metadata["call_id"], metadata["call_token"], journey)
    if session:
        response = await api.post(call.path("/session"), headers=call.headers)
        assert response.status_code == 200, response.text
    return call


async def _verify(api: httpx.AsyncClient, call: AiCall) -> None:
    response = await api.post(
        call.path("/verify-caller"),
        json={"booking_reference": call.journey.reference},
        headers=call.headers,
    )
    assert response.json()["verified"] is True


async def _rows(db: Database, sql: str) -> list[dict[str, Any]]:
    async with db.sessionmaker() as session:
        return [dict(row) for row in (await session.execute(text(sql))).mappings().all()]


async def test_service_and_call_tokens_are_both_required(  # FD-01, FD-08
    desk: Desk,
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    clock: SimulatedClock,
    media: FakeCallMedia,
) -> None:
    call = await _ai_call(desk, db_client, db_app, clock, media, session=False)
    shop = call.path("/shop")
    no_service = await db_client.get(shop, headers={"X-Agent-Call-Token": call.token})
    assert no_service.status_code == 401
    wrong_call = await db_client.get(shop, headers=agent_headers("not-the-token"))
    assert wrong_call.status_code == 404
    session = await db_client.post(call.path("/session"), headers=call.headers)
    assert session.status_code == 200
    body = session.json()
    assert body["max_ai_seconds"] == 300
    assert "customer" not in str(body).lower()  # nothing about the caller before verification
    again = await db_client.post(call.path("/session"), headers=call.headers)
    assert again.status_code == 409
    assert again.json()["code"] == "CALL_NOT_ACTIVE"


async def test_booking_data_needs_a_verified_caller(  # FD-02, FD-03
    desk: Desk,
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    clock: SimulatedClock,
    media: FakeCallMedia,
) -> None:
    call = await _ai_call(desk, db_client, db_app, clock, media)
    gated = await db_client.get(call.path("/bookings"), headers=call.headers)
    assert gated.status_code == 403
    assert gated.json()["code"] == "IDENTITY_NOT_VERIFIED"
    wrong = await db_client.post(
        call.path("/verify-caller"), json={"name": "Zainab"}, headers=call.headers
    )
    assert wrong.json() == {
        "verified": False,
        "method": None,
        "attempts_left": 2,
        "locked": False,
        "first_name": None,
        "call_booking_reference": None,
    }  # a failed check reveals nothing stored
    code = call.journey.reference.removeprefix("BF-")
    spoken = "b f " + code.replace("0", "O")  # "B F 7K2M9Q", with an O for a zero
    verified = await db_client.post(
        call.path("/verify-caller"), json={"booking_reference": spoken}, headers=call.headers
    )
    body = verified.json()
    assert body["verified"] is True
    assert body["method"] == "BOOKING_REFERENCE"
    assert body["first_name"] == "Ahmed"
    assert body["call_booking_reference"] == call.journey.reference
    listed = await db_client.get(call.path("/bookings"), headers=call.headers)
    assert listed.status_code == 200
    [item] = listed.json()["items"]
    assert item["is_call_booking"] is True
    assert item["status_label"] == "Booking received"


async def test_three_failed_checks_lock_the_caller_out(  # FD-03
    desk: Desk,
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    clock: SimulatedClock,
    media: FakeCallMedia,
) -> None:
    call = await _ai_call(desk, db_client, db_app, clock, media)
    for _ in range(3):
        last = await db_client.post(
            call.path("/verify-caller"), json={"email": "x@y.test"}, headers=call.headers
        )
    assert last.json()["locked"] is True
    right_name = await db_client.post(
        call.path("/verify-caller"), json={"name": "Ahmad"}, headers=call.headers
    )
    assert right_name.json()["verified"] is False  # locked for the rest of the call


async def test_estimate_view_and_scoping(  # FD-04, FD-05
    desk: Desk,
    world: World,
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    clock: SimulatedClock,
    media: FakeCallMedia,
) -> None:
    call = await _ai_call(
        desk, db_client, db_app, clock, media, status=BookingStatus.AWAITING_CUSTOMER
    )
    await _verify(db_client, call)
    estimate = await db_client.get(
        call.path(f"/bookings/{call.journey.reference}/estimate"), headers=call.headers
    )
    assert estimate.status_code == 200, estimate.text
    body = estimate.json()
    assert body["has_estimate"] is True
    assert body["status"] == "SENT"
    assert body["grand_total"].endswith(".00")
    booking = await db_client.get(
        call.path(f"/bookings/{call.journey.reference}"), headers=call.headers
    )
    assert booking.json()["status_label"] == "Estimate awaiting your approval"
    assert "approve-estimate" in booking.json()["customer_actions"]
    other = await desk.book()  # another customer's booking at the same shop
    foreign = await db_client.get(call.path(f"/bookings/{other.reference}"), headers=call.headers)
    assert foreign.status_code == 404


async def test_tasks_from_tools(  # noqa: PLR0913, PLR0917 - fixtures; FD-07, FD-13
    desk: Desk,
    world: World,
    db: Database,
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    clock: SimulatedClock,
    media: FakeCallMedia,
) -> None:
    call = await _ai_call(desk, db_client, db_app, clock, media)
    tasks = call.path("/tasks")
    unverified = await db_client.post(
        tasks,
        json={
            "kind": "RESCHEDULE_REQUEST",
            "booking_reference": call.journey.reference,
            "preferred_starts": [utcnow().isoformat()],
        },
        headers=call.headers,
    )
    assert unverified.status_code == 403
    escalation = await db_client.post(
        tasks,
        json={"kind": "ESCALATION", "topic": "brakes not working", "safety_concern": True},
        headers=call.headers,
    )
    assert escalation.status_code == 201
    repeat = await db_client.post(
        tasks,
        json={"kind": "ESCALATION", "topic": "brakes", "description": "still worried"},
        headers=call.headers,
    )
    assert repeat.status_code == 200
    assert repeat.json() == {"task_id": escalation.json()["task_id"], "created": False}
    [task] = await _rows(db, "select title, is_urgent, metadata from tasks")
    assert task["title"] == "URGENT: Ahmed — brakes not working"
    assert task["is_urgent"] is True
    assert task["metadata"]["safety_concern"] is True
    notified = await _rows(
        db, "select recipient_user_id from notifications where type = 'AI_TASK_CREATED'"
    )
    assert [n["recipient_user_id"] for n in notified] == [world.advisor.user.id]
    statuses = await _rows(db, "select id::text as id, status from bookings")
    [booking] = [row for row in statuses if row["id"] == call.journey.id]
    assert booking["status"] == "PENDING"  # the agent never changes a booking


async def test_summary_creates_a_follow_up_task_once(  # noqa: PLR0913, PLR0917 - fixtures; FD-10
    desk: Desk,
    world: World,
    db: Database,
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    clock: SimulatedClock,
    media: FakeCallMedia,
) -> None:
    call = await _ai_call(desk, db_client, db_app, clock, media)
    await _verify(db_client, call)
    end = await db_client.post(call.path("/end"), json={}, headers=call.headers)
    assert end.status_code == 200
    data = await db_client.get(call.path("/bookings"), headers=call.headers)
    assert data.status_code == 409  # FD-12: the leg has ended
    summary = {
        "transcript": [
            {"role": "assistant", "text": "Hello, you've reached the shop."},
            {"role": "customer", "text": "Hi, this is Ahmed, what's my status?"},
        ],
        "summary": {
            "intent": "Asked about the booking status",
            "intent_category": "STATUS_INQUIRY",
            "details": "Ahmed asked for the status; told it was received.",
            "sentiment": "NEUTRAL",
            "follow_up_task_title": "Customer Ahmed asked about status; no action needed",
            "urgent": False,
            "language": "en",
        },
        "model": "gemini-2.5-flash",
    }
    first = await db_client.post(call.path("/summary"), json=summary, headers=call.headers)
    assert first.status_code == 201, first.text
    again = await db_client.post(call.path("/summary"), json=summary, headers=call.headers)
    assert again.status_code == 200
    assert again.json()["summary_id"] == first.json()["summary_id"]
    [task] = await _rows(db, "select kind, title from tasks")
    assert task == {
        "kind": "FOLLOW_UP",
        "title": "Customer Ahmed asked about status; no action needed",
    }
    detail = await db_client.get(
        f"/api/v1/shops/{world.shop_id}/calls/{call.call_id}",
        headers=bearer(world.advisor.user.id),
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["summary"]["intent"] == "Asked about the booking status"
    assert body["identity_method"] == "BOOKING_REFERENCE"
    assert body["ai"]["status"] == "ENDED"
    assert [t["kind"] for t in body["tasks"]] == ["FOLLOW_UP"]
    listed = await db_client.get(
        f"/api/v1/shops/{world.shop_id}/tasks", headers=bearer(world.advisor.user.id)
    )
    [open_task] = listed.json()["items"]
    done_path = f"/api/v1/shops/{world.shop_id}/tasks/{open_task['id']}/mark-done"
    done = await db_client.post(
        done_path, json={"note": "Called back"}, headers=bearer(world.advisor.user.id)
    )
    assert done.json()["status"] == "DONE"
    assert done.json()["done_by"]["user_id"] == str(world.advisor.user.id)


async def test_an_invalid_summary_falls_back(  # FD-10
    desk: Desk,
    db: Database,
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    clock: SimulatedClock,
    media: FakeCallMedia,
) -> None:
    call = await _ai_call(desk, db_client, db_app, clock, media)
    response = await db_client.post(
        call.path("/summary"),
        json={"transcript": [], "summary": {"intent": ""}, "summary_error": "refused"},
        headers=call.headers,
    )
    assert response.status_code == 201
    assert response.json()["is_fallback"] is True
    [task] = await _rows(db, "select kind, title from tasks")
    assert task["kind"] == "CALLBACK"  # no customer speech: the caller left early
    assert "caller left" in task["title"]


async def test_an_agent_that_never_joins_leaves_a_callback(  # FD-09 (A4)
    desk: Desk,
    db: Database,
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    clock: SimulatedClock,
    media: FakeCallMedia,
) -> None:
    call = await _ai_call(desk, db_client, db_app, clock, media, session=False)
    clock.advance(timedelta(seconds=11))
    await calls_service.sweep_once(db_app.state, utcnow())
    await settle()
    [row] = await _rows(db, "select ai_error, ai_ended_at from call_logs")
    assert row["ai_error"] == "AGENT_UNAVAILABLE"
    [task] = await _rows(db, "select kind, title from tasks")
    assert task["kind"] == "CALLBACK"
    assert "AI Front Desk unavailable" in task["title"]
    assert media.deleted_dispatches == ["AD_1"]
    assert f"call-{call.call_id}" in media.deleted_rooms


async def test_a_missing_summary_gets_a_fallback(  # FD-11 (A6)
    desk: Desk,
    db: Database,
    db_client: httpx.AsyncClient,
    db_app: FastAPI,
    clock: SimulatedClock,
    media: FakeCallMedia,
) -> None:
    call = await _ai_call(desk, db_client, db_app, clock, media)
    await db_client.post(call.path("/end"), json={}, headers=call.headers)
    clock.advance(timedelta(seconds=181))
    await calls_service.sweep_once(db_app.state, utcnow())
    [summary] = await _rows(db, "select is_fallback from ai_call_summaries")
    assert summary["is_fallback"] is True
    [task] = await _rows(db, "select kind from tasks")
    assert task["kind"] == "CALLBACK"

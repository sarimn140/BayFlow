"""Call lifecycle over HTTP (spec 05 §3, §14.1 CALL-01 … CALL-15).

LiveKit is the fake gateway; ring deadlines and the sweeper are driven with the `SimulatedClock`.
"""

import asyncio
import json
from datetime import timedelta
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import text

from app.core.database import Database
from app.modules.calls import service as calls_service
from app.modules.calls.providers.fake import FakeCallMedia
from app.shared.clock import SimulatedClock, utcnow
from tests.modules.bookings.support import Desk, Journey, World
from tests.modules.calls.support import Online, settle
from tests.modules.identity.builders import bearer


async def _start_c2s(api: httpx.AsyncClient, journey: Journey) -> dict[str, Any]:
    response = await api.post(
        f"/api/v1/me/bookings/{journey.id}/calls", headers=journey.customer.headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def _staff(world: World, path: str) -> str:
    return f"/api/v1/shops/{world.shop_id}{path}"


async def _rows(db: Database, sql: str) -> list[dict[str, Any]]:
    async with db.sessionmaker() as session:
        return [dict(row) for row in (await session.execute(text(sql))).mappings().all()]


async def test_a_customer_call_rings_the_online_advisor_only(  # CALL-01
    desk: Desk,
    world: World,
    media: FakeCallMedia,
    online: Online,
    db_client: httpx.AsyncClient,
) -> None:
    journey = await desk.book()
    advisor_socket = online.add(world.advisor.user.id)
    technician_socket = online.add(world.technician.user.id)
    started = await _start_c2s(db_client, journey)
    await settle()
    call = started["call"]
    assert call["status"] == "RINGING"
    assert call["rung_count"] == 1
    assert call["direction"] == "CUSTOMER_TO_SHOP"
    assert started["connection"]["room"] == f"call-{call['id']}"
    assert started["connection"]["identity"] == f"u_{journey.customer.user_id}"
    assert f"call-{call['id']}" in media.rooms
    assert advisor_socket.types() == ["call.incoming"]
    assert technician_socket.types() == []
    assert "phone" not in str(call)  # CALL-14
    assert "email" not in str(call)


async def test_first_accept_wins_and_only_the_callee_gets_a_token(  # CALL-02, CALL-03
    desk: Desk, world: World, media: FakeCallMedia, online: Online, db_client: httpx.AsyncClient
) -> None:
    journey = await desk.book()
    online.add(world.advisor.user.id)
    call = (await _start_c2s(db_client, journey))["call"]
    accept = _staff(world, f"/calls/{call['id']}/accept")
    first, second = await asyncio.gather(
        db_client.post(accept, headers=bearer(world.advisor.user.id)),
        db_client.post(accept, headers=bearer(world.advisor.user.id)),
    )
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409]
    winner = first if first.status_code == 200 else second
    loser = second if winner is first else first
    assert loser.json()["code"] == "CALL_ALREADY_ANSWERED"
    assert winner.json()["call"]["status"] == "CONNECTED"
    assert winner.headers["cache-control"] == "no-store"
    assert winner.json()["connection"]["identity"] == f"u_{world.advisor.user.id}"


async def test_a_technician_may_not_answer(  # CALL-10, CALL-21
    desk: Desk, world: World, media: FakeCallMedia, db_client: httpx.AsyncClient
) -> None:
    journey = await desk.book()
    call = (await _start_c2s(db_client, journey))["call"]
    response = await db_client.post(
        _staff(world, f"/calls/{call['id']}/accept"), headers=bearer(world.technician.user.id)
    )
    assert response.status_code == 404
    owner = await db_client.post(  # the shop has an active SA: the Owner is not an eligible callee
        _staff(world, f"/calls/{call['id']}/accept"), headers=bearer(world.owner.id)
    )
    assert owner.status_code == 403


async def test_no_answer_goes_to_the_ai_after_the_deadline(  # noqa: PLR0913, PLR0917 - fixtures; CALL-04, CALL-15
    desk: Desk,
    world: World,
    media: FakeCallMedia,
    db_app: FastAPI,
    db: Database,
    clock: SimulatedClock,
    db_client: httpx.AsyncClient,
) -> None:
    journey = await desk.book()
    call = (await _start_c2s(db_client, journey))["call"]
    assert call["rung_count"] == 0  # nobody online (D77): it still rings the full 20 s
    clock.advance(timedelta(seconds=19))
    await calls_service.sweep_once(db_app.state, utcnow())
    [row] = await _rows(db, "select status from call_logs")
    assert row["status"] == "RINGING"
    clock.advance(timedelta(seconds=1))
    await calls_service.sweep_once(db_app.state, utcnow())
    await settle()
    [row] = await _rows(
        db, "select status, missed_reason, ai_dispatched_at, ai_dispatch_id from call_logs"
    )
    assert (row["status"], row["missed_reason"]) == ("MISSED", "NO_ANSWER")
    assert row["ai_dispatched_at"] is not None
    assert row["ai_dispatch_id"] == "AD_1"
    metadata = media.last_dispatch_metadata
    assert metadata["call_id"] == call["id"]
    assert len(metadata["call_token"]) == 43
    missed = await _rows(
        db, "select recipient_user_id, body from notifications where type = 'CALL_MISSED'"
    )
    assert [n["recipient_user_id"] for n in missed] == [world.advisor.user.id]
    assert "AI Front Desk" in missed[0]["body"]
    await calls_service.sweep_once(db_app.state, utcnow())  # CALL-05: a second pass does nothing
    assert len(media.dispatches) == 1


async def test_every_rung_advisor_declining_sends_the_call_to_the_ai(  # CALL-06
    desk: Desk,
    world: World,
    media: FakeCallMedia,
    online: Online,
    db: Database,
    db_client: httpx.AsyncClient,
) -> None:
    journey = await desk.book()
    online.add(world.advisor.user.id)
    call = (await _start_c2s(db_client, journey))["call"]
    response = await db_client.post(
        _staff(world, f"/calls/{call['id']}/decline"), headers=bearer(world.advisor.user.id)
    )
    assert response.status_code == 200
    assert response.json()["missed_reason"] == "DECLINED"
    await settle()
    assert len(media.dispatches) == 1


async def test_a_caller_hanging_up_while_ringing_gets_no_ai(  # CALL-07
    desk: Desk, media: FakeCallMedia, db_client: httpx.AsyncClient
) -> None:
    journey = await desk.book()
    call = (await _start_c2s(db_client, journey))["call"]
    response = await db_client.post(
        f"/api/v1/me/calls/{call['id']}/end", headers=journey.customer.headers
    )
    assert response.status_code == 200
    assert response.json()["missed_reason"] == "CALLER_HUNG_UP"
    await settle()
    assert media.dispatches == {}
    assert f"call-{call['id']}" in media.deleted_rooms


async def test_a_missed_shop_call_notifies_the_customer_and_never_the_ai(  # noqa: PLR0913, PLR0917 - fixtures; CALL-08
    desk: Desk,
    world: World,
    media: FakeCallMedia,
    db_app: FastAPI,
    db: Database,
    clock: SimulatedClock,
    db_client: httpx.AsyncClient,
) -> None:
    journey = await desk.book()
    started = await db_client.post(
        _staff(world, f"/bookings/{journey.id}/calls"), headers=bearer(world.advisor.user.id)
    )
    assert started.status_code == 201, started.text
    clock.advance(timedelta(seconds=21))
    await calls_service.sweep_once(db_app.state, utcnow())
    await settle()
    assert media.dispatches == {}
    missed = await _rows(
        db, "select recipient_user_id from notifications where type = 'CALL_MISSED'"
    )
    assert [n["recipient_user_id"] for n in missed] == [journey.customer.user_id]


async def test_ending_a_connected_call_records_the_duration_once(  # CALL-09
    desk: Desk,
    world: World,
    media: FakeCallMedia,
    online: Online,
    clock: SimulatedClock,
    db_client: httpx.AsyncClient,
) -> None:
    journey = await desk.book()
    online.add(world.advisor.user.id)
    call = (await _start_c2s(db_client, journey))["call"]
    await db_client.post(
        _staff(world, f"/calls/{call['id']}/accept"), headers=bearer(world.advisor.user.id)
    )
    clock.advance(timedelta(seconds=42))
    end = f"/api/v1/me/calls/{call['id']}/end"
    first = await db_client.post(end, headers=journey.customer.headers)
    second = await db_client.post(end, headers=journey.customer.headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "ENDED"
    assert first.json()["duration_seconds"] == 42
    assert second.json() == first.json()


async def test_one_active_call_per_booking_and_rate_limits(  # CALL-11, CALL-12
    desk: Desk, media: FakeCallMedia, db: Database, db_client: httpx.AsyncClient
) -> None:
    journey = await desk.book()
    call = (await _start_c2s(db_client, journey))["call"]
    busy = await db_client.post(
        f"/api/v1/me/bookings/{journey.id}/calls", headers=journey.customer.headers
    )
    assert busy.status_code == 409
    assert busy.json()["code"] == "CALL_BUSY"
    end = f"/api/v1/me/calls/{call['id']}/end"
    for _ in range(4):
        await db_client.post(end, headers=journey.customer.headers)
        call = (await _start_c2s(db_client, journey))["call"]
        end = f"/api/v1/me/calls/{call['id']}/end"
    await db_client.post(end, headers=journey.customer.headers)
    limited = await db_client.post(
        f"/api/v1/me/bookings/{journey.id}/calls", headers=journey.customer.headers
    )
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


async def test_livekit_failure_stores_nothing(  # CALL-12
    desk: Desk, media: FakeCallMedia, db: Database, db_client: httpx.AsyncClient
) -> None:
    journey = await desk.book()
    media.fail_create_room = True
    response = await db_client.post(
        f"/api/v1/me/bookings/{journey.id}/calls", headers=journey.customer.headers
    )
    assert response.status_code == 503
    assert response.json()["code"] == "CALLING_DISABLED"
    assert await _rows(db, "select id from call_logs") == []


async def test_webhook_signature_and_participant_left(  # CALL-13
    desk: Desk,
    world: World,
    media: FakeCallMedia,
    online: Online,
    db_client: httpx.AsyncClient,
) -> None:
    journey = await desk.book()
    online.add(world.advisor.user.id)
    call = (await _start_c2s(db_client, journey))["call"]
    await db_client.post(
        _staff(world, f"/calls/{call['id']}/accept"), headers=bearer(world.advisor.user.id)
    )
    body = json.dumps(
        {
            "event": "participant_left",
            "room": {"name": f"call-{call['id']}"},
            "participant": {"identity": f"u_{journey.customer.user_id}"},
        }
    )
    bad = await db_client.post(
        "/api/v1/webhooks/livekit", content=body, headers={"Authorization": "forged"}
    )
    assert bad.status_code == 401
    good = await db_client.post(
        "/api/v1/webhooks/livekit", content=body, headers={"Authorization": "valid"}
    )
    assert good.status_code == 200
    calls = await db_client.get(_staff(world, "/calls"), headers=bearer(world.advisor.user.id))
    assert calls.json()["items"][0]["status"] == "ENDED"


async def test_a_socket_that_connects_mid_ring_gets_the_call_again(  # CALL-18, CALL-21
    desk: Desk,
    world: World,
    media: FakeCallMedia,
    db_app: FastAPI,
    db: Database,
    db_client: httpx.AsyncClient,
) -> None:
    journey = await desk.book()
    call = (await _start_c2s(db_client, journey))["call"]  # nobody was rung
    async with db.sessionmaker() as session:
        advisor = await calls_service.list_ringing_calls_for_user(session, world.advisor.user.id)
        technician = await calls_service.list_ringing_calls_for_user(
            session, world.technician.user.id
        )
    assert [str(ringing.id) for ringing in advisor] == [call["id"]]  # rung or not
    assert technician == []


async def test_call_logs_are_staff_data(  # CALL-10, D21
    desk: Desk, world: World, media: FakeCallMedia, db_client: httpx.AsyncClient
) -> None:
    journey = await desk.book()
    await _start_c2s(db_client, journey)
    advisor = await db_client.get(_staff(world, "/calls"), headers=bearer(world.advisor.user.id))
    assert advisor.status_code == 200
    assert advisor.json()["total"] == 1
    technician = await db_client.get(
        _staff(world, "/calls"), headers=bearer(world.technician.user.id)
    )
    assert technician.status_code == 403
    mine = await db_client.get(
        f"/api/v1/me/bookings/{journey.id}/calls", headers=journey.customer.headers
    )
    assert mine.json()["total"] == 1
    assert "has_summary" not in mine.json()["items"][0]  # staff-only fields

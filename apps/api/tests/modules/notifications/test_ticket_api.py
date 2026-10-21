"""`GET /api/v1/realtime/ticket` (D70, spec 03 §4.12 / §6.1) and the module's OpenAPI surface.

NOT-16 (exactly `sub`, `iat`, `exp = iat + 60`, `typ = "ws"`; refused as a Bearer session; no row
or server state), API-13 (`Cache-Control: no-store` on the ticket's 200 and 401), the operation
ids of spec 03 §4.1, and the WebSocket route kept out of OpenAPI (spec 03 §1.1).
"""

from datetime import timedelta

import httpx
import jwt
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.core.security import JWT_ALGORITHM, SESSION_COOKIE_NAME, issue_token
from app.modules.identity.models import User
from app.modules.notifications.models import Notification
from app.shared.clock import SimulatedClock, utcnow
from tests.assertions import assert_problem
from tests.conftest import TEST_JWT_SECRET
from tests.modules.notifications.support import World

pytestmark = pytest.mark.db

TICKET = "/api/v1/realtime/ticket"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def session_token(user: User) -> str:
    return issue_token(user.id, "session", utcnow())


async def test_not16_the_ticket_is_a_60_second_ws_jwt_with_exactly_four_claims(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    response = await db_client.get(TICKET, headers=bearer(session_token(world.ayesha)))

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"  # API-13
    body = response.json()
    assert list(body) == ["ticket", "expires_in"]
    assert body["expires_in"] == 60
    claims = jwt.decode(
        body["ticket"],
        TEST_JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert set(claims) == {"sub", "iat", "exp", "typ"}
    assert claims["sub"] == str(world.ayesha.id)
    assert claims["typ"] == "ws"
    assert claims["iat"] == int(clock.now().timestamp())  # the app clock (D63)
    assert claims["exp"] == claims["iat"] + 60


async def test_not16_the_session_cookie_also_gets_a_ticket(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    """The browser path: cookie auth through the web origin's rewrite (D7)."""
    db_client.cookies.set(SESSION_COOKIE_NAME, session_token(world.a.owner))
    response = await db_client.get(TICKET)
    assert response.status_code == 200
    claims = jwt.decode(response.json()["ticket"], options={"verify_signature": False})
    assert claims["sub"] == str(world.a.owner.id)


async def test_not16_a_ticket_is_refused_as_a_session(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    ticket = (await db_client.get(TICKET, headers=bearer(session_token(world.ayesha)))).json()[
        "ticket"
    ]

    for path in (TICKET, "/api/v1/me/notifications", "/api/v1/me"):
        response = await db_client.get(path, headers=bearer(ticket))
        assert_problem(response, 401, "UNAUTHENTICATED")


async def test_not16_issuing_a_ticket_creates_no_row_and_no_server_state(
    db_app: FastAPI, db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    for _ in range(3):
        response = await db_client.get(TICKET, headers=bearer(session_token(world.ayesha)))
        assert response.status_code == 200

    async with world.db.sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(Notification)) == 0
    assert getattr(db_app.state, "realtime_hub", None) is None  # the hub is not even created


async def test_the_ticket_needs_a_live_session(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    expired = session_token(world.ayesha)
    clock.advance(timedelta(days=8))  # past JWT_EXPIRES_IN (7d)

    anonymous = await db_client.get(TICKET)
    stale = await db_client.get(TICKET, headers=bearer(expired))
    await world.set_user_active(world.a.advisor, active=False)
    deactivated = await db_client.get(TICKET, headers=bearer(session_token(world.a.advisor)))

    for response in (anonymous, stale, deactivated):
        assert_problem(response, 401, "UNAUTHENTICATED")
        assert response.headers["cache-control"] == "no-store"  # API-13
        assert response.headers["www-authenticate"] == "Bearer"


async def test_openapi_lists_the_five_operations_and_never_the_socket(
    db_client: httpx.AsyncClient,
) -> None:
    spec = (await db_client.get("/openapi.json")).json()
    operations = {
        (method.upper(), path): (operation["operationId"], operation["tags"])
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if "notification" in path or "realtime" in path
    }

    assert operations == {
        ("GET", "/api/v1/me/notifications"): (
            "notifications_list_my_notifications",
            ["notifications"],
        ),
        ("GET", "/api/v1/me/notifications/unread-count"): (
            "notifications_get_unread_count",
            ["notifications"],
        ),
        ("POST", "/api/v1/me/notifications/{notification_id}/read"): (
            "notifications_mark_notification_read",
            ["notifications"],
        ),
        ("POST", "/api/v1/me/notifications/read-all"): (
            "notifications_mark_all_notifications_read",
            ["notifications"],
        ),
        ("GET", "/api/v1/realtime/ticket"): (
            "notifications_get_realtime_ticket",
            ["notifications"],
        ),
    }
    assert not [path for path in spec["paths"] if path.endswith("/ws")]
    schemas = spec["components"]["schemas"]
    assert list(schemas["RealtimeTicketRead"]["properties"]) == ["ticket", "expires_in"]
    assert list(schemas["UnreadCountRead"]["properties"]) == ["count"]
    assert "recipient_user_id" not in schemas["NotificationRead"]["properties"]
    assert schemas["NotificationRead"]["required"] == list(
        schemas["NotificationRead"]["properties"]
    )

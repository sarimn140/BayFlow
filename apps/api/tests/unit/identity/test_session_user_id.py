"""`app.shared.auth.session_user_id`: the lenient credential read behind `auth.logged_out`
(spec 19 §3.3). Logout must answer 204 whatever it receives, so this never raises; the transport
rule of `get_current_user` holds (an `Authorization` header wins over the cookie)."""

import uuid
from datetime import timedelta

from starlette.requests import Request

from app.core.security import SESSION_COOKIE_NAME, issue_token
from app.shared.auth import session_user_id
from app.shared.clock import utcnow


def request(headers: dict[str, str]) -> Request:
    raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw})


def test_a_valid_bearer_or_cookie_names_its_user() -> None:
    user_id = uuid.uuid4()
    token = issue_token(user_id, "session", utcnow())
    assert session_user_id(request({"Authorization": f"Bearer {token}"})) == user_id
    assert session_user_id(request({"Cookie": f"{SESSION_COOKIE_NAME}={token}"})) == user_id


def test_anything_else_names_nobody() -> None:
    user_id = uuid.uuid4()
    good = issue_token(user_id, "session", utcnow())
    expired = issue_token(user_id, "session", utcnow() - timedelta(days=30), lifetime_seconds=60)
    ticket = issue_token(user_id, "ws", utcnow())
    for headers in (
        {},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": f"Basic {good}"},
        {"Authorization": f"Bearer {expired}"},
        {"Authorization": f"Bearer {ticket}"},  # a WebSocket ticket is not a session
        {"Authorization": "Bearer x", "Cookie": f"{SESSION_COOKIE_NAME}={good}"},  # no fallback
        {"Cookie": f"{SESSION_COOKIE_NAME}=garbage"},
    ):
        assert session_user_id(request(headers)) is None, headers

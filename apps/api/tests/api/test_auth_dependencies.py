"""`app.shared.auth`: cookie/Bearer transport, live revocation, tenancy, roles (D8, D9, D20, D80).

Spec 04 SEC-04, SEC-13, SEC-25, SEC-26 at the dependency level; the real login flow and the
routes that use these dependencies arrive with the identity and shops modules.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated
from uuid import UUID

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI

from app.core.database import Database
from app.core.security import SESSION_COOKIE_NAME, issue_token
from app.modules.identity.models import User
from app.shared.auth import (
    CurrentUserDep,
    OptionalUserDep,
    ShopContext,
    ShopContextDep,
    require_roles,
    shop_scoped_router,
)
from app.shared.clock import SimulatedClock, utcnow
from app.shared.enums import MembershipRole
from app.shared.tenancy import shop_scoped_router as tenancy_shop_scoped_router
from tests.rows import add_rows, make_membership, make_shop, make_user, new_id

pytestmark = pytest.mark.db

probe = APIRouter(prefix="/api/v1/_probe", tags=["test"])


@probe.get("/me")
async def probe_me(user: CurrentUserDep) -> dict[str, str]:
    return {"id": str(user.id), "email": user.email}


@probe.get("/maybe")
async def probe_maybe(user: OptionalUserDep) -> dict[str, str | None]:
    return {"id": str(user.id) if user else None}


shop_probe = shop_scoped_router(tags=["test"])


@shop_probe.get("/_probe/context")
async def probe_context(context: ShopContextDep) -> dict[str, str]:
    return {"shop_id": str(context.shop_id), "role": context.role.value}


@shop_probe.get("/_probe/owner-only")
async def probe_owner_only(
    context: Annotated[ShopContext, Depends(require_roles(MembershipRole.OWNER))],
) -> dict[str, str]:
    return {"role": context.role.value}


@dataclass
class Cast:
    owner: User
    advisor: User
    technician: User
    outsider: User
    disabled: User
    shop_a: UUID
    shop_b: UUID


@pytest.fixture
async def cast(db: Database, db_app: FastAPI, clock: SimulatedClock) -> Cast:
    owner, advisor, technician = make_user(), make_user(), make_user()
    outsider, disabled = make_user(), make_user(is_active=False)
    other_owner = make_user()
    shop_a, shop_b = make_shop(), make_shop()
    await add_rows(
        db.sessionmaker,
        owner,
        advisor,
        technician,
        outsider,
        disabled,
        other_owner,
        shop_a,
        shop_b,
        make_membership(shop_a, owner, MembershipRole.OWNER),
        make_membership(shop_a, advisor, MembershipRole.SERVICE_ADVISOR, created_by=owner),
        make_membership(
            shop_a, technician, MembershipRole.TECHNICIAN, created_by=owner, is_active=False
        ),
        make_membership(shop_b, other_owner, MembershipRole.OWNER),
    )
    db_app.include_router(probe)
    db_app.include_router(shop_probe)
    return Cast(owner, advisor, technician, outsider, disabled, shop_a.id, shop_b.id)


def bearer(user: User, typ: str = "session") -> dict[str, str]:
    token = issue_token(user.id, typ, utcnow())  # type: ignore[arg-type]
    return {"Authorization": f"Bearer {token}"}


async def test_bearer_token_authenticates(db_client: httpx.AsyncClient, cast: Cast) -> None:
    response = await db_client.get("/api/v1/_probe/me", headers=bearer(cast.owner))
    assert response.status_code == 200
    assert response.json() == {"id": str(cast.owner.id), "email": cast.owner.email}


async def test_session_cookie_authenticates(db_client: httpx.AsyncClient, cast: Cast) -> None:
    db_client.cookies.set(SESSION_COOKIE_NAME, issue_token(cast.advisor.id, "session", utcnow()))
    response = await db_client.get("/api/v1/_probe/me")
    assert response.status_code == 200
    assert response.json()["id"] == str(cast.advisor.id)


async def test_missing_credentials_are_401_with_challenge(
    db_client: httpx.AsyncClient, cast: Cast
) -> None:
    response = await db_client.get("/api/v1/_probe/me")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "authorization", ["Bearer not-a-jwt", "Basic dXNlcjpwYXNz", "Bearer", "token-without-scheme"]
)
async def test_bad_authorization_headers_are_401(
    db_client: httpx.AsyncClient, cast: Cast, authorization: str
) -> None:
    response = await db_client.get("/api/v1/_probe/me", headers={"Authorization": authorization})
    assert response.status_code == 401


async def test_bearer_wins_and_never_falls_back_to_the_cookie(
    db_client: httpx.AsyncClient, cast: Cast
) -> None:
    db_client.cookies.set(SESSION_COOKIE_NAME, issue_token(cast.owner.id, "session", utcnow()))
    response = await db_client.get(
        "/api/v1/_probe/me", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert response.status_code == 401
    assert "set-cookie" not in response.headers  # the cookie was not the failing credential


async def test_invalid_cookie_is_401_and_cleared(db_client: httpx.AsyncClient, cast: Cast) -> None:
    db_client.cookies.set(SESSION_COOKIE_NAME, "garbage")
    response = await db_client.get("/api/v1/_probe/me")
    assert response.status_code == 401
    cleared = response.headers["set-cookie"]
    assert cleared.startswith(f'{SESSION_COOKIE_NAME}=""')
    assert "Max-Age=0" in cleared
    assert "HttpOnly" in cleared
    assert "Path=/" in cleared
    assert "SameSite=lax" in cleared


async def test_ws_ticket_is_not_a_session(db_client: httpx.AsyncClient, cast: Cast) -> None:
    response = await db_client.get("/api/v1/_probe/me", headers=bearer(cast.owner, "ws"))
    assert response.status_code == 401


async def test_expiry_follows_the_app_clock(
    db_client: httpx.AsyncClient, cast: Cast, clock: SimulatedClock
) -> None:
    headers = bearer(cast.owner)
    clock.advance(timedelta(days=7) - timedelta(seconds=1))
    assert (await db_client.get("/api/v1/_probe/me", headers=headers)).status_code == 200
    clock.advance(timedelta(seconds=1))
    assert (await db_client.get("/api/v1/_probe/me", headers=headers)).status_code == 401


async def test_deactivated_or_deleted_users_are_401(
    db_client: httpx.AsyncClient, cast: Cast
) -> None:
    assert (
        await db_client.get("/api/v1/_probe/me", headers=bearer(cast.disabled))
    ).status_code == 401
    ghost = make_user()  # never inserted
    assert (await db_client.get("/api/v1/_probe/me", headers=bearer(ghost))).status_code == 401


async def test_optional_user_is_none_only_without_credentials(
    db_client: httpx.AsyncClient, cast: Cast
) -> None:
    anonymous = await db_client.get("/api/v1/_probe/maybe")
    assert anonymous.json() == {"id": None}
    known = await db_client.get("/api/v1/_probe/maybe", headers=bearer(cast.owner))
    assert known.json() == {"id": str(cast.owner.id)}
    bad = await db_client.get("/api/v1/_probe/maybe", headers={"Authorization": "Bearer x"})
    assert bad.status_code == 401  # never a silent downgrade to anonymous (spec 04 case A)


async def test_active_member_gets_the_shop_context(
    db_client: httpx.AsyncClient, cast: Cast
) -> None:
    response = await db_client.get(
        f"/api/v1/shops/{cast.shop_a}/_probe/context", headers=bearer(cast.advisor)
    )
    assert response.status_code == 200
    assert response.json() == {"shop_id": str(cast.shop_a), "role": "SERVICE_ADVISOR"}


@pytest.mark.parametrize(
    ("who", "shop"),
    [
        ("advisor", "shop_b"),  # another tenant's shop
        ("outsider", "shop_a"),  # a customer with no membership
        ("technician", "shop_a"),  # an inactive membership (D9)
        ("owner", "unknown"),  # a shop that does not exist
    ],
)
async def test_everything_outside_an_active_membership_is_404(
    db_client: httpx.AsyncClient, cast: Cast, who: str, shop: str
) -> None:
    shop_id = new_id() if shop == "unknown" else getattr(cast, shop)
    response = await db_client.get(
        f"/api/v1/shops/{shop_id}/_probe/context", headers=bearer(getattr(cast, who))
    )
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert response.json()["detail"] == "The requested resource was not found."


async def test_unauthenticated_beats_membership(db_client: httpx.AsyncClient, cast: Cast) -> None:
    response = await db_client.get(f"/api/v1/shops/{cast.shop_a}/_probe/context")
    assert response.status_code == 401


async def test_require_roles_is_403_for_a_visible_shop(
    db_client: httpx.AsyncClient, cast: Cast
) -> None:
    url = f"/api/v1/shops/{cast.shop_a}/_probe/owner-only"
    denied = await db_client.get(url, headers=bearer(cast.advisor))
    assert denied.status_code == 403
    assert denied.json()["code"] == "FORBIDDEN"
    allowed = await db_client.get(url, headers=bearer(cast.owner))
    assert allowed.json() == {"role": "OWNER"}


async def test_shop_scoped_router_is_also_exported_by_tenancy() -> None:
    assert tenancy_shop_scoped_router is shop_scoped_router
    router = shop_scoped_router(tags=["x"])
    assert router.prefix == "/api/v1/shops/{shop_id}"
    assert len(router.dependencies) == 1


async def test_session_cookie_helpers_use_the_d8_attributes() -> None:
    from starlette.responses import Response  # noqa: PLC0415

    from app.shared.auth import delete_session_cookie, set_session_cookie  # noqa: PLC0415

    response = Response()
    set_session_cookie(response, "token-value")
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=token-value;")
    assert "HttpOnly" in cookie
    assert "Max-Age=604800" in cookie
    assert "Path=/" in cookie
    assert "SameSite=lax" in cookie
    assert "Domain" not in cookie
    assert "Secure" not in cookie  # COOKIE_SECURE=false in tests

    cleared = Response()
    delete_session_cookie(cleared)
    assert "Max-Age=0" in cleared.headers["set-cookie"]


async def test_a_malformed_shop_id_is_one_field_error_on_role_gated_routes(
    db_client: httpx.AsyncClient, cast: Cast
) -> None:
    """`require_roles` re-resolves `require_shop_member`; the 422 must still list the error once."""
    response = await db_client.get(
        "/api/v1/shops/not-a-uuid/_probe/owner-only", headers=bearer(cast.owner)
    )
    assert response.status_code == 422
    assert [error["field"] for error in response.json()["errors"]] == ["path.shop_id"]

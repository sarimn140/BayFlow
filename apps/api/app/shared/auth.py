"""Authentication and tenant dependencies (D8, D9, D20, D21, D80; spec 04 "Per-request checks").

Per staff request: authenticate (`get_current_user`, 401) -> tenant (`require_shop_member`, 404 for
any shop where the caller has no *active* membership) -> suspension (403 `SHOP_SUSPENDED` for every
member of a suspended shop, the Owner included, D96) -> role (`require_roles`, 403). Booking
actions do not use `require_roles`: the state machine checks role, assignment and status.

Platform admin routes (`/api/v1/admin/*`, D94) use `refuse_cross_site_requests` (D98: 403
`FORBIDDEN` when a browser says the request comes from another site) and then
`require_platform_admin`: 401 when not logged in, 403 `FORBIDDEN` unless the re-read user carries
`is_platform_admin` (spec 19 §4).

Token transport (spec 04 "Cookie or Bearer"): an `Authorization` header always wins and never falls
back to the cookie; a malformed or non-Bearer header is 401. A failed cookie session answers 401
and clears the stale `bf_session` cookie. The user and the membership are re-read from the
database on every request, so deactivation takes effect immediately (D9).

This is one of the two documented `app.shared -> app.modules` edges (spec 01 rule 8): it reads
`identity.service` and `shops.service` (`get_active_user`, `get_active_membership` and the read
port `get_shop_suspension`, spec 19 §6), which never import this module.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.config import get_settings
from app.core.database import DbSession
from app.core.error_handlers import problem_responses
from app.core.errors import Forbidden, NotFound, ShopSuspended, Unauthenticated
from app.core.logging import bind_log_context
from app.core.security import SESSION_COOKIE_NAME, decode_token
from app.modules.identity import service as identity_service
from app.modules.shops import service as shops_service
from app.shared.clock import utcnow
from app.shared.enums import MembershipRole

SHOP_ROUTE_PREFIX = "/api/v1/shops/{shop_id}"

# Documents "Authorize: Bearer <access_token>" in Swagger; the cookie is read from the request.
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerToken",
    description="The `access_token` returned by `POST /api/v1/auth/login`.",
)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


PLATFORM_ADMIN_ONLY = "This area is for BayFlow platform admins."
CROSS_SITE_REFUSED = "Admin requests must come from the BayFlow app."
SAME_SITE_FETCH_VALUES = frozenset({"same-origin", "none"})
"""`Sec-Fetch-Site` values the admin API accepts (D98): our own pages, or a user typing the URL."""


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """The authenticated, active caller. `is_platform_admin` is re-read with the user on every
    request (D9, D94), so a revoked admin loses the console at their next request."""

    id: UUID
    email: str
    full_name: str
    is_platform_admin: bool = False


@dataclass(frozen=True, slots=True)
class ShopContext:
    """The caller's active membership in the shop of the path (D20)."""

    shop_id: UUID
    user: CurrentUser
    membership_id: UUID
    role: MembershipRole


def set_session_cookie(response: Response, token: str) -> None:
    """Set `bf_session` exactly as D8 / spec 04 fix it: HttpOnly, SameSite=Lax, Path=/, host-only,
    `Secure` when `COOKIE_SECURE=true`, `Max-Age` = the token lifetime (`JWT_EXPIRES_IN`)."""
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=settings.jwt_lifetime_seconds,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def delete_session_cookie(response: Response) -> None:
    """Expire `bf_session` (logout, or a request whose cookie was invalid)."""
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=get_settings().cookie_secure,
        httponly=True,
        samesite="lax",
    )


def session_cookie_clearing_headers() -> dict[str, str]:
    """A `Set-Cookie` header that deletes `bf_session` (for error responses)."""
    response = Response()
    delete_session_cookie(response)
    return {"set-cookie": response.headers["set-cookie"]}


async def _load_user(session: AsyncSession, token: str, *, from_cookie: bool) -> CurrentUser:
    failure_headers = session_cookie_clearing_headers() if from_cookie else None
    try:
        user_id = decode_token(token, utcnow(), "session")
    except Unauthenticated:
        raise Unauthenticated(headers=failure_headers) from None
    user = await identity_service.get_active_user(session, user_id)
    if user is None:  # deleted or deactivated user: 401 everywhere (D9)
        raise Unauthenticated(headers=failure_headers)
    bind_log_context(user_id=user.id)
    return CurrentUser(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_platform_admin=user.is_platform_admin,
    )


async def _authenticate(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    session: AsyncSession,
) -> CurrentUser | None:
    """None when the request carries no credentials at all; 401 when they are present but bad."""
    if request.headers.get("authorization") is not None:
        if credentials is None:  # another scheme, or a malformed header
            raise Unauthenticated
        return await _load_user(session, credentials.credentials, from_cookie=False)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    return await _load_user(session, token, from_cookie=True)


async def get_current_user(
    request: Request, credentials: BearerCredentials, session: DbSession
) -> CurrentUser:
    """The authenticated, active user (cookie `bf_session` or Bearer token); else 401."""
    user = await _authenticate(request, credentials, session)
    if user is None:
        raise Unauthenticated
    return user


async def get_optional_user(
    request: Request, credentials: BearerCredentials, session: DbSession
) -> CurrentUser | None:
    """For the booking wizard: None only when no credentials are sent; bad ones are 401 (D32)."""
    return await _authenticate(request, credentials, session)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
OptionalUserDep = Annotated[CurrentUser | None, Depends(get_optional_user)]


async def require_platform_admin(user: CurrentUserDep) -> CurrentUser:
    """A platform admin (D94, spec 19 §4): 401 when not logged in (from `get_current_user`), 403
    `FORBIDDEN` for any other user, shop Owners included (it is not a shop role)."""
    if not user.is_platform_admin:
        raise Forbidden(PLATFORM_ADMIN_ONLY)
    return user


PlatformAdminDep = Annotated[CurrentUser, Depends(require_platform_admin)]


async def refuse_cross_site_requests(request: Request) -> None:
    """Fetch Metadata guard of the admin API (D98; spec 04 threat 8, spec 19 §4).

    `SameSite=Lax` still sends `bf_session` on a cross-site top-level GET, and E-67, E-73 and E-75
    write an audit row on GET, so a link on another site could make a signed-in admin's browser
    write one. A request whose `Sec-Fetch-Site` header is present and not `same-origin` or `none`
    is refused with 403 `FORBIDDEN` before anything else runs. The web calls the API same-origin
    through the Vercel rewrite (D7); without the header (curl, Swagger, tests, server-to-server)
    the request passes.
    """
    site = request.headers.get("sec-fetch-site")
    if site is not None and site.strip().lower() not in SAME_SITE_FETCH_VALUES:
        raise Forbidden(CROSS_SITE_REFUSED)


def session_user_id(request: Request) -> UUID | None:
    """The user a request's session credentials name, or None; it never raises.

    For `POST /api/v1/auth/logout`, which must answer 204 whatever it receives but records
    `auth.logged_out` when the cookie or Bearer token names a user (spec 19 §3.3). The transport
    rule of `get_current_user` holds: an `Authorization` header wins and never falls back to the
    cookie. Only the token is checked here; the identity service re-reads the user.
    """
    authorization = request.headers.get("authorization")
    if authorization is not None:
        scheme, _, token = authorization.strip().partition(" ")
        if scheme.lower() != "bearer":
            return None
        token = token.strip()
    else:
        token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not token:
        return None
    try:
        return decode_token(token, utcnow(), "session")
    except Unauthenticated:
        return None


async def require_shop_member(
    shop_id: Annotated[UUID, Path(description="The shop (tenant) id.")],
    user: CurrentUserDep,
    session: DbSession,
) -> ShopContext:
    """The caller's active membership in `shop_id`, else 404 (never 403: other shops are invisible).

    Unknown shop, another tenant's shop, an inactive membership and a customer without membership
    all give the same 404 (spec 04 "Why 404 and not 403"). A member of a suspended shop — the Owner
    included — then gets 403 `SHOP_SUSPENDED` before any role check (D96, spec 19 §2); non-members
    still get the 404, so a suspension is visible only to the shop's own team.
    """
    membership = await shops_service.get_active_membership(
        session, shop_id=shop_id, user_id=user.id
    )
    if membership is None:
        raise NotFound
    if await shops_service.get_shop_suspension(session, shop_id=shop_id) is not None:
        raise ShopSuspended
    bind_log_context(shop_id=shop_id)
    return ShopContext(
        shop_id=shop_id, user=user, membership_id=membership.id, role=membership.role
    )


ShopContextDep = Annotated[ShopContext, Depends(require_shop_member)]


def require_roles(*roles: MembershipRole) -> Callable[[ShopContext], Awaitable[ShopContext]]:
    """A dependency that admits only the given membership roles (403 `FORBIDDEN` otherwise)."""
    allowed = frozenset(roles)

    async def check_role(context: ShopContextDep) -> ShopContext:
        if context.role not in allowed:
            raise Forbidden  # the shop is visible to the caller; the role is wrong
        return context

    return check_role


def shop_scoped_router(*, tags: Sequence[str | Enum] | None = None) -> APIRouter:
    """An `APIRouter` for `/api/v1/shops/{shop_id}/...` with `require_shop_member` attached at
    router level (D20, D80), so no shop route can forget the tenant check. Endpoints that need
    the context declare `ShopContextDep` too; FastAPI runs the dependency once per request.

    Every such route documents 403: `require_shop_member` answers `SHOP_SUSPENDED` to the
    members of a suspended shop (D96), whatever the route's own role rules."""
    return APIRouter(
        prefix=SHOP_ROUTE_PREFIX,
        tags=list(tags) if tags is not None else None,
        dependencies=[Depends(require_shop_member)],
        responses=problem_responses(403),
    )

"""HTTP routes of the identity module: `/api/v1/auth/*` (D81, spec 03 §4.3).

All three routes are public (spec 03 §1.2). Login and owner registration answer with the token
fields and the `user` (no memberships) and set the `bf_session` cookie; the web then calls
`GET /api/v1/me` (served by the shops module). Per-IP ceilings are slowapi decorators (route
decorator above the limiter decorator; the endpoint takes `request`); the per-account failure
limiter, the primary control, lives in the service (D69). Logout never requires or rejects
credentials, but when its cookie or Bearer token names a user it records `auth.logged_out` for
the platform audit log (spec 19 §3.3). Recording is best effort: whatever fails there, logout
still answers 204 and expires the cookie.
"""

import logging

from fastapi import APIRouter, Request, Response, status

from app.core.error_handlers import problem_responses
from app.core.security import (
    LOGIN_IP_LIMIT,
    LOGOUT_IP_LIMIT,
    REGISTER_OWNER_IP_LIMIT,
    limiter,
)
from app.modules.identity import service
from app.modules.identity.schemas import OwnerRegistrationCreate, SessionCreate, SessionRead
from app.shared.auth import delete_session_cookie, session_user_id, set_session_cookie
from app.shared.uow import UnitOfWork, UowDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["identity"])


@router.post(
    "/register-owner",
    status_code=status.HTTP_201_CREATED,
    summary="Register an owner account",
    description=(
        "Creates a user with no membership (D17) and logs it in: the token is returned in the "
        "body and set as the `bf_session` cookie. Create a shop next with `POST /api/v1/shops`."
    ),
    responses=problem_responses(409, 422, 429),
)
@limiter.limit(REGISTER_OWNER_IP_LIMIT)
async def register_owner(
    request: Request,
    response: Response,
    body: OwnerRegistrationCreate,
    uow: UowDep,
) -> SessionRead:
    session = await service.register_owner(
        uow,
        email=body.email,
        full_name=body.full_name,
        password=body.password,
        phone=body.phone,
    )
    set_session_cookie(response, session.access_token)
    return session


@router.post(
    "/login",
    summary="Log in",
    description=(
        "Returns the session token and the user (no memberships, D81) and sets the `bf_session` "
        "cookie. Call `GET /api/v1/me` next for memberships and capabilities. Five failed "
        "password checks per e-mail within 15 minutes block the account for the rest of the "
        "window (429), even with the right password (D69)."
    ),
    responses=problem_responses(401, 422, 429),
)
@limiter.limit(LOGIN_IP_LIMIT)
async def login(
    request: Request,
    response: Response,
    body: SessionCreate,
    uow: UowDep,
) -> SessionRead:
    session = await service.login(uow, email=body.email, password=body.password)
    set_session_cookie(response, session.access_token)
    return session


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Log out",
    description=(
        "Expires the `bf_session` cookie. Idempotent and needs no authentication. The JWT is "
        "stateless, so a copied Bearer token stays valid until it expires (spec 04). When the "
        "cookie or Bearer token names an active user, the sign-out is recorded in the platform "
        "audit log (spec 19); a failure there never changes the 204."
    ),
    responses=problem_responses(429),
)
@limiter.limit(LOGOUT_IP_LIMIT)
async def logout(request: Request, uow: UowDep) -> Response:
    try:
        await service.logout(uow, user_id=session_user_id(request))
    except Exception as exc:  # recording the sign-out is best effort (spec 19 §3.3)
        # Only the exception's type is logged: its text may quote SQL parameters.
        logger.warning("auth.logout_not_recorded", extra={"error": type(exc).__name__})
        await _discard(uow)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    delete_session_cookie(response)
    return response


async def _discard(uow: UnitOfWork) -> None:
    """Roll the failed recording back; a connection that is already gone is closed with the
    session by the request's dependency."""
    try:
        await uow.rollback()
    except Exception as exc:  # the 204 must not depend on the database
        logger.warning("auth.logout_rollback_failed", extra={"error": type(exc).__name__})


routers = (router,)

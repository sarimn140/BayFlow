"""HTTP and WebSocket routes of the notifications module (spec 03 §4.12, §6; tag `notifications`).

Not shop-scoped (D80 applies to `/shops/{shop_id}` routes only): every bell route serves the
caller's own rows (`recipient_user_id = me`), so another user's notification id is a 404 (SEC-34).

- `me_router` (`/api/v1/me/notifications`): list, unread count, mark one read, mark all read (P0);
- `realtime_router` (`/api/v1`): the WebSocket ticket (D70) and `WS /api/v1/ws` (P1, D88). FastAPI
  never documents WebSocket routes, so the socket is absent from OpenAPI.

Every response is `Cache-Control: no-store` (D61, the request-context middleware).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, WebSocket, status

from app.core.database import DbSession
from app.core.error_handlers import problem_responses
from app.modules.notifications import service
from app.modules.notifications.realtime import serve_websocket
from app.modules.notifications.schemas import NotificationRead, RealtimeTicketRead, UnreadCountRead
from app.shared.auth import CurrentUserDep
from app.shared.pagination import Page, PageParamsDep
from app.shared.uow import UowDep

me_router = APIRouter(prefix="/api/v1/me/notifications", tags=["notifications"])
realtime_router = APIRouter(prefix="/api/v1", tags=["notifications"])

NotificationId = Annotated[uuid.UUID, Path(description="The notification id.")]


@me_router.get(
    "",
    summary="List my notifications",
    description=(
        "The caller's notifications across all shops and roles, newest first, paginated. "
        "`unread_only=true` keeps the unread ones. Each item carries the server-computed `link` "
        "to open for its `recipient_role` (D67)."
    ),
    responses=problem_responses(401, 422),
)
async def list_my_notifications(
    user: CurrentUserDep,
    session: DbSession,
    page: PageParamsDep,
    unread_only: Annotated[
        bool, Query(description="Only notifications that are still unread.")
    ] = False,
) -> Page[NotificationRead]:
    return await service.list_for_user(session, user_id=user.id, unread_only=unread_only, page=page)


@me_router.get(
    "/unread-count",
    summary="Count my unread notifications",
    description="The bell badge, polled every 15 s on every logged-in page (D14).",
    responses=problem_responses(401),
)
async def get_unread_count(user: CurrentUserDep, session: DbSession) -> UnreadCountRead:
    return UnreadCountRead(count=await service.count_unread(session, user_id=user.id))


@me_router.post(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Mark all my notifications read",
    description="Marks every unread notification of the caller read. Idempotent.",
    responses=problem_responses(401),
)
async def mark_all_notifications_read(user: CurrentUserDep, uow: UowDep) -> Response:
    await service.mark_all_read(uow, user_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@me_router.post(
    "/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Mark one of my notifications read",
    description=(
        "Idempotent: a notification that is already read keeps its `read_at`. An unknown id and "
        "another user's notification both answer 404."
    ),
    responses=problem_responses(401, 404, 422),
)
async def mark_notification_read(
    notification_id: NotificationId, user: CurrentUserDep, uow: UowDep
) -> Response:
    await service.mark_read(uow, user_id=user.id, notification_id=notification_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@realtime_router.get(
    "/realtime/ticket",
    summary="Get a WebSocket ticket",
    description=(
        "A 60-second JWT with `typ` = `ws`, good only for opening "
        "`wss://<api-host>/api/v1/ws?ticket=…` (D70); fetch a new one for every connect attempt. "
        "It is refused as a session token. A 401 here means the session has expired."
    ),
    responses=problem_responses(401),
)
async def get_realtime_ticket(user: CurrentUserDep) -> RealtimeTicketRead:
    return service.issue_ws_ticket(user.id)


@realtime_router.websocket("/ws")
async def realtime_socket(websocket: WebSocket) -> None:
    """`WS /api/v1/ws?ticket=…` (spec 03 §6): server → client pushes, client → server `ping`."""
    await serve_websocket(websocket)


routers = (me_router, realtime_router)

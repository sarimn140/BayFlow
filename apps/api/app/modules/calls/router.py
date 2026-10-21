"""HTTP routes of the calls module (spec 05 §8, spec 03 §4.14, `modules/calls.md` "Endpoints").

- `me_router`: the booking's customer — start a call to the shop, the booking's call log, and
  accept / decline / end.
- `shop_router` (`shop_scoped_router`, D80): SA and Owner — call the customer, call logs, call
  detail with the AI summary, accept / decline / end, tasks and mark-done.
- `webhook_router`: LiveKit's signed webhook (not in OpenAPI; 404 while calling is disabled).

The agent's routes live in `internal_router.py`. Every route is always mounted, so the OpenAPI
document never depends on environment variables (CALL-20); disabled features answer 503/404.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status

from app.core.database import DbSession
from app.core.error_handlers import problem_responses
from app.core.errors import NotFound, Unauthenticated
from app.modules.calls import service
from app.modules.calls.internal_router import internal_router
from app.modules.calls.providers.base import WebhookRejectedError
from app.modules.calls.schemas import (
    CallDetailRead,
    CallRead,
    CallStartRead,
    TaskMarkDone,
    TaskRead,
)
from app.shared.auth import CurrentUserDep, ShopContextDep, shop_scoped_router
from app.shared.enums import CallDirection, CallStatus, TaskKind, TaskStatus
from app.shared.pagination import Page, PageParams, get_page_params
from app.shared.uow import UowDep

TAG = "calls"
me_router = APIRouter(prefix="/api/v1/me", tags=[TAG])
shop_router = shop_scoped_router(tags=[TAG])
webhook_router = APIRouter(prefix="/api/v1/webhooks", include_in_schema=False)

BookingId = Annotated[uuid.UUID, Path(description="The booking id.")]
CallId = Annotated[uuid.UUID, Path(description="The call id.")]
PageDep = Annotated[PageParams, Depends(get_page_params)]
START_DESCRIPTION = (
    "Creates a LiveKit room, rings the callees with an open socket and returns the caller's "
    "join token (2-minute TTL, `Cache-Control: no-store`). 503 `CALLING_DISABLED` when calling is "
    "not configured or the monthly cap is reached; 429 after 5 starts in 10 minutes; 409 "
    "`CALL_BUSY` when the booking, the caller or the customer is already in a call."
)


# --- Customer family (spec 05 §8.1) ---------------------------------------------------------------


@me_router.post(
    "/bookings/{booking_id}/calls",
    status_code=status.HTTP_201_CREATED,
    summary="Call the shop about my booking",
    description=START_DESCRIPTION,
    responses=problem_responses(401, 404, 409, 422, 429, 503),
)
async def start_my_call(booking_id: BookingId, user: CurrentUserDep, uow: UowDep) -> CallStartRead:
    return await service.start_customer_call(uow, user, booking_id)


@me_router.get(
    "/bookings/{booking_id}/calls",
    summary="The call log of my booking",
    responses=problem_responses(401, 404, 422),
)
async def list_my_booking_calls(
    booking_id: BookingId, user: CurrentUserDep, session: DbSession, page: PageDep
) -> Page[CallRead]:
    return await service.list_my_booking_calls(session, user, booking_id, page)


@me_router.post(
    "/calls/{call_id}/accept",
    summary="Accept the shop's call",
    responses=problem_responses(401, 403, 404, 409, 422, 503),
)
async def accept_my_call(call_id: CallId, user: CurrentUserDep, uow: UowDep) -> CallStartRead:
    return await service.answer_call(uow, service.CallActor.customer(user), call_id)


@me_router.post(
    "/calls/{call_id}/decline",
    summary="Decline the shop's call",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def decline_my_call(call_id: CallId, user: CurrentUserDep, uow: UowDep) -> CallRead:
    return await service.decline_call(uow, service.CallActor.customer(user), call_id)


@me_router.post(
    "/calls/{call_id}/end",
    summary="Hang up (idempotent)",
    responses=problem_responses(401, 403, 404, 422),
)
async def end_my_call(call_id: CallId, user: CurrentUserDep, uow: UowDep) -> CallRead:
    return await service.end_call(uow, service.CallActor.customer(user), call_id)


# --- Staff family (spec 05 §8.2) ------------------------------------------------------------------


@shop_router.post(
    "/bookings/{booking_id}/calls",
    status_code=status.HTTP_201_CREATED,
    summary="Call the booking's customer",
    description=START_DESCRIPTION,
    responses=problem_responses(401, 403, 404, 409, 422, 429, 503),
)
async def start_call(booking_id: BookingId, ctx: ShopContextDep, uow: UowDep) -> CallStartRead:
    return await service.start_staff_call(uow, ctx, booking_id)


@shop_router.get(
    "/bookings/{booking_id}/calls",
    summary="The call log of a booking",
    responses=problem_responses(401, 403, 404, 422),
)
async def list_booking_calls(
    booking_id: BookingId, ctx: ShopContextDep, session: DbSession, page: PageDep
) -> Page[CallRead]:
    return await service.list_booking_calls(session, ctx, booking_id, page)


@shop_router.get(
    "/calls",
    summary="The shop's call log",
    description="SA and Owner only (D21). Newest first.",
    responses=problem_responses(401, 403, 404, 422),
)
async def list_shop_calls(  # noqa: PLR0913, PLR0917 - the spec'd filters
    ctx: ShopContextDep,
    session: DbSession,
    page: PageDep,
    status: Annotated[CallStatus | None, Query()] = None,
    direction: Annotated[CallDirection | None, Query()] = None,
    ai_handled: Annotated[bool | None, Query()] = None,
    booking_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[CallRead]:
    return await service.list_shop_calls(
        session,
        ctx,
        status=status,
        direction=direction,
        ai_handled=ai_handled,
        booking_id=booking_id,
        page=page,
    )


@shop_router.get(
    "/calls/{call_id}",
    summary="A call with its AI summary, transcript and tasks",
    responses=problem_responses(401, 404, 422),
)
async def get_call(call_id: CallId, ctx: ShopContextDep, session: DbSession) -> CallDetailRead:
    return await service.get_call_detail(session, ctx, call_id)


@shop_router.post(
    "/calls/{call_id}/accept",
    summary="Accept a customer's call (first accept wins)",
    responses=problem_responses(401, 403, 404, 409, 422, 503),
)
async def accept_call(call_id: CallId, ctx: ShopContextDep, uow: UowDep) -> CallStartRead:
    return await service.answer_call(uow, service.CallActor.staff(ctx), call_id)


@shop_router.post(
    "/calls/{call_id}/decline",
    summary="Decline a customer's call",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def decline_call(call_id: CallId, ctx: ShopContextDep, uow: UowDep) -> CallRead:
    return await service.decline_call(uow, service.CallActor.staff(ctx), call_id)


@shop_router.post(
    "/calls/{call_id}/end",
    summary="Hang up (idempotent)",
    responses=problem_responses(401, 403, 404, 422),
)
async def end_call(call_id: CallId, ctx: ShopContextDep, uow: UowDep) -> CallRead:
    return await service.end_call(uow, service.CallActor.staff(ctx), call_id)


@shop_router.get(
    "/tasks",
    summary="AI Front Desk tasks",
    description="Open tasks by default; urgent first, then newest (spec 05 §6.5).",
    responses=problem_responses(401, 403, 404, 422),
)
async def list_tasks(
    ctx: ShopContextDep,
    session: DbSession,
    page: PageDep,
    status: Annotated[TaskStatus, Query()] = TaskStatus.OPEN,
    kind: Annotated[list[TaskKind] | None, Query()] = None,
) -> Page[TaskRead]:
    return await service.list_tasks(session, ctx, status=status, kinds=kind or [], page=page)


@shop_router.post(
    "/tasks/{task_id}/mark-done",
    summary="Mark a task as done (idempotent)",
    responses=problem_responses(401, 404, 422),
)
async def mark_task_done(
    task_id: Annotated[uuid.UUID, Path()], body: TaskMarkDone, ctx: ShopContextDep, uow: UowDep
) -> TaskRead:
    return await service.mark_task_done(uow, ctx, task_id, body.note)


# --- LiveKit webhook (spec 05 §8.5) ---------------------------------------------------------------


@webhook_router.post("/livekit")
async def livekit_webhook(request: Request) -> Response:
    state = request.app.state
    media = service.get_call_media(state)
    if media is None:
        raise NotFound
    body = (await request.body()).decode()
    try:
        event = media.verify_webhook(body, request.headers.get("Authorization", ""))
    except WebhookRejectedError as exc:
        raise Unauthenticated("Invalid webhook signature.") from exc
    await service.on_media_event(state, event)
    return Response(status_code=status.HTTP_200_OK)


routers: tuple[APIRouter, ...] = (me_router, shop_router, webhook_router, internal_router)

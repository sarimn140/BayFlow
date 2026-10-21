"""The AI Front Desk agent's routes: `/api/v1/internal/calls/{call_id}/…` (spec 05 §5.1, §5.3).

Not in OpenAPI. Every request passes, in order: the service token (`Authorization: Bearer
<AGENT_SERVICE_TOKEN>`, constant-time; 401; the routes answer 404 while the variable is blank, as
if not mounted) → the per-call token (`X-Agent-Call-Token`, compared with its stored SHA-256;
404) → an AI call (404) → the time window (409) → the identity gate where it applies (403). The
scope (shop, customer) is always read from the call row; ids in request bodies are ignored.
"""

import hmac
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status

from app.core.database import DbSession
from app.core.errors import NotFound, Unauthenticated
from app.modules.calls import service
from app.modules.calls.models import CallLog
from app.modules.calls.schemas import (
    AgentBookingList,
    AgentBookingRead,
    AgentEndRequest,
    AgentEstimateRead,
    AgentShopRead,
    AgentSlotsRead,
    AgentTaskCreate,
    AgentTaskRead,
    SessionStartRead,
    SummaryPost,
    SummaryStored,
    VerifyCallerRead,
    VerifyCallerRequest,
)
from app.shared.uow import UowDep

internal_router = APIRouter(prefix="/api/v1/internal/calls/{call_id}", include_in_schema=False)

CallId = Annotated[uuid.UUID, Path()]


def _check_service_token(request: Request, authorization: str | None) -> None:
    secret = request.app.state.settings.agent_service_token
    if secret is None:
        raise NotFound  # the internal routes are off: behave as if not mounted
    expected = f"Bearer {secret.get_secret_value()}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise Unauthenticated


async def agent_call(
    request: Request,
    call_id: CallId,
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    x_agent_call_token: Annotated[str | None, Header()] = None,
) -> CallLog:
    """§5.1's first three checks; returns the call (unlocked)."""
    _check_service_token(request, authorization)
    if not x_agent_call_token:
        raise NotFound
    return await service.find_agent_call(session, call_id, x_agent_call_token)


AgentCall = Annotated[CallLog, Depends(agent_call)]


async def open_leg_call(call: AgentCall) -> CallLog:
    service.require_open_leg(call)
    return call


OpenLegCall = Annotated[CallLog, Depends(open_leg_call)]


@internal_router.post("/session")
async def start_session(call: AgentCall, uow: UowDep) -> SessionStartRead:
    return await service.start_ai_session(uow, call.id)


@internal_router.post("/verify-caller")
async def verify_caller(
    call: OpenLegCall, body: VerifyCallerRequest, uow: UowDep
) -> VerifyCallerRead:
    return await service.verify_caller(uow, call.id, body)


@internal_router.get("/shop")
async def get_shop(call: OpenLegCall, session: DbSession) -> AgentShopRead:
    return await service.get_agent_shop(session, call)


@internal_router.get("/bookings")
async def list_bookings(call: OpenLegCall, session: DbSession) -> AgentBookingList:
    return await service.list_agent_bookings(session, call)


@internal_router.get("/bookings/{reference}")
async def get_booking(
    call: OpenLegCall, reference: Annotated[str, Path(max_length=20)], session: DbSession
) -> AgentBookingRead:
    return await service.get_agent_booking(session, call, reference)


@internal_router.get("/bookings/{reference}/estimate")
async def get_estimate(
    call: OpenLegCall, reference: Annotated[str, Path(max_length=20)], session: DbSession
) -> AgentEstimateRead:
    return await service.get_agent_estimate(session, call, reference)


@internal_router.get("/available-slots")
async def available_slots(
    call: OpenLegCall,
    session: DbSession,
    date_from: Annotated[date, Query(alias="date")],
    days: Annotated[int, Query(ge=1, le=7)] = 1,
) -> AgentSlotsRead:
    return await service.list_agent_slots(session, call, date_from=date_from, days=days)


@internal_router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(
    call: OpenLegCall, body: AgentTaskCreate, uow: UowDep, response: Response
) -> AgentTaskRead:
    created = await service.create_agent_task(uow, call.id, body)
    if not created.created:
        response.status_code = status.HTTP_200_OK
    return created


@internal_router.post("/end")
async def end(call: AgentCall, body: AgentEndRequest, uow: UowDep) -> Response:
    await service.end_ai_leg(uow, call.id, body.error)
    return Response(status_code=status.HTTP_200_OK)


@internal_router.post("/summary", status_code=status.HTTP_201_CREATED)
async def post_summary(
    call: AgentCall, body: SummaryPost, uow: UowDep, response: Response
) -> SummaryStored:
    stored, created = await service.record_ai_summary(uow, call.id, body)
    if not created:
        response.status_code = status.HTTP_200_OK
    return stored

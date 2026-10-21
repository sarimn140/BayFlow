"""HTTP routes of the ai module (modules/ai.md "Endpoints", D103): drafts and usage.

Feature endpoints (e.g. "explain this estimate") live in the feature's own module and call
`service.run_feature`. `shop_scoped_router()` attaches `require_shop_member` (D20, D80).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.database import DbSession
from app.core.error_handlers import problem_responses
from app.modules.ai import service
from app.modules.ai.schemas import AiDraftAccept, AiDraftRead, AiDraftReject, AiUsageRead
from app.shared.auth import ShopContext, ShopContextDep, require_roles, shop_scoped_router
from app.shared.enums import AiDraftStatus, MembershipRole
from app.shared.pagination import Page, PageParams, get_page_params
from app.shared.uow import UowDep

router = shop_scoped_router(tags=["ai"])

UsageViewer = Annotated[
    ShopContext,
    Depends(require_roles(MembershipRole.OWNER, MembershipRole.SERVICE_ADVISOR)),
]
PageDep = Annotated[PageParams, Depends(get_page_params)]


@router.get(
    "/ai/usage",
    summary="AI usage against the shop's caps",
    responses=problem_responses(401, 403, 404, 422),
)
async def get_usage(request: Request, ctx: UsageViewer, session: DbSession) -> AiUsageRead:
    return await service.get_usage(session, ctx, request.app.state.settings)


@router.get(
    "/ai/drafts",
    summary="AI drafts the caller may decide",
    description=(
        "Newest first. Only drafts of features the caller's role may decide (a Technician sees "
        "only the drafts they requested). `status` filters, e.g. `PENDING`."
    ),
    responses=problem_responses(401, 403, 404, 422),
)
async def list_drafts(
    ctx: ShopContextDep,
    session: DbSession,
    page: PageDep,
    status: Annotated[AiDraftStatus | None, Query()] = None,
) -> Page[AiDraftRead]:
    return await service.list_drafts(session, ctx, status=status, page=page)


@router.get(
    "/ai/drafts/{draft_id}",
    summary="One AI draft",
    responses=problem_responses(401, 403, 404, 422),
)
async def get_draft(draft_id: uuid.UUID, ctx: ShopContextDep, session: DbSession) -> AiDraftRead:
    return await service.get_draft(session, ctx, draft_id)


@router.post(
    "/ai/drafts/{draft_id}/accept",
    summary="Accept an AI draft, as is or edited",
    description=(
        "Records who accepted the draft and when (AI-41, AI-42). A `final_payload` that differs "
        "from the draft makes it `EDITED`. Applying the accepted content (e.g. sending a message) "
        "is a separate, ordinary action by the same person."
    ),
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def accept_draft(
    draft_id: uuid.UUID, body: AiDraftAccept, ctx: ShopContextDep, uow: UowDep
) -> AiDraftRead:
    return await service.accept_draft(uow, ctx, draft_id, body)


@router.post(
    "/ai/drafts/{draft_id}/reject",
    summary="Reject an AI draft",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def reject_draft(
    draft_id: uuid.UUID, body: AiDraftReject, ctx: ShopContextDep, uow: UowDep
) -> AiDraftRead:
    return await service.reject_draft(uow, ctx, draft_id, body)


routers: tuple[APIRouter, ...] = (router,)

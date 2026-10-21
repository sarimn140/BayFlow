"""HTTP routes of the reporting module (spec 03 §4.13; `modules/reporting.md`; D89).

- `overview_router` = `shop_scoped_router(tags=["reporting"])` (D20, D80): `GET …/overview`
  (`reporting_get_overview`, P0). A caller without an active membership in the shop gets 404 from
  the router-level tenant check; a member whose role is not `OWNER` gets 403 `FORBIDDEN` from
  `require_roles(OWNER)`, and the service checks the role again (D16).
- `me_router` (`/api/v1/me`): `GET /owner-summary` (`reporting_get_owner_summary`, P1). Any
  logged-in user; only the shops the caller owns are listed (`items: []` otherwise, never 403).

Neither route takes a body or query parameters. Both are reads the web polls (D14, spec 03 §6.6);
every response carries `Cache-Control: no-store` (D61, set by the middleware).
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.database import DbSession
from app.core.error_handlers import problem_responses
from app.modules.reporting import service
from app.modules.reporting.schemas import OverviewRead, OwnerSummaryRead
from app.shared.auth import CurrentUserDep, ShopContext, require_roles, shop_scoped_router
from app.shared.enums import MembershipRole

overview_router = shop_scoped_router(tags=["reporting"])
me_router = APIRouter(prefix="/api/v1/me", tags=["reporting"])

OwnerContext = Annotated[ShopContext, Depends(require_roles(MembershipRole.OWNER))]


@overview_router.get(
    "/overview",
    summary="Get the shop overview (Owner)",
    description=(
        "Brief §7.4 Owner: bookings by status (all 17, zeros included), today's figures in the "
        "shop's time zone, the team with open jobs (inactive members and the Owner included), the "
        "inventory summary over active parts, up to 5 low-stock parts and the setup checklist. "
        "Owner only (403 for every other role); 404 for anyone who is not an active member. The "
        "five most recent bookings come from `GET …/bookings?sort=-updated_at&limit=5`."
    ),
    responses=problem_responses(401, 403, 404, 422),
)
async def get_overview(context: OwnerContext, session: DbSession) -> OverviewRead:
    return await service.get_owner_overview(session, context)


@me_router.get(
    "/owner-summary",
    summary="Get the multi-shop summary of the shops I own",
    description=(
        "One row per shop where the caller is the `OWNER`, ordered by shop name: today's bookings, "
        "bookings needing the Service Advisor, jobs in progress, ready for pick-up and low-stock "
        "parts. Suspended shops are left out (`/me` flags them with `shop_suspended`). `items` is "
        "empty for anyone who owns no open shop."
    ),
    responses=problem_responses(401),
)
async def get_owner_summary(user: CurrentUserDep, session: DbSession) -> OwnerSummaryRead:
    return await service.get_owner_summary(session, user)


routers: tuple[APIRouter, ...] = (overview_router, me_router)

"""HTTP routes of the scheduling module (spec 03 §4.5; `modules/scheduling.md` §6).

`GET /api/v1/public/shops/{shop_slug}/availability?date=YYYY-MM-DD` (`scheduling_get_availability`):
public, never reads credentials. The wizard polls it every 15 s on the time step (D14).
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.core.database import DbSession
from app.core.error_handlers import problem_responses
from app.modules.scheduling import service
from app.modules.scheduling.schemas import AvailabilityRead, QueryDate

router = APIRouter(prefix="/api/v1/public/shops", tags=["scheduling"])


@router.get(
    "/{shop_slug}/availability",
    summary="List a shop's free slots on a date",
    description=(
        "The grid slots of the date (a date in the shop's timezone) that start after now, lie "
        "within 30 days and still have `remaining` places (D37, D68); full slots are omitted. "
        "Past dates, dates beyond the horizon and closed days answer `slots: []`. Unknown or "
        "unlisted slug → 404."
    ),
    responses=problem_responses(404, 422),
)
async def get_availability(
    shop_slug: Annotated[str, Path(description="The shop's public slug.")],
    day: Annotated[QueryDate, Query(alias="date", description="YYYY-MM-DD, shop-local.")],
    session: DbSession,
) -> AvailabilityRead:
    return await service.list_availability(session, shop_slug=shop_slug, day=day)


routers = (router,)

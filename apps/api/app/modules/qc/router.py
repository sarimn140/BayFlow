"""HTTP routes of the qc module (spec 03 §4.11): only the default checklist.

The QC queue, the QC history of a booking and the QC actions (`pick-qc`, `pass-qc`, `fail-qc`,
`send-to-qc`) are booking routes served by the bookings module (spec 03 §1.11, §4.8, §5.2).
`shop_scoped_router()` attaches `require_shop_member` at router level (D20, D80): any active
member of the shop may read the checklist; everyone else gets 404.
"""

from fastapi import APIRouter

from app.core.error_handlers import problem_responses
from app.modules.qc import service
from app.modules.qc.schemas import QcChecklistTemplateItem
from app.shared.auth import shop_scoped_router
from app.shared.pagination import ItemList

router = shop_scoped_router(tags=["qc"])


@router.get(
    "/qc/checklist",
    summary="The default QC checklist",
    description=(
        "The five D46 checklist items in fixed order, with their labels. Any active member of "
        "the shop may read it; the QC Inspector's pass/fail form (QI-02) is built from it."
    ),
    responses=problem_responses(401, 404, 422),
)
async def get_checklist() -> ItemList[QcChecklistTemplateItem]:
    return ItemList[QcChecklistTemplateItem](items=service.default_checklist())


routers: tuple[APIRouter, ...] = (router,)

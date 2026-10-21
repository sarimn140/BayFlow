"""Use cases of the reporting module (`modules/reporting.md`): read-only composition.

- `get_owner_overview(session, ctx)` (P0, `GET /api/v1/shops/{shop_id}/overview`): one shop as its
  Owner sees it — bookings by status, today's figures, the team with open jobs, the inventory
  summary, the top low-stock parts and the setup checklist (brief §7.4 Owner).
- `get_owner_summary(session, user)` (P1, `GET /api/v1/me/owner-summary`): one row per shop the
  caller owns and that is not suspended (brief §2 "no visibility across locations"; D99).

Both are top-level reads on the request's session. The module owns no table and runs no SQL of
its own: it composes the read functions of shops, bookings and inventory in-process (D3, D86;
spec 01 rule 5) and never writes, locks or commits. "Now" is read once per request (D63); "today"
is the shop-local date in the shop's IANA time zone as a half-open UTC window (D38). The reads run
at READ COMMITTED, so a figure may straddle a concurrent action by milliseconds; the next 15 s
poll converges (D14).
"""

from collections.abc import Mapping, Sequence
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, NotFound
from app.modules.bookings import service as bookings_service
from app.modules.inventory import service as inventory_service
from app.modules.inventory.schemas import StockSummary
from app.modules.reporting.domain.kpis import (
    IN_PROGRESS_STATUSES,
    LOW_STOCK_PREVIEW_SIZE,
    SA_ACTION_STATUSES,
    count_in,
    local_day_window,
    ordered_status_counts,
)
from app.modules.reporting.schemas import (
    OverviewInventory,
    OverviewRead,
    OverviewSetup,
    OverviewShop,
    OverviewStatusCount,
    OverviewTeamMember,
    OverviewToday,
    OwnerShopRef,
    OwnerShopSummary,
    OwnerSummaryRead,
)
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import TeamMember
from app.shared.auth import CurrentUser, ShopContext
from app.shared.clock import utcnow
from app.shared.enums import BookingStatus, MembershipRole

__all__ = ["get_owner_overview", "get_owner_summary"]


def _team(team: Sequence[TeamMember], open_jobs: Mapping[UUID, int]) -> list[OverviewTeamMember]:
    """Every membership in `list_team`'s order (role in glossary §2.1 order, then name)."""
    return [
        OverviewTeamMember(
            membership_id=member.membership_id,
            user_id=member.user_id,
            full_name=member.full_name,
            role=member.role,
            is_active=member.is_active,
            open_jobs=open_jobs.get(member.user_id, 0),
        )
        for member in team
    ]


def _inventory(stock: StockSummary) -> OverviewInventory:
    return OverviewInventory(
        parts_count=stock.parts_count,
        low_stock_count=stock.low_stock_count,
        out_of_stock_count=stock.out_of_stock_count,
        stock_value=stock.stock_value,
        open_purchase_orders=stock.open_purchase_orders,
    )


async def get_owner_overview(session: AsyncSession, ctx: ShopContext) -> OverviewRead:
    """The Owner's overview of `ctx.shop_id` (spec 03 §3.7 "Reporting definitions").

    The route admits only the shop's Owner (`require_roles`); the role is checked again here so a
    direct caller cannot bypass it (403 `FORBIDDEN`, D16). Counts cover every booking of the shop:
    the Owner sees them all (D21). Inactive parts are left out of every inventory figure.
    """
    if ctx.role != MembershipRole.OWNER:
        raise Forbidden
    shop_id = ctx.shop_id
    now = utcnow()
    brief = (await shops_service.get_shop_briefs(session, shop_ids=[shop_id])).get(shop_id)
    if brief is None:  # the caller's membership guarantees the shop; never trust it blindly
        raise NotFound
    today = local_day_window(now, ZoneInfo(brief.timezone))
    counts = await bookings_service.count_by_status(session, shop_id=shop_id)
    activity = await bookings_service.count_day_activity(
        session, shop_id=shop_id, start=today.start, end=today.end
    )
    team = await shops_service.list_team(session, shop_id=shop_id)
    open_jobs = await bookings_service.count_open_jobs(
        session, shop_id=shop_id, user_ids=[member.user_id for member in team]
    )
    stock = await inventory_service.get_stock_summary(session, shop_id=shop_id)
    flags = await shops_service.get_setup_flags(session, shop_id=shop_id)
    return OverviewRead(
        # One read of `is_listed` feeds both fields, so they can never disagree in one response.
        shop=OverviewShop(
            id=brief.id,
            slug=brief.slug,
            name=brief.name,
            city=brief.city,
            is_listed=brief.is_listed,
        ),
        status_counts=[
            OverviewStatusCount(status=status, count=count)
            for status, count in ordered_status_counts(counts)
        ],
        today=OverviewToday(
            date=today.date,
            bookings=activity.bookings,
            ready_for_pickup=counts.get(BookingStatus.READY_FOR_PICKUP, 0),
            completed=activity.completed,
        ),
        team=_team(team, open_jobs),
        inventory=_inventory(stock),
        low_stock=stock.low_stock[:LOW_STOCK_PREVIEW_SIZE],
        setup=OverviewSetup(
            has_services=flags.has_services,
            has_team=flags.has_team,
            has_parts=stock.parts_count > 0,
            is_listed=brief.is_listed,
        ),
    )


async def get_owner_summary(session: AsyncSession, user: CurrentUser) -> OwnerSummaryRead:
    """One row per shop where `user` holds the `OWNER` membership, ordered by shop name, then id
    (the order of `shops.list_memberships_for_user`, the same as the shop switcher's).

    Any logged-in user may call it: a customer or a pure staff member gets `items: []`, never a
    403 (RPT-02). Each shop's "today" is computed in that shop's own time zone from one instant.
    A suspended shop is left out (D99): its staff routes answer 403 `SHOP_SUSPENDED`, and `/me`
    still lists the membership with `shop_suspended: true`, which is where the web shows it.
    """
    memberships = await shops_service.list_memberships_for_user(
        session, user_id=user.id, roles={MembershipRole.OWNER}
    )
    shop_ids = list(dict.fromkeys(membership.shop_id for membership in memberships))
    if not shop_ids:
        return OwnerSummaryRead(items=[])
    now = utcnow()
    briefs = await shops_service.get_shop_briefs(session, shop_ids=shop_ids)
    owned = [  # membership order
        briefs[shop_id]
        for shop_id in shop_ids
        if shop_id in briefs and not briefs[shop_id].is_suspended
    ]
    if not owned:
        return OwnerSummaryRead(items=[])
    low_stock = await inventory_service.count_low_stock(
        session, shop_ids=[brief.id for brief in owned]
    )
    items: list[OwnerShopSummary] = []
    for brief in owned:
        today = local_day_window(now, ZoneInfo(brief.timezone))
        counts = await bookings_service.count_by_status(session, shop_id=brief.id)
        activity = await bookings_service.count_day_activity(
            session, shop_id=brief.id, start=today.start, end=today.end
        )
        items.append(
            OwnerShopSummary(
                shop=OwnerShopRef(id=brief.id, slug=brief.slug, name=brief.name, city=brief.city),
                today_bookings=activity.bookings,
                needs_sa_action=count_in(counts, SA_ACTION_STATUSES),
                in_progress=count_in(counts, IN_PROGRESS_STATUSES),
                ready_for_pickup=counts.get(BookingStatus.READY_FOR_PICKUP, 0),
                low_stock_count=low_stock.get(brief.id, 0),
            )
        )
    return OwnerSummaryRead(items=items)

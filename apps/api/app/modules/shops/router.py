"""HTTP routes of the shops module (spec 03 §4.4, §4.5, §4.9; `modules/shops.md` §6).

Four routers:
- `public_router` (`/api/v1/public`): the directory, cities and shop pages by slug (D64, D68);
  public routes never read credentials;
- `me_router` (`/api/v1`): `GET /me` (`shops_get_me`, D66, D81);
- `shops_router` (`/api/v1/shops`): `POST` only, any logged-in user creates a shop (D17);
- `shop_router` (`shop_scoped_router()`, D80): every `/api/v1/shops/{shop_id}/…` route, 404 for
  callers without an active membership (D20). Management guards come from `CAPABILITY_ROLES`, so
  a route and `/me`'s capabilities can never disagree (D66, SEC-46).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.database import DbSession
from app.core.error_handlers import problem_responses
from app.modules.shops import service
from app.modules.shops.domain.capabilities import CAPABILITY_ROLES, TEAM_VIEW_ROLES, Capability
from app.modules.shops.schemas import (
    CITY_MAX_LENGTH,
    SEARCH_MAX_LENGTH,
    MemberCreate,
    MemberCreatedRead,
    MemberRead,
    MemberUpdate,
    MeRead,
    ServiceCreate,
    ServiceRead,
    ServiceUpdate,
    ShopCreate,
    ShopPublicDetail,
    ShopPublicSummary,
    ShopRead,
    ShopUpdate,
    WorkingHoursUpdate,
)
from app.shared.auth import (
    CurrentUserDep,
    ShopContext,
    ShopContextDep,
    require_roles,
    shop_scoped_router,
)
from app.shared.enums import MembershipRole
from app.shared.pagination import ItemList, Page, PageParamsDep
from app.shared.uow import UowDep

public_router = APIRouter(prefix="/api/v1/public", tags=["shops"])
me_router = APIRouter(prefix="/api/v1", tags=["shops"])
shops_router = APIRouter(prefix="/api/v1/shops", tags=["shops"])
shop_router = shop_scoped_router(tags=["shops"])

ShopManager = Annotated[
    ShopContext, Depends(require_roles(*CAPABILITY_ROLES[Capability.SHOP_MANAGE]))
]
TeamManager = Annotated[
    ShopContext, Depends(require_roles(*CAPABILITY_ROLES[Capability.TEAM_MANAGE]))
]
ServicesManager = Annotated[
    ShopContext, Depends(require_roles(*CAPABILITY_ROLES[Capability.SERVICES_MANAGE]))
]
TeamViewer = Annotated[ShopContext, Depends(require_roles(*TEAM_VIEW_ROLES))]

ShopSlug = Annotated[str, Path(description="The shop's public slug, e.g. `lahore-auto-care`.")]


# --- Public directory ----------------------------------------------------------------------------


@public_router.get(
    "/shops",
    summary="List the public shop directory",
    description=(
        "Listed shops with at least one active service (D64), ordered by name. `q` matches the "
        "shop name, city or an active service name; `city` is an exact, case-insensitive match."
    ),
    responses=problem_responses(422),
)
async def list_public_shops(
    session: DbSession,
    page: PageParamsDep,
    q: Annotated[
        str | None,
        Query(max_length=SEARCH_MAX_LENGTH, description="Search text (case-insensitive)."),
    ] = None,
    city: Annotated[
        str | None, Query(max_length=CITY_MAX_LENGTH, description="City (exact match).")
    ] = None,
) -> Page[ShopPublicSummary]:
    return await service.list_public_shops(session, q=q, city=city, page=page)


@public_router.get(
    "/cities",
    summary="List the cities of the directory",
    description="One entry per city of the directory's shops, alphabetical.",
)
async def list_public_cities(session: DbSession) -> ItemList[str]:
    return ItemList[str](items=await service.list_public_cities(session))


@public_router.get(
    "/shops/{shop_slug}",
    summary="Get a shop's public page",
    description=(
        "404 for an unknown or unlisted slug. A listed shop without an active service answers "
        "with `services: []` and `is_bookable: false` (D64)."
    ),
    responses=problem_responses(404),
)
async def get_public_shop(shop_slug: ShopSlug, session: DbSession) -> ShopPublicDetail:
    return await service.get_public_shop(session, shop_slug=shop_slug)


# --- Current user ---------------------------------------------------------------------------------


@me_router.get(
    "/me",
    summary="Get the current user with memberships and capabilities",
    description=(
        "The account and its active memberships, sorted by shop name, each with the "
        "server-computed `capabilities` of its role (D66). Call it right after login."
    ),
    responses=problem_responses(401),
)
async def get_me(user: CurrentUserDep, session: DbSession) -> MeRead:
    return await service.get_me(session, user_id=user.id)


# --- Shops ----------------------------------------------------------------------------------------


@shops_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a shop",
    description=(
        "Any logged-in user may create a shop and becomes its `OWNER` (D17). The shop, its 7 "
        "working-hours rows and the `OWNER` membership are created in one transaction; the slug "
        "comes from the name (`-2`, `-3` … on a clash) and never changes."
    ),
    responses=problem_responses(401, 422, 429),
)
async def create_shop(body: ShopCreate, user: CurrentUserDep, uow: UowDep) -> ShopRead:
    return await service.create_shop(uow, actor_user_id=user.id, data=body)


@shop_router.get(
    "",
    summary="Get a shop (staff view)",
    responses=problem_responses(401, 404),
)
async def get_shop(context: ShopContextDep, session: DbSession) -> ShopRead:
    return await service.get_shop(session, shop_id=context.shop_id)


@shop_router.patch(
    "",
    summary="Update a shop's settings",
    description=(
        "Owner only. Changing `slot_duration_minutes` or `timezone` is refused with 409 while the "
        "shop has future bookings, and a new duration must keep the working hours on its grid "
        "(422 `hours_not_on_grid`). Capacity and listing changes are always allowed (D37)."
    ),
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def update_shop(body: ShopUpdate, context: ShopManager, uow: UowDep) -> ShopRead:
    return await service.update_shop(
        uow, shop_id=context.shop_id, actor_user_id=context.user.id, data=body
    )


@shop_router.put(
    "/working-hours",
    summary="Replace the working hours",
    description=(
        "Owner only. Exactly 7 entries, one per weekday; open days need both times on the slot "
        "grid (minutes since midnight divisible by the slot duration). Always allowed: existing "
        "bookings are kept (D37)."
    ),
    responses=problem_responses(401, 403, 404, 422),
)
async def replace_working_hours(
    body: WorkingHoursUpdate, context: ShopManager, uow: UowDep
) -> ShopRead:
    return await service.replace_working_hours(
        uow, shop_id=context.shop_id, actor_user_id=context.user.id, data=body
    )


# --- Team -----------------------------------------------------------------------------------------


@shop_router.get(
    "/members",
    summary="List the team",
    description=(
        "Owner: every membership, inactive ones and the `OWNER` row included. Service Advisor: "
        "active technicians and parts persons only (the assign pickers). Ordered by role, then "
        "name."
    ),
    responses=problem_responses(401, 403, 404, 422),
)
async def list_members(
    context: TeamViewer,
    session: DbSession,
    page: PageParamsDep,
    role: Annotated[list[MembershipRole] | None, Query(description="Repeatable.")] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> Page[MemberRead]:
    return await service.list_members(
        session,
        shop_id=context.shop_id,
        caller_role=context.role,
        roles=role,
        is_active=is_active,
        page=page,
    )


@shop_router.post(
    "/members",
    status_code=status.HTTP_201_CREATED,
    summary="Add a team member",
    description=(
        "Owner only (D18). A new e-mail creates the account with the given initial `password`; "
        "an existing e-mail only gets the membership and keeps its password, name and phone "
        "(`account_created: false`). Already a member here, active or not → 409."
    ),
    responses=problem_responses(401, 403, 404, 409, 422, 429),
)
async def add_member(body: MemberCreate, context: TeamManager, uow: UowDep) -> MemberCreatedRead:
    return await service.add_member(
        uow, shop_id=context.shop_id, actor_user_id=context.user.id, data=body
    )


@shop_router.patch(
    "/members/{membership_id}",
    summary="Change a member's role, deactivate or reactivate",
    description=(
        "Owner only (D19). The `OWNER` membership can never be changed (403). Takes effect on the "
        "member's next request; their bookings stay assigned."
    ),
    responses=problem_responses(401, 403, 404, 422),
)
async def update_member(
    membership_id: uuid.UUID, body: MemberUpdate, context: TeamManager, uow: UowDep
) -> MemberRead:
    return await service.update_member(
        uow,
        shop_id=context.shop_id,
        actor_user_id=context.user.id,
        membership_id=membership_id,
        data=body,
    )


# --- Service catalogue ----------------------------------------------------------------------------


@shop_router.get(
    "/services",
    summary="List the service catalogue",
    responses=problem_responses(401, 404, 422),
)
async def list_services(
    context: ShopContextDep,
    session: DbSession,
    page: PageParamsDep,
    include_inactive: Annotated[bool, Query(description="Include deactivated services.")] = False,
) -> Page[ServiceRead]:
    return await service.list_services(
        session, shop_id=context.shop_id, include_inactive=include_inactive, page=page
    )


@shop_router.post(
    "/services",
    status_code=status.HTTP_201_CREATED,
    summary="Add a service to the catalogue",
    description="Owner only. A duplicate active name (case-insensitive) → 409.",
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def create_service(body: ServiceCreate, context: ServicesManager, uow: UowDep) -> ServiceRead:
    return await service.create_service(
        uow, shop_id=context.shop_id, actor_user_id=context.user.id, data=body
    )


@shop_router.patch(
    "/services/{service_id}",
    summary="Update or deactivate a service",
    description=(
        "Owner only. Deactivating hides the service from the directory and the wizard; existing "
        "bookings keep their snapshots (D34)."
    ),
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def update_service(
    service_id: uuid.UUID, body: ServiceUpdate, context: ServicesManager, uow: UowDep
) -> ServiceRead:
    return await service.update_service(
        uow,
        shop_id=context.shop_id,
        actor_user_id=context.user.id,
        service_id=service_id,
        data=body,
    )


routers = (public_router, me_router, shops_router, shop_router)

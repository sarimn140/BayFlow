"""HTTP routes of the admin module: `/api/v1/admin/*`, E-61…E-75 (spec 19 §4; D94-D97).

One router, tag `admin` (operation ids `admin_<function>`), with two router-level dependencies, so
no admin route can forget them: `refuse_cross_site_requests` (D98: 403 `FORBIDDEN` when
`Sec-Fetch-Site` names another site) and `require_platform_admin` (401 when not logged in, 403
`FORBIDDEN` for any user without `is_platform_admin`, shop Owners included). Every endpoint calls
one service function.
GET routes that open a person's or a booking's detail (E-67, E-73) and the export (E-75) write an
audit row, so they take a unit of work.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse

from app.core.database import DbSession
from app.core.error_handlers import problem_responses
from app.modules.admin import service
from app.modules.admin.schemas import (
    SEARCH_MAX_LENGTH,
    AdminBookingDetail,
    AdminBookingFilters,
    AdminBookingSort,
    AdminBookingSummary,
    AdminShopDetail,
    AdminShopRow,
    AdminShopSort,
    AdminShopStatus,
    AdminUserDetail,
    AdminUserKind,
    AdminUserRow,
    AdminUserStatus,
    AuditEventRead,
    AuditFilters,
    AuditSort,
    PlatformOverviewRead,
    QueryDate,
    ShopSuspendRequest,
    UserAdminSort,
    UserDeactivateRequest,
)
from app.shared.auth import (
    PlatformAdminDep,
    refuse_cross_site_requests,
    require_platform_admin,
)
from app.shared.enums import AuditCategory, AuditTargetType, BookingStatus
from app.shared.pagination import Page, PageParamsDep
from app.shared.timestamps import Timestamp
from app.shared.uow import UowDep

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(refuse_cross_site_requests), Depends(require_platform_admin)],
    responses=problem_responses(401, 403),
)

ShopIdPath = Annotated[uuid.UUID, Path(description="The shop (tenant) id.")]
UserIdPath = Annotated[uuid.UUID, Path(description="The account id.")]
BookingIdPath = Annotated[uuid.UUID, Path(description="The booking id.")]
SearchText = Annotated[
    str | None, Query(max_length=SEARCH_MAX_LENGTH, description="Case-insensitive search text.")
]
CSV_MEDIA_TYPE = "text/csv; charset=utf-8"


# --- E-61 ----------------------------------------------------------------------------------------


@router.get(
    "/overview",
    summary="Platform overview",
    description=(
        "Shops, accounts and bookings across every tenant: booking counts by placement date in "
        "`Asia/Karachi` local days (D38), open bookings per phase, bookings per day for 14 days, "
        "the 5 busiest shops of the last 30 days and the 10 newest audit events."
    ),
)
async def get_overview(session: DbSession) -> PlatformOverviewRead:
    return await service.get_overview(session)


# --- E-62 - E-65 ---------------------------------------------------------------------------------


@router.get(
    "/shops",
    summary="Every shop",
    description=(
        "Every tenant, suspended ones included. `q` matches the name, slug, city or the owner's "
        "e-mail. Sort `-created_at` (default), `name` or `-bookings_30d` (bookings placed in the "
        "last 30 days)."
    ),
    responses=problem_responses(422),
)
async def list_shops(  # noqa: PLR0913 - one parameter per E-62 filter
    *,
    session: DbSession,
    page: PageParamsDep,
    q: SearchText = None,
    status: Annotated[AdminShopStatus | None, Query(description="Suspended or not.")] = None,
    listed: Annotated[bool | None, Query(description="The `is_listed` flag.")] = None,
    city: Annotated[str | None, Query(max_length=80, description="Exact city.")] = None,
    sort: Annotated[AdminShopSort, Query()] = "-created_at",
) -> Page[AdminShopRow]:
    return await service.list_shops(
        session, q=q, status=status, listed=listed, city=city, sort=sort, page=page
    )


@router.get(
    "/shops/{shop_id}",
    summary="One shop",
    description=(
        "The profile, the suspension, the team by role, bookings per phase, the 10 newest "
        "bookings and the 10 newest audit events of the shop."
    ),
    responses=problem_responses(404, 422),
)
async def get_shop(shop_id: ShopIdPath, session: DbSession) -> AdminShopDetail:
    return await service.get_shop(session, shop_id=shop_id)


@router.post(
    "/shops/{shop_id}/suspend",
    summary="Suspend a shop",
    description=(
        "With a reason of 5-500 characters (D96). The shop disappears from the public directory "
        "and booking, its staff get 403 `SHOP_SUSPENDED`, its customers can still read and cancel "
        "their bookings. Nothing is deleted. Already suspended → 409. Answers the shop's detail."
    ),
    responses=problem_responses(404, 409, 422),
)
async def suspend_shop(
    shop_id: ShopIdPath, body: ShopSuspendRequest, admin: PlatformAdminDep, uow: UowDep
) -> AdminShopDetail:
    return await service.suspend_shop(uow, admin, shop_id=shop_id, reason=body.reason)


@router.post(
    "/shops/{shop_id}/reactivate",
    summary="Reactivate a suspended shop",
    description="Everything resumes as it was (D96). Not suspended → 409.",
    responses=problem_responses(404, 409, 422),
)
async def reactivate_shop(
    shop_id: ShopIdPath, admin: PlatformAdminDep, uow: UowDep
) -> AdminShopDetail:
    return await service.reactivate_shop(uow, admin, shop_id=shop_id)


# --- E-66 - E-71 ---------------------------------------------------------------------------------


@router.get(
    "/users",
    summary="Every account",
    description=(
        "`q` matches the name, e-mail or phone; `kind` `CUSTOMER` = no active membership, `STAFF`"
        " = at least one, `PLATFORM_ADMIN` = the flag. Sort `-created_at` (default), `name` or "
        "`-last_login_at`."
    ),
    responses=problem_responses(422),
)
async def list_users(
    session: DbSession,
    page: PageParamsDep,
    q: SearchText = None,
    kind: Annotated[AdminUserKind | None, Query()] = None,
    status: Annotated[AdminUserStatus | None, Query()] = None,
    sort: Annotated[UserAdminSort, Query()] = "-created_at",
) -> Page[AdminUserRow]:
    return await service.list_users(session, q=q, kind=kind, status=status, sort=sort, page=page)


@router.get(
    "/users/{user_id}",
    summary="One account",
    description=(
        "The account with its memberships, its bookings as a customer and the 10 newest audit "
        "events done by or about it. Recorded as `admin.user_viewed`."
    ),
    responses=problem_responses(404, 422),
)
async def get_user(user_id: UserIdPath, admin: PlatformAdminDep, uow: UowDep) -> AdminUserDetail:
    return await service.view_user(uow, admin, user_id=user_id)


@router.post(
    "/users/{user_id}/deactivate",
    summary="Deactivate an account",
    description=(
        "With a reason of 5-500 characters. Its tokens stop working at its next request (D9). "
        "Yourself → 403; the last active platform admin → 409; already inactive → 409."
    ),
    responses=problem_responses(404, 409, 422),
)
async def deactivate_user(
    user_id: UserIdPath, body: UserDeactivateRequest, admin: PlatformAdminDep, uow: UowDep
) -> AdminUserDetail:
    return await service.deactivate_user(uow, admin, user_id=user_id, reason=body.reason)


@router.post(
    "/users/{user_id}/reactivate",
    summary="Reactivate an account",
    description="Already active → 409.",
    responses=problem_responses(404, 409, 422),
)
async def reactivate_user(
    user_id: UserIdPath, admin: PlatformAdminDep, uow: UowDep
) -> AdminUserDetail:
    return await service.reactivate_user(uow, admin, user_id=user_id)


@router.post(
    "/users/{user_id}/grant-platform-admin",
    summary="Make an account a platform admin",
    description="An inactive account → 422 (`path.user_id`); already an admin → 409.",
    responses=problem_responses(404, 409, 422),
)
async def grant_platform_admin(
    user_id: UserIdPath, admin: PlatformAdminDep, uow: UowDep
) -> AdminUserDetail:
    return await service.grant_platform_admin(uow, admin, user_id=user_id)


@router.post(
    "/users/{user_id}/revoke-platform-admin",
    summary="Revoke an account's platform admin access",
    description="Yourself → 403; the last active platform admin → 409; not an admin → 409.",
    responses=problem_responses(404, 409, 422),
)
async def revoke_platform_admin(
    user_id: UserIdPath, admin: PlatformAdminDep, uow: UowDep
) -> AdminUserDetail:
    return await service.revoke_platform_admin(uow, admin, user_id=user_id)


# --- E-72, E-73 ----------------------------------------------------------------------------------


def admin_booking_filters(
    q: Annotated[
        str | None,
        Query(
            max_length=SEARCH_MAX_LENGTH,
            description="Reference (with or without `BF-`), plate, customer name or e-mail.",
        ),
    ] = None,
    shop_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[
        list[BookingStatus] | None, Query(description="Repeatable: `?status=A&status=B`.")
    ] = None,
    date_from: Annotated[
        QueryDate | None, Query(description="Slot date in the shop's zone, inclusive.")
    ] = None,
    date_to: Annotated[
        QueryDate | None, Query(description="Slot date in the shop's zone, inclusive.")
    ] = None,
) -> AdminBookingFilters:
    return AdminBookingFilters(
        q=q, shop_id=shop_id, statuses=tuple(status or ()), date_from=date_from, date_to=date_to
    )


@router.get(
    "/bookings",
    summary="Every tenant's bookings",
    description=(
        "Read-only (no `allowed_actions`). Sort `-slot_start` (default), `slot_start` or "
        "`-created_at`."
    ),
    responses=problem_responses(422),
)
async def list_bookings(
    session: DbSession,
    page: PageParamsDep,
    filters: Annotated[AdminBookingFilters, Depends(admin_booking_filters)],
    sort: Annotated[AdminBookingSort, Query()] = "-slot_start",
) -> Page[AdminBookingSummary]:
    return await service.list_bookings(session, filters=filters, sort=sort, page=page)


@router.get(
    "/bookings/{booking_id}",
    summary="One booking (read-only)",
    description=(
        "The staff projection without `allowed_actions`, with the full timeline. Recorded as "
        "`admin.booking_viewed`."
    ),
    responses=problem_responses(404, 422),
)
async def get_booking(
    booking_id: BookingIdPath, admin: PlatformAdminDep, uow: UowDep
) -> AdminBookingDetail:
    return await service.view_booking(uow, admin, booking_id=booking_id)


# --- E-74, E-75 ----------------------------------------------------------------------------------


def audit_filters(  # noqa: PLR0913 - one parameter per E-74 filter
    *,
    category: Annotated[
        list[AuditCategory] | None, Query(description="Repeatable: `?category=A&category=B`.")
    ] = None,
    action: Annotated[
        str | None, Query(max_length=64, description="E.g. `shop.suspended`.")
    ] = None,
    actor_user_id: Annotated[uuid.UUID | None, Query()] = None,
    shop_id: Annotated[uuid.UUID | None, Query()] = None,
    target_type: Annotated[AuditTargetType | None, Query()] = None,
    target_id: Annotated[uuid.UUID | None, Query()] = None,
    occurred_from: Annotated[
        Timestamp | None, Query(alias="from", description="Inclusive instant (`Z` or offset).")
    ] = None,
    occurred_to: Annotated[
        Timestamp | None, Query(alias="to", description="Exclusive instant (`Z` or offset).")
    ] = None,
    q: Annotated[
        str | None,
        Query(max_length=SEARCH_MAX_LENGTH, description="Matches the summary or target label."),
    ] = None,
) -> AuditFilters:
    return AuditFilters(
        categories=tuple(category or ()),
        action=action,
        actor_user_id=actor_user_id,
        shop_id=shop_id,
        target_type=target_type,
        target_id=target_id,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        q=q,
    )


AuditFiltersDep = Annotated[AuditFilters, Depends(audit_filters)]


@router.get(
    "/audit-events",
    summary="The platform audit log",
    description="Every recorded action across tenants (D95). Sort `-occurred_at` (default).",
    responses=problem_responses(422),
)
async def list_audit_events(
    session: DbSession,
    page: PageParamsDep,
    filters: AuditFiltersDep,
    sort: Annotated[AuditSort, Query()] = "-occurred_at",
) -> Page[AuditEventRead]:
    return await service.list_audit_events(session, filters=filters, sort=sort, page=page)


@router.get(
    "/audit-events/export",
    summary="Export the audit log as CSV",
    description=(
        "The same filters as the list; at most 10 000 rows, newest first. RFC 4180 CSV in UTF-8 "
        "with a header row; a cell starting with `=`, `+`, `-` or `@` is prefixed with `'`. "
        "Recorded as `admin.audit_exported`."
    ),
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "The CSV file.",
            "content": {"text/csv": {"schema": {"type": "string"}}},
        },
        **problem_responses(422),
    },
)
async def export_audit_events(
    admin: PlatformAdminDep, uow: UowDep, filters: AuditFiltersDep
) -> StreamingResponse:
    export = await service.export_audit_events(uow, admin, filters=filters)
    return StreamingResponse(
        iter(export.lines),
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
    )


routers = (router,)

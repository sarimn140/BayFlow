"""HTTP routes of the bookings module (spec 03 §4.6-§4.8, §5; `modules/bookings.md` §6, §7.8).

Three routers, all tagged `bookings` and exported as `routers` (D89):

- `wizard_router` (`/api/v1`): `POST /bookings` (T01). Credentials are optional but never ignored:
  present and invalid → 401 (D32 case A). Anonymous callers pass the per-IP ceiling here (D69); a
  session is limited per user by the service. Every 201 sets the session cookie.
- `me_router` (`/api/v1/me`): the customer family — own bookings, timeline, estimate history,
  vehicles and the four customer action routes. Anything not the caller's own is 404.
- `shop_router` (`shop_scoped_router()`, D20, D80): the staff family — list, status counts
  (registered before `{booking_id}`), detail, timeline, estimate versions, the estimate editor,
  booking parts, QC rounds and one action route per staff slug.

Action routes are generated from spec 08's rule table (D48): one `POST …/actions/{slug}` per slug
of each family, named after the slug (`bookings_<slug>`, customer `bookings_my_<slug>`), each with
its own `<PascalCaseSlug>Request` body; a body without required fields may be omitted. A slug
outside a family has no route (404, API-10); `edit-estimate` is `PUT …/estimate`. Every endpoint
calls exactly one service function (the wizard also asks the service for the anonymous limit).
"""

import inspect
from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Query, Request, Response, status

from app.core.database import DbSession
from app.core.error_handlers import problem_responses
from app.core.security import client_ip
from app.modules.bookings import service
from app.modules.bookings.domain.state_machine import ACTION_TO_SLUG, RULES
from app.modules.bookings.domain.timeline import customer_route_actions, staff_route_actions
from app.modules.bookings.schemas import (
    CUSTOMER_ACTION_REQUESTS,
    SEARCH_MAX_LENGTH,
    STAFF_ACTION_REQUESTS,
    ActionRequest,
    BookingCreate,
    BookingCreatedRead,
    BookingDetail,
    BookingEventRead,
    BookingPartsRead,
    BookingSort,
    BookingSummary,
    CustomerBookingDetail,
    CustomerBookingEventRead,
    CustomerBookingSort,
    CustomerBookingSummary,
    CustomerEstimateRead,
    EstimateEditRead,
    EstimateRead,
    EstimateUpdate,
    QcInspectionRead,
    QueryDate,
    StaffBookingFilters,
    StatusCountsRead,
    VehicleRead,
)
from app.shared.auth import (
    CurrentUser,
    CurrentUserDep,
    OptionalUserDep,
    ShopContext,
    ShopContextDep,
    set_session_cookie,
    shop_scoped_router,
)
from app.shared.enums import BookingAction, BookingStatus
from app.shared.pagination import ItemList, Page, PageParamsDep
from app.shared.uow import UnitOfWork, UowDep

TAG = "bookings"

wizard_router = APIRouter(prefix="/api/v1", tags=[TAG])
me_router = APIRouter(prefix="/api/v1/me", tags=[TAG])
shop_router = shop_scoped_router(tags=[TAG])

BookingIdPath = Annotated[UUID, Path(description="The booking id.")]


# --- Wizard (spec 03 §4.6) ------------------------------------------------------------------------


@wizard_router.post(
    "/bookings",
    status_code=status.HTTP_201_CREATED,
    summary="Book a service (the booking wizard)",
    description=(
        "Creates a `PENDING` booking (T01) and always logs the customer in: the response sets the "
        "`bf_session` cookie and carries `access_token`, `expires_in` and `account_created` (D32). "
        "Without a session, `customer.full_name`, `customer.email` and `customer.password` are "
        "required: a new e-mail creates the account, an existing one must come with its password "
        "(else 409 `EMAIL_ALREADY_REGISTERED`, nothing created). With a session only "
        "`customer.phone` is used. 404 when the shop is unknown, unlisted or has no active "
        "service; 422 `INVALID_SLOT` off the grid; 409 `SLOT_FULL` when the slot is taken."
    ),
    responses=problem_responses(401, 404, 409, 422, 429),
)
async def create_booking(
    data: BookingCreate,
    request: Request,
    response: Response,
    user: OptionalUserDep,
    uow: UowDep,
) -> BookingCreatedRead:
    if user is None:
        service.check_anonymous_booking_rate(client_ip(request))
    created = await service.create_booking(uow, caller=user, data=data)
    set_session_cookie(response, created.access_token)
    return created


# --- Customer family (spec 03 §4.7) ---------------------------------------------------------------


@me_router.get(
    "/bookings",
    summary="My bookings",
    description=(
        "The caller's own bookings at every shop. `active=true` lists the non-terminal ones, "
        "`active=false` the completed and cancelled ones; default sort `slot_start` for active "
        "bookings, else `-slot_start`. A booking that waits for the customer is recognisable from "
        "its `allowed_actions`."
    ),
    responses=problem_responses(401, 422),
)
async def list_my_bookings(
    user: CurrentUserDep,
    session: DbSession,
    page: PageParamsDep,
    active: Annotated[
        bool | None, Query(description="true = active, false = completed or cancelled.")
    ] = None,
    sort: Annotated[
        CustomerBookingSort | None, Query(description="`slot_start`, `-slot_start`, `-updated_at`.")
    ] = None,
) -> Page[CustomerBookingSummary]:
    return await service.list_customer_bookings(session, user, active=active, sort=sort, page=page)


@me_router.get(
    "/bookings/{booking_id}",
    summary="One of my bookings",
    description="404 unless it is the caller's own booking, even for staff of that shop.",
    responses=problem_responses(401, 404, 422),
)
async def get_my_booking(
    booking_id: BookingIdPath, user: CurrentUserDep, session: DbSession
) -> CustomerBookingDetail:
    return await service.get_customer_booking(session, user, booking_id=booking_id)


@me_router.get(
    "/bookings/{booking_id}/events",
    summary="My booking's timeline",
    description=(
        "Oldest first. Estimate edits and reassignments are left out; a note appears only for a "
        "decline, cancel or reject reason; no staff names, roles or metadata."
    ),
    responses=problem_responses(401, 404, 422),
)
async def list_my_booking_events(
    booking_id: BookingIdPath, user: CurrentUserDep, session: DbSession
) -> ItemList[CustomerBookingEventRead]:
    items = await service.list_customer_booking_events(session, user, booking_id=booking_id)
    return ItemList[CustomerBookingEventRead](items=items)


@me_router.get(
    "/bookings/{booking_id}/estimates",
    summary="My booking's estimate versions",
    description="Only `SENT`, `APPROVED` and `REJECTED` versions, ascending by version (D39).",
    responses=problem_responses(401, 404, 422),
)
async def list_my_booking_estimates(
    booking_id: BookingIdPath, user: CurrentUserDep, session: DbSession
) -> ItemList[CustomerEstimateRead]:
    items = await service.list_customer_estimates(session, user, booking_id=booking_id)
    return ItemList[CustomerEstimateRead](items=items)


@me_router.get(
    "/vehicles",
    summary="My vehicles",
    description=(
        "The caller's vehicles, most recently updated first. Re-booking one sends its fields "
        "again; the wizard matches it on the normalised registration (D35)."
    ),
    responses=problem_responses(401),
)
async def list_my_vehicles(user: CurrentUserDep, session: DbSession) -> ItemList[VehicleRead]:
    return ItemList[VehicleRead](items=await service.list_my_vehicles(session, user))


# --- Staff family (spec 03 §4.8) ------------------------------------------------------------------


def staff_booking_filters(
    status: Annotated[
        list[BookingStatus] | None, Query(description="Repeatable: `?status=A&status=B`.")
    ] = None,
    q: Annotated[
        str | None,
        Query(
            max_length=SEARCH_MAX_LENGTH,
            description="Reference (with or without `BF-`), customer name or plate.",
        ),
    ] = None,
    date_from: Annotated[
        QueryDate | None, Query(description="Shop-local date `YYYY-MM-DD`, inclusive.")
    ] = None,
    date_to: Annotated[
        QueryDate | None, Query(description="Shop-local date `YYYY-MM-DD`, inclusive.")
    ] = None,
    technician_user_id: Annotated[UUID | None, Query()] = None,
    parts_person_user_id: Annotated[UUID | None, Query()] = None,
) -> StaffBookingFilters:
    """The `GET …/bookings` filters; they narrow the caller's D21 set and never widen it."""
    return StaffBookingFilters(
        statuses=tuple(status or ()),
        q=q,
        date_from=date_from,
        date_to=date_to,
        technician_user_id=technician_user_id,
        parts_person_user_id=parts_person_user_id,
    )


@shop_router.get(
    "/bookings",
    summary="The shop's bookings the caller can see",
    description=(
        "Owner and Service Advisors see every booking of the shop, a technician or parts person "
        "the bookings assigned to them, QC inspectors the QC queue plus bookings they inspected "
        "(D21). Filters narrow that set. The QC queue is "
        "`?status=QC_PENDING&status=QC_IN_PROGRESS&sort=status_changed_at`."
    ),
    responses=problem_responses(401, 404, 422),
)
async def list_shop_bookings(
    ctx: ShopContextDep,
    session: DbSession,
    page: PageParamsDep,
    filters: Annotated[StaffBookingFilters, Depends(staff_booking_filters)],
    sort: Annotated[
        BookingSort,
        Query(
            description="`slot_start`, `updated_at`, `status_changed_at`, "
            "`created_at`; `-` = descending."
        ),
    ] = "-updated_at",
) -> Page[BookingSummary]:
    return await service.list_staff_bookings(session, ctx, filters=filters, sort=sort, page=page)


@shop_router.get(
    "/bookings/status-counts",
    summary="Booking counts by status",
    description="All 17 statuses in glossary order, zeros included, over the caller's D21 scope.",
    responses=problem_responses(401, 404),
)
async def get_status_counts(ctx: ShopContextDep, session: DbSession) -> StatusCountsRead:
    return await service.get_status_counts(session, ctx)


@shop_router.get(
    "/bookings/{booking_id}",
    summary="One booking",
    description=(
        "404 when the caller cannot see it (D21). The customer's e-mail and phone are shown to the "
        "Owner and Service Advisors only."
    ),
    responses=problem_responses(401, 404, 422),
)
async def get_shop_booking(
    booking_id: BookingIdPath, ctx: ShopContextDep, session: DbSession
) -> BookingDetail:
    return await service.get_staff_booking(session, ctx, booking_id=booking_id)


@shop_router.get(
    "/bookings/{booking_id}/events",
    summary="A booking's audit log",
    description="Every event, oldest first, with actor, role, note and metadata.",
    responses=problem_responses(401, 404, 422),
)
async def list_booking_events(
    booking_id: BookingIdPath, ctx: ShopContextDep, session: DbSession
) -> ItemList[BookingEventRead]:
    items = await service.list_booking_events(session, ctx, booking_id=booking_id)
    return ItemList[BookingEventRead](items=items)


@shop_router.get(
    "/bookings/{booking_id}/estimates",
    summary="A booking's estimate versions",
    description="Every version, ascending; part lines carry live stock, except for QC inspectors.",
    responses=problem_responses(401, 404, 422),
)
async def list_booking_estimates(
    booking_id: BookingIdPath, ctx: ShopContextDep, session: DbSession
) -> ItemList[EstimateRead]:
    items = await service.list_booking_estimates(session, ctx, booking_id=booking_id)
    return ItemList[EstimateRead](items=items)


@shop_router.put(
    "/bookings/{booking_id}/estimate",
    summary="Edit the estimate (`edit-estimate`)",
    description=(
        "Replaces the lines of the editable version (O1): the assigned technician while "
        "`INSPECTING` (also `inspection_notes`), the Service Advisor or Owner while "
        "`ESTIMATE_REVIEW`. Any other status → 409 `ESTIMATE_LOCKED`. The first desk edit of a "
        "submitted version creates a new version and one `EDIT_ESTIMATE` event; draft saves "
        "write no event and keep the booking `version`."
    ),
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def edit_estimate(
    booking_id: BookingIdPath, ctx: ShopContextDep, uow: UowDep, body: EstimateUpdate
) -> EstimateEditRead:
    return await service.edit_estimate(uow, ctx, booking_id=booking_id, body=body)


@shop_router.get(
    "/bookings/{booking_id}/parts",
    summary="A booking's parts: required, reserved and available",
    description="404 when not visible; 403 for QC inspectors (stock data).",
    responses=problem_responses(401, 403, 404, 422),
)
async def get_booking_parts(
    booking_id: BookingIdPath, ctx: ShopContextDep, session: DbSession
) -> BookingPartsRead:
    return await service.get_booking_parts(session, ctx, booking_id=booking_id)


@shop_router.get(
    "/bookings/{booking_id}/qc-inspections",
    summary="A booking's QC rounds",
    description="Every round with its checklist, notes and issues, oldest first.",
    responses=problem_responses(401, 404, 422),
)
async def list_booking_qc_inspections(
    booking_id: BookingIdPath, ctx: ShopContextDep, session: DbSession
) -> ItemList[QcInspectionRead]:
    items = await service.list_booking_qc_inspections(session, ctx, booking_id=booking_id)
    return ItemList[QcInspectionRead](items=items)


# --- Action routes, generated from spec 08's rule table (spec 03 §5) ------------------------------

_KEYWORD = inspect.Parameter.KEYWORD_ONLY


def _description(action: BookingAction) -> str:
    """Who may act, from which status, to which status — straight from `RULES`."""
    rule = RULES[action]
    sources = ", ".join(f"`{source}`" for source in sorted(rule.from_statuses))
    target = (
        "an operation (the status stays)" if rule.to_status is None else f"→ `{rule.to_status}`"
    )
    actors = ", ".join(sorted(rule.actors))
    guard = "" if rule.guard is None else f" Guard: `{rule.guard}`."
    return (
        f"From {sources}; {target}. Actors: {actors}.{guard} The body may carry "
        "`expected_version` (409 `CONCURRENT_UPDATE` on mismatch). Responds with the booking and "
        "the caller's fresh `allowed_actions`."
    )


def _body_parameter(model: type[ActionRequest]) -> inspect.Parameter:
    """The action's request body; optional (defaults to an empty body) without required fields."""
    annotation = Annotated[model, Body()]  # type: ignore[valid-type]
    if any(field.is_required() for field in model.model_fields.values()):
        return inspect.Parameter("body", _KEYWORD, annotation=annotation)
    return inspect.Parameter("body", _KEYWORD, annotation=annotation, default=model())


def _staff_action(action: BookingAction) -> Callable[..., Awaitable[BookingDetail]]:
    async def endpoint(
        *, booking_id: UUID, ctx: ShopContext, uow: UnitOfWork, body: ActionRequest
    ) -> BookingDetail:
        return await service.apply_staff_action(
            uow, ctx, booking_id=booking_id, action=action, payload=body
        )

    endpoint.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [
            inspect.Parameter("booking_id", _KEYWORD, annotation=BookingIdPath),
            inspect.Parameter("ctx", _KEYWORD, annotation=ShopContextDep),
            inspect.Parameter("uow", _KEYWORD, annotation=UowDep),
            _body_parameter(STAFF_ACTION_REQUESTS[action]),
        ]
    )
    return endpoint


def _customer_action(action: BookingAction) -> Callable[..., Awaitable[CustomerBookingDetail]]:
    async def endpoint(
        *, booking_id: UUID, user: CurrentUser, uow: UnitOfWork, body: ActionRequest
    ) -> CustomerBookingDetail:
        return await service.apply_customer_action(
            uow, user, booking_id=booking_id, action=action, payload=body
        )

    endpoint.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [
            inspect.Parameter("booking_id", _KEYWORD, annotation=BookingIdPath),
            inspect.Parameter("user", _KEYWORD, annotation=CurrentUserDep),
            inspect.Parameter("uow", _KEYWORD, annotation=UowDep),
            _body_parameter(CUSTOMER_ACTION_REQUESTS[action]),
        ]
    )
    return endpoint


def _route_name(slug: str) -> str:
    return slug.replace("-", "_")


def _add_action_routes() -> None:
    for action in staff_route_actions():
        slug = ACTION_TO_SLUG[action]
        shop_router.add_api_route(
            f"/bookings/{{booking_id}}/actions/{slug}",
            _staff_action(action),
            methods=["POST"],
            name=_route_name(slug),
            response_model=BookingDetail,
            summary=f"Booking action `{slug}`",
            description=_description(action),
            responses=problem_responses(401, 403, 404, 409, 422),
        )
    for action in customer_route_actions():
        slug = ACTION_TO_SLUG[action]
        me_router.add_api_route(
            f"/bookings/{{booking_id}}/actions/{slug}",
            _customer_action(action),
            methods=["POST"],
            name=f"my_{_route_name(slug)}",
            response_model=CustomerBookingDetail,
            summary=f"My booking action `{slug}`",
            description=_description(action),
            responses=_customer_problems(action),
        )


def _customer_problems(action: BookingAction) -> dict[int | str, dict[str, Any]]:
    """Every customer action but `cancel` is 403 `SHOP_SUSPENDED` while the shop is suspended
    (D96, spec 19 §2); `cancel` stays open, so it never answers 403."""
    if action is BookingAction.CANCEL:
        return problem_responses(401, 404, 409, 422)
    return problem_responses(401, 403, 404, 409, 422)


_add_action_routes()

routers: tuple[APIRouter, ...] = (wizard_router, me_router, shop_router)

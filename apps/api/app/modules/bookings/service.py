"""Use cases of the bookings module (`modules/bookings.md` §5; spec 08 "How an action is executed").

- **Top-level use cases** (each commits exactly once, D3): `create_booking` (T01, the wizard, D32),
  `apply_staff_action` and `apply_customer_action` (T02-T22, O2-O5), `edit_estimate` (O1).
- **Reads behind the routes:** the customer family (`list_customer_bookings`,
  `get_customer_booking`, `list_customer_booking_events`, `list_customer_estimates`,
  `list_my_vehicles`) and the staff family (`list_staff_bookings`, `get_status_counts`,
  `get_staff_booking`, `list_booking_events`, `list_booking_estimates`, `get_booking_parts`,
  `list_booking_qc_inspections`). Every staff read applies D21 first (not visible → 404).
- **Event-handler bodies** (called by `handlers.py` inside the publisher's transaction, never
  committing): `lock_booking_for_receipt`, `apply_purchase_order_receipt` (D43, D83),
  `veto_grid_change` (D37).
- **Reads for other modules** (signatures pinned before wave 2, §5.3): `BookingRefData`,
  `get_booking_refs`, `list_booking_viewer_ids`, `DayActivity`, `count_by_status`,
  `count_open_jobs`, `count_day_activity`, plus `has_future_bookings`, the D86 port object
  `shop_activity_reader` and `register_ports()` (D89).
- **Platform admin reads** (spec 19 §4, D94): `list_admin_bookings`, `get_admin_booking`,
  `platform_booking_stats`, `count_created_by_shop`. They are explicit, read-only and cross-tenant;
  they never widen the D21 predicate of the staff and customer reads, and carry no
  `allowed_actions`.

Shop suspension (D96, spec 19 §2): a customer's actions on a suspended shop's booking answer 403
`SHOP_SUSPENDED`, except `cancel`, and the customer's `allowed_actions` there hold `cancel` only;
staff never get this far (`require_shop_member`), and the wizard sees the shop as unlisted (404).

Every action locks the booking row first (key only), then reads the clock once (D63) and keeps
D30's lock order booking → purchase order → parts (ascending id) → slot counter through the
owning modules' nested services. Booking columns are changed only after the side effects have
run, together with the status, so no intermediate flush ever writes an impossible booking.
"""

import logging
from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Final
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from limits import RateLimitItem, parse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    AlreadyPicked,
    AppError,
    ConcurrentUpdate,
    Conflict,
    EmailAlreadyRegistered,
    EstimateLocked,
    FieldError,
    Forbidden,
    InternalError,
    InvalidCredentials,
    InvalidTransition,
    NotAssigned,
    NotFound,
    RateLimited,
    ShopSuspended,
    ValidationFailed,
)
from app.core.security import (
    ANONYMOUS_BOOKING_IP_LIMIT,
    AUTHENTICATED_BOOKING_LIMIT,
    account_limiter,
    retry_after_seconds,
)
from app.modules.bookings.domain.references import is_seed_reference, new_booking_reference
from app.modules.bookings.domain.state_machine import (
    RULES,
    ActorContext,
    Denial,
    Rule,
    TransitionDenied,
    allowed_actions,
    check,
    next_status,
)
from app.modules.bookings.domain.timeline import customer_note, is_customer_visible, routed
from app.modules.bookings.domain.vehicles import registration_key
from app.modules.bookings.domain.visibility import (
    QC_QUEUE_STATUSES,
    SHOP_WIDE_ROLES,
    can_view,
    needs_inspection_history,
)
from app.modules.bookings.events import BookingActionApplied, BookingPartsChanged
from app.modules.bookings.models import Booking, BookingEvent, BookingService, Vehicle
from app.modules.bookings.repository import (
    AdminListQuery,
    BookingEventRepository,
    BookingKey,
    BookingRepository,
    BookingRow,
    BookingServiceRepository,
    CustomerListQuery,
    SlotWindow,
    StaffListQuery,
    StaffScope,
    VehicleRepository,
    shop_condition,
    visibility_condition,
)
from app.modules.bookings.schemas import (
    CUSTOMER_ACTION_REQUESTS,
    STAFF_ACTION_REQUESTS,
    ActionRequest,
    AdminBookingDetail,
    AdminBookingFilters,
    AdminBookingSort,
    AdminBookingSummary,
    ApproveEstimateRequest,
    AssignPartsPersonRequest,
    AssignTechnicianRequest,
    BookingActionSlug,
    BookingCreate,
    BookingCreatedRead,
    BookingCustomer,
    BookingDetail,
    BookingDetailBase,
    BookingEventRead,
    BookingLabel,
    BookingServiceRead,
    BookingShopRead,
    BookingShopRef,
    BookingSort,
    BookingSummary,
    CancelRequest,
    ConfirmRequest,
    CustomerBookingDetail,
    CustomerBookingEventRead,
    CustomerBookingSort,
    CustomerBookingSummary,
    CustomerCancelRequest,
    CustomerWrite,
    DeclineRequest,
    FailQcRequest,
    OrderPartsRequest,
    PassQcRequest,
    ReassignPartsPersonRequest,
    ReassignTechnicianRequest,
    RejectEstimateRequest,
    ReturnToTechnicianRequest,
    SendToQcRequest,
    StaffBookingFilters,
    StatusCount,
    StatusCountsRead,
    SubmitEstimateRequest,
    VehicleBrief,
    VehicleRead,
    VehicleWrite,
)
from app.modules.estimates import service as estimates_service
from app.modules.estimates.schemas import (
    CustomerEstimateRead,
    EstimateEditRead,
    EstimateRead,
    EstimateSummary,
    EstimateUpdate,
)
from app.modules.identity import service as identity_service
from app.modules.identity.schemas import UserRecord, UserRef
from app.modules.inventory import service as inventory_service
from app.modules.inventory.domain.stock import PartQty
from app.modules.inventory.events import PurchaseOrderReceived
from app.modules.inventory.schemas import BookingPartsRead, PartsSummary
from app.modules.qc import service as qc_service
from app.modules.qc.schemas import QcInspectionRead, QcSummary
from app.modules.scheduling import service as scheduling_service
from app.modules.scheduling.domain.slots import GridSlot
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import MemberRef, ServiceSnapshot, ShopBrief
from app.shared.auth import CurrentUser, ShopContext
from app.shared.clock import utcnow
from app.shared.enums import ActorRole, BookingAction, BookingStatus, MembershipRole
from app.shared.orm import touch
from app.shared.pagination import Page, PageParams
from app.shared.repository import constraint_name
from app.shared.uow import UnitOfWork

logger = logging.getLogger(__name__)

BOOKING_IP_SCOPE: Final = "booking-ip"
"""Limiter key `("booking-ip", <client ip>)`: anonymous booking creation (D69)."""
BOOKING_USER_SCOPE: Final = "booking-user"
"""Limiter key `("booking-user", <user id>)`: booking creation with a session (D69)."""
ANONYMOUS_BOOKING_LIMIT: Final[RateLimitItem] = parse(ANONYMOUS_BOOKING_IP_LIMIT)

REFERENCE_ATTEMPTS: Final = 5
USERS_EMAIL_CONSTRAINT: Final = "uq_users_email"

ACCOUNT_EXISTS_DETAIL: Final = (
    "There's already a BayFlow account for this e-mail and the password didn't match. "
    "Log in to finish your booking."
)
ACCOUNT_TAKEN_DETAIL: Final = (
    "There's already a BayFlow account for this e-mail. Log in to finish your booking."
)
GRID_LOCKED: Final = (
    "This shop has upcoming bookings — slot duration and timezone can change when none are left."
)
QC_NO_STOCK: Final = "QC inspectors cannot see a booking's stock data."
NOTES_NOT_ALLOWED: Final = "Only the assigned technician writes inspection notes, while inspecting."
DATE_RANGE: Final = "date_from must not be later than date_to."


# =================================================================================================
# Reads for other modules (pinned signatures, `modules/bookings.md` §5.3) and the D86 ports
# =================================================================================================


@dataclass(frozen=True, slots=True)
class BookingRefData:
    """A booking's identity and state as other modules show it (D86; inventory's `BookingRef`)."""

    id: UUID
    reference: str
    status: BookingStatus
    version: int


async def get_booking_refs(
    session: AsyncSession, *, shop_id: UUID, booking_ids: Collection[UUID]
) -> dict[UUID, BookingRefData]:
    """`BookingRefData` for each id that is a booking of `shop_id` (ids of other shops are absent).

    One query, on the caller's session (so it sees the current transaction's writes). The values
    are fresh, immutable snapshots of plain columns, never live ORM rows.
    """
    if not booking_ids:
        return {}
    rows = await BookingRepository(session).refs(shop_id=shop_id, booking_ids=booking_ids)
    return {
        row.id: BookingRefData(
            id=row.id, reference=row.reference, status=row.status, version=row.version
        )
        for row in rows
    }


async def list_booking_viewer_ids(session: AsyncSession, *, booking_id: UUID) -> list[UUID]:
    """Users who may see the booking now (D21 at push time, active memberships only; §7.11).

    The customer, the shop's active SAs and Owner, its technician and parts person while still
    active members, and active QC inspectors while it is `QC_PENDING` / `QC_IN_PROGRESS` or when
    they inspected it. Unknown booking → `[]`.

    Each active member is judged by `domain.visibility.can_view` with the role they hold now, so
    a former assignee (after `reassign-*`), a deactivated member, a QC inspector who never touched
    the booking outside the queue and members of other shops receive nothing (NOT-12).
    """
    booking = await BookingRepository(session).get_unscoped(booking_id)
    if booking is None:
        return []
    viewers = {booking.customer_user_id}
    active = await shops_service.list_active_member_ids(
        session, shop_id=booking.shop_id, roles=tuple(MembershipRole)
    )
    if not active:
        return sorted(viewers)
    team = await shops_service.list_team(session, shop_id=booking.shop_id)
    roles = {member.user_id: member.role for member in team if member.is_active}
    inspectors: Collection[UUID] = frozenset()
    if booking.status not in QC_QUEUE_STATUSES and any(
        roles.get(user_id) == MembershipRole.QC_INSPECTOR for user_id in active
    ):
        inspectors = await qc_service.list_inspector_ids(
            session, shop_id=booking.shop_id, booking_id=booking.id
        )
    for user_id in active:
        role = roles.get(user_id)
        if role is not None and can_view(
            role,
            is_technician=booking.technician_user_id == user_id,
            is_parts_person=booking.parts_person_user_id == user_id,
            status=booking.status,
            has_inspected=user_id in inspectors,
        ):
            viewers.add(user_id)
    return sorted(viewers)


@dataclass(frozen=True, slots=True)
class DayActivity:
    """A shop's activity in one shop-local day (reporting's "today" figures)."""

    bookings: int  # non-cancelled bookings whose slot_start is in [start, end)
    completed: int  # bookings whose completed_at is in [start, end)


async def count_by_status(session: AsyncSession, *, shop_id: UUID) -> dict[BookingStatus, int]:
    """Every booking of the shop counted by status; all 17 statuses are keys, zeros included."""
    counts = await BookingRepository(session).status_counts(condition=shop_condition(shop_id))
    return {status: counts.get(status, 0) for status in BookingStatus}


async def count_open_jobs(
    session: AsyncSession, *, shop_id: UUID, user_ids: Collection[UUID]
) -> dict[UUID, int]:
    """Distinct bookings not `READY_FOR_PICKUP` / `COMPLETED` / `CANCELLED` where the user is the
    technician, the parts person or the current QC picker; every requested id is a key (zeros
    included). One query whatever the number of users."""
    ids = list(dict.fromkeys(user_ids))
    if not ids:
        return {}
    counts = await BookingRepository(session).open_job_counts(shop_id=shop_id, user_ids=ids)
    return {user_id: counts.get(user_id, 0) for user_id in ids}


async def count_day_activity(
    session: AsyncSession, *, shop_id: UUID, start: datetime, end: datetime
) -> DayActivity:
    """Counts over the half-open UTC window `[start, end)` of one shop-local day, computed by the
    caller (`ix_bookings_shop_id_slot_start`)."""
    bookings, completed = await BookingRepository(session).day_activity(
        shop_id=shop_id, start=start, end=end
    )
    return DayActivity(bookings=bookings, completed=completed)


async def has_future_bookings(session: AsyncSession, *, shop_id: UUID, now: datetime) -> bool:
    """A booking of the shop with `slot_start > now` that is not `CANCELLED` (D37). A booking whose
    slot already started is not "future" and never blocks a grid change."""
    return await BookingRepository(session).has_future(shop_id=shop_id, now=now)


class _ShopActivityReader:
    """Shops' D86 `ShopActivityReader` port (`ShopRead.has_future_bookings`,
    `MemberRead.open_jobs`), implemented with this module's reads."""

    async def has_future_bookings(
        self, session: AsyncSession, *, shop_id: UUID, now: datetime
    ) -> bool:
        return await has_future_bookings(session, shop_id=shop_id, now=now)

    async def count_open_jobs(
        self, session: AsyncSession, *, shop_id: UUID, user_ids: Collection[UUID]
    ) -> Mapping[UUID, int]:
        return await count_open_jobs(session, shop_id=shop_id, user_ids=user_ids)


shop_activity_reader = _ShopActivityReader()
"""The object `register_ports()` hands to `shops.service.register_activity_reader` (D86)."""


def register_ports() -> None:
    """Register this module's read-port implementations in the lower modules (D86), called by
    `app.main.wire_modules()` at start-up, in tests and in the seed (D89)."""
    shops_service.register_activity_reader(shop_activity_reader)
    inventory_service.register_booking_ref_reader(get_booking_refs)


# =================================================================================================
# Shared pieces of every action
# =================================================================================================


@dataclass(frozen=True, slots=True)
class _By:
    """Who performs an action (as the event row records it) and the action's single clock instant,
    read once right after the booking lock (D63)."""

    user_id: UUID
    role: ActorRole
    now: datetime


@dataclass(frozen=True, slots=True)
class _Effect:
    """What an action's side effects contribute to its event row (spec 08 metadata examples)."""

    note: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _actor_context(role: ActorRole, user_id: UUID, booking: Booking) -> ActorContext:
    """The caller relative to one booking (spec 08 "Who is the actor?"; ADR of state_machine)."""
    return ActorContext(
        role=role,
        is_assigned_technician=booking.technician_user_id == user_id,
        is_assigned_parts_person=booking.parts_person_user_id == user_id,
        is_qc_picker=booking.qc_inspector_user_id == user_id,
        is_booking_customer=booking.customer_user_id == user_id,
        is_booking_technician=booking.technician_user_id == user_id,
    )


def _staff_role(ctx: ShopContext) -> ActorRole:
    return ActorRole(ctx.role.value)


def _slugs(booking: Booking, actor: ActorContext) -> list[BookingActionSlug]:
    """`allowed_actions` for this caller and endpoint family (§7.8): the domain's list, in
    glossary order, without slugs whose route does not exist yet."""
    return [BookingActionSlug(slug) for slug in routed(allowed_actions(booking.status, actor))]


def _staff_slugs(ctx: ShopContext, booking: Booking) -> list[BookingActionSlug]:
    return _slugs(booking, _actor_context(_staff_role(ctx), ctx.user.id, booking))


def _customer_slugs(
    customer_id: UUID, booking: Booking, *, shop_suspended: bool = False
) -> list[BookingActionSlug]:
    """The customer's `allowed_actions`; at a suspended shop only `cancel` stays open (D96)."""
    slugs = _slugs(booking, _actor_context(ActorRole.CUSTOMER, customer_id, booking))
    if shop_suspended:
        return [slug for slug in slugs if slug == BookingActionSlug.CANCEL]
    return slugs


async def _picker_detail(session: AsyncSession, booking: Booking) -> str:
    """`ALREADY_PICKED` names who is inspecting (spec 03 §5.2 `pick-qc`)."""
    picker_id = booking.qc_inspector_user_id
    picker = await identity_service.get_user(session, picker_id) if picker_id else None
    if picker is None:
        return "Another QC inspector has already picked this job."
    return f"Already picked by {picker.full_name}."


async def _denial_error(
    session: AsyncSession, denied: TransitionDenied, booking: Booking
) -> AppError:
    """The domain's refusal as the API error with the same code (spec 08 "Error mapping")."""
    if denied.code is Denial.FORBIDDEN:
        return Forbidden(denied.message)
    if denied.code is Denial.NOT_ASSIGNED:
        return NotAssigned(denied.message)
    if denied.code is Denial.ALREADY_PICKED:
        return AlreadyPicked(await _picker_detail(session, booking))
    return InvalidTransition(denied.message)


async def _checked_rule(
    session: AsyncSession, action: BookingAction, booking: Booking, actor: ActorContext
) -> Rule:
    """Spec 08 steps 5-7 on the locked row: role → assignment → status."""
    try:
        return check(action, booking.status, actor)
    except TransitionDenied as denied:
        raise await _denial_error(session, denied, booking) from None


def _check_version(expected: int | None, booking: Booking) -> None:
    """Spec 08 step 8 (D30): checked after the status, so a double click reads 409
    `INVALID_TRANSITION` / `ALREADY_PICKED` rather than `CONCURRENT_UPDATE` (spec 03 §7.5)."""
    if expected is not None and expected != booking.version:
        raise ConcurrentUpdate(
            f"The booking was changed by someone else (it is now at version {booking.version}). "
            "Reload and try again."
        )


async def _staff_can_view(session: AsyncSession, ctx: ShopContext, booking: Booking) -> bool:
    """D21 for one booking of the caller's shop; a QC inspector outside the queue costs one read
    of the booking's QC history."""
    has_inspected = False
    if needs_inspection_history(ctx.role, booking.status):
        has_inspected = await qc_service.has_inspected(
            session, shop_id=ctx.shop_id, booking_id=booking.id, inspector_user_id=ctx.user.id
        )
    return can_view(
        ctx.role,
        is_technician=booking.technician_user_id == ctx.user.id,
        is_parts_person=booking.parts_person_user_id == ctx.user.id,
        status=booking.status,
        has_inspected=has_inspected,
    )


async def _locked_staff_booking(uow: UnitOfWork, ctx: ShopContext, booking_id: UUID) -> Booking:
    """Spec 08 steps 3-4: lock by key (`id` + `shop_id`), then D21 on the locked row. Not found
    and not visible are the same 404."""
    booking = await BookingRepository(uow.session).get_for_update(
        shop_id=ctx.shop_id, booking_id=booking_id
    )
    if booking is None:
        raise NotFound
    return booking


async def _write_event(
    uow: UnitOfWork,
    booking: Booking,
    *,
    action: BookingAction,
    from_status: BookingStatus | None,
    by: _By,
    effect: _Effect,
) -> None:
    """Spec 08 steps 12-13: one `booking_events` row, then `BookingActionApplied` with the values
    after the action (`modules/bookings.md` §8). The booking's columns are already updated."""
    uow.session.add(
        BookingEvent(
            shop_id=booking.shop_id,
            booking_id=booking.id,
            action=action,
            from_status=from_status,
            to_status=booking.status,
            actor_user_id=by.user_id,
            actor_role=by.role,
            note=effect.note,
            metadata_=deepcopy(effect.metadata),
            created_at=by.now,
        )
    )
    await uow.session.flush()
    await uow.publish(
        BookingActionApplied(
            occurred_at=by.now,
            shop_id=booking.shop_id,
            booking_id=booking.id,
            reference=booking.reference,
            action=action,
            from_status=from_status,
            to_status=booking.status,
            version=booking.version,
            actor_user_id=by.user_id,
            actor_role=by.role,
            customer_user_id=booking.customer_user_id,
            technician_user_id=booking.technician_user_id,
            parts_person_user_id=booking.parts_person_user_id,
            qc_inspector_user_id=booking.qc_inspector_user_id,
            note=effect.note,
            metadata=deepcopy(effect.metadata),
        )
    )


async def _record(
    uow: UnitOfWork,
    booking: Booking,
    *,
    rule: Rule,
    by: _By,
    effect: _Effect,
) -> None:
    """Spec 08 steps 11-13: new status (an operation keeps it), `version += 1`, `updated_at`,
    the event row and the published event."""
    from_status = booking.status
    booking.status = next_status(rule, from_status)
    booking.version += 1
    touch(booking, by.now)
    await _write_event(
        uow, booking, action=rule.action, from_status=from_status, by=by, effect=effect
    )


# =================================================================================================
# The action executor (spec 08 "How an action is executed", `modules/bookings.md` §7.4, §7.6)
# =================================================================================================


@dataclass(frozen=True, slots=True)
class _Step:
    """One action in progress, after its checks: what the side effects need."""

    uow: UnitOfWork
    booking: Booking
    by: _By
    payload: ActionRequest

    @property
    def session(self) -> AsyncSession:
        return self.uow.session

    @property
    def now(self) -> datetime:
        return self.by.now

    @property
    def actor_id(self) -> UUID:
        return self.by.user_id


def _body[R: ActionRequest](step: _Step, kind: type[R]) -> R:
    """The payload as the action's request type (checked at the use case's entry)."""
    if not isinstance(step.payload, kind):
        msg = f"expected {kind.__name__}, got {type(step.payload).__name__}"
        raise TypeError(msg)
    return step.payload


def _quantities(items: Iterable[PartQty]) -> list[dict[str, str | int]]:
    """`[{part_id, qty}]` for event metadata (spec 08)."""
    return [item.as_json() for item in items]


def _cancel_columns(step: _Step, reason: str | None) -> None:
    """`DECLINE` / `CANCEL`: who and why (D24); written with the `CANCELLED` status."""
    step.booking.cancelled_at = step.now
    step.booking.cancelled_by_user_id = step.actor_id
    step.booking.cancel_reason = reason


async def _confirm(step: _Step) -> _Effect:
    """T02: status only; the note is staff-only."""
    return _Effect(note=_body(step, ConfirmRequest).note)


async def _decline(step: _Step) -> _Effect:
    """T03: free the slot (booking → slot counter), record who and why."""
    body = _body(step, DeclineRequest)
    booking = step.booking
    await scheduling_service.release_slot(
        step.uow, shop_id=booking.shop_id, slot_start=booking.slot_start, now=step.now
    )
    _cancel_columns(step, body.reason)
    return _Effect(note=body.reason)


async def _assign_technician(step: _Step) -> _Effect:
    """T04: an active `TECHNICIAN` member of this shop (422 `MEMBER_NOT_ELIGIBLE`)."""
    body = _body(step, AssignTechnicianRequest)
    member = await shops_service.require_eligible_member(
        step.session,
        shop_id=step.booking.shop_id,
        user_id=body.technician_user_id,
        role=MembershipRole.TECHNICIAN,
        field="technician_user_id",
    )
    step.booking.technician_user_id = member.user_id
    return _Effect(metadata={"technician_user_id": str(member.user_id)})


async def _start_inspection(step: _Step) -> _Effect:
    """T05: `DRAFT` v1 authored by the technician, unless the booking already has one."""
    snapshot = await estimates_service.ensure_draft(
        step.uow,
        shop_id=step.booking.shop_id,
        booking_id=step.booking.id,
        created_by_user_id=step.actor_id,
        now=step.now,
    )
    return _Effect(metadata=snapshot.event_ref())


async def _submit_estimate(step: _Step) -> _Effect:
    """T06: the draft → `SUBMITTED` (422 `ESTIMATE_EMPTY`); sent notes replace the booking's."""
    body = _body(step, SubmitEstimateRequest)
    snapshot = await estimates_service.submit(
        step.uow, shop_id=step.booking.shop_id, booking_id=step.booking.id, now=step.now
    )
    if body.inspection_notes is not None:
        step.booking.inspection_notes = body.inspection_notes
    return _Effect(metadata=snapshot.event_metadata())


async def _send_estimate(step: _Step) -> _Effect:
    """T07: the open version → `SENT` by the SA or Owner (422 `ESTIMATE_EMPTY`)."""
    snapshot = await estimates_service.send(
        step.uow,
        shop_id=step.booking.shop_id,
        booking_id=step.booking.id,
        sent_by_user_id=step.actor_id,
        now=step.now,
    )
    return _Effect(metadata=snapshot.event_metadata())


async def _approve_estimate(step: _Step) -> _Effect:
    """T08: the current `SENT` version → `APPROVED` (409 `STALE_ESTIMATE` otherwise)."""
    body = _body(step, ApproveEstimateRequest)
    snapshot = await estimates_service.approve(
        step.uow,
        shop_id=step.booking.shop_id,
        booking_id=step.booking.id,
        estimate_id=body.estimate_id,
        decided_by_user_id=step.actor_id,
        now=step.now,
    )
    return _Effect(metadata=snapshot.event_metadata())


async def _reject_estimate(step: _Step) -> _Effect:
    """T09: the current `SENT` version → `REJECTED`; the reason is the event note."""
    body = _body(step, RejectEstimateRequest)
    snapshot = await estimates_service.reject(
        step.uow,
        shop_id=step.booking.shop_id,
        booking_id=step.booking.id,
        estimate_id=body.estimate_id,
        decided_by_user_id=step.actor_id,
        reason=body.reason,
        now=step.now,
    )
    return _Effect(note=body.reason, metadata=snapshot.event_metadata())


async def _revise_estimate(step: _Step) -> _Effect:
    """T10: the rejected version copied into `DRAFT` v+1 authored by the SA or Owner."""
    snapshot = await estimates_service.copy_rejected_to_draft(
        step.uow,
        shop_id=step.booking.shop_id,
        booking_id=step.booking.id,
        created_by_user_id=step.actor_id,
        now=step.now,
    )
    return _Effect(metadata=snapshot.event_ref())


async def _return_to_technician(step: _Step) -> _Effect:
    """T11: the same copy, for the technician to edit while `INSPECTING`; the note is theirs."""
    body = _body(step, ReturnToTechnicianRequest)
    snapshot = await estimates_service.copy_rejected_to_draft(
        step.uow,
        shop_id=step.booking.shop_id,
        booking_id=step.booking.id,
        created_by_user_id=step.actor_id,
        now=step.now,
    )
    return _Effect(note=body.note, metadata=snapshot.event_ref())


async def _assign_parts_person(step: _Step) -> _Effect:
    """T12: an eligible parts person; `booking_parts` from the approved version (none for a
    labour-only job, D31)."""
    body = _body(step, AssignPartsPersonRequest)
    booking = step.booking
    member = await shops_service.require_eligible_member(
        step.session,
        shop_id=booking.shop_id,
        user_id=body.parts_person_user_id,
        role=MembershipRole.PARTS_PERSON,
        field="parts_person_user_id",
    )
    requirements = await estimates_service.get_approved_part_requirements(
        step.session, shop_id=booking.shop_id, booking_id=booking.id
    )
    await inventory_service.create_booking_parts(
        step.uow,
        shop_id=booking.shop_id,
        booking_id=booking.id,
        requirements=requirements,
        now=step.now,
    )
    booking.parts_person_user_id = member.user_id
    return _Effect(
        metadata={
            "parts_person_user_id": str(member.user_id),
            "required": _quantities(requirements),
        }
    )


async def _order_parts(step: _Step) -> _Effect:
    """T13: reserve what is available, order the shortages on a PO linked to the booking."""
    body = _body(step, OrderPartsRequest)
    items = None if body.items is None else [PartQty(i.part_id, i.quantity) for i in body.items]
    result = await inventory_service.order_missing_parts(
        step.uow,
        shop_id=step.booking.shop_id,
        booking_id=step.booking.id,
        actor_user_id=step.actor_id,
        items=items,
        supplier_name=body.supplier_name,
        now=step.now,
    )
    return _Effect(
        metadata={
            "purchase_order_id": str(result.purchase_order_id),
            "po_number": result.po_number,
            "reserved": _quantities(result.reserved),
        }
    )


async def _mark_parts_ready(step: _Step) -> _Effect:
    """T14: reserve every outstanding quantity, all or nothing (409 `INSUFFICIENT_STOCK`)."""
    reserved = await inventory_service.reserve_outstanding(
        step.uow,
        shop_id=step.booking.shop_id,
        booking_id=step.booking.id,
        actor_user_id=step.actor_id,
        now=step.now,
    )
    return _Effect(metadata={"reserved": _quantities(reserved)})


async def _allocate_parts(step: _Step) -> _Effect:
    """T16: consume the reservations (409 `INSUFFICIENT_STOCK` while any is incomplete)."""
    consumed = await inventory_service.consume_reservations(
        step.uow,
        shop_id=step.booking.shop_id,
        booking_id=step.booking.id,
        actor_user_id=step.actor_id,
        now=step.now,
    )
    return _Effect(metadata={"consumed": _quantities(consumed)})


async def _start_repair(step: _Step) -> _Effect:
    """O2: each repair round overwrites `repair_started_at`; the events keep every round."""
    step.booking.repair_started_at = step.now
    return _Effect()


async def _send_to_qc(step: _Step) -> _Effect:
    """T17: open QC issues → `RESOLVED` by the technician; the picker is cleared (D47)."""
    body = _body(step, SendToQcRequest)
    resolved = await qc_service.resolve_open_issues(
        step.uow,
        shop_id=step.booking.shop_id,
        booking_id=step.booking.id,
        resolved_by_user_id=step.actor_id,
        now=step.now,
    )
    step.booking.qc_inspector_user_id = None
    return _Effect(
        note=body.repair_notes,
        metadata={"resolved_qc_issue_ids": [str(issue_id) for issue_id in resolved]},
    )


async def _pick_qc(step: _Step) -> _Effect:
    """T18: a new QC round picked by the caller (never the booking's technician, D47)."""
    booking = step.booking
    inspection_id = await qc_service.open_inspection(
        step.uow,
        shop_id=booking.shop_id,
        booking_id=booking.id,
        inspector_user_id=step.actor_id,
        now=step.now,
        booking_technician_user_id=booking.technician_user_id,
    )
    booking.qc_inspector_user_id = step.actor_id
    return _Effect(metadata={"qc_inspection_id": str(inspection_id)})


async def _pass_qc(step: _Step) -> _Effect:
    """T19: the round passes with the full checklist; the picker is kept (D47)."""
    body = _body(step, PassQcRequest)
    inspection_id = await qc_service.record_pass(
        step.uow,
        shop_id=step.booking.shop_id,
        booking_id=step.booking.id,
        inspector_user_id=step.actor_id,
        checklist=body.checklist,
        notes=body.notes,
        now=step.now,
    )
    return _Effect(metadata={"qc_inspection_id": str(inspection_id)})


async def _fail_qc(step: _Step) -> _Effect:
    """T20: the round fails with an `OPEN` issue; back to the same technician, picker cleared
    (D47); the event note is the issue title (D92)."""
    body = _body(step, FailQcRequest)
    recorded = await qc_service.record_fail(
        step.uow,
        shop_id=step.booking.shop_id,
        booking_id=step.booking.id,
        inspector_user_id=step.actor_id,
        issue_title=body.issue_title,
        issue_description=body.issue_description,
        checklist=body.checklist,
        notes=body.notes,
        now=step.now,
    )
    step.booking.qc_inspector_user_id = None
    return _Effect(
        note=body.issue_title,
        metadata={
            "qc_inspection_id": str(recorded.qc_inspection_id),
            "qc_issue_id": str(recorded.qc_issue_id),
        },
    )


async def _notify_ready(step: _Step) -> _Effect:
    """O3: repeatable; each call sets `ready_notified_at` (D27)."""
    step.booking.ready_notified_at = step.now
    return _Effect()


async def _complete(step: _Step) -> _Effect:
    """T21: by the SA, the Owner or the booking's customer (D28)."""
    step.booking.completed_at = step.now
    return _Effect()


async def _cancel(step: _Step) -> _Effect:
    """T22 (D24): release the reservations (parts ascending), free the slot, supersede open
    estimate versions; linked purchase orders stay open."""
    payload = step.payload
    if not isinstance(payload, CancelRequest | CustomerCancelRequest):
        msg = f"cancel expects a cancel request, got {type(payload).__name__}"
        raise TypeError(msg)
    booking = step.booking
    released = await inventory_service.release_reservations(
        step.uow,
        shop_id=booking.shop_id,
        booking_id=booking.id,
        actor_user_id=step.actor_id,
        now=step.now,
    )
    await scheduling_service.release_slot(
        step.uow, shop_id=booking.shop_id, slot_start=booking.slot_start, now=step.now
    )
    await estimates_service.supersede_open_versions(
        step.uow, shop_id=booking.shop_id, booking_id=booking.id, now=step.now
    )
    _cancel_columns(step, payload.reason)
    return _Effect(note=payload.reason, metadata={"released": _quantities(released)})


async def _eligible_new_assignee(
    step: _Step, *, user_id: UUID, role: MembershipRole, current: UUID | None, field_name: str
) -> UUID:
    """O4/O5: eligible (422 `MEMBER_NOT_ELIGIBLE`), then different from the current assignee
    (422 `unchanged`)."""
    member = await shops_service.require_eligible_member(
        step.session, shop_id=step.booking.shop_id, user_id=user_id, role=role, field=field_name
    )
    if member.user_id == current:
        raise ValidationFailed(
            errors=[
                FieldError(
                    field=field_name,
                    code="unchanged",
                    message="This person is already assigned; choose someone else.",
                )
            ]
        )
    return member.user_id


async def _reassign_technician(step: _Step) -> _Effect:
    """O4: the draft estimate stays; the previous technician loses visibility."""
    body = _body(step, ReassignTechnicianRequest)
    previous = step.booking.technician_user_id
    new_id = await _eligible_new_assignee(
        step,
        user_id=body.technician_user_id,
        role=MembershipRole.TECHNICIAN,
        current=previous,
        field_name="technician_user_id",
    )
    step.booking.technician_user_id = new_id
    return _Effect(
        metadata={
            "technician_user_id": str(new_id),
            "previous_technician_user_id": None if previous is None else str(previous),
        }
    )


async def _reassign_parts_person(step: _Step) -> _Effect:
    """O5: reservations and linked purchase orders are unchanged."""
    body = _body(step, ReassignPartsPersonRequest)
    previous = step.booking.parts_person_user_id
    new_id = await _eligible_new_assignee(
        step,
        user_id=body.parts_person_user_id,
        role=MembershipRole.PARTS_PERSON,
        current=previous,
        field_name="parts_person_user_id",
    )
    step.booking.parts_person_user_id = new_id
    return _Effect(
        metadata={
            "parts_person_user_id": str(new_id),
            "previous_parts_person_user_id": None if previous is None else str(previous),
        }
    )


type _EffectFn = Callable[[_Step], Awaitable[_Effect]]

_EFFECTS: Final[Mapping[BookingAction, _EffectFn]] = {
    BookingAction.CONFIRM: _confirm,
    BookingAction.DECLINE: _decline,
    BookingAction.ASSIGN_TECHNICIAN: _assign_technician,
    BookingAction.START_INSPECTION: _start_inspection,
    BookingAction.SUBMIT_ESTIMATE: _submit_estimate,
    BookingAction.SEND_ESTIMATE: _send_estimate,
    BookingAction.APPROVE_ESTIMATE: _approve_estimate,
    BookingAction.REJECT_ESTIMATE: _reject_estimate,
    BookingAction.REVISE_ESTIMATE: _revise_estimate,
    BookingAction.RETURN_TO_TECHNICIAN: _return_to_technician,
    BookingAction.ASSIGN_PARTS_PERSON: _assign_parts_person,
    BookingAction.ORDER_PARTS: _order_parts,
    BookingAction.MARK_PARTS_READY: _mark_parts_ready,
    BookingAction.ALLOCATE_PARTS: _allocate_parts,
    BookingAction.START_REPAIR: _start_repair,
    BookingAction.SEND_TO_QC: _send_to_qc,
    BookingAction.PICK_QC: _pick_qc,
    BookingAction.PASS_QC: _pass_qc,
    BookingAction.FAIL_QC: _fail_qc,
    BookingAction.NOTIFY_READY: _notify_ready,
    BookingAction.COMPLETE: _complete,
    BookingAction.CANCEL: _cancel,
    BookingAction.REASSIGN_TECHNICIAN: _reassign_technician,
    BookingAction.REASSIGN_PARTS_PERSON: _reassign_parts_person,
}
"""Step 9-10 of every action routed through `/actions/{slug}` (spec 08 T02-T22, O2-O5)."""


def _expect_payload(
    requests: Mapping[BookingAction, type[ActionRequest]],
    action: BookingAction,
    payload: ActionRequest,
    family: str,
) -> None:
    """A programming error (never reachable over HTTP) when the action has no route in this
    family or the payload is not its request type: `CREATE`, `RECEIVE_PARTS` and
    `EDIT_ESTIMATE` have their own use cases."""
    expected = requests.get(action)
    if expected is None:
        msg = f"{action} is not a {family} booking action"
        raise ValueError(msg)
    if type(payload) is not expected:
        msg = f"{action} expects {expected.__name__}, got {type(payload).__name__}"
        raise TypeError(msg)


async def _execute(
    uow: UnitOfWork,
    booking: Booking,
    *,
    action: BookingAction,
    context: ActorContext,
    by: _By,
    payload: ActionRequest,
) -> None:
    """Spec 08 steps 5-13 on the locked booking."""
    rule = await _checked_rule(uow.session, action, booking, context)
    _check_version(payload.expected_version, booking)
    effect = await _EFFECTS[action](_Step(uow, booking, by, payload))
    await _record(uow, booking, rule=rule, by=by, effect=effect)


async def apply_staff_action(
    uow: UnitOfWork,
    ctx: ShopContext,
    *,
    booking_id: UUID,
    action: BookingAction,
    payload: ActionRequest,
) -> BookingDetail:
    """`POST /api/v1/shops/{shop_id}/bookings/{booking_id}/actions/{slug}` (one transaction).

    Lock by `id` + `shop_id` → `now` → D21 (404) → role (403 `FORBIDDEN`) → assignment (403
    `NOT_ASSIGNED`) → status (409) → `expected_version` (409 `CONCURRENT_UPDATE`) → data guards
    and side effects → booking, event, `BookingActionApplied` → commit → the detail re-read with
    the caller's fresh `allowed_actions` and this action's event as `last_event`.
    """
    _expect_payload(STAFF_ACTION_REQUESTS, action, payload, "staff")
    booking = await _locked_staff_booking(uow, ctx, booking_id)
    now = utcnow()
    if not await _staff_can_view(uow.session, ctx, booking):
        raise NotFound
    role = _staff_role(ctx)
    await _execute(
        uow,
        booking,
        action=action,
        context=_actor_context(role, ctx.user.id, booking),
        by=_By(ctx.user.id, role, now),
        payload=payload,
    )
    await uow.commit()
    return await _staff_detail(uow.session, ctx, booking.id)


async def apply_customer_action(
    uow: UnitOfWork,
    customer: CurrentUser,
    *,
    booking_id: UUID,
    action: BookingAction,
    payload: ActionRequest,
) -> CustomerBookingDetail:
    """`POST /api/v1/me/bookings/{booking_id}/actions/{slug}` (one transaction): the booking is
    locked by `id` + `customer_user_id` (anything else is 404, even for staff of that shop)."""
    _expect_payload(CUSTOMER_ACTION_REQUESTS, action, payload, "customer")
    booking = await BookingRepository(uow.session).get_for_update_customer(
        customer_user_id=customer.id, booking_id=booking_id
    )
    if booking is None:
        raise NotFound
    # D96, spec 19 §2: a suspended shop's bookings stay readable, and `cancel` stays open so a
    # customer is never stuck with a booking at a closed shop; every other action is refused.
    if action != BookingAction.CANCEL:
        suspension = await shops_service.get_shop_suspension(uow.session, shop_id=booking.shop_id)
        if suspension is not None:
            raise ShopSuspended
    now = utcnow()
    await _execute(
        uow,
        booking,
        action=action,
        context=_actor_context(ActorRole.CUSTOMER, customer.id, booking),
        by=_By(customer.id, ActorRole.CUSTOMER, now),
        payload=payload,
    )
    await uow.commit()
    return await _customer_detail(uow.session, customer.id, booking.id)


async def _edit_rule(session: AsyncSession, booking: Booking, actor: ActorContext) -> Rule:
    """O1's rule check: the domain's `INVALID_TRANSITION` is 409 `ESTIMATE_LOCKED` here, never
    403 (EST-11, §7.6.1)."""
    try:
        return check(BookingAction.EDIT_ESTIMATE, booking.status, actor)
    except TransitionDenied as denied:
        if denied.code is Denial.INVALID_TRANSITION:
            raise EstimateLocked(
                f"The estimate cannot be edited by you while the booking is {booking.status}."
            ) from None
        raise await _denial_error(session, denied, booking) from None


async def edit_estimate(
    uow: UnitOfWork, ctx: ShopContext, *, booking_id: UUID, body: EstimateUpdate
) -> EstimateEditRead:
    """`PUT …/bookings/{booking_id}/estimate` (O1, §7.6.1; one transaction).

    The assigned technician edits while `INSPECTING`, the SA or Owner while `ESTIMATE_REVIEW`.
    A plain draft save writes no event and keeps `version` (last write wins, D30); the first desk
    edit of a `SUBMITTED` version creates `DRAFT` v+1 and one `EDIT_ESTIMATE` event (D39).
    """
    session = uow.session
    booking = await _locked_staff_booking(uow, ctx, booking_id)
    now = utcnow()
    if not await _staff_can_view(session, ctx, booking):
        raise NotFound
    role = _staff_role(ctx)
    rule = await _edit_rule(session, booking, _actor_context(role, ctx.user.id, booking))
    _check_version(body.expected_version, booking)
    if body.inspection_notes is not None and ctx.role != MembershipRole.TECHNICIAN:
        raise ValidationFailed(
            errors=[
                FieldError(field="inspection_notes", code="not_allowed", message=NOTES_NOT_ALLOWED)
            ]
        )
    edit = await estimates_service.replace_lines(
        uow,
        shop_id=booking.shop_id,
        booking_id=booking.id,
        booking_status=booking.status,
        actor_user_id=ctx.user.id,
        lines=body.lines,
        now=now,
    )
    if body.inspection_notes is not None and booking.inspection_notes != body.inspection_notes:
        booking.inspection_notes = body.inspection_notes
        touch(booking, now)
    if edit.created_new_version:
        effect = _Effect(metadata=edit.event_metadata())
        await _record(uow, booking, rule=rule, by=_By(ctx.user.id, role, now), effect=effect)
    await uow.commit()
    return EstimateEditRead.from_edit(edit, booking_version=booking.version)


# =================================================================================================
# Purchase-order receipts (D43, D83) and the grid veto (D37): bodies of the event handlers
# =================================================================================================


async def lock_booking_for_receipt(uow: UnitOfWork, *, shop_id: UUID, booking_id: UUID) -> None:
    """`PurchaseOrderReceiving`: lock the linked booking before inventory locks the purchase
    order and the parts, so the receipt keeps D30's order booking → PO → parts (§7.7)."""
    await BookingRepository(uow.session).get_for_update(shop_id=shop_id, booking_id=booking_id)


async def apply_purchase_order_receipt(uow: UnitOfWork, event: PurchaseOrderReceived) -> None:
    """`PurchaseOrderReceived` (§7.7): while the linked booking is `PARTS_ORDERED`, reserve the
    received stock for it; when every booking part is then fully reserved apply `RECEIVE_PARTS`
    (T15, by the receiving Parts Person, at the receipt's instant); when something but not
    everything was reserved publish `BookingPartsChanged` (D83). Any other status, or a general
    restock: nothing (the stock stays general, D24, INV-08, INV-09, INV-24)."""
    if event.booking_id is None:
        return
    booking = await BookingRepository(uow.session).get_for_update(
        shop_id=event.shop_id, booking_id=event.booking_id
    )
    if booking is None or booking.status != BookingStatus.PARTS_ORDERED:
        return
    reservation = await inventory_service.reserve_received_for_booking(
        uow,
        shop_id=booking.shop_id,
        booking_id=booking.id,
        purchase_order_id=event.purchase_order_id,
        received=event.received,
        actor_user_id=event.actor_user_id,
        now=event.occurred_at,
    )
    if reservation.all_reserved:
        rule = check(
            BookingAction.RECEIVE_PARTS, booking.status, ActorContext(role=ActorRole.PARTS_PERSON)
        )
        await _record(
            uow,
            booking,
            rule=rule,
            by=_By(event.actor_user_id, ActorRole.PARTS_PERSON, event.occurred_at),
            effect=_Effect(metadata={"purchase_order_id": str(event.purchase_order_id)}),
        )
    elif reservation.reserved:
        await uow.publish(
            BookingPartsChanged(
                occurred_at=event.occurred_at,
                shop_id=booking.shop_id,
                booking_id=booking.id,
                status=booking.status,
                version=booking.version,
            )
        )


async def veto_grid_change(session: AsyncSession, *, shop_id: UUID, now: datetime) -> None:
    """`ShopGridChanging` (§7.9): 409 `CONFLICT` while a future non-cancelled booking exists.
    The shop row is locked `FOR UPDATE` by shops and booking creation holds it `FOR SHARE`, so no
    in-flight booking can be missed (CON-05)."""
    if await has_future_bookings(session, shop_id=shop_id, now=now):
        raise Conflict(GRID_LOCKED)


# =================================================================================================
# Booking creation — the wizard (T01, §7.1; D32-D35, D37, D64, D65, D69)
# =================================================================================================


def _rate_limited(item: RateLimitItem, *identifiers: str) -> None:
    """Count one attempt; 429 `RATE_LIMITED` with `Retry-After` once the window is full (D69)."""
    if not account_limiter().hit(item, *identifiers):
        retry_after = retry_after_seconds(item, *identifiers)
        raise RateLimited(
            f"Too many bookings. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


def check_anonymous_booking_rate(client_ip: str) -> None:
    """The anonymous wizard's per-IP ceiling (20 per minute, D69), applied by the route only when
    the request carries no credentials (a session is limited per user in `create_booking`)."""
    _rate_limited(ANONYMOUS_BOOKING_LIMIT, BOOKING_IP_SCOPE, client_ip)


def _wizard_field_errors(data: BookingCreate, *, anonymous: bool, now: datetime) -> None:
    """§7.1 steps 4-5 in one 422: an anonymous caller's account fields, and a vehicle year no
    later than next year (the schema allows up to 2100, the clock decides the rest)."""
    errors: list[FieldError] = []
    if anonymous:
        customer = data.customer
        errors.extend(
            FieldError(field=f"customer.{name}", code="missing", message="Field required")
            for name in ("full_name", "email", "password")
            if customer is None or getattr(customer, name) is None
        )
    latest_year = now.year + 1
    if data.vehicle.year > latest_year:
        errors.append(
            FieldError(
                field="vehicle.year",
                code="value_error",
                message=f"Year must be between 1900 and {latest_year}.",
            )
        )
    if errors:
        raise ValidationFailed(errors=errors)


@dataclass(frozen=True, slots=True)
class _Account:
    user_id: UUID
    created: bool


async def _new_customer(uow: UnitOfWork, customer: CustomerWrite, now: datetime) -> UserRecord:
    """Case B: create the account (the booking logs it in). A concurrent registration of the same
    e-mail is 409 `EMAIL_ALREADY_REGISTERED` (`uq_users_email`)."""
    if customer.email is None or customer.full_name is None or customer.password is None:
        msg = "the wizard's account fields were checked before"
        raise RuntimeError(msg)
    try:
        return await identity_service.create_customer(
            uow,
            email=customer.email,
            full_name=customer.full_name,
            password=customer.password,
            phone=customer.phone,
            now=now,
        )
    except EmailAlreadyRegistered:
        raise EmailAlreadyRegistered(ACCOUNT_TAKEN_DETAIL) from None
    except IntegrityError as exc:
        if constraint_name(exc) == USERS_EMAIL_CONSTRAINT:
            raise EmailAlreadyRegistered(ACCOUNT_TAKEN_DETAIL) from exc
        raise


async def _resolve_account(
    uow: UnitOfWork, caller: CurrentUser | None, data: BookingCreate, now: datetime
) -> _Account:
    """§7.1 step 9, spec 04 cases A-D. No row lock is held yet, so Argon2 never holds one."""
    customer = data.customer
    phone = customer.phone if customer is not None else None
    if caller is not None:  # A: the session user; the other account fields are ignored
        if phone is not None:
            await identity_service.set_phone_if_empty(uow, user_id=caller.id, phone=phone, now=now)
        return _Account(caller.id, created=False)
    if customer is None or customer.email is None or customer.password is None:
        msg = "the wizard's account fields were checked before"
        raise RuntimeError(msg)
    if await identity_service.find_user_by_email(uow.session, customer.email) is None:  # B
        user = await _new_customer(uow, customer, now)
        return _Account(user.id, created=True)
    try:  # C, or D: wrong password or inactive account (a blocked account → 429 passes through)
        user = await identity_service.sign_in_for_booking(
            uow, email=customer.email, password=customer.password, now=now
        )
    except InvalidCredentials:
        raise EmailAlreadyRegistered(ACCOUNT_EXISTS_DETAIL) from None
    if phone is not None:
        await identity_service.set_phone_if_empty(uow, user_id=user.id, phone=phone, now=now)
    return _Account(user.id, created=False)


async def _upsert_vehicle(
    session: AsyncSession, owner_user_id: UUID, vehicle: VehicleWrite, now: datetime
) -> UUID:
    """§7.2 (D35): lock 2 of T01."""
    return await VehicleRepository(session).upsert(
        owner_user_id=owner_user_id,
        registration_number=vehicle.registration_number,
        registration_key=vehicle.registration_key,
        make=vehicle.make,
        model=vehicle.model,
        year=vehicle.year,
        color=vehicle.color,
        mileage_km=vehicle.mileage_km,
        now=now,
    )


def _created_status() -> BookingStatus:
    status = RULES[BookingAction.CREATE].to_status
    if status is None:  # pragma: no cover - the rule table always gives CREATE a target
        msg = "CREATE has no target status"
        raise RuntimeError(msg)
    return status


async def _insert_booking(  # noqa: PLR0913 - the columns T01 decides
    session: AsyncSession,
    *,
    data: BookingCreate,
    customer_id: UUID,
    vehicle_id: UUID,
    slot: GridSlot,
    now: datetime,
    reference: str | None,
) -> Booking:
    """§7.1 step 13 with §7.3's references: a random `BF-XXXXXX` retried in a savepoint up to 5
    times on `uq_bookings_reference`, or the seed's reserved reference (taken → 409 `CONFLICT`)."""
    booking_id = uuid4()
    repository = BookingRepository(session)
    for _ in range(1 if reference is not None else REFERENCE_ATTEMPTS):
        booking = Booking(
            id=booking_id,
            shop_id=data.shop_id,
            reference=reference or new_booking_reference(),
            customer_user_id=customer_id,
            vehicle_id=vehicle_id,
            mileage_km=data.vehicle.mileage_km,
            slot_start=slot.slot_start,
            slot_end=slot.slot_end,
            status=_created_status(),
            version=1,
            customer_notes=data.customer_notes,
            created_at=now,
            updated_at=now,
        )
        if await repository.insert(booking):
            return booking
    if reference is not None:
        raise Conflict(f"Booking reference {reference} already exists.")
    raise InternalError("Could not allocate a booking reference. Please try again.")


def _add_services(
    session: AsyncSession, booking: Booking, services: Sequence[ServiceSnapshot], now: datetime
) -> None:
    """§7.1 step 14 (D34): one immutable snapshot per selected service."""
    session.add_all(
        BookingService(
            shop_id=booking.shop_id,
            booking_id=booking.id,
            service_id=service.service_id,
            name_snapshot=service.name,
            base_price_snapshot=service.base_price,
            created_at=now,
        )
        for service in services
    )


async def create_booking(
    uow: UnitOfWork,
    *,
    caller: CurrentUser | None,
    data: BookingCreate,
    reference: str | None = None,
) -> BookingCreatedRead:
    """`POST /api/v1/bookings` (T01, §7.1), in the order of spec 03 §4.6.

    Rate limit (session) → account and year fields (422) → bookable shop (404) → services (422)
    → slot (422 `INVALID_SLOT`) → account rule D32 (409, 429; Argon2 before any lock) → shop
    `FOR SHARE` → bookable shop again (404: unlisted or suspended while this request waited, D96)
    → vehicle upsert → slot counter (`SLOT_FULL`) → booking, services, `CREATE` event → commit →
    session token and the customer's detail. Any failure rolls everything back, a case-B account
    included (SEC-18).

    `reference` is internal (the seed's `BF-SEEDnn`, D51), absent from every HTTP schema; a value
    that is not a reserved seed reference is a programming error (`ValueError`).
    """
    if reference is not None and not is_seed_reference(reference):
        msg = f"{reference!r} is not a reserved BF-SEED reference"
        raise ValueError(msg)
    session = uow.session
    now = utcnow()
    if caller is not None:
        _rate_limited(AUTHENTICATED_BOOKING_LIMIT, BOOKING_USER_SCOPE, str(caller.id))
    _wizard_field_errors(data, anonymous=caller is None, now=now)
    if await shops_service.get_bookable_shop(session, shop_id=data.shop_id) is None:
        raise NotFound
    services = await shops_service.snapshot_services(
        session, shop_id=data.shop_id, service_ids=data.service_ids
    )
    config = await shops_service.get_schedule_config(session, shop_id=data.shop_id)
    scheduling_service.validate_slot(config, slot_start=data.slot_start, now=now)
    account = await _resolve_account(uow, caller, data, now)
    locked = await shops_service.get_schedule_config(session, shop_id=data.shop_id, for_share=True)
    # Unlisting and suspension write the shop row, so under `FOR SHARE` this re-read is final: a
    # change committed while the request waited for the lock is seen here (spec 19 §7).
    if await shops_service.get_bookable_shop(session, shop_id=data.shop_id) is None:
        raise NotFound
    vehicle_id = await _upsert_vehicle(session, account.user_id, data.vehicle, now)
    slot = await scheduling_service.reserve_slot(
        uow, config=locked, slot_start=data.slot_start, now=now
    )
    booking = await _insert_booking(
        session,
        data=data,
        customer_id=account.user_id,
        vehicle_id=vehicle_id,
        slot=slot,
        now=now,
        reference=reference,
    )
    _add_services(session, booking, services, now)
    await _write_event(
        uow,
        booking,
        action=BookingAction.CREATE,
        from_status=None,
        by=_By(account.user_id, ActorRole.CUSTOMER, now),
        effect=_Effect(),
    )
    await uow.commit()
    token = identity_service.issue_session(account.user_id)
    return BookingCreatedRead(
        access_token=token.access_token,
        token_type=token.token_type,
        expires_in=token.expires_in,
        account_created=account.created,
        booking=await _customer_detail(session, account.user_id, booking.id),
    )


# =================================================================================================
# Read assembly (fixed number of batched calls whatever the page size, API-11)
# =================================================================================================


def _vehicle_brief(vehicle: Vehicle) -> VehicleBrief:
    return VehicleBrief(
        registration_number=vehicle.registration_number,
        make=vehicle.make,
        model=vehicle.model,
        year=vehicle.year,
    )


def _service_reads(rows: Iterable[BookingService]) -> list[BookingServiceRead]:
    return [
        BookingServiceRead(
            service_id=row.service_id, name=row.name_snapshot, base_price=row.base_price_snapshot
        )
        for row in rows
    ]


def _user_ref(users: Mapping[UUID, UserRecord], user_id: UUID) -> UserRef:
    return UserRef(user_id=user_id, full_name=users[user_id].full_name)


def _event_read(event: BookingEvent, users: Mapping[UUID, UserRecord]) -> BookingEventRead:
    return BookingEventRead(
        id=event.id,
        action=event.action,
        from_status=event.from_status,
        to_status=event.to_status,
        actor=None if event.actor_user_id is None else _user_ref(users, event.actor_user_id),
        actor_role=event.actor_role,
        note=event.note,
        metadata=dict(event.metadata_),
        created_at=event.created_at,
    )


def _keys(bookings: Iterable[Booking]) -> set[BookingKey]:
    return {(booking.shop_id, booking.id) for booking in bookings}


def _vehicle_keys(bookings: Iterable[Booking]) -> set[tuple[UUID, UUID]]:
    return {(booking.customer_user_id, booking.vehicle_id) for booking in bookings}


@dataclass(frozen=True, slots=True)
class _Viewer:
    """Who reads a staff projection: the shop, and whether stock data and the customer's e-mail
    and phone are shown (spec 04 §C). Staff get their role's view; a platform admin sees both."""

    shop_id: UUID
    include_parts: bool
    show_contact: bool


def _staff_viewer(ctx: ShopContext) -> _Viewer:
    return _Viewer(
        shop_id=ctx.shop_id,
        include_parts=ctx.role != MembershipRole.QC_INSPECTOR,
        show_contact=ctx.role in SHOP_WIDE_ROLES,
    )


def _admin_viewer(booking: Booking) -> _Viewer:
    return _Viewer(shop_id=booking.shop_id, include_parts=True, show_contact=True)


@dataclass(frozen=True, slots=True)
class _StaffFacts:
    """Everything a page of staff bookings shows besides its own columns, read in batches."""

    vehicles: Mapping[UUID, Vehicle]
    services: Mapping[UUID, list[BookingService]]
    users: Mapping[UUID, UserRecord]
    members: Mapping[UUID, MemberRef]
    estimates: Mapping[UUID, EstimateSummary]
    parts: Mapping[UUID, PartsSummary]
    qc: Mapping[UUID, QcSummary]

    def member(self, user_id: UUID | None) -> MemberRef | None:
        return None if user_id is None else self.members.get(user_id)

    def qc_of(self, booking_id: UUID) -> QcSummary:
        return self.qc.get(booking_id, QcSummary(inspections=0, open_issues=0))


async def _staff_facts(
    session: AsyncSession,
    viewer: _Viewer,
    bookings: Sequence[Booking],
    *,
    extra_user_ids: Iterable[UUID] = (),
) -> _StaffFacts:
    """Vehicles, services, customer names, assignees, estimate summaries, parts summaries (never
    for QC callers, never before `assign-parts-person`) and QC summaries of these bookings, all of
    `viewer.shop_id`."""
    ids = [booking.id for booking in bookings]
    staff_ids = {
        user_id
        for booking in bookings
        for user_id in (
            booking.technician_user_id,
            booking.parts_person_user_id,
            booking.qc_inspector_user_id,
        )
        if user_id is not None
    }
    with_parts = [booking.id for booking in bookings if booking.parts_person_user_id is not None]
    parts: Mapping[UUID, PartsSummary] = {}
    if viewer.include_parts:
        parts = await inventory_service.get_booking_parts_summary(
            session, shop_id=viewer.shop_id, booking_ids=with_parts
        )
    return _StaffFacts(
        vehicles=await VehicleRepository(session).get_many(keys=_vehicle_keys(bookings)),
        services=await BookingServiceRepository(session).list_for_bookings(keys=_keys(bookings)),
        users=await identity_service.get_users_by_ids(
            session, {booking.customer_user_id for booking in bookings} | set(extra_user_ids)
        ),
        members=await shops_service.get_member_refs(
            session, shop_id=viewer.shop_id, user_ids=staff_ids
        ),
        estimates=await estimates_service.get_estimate_summaries(
            session, shop_id=viewer.shop_id, booking_ids=ids, audience="staff"
        ),
        parts=parts,
        qc=await qc_service.get_qc_summaries(session, shop_id=viewer.shop_id, booking_ids=ids),
    )


def _staff_summary(
    ctx: ShopContext, booking: Booking, changed: datetime | None, facts: _StaffFacts
) -> BookingSummary:
    qc = facts.qc_of(booking.id)
    return BookingSummary(
        id=booking.id,
        shop_id=booking.shop_id,
        reference=booking.reference,
        status=booking.status,
        version=booking.version,
        slot_start=booking.slot_start,
        slot_end=booking.slot_end,
        status_changed_at=changed or booking.created_at,
        customer=_user_ref(facts.users, booking.customer_user_id),
        vehicle=_vehicle_brief(facts.vehicles[booking.vehicle_id]),
        service_names=[row.name_snapshot for row in facts.services.get(booking.id, [])],
        technician=facts.member(booking.technician_user_id),
        parts_person=facts.member(booking.parts_person_user_id),
        qc_inspector=facts.member(booking.qc_inspector_user_id),
        estimate_summary=facts.estimates.get(booking.id),
        parts_summary=facts.parts.get(booking.id),
        open_qc_issues_count=qc.open_issues,
        qc_round=qc.qc_round(booking.status),
        repair_started_at=booking.repair_started_at,
        allowed_actions=_staff_slugs(ctx, booking),
        created_at=booking.created_at,
        updated_at=booking.updated_at,
    )


async def _detail_base(
    session: AsyncSession, viewer: _Viewer, booking: Booking
) -> BookingDetailBase:
    """The staff projection of one booking (spec 03 §3.3) without `allowed_actions`: the
    customer's e-mail and phone only when `viewer.show_contact` (the Owner, Service Advisors and
    platform admins, spec 04 §C); `last_event` with its actor."""
    events = BookingEventRepository(session)
    key = (booking.shop_id, booking.id)
    last = await events.latest(shop_id=booking.shop_id, booking_id=booking.id)
    extra = {booking.cancelled_by_user_id, None if last is None else last.actor_user_id}
    facts = await _staff_facts(
        session, viewer, [booking], extra_user_ids={uid for uid in extra if uid is not None}
    )
    changed = (await events.status_changed_at(keys=[key])).get(booking.id)
    customer = facts.users[booking.customer_user_id]
    contact = viewer.show_contact
    qc = facts.qc_of(booking.id)
    return BookingDetailBase(
        id=booking.id,
        shop_id=booking.shop_id,
        reference=booking.reference,
        status=booking.status,
        version=booking.version,
        slot_start=booking.slot_start,
        slot_end=booking.slot_end,
        status_changed_at=changed or booking.created_at,
        customer=BookingCustomer(
            user_id=customer.id,
            full_name=customer.full_name,
            email=customer.email if contact else None,
            phone=customer.phone if contact else None,
        ),
        vehicle=VehicleRead.model_validate(facts.vehicles[booking.vehicle_id]),
        mileage_km=booking.mileage_km,
        services=_service_reads(facts.services.get(booking.id, [])),
        customer_notes=booking.customer_notes,
        inspection_notes=booking.inspection_notes,
        technician=facts.member(booking.technician_user_id),
        parts_person=facts.member(booking.parts_person_user_id),
        qc_inspector=facts.member(booking.qc_inspector_user_id),
        estimate_summary=facts.estimates.get(booking.id),
        parts_summary=facts.parts.get(booking.id),
        open_qc_issues_count=qc.open_issues,
        qc_round=qc.qc_round(booking.status),
        repair_started_at=booking.repair_started_at,
        ready_notified_at=booking.ready_notified_at,
        completed_at=booking.completed_at,
        cancelled_at=booking.cancelled_at,
        cancelled_by=(
            None
            if booking.cancelled_by_user_id is None
            else _user_ref(facts.users, booking.cancelled_by_user_id)
        ),
        cancel_reason=booking.cancel_reason,
        last_event=None if last is None else _event_read(last, facts.users),
    )


async def _staff_detail_of(
    session: AsyncSession, ctx: ShopContext, booking: Booking
) -> BookingDetail:
    """The staff detail (spec 03 §3.3) with the caller's `allowed_actions`."""
    base = await _detail_base(session, _staff_viewer(ctx), booking)
    return BookingDetail(
        **dict(base),
        allowed_actions=_staff_slugs(ctx, booking),
        created_at=booking.created_at,
        updated_at=booking.updated_at,
    )


async def _staff_detail(session: AsyncSession, ctx: ShopContext, booking_id: UUID) -> BookingDetail:
    """The detail re-read after an action's commit (spec 08 step 16)."""
    booking = await BookingRepository(session).get(shop_id=ctx.shop_id, booking_id=booking_id)
    if booking is None:  # pragma: no cover - bookings are never deleted
        raise NotFound
    return await _staff_detail_of(session, ctx, booking)


async def _customer_detail_of(session: AsyncSession, booking: Booking) -> CustomerBookingDetail:
    """The customer detail (spec 03 §3.3): the latest customer-visible estimate version only."""
    key = (booking.shop_id, booking.id)
    shops = await shops_service.get_shop_briefs(session, shop_ids=[booking.shop_id])
    vehicles = await VehicleRepository(session).get_many(keys=_vehicle_keys([booking]))
    services = await BookingServiceRepository(session).list_for_bookings(keys=[key])
    changed = (await BookingEventRepository(session).status_changed_at(keys=[key])).get(booking.id)
    view = await estimates_service.get_customer_view(
        session, shop_id=booking.shop_id, booking_id=booking.id
    )
    shop = shops[booking.shop_id]
    return CustomerBookingDetail(
        id=booking.id,
        reference=booking.reference,
        status=booking.status,
        version=booking.version,
        slot_start=booking.slot_start,
        slot_end=booking.slot_end,
        status_changed_at=changed or booking.created_at,
        shop=_shop_read(shop),
        vehicle=VehicleRead.model_validate(vehicles[booking.vehicle_id]),
        mileage_km=booking.mileage_km,
        services=_service_reads(services.get(booking.id, [])),
        customer_notes=booking.customer_notes,
        estimate=view.estimate,
        estimate_revision_in_progress=view.revision_in_progress,
        allowed_actions=_customer_slugs(
            booking.customer_user_id, booking, shop_suspended=shop.is_suspended
        ),
        ready_notified_at=booking.ready_notified_at,
        completed_at=booking.completed_at,
        cancelled_at=booking.cancelled_at,
        cancelled_by_customer=(
            None
            if booking.cancelled_at is None
            else booking.cancelled_by_user_id == booking.customer_user_id
        ),
        cancel_reason=booking.cancel_reason,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
    )


async def _customer_detail(
    session: AsyncSession, customer_id: UUID, booking_id: UUID
) -> CustomerBookingDetail:
    """The customer detail re-read after a commit (wizard, customer actions)."""
    booking = await BookingRepository(session).get_for_customer(
        customer_user_id=customer_id, booking_id=booking_id
    )
    if booking is None:  # pragma: no cover - bookings are never deleted
        raise NotFound
    return await _customer_detail_of(session, booking)


def _shop_ref(shop: ShopBrief) -> BookingShopRef:
    return BookingShopRef(
        id=shop.id,
        slug=shop.slug,
        name=shop.name,
        city=shop.city,
        phone=shop.phone,
        timezone=shop.timezone,
    )


def _shop_read(shop: ShopBrief) -> BookingShopRead:
    return BookingShopRead(**_shop_ref(shop).model_dump(), address=shop.address)


async def _customer_summaries(
    session: AsyncSession, rows: Sequence[BookingRow]
) -> list[CustomerBookingSummary]:
    """A page of the customer's bookings at any shops: shops, vehicles, services and customer
    estimate summaries in one batch each (API-11)."""
    bookings = [booking for booking, _ in rows]
    if not bookings:
        return []
    shops = await shops_service.get_shop_briefs(
        session, shop_ids={booking.shop_id for booking in bookings}
    )
    vehicles = await VehicleRepository(session).get_many(keys=_vehicle_keys(bookings))
    services = await BookingServiceRepository(session).list_for_bookings(keys=_keys(bookings))
    estimates = await estimates_service.get_customer_estimate_summaries(
        session, booking_keys=_keys(bookings)
    )
    return [
        CustomerBookingSummary(
            id=booking.id,
            reference=booking.reference,
            status=booking.status,
            version=booking.version,
            slot_start=booking.slot_start,
            slot_end=booking.slot_end,
            status_changed_at=changed or booking.created_at,
            shop=_shop_ref(shops[booking.shop_id]),
            vehicle=_vehicle_brief(vehicles[booking.vehicle_id]),
            service_names=[row.name_snapshot for row in services.get(booking.id, [])],
            estimate_summary=estimates.get(booking.id),
            allowed_actions=_customer_slugs(
                booking.customer_user_id,
                booking,
                shop_suspended=shops[booking.shop_id].is_suspended,
            ),
            created_at=booking.created_at,
            updated_at=booking.updated_at,
        )
        for booking, changed in rows
    ]


# =================================================================================================
# P2 read helpers for the calls module and the AI Front Desk (spec 05 §5.3, modules/bookings.md)
# =================================================================================================


def vehicle_label(vehicle: Vehicle) -> str:
    """`2016 Honda Civic (LEA-1234)`: how calls and the agent name a car."""
    return f"{vehicle.year} {vehicle.make} {vehicle.model} ({vehicle.registration_number})"


async def find_customer_bookings(
    session: AsyncSession, *, shop_id: UUID, customer_user_id: UUID, limit: int = 10
) -> list[CustomerBookingSummary]:
    """The customer's bookings at one shop, newest slot first, as the customer sees them."""
    rows = await BookingRepository(session).customer_at_shop(
        shop_id=shop_id, customer_user_id=customer_user_id, limit=limit
    )
    return await _customer_summaries(session, rows)


async def get_booking_labels(
    session: AsyncSession, *, shop_id: UUID, booking_ids: Collection[UUID]
) -> dict[UUID, BookingLabel]:
    """Reference, vehicle label and customer of each booking, in two queries."""
    bookings = await BookingRepository(session).get_many_at_shop(
        shop_id=shop_id, booking_ids=booking_ids
    )
    vehicles = await VehicleRepository(session).get_many(keys=_vehicle_keys(bookings))
    return {
        booking.id: BookingLabel(
            reference=booking.reference,
            vehicle_label=vehicle_label(vehicles[booking.vehicle_id]),
            customer_user_id=booking.customer_user_id,
        )
        for booking in bookings
    }


# =================================================================================================
# Customer reads (spec 03 §4.7)
# =================================================================================================


async def _own_booking(session: AsyncSession, customer_id: UUID, booking_id: UUID) -> Booking:
    """The caller's own booking, else 404 (SM-17), even for staff of that shop."""
    booking = await BookingRepository(session).get_for_customer(
        customer_user_id=customer_id, booking_id=booking_id
    )
    if booking is None:
        raise NotFound
    return booking


async def list_customer_bookings(
    session: AsyncSession,
    customer: CurrentUser,
    *,
    active: bool | None,
    sort: CustomerBookingSort | None,
    page: PageParams,
) -> Page[CustomerBookingSummary]:
    """`GET /api/v1/me/bookings`: own bookings at every shop. `active` true = non-terminal, false
    = terminal, omitted = all; default sort `slot_start` when `active=true`, else `-slot_start`."""
    resolved = sort or ("slot_start" if active is True else "-slot_start")
    rows, total = await BookingRepository(session).customer_page(
        CustomerListQuery(
            customer_user_id=customer.id,
            active=active,
            sort=resolved,
            limit=page.limit,
            offset=page.offset,
        )
    )
    return Page.build(await _customer_summaries(session, rows), total=total, params=page)


async def get_customer_booking(
    session: AsyncSession, customer: CurrentUser, *, booking_id: UUID
) -> CustomerBookingDetail:
    """`GET /api/v1/me/bookings/{booking_id}`."""
    return await _customer_detail_of(session, await _own_booking(session, customer.id, booking_id))


async def list_customer_booking_events(
    session: AsyncSession, customer: CurrentUser, *, booking_id: UUID
) -> list[CustomerBookingEventRead]:
    """`GET /api/v1/me/bookings/{booking_id}/events`: the customer projection, oldest first."""
    booking = await _own_booking(session, customer.id, booking_id)
    events = await BookingEventRepository(session).list_for_booking(
        shop_id=booking.shop_id, booking_id=booking.id
    )
    return [
        CustomerBookingEventRead(
            id=event.id,
            action=event.action,
            from_status=event.from_status,
            to_status=event.to_status,
            by_customer=event.actor_role == ActorRole.CUSTOMER,
            note=customer_note(event.action, event.note),
            created_at=event.created_at,
        )
        for event in events
        if is_customer_visible(event.action)
    ]


async def list_customer_estimates(
    session: AsyncSession, customer: CurrentUser, *, booking_id: UUID
) -> list[CustomerEstimateRead]:
    """`GET /api/v1/me/bookings/{booking_id}/estimates` (P1): `SENT`, `APPROVED` and `REJECTED`
    versions only, ascending (D39)."""
    booking = await _own_booking(session, customer.id, booking_id)
    return await estimates_service.list_customer_versions(
        session, shop_id=booking.shop_id, booking_id=booking.id
    )


async def list_my_vehicles(session: AsyncSession, customer: CurrentUser) -> list[VehicleRead]:
    """`GET /api/v1/me/vehicles` (P1): the caller's vehicles, most recently updated first."""
    vehicles = await VehicleRepository(session).list_for_owner(owner_user_id=customer.id)
    return [VehicleRead.model_validate(vehicle) for vehicle in vehicles]


# =================================================================================================
# Staff reads (spec 03 §4.8)
# =================================================================================================


async def _visible_booking(session: AsyncSession, ctx: ShopContext, booking_id: UUID) -> Booking:
    """A booking of the caller's shop that D21 lets them see, else 404 (identical bodies for
    unknown, other shop and not visible)."""
    booking = await BookingRepository(session).get(shop_id=ctx.shop_id, booking_id=booking_id)
    if booking is None or not await _staff_can_view(session, ctx, booking):
        raise NotFound
    return booking


async def _staff_scope(session: AsyncSession, ctx: ShopContext) -> StaffScope:
    inspected: frozenset[UUID] = frozenset()
    if ctx.role == MembershipRole.QC_INSPECTOR:
        inspected = await qc_service.list_inspected_booking_ids(
            session, shop_id=ctx.shop_id, inspector_user_id=ctx.user.id
        )
    return StaffScope(
        shop_id=ctx.shop_id, role=ctx.role, user_id=ctx.user.id, inspected_ids=inspected
    )


def _local_midnight(day: date, zone: ZoneInfo) -> datetime | None:
    """The UTC instant of `day`'s local midnight; None beyond `datetime`'s range."""
    try:
        return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
    except OverflowError:
        return None


def _day_after(day: date) -> date | None:
    try:
        return day + timedelta(days=1)
    except OverflowError:
        return None


async def _slot_bounds(
    session: AsyncSession, ctx: ShopContext, filters: StaffBookingFilters
) -> tuple[datetime | None, datetime | None]:
    """Inclusive shop-local `date_from` / `date_to` as a half-open UTC window on `slot_start`."""
    if filters.date_from is None and filters.date_to is None:
        return None, None
    shop = (await shops_service.get_shop_briefs(session, shop_ids=[ctx.shop_id]))[ctx.shop_id]
    zone = ZoneInfo(shop.timezone)
    start = None if filters.date_from is None else _local_midnight(filters.date_from, zone)
    end = None
    if filters.date_to is not None:
        after = _day_after(filters.date_to)
        end = None if after is None else _local_midnight(after, zone)
    return start, end


async def _staff_query(
    session: AsyncSession,
    ctx: ShopContext,
    filters: StaffBookingFilters,
    sort: BookingSort,
    page: PageParams,
) -> StaffListQuery:
    """The filters resolved: D21 scope, the three free-text matches, the UTC date bounds."""
    if (
        filters.date_from is not None
        and filters.date_to is not None
        and filters.date_from > filters.date_to
    ):
        raise ValidationFailed(
            errors=[FieldError(field="query.date_to", code="invalid_range", message=DATE_RANGE)]
        )
    text = (filters.q or "").strip() or None
    registration = None
    customer_ids: tuple[UUID, ...] = ()
    if text is not None:
        registration = registration_key(text) or None
        customer_ids = tuple(await identity_service.find_user_ids_by_name(session, q=text))
    slot_from, slot_to = await _slot_bounds(session, ctx, filters)
    return StaffListQuery(
        scope=await _staff_scope(session, ctx),
        statuses=filters.statuses,
        text=text,
        registration=registration,
        customer_ids=customer_ids,
        slot_from=slot_from,
        slot_to=slot_to,
        technician_user_id=filters.technician_user_id,
        parts_person_user_id=filters.parts_person_user_id,
        sort=sort,
        limit=page.limit,
        offset=page.offset,
    )


async def list_staff_bookings(
    session: AsyncSession,
    ctx: ShopContext,
    *,
    filters: StaffBookingFilters,
    sort: BookingSort,
    page: PageParams,
) -> Page[BookingSummary]:
    """`GET /api/v1/shops/{shop_id}/bookings`: the caller's D21 set, narrowed by the filters
    (never widened), sorted with `id` as the tie-breaker. The QC queue is this list with
    `status=QC_PENDING&status=QC_IN_PROGRESS&sort=status_changed_at`."""
    query = await _staff_query(session, ctx, filters, sort, page)
    rows, total = await BookingRepository(session).staff_page(query)
    items: list[BookingSummary] = []
    if rows:
        facts = await _staff_facts(session, _staff_viewer(ctx), [booking for booking, _ in rows])
        items = [_staff_summary(ctx, booking, changed, facts) for booking, changed in rows]
    return Page.build(items, total=total, params=page)


async def get_status_counts(session: AsyncSession, ctx: ShopContext) -> StatusCountsRead:
    """`GET …/bookings/status-counts`: all 17 statuses over the caller's D21 scope."""
    scope = await _staff_scope(session, ctx)
    counts = await BookingRepository(session).status_counts(condition=visibility_condition(scope))
    items = [StatusCount(status=status, count=counts.get(status, 0)) for status in BookingStatus]
    return StatusCountsRead(items=items, total=sum(item.count for item in items))


async def get_staff_booking(
    session: AsyncSession, ctx: ShopContext, *, booking_id: UUID
) -> BookingDetail:
    """`GET …/bookings/{booking_id}`."""
    return await _staff_detail_of(session, ctx, await _visible_booking(session, ctx, booking_id))


async def list_booking_events(
    session: AsyncSession, ctx: ShopContext, *, booking_id: UUID
) -> list[BookingEventRead]:
    """`GET …/bookings/{booking_id}/events`: every event, oldest first by `(created_at, seq)`."""
    return await _event_reads(session, await _visible_booking(session, ctx, booking_id))


async def _event_reads(session: AsyncSession, booking: Booking) -> list[BookingEventRead]:
    """Every event of `booking` as staff see it, oldest first by `(created_at, seq)` (D79)."""
    events = await BookingEventRepository(session).list_for_booking(
        shop_id=booking.shop_id, booking_id=booking.id
    )
    users = await identity_service.get_users_by_ids(
        session, {event.actor_user_id for event in events if event.actor_user_id is not None}
    )
    return [_event_read(event, users) for event in events]


async def list_booking_estimates(
    session: AsyncSession, ctx: ShopContext, *, booking_id: UUID
) -> list[EstimateRead]:
    """`GET …/bookings/{booking_id}/estimates`: every version, live stock except for QC."""
    booking = await _visible_booking(session, ctx, booking_id)
    return await estimates_service.list_versions(
        session,
        shop_id=booking.shop_id,
        booking_id=booking.id,
        include_stock=ctx.role != MembershipRole.QC_INSPECTOR,
    )


async def get_booking_parts(
    session: AsyncSession, ctx: ShopContext, *, booking_id: UUID
) -> BookingPartsRead:
    """`GET …/bookings/{booking_id}/parts`: visibility first (404), then 403 for QC inspectors
    (stock data, spec 04 §B)."""
    booking = await _visible_booking(session, ctx, booking_id)
    if ctx.role == MembershipRole.QC_INSPECTOR:
        raise Forbidden(QC_NO_STOCK)
    return await inventory_service.get_booking_parts(
        session, shop_id=booking.shop_id, booking_id=booking.id
    )


async def list_booking_qc_inspections(
    session: AsyncSession, ctx: ShopContext, *, booking_id: UUID
) -> list[QcInspectionRead]:
    """`GET …/bookings/{booking_id}/qc-inspections`: every round with checklist and issues."""
    booking = await _visible_booking(session, ctx, booking_id)
    return await qc_service.list_booking_qc_history(
        session, shop_id=booking.shop_id, booking_id=booking.id
    )


# =================================================================================================
# Platform admin reads (spec 19 §4 E-61, E-63, E-67, E-72, E-73; D94): every tenant, read-only
# =================================================================================================


def _admin_dates(filters: AdminBookingFilters) -> None:
    if (
        filters.date_from is not None
        and filters.date_to is not None
        and filters.date_from > filters.date_to
    ):
        raise ValidationFailed(
            errors=[FieldError(field="query.date_to", code="invalid_range", message=DATE_RANGE)]
        )


async def _admin_slot_windows(
    session: AsyncSession, filters: AdminBookingFilters
) -> tuple[SlotWindow, ...] | None:
    """The inclusive slot dates as half-open UTC windows, one per shop time zone (D38): a slot
    date is always read in its own shop's zone, whatever the shops' zones are."""
    if filters.date_from is None and filters.date_to is None:
        return None
    zones = await shops_service.get_shop_timezones(session)
    if filters.shop_id is not None:
        zones = {key: zone for key, zone in zones.items() if key == filters.shop_id}
    grouped: dict[str, set[UUID]] = {}
    for shop_id, zone_name in zones.items():
        grouped.setdefault(zone_name, set()).add(shop_id)
    windows = []
    for zone_name, shop_ids in sorted(grouped.items()):
        zone = ZoneInfo(zone_name)
        start = None if filters.date_from is None else _local_midnight(filters.date_from, zone)
        end = None
        if filters.date_to is not None:
            after = _day_after(filters.date_to)
            end = None if after is None else _local_midnight(after, zone)
        # One zone for every shop (the usual case): no need to list the shops.
        scope = None if len(grouped) == 1 else frozenset(shop_ids)
        windows.append(SlotWindow(start=start, end=end, shop_ids=scope))
    return tuple(windows)


async def _admin_query(
    session: AsyncSession, filters: AdminBookingFilters, sort: AdminBookingSort, page: PageParams
) -> AdminListQuery:
    """The filters resolved: free text (reference, plate, customer name or e-mail) and dates."""
    _admin_dates(filters)
    text = (filters.q or "").strip() or None
    registration = None
    customer_ids: tuple[UUID, ...] = ()
    if text is not None:
        registration = registration_key(text) or None
        by_name = await identity_service.find_user_ids_by_name(session, q=text)
        by_email = await identity_service.find_user_ids_by_email(session, q=text)
        customer_ids = tuple(dict.fromkeys([*by_name, *by_email]))
    return AdminListQuery(
        shop_id=filters.shop_id,
        customer_user_id=filters.customer_user_id,
        statuses=filters.statuses,
        text=text,
        registration=registration,
        customer_ids=customer_ids,
        slot_windows=await _admin_slot_windows(session, filters),
        sort=sort,
        limit=page.limit,
        offset=page.offset,
    )


async def _admin_summaries(
    session: AsyncSession, bookings: Sequence[Booking]
) -> list[AdminBookingSummary]:
    """A page of any tenants' bookings: shops, customers, vehicles and services, one batch each."""
    if not bookings:
        return []
    shops = await shops_service.get_shop_briefs(
        session, shop_ids={booking.shop_id for booking in bookings}
    )
    users = await identity_service.get_users_by_ids(
        session, {booking.customer_user_id for booking in bookings}
    )
    vehicles = await VehicleRepository(session).get_many(keys=_vehicle_keys(bookings))
    services = await BookingServiceRepository(session).list_for_bookings(keys=_keys(bookings))
    items = []
    for booking in bookings:
        customer = users[booking.customer_user_id]
        items.append(
            AdminBookingSummary(
                id=booking.id,
                reference=booking.reference,
                shop=_shop_ref(shops[booking.shop_id]),
                status=booking.status,
                version=booking.version,
                slot_start=booking.slot_start,
                slot_end=booking.slot_end,
                customer=BookingCustomer(
                    user_id=customer.id,
                    full_name=customer.full_name,
                    email=customer.email,
                    phone=customer.phone,
                ),
                vehicle=_vehicle_brief(vehicles[booking.vehicle_id]),
                service_names=[row.name_snapshot for row in services.get(booking.id, [])],
                created_at=booking.created_at,
                updated_at=booking.updated_at,
            )
        )
    return items


async def list_admin_bookings(
    session: AsyncSession,
    *,
    filters: AdminBookingFilters,
    sort: AdminBookingSort,
    page: PageParams,
) -> Page[AdminBookingSummary]:
    """E-72 (and the latest bookings of E-63 / E-67): every tenant's bookings matching the
    filters, sorted with `id` as the tie-breaker. Read-only: no `allowed_actions`."""
    query = await _admin_query(session, filters, sort, page)
    bookings, total = await BookingRepository(session).admin_page(query)
    return Page.build(await _admin_summaries(session, bookings), total=total, params=page)


async def get_admin_booking(session: AsyncSession, *, booking_id: UUID) -> AdminBookingDetail:
    """E-73: any tenant's booking as its Owner would see it (customer contact and stock data
    included), with every event, oldest first. Read-only: no `allowed_actions`. Unknown → 404."""
    booking = await BookingRepository(session).get_unscoped(booking_id)
    if booking is None:
        raise NotFound
    base = await _detail_base(session, _admin_viewer(booking), booking)
    shop = (await shops_service.get_shop_briefs(session, shop_ids=[booking.shop_id]))[
        booking.shop_id
    ]
    return AdminBookingDetail(
        **dict(base),
        created_at=booking.created_at,
        updated_at=booking.updated_at,
        shop=_shop_ref(shop),
        events=await _event_reads(session, booking),
    )


@dataclass(frozen=True, slots=True)
class PlatformBookingStats:
    """Every tenant's bookings for the platform overview (spec 19 E-61).

    `created_per_day[i]` counts the bookings created in `[day_bounds[i], day_bounds[i + 1])`;
    `completed` / `cancelled` the bookings completed / cancelled within the whole span; `by_status`
    every booking now (all 17 statuses); `top_shops` the shops with the most bookings created
    within the span, most first."""

    created_per_day: tuple[int, ...]
    completed: int
    cancelled: int
    by_status: Mapping[BookingStatus, int]
    top_shops: tuple[tuple[UUID, int], ...]


async def platform_booking_stats(
    session: AsyncSession, *, day_bounds: Sequence[datetime], top_shops: int = 5
) -> PlatformBookingStats:
    """E-61's booking figures in four statements, over the local days `day_bounds` delimits."""
    if len(day_bounds) < 2:  # noqa: PLR2004 - a span needs a start and an end
        msg = "day_bounds needs at least a start and an end"
        raise ValueError(msg)
    bookings = BookingRepository(session)
    per_day = await bookings.created_per_bucket(day_bounds)
    completed, cancelled = await bookings.finished_between(start=day_bounds[0], end=day_bounds[-1])
    counts = await bookings.all_status_counts()
    top = await bookings.created_by_shop(start=day_bounds[0], end=day_bounds[-1], limit=top_shops)
    return PlatformBookingStats(
        created_per_day=tuple(per_day),
        completed=completed,
        cancelled=cancelled,
        by_status={status: counts.get(status, 0) for status in BookingStatus},
        top_shops=tuple(top),
    )


async def count_created_by_shop(
    session: AsyncSession, *, start: datetime, end: datetime, shop_ids: Collection[UUID]
) -> dict[UUID, int]:
    """Bookings created in `[start, end)` per shop; every requested shop is a key (E-62)."""
    ids = list(dict.fromkeys(shop_ids))
    if not ids:
        return {}
    rows = await BookingRepository(session).created_by_shop(start=start, end=end, shop_ids=ids)
    counts = dict(rows)
    return {shop_id: counts.get(shop_id, 0) for shop_id in ids}

"""Use cases of the calls module (spec 05, `modules/calls.md`).

- Lifecycle C1-C6 for both directions; first accept wins; `end` is idempotent.
- The AI leg A1-A6 for customer → shop calls; the call stays `MISSED` (D58).
- The agent's use cases behind `/api/v1/internal/calls/{call_id}/…` (scope read from the row).
- Reads for customers and staff, tasks and mark-done.
- System entry points (own sessions): `expire_ringing_call`, `sweep_once`, `on_media_event`.

Every write locks only its `call_logs` row (`FOR UPDATE`) and never a booking, so it cannot deadlock
with booking actions (§3.9). LiveKit calls run after the commit, except `create_room` in C1, which
runs before the insert while no lock is held. Pushes are the notifications module's: it subscribes
to `CallStateChanged` and `AiTaskCreated` (spec 01 rule 6).
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import math
import secrets
import uuid
from collections.abc import Awaitable, Callable, Iterable, Sequence
from datetime import date, datetime, timedelta
from functools import partial
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import State

from app.core.config import Settings
from app.core.database import Database
from app.core.errors import (
    CallAlreadyAnswered,
    CallBusy,
    CallingDisabled,
    CallNotActive,
    FieldError,
    Forbidden,
    IdentityNotVerified,
    NotFound,
    RateLimited,
    ValidationFailed,
)
from app.modules.bookings import service as bookings_service
from app.modules.calls import timers
from app.modules.calls.constants import (
    AGENT_NAME,
    AI_JOIN_TIMEOUT_SECONDS,
    AI_MAX_BACKSTOP_SECONDS,
    AI_MAX_CALL_SECONDS,
    CALL_MAX_SECONDS,
    IDENTITY_PREFIX,
    MAX_AGENT_BOOKINGS,
    MAX_IDENTITY_ATTEMPTS,
    MAX_SLOTS,
    MAX_TRANSCRIPT_BYTES,
    MAX_TRANSCRIPT_ENTRIES,
    ROOM_PREFIX,
    START_LIMIT,
    START_WINDOW_SECONDS,
    SUMMARY_GRACE_SECONDS,
    SUMMARY_WINDOW_SECONDS,
    TOKEN_TTL_SECONDS,
)
from app.modules.calls.domain import caller_match
from app.modules.calls.domain.lifecycle import (
    AiLeg,
    UsageRow,
    ai_leg_open,
    ai_leg_status,
    dispatches_ai,
    every_rung_declined,
    participant_minutes,
    ring_set,
    seconds_between,
)
from app.modules.calls.domain.tasks import (
    CUSTOMER_STATUS_LABELS,
    FALLBACK_SUMMARY,
    SummaryFields,
    callback_title,
    escalation_title,
    follow_up_title,
    left_early_callback_title,
    reschedule_title,
    unavailable_callback_title,
)
from app.modules.calls.events import AiTaskCreated, CallStateChanged
from app.modules.calls.models import AiCallSummary, CallLog, Task
from app.modules.calls.providers.base import CallMediaGateway, MediaError, MediaEvent
from app.modules.calls.providers.livekit import LiveKitGateway
from app.modules.calls.repository import CallLogRepository, SummaryRepository, TaskRepository
from app.modules.calls.schemas import (
    AgentBookingItem,
    AgentBookingList,
    AgentBookingRead,
    AgentEstimateBrief,
    AgentEstimateLine,
    AgentEstimateRead,
    AgentHours,
    AgentShopBrief,
    AgentShopRead,
    AgentSlot,
    AgentSlotsRead,
    AgentSummaryIn,
    AgentTaskCreate,
    AgentTaskRead,
    AiLegRead,
    CallConnection,
    CallDetailRead,
    CallRead,
    CallStartRead,
    Party,
    SessionStartRead,
    StaffCallRead,
    SummaryPost,
    SummaryRead,
    SummaryStored,
    TaskRead,
    TaskSummary,
    TranscriptEntry,
    VerifyCallerRead,
    VerifyCallerRequest,
)
from app.modules.identity import service as identity_service
from app.modules.identity.schemas import UserRecord
from app.modules.scheduling import service as scheduling_service
from app.modules.shops import service as shops_service
from app.shared.auth import CurrentUser, ShopContext
from app.shared.clock import utcnow
from app.shared.enums import (
    AiLegStatus,
    CallDirection,
    CallIntent,
    CallStatus,
    MembershipRole,
    MissedReason,
    TaskKind,
    TaskStatus,
)
from app.shared.event_bus import EventBus
from app.shared.orm import touch
from app.shared.pagination import Page, PageParams
from app.shared.uow import UnitOfWork

logger = logging.getLogger(__name__)

STAFF_CALL_ROLES = frozenset({MembershipRole.SERVICE_ADVISOR, MembershipRole.OWNER})
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


# --- Ports and runtime (D90) ----------------------------------------------------------------------


class Presence(Protocol):
    """Who has an open WebSocket: the notifications hub, read duck-typed (calls may not import
    notifications, spec 01)."""

    def online_user_ids(self, user_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]: ...


def build_call_media(settings: Settings) -> CallMediaGateway | None:
    if not (
        settings.calling_enabled
        and settings.call_provider_url
        and settings.call_provider_api_key
        and settings.call_provider_api_secret
    ):
        return None
    return LiveKitGateway(
        url=settings.call_provider_url,
        api_key=settings.call_provider_api_key.get_secret_value(),
        api_secret=settings.call_provider_api_secret.get_secret_value(),
    )


def get_call_media(state: State) -> CallMediaGateway | None:
    """The app's gateway, created on first use at `state.call_media` (None = calling disabled)."""
    if not hasattr(state, "call_media"):
        state.call_media = build_call_media(state.settings)
    media: CallMediaGateway | None = state.call_media
    return media


def _online(state: State | None, user_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    hub = getattr(state, "realtime_hub", None) if state is not None else None
    if hub is None or not hasattr(hub, "online_user_ids"):
        return set()  # no hub yet: nobody is online
    presence: Presence = hub
    return presence.online_user_ids(user_ids)


def _state(uow: UnitOfWork) -> State:
    if uow.app_state is None:
        msg = "the calls module needs the app state (build the app with create_app())"
        raise RuntimeError(msg)
    return uow.app_state


def _settings(state: State) -> Settings:
    settings: Settings = state.settings
    return settings


def _new_uow(state: State, session: AsyncSession) -> UnitOfWork:
    bus = getattr(state, "event_bus", None)
    return UnitOfWork(session, bus if isinstance(bus, EventBus) else EventBus(), app_state=state)


def _database(state: State) -> Database:
    database: Database = state.db
    return database


async def _best_effort(label: str, call_id: uuid.UUID, work: Awaitable[object]) -> None:
    try:
        await work
    except Exception as exc:
        logger.warning(
            "calls.media_cleanup_failed",
            extra={"call_id": str(call_id), "step": label, "error": type(exc).__name__},
        )


# --- Small helpers --------------------------------------------------------------------------------


def _leg(call: CallLog) -> AiLeg:
    return AiLeg(call.ai_dispatched_at, call.ai_answered_at, call.ai_ended_at, call.ai_error)


def _identity(user_id: uuid.UUID) -> str:
    return f"{IDENTITY_PREFIX}{user_id}"


def _event(call: CallLog, previous: CallStatus | None) -> CallStateChanged:
    return CallStateChanged(
        occurred_at=utcnow(),
        shop_id=call.shop_id,
        call_id=call.id,
        booking_id=call.booking_id,
        direction=call.direction,
        previous_status=previous,
        status=call.status,
        missed_reason=call.missed_reason,
        ai_status=ai_leg_status(_leg(call)),
        caller_user_id=call.caller_user_id,
        customer_user_id=call.customer_user_id,
        answered_by_user_id=call.answered_by_user_id,
        rung_user_ids=tuple(call.rung_user_ids or ()),
    )


async def _eligible_shop_callees(session: AsyncSession, shop_id: uuid.UUID) -> list[uuid.UUID]:
    """D26: the active SAs of the shop; none → the Owner."""
    advisors = await shops_service.list_active_member_ids(
        session, shop_id=shop_id, roles=[MembershipRole.SERVICE_ADVISOR]
    )
    if advisors:
        return advisors
    return [await shops_service.get_owner_user_id(session, shop_id=shop_id)]


async def _user(session: AsyncSession, user_id: uuid.UUID) -> UserRecord:
    user = await identity_service.get_user(session, user_id)
    if user is None:
        raise NotFound
    return user


# --- Views ----------------------------------------------------------------------------------------


async def _call_reads(
    session: AsyncSession, calls: Sequence[CallLog], *, staff: bool
) -> list[CallRead]:
    """Batched: labels per shop, names, shop names; staff views add summary and task counts."""
    if not calls:
        return []
    labels: dict[uuid.UUID, Any] = {}
    for shop_id in {call.shop_id for call in calls}:
        labels |= await bookings_service.get_booking_labels(
            session,
            shop_id=shop_id,
            booking_ids={call.booking_id for call in calls if call.shop_id == shop_id},
        )
    user_ids = {call.caller_user_id for call in calls} | {call.customer_user_id for call in calls}
    user_ids |= {call.answered_by_user_id for call in calls if call.answered_by_user_id}
    users = await identity_service.get_users_by_ids(session, user_ids)
    shops = await shops_service.get_shop_briefs(session, shop_ids={call.shop_id for call in calls})
    summaries: dict[uuid.UUID, AiCallSummary] = {}
    open_tasks: dict[uuid.UUID, int] = {}
    if staff:
        call_ids = [call.id for call in calls]
        summaries = await SummaryRepository(session).for_calls(call_ids)
        for task in await TaskRepository(session).for_calls(call_ids):
            if task.status is TaskStatus.OPEN and task.call_log_id is not None:
                open_tasks[task.call_log_id] = open_tasks.get(task.call_log_id, 0) + 1

    def party(user_id: uuid.UUID) -> Party:
        user = users.get(user_id)
        return Party(user_id=user_id, display_name=user.full_name if user else "Unknown")

    reads: list[CallRead] = []
    for call in calls:
        label = labels.get(call.booking_id)
        shop_name = shops[call.shop_id].name if call.shop_id in shops else ""
        leg = _leg(call)
        status = ai_leg_status(leg)
        base: dict[str, Any] = {
            "id": call.id,
            "shop_id": call.shop_id,
            "shop_name": shop_name,
            "booking_id": call.booking_id,
            "booking_reference": label.reference if label else "",
            "vehicle_label": label.vehicle_label if label else "",
            "direction": call.direction,
            "status": call.status,
            "missed_reason": call.missed_reason,
            "caller": party(call.caller_user_id),
            "callee_label": (
                shop_name
                if call.direction is CallDirection.CUSTOMER_TO_SHOP
                else party(call.customer_user_id).display_name
            ),
            "answered_by": party(call.answered_by_user_id) if call.answered_by_user_id else None,
            "rung_count": len(call.rung_user_ids or ()),
            "started_at": call.started_at,
            "ring_deadline": call.ring_deadline,
            "answered_at": call.answered_at,
            "ended_at": call.ended_at,
            "duration_seconds": call.duration_seconds,
            "ai": None
            if status is AiLegStatus.NONE
            else AiLegRead(
                status=status,
                answered_at=call.ai_answered_at,
                ended_at=call.ai_ended_at,
                duration_seconds=call.ai_duration_seconds,
            ),
        }
        if staff:
            reads.append(
                StaffCallRead(
                    **base,
                    has_summary=call.id in summaries,
                    open_task_count=open_tasks.get(call.id, 0),
                )
            )
        else:
            reads.append(CallRead(**base))
    return reads


async def get_call_read(session: AsyncSession, call_id: uuid.UUID) -> CallRead | None:
    """For notifications' pushes: the base `CallRead` (no staff-only fields)."""
    call = await CallLogRepository(session).get(call_id)
    if call is None:
        return None
    return (await _call_reads(session, [call], staff=False))[0]


async def _task_reads(session: AsyncSession, tasks: Sequence[Task]) -> list[TaskRead]:
    if not tasks:
        return []
    labels: dict[uuid.UUID, Any] = {}
    for shop_id in {task.shop_id for task in tasks}:
        labels |= await bookings_service.get_booking_labels(
            session,
            shop_id=shop_id,
            booking_ids={t.booking_id for t in tasks if t.shop_id == shop_id and t.booking_id},
        )
    user_ids = {task.customer_user_id for task in tasks if task.customer_user_id}
    user_ids |= {task.done_by_user_id for task in tasks if task.done_by_user_id}
    users = await identity_service.get_users_by_ids(session, user_ids)
    summaries = await SummaryRepository(session).for_calls(
        {task.call_log_id for task in tasks if task.call_log_id}
    )

    def party(user_id: uuid.UUID | None) -> Party | None:
        if user_id is None:
            return None
        user = users.get(user_id)
        return Party(user_id=user_id, display_name=user.full_name if user else "Unknown")

    reads: list[TaskRead] = []
    for task in tasks:
        label = labels.get(task.booking_id) if task.booking_id else None
        summary = summaries.get(task.call_log_id) if task.call_log_id else None
        reads.append(
            TaskRead(
                id=task.id,
                shop_id=task.shop_id,
                booking_id=task.booking_id,
                booking_reference=label.reference if label else None,
                call_id=task.call_log_id,
                customer=party(task.customer_user_id),
                kind=task.kind,
                title=task.title,
                description=task.description,
                is_urgent=task.is_urgent,
                status=task.status,
                metadata=task.metadata_ or {},
                created_at=task.created_at,
                done_at=task.done_at,
                done_by=party(task.done_by_user_id),
                done_note=task.done_note,
                summary=TaskSummary(
                    intent=summary.intent,
                    intent_category=summary.intent_category,
                    sentiment=summary.sentiment,
                    is_fallback=summary.is_fallback,
                )
                if summary
                else None,
            )
        )
    return reads


async def get_task_read(session: AsyncSession, task_id: uuid.UUID) -> TaskRead | None:
    task = await session.get(Task, task_id)
    return (await _task_reads(session, [task]))[0] if task is not None else None


async def list_ringing_calls_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[CallRead]:
    """Re-send on connect (§8.4): ringing calls this user may answer, rung or not."""
    memberships = await shops_service.list_memberships_for_user(
        session, user_id=user_id, roles=[MembershipRole.SERVICE_ADVISOR, MembershipRole.OWNER]
    )
    shop_ids: set[uuid.UUID] = set()
    for membership in memberships:
        if user_id in await _eligible_shop_callees(session, membership.shop_id):
            shop_ids.add(membership.shop_id)
    calls = await CallLogRepository(session).ringing_eligible(
        shop_ids=shop_ids, customer_user_id=user_id
    )
    wanted = [
        call
        for call in calls
        if call.caller_user_id != user_id
        and (call.direction is CallDirection.CUSTOMER_TO_SHOP or call.customer_user_id == user_id)
    ]
    return await _call_reads(session, wanted, staff=False)


# --- C1 — start -----------------------------------------------------------------------------------


async def _check_caps(session: AsyncSession, settings: Settings, caller: uuid.UUID) -> None:
    """503 monthly cap → 429 start limit (spec 05 §8.7 order)."""
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    calls = CallLogRepository(session)
    rows = [
        UsageRow(
            call.status,
            call.started_at,
            call.answered_at,
            call.ended_at,
            call.duration_seconds,
            call.ai_duration_seconds,
        )
        for call in await calls.started_since(month_start)
    ]
    if participant_minutes(rows, now=now) >= settings.call_monthly_minutes_cap:
        raise CallingDisabled
    starts = await calls.starts_since(
        caller_user_id=caller, since=now - timedelta(seconds=START_WINDOW_SECONDS)
    )
    if len(starts) >= START_LIMIT:
        retry = math.ceil(
            (starts[0] + timedelta(seconds=START_WINDOW_SECONDS) - now).total_seconds()
        )
        retry = max(1, retry)
        raise RateLimited(
            f"Too many calls. Try again in {retry} seconds.", headers={"Retry-After": str(retry)}
        )


async def _start(
    uow: UnitOfWork,
    *,
    shop_id: uuid.UUID,
    booking_id: uuid.UUID,
    customer_user_id: uuid.UUID,
    caller: UserRecord,
    direction: CallDirection,
) -> CallStartRead:
    state = _state(uow)
    settings = _settings(state)
    media = get_call_media(state)
    if media is None:
        raise CallingDisabled
    session = uow.session
    await _check_caps(session, settings, caller.id)
    calls = CallLogRepository(session)
    involved = {caller.id, customer_user_id}
    if await calls.booking_busy(booking_id) or await calls.busy_user_ids(involved):
        raise CallBusy
    if direction is CallDirection.CUSTOMER_TO_SHOP:
        eligible = await _eligible_shop_callees(session, shop_id)
    else:
        eligible = [customer_user_id]
    rung = ring_set(
        eligible=eligible,
        online=_online(state, eligible),
        busy=await calls.connected_user_ids(eligible),
        caller=caller.id,
    )
    call_id = uuid.uuid4()
    room = f"{ROOM_PREFIX}{call_id}"
    try:
        await media.create_room(room)  # before the insert; no lock is held here
    except MediaError as exc:
        logger.warning("calls.create_room_failed", extra={"error": str(exc)})
        raise CallingDisabled from exc
    now = utcnow()
    call = CallLog(
        id=call_id,
        shop_id=shop_id,
        booking_id=booking_id,
        customer_user_id=customer_user_id,
        direction=direction,
        status=CallStatus.RINGING,
        caller_user_id=caller.id,
        rung_user_ids=rung,
        declined_user_ids=[],
        room_name=room,
        started_at=now,
        ring_deadline=now + timedelta(seconds=settings.ai_ring_timeout_seconds),
        ai_identity_attempts=0,
    )
    calls.add(call)
    try:
        await session.flush()
    except IntegrityError as exc:  # uq_call_logs_one_active_per_booking: a concurrent start won
        await uow.rollback()
        await _best_effort("delete_room", call_id, media.delete_room(room))
        raise CallBusy from exc
    await uow.publish(_event(call, None))
    deadline = call.ring_deadline
    uow.after_commit(partial(_schedule_expiry, state, call_id, deadline))
    await uow.commit()
    token = media.issue_token(
        room=room,
        identity=_identity(caller.id),
        name=caller.full_name,
        ttl_seconds=TOKEN_TTL_SECONDS,
        now=now,
    )
    read = (await _call_reads(session, [call], staff=False))[0]
    return CallStartRead(
        call=read,
        connection=CallConnection(
            url=media.url,
            room=room,
            token=token.token,
            identity=_identity(caller.id),
            expires_at=token.expires_at,
        ),
    )


async def _schedule_expiry(state: State, call_id: uuid.UUID, deadline: datetime) -> None:
    timers.schedule_ring_timeout(call_id, deadline, partial(expire_ringing_call, state, call_id))


async def start_customer_call(
    uow: UnitOfWork, customer: CurrentUser, booking_id: uuid.UUID
) -> CallStartRead:
    """`POST /api/v1/me/bookings/{booking_id}/calls` (C1, C2S)."""
    booking = await bookings_service.get_customer_booking(
        uow.session, customer, booking_id=booking_id
    )
    caller = await _user(uow.session, customer.id)
    return await _start(
        uow,
        shop_id=booking.shop.id,
        booking_id=booking.id,
        customer_user_id=customer.id,
        caller=caller,
        direction=CallDirection.CUSTOMER_TO_SHOP,
    )


async def start_staff_call(
    uow: UnitOfWork, ctx: ShopContext, booking_id: uuid.UUID
) -> CallStartRead:
    """`POST …/bookings/{booking_id}/calls` (C1, S2C): booking visible (404) → SA/Owner (403)."""
    booking = await bookings_service.get_staff_booking(uow.session, ctx, booking_id=booking_id)
    if ctx.role not in STAFF_CALL_ROLES:
        raise Forbidden
    caller = await _user(uow.session, ctx.user.id)
    return await _start(
        uow,
        shop_id=ctx.shop_id,
        booking_id=booking.id,
        customer_user_id=booking.customer.user_id,
        caller=caller,
        direction=CallDirection.SHOP_TO_CUSTOMER,
    )


# --- C2, C3, C5, C6 — accept, decline, end --------------------------------------------------------


class CallActor:
    """Who acts on a call: a customer (`/me` routes) or a staff member of the call's shop."""

    def __init__(self, user_id: uuid.UUID, shop: ShopContext | None) -> None:
        self.user_id = user_id
        self.shop = shop

    @classmethod
    def customer(cls, user: CurrentUser) -> "CallActor":
        return cls(user.id, None)

    @classmethod
    def staff(cls, ctx: ShopContext) -> "CallActor":
        return cls(ctx.user.id, ctx)


async def _locked_visible(uow: UnitOfWork, actor: CallActor, call_id: uuid.UUID) -> CallLog:
    """404 unless the actor may see the call: its customer, or a member of its shop who may see
    calls (SA/Owner; other roles get 404 on items, D21)."""
    call = await CallLogRepository(uow.session).lock(call_id)
    if call is None:
        raise NotFound
    if actor.shop is None:
        if call.customer_user_id != actor.user_id:
            raise NotFound
    elif call.shop_id != actor.shop.shop_id or actor.shop.role not in STAFF_CALL_ROLES:
        raise NotFound
    return call


async def _eligible_callee(session: AsyncSession, actor: CallActor, call: CallLog) -> bool:
    if call.direction is CallDirection.SHOP_TO_CUSTOMER:
        return actor.shop is None and call.customer_user_id == actor.user_id
    if actor.shop is None:
        return False
    return actor.user_id in await _eligible_shop_callees(session, call.shop_id)


def _is_participant(actor: CallActor, call: CallLog) -> bool:
    if actor.user_id in {call.caller_user_id, call.answered_by_user_id}:
        return True
    return actor.shop is None and actor.user_id == call.customer_user_id and ai_leg_open(_leg(call))


async def answer_call(uow: UnitOfWork, actor: CallActor, call_id: uuid.UUID) -> CallStartRead:
    """C2: first accept wins (row lock, D30)."""
    state = _state(uow)
    media = get_call_media(state)
    call = await _locked_visible(uow, actor, call_id)
    if not await _eligible_callee(uow.session, actor, call):
        raise Forbidden
    if call.status is not CallStatus.RINGING:
        raise CallAlreadyAnswered if call.status is CallStatus.CONNECTED else CallNotActive
    if media is None:
        raise CallingDisabled
    now = utcnow()
    call.status = CallStatus.CONNECTED
    call.answered_by_user_id = actor.user_id
    call.answered_at = now
    touch(call, now)
    await uow.publish(_event(call, CallStatus.RINGING))
    await uow.commit()
    timers.cancel_ring_timeout(call.id)
    user = await _user(uow.session, actor.user_id)
    token = media.issue_token(
        room=call.room_name,
        identity=_identity(user.id),
        name=user.full_name,
        ttl_seconds=TOKEN_TTL_SECONDS,
        now=now,
    )
    staff = actor.shop is not None
    read = (await _call_reads(uow.session, [call], staff=staff))[0]
    return CallStartRead(
        call=read,
        connection=CallConnection(
            url=media.url,
            room=call.room_name,
            token=token.token,
            identity=_identity(user.id),
            expires_at=token.expires_at,
        ),
    )


async def decline_call(uow: UnitOfWork, actor: CallActor, call_id: uuid.UUID) -> CallRead:
    """C3: recorded; the call ends only when every rung callee has declined (D77)."""
    state = _state(uow)
    call = await _locked_visible(uow, actor, call_id)
    if not await _eligible_callee(uow.session, actor, call):
        raise Forbidden
    if call.status is not CallStatus.RINGING:
        raise CallNotActive
    now = utcnow()
    declined = list(call.declined_user_ids or [])
    if actor.user_id not in declined:
        declined.append(actor.user_id)
    call.declined_user_ids = declined
    if every_rung_declined(call.rung_user_ids or [], declined):
        await _miss(uow, state, call, MissedReason.DECLINED, now)
    else:
        touch(call, now)
        await uow.commit()
    return (await _call_reads(uow.session, [call], staff=actor.shop is not None))[0]


async def end_call(uow: UnitOfWork, actor: CallActor, call_id: uuid.UUID) -> CallRead:
    """C5 (caller while ringing), C6 (a participant while connected), A3 (the customer during the
    AI leg). Idempotent: a finished call is returned unchanged."""
    state = _state(uow)
    call = await _locked_visible(uow, actor, call_id)
    staff = actor.shop is not None
    if not _is_participant(actor, call):
        if call.status in {CallStatus.ENDED, CallStatus.MISSED}:
            return (await _call_reads(uow.session, [call], staff=staff))[0]
        raise Forbidden
    now = utcnow()
    if call.status is CallStatus.RINGING:
        if actor.user_id != call.caller_user_id:
            raise Forbidden
        call.status = CallStatus.MISSED
        call.missed_reason = MissedReason.CALLER_HUNG_UP
        call.ended_at = now
        call.ended_by_user_id = actor.user_id
        touch(call, now)
        await uow.publish(_event(call, CallStatus.RINGING))
        _after_delete_room(uow, state, call)
        await uow.commit()
        timers.cancel_ring_timeout(call.id)
    elif call.status is CallStatus.CONNECTED:
        _finish_connected(call, now, ended_by=actor.user_id)
        await uow.publish(_event(call, CallStatus.CONNECTED))
        _after_delete_room(uow, state, call)
        await uow.commit()
    elif ai_leg_open(_leg(call)) and actor.user_id == call.customer_user_id:
        await _end_leg(uow, state, call, now, error=None)
    else:
        await uow.commit()
    return (await _call_reads(uow.session, [call], staff=staff))[0]


def _finish_connected(call: CallLog, now: datetime, *, ended_by: uuid.UUID | None) -> None:
    call.status = CallStatus.ENDED
    call.ended_at = now
    call.duration_seconds = seconds_between(call.answered_at or now, now)
    call.ended_by_user_id = ended_by
    touch(call, now)


def _after_delete_room(uow: UnitOfWork, state: State, call: CallLog) -> None:
    media = get_call_media(state)
    if media is not None:
        uow.after_commit(partial(_delete_room, media, call.id, call.room_name))


async def _delete_room(media: CallMediaGateway, call_id: uuid.UUID, room: str) -> None:
    await _best_effort("delete_room", call_id, media.delete_room(room))


# --- C3/C4 → MISSED, A1 dispatch, A3/A4 leg ends --------------------------------------------------


async def _miss(
    uow: UnitOfWork, state: State, call: CallLog, reason: MissedReason, now: datetime
) -> None:
    """C3/C4 in the caller's transaction, plus A1 when it applies; commits."""
    call.status = CallStatus.MISSED
    call.missed_reason = reason
    call.ended_at = now
    touch(call, now)
    call_token = await _maybe_dispatch(uow.session, _settings(state), call, reason, now)
    await uow.publish(_event(call, CallStatus.RINGING))
    if call_token is not None:
        uow.after_commit(partial(dispatch_agent, state, call.id, call_token))
    else:
        _after_delete_room(uow, state, call)
    await uow.commit()
    timers.cancel_ring_timeout(call.id)


async def _maybe_dispatch(
    session: AsyncSession, settings: Settings, call: CallLog, reason: MissedReason, now: datetime
) -> str | None:
    """A1: mark the leg dispatched and return the plain per-call token (only its hash is stored)."""
    if not (settings.ai_enabled and dispatches_ai(call.direction, reason)):
        return None
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if await CallLogRepository(session).ai_legs_since(day_start) >= settings.ai_daily_call_cap:
        return None
    token = secrets.token_urlsafe(32)
    call.ai_dispatched_at = now
    call.ai_call_token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token


async def dispatch_agent(state: State, call_id: uuid.UUID, call_token: str) -> None:
    """A1's after-commit half: create the dispatch, store its id; a failure is A4."""
    media = get_call_media(state)
    async with _database(state).sessionmaker() as session:
        call = await CallLogRepository(session).get(call_id)
        if call is None or media is None:
            return
        metadata = json.dumps(
            {
                "call_id": str(call.id),
                "booking_id": str(call.booking_id),
                "customer_user_id": str(call.customer_user_id),
                "call_token": call_token,
            }
        )
        room = call.room_name
    try:
        dispatch_id = await media.create_dispatch(
            room=room, agent_name=AGENT_NAME, metadata=metadata
        )
    except MediaError as exc:
        logger.warning("calls.dispatch_failed", extra={"call_id": str(call_id), "error": str(exc)})
        await fail_unjoined_leg(state, call_id, force=True)
        return
    async with _database(state).sessionmaker() as session:
        uow = _new_uow(state, session)
        locked = await CallLogRepository(session).lock(call_id)
        if locked is not None and locked.ai_dispatch_id is None:
            locked.ai_dispatch_id = dispatch_id[:64]
            touch(locked, utcnow())
        await uow.commit()


async def _ensure_callback_task(
    uow: UnitOfWork, call: CallLog, title_for: Callable[[str], str], now: datetime
) -> None:
    """A CALLBACK task when the call has no task yet (A3 with error, A4, A6)."""
    tasks = TaskRepository(uow.session)
    if await tasks.count_for_call(call.id):
        return
    customer = await _user(uow.session, call.customer_user_id)
    await _insert_task(
        uow,
        call,
        kind=TaskKind.CALLBACK,
        title=title_for(caller_match.first_name(customer.full_name)),
        description=None,
        is_urgent=False,
        metadata={"caller_verified": call.ai_identity_verified_at is not None},
        now=now,
    )


async def _end_leg(
    uow: UnitOfWork, state: State, call: CallLog, now: datetime, *, error: str | None
) -> None:
    """A3: end the open AI leg (idempotent); an error leaves a CALLBACK task. Commits."""
    if not ai_leg_open(_leg(call)):
        await uow.commit()
        return
    call.ai_ended_at = now
    if call.ai_answered_at is not None:
        call.ai_duration_seconds = seconds_between(call.ai_answered_at, now)
    call.ai_error = error[:200] if error else None
    touch(call, now)
    if error:
        await _ensure_callback_task(
            uow, call, lambda first: callback_title(first, "their call"), now
        )
    await uow.publish(_event(call, CallStatus.MISSED))
    _after_delete_room(uow, state, call)
    await uow.commit()


async def fail_unjoined_leg(state: State, call_id: uuid.UUID, *, force: bool = False) -> None:
    """A4: no `/session` within the join timeout, or the dispatch failed (`force`)."""
    media = get_call_media(state)
    async with _database(state).sessionmaker() as session:
        uow = _new_uow(state, session)
        call = await CallLogRepository(session).lock(call_id)
        now = utcnow()
        if call is None or ai_leg_status(_leg(call)) is not AiLegStatus.CONNECTING:
            await uow.commit()
            return
        dispatched = call.ai_dispatched_at or now
        if not force and now - dispatched < timedelta(seconds=AI_JOIN_TIMEOUT_SECONDS):
            await uow.commit()
            return
        call.ai_ended_at = now
        call.ai_error = "AGENT_UNAVAILABLE"
        touch(call, now)
        await _ensure_callback_task(uow, call, unavailable_callback_title, now)
        await uow.publish(_event(call, CallStatus.MISSED))
        dispatch_id, room = call.ai_dispatch_id, call.room_name
        await uow.commit()
    if media is not None:
        if dispatch_id:
            await _best_effort(
                "delete_dispatch",
                call_id,
                media.delete_dispatch(dispatch_id=dispatch_id, room=room),
            )
        await _best_effort("delete_room", call_id, media.delete_room(room))


# --- System entry points: timer, sweeper, webhook -------------------------------------------------


async def expire_ringing_call(state: State, call_id: uuid.UUID) -> None:
    """C4 (+A1) if the call is still ringing and its deadline has passed; otherwise nothing."""
    async with _database(state).sessionmaker() as session:
        uow = _new_uow(state, session)
        call = await CallLogRepository(session).lock(call_id)
        now = utcnow()
        if call is None or call.status is not CallStatus.RINGING or call.ring_deadline > now:
            await uow.commit()
            return
        await _miss(uow, state, call, MissedReason.NO_ANSWER, now)


async def _system_end_connected(state: State, call_id: uuid.UUID) -> None:
    async with _database(state).sessionmaker() as session:
        uow = _new_uow(state, session)
        call = await CallLogRepository(session).lock(call_id)
        now = utcnow()
        if call is None or call.status is not CallStatus.CONNECTED:
            await uow.commit()
            return
        _finish_connected(call, now, ended_by=None)
        await uow.publish(_event(call, CallStatus.CONNECTED))
        _after_delete_room(uow, state, call)
        await uow.commit()


async def _system_end_leg(state: State, call_id: uuid.UUID, error: str | None) -> None:
    async with _database(state).sessionmaker() as session:
        uow = _new_uow(state, session)
        call = await CallLogRepository(session).lock(call_id)
        if call is None:
            await uow.commit()
            return
        await _end_leg(uow, state, call, utcnow(), error=error)


async def _fallback_summary(state: State, call_id: uuid.UUID) -> None:
    """A6: an answered leg ended long ago without a summary."""
    async with _database(state).sessionmaker() as session:
        uow = _new_uow(state, session)
        call = await CallLogRepository(session).lock(call_id)
        if call is None or await SummaryRepository(session).for_call(call_id) is not None:
            await uow.commit()
            return
        now = utcnow()
        _insert_summary(uow, call, FALLBACK_SUMMARY, transcript=[], model=None, now=now)
        await _ensure_callback_task(
            uow, call, lambda first: callback_title(first, "their call"), now
        )
        await uow.commit()


async def _sweep_step(
    state: State,
    claim: Callable[[CallLogRepository], Awaitable[list[uuid.UUID]]],
    apply: Callable[[uuid.UUID], Awaitable[None]],
) -> int:
    async with _database(state).sessionmaker() as session:
        ids = await claim(CallLogRepository(session))
        await session.commit()
    for call_id in ids:
        try:
            await apply(call_id)
        except Exception:
            logger.exception("calls.sweep_failed", extra={"call_id": str(call_id)})
    return len(ids)


async def sweep_once(state: State, now: datetime) -> int:
    """The five checks of §3.5, each with its own claim; returns how many rows were handled."""
    handled = await _sweep_step(
        state, lambda r: r.claim_expired_ringing(now), partial(expire_ringing_call, state)
    )
    handled += await _sweep_step(
        state,
        lambda r: r.claim_unjoined_legs(now - timedelta(seconds=AI_JOIN_TIMEOUT_SECONDS)),
        partial(fail_unjoined_leg, state),
    )
    handled += await _sweep_step(
        state,
        lambda r: r.claim_long_connected(now - timedelta(seconds=CALL_MAX_SECONDS)),
        partial(_system_end_connected, state),
    )
    handled += await _sweep_step(
        state,
        lambda r: r.claim_long_ai_legs(now - timedelta(seconds=AI_MAX_BACKSTOP_SECONDS)),
        lambda call_id: _system_end_leg(state, call_id, "MAX_DURATION_BACKSTOP"),
    )
    handled += await _sweep_step(
        state,
        lambda r: r.claim_unsummarised(now - timedelta(seconds=SUMMARY_GRACE_SECONDS)),
        partial(_fallback_summary, state),
    )
    return handled


async def run_sweeper(state: State, stop: asyncio.Event, interval: float) -> None:
    """At boot and every `interval` seconds until `stop` is set (started by `lifespan.py`)."""
    while not stop.is_set():
        try:
            await sweep_once(state, utcnow())
        except Exception:
            logger.exception("calls.sweeper_failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)


def _call_id_of(room: str) -> uuid.UUID | None:
    if not room.startswith(ROOM_PREFIX):
        return None
    try:
        return uuid.UUID(room.removeprefix(ROOM_PREFIX))
    except ValueError:
        return None


def _user_of(identity: str | None) -> uuid.UUID | None:
    if not identity or not identity.startswith(IDENTITY_PREFIX):
        return None
    try:
        return uuid.UUID(identity.removeprefix(IDENTITY_PREFIX))
    except ValueError:
        return None


async def on_media_event(state: State, event: MediaEvent) -> None:
    """The signed webhook's safety net (§8.5); idempotent; unknown rooms are ignored."""
    call_id = _call_id_of(event.room)
    if call_id is None or event.event not in {
        "participant_left",
        "participant_connection_aborted",
        "room_finished",
    }:
        return
    async with _database(state).sessionmaker() as session:
        uow = _new_uow(state, session)
        call = await CallLogRepository(session).lock(call_id)
        if call is None:
            await uow.commit()
            return
        now = utcnow()
        user_id = _user_of(event.identity)
        leaving = event.event != "room_finished"
        if call.status is CallStatus.RINGING:
            if leaving and user_id == call.caller_user_id:
                call.status = CallStatus.MISSED
                call.missed_reason = MissedReason.CALLER_HUNG_UP
                call.ended_at = now
                call.ended_by_user_id = user_id
                touch(call, now)
                await uow.publish(_event(call, CallStatus.RINGING))
                _after_delete_room(uow, state, call)
                await uow.commit()
                timers.cancel_ring_timeout(call.id)
                return
        elif call.status is CallStatus.CONNECTED:
            if not leaving or user_id in {call.caller_user_id, call.answered_by_user_id}:
                _finish_connected(call, now, ended_by=None)
                await uow.publish(_event(call, CallStatus.CONNECTED))
                _after_delete_room(uow, state, call)
                await uow.commit()
                return
        elif ai_leg_open(_leg(call)) and (
            not leaving or user_id is None or user_id == call.customer_user_id
        ):
            await _end_leg(uow, state, call, now, error=None)
            return
        await uow.commit()


# --- Reads (customers and staff) and tasks --------------------------------------------------------


async def list_my_booking_calls(
    session: AsyncSession, customer: CurrentUser, booking_id: uuid.UUID, page: PageParams
) -> Page[CallRead]:
    await bookings_service.get_customer_booking(session, customer, booking_id=booking_id)
    rows, total = await CallLogRepository(session).page(
        CallLog.booking_id == booking_id,
        CallLog.customer_user_id == customer.id,
        limit=page.limit,
        offset=page.offset,
    )
    return Page.build(await _call_reads(session, rows, staff=False), total=total, params=page)


def _require_staff(ctx: ShopContext) -> None:
    if ctx.role not in STAFF_CALL_ROLES:
        raise Forbidden


async def list_booking_calls(
    session: AsyncSession, ctx: ShopContext, booking_id: uuid.UUID, page: PageParams
) -> Page[CallRead]:
    await bookings_service.get_staff_booking(session, ctx, booking_id=booking_id)
    _require_staff(ctx)
    rows, total = await CallLogRepository(session).page(
        CallLog.shop_id == ctx.shop_id,
        CallLog.booking_id == booking_id,
        limit=page.limit,
        offset=page.offset,
    )
    return Page.build(await _call_reads(session, rows, staff=True), total=total, params=page)


async def list_shop_calls(  # noqa: PLR0913 - the spec'd filters
    session: AsyncSession,
    ctx: ShopContext,
    *,
    status: CallStatus | None,
    direction: CallDirection | None,
    ai_handled: bool | None,
    booking_id: uuid.UUID | None,
    page: PageParams,
) -> Page[CallRead]:
    _require_staff(ctx)
    conditions: list[Any] = [CallLog.shop_id == ctx.shop_id]
    if status is not None:
        conditions.append(CallLog.status == status)
    if direction is not None:
        conditions.append(CallLog.direction == direction)
    if ai_handled is not None:
        handled = CallLog.ai_answered_at.is_not(None)
        conditions.append(handled if ai_handled else ~handled)
    if booking_id is not None:
        conditions.append(CallLog.booking_id == booking_id)
    rows, total = await CallLogRepository(session).page(
        *conditions, limit=page.limit, offset=page.offset
    )
    return Page.build(await _call_reads(session, rows, staff=True), total=total, params=page)


async def get_call_detail(
    session: AsyncSession, ctx: ShopContext, call_id: uuid.UUID
) -> CallDetailRead:
    call = await CallLogRepository(session).get(call_id)
    if call is None or call.shop_id != ctx.shop_id or ctx.role not in STAFF_CALL_ROLES:
        raise NotFound
    base = (await _call_reads(session, [call], staff=True))[0]
    summary = await SummaryRepository(session).for_call(call.id)
    tasks = await _task_reads(session, await TaskRepository(session).for_calls([call.id]))
    return CallDetailRead(
        **base.model_dump(),
        identity_method=call.ai_identity_method,
        summary=SummaryRead(
            intent=summary.intent,
            intent_category=summary.intent_category,
            details=summary.details,
            sentiment=summary.sentiment,
            is_urgent=summary.is_urgent,
            language=summary.language,
            is_fallback=summary.is_fallback,
            transcript=[TranscriptEntry.model_validate(entry) for entry in summary.transcript],
            created_at=summary.created_at,
        )
        if summary
        else None,
        tasks=tasks,
    )


async def list_tasks(
    session: AsyncSession,
    ctx: ShopContext,
    *,
    status: TaskStatus,
    kinds: Sequence[TaskKind],
    page: PageParams,
) -> Page[TaskRead]:
    _require_staff(ctx)
    rows, total = await TaskRepository(session).page(
        shop_id=ctx.shop_id, status=status, kinds=kinds, limit=page.limit, offset=page.offset
    )
    return Page.build(await _task_reads(session, rows), total=total, params=page)


async def mark_task_done(
    uow: UnitOfWork, ctx: ShopContext, task_id: uuid.UUID, note: str | None
) -> TaskRead:
    """Idempotent: a task already done is returned unchanged (the first closer is kept)."""
    if ctx.role not in STAFF_CALL_ROLES:
        raise NotFound
    task = await TaskRepository(uow.session).lock(shop_id=ctx.shop_id, task_id=task_id)
    if task is None:
        raise NotFound
    if task.status is TaskStatus.OPEN:
        now = utcnow()
        task.status = TaskStatus.DONE
        task.done_at = now
        task.done_by_user_id = ctx.user.id
        task.done_note = note
        touch(task, now)
    await uow.commit()
    return (await _task_reads(uow.session, [task]))[0]


# --- Tasks and summaries (A3-A6, §6.3, §6.4) ------------------------------------------------------


async def _insert_task(  # noqa: PLR0913 - one argument per task column the rule decides
    uow: UnitOfWork,
    call: CallLog,
    *,
    kind: TaskKind,
    title: str,
    description: str | None,
    is_urgent: bool,
    metadata: dict[str, Any],
    now: datetime,
) -> Task:
    task = Task(
        id=uuid.uuid4(),
        shop_id=call.shop_id,
        booking_id=call.booking_id,
        call_log_id=call.id,
        customer_user_id=call.customer_user_id,
        kind=kind,
        title=title,
        description=description,
        is_urgent=is_urgent,
        status=TaskStatus.OPEN,
        metadata_=metadata,
        created_at=now,
        updated_at=now,
    )
    TaskRepository(uow.session).add(task)
    await uow.session.flush()
    labels = await bookings_service.get_booking_labels(
        uow.session, shop_id=call.shop_id, booking_ids=[call.booking_id]
    )
    await uow.publish(
        AiTaskCreated(
            occurred_at=now,
            shop_id=call.shop_id,
            task_id=task.id,
            call_id=call.id,
            booking_id=call.booking_id,
            booking_reference=labels[call.booking_id].reference,
            kind=kind,
            title=title,
            is_urgent=is_urgent,
        )
    )
    return task


def _insert_summary(
    uow: UnitOfWork,
    call: CallLog,
    fields: SummaryFields,
    *,
    transcript: list[dict[str, Any]],
    model: str | None,
    now: datetime,
) -> AiCallSummary:
    summary = AiCallSummary(
        id=uuid.uuid4(),
        shop_id=call.shop_id,
        call_log_id=call.id,
        booking_id=call.booking_id,
        customer_user_id=call.customer_user_id,
        intent=fields.intent,
        intent_category=fields.intent_category,
        details=fields.details,
        sentiment=fields.sentiment,
        is_urgent=fields.urgent,
        language=fields.language,
        transcript=transcript,
        is_fallback=fields.is_fallback,
        model=None if fields.is_fallback else model,
        created_at=now,
    )
    SummaryRepository(uow.session).add(summary)
    return summary


# --- The agent's use cases (internal routes; scope from the call row, §5.1) -----------------------


def token_hash(call_token: str) -> str:
    return hashlib.sha256(call_token.encode()).hexdigest()


async def find_agent_call(session: AsyncSession, call_id: uuid.UUID, call_token: str) -> CallLog:
    """§5.1 per-call token and AI-call checks (404); the service token is checked by the route."""
    call = await CallLogRepository(session).get(call_id)
    if (
        call is None
        or call.ai_dispatched_at is None
        or call.ai_call_token_hash is None
        or not secrets.compare_digest(call.ai_call_token_hash, token_hash(call_token))
    ):
        raise NotFound
    return call


def require_open_leg(call: CallLog) -> None:
    """Data and task routes: only while the AI leg has not ended (409)."""
    if call.ai_ended_at is not None:
        raise CallNotActive


def require_verified(call: CallLog) -> None:
    if call.ai_identity_verified_at is None:
        raise IdentityNotVerified


async def start_ai_session(uow: UnitOfWork, call_id: uuid.UUID) -> SessionStartRead:
    """A2: only from `CONNECTING`; no customer data before verification."""
    call = await CallLogRepository(uow.session).lock(call_id)
    if call is None:
        raise NotFound
    if ai_leg_status(_leg(call)) is not AiLegStatus.CONNECTING:
        raise CallNotActive
    now = utcnow()
    call.ai_answered_at = now
    touch(call, now)
    await uow.publish(_event(call, CallStatus.MISSED))
    await uow.commit()
    shops = await shops_service.get_shop_briefs(uow.session, shop_ids=[call.shop_id])
    shop = shops[call.shop_id]
    return SessionStartRead(
        shop=AgentShopBrief(name=shop.name, city=shop.city, timezone=shop.timezone),
        max_ai_seconds=AI_MAX_CALL_SECONDS,
    )


async def _customer_references(session: AsyncSession, call: CallLog) -> list[tuple[str, uuid.UUID]]:
    bookings = await bookings_service.find_customer_bookings(
        session, shop_id=call.shop_id, customer_user_id=call.customer_user_id, limit=50
    )
    return [(booking.reference, booking.id) for booking in bookings]


async def verify_caller(
    uow: UnitOfWork, call_id: uuid.UUID, body: VerifyCallerRequest
) -> VerifyCallerRead:
    """§4.2: compare only with the dispatched customer; 3 failures lock the caller out."""
    session = uow.session
    call = await CallLogRepository(session).lock(call_id)
    if call is None:
        raise NotFound
    require_open_leg(call)
    customer = await _user(session, call.customer_user_id)
    labels = await bookings_service.get_booking_labels(
        session, shop_id=call.shop_id, booking_ids=[call.booking_id]
    )
    call_reference = labels[call.booking_id].reference

    def verified_read() -> VerifyCallerRead:
        return VerifyCallerRead(
            verified=True,
            method=call.ai_identity_method,
            attempts_left=MAX_IDENTITY_ATTEMPTS - call.ai_identity_attempts,
            locked=False,
            first_name=caller_match.first_name(customer.full_name),
            call_booking_reference=call_reference,
        )

    if call.ai_identity_verified_at is not None:
        await uow.commit()
        return verified_read()
    if call.ai_identity_attempts >= MAX_IDENTITY_ATTEMPTS:
        await uow.commit()
        return VerifyCallerRead(verified=False, method=None, attempts_left=0, locked=True)
    references = await _customer_references(session, call)
    method = caller_match.match(
        caller_match.Claim(
            name=body.name,
            phone=body.phone,
            email=body.email,
            booking_reference=body.booking_reference,
        ),
        caller_match.Customer(
            full_name=customer.full_name,
            email=customer.email,
            phone=customer.phone,
            references=caller_match.known_references(ref for ref, _ in references),
        ),
    )
    now = utcnow()
    if method is not None:
        call.ai_identity_verified_at = now
        call.ai_identity_method = method
        touch(call, now)
        await uow.commit()
        return verified_read()
    call.ai_identity_attempts += 1
    touch(call, now)
    await uow.commit()
    left = max(0, MAX_IDENTITY_ATTEMPTS - call.ai_identity_attempts)
    return VerifyCallerRead(verified=False, method=None, attempts_left=left, locked=left == 0)


async def _shop_zone(session: AsyncSession, shop_id: uuid.UUID) -> str:
    return (await shops_service.get_shop_briefs(session, shop_ids=[shop_id]))[shop_id].timezone


def _local(moment: datetime, zone: str) -> str:
    local = moment.astimezone(ZoneInfo(zone))
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{local:%A} {local.day} {local:%B %Y}, {hour}:{local:%M} {local:%p}"


async def get_agent_shop(session: AsyncSession, call: CallLog) -> AgentShopRead:
    profile = await shops_service.get_shop_profile(session, shop_id=call.shop_id)
    return AgentShopRead(
        name=profile.name,
        city=profile.city,
        address=profile.address,
        phone=profile.phone,
        working_hours=[
            AgentHours(
                weekday=WEEKDAYS[day.weekday],
                open=None if day.is_closed else day.opens_at,
                close=None if day.is_closed else day.closes_at,
            )
            for day in profile.working_hours
        ],
        services=[service.name for service in profile.services if service.is_active],
    )


async def list_agent_bookings(session: AsyncSession, call: CallLog) -> AgentBookingList:
    require_verified(call)
    bookings = await bookings_service.find_customer_bookings(
        session,
        shop_id=call.shop_id,
        customer_user_id=call.customer_user_id,
        limit=MAX_AGENT_BOOKINGS,
    )
    zone = await _shop_zone(session, call.shop_id)
    items = [
        AgentBookingItem(
            reference=booking.reference,
            vehicle=f"{booking.vehicle.year} {booking.vehicle.make} {booking.vehicle.model}"
            f" ({booking.vehicle.registration_number})",
            status=booking.status.value,
            status_label=CUSTOMER_STATUS_LABELS[booking.status],
            appointment_local=_local(booking.slot_start, zone),
            is_call_booking=booking.id == call.booking_id,
        )
        for booking in bookings
    ]
    return AgentBookingList(items=items, total=len(items))


async def _scoped_booking_id(session: AsyncSession, call: CallLog, reference: str) -> uuid.UUID:
    wanted = caller_match.normalise_reference(reference)
    for known, booking_id in await _customer_references(session, call):
        if caller_match.normalise_reference(known) == wanted:
            return booking_id
    raise NotFound


async def get_agent_booking(
    session: AsyncSession, call: CallLog, reference: str
) -> AgentBookingRead:
    require_verified(call)
    booking_id = await _scoped_booking_id(session, call, reference)
    customer = await _user(session, call.customer_user_id)
    actor = CurrentUser(id=customer.id, email=customer.email, full_name=customer.full_name)
    detail = await bookings_service.get_customer_booking(session, actor, booking_id=booking_id)
    zone = await _shop_zone(session, call.shop_id)
    vehicle = detail.vehicle
    estimate = detail.estimate
    return AgentBookingRead(
        reference=detail.reference,
        vehicle=f"{vehicle.year} {vehicle.make} {vehicle.model} ({vehicle.registration_number})",
        status=detail.status.value,
        status_label=CUSTOMER_STATUS_LABELS[detail.status],
        appointment_local=_local(detail.slot_start, zone),
        is_call_booking=detail.id == call.booking_id,
        services=[service.name for service in detail.services],
        is_ready_for_pickup=detail.status.value == "READY_FOR_PICKUP",
        customer_actions=[str(slug) for slug in detail.allowed_actions],
        last_update_local=_local(detail.status_changed_at, zone),
        estimate=AgentEstimateBrief(
            version=estimate.version, status=estimate.status.value, grand_total=estimate.grand_total
        )
        if estimate
        else None,
    )


async def get_agent_estimate(
    session: AsyncSession, call: CallLog, reference: str
) -> AgentEstimateRead:
    require_verified(call)
    booking_id = await _scoped_booking_id(session, call, reference)
    customer = await _user(session, call.customer_user_id)
    actor = CurrentUser(id=customer.id, email=customer.email, full_name=customer.full_name)
    detail = await bookings_service.get_customer_booking(session, actor, booking_id=booking_id)
    estimate = detail.estimate
    if estimate is None:
        return AgentEstimateRead(
            reference=detail.reference,
            has_estimate=False,
            revision_in_progress=detail.estimate_revision_in_progress,
        )
    return AgentEstimateRead(
        reference=detail.reference,
        has_estimate=True,
        version=estimate.version,
        status=estimate.status.value,
        lines=[
            AgentEstimateLine(
                type=line.line_type.value,
                description=line.description,
                quantity=line.quantity,
                line_total=line.line_total,
            )
            for line in estimate.lines
        ],
        parts_total=estimate.parts_total,
        labour_total=estimate.labour_total,
        grand_total=estimate.grand_total,
        revision_in_progress=detail.estimate_revision_in_progress,
    )


async def list_agent_slots(
    session: AsyncSession, call: CallLog, *, date_from: date, days: int
) -> AgentSlotsRead:
    zone = await _shop_zone(session, call.shop_id)
    slots = await scheduling_service.list_open_slots(
        session, shop_id=call.shop_id, date_from=date_from, days=days, limit=MAX_SLOTS
    )
    return AgentSlotsRead(
        timezone=zone,
        slots=[
            AgentSlot(start=slot.slot_start, start_local=_local(slot.slot_start, zone))
            for slot in slots
        ],
    )


def _invalid(field: str, message: str) -> ValidationFailed:
    return ValidationFailed(errors=[FieldError(field=field, code="value_error", message=message)])


async def create_agent_task(
    uow: UnitOfWork, call_id: uuid.UUID, body: AgentTaskCreate
) -> AgentTaskRead:
    """§6.4: one task per (call, kind); a repeat updates the description and metadata."""
    session = uow.session
    call = await CallLogRepository(session).lock(call_id)
    if call is None:
        raise NotFound
    require_open_leg(call)
    customer = await _user(session, call.customer_user_id)
    first = caller_match.first_name(customer.full_name)
    verified = call.ai_identity_verified_at is not None
    metadata: dict[str, Any] = {"caller_verified": verified, "source_tool": body.kind.value}
    if body.kind is TaskKind.RESCHEDULE_REQUEST:
        require_verified(call)
        if not body.booking_reference:
            raise _invalid("booking_reference", "A booking reference is required.")
        await _scoped_booking_id(session, call, body.booking_reference)
        starts = body.preferred_starts or []
        if not 1 <= len(starts) <= 3:  # noqa: PLR2004 - spec 05 §5.2: 1-3 preferred starts
            raise _invalid("preferred_starts", "Give one to three preferred times.")
        for start in starts:
            if not await scheduling_service.is_slot_open(
                session, shop_id=call.shop_id, slot_start=start
            ):
                raise _invalid("preferred_starts", "That time is no longer available.")
        reference = caller_match.normalise_reference(body.booking_reference)
        metadata |= {
            "booking_reference": reference,
            "preferred_starts": [start.isoformat() for start in starts],
        }
        title, urgent = reschedule_title(first, reference), False
    elif body.kind is TaskKind.ESCALATION:
        metadata["safety_concern"] = body.safety_concern
        title, urgent = escalation_title(first, body.topic or "asked for a person"), True
    else:
        title, urgent = callback_title(first, body.topic or "their booking"), False
    existing = await TaskRepository(session).for_call_and_kind(call.id, body.kind)
    now = utcnow()
    if existing is not None:
        previous = existing.metadata_ or {}
        if previous.get("safety_concern"):  # a repeat never downgrades a safety escalation
            metadata["safety_concern"] = True
        existing.description = body.description
        existing.metadata_ = {**previous, **metadata}
        touch(existing, now)
        await uow.commit()
        return AgentTaskRead(task_id=existing.id, created=False)
    task = await _insert_task(
        uow,
        call,
        kind=body.kind,
        title=title,
        description=body.description,
        is_urgent=urgent,
        metadata=metadata,
        now=now,
    )
    await uow.commit()
    return AgentTaskRead(task_id=task.id, created=True)


async def end_ai_leg(uow: UnitOfWork, call_id: uuid.UUID, error: str | None) -> None:
    """A3 by the agent (`end_call`, or a model error); idempotent."""
    call = await CallLogRepository(uow.session).lock(call_id)
    if call is None:
        raise NotFound
    await _end_leg(uow, _state(uow), call, utcnow(), error=error)


def _summary_fields(body: SummaryPost) -> SummaryFields:
    """§6.3 step 4: the agent's summary under the API's own limits, or the fallback."""
    try:
        parsed = AgentSummaryIn.model_validate(body.summary) if body.summary else None
    except ValidationError:
        parsed = None
    if parsed is None:
        return FALLBACK_SUMMARY
    return SummaryFields(
        intent=parsed.intent,
        intent_category=parsed.intent_category,
        details=parsed.details,
        sentiment=parsed.sentiment,
        follow_up_task_title=parsed.follow_up_task_title,
        urgent=parsed.urgent or parsed.intent_category is CallIntent.SAFETY_CONCERN,
        language=parsed.language,
        is_fallback=False,
    )


async def _post_call_task(
    uow: UnitOfWork, call: CallLog, body: SummaryPost, fields: SummaryFields, now: datetime
) -> None:
    """§6.3 step 6: every AI call ends with at least one task."""
    if await TaskRepository(uow.session).count_for_call(call.id):
        return
    first = caller_match.first_name((await _user(uow.session, call.customer_user_id)).full_name)
    metadata = {"caller_verified": call.ai_identity_verified_at is not None}
    spoke = any(entry.role == "customer" and entry.text.strip() for entry in body.transcript)
    if not spoke:
        kind, title, description = TaskKind.CALLBACK, left_early_callback_title(first), None
    elif fields.is_fallback:
        kind, title, description = TaskKind.FOLLOW_UP, callback_title(first, "their call"), None
    else:
        kind = TaskKind.FOLLOW_UP
        title, description = follow_up_title(fields.follow_up_task_title), fields.details
    await _insert_task(
        uow,
        call,
        kind=kind,
        title=title,
        description=description,
        is_urgent=fields.urgent and spoke,
        metadata=metadata,
        now=now,
    )


def _checked_transcript(body: SummaryPost) -> list[dict[str, Any]]:
    transcript = [entry.model_dump(mode="json", exclude_none=True) for entry in body.transcript]
    if len(transcript) > MAX_TRANSCRIPT_ENTRIES:
        raise _invalid("transcript", f"At most {MAX_TRANSCRIPT_ENTRIES} entries.")
    if len(json.dumps(transcript).encode()) > MAX_TRANSCRIPT_BYTES:
        raise _invalid("transcript", "The transcript is too large.")
    return transcript


async def record_ai_summary(
    uow: UnitOfWork, call_id: uuid.UUID, body: SummaryPost
) -> tuple[SummaryStored, bool]:
    """A5 (§6.3); returns the stored summary and whether it was created now (idempotent)."""
    session = uow.session
    call = await CallLogRepository(session).lock(call_id)
    if call is None:
        raise NotFound
    now = utcnow()
    window = timedelta(seconds=SUMMARY_WINDOW_SECONDS)
    if call.ai_ended_at is not None and now > call.ai_ended_at + window:
        raise CallNotActive
    transcript = _checked_transcript(body)
    existing = await SummaryRepository(session).for_call(call.id)
    created = existing is None
    if existing is None:
        if call.ai_ended_at is None:  # A3: the customer simply left
            call.ai_ended_at = now
            if call.ai_answered_at is not None:
                call.ai_duration_seconds = seconds_between(call.ai_answered_at, now)
            touch(call, now)
        fields = _summary_fields(body)
        existing = _insert_summary(
            uow, call, fields, transcript=transcript, model=body.model, now=now
        )
        await _post_call_task(uow, call, body, fields, now)
    await uow.commit()
    tasks = await TaskRepository(session).for_calls([call.id])
    stored = SummaryStored(
        summary_id=existing.id,
        is_fallback=existing.is_fallback,
        task_ids=[task.id for task in tasks],
    )
    return stored, created

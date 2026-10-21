"""Data access of the calls module (`modules/calls.md` "Files").

Every write locks only its `call_logs` row (`FOR UPDATE`); the sweeper claims rows with
`SKIP LOCKED`. No booking row is ever locked here (§3.9).
"""

import uuid
from collections.abc import Collection, Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calls.models import AiCallSummary, CallLog, Task
from app.shared.enums import CallDirection, CallStatus, TaskKind, TaskStatus

_ACTIVE = or_(
    CallLog.status.in_([CallStatus.RINGING, CallStatus.CONNECTED]),
    and_(CallLog.ai_dispatched_at.is_not(None), CallLog.ai_ended_at.is_(None)),
)


class CallLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, call: CallLog) -> None:
        self.session.add(call)

    async def get(self, call_id: uuid.UUID) -> CallLog | None:
        call: CallLog | None = await self.session.get(CallLog, call_id)
        return call

    async def lock(self, call_id: uuid.UUID) -> CallLog | None:
        call: CallLog | None = await self.session.scalar(
            select(CallLog).where(CallLog.id == call_id).with_for_update()
        )
        return call

    async def busy_user_ids(self, user_ids: Collection[uuid.UUID]) -> set[uuid.UUID]:
        """Users who are the caller or answerer of an active call, or the customer of an open AI
        leg (C1's busy check)."""
        if not user_ids:
            return set()
        wanted = set(user_ids)
        rows = await self.session.execute(
            select(CallLog.caller_user_id, CallLog.answered_by_user_id, CallLog.customer_user_id)
            .where(_ACTIVE)
            .where(
                or_(
                    CallLog.caller_user_id.in_(wanted),
                    CallLog.answered_by_user_id.in_(wanted),
                    CallLog.customer_user_id.in_(wanted),
                )
            )
        )
        busy: set[uuid.UUID] = set()
        for caller, answerer, customer in rows:
            busy |= {caller, customer} if answerer is None else {caller, answerer, customer}
        return busy & wanted

    async def connected_user_ids(self, user_ids: Collection[uuid.UUID]) -> set[uuid.UUID]:
        """Callees in a `CONNECTED` call are not rung (§3.3)."""
        if not user_ids:
            return set()
        wanted = set(user_ids)
        rows = await self.session.execute(
            select(CallLog.caller_user_id, CallLog.answered_by_user_id).where(
                CallLog.status == CallStatus.CONNECTED
            )
        )
        return {user for row in rows for user in row if user in wanted}

    async def booking_busy(self, booking_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            select(CallLog.id).where(CallLog.booking_id == booking_id, _ACTIVE).limit(1)
        )
        return found is not None

    async def starts_since(self, *, caller_user_id: uuid.UUID, since: datetime) -> list[datetime]:
        rows = await self.session.scalars(
            select(CallLog.started_at)
            .where(CallLog.caller_user_id == caller_user_id, CallLog.started_at > since)
            .order_by(CallLog.started_at)
        )
        return list(rows)

    async def started_since(self, since: datetime) -> Sequence[CallLog]:
        rows = await self.session.scalars(select(CallLog).where(CallLog.started_at >= since))
        return rows.all()

    async def ai_legs_since(self, since: datetime) -> int:
        count = await self.session.scalar(
            select(func.count()).select_from(CallLog).where(CallLog.ai_dispatched_at >= since)
        )
        return int(count or 0)

    async def page(
        self, *conditions: ColumnElement[bool], limit: int, offset: int
    ) -> tuple[Sequence[CallLog], int]:
        query = select(CallLog).where(*conditions)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.scalars(
            query.order_by(CallLog.started_at.desc(), CallLog.id.desc()).limit(limit).offset(offset)
        )
        return rows.all(), int(total or 0)

    async def ringing_for(self, user_id: uuid.UUID) -> Sequence[CallLog]:
        rows = await self.session.scalars(
            select(CallLog).where(
                CallLog.status == CallStatus.RINGING, CallLog.rung_user_ids.contains([user_id])
            )
        )
        return rows.all()

    async def ringing_eligible(
        self, *, shop_ids: Collection[uuid.UUID], customer_user_id: uuid.UUID
    ) -> Sequence[CallLog]:
        """Ringing calls a just-connected user may answer: C2S calls of their shops (eligibility
        is checked by the caller) and S2C calls to them."""
        conditions = [CallLog.customer_user_id == customer_user_id]
        if shop_ids:
            conditions.append(
                and_(
                    CallLog.shop_id.in_(set(shop_ids)),
                    CallLog.direction == CallDirection.CUSTOMER_TO_SHOP,
                )
            )
        rows = await self.session.scalars(
            select(CallLog).where(CallLog.status == CallStatus.RINGING, or_(*conditions))
        )
        return rows.all()

    # --- Sweeper claims (FOR UPDATE SKIP LOCKED) ---

    async def _claim(self, *conditions: ColumnElement[bool]) -> list[uuid.UUID]:
        rows = await self.session.scalars(
            select(CallLog.id).where(*conditions).with_for_update(skip_locked=True).limit(50)
        )
        return list(rows)

    async def claim_expired_ringing(self, now: datetime) -> list[uuid.UUID]:
        return await self._claim(CallLog.status == CallStatus.RINGING, CallLog.ring_deadline <= now)

    async def claim_unjoined_legs(self, before: datetime) -> list[uuid.UUID]:
        return await self._claim(
            CallLog.ai_dispatched_at.is_not(None),
            CallLog.ai_answered_at.is_(None),
            CallLog.ai_ended_at.is_(None),
            CallLog.ai_dispatched_at <= before,
        )

    async def claim_long_connected(self, before: datetime) -> list[uuid.UUID]:
        return await self._claim(
            CallLog.status == CallStatus.CONNECTED, CallLog.answered_at <= before
        )

    async def claim_long_ai_legs(self, before: datetime) -> list[uuid.UUID]:
        return await self._claim(
            CallLog.ai_answered_at.is_not(None),
            CallLog.ai_ended_at.is_(None),
            CallLog.ai_answered_at <= before,
        )

    async def claim_unsummarised(self, before: datetime) -> list[uuid.UUID]:
        summarised = select(AiCallSummary.call_log_id)
        return await self._claim(
            CallLog.ai_answered_at.is_not(None),
            CallLog.ai_ended_at.is_not(None),
            CallLog.ai_ended_at <= before,
            CallLog.id.not_in(summarised),
        )


class SummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, summary: AiCallSummary) -> None:
        self.session.add(summary)

    async def for_call(self, call_id: uuid.UUID) -> AiCallSummary | None:
        summary: AiCallSummary | None = await self.session.scalar(
            select(AiCallSummary).where(AiCallSummary.call_log_id == call_id)
        )
        return summary

    async def for_calls(self, call_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, AiCallSummary]:
        if not call_ids:
            return {}
        rows = await self.session.scalars(
            select(AiCallSummary).where(AiCallSummary.call_log_id.in_(set(call_ids)))
        )
        return {row.call_log_id: row for row in rows}


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, task: Task) -> None:
        self.session.add(task)

    async def for_call_and_kind(self, call_id: uuid.UUID, kind: TaskKind) -> Task | None:
        task: Task | None = await self.session.scalar(
            select(Task).where(Task.call_log_id == call_id, Task.kind == kind)
        )
        return task

    async def count_for_call(self, call_id: uuid.UUID) -> int:
        count = await self.session.scalar(
            select(func.count()).select_from(Task).where(Task.call_log_id == call_id)
        )
        return int(count or 0)

    async def for_calls(self, call_ids: Collection[uuid.UUID]) -> list[Task]:
        if not call_ids:
            return []
        rows = await self.session.scalars(
            select(Task).where(Task.call_log_id.in_(set(call_ids))).order_by(Task.created_at)
        )
        return list(rows)

    async def lock(self, *, shop_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        task: Task | None = await self.session.scalar(
            select(Task).where(Task.shop_id == shop_id, Task.id == task_id).with_for_update()
        )
        return task

    async def get(self, *, shop_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        task: Task | None = await self.session.scalar(
            select(Task).where(Task.shop_id == shop_id, Task.id == task_id)
        )
        return task

    async def page(
        self,
        *,
        shop_id: uuid.UUID,
        status: TaskStatus,
        kinds: Collection[TaskKind],
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Task], int]:
        query = select(Task).where(Task.shop_id == shop_id, Task.status == status)
        if kinds:
            query = query.where(Task.kind.in_(set(kinds)))
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.scalars(
            query.order_by(Task.is_urgent.desc(), Task.created_at.desc(), Task.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return rows.all(), int(total or 0)

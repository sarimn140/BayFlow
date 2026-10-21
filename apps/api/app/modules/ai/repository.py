"""Data access of the ai module (modules/ai.md "Tables")."""

import uuid
from collections.abc import Collection, Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.models import AiAuditEvent, AiDraft
from app.shared.enums import AiDraftStatus, AiFeature


class AiAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, event: AiAuditEvent) -> None:
        self.session.add(event)

    async def count_since(self, *, shop_id: uuid.UUID, since: datetime) -> int:
        count = await self.session.scalar(
            select(func.count())
            .select_from(AiAuditEvent)
            .where(AiAuditEvent.shop_id == shop_id, AiAuditEvent.created_at >= since)
        )
        return int(count or 0)


class AiDraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, draft: AiDraft) -> None:
        self.session.add(draft)

    async def get(self, *, shop_id: uuid.UUID, draft_id: uuid.UUID) -> AiDraft | None:
        draft: AiDraft | None = await self.session.scalar(
            select(AiDraft).where(AiDraft.shop_id == shop_id, AiDraft.id == draft_id)
        )
        return draft

    async def lock(self, *, shop_id: uuid.UUID, draft_id: uuid.UUID) -> AiDraft | None:
        draft: AiDraft | None = await self.session.scalar(
            select(AiDraft)
            .where(AiDraft.shop_id == shop_id, AiDraft.id == draft_id)
            .with_for_update()
        )
        return draft

    async def page(
        self,
        *,
        shop_id: uuid.UUID,
        features: Collection[AiFeature],
        status: AiDraftStatus | None,
        requested_by: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[AiDraft], int]:
        query = select(AiDraft).where(AiDraft.shop_id == shop_id, AiDraft.feature.in_(features))
        if status is not None:
            query = query.where(AiDraft.status == status)
        if requested_by is not None:
            query = query.where(AiDraft.requested_by_user_id == requested_by)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.scalars(
            query.order_by(AiDraft.created_at.desc(), AiDraft.id.desc()).limit(limit).offset(offset)
        )
        return rows.all(), int(total or 0)

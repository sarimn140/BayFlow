"""SQL for the qc module's tables: `qc_inspections` and `qc_issues` (spec 02 §3.18-§3.19).

Every method takes a keyword-only `shop_id` and filters by it (D20), so another shop's booking id
simply matches nothing. No qc row is ever locked: every QC write runs inside a booking action that
already holds the booking row lock, which serialises the QC writes of that booking (spec 02 §7.2).
"""

import uuid
from collections.abc import Collection
from datetime import datetime

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import AlreadyPicked
from app.modules.qc.models import QcInspection, QcIssue
from app.shared.enums import QcIssueStatus
from app.shared.repository import ShopScopedRepository, constraint_name

# The database backstop for "first QC inspector to pick wins" (T18, D30; spec 02 §7.5).
ONE_OPEN_ROUND_PER_BOOKING = "uq_qc_inspections_one_open_per_booking"


class QcInspectionRepository(ShopScopedRepository):
    """`qc_inspections`: one row per QC round of a booking."""

    async def insert_open_round(self, inspection: QcInspection) -> None:
        """Insert a new open round (`result IS NULL`) inside a savepoint.

        A second open round of the same booking violates `uq_qc_inspections_one_open_per_booking`
        -> 409 `ALREADY_PICKED`; the savepoint keeps the caller's transaction usable after that
        refusal. Every other integrity error propagates unchanged — e.g. the composite tenant FK
        (D20) refusing a booking of another shop, which only a tenant-scoping bug in the caller can
        reach — so the global handler logs it and answers 500 (spec 03 §2.4: unmapped -> 500).
        """
        try:
            async with self.session.begin_nested():
                self.session.add(inspection)
                await self.session.flush()
        except IntegrityError as error:
            if constraint_name(error) == ONE_OPEN_ROUND_PER_BOOKING:
                raise AlreadyPicked from error
            raise

    async def get_open_round(
        self, *, shop_id: uuid.UUID, booking_id: uuid.UUID
    ) -> QcInspection | None:
        """The booking's open round (at most one, by the partial unique index), freshly read."""
        statement = (
            select(QcInspection)
            .where(
                QcInspection.shop_id == shop_id,
                QcInspection.booking_id == booking_id,
                QcInspection.result.is_(None),
            )
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_rounds(self, *, shop_id: uuid.UUID, booking_id: uuid.UUID) -> list[QcInspection]:
        """Every round of the booking, oldest first by `(picked_at, id)` (`modules/qc.md`)."""
        statement = (
            select(QcInspection)
            .where(QcInspection.shop_id == shop_id, QcInspection.booking_id == booking_id)
            .order_by(QcInspection.picked_at, QcInspection.id)
        )
        return list((await self.session.execute(statement)).scalars())

    async def count_rounds(
        self, *, shop_id: uuid.UUID, booking_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Rounds per booking, for the given bookings only (bookings without rounds are absent)."""
        statement = (
            select(QcInspection.booking_id, func.count())
            .where(QcInspection.shop_id == shop_id, QcInspection.booking_id.in_(booking_ids))
            .group_by(QcInspection.booking_id)
        )
        return dict((await self.session.execute(statement)).all())

    async def booking_ids_inspected_by(
        self, *, shop_id: uuid.UUID, inspector_user_id: uuid.UUID
    ) -> frozenset[uuid.UUID]:
        """Bookings of the shop with a round by this inspector (D21; any result, open included)."""
        statement = (
            select(QcInspection.booking_id)
            .where(
                QcInspection.shop_id == shop_id,
                QcInspection.inspector_user_id == inspector_user_id,
            )
            .distinct()
        )
        return frozenset((await self.session.execute(statement)).scalars())

    async def has_round_by(
        self, *, shop_id: uuid.UUID, booking_id: uuid.UUID, inspector_user_id: uuid.UUID
    ) -> bool:
        statement = select(
            exists().where(
                QcInspection.shop_id == shop_id,
                QcInspection.booking_id == booking_id,
                QcInspection.inspector_user_id == inspector_user_id,
            )
        )
        return bool((await self.session.execute(statement)).scalar_one())

    async def inspector_ids(
        self, *, shop_id: uuid.UUID, booking_id: uuid.UUID
    ) -> frozenset[uuid.UUID]:
        """Everyone who inspected the booking (any round, any result)."""
        statement = (
            select(QcInspection.inspector_user_id)
            .where(QcInspection.shop_id == shop_id, QcInspection.booking_id == booking_id)
            .distinct()
        )
        return frozenset((await self.session.execute(statement)).scalars())


class QcIssueRepository(ShopScopedRepository):
    """`qc_issues`: raised `OPEN` by a failed round, `RESOLVED` by the next `send-to-qc`."""

    async def resolve_open(
        self,
        *,
        shop_id: uuid.UUID,
        booking_id: uuid.UUID,
        resolved_by_user_id: uuid.UUID,
        now: datetime,
    ) -> list[uuid.UUID]:
        """T17: every `OPEN` issue of this booking -> `RESOLVED`, in one statement.

        Returns the resolved ids, oldest issue first by `(created_at, id)` (possibly none).
        """
        statement = (
            update(QcIssue)
            .where(
                QcIssue.shop_id == shop_id,
                QcIssue.booking_id == booking_id,
                QcIssue.status == QcIssueStatus.OPEN,
            )
            .values(
                status=QcIssueStatus.RESOLVED,
                resolved_at=now,
                resolved_by_user_id=resolved_by_user_id,
                updated_at=now,
            )
            .returning(QcIssue.id, QcIssue.created_at)
        )
        rows = (await self.session.execute(statement)).all()
        return [issue_id for _, issue_id in sorted((created, id_) for id_, created in rows)]

    async def list_issues(self, *, shop_id: uuid.UUID, booking_id: uuid.UUID) -> list[QcIssue]:
        """Every issue of the booking, oldest first by `(created_at, id)`."""
        statement = (
            select(QcIssue)
            .where(QcIssue.shop_id == shop_id, QcIssue.booking_id == booking_id)
            .order_by(QcIssue.created_at, QcIssue.id)
        )
        return list((await self.session.execute(statement)).scalars())

    async def count_open(
        self, *, shop_id: uuid.UUID, booking_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """`OPEN` issues per booking, for the given bookings only (zero counts are absent)."""
        statement = (
            select(QcIssue.booking_id, func.count())
            .where(
                QcIssue.shop_id == shop_id,
                QcIssue.booking_id.in_(booking_ids),
                QcIssue.status == QcIssueStatus.OPEN,
            )
            .group_by(QcIssue.booking_id)
        )
        return dict((await self.session.execute(statement)).all())

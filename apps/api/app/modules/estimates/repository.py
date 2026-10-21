"""SQL for the estimates module's tables: `estimates` (one row per version) and `estimate_lines`.

Every method takes a keyword-only `shop_id` (D20) and filters by it, so another shop's ids find
nothing; the one cross-shop read (`latest_for_booking_keys`, the customer's booking list) takes
`(shop_id, booking_id)` pairs and matches every row on its own pair. Writes run inside the
caller's transaction, which already holds the booking row lock (spec 02 §7.2: T05-T12, O1 and
T22 lock the booking only), so this module takes no row locks of its own. Estimate reads refresh
any copy already in the session (`populate_existing`), so a decision is never taken on stale
identity-map data. Unique-index violations (`uq_estimates_*`) map to 409 `CONCURRENT_UPDATE`
through `app.core.db_errors`; with the booking lock held they cannot happen.
"""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, Integer, cast, delete, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import distinct_on

from app.modules.estimates.domain.versions import SUPERSEDABLE_STATUSES
from app.modules.estimates.models import Estimate, EstimateLine
from app.shared.enums import EstimateLineType, EstimateStatus
from app.shared.repository import ShopScopedRepository


@dataclass(frozen=True, slots=True)
class SummaryRow:
    """The newest matching version of one booking, with its number of lines."""

    estimate_id: UUID
    booking_id: UUID
    version: int
    status: EstimateStatus
    grand_total: Decimal
    line_count: int


@dataclass(frozen=True, slots=True)
class PartRequirementRow:
    """The total quantity of one part over the `PART` lines of one version."""

    part_id: UUID
    qty: int


class EstimateRepository(ShopScopedRepository):
    async def latest(self, *, shop_id: UUID, booking_id: UUID) -> Estimate | None:
        """The booking's highest version (D39: "the current estimate"), or None."""
        statement = (
            select(Estimate)
            .where(Estimate.shop_id == shop_id, Estimate.booking_id == booking_id)
            .order_by(Estimate.version.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def newest_with_status(
        self, *, shop_id: UUID, booking_id: UUID, status: EstimateStatus
    ) -> Estimate | None:
        """The newest version in `status`. `SENT` and `APPROVED` are unique per booking
        (`uq_estimates_one_open_version_per_booking`, `uq_estimates_one_approved_per_booking`)."""
        statement = (
            select(Estimate)
            .where(
                Estimate.shop_id == shop_id,
                Estimate.booking_id == booking_id,
                Estimate.status == status,
            )
            .order_by(Estimate.version.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_for_booking(
        self,
        *,
        shop_id: UUID,
        booking_id: UUID,
        statuses: Collection[EstimateStatus] | None = None,
    ) -> list[Estimate]:
        """Every version of the booking (optionally only these statuses), ascending `version`."""
        statement = (
            select(Estimate)
            .where(Estimate.shop_id == shop_id, Estimate.booking_id == booking_id)
            .order_by(Estimate.version)
            .execution_options(populate_existing=True)
        )
        if statuses is not None:
            statement = statement.where(Estimate.status.in_(list(statuses)))
        return list((await self.session.scalars(statement)).all())

    async def latest_for_bookings(
        self,
        *,
        shop_id: UUID,
        booking_ids: Collection[UUID],
        statuses: Collection[EstimateStatus] | None = None,
    ) -> list[SummaryRow]:
        """Per booking of one shop, the newest version (optionally among these statuses) and its
        line count, in one query whatever the number of bookings (`DISTINCT ON (booking_id)`)."""
        if not booking_ids:
            return []
        return await self._newest_per_booking(
            [Estimate.shop_id == shop_id, Estimate.booking_id.in_(list(booking_ids))], statuses
        )

    async def latest_for_booking_keys(
        self,
        *,
        booking_keys: Collection[tuple[UUID, UUID]],
        statuses: Collection[EstimateStatus] | None = None,
    ) -> list[SummaryRow]:
        """The same for bookings of several shops (the customer's list): each key is a
        `(shop_id, booking_id)` pair and a row matches only its own pair
        (`(shop_id, booking_id) IN (…)`), so every row stays shop-scoped (D20). One query whatever
        the number of shops."""
        if not booking_keys:
            return []
        pairs = list(dict.fromkeys(booking_keys))
        return await self._newest_per_booking(
            [tuple_(Estimate.shop_id, Estimate.booking_id).in_(pairs)], statuses
        )

    async def _newest_per_booking(
        self,
        criteria: Sequence[ColumnElement[bool]],
        statuses: Collection[EstimateStatus] | None,
    ) -> list[SummaryRow]:
        line_count = (
            select(func.count(EstimateLine.id))
            .where(
                EstimateLine.shop_id == Estimate.shop_id, EstimateLine.estimate_id == Estimate.id
            )
            .correlate(Estimate)
            .scalar_subquery()
        )
        statement = (
            select(
                Estimate.id,
                Estimate.booking_id,
                Estimate.version,
                Estimate.status,
                Estimate.grand_total,
                line_count.label("line_count"),
            )
            .ext(distinct_on(Estimate.booking_id))
            .where(*criteria)
            .order_by(Estimate.booking_id, Estimate.version.desc())
        )
        if statuses is not None:
            statement = statement.where(Estimate.status.in_(list(statuses)))
        rows = (await self.session.execute(statement)).all()
        return [
            SummaryRow(
                estimate_id=row.id,
                booking_id=row.booking_id,
                version=row.version,
                status=row.status,
                grand_total=row.grand_total,
                line_count=row.line_count,
            )
            for row in rows
        ]

    async def supersede_open(self, *, shop_id: UUID, booking_id: UUID, now: datetime) -> list[UUID]:
        """T22: every open version (`DRAFT`, `SUBMITTED`, `SENT`) -> `SUPERSEDED` in one statement;
        `APPROVED` and `REJECTED` stay. A superseded `SENT` version keeps `sent_at`."""
        statement = (
            update(Estimate)
            .where(
                Estimate.shop_id == shop_id,
                Estimate.booking_id == booking_id,
                Estimate.status.in_(list(SUPERSEDABLE_STATUSES)),
            )
            .values(status=EstimateStatus.SUPERSEDED, updated_at=now)
            .returning(Estimate.id)
            .execution_options(synchronize_session="fetch")
        )
        return sorted((await self.session.execute(statement)).scalars().all())


class EstimateLineRepository(ShopScopedRepository):
    async def list_for_estimates(
        self, *, shop_id: UUID, estimate_ids: Collection[UUID]
    ) -> list[EstimateLine]:
        """The lines of these versions, `ORDER BY estimate_id, position` (one query)."""
        if not estimate_ids:
            return []
        statement = (
            select(EstimateLine)
            .where(
                EstimateLine.shop_id == shop_id,
                EstimateLine.estimate_id.in_(list(estimate_ids)),
            )
            .order_by(EstimateLine.estimate_id, EstimateLine.position)
        )
        return list((await self.session.scalars(statement)).all())

    async def delete_for_estimate(self, *, shop_id: UUID, estimate_id: UUID) -> None:
        """Remove every line of one `DRAFT` (the schema's only hard delete, spec 02 §2).

        Runs as its own statement, before the replacement lines are inserted:
        `uq_estimate_lines_estimate_id_position` is checked per row and cannot be deferred.
        """
        statement = delete(EstimateLine).where(
            EstimateLine.shop_id == shop_id, EstimateLine.estimate_id == estimate_id
        )
        await self.session.execute(statement)

    def add_many(self, lines: Iterable[EstimateLine]) -> None:
        self.session.add_all(list(lines))

    async def part_requirements(
        self, *, shop_id: UUID, estimate_id: UUID
    ) -> list[PartRequirementRow]:
        """`SELECT part_id, SUM(quantity)::int … WHERE line_type = 'PART' GROUP BY part_id
        ORDER BY part_id` for one version (T12; a part on several lines is summed)."""
        total = cast(func.sum(EstimateLine.quantity), Integer)
        statement = (
            select(EstimateLine.part_id, total.label("qty"))
            .where(
                EstimateLine.shop_id == shop_id,
                EstimateLine.estimate_id == estimate_id,
                EstimateLine.line_type == EstimateLineType.PART,
                EstimateLine.part_id.is_not(None),
            )
            .group_by(EstimateLine.part_id)
            .order_by(EstimateLine.part_id)
        )
        rows = (await self.session.execute(statement)).all()
        return [PartRequirementRow(part_id=row.part_id, qty=int(row.qty)) for row in rows]

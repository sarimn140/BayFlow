"""Use cases of the estimates module (`modules/estimates.md` §5, §7; D39-D41).

The module has no router: bookings serves every estimate route, locks the booking row, applies
D21 visibility and spec 08's rules, then calls these functions inside the same transaction.

- **Writes are nested.** They run in the caller's `UnitOfWork`, which already holds the booking
  row lock (spec 02 §7.2), so writes for one booking are serialised and no further lock is taken.
  They flush their own statements in the order spec 02 §7.6 requires and never commit. `now` is the
  caller's action instant (D63), written to every timestamp the action touches.
- **Backstops.** Bookings' state machine decides who may act and when; this module still refuses
  to change a frozen version (`ESTIMATE_LOCKED`) or to decide anything but the current `SENT`
  version (`STALE_ESTIMATE`), whatever the caller.
- **Totals** are always recomputed on the server from the lines (D40, D41), never taken from a
  client or trusted from the cache.
- **Reads** run a fixed number of queries whatever the number of versions or bookings.
- **Other modules:** inventory's `get_parts_for_estimate` (catalogue facts and live stock, D40) and
  identity's `get_users_by_ids` (author names); never their tables.
"""

import logging
from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    EstimateEmpty,
    EstimateLocked,
    FieldError,
    InternalError,
    StaleEstimate,
    ValidationFailed,
)
from app.modules.estimates.domain.lines import (
    NUL_NOT_ALLOWED,
    CatalogPart,
    LineError,
    LineInput,
    PricedLine,
    contains_nul,
    inactive_part_errors,
    price_lines,
)
from app.modules.estimates.domain.totals import ZERO, Totals, estimate_totals
from app.modules.estimates.domain.versions import (
    COPYABLE_STATUSES,
    CUSTOMER_VISIBLE_STATUSES,
    DECIDABLE_STATUSES,
    SENDABLE_STATUSES,
    SUBMITTABLE_STATUSES,
    EditDecision,
    customer_shown,
    edit_target,
    revision_in_progress,
)
from app.modules.estimates.models import Estimate, EstimateLine
from app.modules.estimates.repository import (
    EstimateLineRepository,
    EstimateRepository,
    SummaryRow,
)
from app.modules.estimates.schemas import (
    CustomerEstimateLineRead,
    CustomerEstimateRead,
    CustomerEstimateView,
    EstimateEdit,
    EstimateLineRead,
    EstimateLineWrite,
    EstimateRead,
    EstimateSnapshot,
    EstimateSummary,
)
from app.modules.identity import service as identity_service
from app.modules.identity.schemas import UserRef
from app.modules.inventory import service as inventory_service
from app.modules.inventory.domain.stock import PartQty
from app.modules.inventory.schemas import PartStockRef
from app.shared.enums import BookingStatus, EstimateLineType, EstimateStatus
from app.shared.orm import touch
from app.shared.uow import UnitOfWork

logger = logging.getLogger(__name__)

SummaryAudience = Literal["staff", "customer"]
REJECT_REASON_MAX_LENGTH = 500

__all__ = [
    "REJECT_REASON_MAX_LENGTH",
    "SummaryAudience",
    "approve",
    "copy_rejected_to_draft",
    "ensure_draft",
    "get_approved_part_requirements",
    "get_customer_estimate_summaries",
    "get_customer_view",
    "get_estimate_summaries",
    "list_customer_versions",
    "list_versions",
    "reject",
    "replace_lines",
    "send",
    "submit",
    "supersede_open_versions",
]


# --- Helpers --------------------------------------------------------------------------------------


def _snapshot(estimate: Estimate) -> EstimateSnapshot:
    return EstimateSnapshot(
        estimate_id=estimate.id,
        version=estimate.version,
        status=estimate.status,
        grand_total=estimate.grand_total,
    )


def _apply_totals(estimate: Estimate, totals: Totals) -> None:
    estimate.parts_total = totals.parts_total
    estimate.labour_total = totals.labour_total
    estimate.grand_total = totals.grand_total


def _estimate_empty(action: str) -> EstimateEmpty:
    message = f"Add at least one line before {action} the estimate."
    return EstimateEmpty(
        message, errors=[FieldError(field="lines", message=message, code="too_short")]
    )


def _validation_failed(errors: Iterable[LineError]) -> ValidationFailed:
    return ValidationFailed(
        errors=[
            FieldError(field=error.field, message=error.message, code=error.code)
            for error in errors
        ]
    )


def _invariant_breach(message: str, *, shop_id: UUID, booking_id: UUID) -> InternalError:
    """A state the booking lifecycle makes impossible: log it with context, answer a plain 500."""
    logger.error(
        "estimate invariant breached: %s (shop %s, booking %s)", message, shop_id, booking_id
    )
    return InternalError()


def _summaries(rows: Iterable[SummaryRow]) -> dict[UUID, EstimateSummary]:
    return {
        row.booking_id: EstimateSummary(
            estimate_id=row.estimate_id,
            version=row.version,
            status=row.status,
            grand_total=row.grand_total,
            line_count=row.line_count,
        )
        for row in rows
    }


def _group_lines(lines: Iterable[EstimateLine]) -> dict[UUID, list[EstimateLine]]:
    grouped: dict[UUID, list[EstimateLine]] = defaultdict(list)
    for line in lines:
        grouped[line.estimate_id].append(line)
    return grouped


async def _part_refs(
    session: AsyncSession, *, shop_id: UUID, part_ids: Collection[UUID], include_stock: bool
) -> dict[UUID, PartStockRef]:
    """Catalogue facts (+ live stock unless `include_stock` is false) of this shop's parts, in one
    inventory call; unknown and other-shop ids are absent (D20, D40)."""
    if not part_ids:
        return {}
    return await inventory_service.get_parts_for_estimate(
        session, shop_id=shop_id, part_ids=part_ids, include_stock=include_stock
    )


def _catalog(parts: Mapping[UUID, PartStockRef]) -> dict[UUID, CatalogPart]:
    return {
        part_id: CatalogPart(name=part.name, unit_cost=part.unit_cost, is_active=part.is_active)
        for part_id, part in parts.items()
    }


async def _user_refs(session: AsyncSession, estimates: Iterable[Estimate]) -> dict[UUID, UserRef]:
    """`created_by`, `sent_by` and `decided_by` of these versions, in one identity call."""
    user_ids: set[UUID] = set()
    for estimate in estimates:
        user_ids.add(estimate.created_by_user_id)
        user_ids.update(
            user_id
            for user_id in (estimate.sent_by_user_id, estimate.decided_by_user_id)
            if user_id is not None
        )
    users = await identity_service.get_users_by_ids(session, user_ids)
    missing = user_ids - users.keys()
    if missing:  # users are never deleted (spec 02 §2) and every column is an FK to users
        msg = f"unknown estimate authors {sorted(map(str, missing))}"
        raise RuntimeError(msg)
    return {
        user_id: UserRef(user_id=user_id, full_name=users[user_id].full_name)
        for user_id in user_ids
    }


def _line_read(line: EstimateLine, parts: Mapping[UUID, PartStockRef]) -> EstimateLineRead:
    return EstimateLineRead(
        id=line.id,
        position=line.position,
        line_type=line.line_type,
        part=parts.get(line.part_id) if line.part_id is not None else None,
        description=line.description,
        quantity=line.quantity,
        unit_price=line.unit_price,
        line_total=line.line_total,
    )


def _estimate_read(
    estimate: Estimate,
    lines: Sequence[EstimateLine],
    parts: Mapping[UUID, PartStockRef],
    users: Mapping[UUID, UserRef],
) -> EstimateRead:
    return EstimateRead(
        id=estimate.id,
        booking_id=estimate.booking_id,
        version=estimate.version,
        status=estimate.status,
        lines=[_line_read(line, parts) for line in lines],
        parts_total=estimate.parts_total,
        labour_total=estimate.labour_total,
        grand_total=estimate.grand_total,
        created_by=users[estimate.created_by_user_id],
        created_at=estimate.created_at,
        submitted_at=estimate.submitted_at,
        sent_at=estimate.sent_at,
        sent_by=users[estimate.sent_by_user_id] if estimate.sent_by_user_id is not None else None,
        decided_at=estimate.decided_at,
        decided_by=(
            users[estimate.decided_by_user_id] if estimate.decided_by_user_id is not None else None
        ),
        customer_note=estimate.customer_note,
    )


def _customer_read(estimate: Estimate, lines: Sequence[EstimateLine]) -> CustomerEstimateRead:
    if estimate.sent_at is None:  # ck_estimates_sent_fields: every visible version was sent
        raise _invariant_breach(
            f"customer-visible version {estimate.version} has no sent_at",
            shop_id=estimate.shop_id,
            booking_id=estimate.booking_id,
        )
    return CustomerEstimateRead(
        id=estimate.id,
        version=estimate.version,
        status=estimate.status,
        lines=[
            CustomerEstimateLineRead(
                id=line.id,
                position=line.position,
                line_type=line.line_type,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
            )
            for line in lines
        ],
        parts_total=estimate.parts_total,
        labour_total=estimate.labour_total,
        grand_total=estimate.grand_total,
        sent_at=estimate.sent_at,
        decided_at=estimate.decided_at,
        customer_note=estimate.customer_note,
    )


def _stored_line(
    priced: PricedLine, *, shop_id: UUID, estimate_id: UUID, now: datetime
) -> EstimateLine:
    return EstimateLine(
        shop_id=shop_id,
        estimate_id=estimate_id,
        position=priced.position,
        line_type=priced.line_type,
        part_id=priced.part_id,
        description=priced.description,
        quantity=priced.quantity,
        unit_price=priced.unit_price,
        line_total=priced.line_total,
        created_at=now,
    )


def _new_version(
    previous: Estimate, *, author_user_id: UUID, totals: Totals, now: datetime
) -> Estimate:
    """A `DRAFT` `version + 1` of the same booking (versions never have gaps, §7.1 invariant 3)."""
    return Estimate(
        shop_id=previous.shop_id,
        booking_id=previous.booking_id,
        version=previous.version + 1,
        status=EstimateStatus.DRAFT,
        parts_total=totals.parts_total,
        labour_total=totals.labour_total,
        grand_total=totals.grand_total,
        created_by_user_id=author_user_id,
        created_at=now,
        updated_at=now,
    )


async def _current_sent(
    repo: EstimateRepository, *, shop_id: UUID, booking_id: UUID, estimate_id: UUID
) -> Estimate:
    """T08/T09: `estimate_id` must be this booking's current `SENT` version, else 409
    `STALE_ESTIMATE` (superseded, already decided, another booking's or unknown; EST-14)."""
    current = await repo.newest_with_status(
        shop_id=shop_id, booking_id=booking_id, status=EstimateStatus.SENT
    )
    if current is None or current.id != estimate_id or current.status not in DECIDABLE_STATUSES:
        raise StaleEstimate()
    return current


# --- Writes (nested in the caller's transaction), in lifecycle order -----------------------------


async def ensure_draft(
    uow: UnitOfWork, *, shop_id: UUID, booking_id: UUID, created_by_user_id: UUID, now: datetime
) -> EstimateSnapshot:
    """T05 `START_INSPECTION`: create `DRAFT` v1 (author = the technician, totals 0) when the
    booking has no estimate yet; an existing draft is returned unchanged (EST-01)."""
    repo = EstimateRepository(uow.session)
    latest = await repo.latest(shop_id=shop_id, booking_id=booking_id)
    if latest is None:
        draft = repo.add(
            Estimate(
                shop_id=shop_id,
                booking_id=booking_id,
                version=1,
                status=EstimateStatus.DRAFT,
                parts_total=ZERO,
                labour_total=ZERO,
                grand_total=ZERO,
                created_by_user_id=created_by_user_id,
                created_at=now,
                updated_at=now,
            )
        )
        await repo.flush()
        return _snapshot(draft)
    if latest.status == EstimateStatus.DRAFT:
        return _snapshot(latest)
    raise _invariant_breach(
        f"ensure_draft found version {latest.version} in status {latest.status}",
        shop_id=shop_id,
        booking_id=booking_id,
    )


async def replace_lines(  # noqa: PLR0913 - the signature is fixed by modules/estimates.md §5
    uow: UnitOfWork,
    *,
    shop_id: UUID,
    booking_id: UUID,
    booking_status: BookingStatus,
    actor_user_id: UUID,
    lines: Sequence[EstimateLineWrite],
    now: datetime,
) -> EstimateEdit:
    """O1 `EDIT_ESTIMATE` (`PUT …/estimate`): replace the lines of the editable version with the
    full new list (1-50, display order), priced on the server (§7.3).

    Which version (§7.2): the technician's `DRAFT` in `INSPECTING` and the desk's `DRAFT` in
    `ESTIMATE_REVIEW` are edited in place (no event, no booking version bump - last write wins,
    D30); the first SA/Owner edit of a `SUBMITTED` version supersedes it and creates `DRAFT`
    v+1 authored by the editor (`created_new_version`, D39). Anything else -> 409
    `ESTIMATE_LOCKED`. Lines: `PART` = an active part of this shop (`lines.N.part_id`
    `invalid_reference`), description = the catalogue name, unit price defaults to `unit_cost`;
    every invalid line is reported in one 422 and nothing is written (EST-07, EST-24); amounts
    above `numeric(12,2)` -> 422, never a 500 (EST-21). The response carries live stock (EST-18).
    """
    repo = EstimateRepository(uow.session)
    line_repo = EstimateLineRepository(uow.session)
    latest = await repo.latest(shop_id=shop_id, booking_id=booking_id)
    decision = edit_target(booking_status, latest.status if latest is not None else None)
    if latest is None or decision is EditDecision.LOCKED:
        raise EstimateLocked()
    inputs: list[LineInput] = [line.to_line_input() for line in lines]
    parts = await _part_refs(
        uow.session,
        shop_id=shop_id,
        part_ids={
            line.part_id
            for line in inputs
            if line.line_type == EstimateLineType.PART and line.part_id is not None
        },
        include_stock=True,
    )
    pricing = price_lines(inputs, _catalog(parts))
    if pricing.errors:
        raise _validation_failed(pricing.errors)
    if decision is EditDecision.NEW_VERSION:
        latest.status = EstimateStatus.SUPERSEDED
        touch(latest, now)
        await repo.flush()  # supersede BEFORE inserting v+1: the open-version index is per row
        target = repo.add(
            _new_version(latest, author_user_id=actor_user_id, totals=pricing.totals, now=now)
        )
        await repo.flush()  # the version row exists before its lines reference it
    else:
        target = latest
        await line_repo.delete_for_estimate(shop_id=shop_id, estimate_id=target.id)
    stored = [
        _stored_line(priced, shop_id=shop_id, estimate_id=target.id, now=now)
        for priced in pricing.lines
    ]
    line_repo.add_many(stored)
    _apply_totals(target, pricing.totals)
    touch(target, now)
    await repo.flush()
    users = await _user_refs(uow.session, [target])
    return EstimateEdit(
        estimate=_estimate_read(target, stored, parts, users),
        created_new_version=decision is EditDecision.NEW_VERSION,
    )


async def submit(
    uow: UnitOfWork, *, shop_id: UUID, booking_id: UUID, now: datetime
) -> EstimateSnapshot:
    """T06 `SUBMIT_ESTIMATE`: the technician's `DRAFT` -> `SUBMITTED` (`submitted_at`), totals
    recomputed from the lines.

    422 `ESTIMATE_EMPTY` (field `lines`) without lines (EST-10); 422 `VALIDATION_ERROR`
    `lines.N.part_id` `invalid_reference` for every part deactivated since it was added
    (spec 03 §5.2); 409 `ESTIMATE_LOCKED` when the latest version is not a draft (backstop).
    """
    repo = EstimateRepository(uow.session)
    draft = await repo.latest(shop_id=shop_id, booking_id=booking_id)
    if draft is None or draft.status not in SUBMITTABLE_STATUSES:
        raise EstimateLocked("Only a draft estimate can be submitted.")
    lines = await EstimateLineRepository(uow.session).list_for_estimates(
        shop_id=shop_id, estimate_ids=[draft.id]
    )
    if not lines:
        raise _estimate_empty("submitting")
    part_lines = [(line.position - 1, line.part_id) for line in lines if line.part_id is not None]
    parts = await _part_refs(
        uow.session,
        shop_id=shop_id,
        part_ids={part_id for _, part_id in part_lines},
        include_stock=False,
    )
    errors = inactive_part_errors(part_lines, _catalog(parts))
    if errors:
        raise _validation_failed(errors)
    _apply_totals(draft, estimate_totals(lines))
    draft.status = EstimateStatus.SUBMITTED
    draft.submitted_at = now
    touch(draft, now)
    await repo.flush()
    return _snapshot(draft)


async def send(
    uow: UnitOfWork, *, shop_id: UUID, booking_id: UUID, sent_by_user_id: UUID, now: datetime
) -> EstimateSnapshot:
    """T07 `SEND_ESTIMATE`: the open version (the technician's `SUBMITTED` one or the desk's
    `DRAFT`) -> `SENT` with `sent_at` and `sent_by_user_id`; totals recomputed from the lines.

    422 `ESTIMATE_EMPTY` without lines (EST-10); 409 `ESTIMATE_LOCKED` when the latest version is
    not open (a backstop the state machine makes unreachable). Older versions were superseded by
    the edit that created this one (O1), so the one-open-version index never blocks (EST-04).
    Like spec 08 T07, only emptiness is checked: the lines the SA reviewed go out as saved.
    """
    repo = EstimateRepository(uow.session)
    latest = await repo.latest(shop_id=shop_id, booking_id=booking_id)
    if latest is None or latest.status not in SENDABLE_STATUSES:
        raise EstimateLocked("Only the estimate version under review can be sent.")
    lines = await EstimateLineRepository(uow.session).list_for_estimates(
        shop_id=shop_id, estimate_ids=[latest.id]
    )
    if not lines:
        raise _estimate_empty("sending")
    _apply_totals(latest, estimate_totals(lines))
    latest.status = EstimateStatus.SENT
    latest.sent_at = now
    latest.sent_by_user_id = sent_by_user_id
    touch(latest, now)
    await repo.flush()
    return _snapshot(latest)


async def approve(
    uow: UnitOfWork,
    *,
    shop_id: UUID,
    booking_id: UUID,
    estimate_id: UUID,
    decided_by_user_id: UUID,
    now: datetime,
) -> EstimateSnapshot:
    """T08 `APPROVE_ESTIMATE`: the current `SENT` version -> `APPROVED` with `decided_at` and
    `decided_by_user_id` - the customer's timestamped in-app acceptance (brief §3), frozen from
    now on (EST-13). Any other `estimate_id` -> 409 `STALE_ESTIMATE` (EST-14, SM-14)."""
    repo = EstimateRepository(uow.session)
    current = await _current_sent(
        repo, shop_id=shop_id, booking_id=booking_id, estimate_id=estimate_id
    )
    current.status = EstimateStatus.APPROVED
    current.decided_at = now
    current.decided_by_user_id = decided_by_user_id
    touch(current, now)
    await repo.flush()
    return _snapshot(current)


async def reject(  # noqa: PLR0913 - the signature is fixed by modules/estimates.md §5
    uow: UnitOfWork,
    *,
    shop_id: UUID,
    booking_id: UUID,
    estimate_id: UUID,
    decided_by_user_id: UUID,
    reason: str | None,
    now: datetime,
) -> EstimateSnapshot:
    """T09 `REJECT_ESTIMATE`: the current `SENT` version -> `REJECTED` with `decided_at`,
    `decided_by_user_id` and `customer_note` = the trimmed reason (≤ 500; blank -> null).
    Any other `estimate_id` -> 409 `STALE_ESTIMATE`."""
    note = reason.strip() if reason is not None else None
    if note is not None and len(note) > REJECT_REASON_MAX_LENGTH:
        message = f"String should have at most {REJECT_REASON_MAX_LENGTH} characters"
        raise ValidationFailed(
            errors=[FieldError(field="reason", message=message, code="string_too_long")]
        )
    if note is not None and contains_nul(note):
        raise ValidationFailed(
            errors=[FieldError(field="reason", message=NUL_NOT_ALLOWED, code="value_error")]
        )
    repo = EstimateRepository(uow.session)
    current = await _current_sent(
        repo, shop_id=shop_id, booking_id=booking_id, estimate_id=estimate_id
    )
    current.status = EstimateStatus.REJECTED
    current.decided_at = now
    current.decided_by_user_id = decided_by_user_id
    current.customer_note = note or None
    touch(current, now)
    await repo.flush()
    return _snapshot(current)


async def copy_rejected_to_draft(
    uow: UnitOfWork, *, shop_id: UUID, booking_id: UUID, created_by_user_id: UUID, now: datetime
) -> EstimateSnapshot:
    """T10 `REVISE_ESTIMATE` / T11 `RETURN_TO_TECHNICIAN`: copy the `REJECTED` version into a new
    `DRAFT` `version + 1` (author = the acting SA/Owner): every line verbatim (position, type,
    part, stored description, quantity, unit price, line total) and the totals. The rejected
    version is unchanged (EST-15). The next save re-validates the copied lines against the
    catalogue (`replace_lines`). 409 `ESTIMATE_LOCKED` when the latest version is not `REJECTED`."""
    repo = EstimateRepository(uow.session)
    line_repo = EstimateLineRepository(uow.session)
    rejected = await repo.latest(shop_id=shop_id, booking_id=booking_id)
    if rejected is None or rejected.status not in COPYABLE_STATUSES:
        raise EstimateLocked("Only a rejected estimate can be revised.")
    lines = await line_repo.list_for_estimates(shop_id=shop_id, estimate_ids=[rejected.id])
    draft = repo.add(
        _new_version(
            rejected,
            author_user_id=created_by_user_id,
            totals=estimate_totals(lines),
            now=now,
        )
    )
    await repo.flush()  # the version row exists before its lines reference it
    line_repo.add_many(
        EstimateLine(
            shop_id=shop_id,
            estimate_id=draft.id,
            position=line.position,
            line_type=line.line_type,
            part_id=line.part_id,
            description=line.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            line_total=line.line_total,
            created_at=now,
        )
        for line in lines
    )
    await repo.flush()
    return _snapshot(draft)


async def supersede_open_versions(
    uow: UnitOfWork, *, shop_id: UUID, booking_id: UUID, now: datetime
) -> list[UUID]:
    """T22 `CANCEL`: every open version (`DRAFT`, `SUBMITTED`, `SENT`) -> `SUPERSEDED`;
    `APPROVED` and `REJECTED` stay (EST-17). Returns the ids it superseded (at most one)."""
    return await EstimateRepository(uow.session).supersede_open(
        shop_id=shop_id, booking_id=booking_id, now=now
    )


async def get_approved_part_requirements(
    session: AsyncSession, *, shop_id: UUID, booking_id: UUID
) -> list[PartQty]:
    """T12 `ASSIGN_PARTS_PERSON`: the `APPROVED` version's `PART` lines, quantities summed per
    part, ordered by `part_id` (inventory's `create_booking_parts` input). A labour-only estimate
    gives `[]` (D31). No approved version is an invariant breach (T12 only runs from
    `ESTIMATE_APPROVED`) -> 500."""
    approved = await EstimateRepository(session).newest_with_status(
        shop_id=shop_id, booking_id=booking_id, status=EstimateStatus.APPROVED
    )
    if approved is None:
        raise _invariant_breach(
            "part requirements asked without an APPROVED version",
            shop_id=shop_id,
            booking_id=booking_id,
        )
    rows = await EstimateLineRepository(session).part_requirements(
        shop_id=shop_id, estimate_id=approved.id
    )
    return [PartQty(part_id=row.part_id, qty=row.qty) for row in rows]


# --- Reads ----------------------------------------------------------------------------------------


async def list_versions(
    session: AsyncSession, *, shop_id: UUID, booking_id: UUID, include_stock: bool
) -> list[EstimateRead]:
    """`GET …/bookings/{booking_id}/estimates`: every version ascending, part lines with **live**
    stock (D40, EST-18) - null stock fields when `include_stock` is false (QC inspectors, spec 04
    §B). Four queries whatever the number of versions: versions, lines, parts, users."""
    versions = await EstimateRepository(session).list_for_booking(
        shop_id=shop_id, booking_id=booking_id
    )
    if not versions:
        return []
    lines = await EstimateLineRepository(session).list_for_estimates(
        shop_id=shop_id, estimate_ids=[version.id for version in versions]
    )
    parts = await _part_refs(
        session,
        shop_id=shop_id,
        part_ids={line.part_id for line in lines if line.part_id is not None},
        include_stock=include_stock,
    )
    users = await _user_refs(session, versions)
    by_estimate = _group_lines(lines)
    return [
        _estimate_read(version, by_estimate.get(version.id, []), parts, users)
        for version in versions
    ]


async def get_estimate_summaries(
    session: AsyncSession,
    *,
    shop_id: UUID,
    booking_ids: Collection[UUID],
    audience: SummaryAudience,
) -> dict[UUID, EstimateSummary]:
    """`estimate_summary` for a page of bookings of one shop, in one query: staff get the latest
    version, customers the latest `SENT` / `APPROVED` / `REJECTED` one (D39). Bookings without
    such a version are absent from the result (the field is then `null`). An unknown `audience`
    raises `ValueError` - it never falls back to the staff view (fail closed, SEC-12). For the
    customer's list, which spans shops, use `get_customer_estimate_summaries`."""
    statuses: Collection[EstimateStatus] | None
    if audience == "customer":
        statuses = CUSTOMER_VISIBLE_STATUSES
    elif audience == "staff":
        statuses = None
    else:
        raise ValueError(f"unknown estimate summary audience {audience!r}")
    rows = await EstimateRepository(session).latest_for_bookings(
        shop_id=shop_id, booking_ids=booking_ids, statuses=statuses
    )
    return _summaries(rows)


async def get_customer_estimate_summaries(
    session: AsyncSession, *, booking_keys: Collection[tuple[UUID, UUID]]
) -> dict[UUID, EstimateSummary]:
    """`estimate_summary` for the customer's booking list, which spans shops: per
    `(shop_id, booking_id)` key, the latest `SENT` / `APPROVED` / `REJECTED` version (D39), in one
    query whatever the number of shops (API-11). Each key matches only its own shop's rows (D20).
    Bookings without a visible version are absent (`null`); no keys -> `{}` without a query."""
    rows = await EstimateRepository(session).latest_for_booking_keys(
        booking_keys=booking_keys, statuses=CUSTOMER_VISIBLE_STATUSES
    )
    return _summaries(rows)


async def get_customer_view(
    session: AsyncSession, *, shop_id: UUID, booking_id: UUID
) -> CustomerEstimateView:
    """The customer's booking detail (§7.7) and the P2 agent's estimate view: the visible version
    with the highest `version` (or None) and whether a newer `DRAFT` / `SUBMITTED` revision is in
    progress. Drafts, submitted and superseded versions are never returned (SEC-12, EST-27)."""
    versions = await EstimateRepository(session).list_for_booking(
        shop_id=shop_id, booking_id=booking_id
    )
    shown = customer_shown(versions)
    if shown is None:
        return CustomerEstimateView(estimate=None, revision_in_progress=False)
    lines = await EstimateLineRepository(session).list_for_estimates(
        shop_id=shop_id, estimate_ids=[shown.id]
    )
    return CustomerEstimateView(
        estimate=_customer_read(shown, lines),
        revision_in_progress=revision_in_progress(versions, shown),
    )


async def list_customer_versions(
    session: AsyncSession, *, shop_id: UUID, booking_id: UUID
) -> list[CustomerEstimateRead]:
    """P1 "previous versions": every `SENT`, `APPROVED` and `REJECTED` version, ascending."""
    versions = await EstimateRepository(session).list_for_booking(
        shop_id=shop_id, booking_id=booking_id, statuses=CUSTOMER_VISIBLE_STATUSES
    )
    lines = await EstimateLineRepository(session).list_for_estimates(
        shop_id=shop_id, estimate_ids=[version.id for version in versions]
    )
    by_estimate = _group_lines(lines)
    return [_customer_read(version, by_estimate.get(version.id, [])) for version in versions]

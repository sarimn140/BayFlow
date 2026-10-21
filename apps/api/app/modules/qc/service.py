"""Use cases of the qc module (`modules/qc.md` "Public service interface"; spec 08 T17-T20).

Nested writes — called only by `bookings.service`, inside a booking action that already holds the
booking row lock and has passed the state machine (role, `QC_PICKER` guard, status,
`expected_version`). They never commit, never change the booking, and stamp every row with the
action's instant `now` (D63):

- `resolve_open_issues` (T17 `send-to-qc`): the booking's `OPEN` issues -> `RESOLVED`.
- `open_inspection` (T18 `pick-qc`): a new round, `result` NULL; a second open round of the same
  booking is 409 `ALREADY_PICKED` (the `uq_qc_inspections_one_open_per_booking` backstop, D30).
- `record_pass` (T19 `pass-qc`): the open round -> `PASS` with the full checklist, every item
  passed (else 422 `checklist_incomplete` / `checklist_item_failed`).
- `record_fail` (T20 `fail-qc`): the open round -> `FAIL` (checklist optional) + one `OPEN` issue.
- `reassign_open_inspection` (P1, planned D87 `REASSIGN_QC_INSPECTOR`): the open round moves to
  another inspector.

Reads (take an `AsyncSession`): `default_checklist`, `list_booking_qc_history`,
`get_qc_summaries`, `list_inspected_booking_ids`, `has_inspected`, `list_inspector_ids`.
Visibility (D21) is applied by bookings before any of them runs; every function is scoped by
`shop_id` (D20), so another shop's booking id matches nothing.

This module never imports bookings (spec 01 rule 3); it reads user names from identity.
"""

import uuid
from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FieldError, Forbidden, ValidationFailed
from app.modules.identity import service as identity_service
from app.modules.identity.schemas import UserRef
from app.modules.qc.domain.checklist import stored_checklist, validate_checklist
from app.modules.qc.domain.rules import (
    ISSUE_DESCRIPTION_FIELD,
    ISSUE_DESCRIPTION_MAX_LENGTH,
    ISSUE_TITLE_FIELD,
    ISSUE_TITLE_MAX_LENGTH,
    NOTES_FIELD,
    NOTES_MAX_LENGTH,
    check_optional_text,
    check_required_text,
)
from app.modules.qc.models import QcInspection, QcIssue
from app.modules.qc.repository import QcInspectionRepository, QcIssueRepository
from app.modules.qc.schemas import (
    FailRecorded,
    QcChecklistItemRead,
    QcChecklistItemWrite,
    QcChecklistTemplateItem,
    QcInspectionRead,
    QcIssueRead,
    QcSummary,
    checklist_template,
)
from app.shared.enums import QcIssueStatus, QcResult
from app.shared.orm import touch
from app.shared.uow import UnitOfWork

TECHNICIAN_CANNOT_PICK = "The booking's technician cannot run its quality check."


class QcIntegrityError(RuntimeError):
    """QC rows contradict the booking the state machine already checked.

    `modules/qc.md`: in T19/T20 the open round must exist and belong to the caller, because the
    state machine already checked `bookings.qc_inspector_user_id`; a mismatch is a data-integrity
    bug -> 500 (logged with its traceback), never a user error.
    """


# --- Nested writes (T17-T20) ----------------------------------------------------------------------


async def resolve_open_issues(
    uow: UnitOfWork,
    *,
    shop_id: uuid.UUID,
    booking_id: uuid.UUID,
    resolved_by_user_id: uuid.UUID,
    now: datetime,
) -> list[uuid.UUID]:
    """T17: mark every `OPEN` issue of this booking `RESOLVED` by the technician (D47).

    Returns the resolved issue ids, oldest first (possibly none); bookings stores them as the
    `SEND_TO_QC` metadata `{resolved_qc_issue_ids}`. Issues of other bookings are never touched.
    """
    return await QcIssueRepository(uow.session).resolve_open(
        shop_id=shop_id,
        booking_id=booking_id,
        resolved_by_user_id=resolved_by_user_id,
        now=now,
    )


async def open_inspection(
    uow: UnitOfWork,
    *,
    shop_id: uuid.UUID,
    booking_id: uuid.UUID,
    inspector_user_id: uuid.UUID,
    now: datetime,
    booking_technician_user_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """T18: open a new QC round picked by `inspector_user_id` at `now`; returns its id
    (`PICK_QC` metadata `{qc_inspection_id}`).

    Raises 409 `ALREADY_PICKED` when the booking already has an open round (the unique-index
    backstop behind the state machine's first-pick-wins check, D30). When the caller passes the
    booking's technician, picking one's own repair is 403 `FORBIDDEN` (D47 backstop; the state
    machine and `ck_bookings_qc_picker_not_technician` guard it too). A `booking_id` that is not
    of `shop_id` is a caller bug: the composite tenant FK (D20) rejects the insert and the
    `IntegrityError` propagates as a logged 500.
    """
    if booking_technician_user_id is not None and booking_technician_user_id == inspector_user_id:
        raise Forbidden(TECHNICIAN_CANNOT_PICK)
    inspection = QcInspection(
        shop_id=shop_id,
        booking_id=booking_id,
        inspector_user_id=inspector_user_id,
        picked_at=now,
        created_at=now,
        updated_at=now,
    )
    await QcInspectionRepository(uow.session).insert_open_round(inspection)
    return inspection.id


async def record_pass(  # noqa: PLR0913 - signature fixed by modules/qc.md
    uow: UnitOfWork,
    *,
    shop_id: uuid.UUID,
    booking_id: uuid.UUID,
    inspector_user_id: uuid.UUID,
    checklist: Sequence[QcChecklistItemWrite],
    notes: str | None,
    now: datetime,
) -> uuid.UUID:
    """T19: the open round -> `PASS` with the checklist (every item passed) and notes.

    Returns the round's id (`PASS_QC` metadata). 422 `VALIDATION_ERROR` with
    `checklist`/`checklist_incomplete` (missing or repeated key) and `checklist.N.passed`/
    `checklist_item_failed` for every failed item ("use fail-qc"), or an over-long `notes`.
    """
    errors = validate_checklist(checklist, require_all_passed=True)
    clean_notes, notes_errors = check_optional_text(
        notes, field=NOTES_FIELD, max_length=NOTES_MAX_LENGTH
    )
    errors.extend(notes_errors)
    if errors:
        raise ValidationFailed(errors=errors)

    inspection = await _open_round_of(
        uow.session, shop_id=shop_id, booking_id=booking_id, inspector_user_id=inspector_user_id
    )
    inspection.result = QcResult.PASS
    inspection.completed_at = now
    inspection.checklist = stored_checklist(checklist)
    inspection.notes = clean_notes
    touch(inspection, now)
    await uow.session.flush()
    return inspection.id


async def record_fail(  # noqa: PLR0913 - signature fixed by modules/qc.md
    uow: UnitOfWork,
    *,
    shop_id: uuid.UUID,
    booking_id: uuid.UUID,
    inspector_user_id: uuid.UUID,
    issue_title: str,
    issue_description: str,
    checklist: Sequence[QcChecklistItemWrite] | None,
    notes: str | None,
    now: datetime,
) -> FailRecorded:
    """T20: the open round -> `FAIL` (checklist stored when sent, else NULL) + one `OPEN` issue.

    The issue belongs to the same booking as its round and is raised by the inspector; the job
    goes back to the same technician (bookings, D47). 422 `VALIDATION_ERROR` when the title
    (1-120) or description (1-2000) is missing, blank or too long, when a sent checklist misses
    or repeats a key (`checklist_incomplete`; failed items are allowed here) or `notes` is too long.
    """
    title, title_errors = check_required_text(
        issue_title, field=ISSUE_TITLE_FIELD, max_length=ISSUE_TITLE_MAX_LENGTH
    )
    description, description_errors = check_required_text(
        issue_description, field=ISSUE_DESCRIPTION_FIELD, max_length=ISSUE_DESCRIPTION_MAX_LENGTH
    )
    clean_notes, notes_errors = check_optional_text(
        notes, field=NOTES_FIELD, max_length=NOTES_MAX_LENGTH
    )
    checklist_errors: list[FieldError] = (
        [] if checklist is None else validate_checklist(checklist, require_all_passed=False)
    )
    # In the order of FailQcRequest's fields (spec 03 §5.2), every problem at once (API-02).
    errors = [*title_errors, *description_errors, *checklist_errors, *notes_errors]
    if errors:
        raise ValidationFailed(errors=errors)

    inspection = await _open_round_of(
        uow.session, shop_id=shop_id, booking_id=booking_id, inspector_user_id=inspector_user_id
    )
    inspection.result = QcResult.FAIL
    inspection.completed_at = now
    inspection.checklist = None if checklist is None else stored_checklist(checklist)
    inspection.notes = clean_notes
    touch(inspection, now)
    issue = QcIssue(
        shop_id=shop_id,
        booking_id=inspection.booking_id,  # always the round's booking (spec 02 §3.19)
        qc_inspection_id=inspection.id,
        title=title,
        description=description,
        status=QcIssueStatus.OPEN,
        created_by_user_id=inspector_user_id,
        created_at=now,
        updated_at=now,
    )
    uow.session.add(issue)
    await uow.session.flush()
    return FailRecorded(qc_inspection_id=inspection.id, qc_issue_id=issue.id)


async def reassign_open_inspection(
    uow: UnitOfWork,
    *,
    shop_id: uuid.UUID,
    booking_id: uuid.UUID,
    new_inspector_user_id: uuid.UUID,
    now: datetime,
    booking_technician_user_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """P1, planned with D87's `REASSIGN_QC_INSPECTOR` (bookings): move the open round to a new
    inspector, so their `pass-qc` / `fail-qc` finds it. Returns the round's id.

    `picked_at` stays the instant the round was first picked; the previous picker survives only
    in the booking event's metadata (`modules/qc.md` "In scope"). Bookings checks eligibility
    (an active QC inspector of the shop, not the technician) before calling; passing the booking's
    technician here is still 403 `FORBIDDEN` (D47 backstop). No open round is an integrity error.
    """
    if (
        booking_technician_user_id is not None
        and booking_technician_user_id == new_inspector_user_id
    ):
        raise Forbidden(TECHNICIAN_CANNOT_PICK)
    inspection = await QcInspectionRepository(uow.session).get_open_round(
        shop_id=shop_id, booking_id=booking_id
    )
    if inspection is None:
        msg = f"booking {booking_id} of shop {shop_id} has no open QC round to reassign"
        raise QcIntegrityError(msg)
    inspection.inspector_user_id = new_inspector_user_id
    touch(inspection, now)
    await uow.session.flush()
    return inspection.id


async def _open_round_of(
    session: AsyncSession,
    *,
    shop_id: uuid.UUID,
    booking_id: uuid.UUID,
    inspector_user_id: uuid.UUID,
) -> QcInspection:
    """The booking's open round, which must have been picked by `inspector_user_id`."""
    inspection = await QcInspectionRepository(session).get_open_round(
        shop_id=shop_id, booking_id=booking_id
    )
    if inspection is None:
        msg = f"booking {booking_id} of shop {shop_id} has no open QC round"
        raise QcIntegrityError(msg)
    if inspection.inspector_user_id != inspector_user_id:
        msg = (
            f"the open QC round {inspection.id} was picked by {inspection.inspector_user_id}, "
            f"not by {inspector_user_id}"
        )
        raise QcIntegrityError(msg)
    return inspection


# --- Reads ----------------------------------------------------------------------------------------


def default_checklist() -> list[QcChecklistTemplateItem]:
    """The D46 checklist in fixed order (pure; `GET …/qc/checklist`)."""
    return checklist_template()


async def list_booking_qc_history(
    session: AsyncSession, *, shop_id: uuid.UUID, booking_id: uuid.UUID
) -> list[QcInspectionRead]:
    """Every QC round of the booking with checklist, notes and issues, oldest first.

    Served by bookings as `GET …/bookings/{booking_id}/qc-inspections` after its D21 check.
    `round` is the 1-based position by `(picked_at, id)`. Names come from one identity batch.
    """
    rounds = await QcInspectionRepository(session).list_rounds(
        shop_id=shop_id, booking_id=booking_id
    )
    if not rounds:
        return []
    issues = await QcIssueRepository(session).list_issues(shop_id=shop_id, booking_id=booking_id)
    user_ids = {inspection.inspector_user_id for inspection in rounds}
    user_ids.update(issue.created_by_user_id for issue in issues)
    user_ids.update(issue.resolved_by_user_id for issue in issues if issue.resolved_by_user_id)
    refs = await _user_refs(session, user_ids)

    issues_by_round: defaultdict[uuid.UUID, list[QcIssueRead]] = defaultdict(list)
    for issue in issues:
        issues_by_round[issue.qc_inspection_id].append(_issue_read(issue, refs))
    return [
        _inspection_read(inspection, number, refs, issues_by_round[inspection.id])
        for number, inspection in enumerate(rounds, start=1)
    ]


async def get_qc_summaries(
    session: AsyncSession, *, shop_id: uuid.UUID, booking_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, QcSummary]:
    """Rounds and open issues per booking — one entry per id, zeros included; two queries
    whatever the number of ids (API-11). Bookings derives `qc_round` (`QcSummary.qc_round`)
    and `open_qc_issues_count` from it (spec 03 §3.3)."""
    ids = list(dict.fromkeys(booking_ids))
    if not ids:
        return {}
    rounds = await QcInspectionRepository(session).count_rounds(shop_id=shop_id, booking_ids=ids)
    open_issues = await QcIssueRepository(session).count_open(shop_id=shop_id, booking_ids=ids)
    return {
        booking_id: QcSummary(
            inspections=rounds.get(booking_id, 0), open_issues=open_issues.get(booking_id, 0)
        )
        for booking_id in ids
    }


async def list_inspected_booking_ids(
    session: AsyncSession, *, shop_id: uuid.UUID, inspector_user_id: uuid.UUID
) -> frozenset[uuid.UUID]:
    """D21: the shop's bookings this QC inspector picked at least once (any round, any result)."""
    return await QcInspectionRepository(session).booking_ids_inspected_by(
        shop_id=shop_id, inspector_user_id=inspector_user_id
    )


async def has_inspected(
    session: AsyncSession,
    *,
    shop_id: uuid.UUID,
    booking_id: uuid.UUID,
    inspector_user_id: uuid.UUID,
) -> bool:
    """D21 on item routes and actions: did this QC inspector ever pick this booking?"""
    return await QcInspectionRepository(session).has_round_by(
        shop_id=shop_id, booking_id=booking_id, inspector_user_id=inspector_user_id
    )


async def list_inspector_ids(
    session: AsyncSession, *, shop_id: uuid.UUID, booking_id: uuid.UUID
) -> frozenset[uuid.UUID]:
    """Everyone who inspected the booking — the QC viewers of `booking.updated` (glossary §11)."""
    return await QcInspectionRepository(session).inspector_ids(
        shop_id=shop_id, booking_id=booking_id
    )


# --- Read assembly --------------------------------------------------------------------------------


async def _user_refs(
    session: AsyncSession, user_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, UserRef]:
    users = await identity_service.get_users_by_ids(session, user_ids)
    missing = set(user_ids) - set(users)
    if missing:  # every id comes from a foreign key to `users`, so this is a bug
        msg = f"users referenced by QC rows were not found: {sorted(map(str, missing))}"
        raise QcIntegrityError(msg)
    return {
        user_id: UserRef(user_id=user_id, full_name=users[user_id].full_name)
        for user_id in user_ids
    }


def _issue_read(issue: QcIssue, refs: dict[uuid.UUID, UserRef]) -> QcIssueRead:
    return QcIssueRead(
        id=issue.id,
        qc_inspection_id=issue.qc_inspection_id,
        title=issue.title,
        description=issue.description,
        status=issue.status,
        created_by=refs[issue.created_by_user_id],
        created_at=issue.created_at,
        resolved_at=issue.resolved_at,
        resolved_by=refs[issue.resolved_by_user_id] if issue.resolved_by_user_id else None,
    )


def _inspection_read(
    inspection: QcInspection,
    number: int,
    refs: dict[uuid.UUID, UserRef],
    issues: list[QcIssueRead],
) -> QcInspectionRead:
    checklist = (
        None
        if inspection.checklist is None
        else [
            QcChecklistItemRead(
                key=item["key"],
                label=item["label"],
                passed=item["passed"],
                note=item.get("note"),
            )
            for item in inspection.checklist
        ]
    )
    return QcInspectionRead(
        id=inspection.id,
        round=number,
        inspector=refs[inspection.inspector_user_id],
        picked_at=inspection.picked_at,
        completed_at=inspection.completed_at,
        result=inspection.result,
        checklist=checklist,
        notes=inspection.notes,
        issues=issues,
    )

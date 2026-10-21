"""Estimate version lifecycle at the service layer (D39; `modules/estimates.md` §7.1, §7.6):
EST-01, EST-04, EST-10, EST-12, EST-13, EST-14, EST-15, EST-16, EST-17 (service halves), SM-14.

The booking-level halves (events, `bookings.version`, HTTP codes) come with the bookings module."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.core.database import Database
from app.core.errors import (
    EstimateEmpty,
    EstimateLocked,
    InternalError,
    StaleEstimate,
    ValidationFailed,
)
from app.modules.estimates import service
from app.modules.estimates.models import Estimate
from app.shared.enums import EstimateStatus
from tests.modules.estimates.support import (
    World,
    at,
    insert_version,
    labour_spec,
    line_facts,
    lines_of,
    part_spec,
    read,
    versions_of,
    worked_example_v1,
    write,
)

pytestmark = pytest.mark.db

DRAFT = EstimateStatus.DRAFT
SUBMITTED = EstimateStatus.SUBMITTED
SENT = EstimateStatus.SENT
APPROVED = EstimateStatus.APPROVED
REJECTED = EstimateStatus.REJECTED
SUPERSEDED = EstimateStatus.SUPERSEDED


def statuses(versions: list[Estimate]) -> list[tuple[int, EstimateStatus]]:
    return [(version.version, version.status) for version in versions]


async def sent_v2(db: Database, world: World) -> tuple[uuid.UUID, uuid.UUID]:
    """Brief §6 after step 6: v1 superseded by Bilal's edit, v2 (labour 3,500) sent: 16,100."""
    v1 = await insert_version(
        db, world, version=1, status=SUPERSEDED, lines=worked_example_v1(world)
    )
    v2_lines = [*worked_example_v1(world)[:3], labour_spec("Diagnosis and repair labour", "3500")]
    v2 = await insert_version(
        db, world, version=2, status=SENT, lines=v2_lines, created_by=world.sa_id
    )
    return v1, v2


# --- T05 ensure_draft -----------------------------------------------------------------------------


async def test_est_01_ensure_draft_creates_v1_only_when_the_booking_has_none(
    db: Database, world: World
) -> None:
    """EST-01: `start-inspection` creates `DRAFT` v1 (author = technician, totals 0) only when the
    booking has no estimate; a second call returns the same draft."""
    first = await write(
        db,
        service.ensure_draft,
        lock=world.booking_id,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        created_by_user_id=world.tech_id,
        now=at(0),
    )
    assert (first.version, first.status, first.grand_total) == (1, DRAFT, Decimal("0.00"))
    again = await write(
        db,
        service.ensure_draft,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        created_by_user_id=world.sa_id,
        now=at(5),
    )
    assert again == first
    [v1] = await versions_of(db, world.booking_id)
    assert v1.id == first.estimate_id
    assert v1.created_by_user_id == world.tech_id
    assert v1.created_at == v1.updated_at == at(0)
    assert (v1.parts_total, v1.labour_total, v1.grand_total) == (Decimal("0.00"),) * 3
    assert v1.submitted_at is v1.sent_at is v1.decided_at is None
    assert await lines_of(db, v1.id) == []


async def test_ensure_draft_on_a_non_draft_estimate_is_an_invariant_breach(
    db: Database, world: World
) -> None:
    """`modules/estimates.md` §10: T05 can never meet a submitted version; if it does, 500."""
    await insert_version(db, world, version=1, status=SUBMITTED, lines=worked_example_v1(world))
    with pytest.raises(InternalError):
        await write(
            db,
            service.ensure_draft,
            shop_id=world.shop_id,
            booking_id=world.booking_id,
            created_by_user_id=world.tech_id,
            now=at(1),
        )
    assert statuses(await versions_of(db, world.booking_id)) == [(1, SUBMITTED)]


# --- T07 send -------------------------------------------------------------------------------------


async def test_est_04_send_marks_the_submitted_v1_sent_when_nobody_edited_it(
    db: Database, world: World
) -> None:
    """EST-04: with no SA edit, v1 itself is sent (`sent_at`, `sent_by_user_id`)."""
    v1 = await insert_version(
        db, world, version=1, status=SUBMITTED, lines=worked_example_v1(world)
    )
    snapshot = await write(
        db,
        service.send,
        lock=world.booking_id,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        sent_by_user_id=world.sa_id,
        now=at(10),
    )
    assert (snapshot.estimate_id, snapshot.version, snapshot.status) == (v1, 1, SENT)
    assert snapshot.grand_total == Decimal("16600.00")
    [sent] = await versions_of(db, world.booking_id)
    assert (sent.sent_at, sent.sent_by_user_id, sent.updated_at) == (at(10), world.sa_id, at(10))
    assert sent.submitted_at == at(1)  # kept from T06


async def test_est_04_send_marks_the_desk_draft_sent(db: Database, world: World) -> None:
    """EST-04: the SA's `DRAFT` v2 is the one sent; v1 stays `SUPERSEDED` (it was superseded by
    the edit that created v2, so the one-open-version index never blocks)."""
    await insert_version(db, world, version=1, status=SUPERSEDED, lines=worked_example_v1(world))
    v2_lines = [*worked_example_v1(world)[:3], labour_spec("Diagnosis and repair labour", "3500")]
    v2 = await insert_version(
        db, world, version=2, status=DRAFT, lines=v2_lines, created_by=world.sa_id
    )
    snapshot = await write(
        db,
        service.send,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        sent_by_user_id=world.owner_id,
        now=at(10),
    )
    assert (snapshot.estimate_id, snapshot.version, snapshot.grand_total) == (
        v2,
        2,
        Decimal("16100.00"),
    )
    versions = await versions_of(db, world.booking_id)
    assert statuses(versions) == [(1, SUPERSEDED), (2, SENT)]
    assert versions[1].sent_by_user_id == world.owner_id  # D16: the Owner sends like an SA
    assert versions[0].sent_at is None


async def test_send_recomputes_the_cached_totals_from_the_lines(db: Database, world: World) -> None:
    """Totals are always recomputed on the server (D40, DI-5), even from a stale cache."""
    v1 = await insert_version(
        db, world, version=1, status=SUBMITTED, lines=worked_example_v1(world)
    )
    async with db.sessionmaker() as session:
        await session.execute(
            update(Estimate)
            .where(Estimate.id == v1)
            .values(parts_total=0, labour_total=0, grand_total=0)
        )
        await session.commit()
    snapshot = await write(
        db,
        service.send,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        sent_by_user_id=world.sa_id,
        now=at(10),
    )
    assert snapshot.grand_total == Decimal("16600.00")
    [sent] = await versions_of(db, world.booking_id)
    assert (sent.parts_total, sent.labour_total) == (Decimal("12600.00"), Decimal("4000.00"))


async def test_est_10_send_without_lines_is_estimate_empty(db: Database, world: World) -> None:
    """EST-10: 422 `ESTIMATE_EMPTY` carrying the field `lines`; nothing changes."""
    await insert_version(db, world, version=1, status=DRAFT)
    with pytest.raises(EstimateEmpty) as caught:
        await write(
            db,
            service.send,
            shop_id=world.shop_id,
            booking_id=world.booking_id,
            sent_by_user_id=world.sa_id,
            now=at(10),
        )
    assert caught.value.status_code == 422
    assert caught.value.errors is not None
    assert [(error["field"], error["code"]) for error in caught.value.errors] == [
        ("lines", "too_short")
    ]
    assert statuses(await versions_of(db, world.booking_id)) == [(1, DRAFT)]


@pytest.mark.parametrize("latest", [None, SENT, APPROVED, REJECTED, SUPERSEDED])
async def test_est_12_send_is_refused_unless_the_latest_version_is_under_review(
    db: Database, world: World, latest: EstimateStatus | None
) -> None:
    """EST-12 / backstop: a frozen version is never sent again (a double send included)."""
    if latest is not None:
        await insert_version(db, world, version=1, status=latest, lines=worked_example_v1(world))
    before = await versions_of(db, world.booking_id)
    with pytest.raises(EstimateLocked):
        await write(
            db,
            service.send,
            shop_id=world.shop_id,
            booking_id=world.booking_id,
            sent_by_user_id=world.sa_id,
            now=at(10),
        )
    after = await versions_of(db, world.booking_id)
    assert [(v.status, v.sent_at, v.updated_at) for v in after] == [
        (v.status, v.sent_at, v.updated_at) for v in before
    ]


# --- T08 / T09 approve and reject -----------------------------------------------------------------


async def test_est_13_approve_records_the_timestamped_acceptance(
    db: Database, world: World
) -> None:
    """EST-13: `APPROVED` with `decided_at` and `decided_by_user_id` = the customer (brief §3);
    the customer's view shows it with the timestamp."""
    _, v2 = await sent_v2(db, world)
    snapshot = await write(
        db,
        service.approve,
        lock=world.booking_id,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        estimate_id=v2,
        decided_by_user_id=world.customer_id,
        now=at(20),
    )
    assert (snapshot.estimate_id, snapshot.status, snapshot.grand_total) == (
        v2,
        APPROVED,
        Decimal("16100.00"),
    )
    assert snapshot.event_metadata() == {
        "estimate_id": str(v2),
        "version": 2,
        "grand_total": "16100.00",
    }
    versions = await versions_of(db, world.booking_id)
    assert statuses(versions) == [(1, SUPERSEDED), (2, APPROVED)]
    approved = versions[1]
    assert (approved.decided_at, approved.decided_by_user_id) == (at(20), world.customer_id)
    assert approved.customer_note is None
    view = await read(
        db, service.get_customer_view, shop_id=world.shop_id, booking_id=world.booking_id
    )
    assert view.estimate is not None
    assert (view.estimate.id, view.estimate.status, view.estimate.decided_at) == (
        v2,
        APPROVED,
        at(20),
    )
    assert view.revision_in_progress is False


async def stale_ids(db: Database, world: World) -> dict[str, uuid.UUID]:
    v1, _ = await sent_v2(db, world)
    other = await insert_version(
        db,
        world,
        version=1,
        status=SENT,
        booking_id=world.second_booking_id,
        lines=[labour_spec("Wheel alignment", "2000")],
    )
    return {"superseded": v1, "another booking's": other, "unknown": uuid.uuid4()}


@pytest.mark.parametrize("decision", ["approve", "reject"])
async def test_est_14_a_stale_estimate_id_is_refused(
    db: Database, world: World, decision: str
) -> None:
    """EST-14 / SM-14: an `estimate_id` that is not this booking's current `SENT` version
    (superseded, another booking's or unknown) -> 409 `STALE_ESTIMATE`; nothing changes."""
    candidates = await stale_ids(db, world)
    before = statuses(await versions_of(db, world.booking_id))
    extra: dict[str, object] = {} if decision == "approve" else {"reason": "No"}
    for label, estimate_id in candidates.items():
        arguments = {
            "shop_id": world.shop_id,
            "booking_id": world.booking_id,
            "estimate_id": estimate_id,
            "decided_by_user_id": world.customer_id,
            "now": at(20),
            **extra,
        }
        with pytest.raises(StaleEstimate):
            await write(db, getattr(service, decision), **arguments)
        assert statuses(await versions_of(db, world.booking_id)) == before, label
    [other] = await versions_of(db, world.second_booking_id)
    assert other.status == SENT


async def test_est_14_a_decided_version_cannot_be_decided_again(db: Database, world: World) -> None:
    """A double click, or an old tab: the second decision on the same version is stale."""
    _, v2 = await sent_v2(db, world)
    arguments = {
        "shop_id": world.shop_id,
        "booking_id": world.booking_id,
        "estimate_id": v2,
        "decided_by_user_id": world.customer_id,
    }
    await write(db, service.approve, now=at(20), **arguments)
    with pytest.raises(StaleEstimate):
        await write(db, service.approve, now=at(21), **arguments)
    with pytest.raises(StaleEstimate):
        await write(db, service.reject, reason=None, now=at(21), **arguments)
    approved = (await versions_of(db, world.booking_id))[1]
    assert (approved.status, approved.decided_at) == (APPROVED, at(20))


@pytest.mark.parametrize(
    ("reason", "stored"),
    [
        ("Labour seems high", "Labour seems high"),
        ("  Labour seems high \n", "Labour seems high"),
        ("   ", None),
        (None, None),
        ("x" * 500, "x" * 500),
    ],
)
async def test_reject_stores_the_reason_as_customer_note(
    db: Database, world: World, reason: str | None, stored: str | None
) -> None:
    """T09 / EST-15: the version -> `REJECTED` with `decided_at`, `decided_by_user_id` and
    `customer_note` = the reason (trimmed; blank -> null)."""
    _, v2 = await sent_v2(db, world)
    snapshot = await write(
        db,
        service.reject,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        estimate_id=v2,
        decided_by_user_id=world.customer_id,
        reason=reason,
        now=at(20),
    )
    assert snapshot.status == REJECTED
    rejected = (await versions_of(db, world.booking_id))[1]
    assert (rejected.status, rejected.decided_at, rejected.decided_by_user_id) == (
        REJECTED,
        at(20),
        world.customer_id,
    )
    assert rejected.customer_note == stored


async def test_reject_reason_with_a_nul_character_is_a_validation_error(
    db: Database, world: World
) -> None:
    """PostgreSQL cannot store U+0000: 422 on `reason`, never a database 500."""
    _, v2 = await sent_v2(db, world)
    with pytest.raises(ValidationFailed) as caught:
        await write(
            db,
            service.reject,
            shop_id=world.shop_id,
            booking_id=world.booking_id,
            estimate_id=v2,
            decided_by_user_id=world.customer_id,
            reason="Too\x00expensive",
            now=at(20),
        )
    assert caught.value.errors is not None
    assert [(e["field"], e["code"]) for e in caught.value.errors] == [("reason", "value_error")]
    assert (await versions_of(db, world.booking_id))[1].status == SENT


async def test_reject_reason_longer_than_500_is_a_validation_error(
    db: Database, world: World
) -> None:
    _, v2 = await sent_v2(db, world)
    with pytest.raises(ValidationFailed) as caught:
        await write(
            db,
            service.reject,
            shop_id=world.shop_id,
            booking_id=world.booking_id,
            estimate_id=v2,
            decided_by_user_id=world.customer_id,
            reason="x" * 501,
            now=at(20),
        )
    assert caught.value.errors is not None
    assert [(e["field"], e["code"]) for e in caught.value.errors] == [("reason", "string_too_long")]
    assert (await versions_of(db, world.booking_id))[1].status == SENT


# --- T10 / T11 copy_rejected_to_draft -------------------------------------------------------------


async def test_est_15_revise_copies_the_rejected_version_verbatim(
    db: Database, world: World
) -> None:
    """EST-15: a new `DRAFT` `version + 1` authored by the acting SA - not by the rejected
    version's author (here the technician) - with every line copied verbatim and the same
    totals; the rejected version is unchanged."""
    await insert_version(db, world, version=1, status=SUPERSEDED, lines=worked_example_v1(world))
    v2_lines = [
        part_spec(world.coil_id, "Ignition coil", "6000"),
        part_spec(world.oil_id, "Engine oil 4 L", "5200", quantity="2"),
        labour_spec("Diagnosis and repair labour", "999", quantity="1.50"),
    ]
    v2 = await insert_version(
        db,
        world,
        version=2,
        status=REJECTED,
        lines=v2_lines,
        created_by=world.tech_id,
        customer_note="Labour seems high",
    )
    rejected_lines = await lines_of(db, v2)
    snapshot = await write(
        db,
        service.copy_rejected_to_draft,
        lock=world.booking_id,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        created_by_user_id=world.sa_id,
        now=at(30),
    )
    assert (snapshot.version, snapshot.status) == (3, DRAFT)
    assert snapshot.grand_total == Decimal("17899.00")  # 6,000 + 10,400 + 1,499 (half-up)
    versions = await versions_of(db, world.booking_id)
    assert statuses(versions) == [(1, SUPERSEDED), (2, REJECTED), (3, DRAFT)]
    rejected, draft = versions[1], versions[2]
    assert draft.id == snapshot.estimate_id
    assert (draft.created_by_user_id, draft.created_at, draft.updated_at) == (
        world.sa_id,
        at(30),
        at(30),
    )
    assert rejected.created_by_user_id == world.tech_id  # the author came from the actor
    assert draft.submitted_at is draft.sent_at is draft.decided_at is None
    assert (draft.parts_total, draft.labour_total, draft.grand_total) == (
        rejected.parts_total,
        rejected.labour_total,
        rejected.grand_total,
    )
    copied = await lines_of(db, draft.id)
    assert line_facts(copied) == line_facts(rejected_lines)
    assert {line.id for line in copied}.isdisjoint({line.id for line in rejected_lines})
    assert all(line.created_at == at(30) for line in copied)
    # The rejected version is untouched (EST-12): status, decision, note and its own lines.
    assert (rejected.status, rejected.customer_note, rejected.updated_at) == (
        REJECTED,
        "Labour seems high",
        at(2),
    )
    assert [line.id for line in await lines_of(db, v2)] == [line.id for line in rejected_lines]


@pytest.mark.parametrize("latest", [None, DRAFT, SUBMITTED, SENT, APPROVED, SUPERSEDED])
async def test_est_12_copy_is_refused_unless_the_latest_version_is_rejected(
    db: Database, world: World, latest: EstimateStatus | None
) -> None:
    """Backstop (T10/T11 only run from `ESTIMATE_REJECTED`): no copy of anything else."""
    if latest is not None:
        await insert_version(db, world, version=1, status=latest, lines=worked_example_v1(world))
    with pytest.raises(EstimateLocked):
        await write(
            db,
            service.copy_rejected_to_draft,
            shop_id=world.shop_id,
            booking_id=world.booking_id,
            created_by_user_id=world.sa_id,
            now=at(30),
        )
    assert len(await versions_of(db, world.booking_id)) == (0 if latest is None else 1)


async def test_a_rejected_version_is_copied_only_once(db: Database, world: World) -> None:
    """After a copy the latest version is the new draft: a repeated revise is refused (EST-16)."""
    await insert_version(db, world, version=1, status=REJECTED, lines=worked_example_v1(world))
    arguments = {
        "shop_id": world.shop_id,
        "booking_id": world.booking_id,
        "created_by_user_id": world.sa_id,
    }
    await write(db, service.copy_rejected_to_draft, now=at(30), **arguments)
    with pytest.raises(EstimateLocked):
        await write(db, service.copy_rejected_to_draft, now=at(31), **arguments)
    assert statuses(await versions_of(db, world.booking_id)) == [(1, REJECTED), (2, DRAFT)]


# --- T22 supersede_open_versions ------------------------------------------------------------------


@pytest.mark.parametrize("status", [DRAFT, SUBMITTED, SENT])
async def test_est_17_cancel_supersedes_the_open_version(
    db: Database, world: World, status: EstimateStatus
) -> None:
    """EST-17: `DRAFT`, `SUBMITTED` or `SENT` -> `SUPERSEDED`; a superseded `SENT` version keeps
    `sent_at` (`ck_estimates_sent_fields`). A second call finds nothing (idempotent)."""
    open_id = await insert_version(
        db, world, version=1, status=status, lines=worked_example_v1(world)
    )
    arguments = {"shop_id": world.shop_id, "booking_id": world.booking_id}
    superseded = await write(
        db, service.supersede_open_versions, lock=world.booking_id, now=at(40), **arguments
    )
    assert superseded == [open_id]
    [version] = await versions_of(db, world.booking_id)
    assert (version.status, version.updated_at) == (SUPERSEDED, at(40))
    assert (version.sent_at is not None) is (status == SENT)
    assert await write(db, service.supersede_open_versions, now=at(41), **arguments) == []


@pytest.mark.parametrize("status", [APPROVED, REJECTED])
async def test_est_17_cancel_leaves_decided_versions_alone(
    db: Database, world: World, status: EstimateStatus
) -> None:
    """EST-17: `APPROVED` and `REJECTED` stay as they are."""
    await insert_version(db, world, version=1, status=status, lines=worked_example_v1(world))
    superseded = await write(
        db,
        service.supersede_open_versions,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        now=at(40),
    )
    assert superseded == []
    [version] = await versions_of(db, world.booking_id)
    assert (version.status, version.updated_at) == (status, at(1))


async def test_est_17_cancel_after_a_revise_supersedes_only_the_new_draft(
    db: Database, world: World
) -> None:
    await insert_version(db, world, version=1, status=REJECTED, lines=worked_example_v1(world))
    draft = await insert_version(
        db, world, version=2, status=DRAFT, lines=worked_example_v1(world), created_by=world.sa_id
    )
    superseded = await write(
        db,
        service.supersede_open_versions,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        now=at(40),
    )
    assert superseded == [draft]
    assert statuses(await versions_of(db, world.booking_id)) == [(1, REJECTED), (2, SUPERSEDED)]


async def test_est_17_cancel_only_touches_its_own_booking(db: Database, world: World) -> None:
    await insert_version(db, world, version=1, status=SENT, lines=worked_example_v1(world))
    other = await insert_version(
        db,
        world,
        version=1,
        status=DRAFT,
        booking_id=world.second_booking_id,
        lines=worked_example_v1(world),
    )
    await write(
        db,
        service.supersede_open_versions,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        now=at(40),
    )
    [untouched] = await versions_of(db, world.second_booking_id)
    assert (untouched.id, untouched.status) == (other, DRAFT)


# --- Tenancy (D20) --------------------------------------------------------------------------------


async def test_another_shops_id_finds_nothing(db: Database, world: World) -> None:
    """Every function is scoped by `shop_id`: Shop B's id never reaches Shop A's versions."""
    _, v2 = await sent_v2(db, world)
    foreign = {"shop_id": world.other_shop_id, "booking_id": world.booking_id}
    with pytest.raises(EstimateLocked):
        await write(db, service.send, sent_by_user_id=world.sa_id, now=at(50), **foreign)
    with pytest.raises(StaleEstimate):
        await write(
            db,
            service.approve,
            estimate_id=v2,
            decided_by_user_id=world.customer_id,
            now=at(50),
            **foreign,
        )
    assert await write(db, service.supersede_open_versions, now=at(50), **foreign) == []
    view = await read(db, service.get_customer_view, **foreign)
    assert (view.estimate, view.revision_in_progress) == (None, False)
    assert await read(db, service.list_customer_versions, **foreign) == []
    summaries = await read(
        db,
        service.get_estimate_summaries,
        shop_id=world.other_shop_id,
        booking_ids=[world.booking_id],
        audience="staff",
    )
    assert summaries == {}
    assert statuses(await versions_of(db, world.booking_id)) == [(1, SUPERSEDED), (2, SENT)]
    assert (await versions_of(db, world.booking_id))[1].updated_at == at(2)


async def test_timestamps_are_the_callers_instant(db: Database, world: World) -> None:
    """D63: every timestamp an action writes is the `now` it was given, not the database clock."""
    _, v2 = await sent_v2(db, world)
    instant = at(0) + timedelta(days=3, microseconds=123456)
    await write(
        db,
        service.approve,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        estimate_id=v2,
        decided_by_user_id=world.customer_id,
        now=instant,
    )
    approved = (await versions_of(db, world.booking_id))[1]
    assert approved.decided_at == approved.updated_at == instant

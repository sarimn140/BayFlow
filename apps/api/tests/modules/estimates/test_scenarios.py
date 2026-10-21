"""Estimate journeys through every estimates function, as bookings will drive them (spec 08
T05-T12, T22, O1; spec 06 E1): the worked example's estimate steps (SM-18 ★, EST-05 ★), the
estimate-rejected paths (SM-08 ★, SM-09), cancellations (EST-17, EST-27) and stale approvals
(SM-14). After every step: EST-16 / DI-5 invariants and the §7.1 status table (EST-26)."""

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from app.core.database import Database
from app.core.errors import StaleEstimate
from app.modules.estimates import service
from app.modules.estimates.schemas import (
    CustomerEstimateView,
    EstimateEdit,
    EstimateLineWrite,
    EstimateSnapshot,
)
from app.modules.inventory.domain.stock import PartQty
from app.shared.enums import BookingStatus, EstimateStatus
from tests.modules.estimates.support import (
    World,
    assert_estimate_invariants,
    assert_latest_matches,
    at,
    edit,
    labour_line,
    part_line,
    read,
    versions_of,
    worked_example_lines,
    write,
)

pytestmark = pytest.mark.db

DRAFT = EstimateStatus.DRAFT
SUBMITTED = EstimateStatus.SUBMITTED
SENT = EstimateStatus.SENT
APPROVED = EstimateStatus.APPROVED
REJECTED = EstimateStatus.REJECTED
SUPERSEDED = EstimateStatus.SUPERSEDED


class Journey:
    """One booking's estimate, step by step, with a stepping clock (spec 12 §4.4) and the
    invariants checked after every step."""

    def __init__(self, db: Database, world: World) -> None:
        self.db = db
        self.world = world
        self.minute = 0
        self.status = BookingStatus.ASSIGNED
        self.common = {"shop_id": world.shop_id, "booking_id": world.booking_id}

    def now(self) -> datetime:
        self.minute += 1
        return at(self.minute)

    async def check(self, status: BookingStatus) -> None:
        self.status = status
        await assert_estimate_invariants(self.db, self.world.booking_id)
        await assert_latest_matches(self.db, self.world.booking_id, status)

    async def start_inspection(self) -> EstimateSnapshot:  # T05
        snapshot = await write(
            self.db,
            service.ensure_draft,
            lock=self.world.booking_id,
            created_by_user_id=self.world.tech_id,
            now=self.now(),
            **self.common,
        )
        await self.check(BookingStatus.INSPECTING)
        return snapshot

    async def edit(self, actor: uuid.UUID, lines: list[EstimateLineWrite]) -> EstimateEdit:  # O1
        result = await edit(
            self.db, self.world, status=self.status, actor=actor, lines=lines, now=self.now()
        )
        await self.check(self.status)
        return result

    async def submit(self) -> EstimateSnapshot:  # T06
        snapshot = await write(
            self.db, service.submit, lock=self.world.booking_id, now=self.now(), **self.common
        )
        await self.check(BookingStatus.ESTIMATE_REVIEW)
        return snapshot

    async def send(self, by: uuid.UUID) -> EstimateSnapshot:  # T07
        snapshot = await write(
            self.db,
            service.send,
            lock=self.world.booking_id,
            sent_by_user_id=by,
            now=self.now(),
            **self.common,
        )
        await self.check(BookingStatus.AWAITING_CUSTOMER)
        return snapshot

    async def approve(self, estimate_id: uuid.UUID) -> EstimateSnapshot:  # T08
        snapshot = await write(
            self.db,
            service.approve,
            lock=self.world.booking_id,
            estimate_id=estimate_id,
            decided_by_user_id=self.world.customer_id,
            now=self.now(),
            **self.common,
        )
        await self.check(BookingStatus.ESTIMATE_APPROVED)
        return snapshot

    async def reject(self, estimate_id: uuid.UUID, reason: str | None) -> EstimateSnapshot:  # T09
        snapshot = await write(
            self.db,
            service.reject,
            lock=self.world.booking_id,
            estimate_id=estimate_id,
            decided_by_user_id=self.world.customer_id,
            reason=reason,
            now=self.now(),
            **self.common,
        )
        await self.check(BookingStatus.ESTIMATE_REJECTED)
        return snapshot

    async def copy(self, by: uuid.UUID, then: BookingStatus) -> EstimateSnapshot:  # T10 / T11
        snapshot = await write(
            self.db,
            service.copy_rejected_to_draft,
            lock=self.world.booking_id,
            created_by_user_id=by,
            now=self.now(),
            **self.common,
        )
        await self.check(then)
        return snapshot

    async def cancel(self) -> list[uuid.UUID]:  # T22
        superseded = await write(
            self.db,
            service.supersede_open_versions,
            lock=self.world.booking_id,
            now=self.now(),
            **self.common,
        )
        await self.check(BookingStatus.CANCELLED)
        return superseded

    async def customer_view(self) -> CustomerEstimateView:
        return await read(self.db, service.get_customer_view, **self.common)

    async def shown(self) -> tuple[uuid.UUID | None, bool]:
        view = await self.customer_view()
        return (view.estimate.id if view.estimate else None), view.revision_in_progress

    async def statuses(self) -> list[tuple[int, EstimateStatus]]:
        return [(v.version, v.status) for v in await versions_of(self.db, self.world.booking_id)]

    async def sent_v1(self) -> uuid.UUID:
        """Steps 5 + send without a desk edit: v1 16,600 sent to the customer."""
        draft = await self.start_inspection()
        await self.edit(self.world.tech_id, worked_example_lines(self.world))
        await self.submit()
        await self.send(self.world.sa_id)
        return draft.estimate_id


async def test_sm_18_the_worked_example_estimate_steps(db: Database, world: World) -> None:
    """SM-18 ★ / EST-05 ★ (brief §6 steps 4-8): Imran's v1 is 16,600 (coil 6,500 + filter 900 +
    oil 5,200 + labour 4,000); Bilal's edit of labour to 3,500 creates v2 = 16,100 and supersedes
    v1; v2 is sent, Ahmed approves it with a timestamp; T12 needs one coil, one filter, one oil."""
    journey = Journey(db, world)
    await journey.check(BookingStatus.ASSIGNED)  # no estimate before the inspection

    v1 = (await journey.start_inspection()).estimate_id  # step 5
    imran = await journey.edit(world.tech_id, worked_example_lines(world))
    assert (imran.created_new_version, imran.estimate.grand_total) == (False, Decimal("16600.00"))
    submitted = await journey.submit()
    assert submitted.event_metadata() == {
        "estimate_id": str(v1),
        "version": 1,
        "grand_total": "16600.00",
    }
    assert await journey.shown() == (None, False)  # "Preparing your estimate" (SEC-12)

    bilal = await journey.edit(world.sa_id, worked_example_lines(world, labour="3500"))  # step 6
    assert bilal.created_new_version is True
    v2 = bilal.estimate
    assert (v2.version, v2.status, v2.created_by.full_name) == (2, DRAFT, "Bilal")
    assert (v2.parts_total, v2.labour_total, v2.grand_total) == (
        Decimal("12600.00"),
        Decimal("3500.00"),
        Decimal("16100.00"),
    )
    assert await journey.statuses() == [(1, SUPERSEDED), (2, DRAFT)]
    sent = await journey.send(world.sa_id)
    assert sent.event_metadata() == {
        "estimate_id": str(v2.id),
        "version": 2,
        "grand_total": "16100.00",
    }
    view = await journey.customer_view()  # step 7: Ahmed sees the pending estimate
    assert view.estimate is not None
    assert (view.estimate.id, view.estimate.status, view.estimate.grand_total) == (
        v2.id,
        SENT,
        Decimal("16100.00"),
    )
    assert [line.line_total for line in view.estimate.lines] == [
        Decimal("6500.00"),
        Decimal("900.00"),
        Decimal("5200.00"),
        Decimal("3500.00"),
    ]

    approved = await journey.approve(v2.id)
    assert (approved.status, approved.grand_total) == (APPROVED, Decimal("16100.00"))
    with pytest.raises(StaleEstimate):  # SM-14: an old tab still showing v1
        await journey.approve(v1)
    assert await journey.statuses() == [(1, SUPERSEDED), (2, APPROVED)]

    requirements = await read(db, service.get_approved_part_requirements, **journey.common)
    assert requirements == sorted(
        [PartQty(world.coil_id, 1), PartQty(world.filter_id, 1), PartQty(world.oil_id, 1)],
        key=lambda requirement: requirement.part_id,
    )
    history = await read(db, service.list_versions, include_stock=True, **journey.common)
    assert [(v.version, v.status, v.grand_total, v.created_by.full_name) for v in history] == [
        (1, SUPERSEDED, Decimal("16600.00"), "Imran"),
        (2, APPROVED, Decimal("16100.00"), "Bilal"),
    ]
    final = history[1]
    assert final.sent_by is not None
    assert final.decided_by is not None
    assert (final.sent_by.full_name, final.decided_by.full_name) == ("Bilal", "Ahmed")
    assert final.sent_at is not None
    assert final.decided_at is not None
    assert final.sent_at < final.decided_at  # the timeline follows the action order (D63)
    summaries = await read(
        db,
        service.get_estimate_summaries,
        shop_id=world.shop_id,
        booking_ids=[world.booking_id],
        audience="customer",
    )
    assert summaries[world.booking_id].model_dump(mode="json") == {
        "estimate_id": str(v2.id),
        "version": 2,
        "status": "APPROVED",
        "grand_total": "16100.00",
        "line_count": 4,
    }


async def test_sm_08_rejected_estimate_revised_by_the_sa(db: Database, world: World) -> None:
    """SM-08 ★ (spec 06 E1 path a): reject -> `revise-estimate` (v2 `DRAFT` copy by the SA) ->
    desk edits update v2 -> send -> approve. The customer sees v1 and "revision in progress"
    until v2 is sent."""
    journey = Journey(db, world)
    v1 = await journey.sent_v1()
    await journey.reject(v1, "Labour seems high")
    view = await journey.customer_view()
    assert view.estimate is not None
    assert (view.estimate.status, view.estimate.customer_note) == (REJECTED, "Labour seems high")

    v2 = await journey.copy(world.sa_id, then=BookingStatus.ESTIMATE_REVIEW)
    assert (v2.version, v2.status, v2.grand_total) == (2, DRAFT, Decimal("16600.00"))
    assert await journey.shown() == (v1, True)
    revised = await journey.edit(world.sa_id, worked_example_lines(world, labour="3000"))
    assert (revised.created_new_version, revised.estimate.id) == (False, v2.estimate_id)
    again = await journey.edit(world.sa_id, worked_example_lines(world, labour="2500"))
    assert again.created_new_version is False
    assert again.estimate.grand_total == Decimal("15100.00")
    await journey.send(world.sa_id)
    assert await journey.shown() == (v2.estimate_id, False)
    with pytest.raises(StaleEstimate):  # the rejected v1 cannot be approved any more
        await journey.approve(v1)
    await journey.approve(v2.estimate_id)
    assert await journey.statuses() == [(1, REJECTED), (2, APPROVED)]
    history = await read(db, service.list_customer_versions, **journey.common)
    assert [(v.version, v.status, v.grand_total) for v in history] == [
        (1, REJECTED, Decimal("16600.00")),
        (2, APPROVED, Decimal("15100.00")),
    ]


async def test_sm_09_rejected_estimate_returned_to_the_technician(
    db: Database, world: World
) -> None:
    """SM-09 (spec 06 E1 path b): reject -> `return-to-technician` (v2 `DRAFT` copy, author the
    SA) -> the technician edits v2 in `INSPECTING` -> submit -> the SA sends it unchanged ->
    approve."""
    journey = Journey(db, world)
    v1 = await journey.sent_v1()
    await journey.reject(v1, "Use an aftermarket coil")
    v2 = await journey.copy(world.sa_id, then=BookingStatus.INSPECTING)
    copied = (await versions_of(db, world.booking_id))[1]
    assert copied.created_by_user_id == world.sa_id
    cheaper = [
        part_line(world.coil_id, unit_price="3800"),
        part_line(world.filter_id),
        part_line(world.oil_id),
        labour_line("Diagnosis and repair labour", "4000"),
    ]
    technician = await journey.edit(world.tech_id, cheaper)
    assert (technician.created_new_version, technician.estimate.id) == (False, v2.estimate_id)
    assert technician.estimate.grand_total == Decimal("13900.00")
    resubmitted = await journey.submit()
    assert (resubmitted.estimate_id, resubmitted.status) == (v2.estimate_id, SUBMITTED)
    assert await journey.shown() == (v1, True)
    await journey.send(world.sa_id)
    await journey.approve(v2.estimate_id)
    assert await journey.statuses() == [(1, REJECTED), (2, APPROVED)]


async def test_sm_09_a_desk_edit_after_the_resubmission_creates_v3(
    db: Database, world: World
) -> None:
    """After a resubmission the SA's first edit is again a new version (D39): v2 `SUPERSEDED`,
    v3 sent and approved; customers only ever saw v1 and v3."""
    journey = Journey(db, world)
    v1 = await journey.sent_v1()
    await journey.reject(v1, None)
    await journey.copy(world.sa_id, then=BookingStatus.INSPECTING)
    await journey.edit(world.tech_id, worked_example_lines(world, labour="3800"))
    await journey.submit()
    desk = await journey.edit(world.owner_id, worked_example_lines(world, labour="3600"))
    assert (desk.created_new_version, desk.estimate.version) == (True, 3)
    assert desk.estimate.created_by.full_name == "Fatima Raza"
    await journey.send(world.owner_id)
    await journey.approve(desk.estimate.id)
    assert await journey.statuses() == [(1, REJECTED), (2, SUPERSEDED), (3, APPROVED)]
    history = await read(db, service.list_customer_versions, **journey.common)
    assert [(v.version, v.status) for v in history] == [(1, REJECTED), (3, APPROVED)]


async def test_est_17_cancel_while_inspecting(db: Database, world: World) -> None:
    journey = Journey(db, world)
    draft = await journey.start_inspection()
    await journey.edit(world.tech_id, worked_example_lines(world))
    assert await journey.cancel() == [draft.estimate_id]
    assert await journey.statuses() == [(1, SUPERSEDED)]
    assert await journey.shown() == (None, False)


async def test_est_27_cancel_while_awaiting_the_customer(db: Database, world: World) -> None:
    """EST-27: the sent version is superseded (keeps `sent_at`) and vanishes for the customer."""
    journey = Journey(db, world)
    v1 = await journey.sent_v1()
    assert await journey.cancel() == [v1]
    [version] = await versions_of(db, world.booking_id)
    assert (version.status, version.sent_at is not None) == (SUPERSEDED, True)
    assert await journey.shown() == (None, False)
    assert await read(db, service.list_customer_versions, **journey.common) == []


async def test_est_17_cancel_during_a_revision_keeps_the_rejected_version(
    db: Database, world: World
) -> None:
    journey = Journey(db, world)
    v1 = await journey.sent_v1()
    await journey.reject(v1, "Too expensive")
    v2 = await journey.copy(world.sa_id, then=BookingStatus.ESTIMATE_REVIEW)
    assert await journey.cancel() == [v2.estimate_id]
    assert await journey.statuses() == [(1, REJECTED), (2, SUPERSEDED)]
    assert await journey.shown() == (v1, False)  # EST-22: no revision after a cancellation


async def test_est_17_cancel_after_approval_leaves_the_approved_version(
    db: Database, world: World
) -> None:
    journey = Journey(db, world)
    v1 = await journey.sent_v1()
    await journey.approve(v1)
    assert await journey.cancel() == []
    assert await journey.statuses() == [(1, APPROVED)]
    assert await journey.shown() == (v1, False)

"""Editing and submitting an estimate at the service layer (O1, T06; D39-D41;
`modules/estimates.md` §7.2-§7.6): EST-02, EST-03, EST-05, EST-07, EST-09, EST-10, EST-11,
EST-12, EST-18, EST-20, EST-21, EST-23, EST-24 (service halves), SEC-35."""

import uuid
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, update

from app.core.database import Database
from app.core.error_handlers import register_error_handlers
from app.core.errors import EstimateEmpty, EstimateLocked, ValidationFailed
from app.modules.estimates import service
from app.modules.estimates.models import Estimate, EstimateLine
from app.modules.estimates.schemas import EstimateEditRead, EstimateUpdate
from app.shared.enums import BookingStatus, EstimateLineType, EstimateStatus, StockState
from tests.modules.estimates.support import (
    World,
    assert_estimate_invariants,
    at,
    edit,
    insert_version,
    labour_line,
    line_facts,
    lines_of,
    lock_booking,
    new_uow,
    part_line,
    set_part,
    versions_of,
    worked_example_lines,
    worked_example_v1,
    write,
)

pytestmark = pytest.mark.db

INSPECTING = BookingStatus.INSPECTING
ESTIMATE_REVIEW = BookingStatus.ESTIMATE_REVIEW
DRAFT = EstimateStatus.DRAFT
SUBMITTED = EstimateStatus.SUBMITTED
SENT = EstimateStatus.SENT
APPROVED = EstimateStatus.APPROVED
REJECTED = EstimateStatus.REJECTED
SUPERSEDED = EstimateStatus.SUPERSEDED


async def start_inspection(db: Database, world: World) -> uuid.UUID:
    snapshot = await write(
        db,
        service.ensure_draft,
        lock=world.booking_id,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        created_by_user_id=world.tech_id,
        now=at(0),
    )
    return snapshot.estimate_id


async def submitted_v1(db: Database, world: World) -> uuid.UUID:
    """Brief §6 step 5: Imran's v1 at 16,600, submitted."""
    v1 = await start_inspection(db, world)
    await edit(
        db,
        world,
        status=INSPECTING,
        actor=world.tech_id,
        lines=worked_example_lines(world),
        now=at(1),
    )
    await write(db, service.submit, shop_id=world.shop_id, booking_id=world.booking_id, now=at(2))
    return v1


def field_codes(error: ValidationFailed) -> list[tuple[str, str]]:
    assert error.errors is not None
    return [(item["field"], item["code"]) for item in error.errors]


# --- O1 in INSPECTING: the technician's draft is edited in place ----------------------------------


async def test_est_02_the_technician_edits_v1_in_place(db: Database, world: World) -> None:
    """EST-02: in `INSPECTING` the technician's `DRAFT` v1 is replaced in place - no new version
    (`created_new_version` false, so bookings writes no event and keeps its version, D30)."""
    v1 = await start_inspection(db, world)
    first = await edit(
        db,
        world,
        status=INSPECTING,
        actor=world.tech_id,
        lines=worked_example_lines(world),
        now=at(1),
    )
    assert first.created_new_version is False
    assert (first.estimate.id, first.estimate.version, first.estimate.status) == (v1, 1, DRAFT)
    assert first.estimate.grand_total == Decimal("16600.00")
    assert [line.position for line in first.estimate.lines] == [1, 2, 3, 4]
    old_line_ids = {line.id for line in await lines_of(db, v1)}

    second = await edit(
        db,
        world,
        status=INSPECTING,
        actor=world.tech_id,
        lines=[labour_line("Diagnosis", "1500"), part_line(world.filter_id, quantity="2")],
        now=at(2),
    )
    assert second.created_new_version is False
    assert second.estimate.id == v1
    [version] = await versions_of(db, world.booking_id)
    assert (version.status, version.created_at, version.updated_at) == (DRAFT, at(0), at(2))
    assert (version.parts_total, version.labour_total, version.grand_total) == (
        Decimal("1800.00"),
        Decimal("1500.00"),
        Decimal("3300.00"),
    )
    stored = await lines_of(db, v1)
    assert [(line.position, line.description, line.quantity) for line in stored] == [
        (1, "Diagnosis", Decimal("1.00")),
        (2, "Oil filter", Decimal("2.00")),
    ]
    assert old_line_ids.isdisjoint({line.id for line in stored})  # replaced, not appended
    await assert_estimate_invariants(db, world.booking_id)


async def test_a_repeated_identical_save_is_harmless(db: Database, world: World) -> None:
    """Spec 03 §1.7: `PUT …/estimate` is idempotent - same lines, same totals, one version."""
    await start_inspection(db, world)
    for minute in (1, 2, 3):
        result = await edit(
            db,
            world,
            status=INSPECTING,
            actor=world.tech_id,
            lines=worked_example_lines(world),
            now=at(minute),
        )
        assert result.created_new_version is False
        assert result.estimate.grand_total == Decimal("16600.00")
    [version] = await versions_of(db, world.booking_id)
    assert len(await lines_of(db, version.id)) == 4


# --- O1 in ESTIMATE_REVIEW: the first desk edit creates a version ---------------------------------


async def test_est_03_the_first_sa_edit_creates_v2_and_later_edits_update_it(
    db: Database, world: World
) -> None:
    """EST-03 (brief §6 step 6): Bilal's edit of the `SUBMITTED` v1 creates v2 `DRAFT` (author =
    Bilal) at 16,100 and supersedes v1; further desk edits (Bilal, or the Owner, D16) update v2."""
    v1 = await submitted_v1(db, world)
    v1_lines = line_facts(await lines_of(db, v1))
    first = await edit(
        db,
        world,
        status=ESTIMATE_REVIEW,
        actor=world.sa_id,
        lines=worked_example_lines(world, labour="3500"),
        now=at(3),
    )
    assert first.created_new_version is True
    v2 = first.estimate
    assert (v2.version, v2.status, v2.grand_total) == (2, DRAFT, Decimal("16100.00"))
    assert (v2.created_by.user_id, v2.created_by.full_name) == (world.sa_id, "Bilal")
    versions = await versions_of(db, world.booking_id)
    assert [(v.version, v.status) for v in versions] == [(1, SUPERSEDED), (2, DRAFT)]
    assert versions[0].updated_at == at(3)
    assert versions[0].grand_total == Decimal("16600.00")  # v1 itself is frozen (EST-12)
    assert line_facts(await lines_of(db, v1)) == v1_lines

    again = await edit(
        db,
        world,
        status=ESTIMATE_REVIEW,
        actor=world.owner_id,
        lines=[*worked_example_lines(world, labour="3500")[:3], labour_line("Labour", "3000")],
        now=at(4),
    )
    assert again.created_new_version is False
    assert (again.estimate.id, again.estimate.version) == (v2.id, 2)
    assert again.estimate.grand_total == Decimal("15600.00")
    assert again.estimate.created_by.user_id == world.sa_id  # the version's author stays
    assert len(await versions_of(db, world.booking_id)) == 2
    await assert_estimate_invariants(db, world.booking_id)


@pytest.mark.parametrize("path", ["new version", "in place"])
async def test_validation_runs_before_any_write(db: Database, world: World, path: str) -> None:
    """A 422 is decided before the first write. Checked inside the caller's still-open
    transaction, before its rollback: the `SUBMITTED` v1 is not superseded and no v2 exists, or
    the technician's draft still has its lines - an implementation that superseded or deleted
    first (even unflushed: the query autoflushes) fails here."""
    if path == "new version":
        estimate_id = await submitted_v1(db, world)
        booking_status, actor, expected = ESTIMATE_REVIEW, world.sa_id, (SUBMITTED, at(2))
    else:
        estimate_id = await start_inspection(db, world)
        await edit(
            db,
            world,
            status=INSPECTING,
            actor=world.tech_id,
            lines=worked_example_lines(world),
            now=at(1),
        )
        booking_status, actor, expected = INSPECTING, world.tech_id, (DRAFT, at(1))
    async with db.sessionmaker() as session:
        await lock_booking(session, world.booking_id)
        with pytest.raises(ValidationFailed):
            await service.replace_lines(
                new_uow(session),
                shop_id=world.shop_id,
                booking_id=world.booking_id,
                booking_status=booking_status,
                actor_user_id=actor,
                lines=[part_line(world.retired_id), labour_line("Labour", "3500")],
                now=at(3),
            )
        in_transaction = (
            await session.execute(
                select(Estimate.id, Estimate.status, Estimate.updated_at).where(
                    Estimate.booking_id == world.booking_id
                )
            )
        ).all()
        line_count = (
            await session.execute(
                select(func.count(EstimateLine.id)).where(EstimateLine.estimate_id == estimate_id)
            )
        ).scalar_one()
        await session.rollback()
    assert [(row.id, row.status, row.updated_at) for row in in_transaction] == [
        (estimate_id, *expected)
    ]
    assert line_count == 4


async def test_est_03_an_sa_edit_after_a_revise_updates_the_copied_draft(
    db: Database, world: World
) -> None:
    """After `REVISE_ESTIMATE` the latest version is the desk's `DRAFT`: edited in place."""
    await insert_version(db, world, version=1, status=REJECTED, lines=worked_example_v1(world))
    copy = await write(
        db,
        service.copy_rejected_to_draft,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        created_by_user_id=world.sa_id,
        now=at(10),
    )
    result = await edit(
        db,
        world,
        status=ESTIMATE_REVIEW,
        actor=world.sa_id,
        lines=worked_example_lines(world, labour="2500"),
        now=at(11),
    )
    assert result.created_new_version is False
    assert result.estimate.id == copy.estimate_id
    assert result.estimate.grand_total == Decimal("15100.00")


# --- EST-11 / EST-12: frozen versions and the backstop --------------------------------------------


@pytest.mark.parametrize(
    ("booking_status", "latest"),
    [
        (BookingStatus.INSPECTING, None),
        (BookingStatus.INSPECTING, SUBMITTED),  # the technician after submitting
        (BookingStatus.ESTIMATE_REVIEW, SENT),
        (BookingStatus.AWAITING_CUSTOMER, SENT),  # SEC-35: after send
        (BookingStatus.ESTIMATE_APPROVED, APPROVED),  # SEC-35: after approval
        (BookingStatus.ESTIMATE_REJECTED, REJECTED),
        (BookingStatus.CANCELLED, SUPERSEDED),
        (BookingStatus.ASSIGNED, DRAFT),  # a draft outside an editable status
        (BookingStatus.IN_REPAIR, APPROVED),
    ],
)
async def test_est_11_editing_outside_the_editable_combinations_is_locked(
    db: Database, world: World, booking_status: BookingStatus, latest: EstimateStatus | None
) -> None:
    """EST-11 / EST-12 / SEC-35 (backstop half): 409 `ESTIMATE_LOCKED`; lines and totals of the
    latest version are unchanged."""
    if latest is not None:
        await insert_version(db, world, version=1, status=latest, lines=worked_example_v1(world))
    before = await versions_of(db, world.booking_id)
    before_lines = [line_facts(await lines_of(db, version.id)) for version in before]
    with pytest.raises(EstimateLocked) as caught:
        await edit(
            db,
            world,
            status=booking_status,
            actor=world.sa_id,
            lines=[labour_line("Tampering", "1")],
            now=at(9),
        )
    assert caught.value.status_code == 409
    after = await versions_of(db, world.booking_id)
    assert [(v.status, v.grand_total, v.updated_at) for v in after] == [
        (v.status, v.grand_total, v.updated_at) for v in before
    ]
    assert [line_facts(await lines_of(db, version.id)) for version in after] == before_lines


@pytest.mark.parametrize("frozen", [SENT, APPROVED, REJECTED, SUPERSEDED])
async def test_est_12_frozen_versions_cannot_be_submitted(
    db: Database, world: World, frozen: EstimateStatus
) -> None:
    """EST-12: no function changes the lines or status of a frozen version."""
    await insert_version(db, world, version=1, status=frozen, lines=worked_example_v1(world))
    with pytest.raises(EstimateLocked):
        await write(
            db, service.submit, shop_id=world.shop_id, booking_id=world.booking_id, now=at(9)
        )
    [version] = await versions_of(db, world.booking_id)
    assert (version.status, version.updated_at) == (frozen, at(1))


# --- Line validation and pricing ------------------------------------------------------------------


@pytest.mark.parametrize("which", ["inactive", "other shop", "unknown"])
async def test_est_07_a_part_line_needs_an_active_part_of_this_shop(
    db: Database, world: World, which: str
) -> None:
    """EST-07: another shop's, an inactive or an unknown part -> 422 `VALIDATION_ERROR`
    `lines.N.part_id` `invalid_reference`; nothing is written."""
    part_id = {
        "inactive": world.retired_id,
        "other shop": world.foreign_part_id,
        "unknown": uuid.uuid4(),
    }[which]
    v1 = await start_inspection(db, world)
    with pytest.raises(ValidationFailed) as caught:
        await edit(
            db,
            world,
            status=INSPECTING,
            actor=world.tech_id,
            lines=[labour_line("Diagnosis", "1000"), part_line(part_id)],
            now=at(1),
        )
    assert field_codes(caught.value) == [("lines.1.part_id", "invalid_reference")]
    assert await lines_of(db, v1) == []
    [version] = await versions_of(db, world.booking_id)
    assert (version.grand_total, version.updated_at) == (Decimal("0.00"), at(0))


async def test_est_24_every_invalid_line_is_reported_in_one_error(
    db: Database, world: World
) -> None:
    """EST-24: one 422 lists every invalid line (`lines.0.part_id`, `lines.2.part_id`,
    `lines.3.quantity`, …), not just the first."""
    await start_inspection(db, world)
    with pytest.raises(ValidationFailed) as caught:
        await edit(
            db,
            world,
            status=INSPECTING,
            actor=world.tech_id,
            lines=[
                part_line(world.retired_id),
                labour_line("Diagnosis", "1000"),
                part_line(world.foreign_part_id),
                part_line(world.filter_id, quantity="9999", unit_price="9999999999"),
            ],
            now=at(1),
        )
    assert field_codes(caught.value) == [
        ("lines.0.part_id", "invalid_reference"),
        ("lines.2.part_id", "invalid_reference"),
        ("lines.3.quantity", "value_error"),
    ]


async def test_est_09_part_price_defaults_to_unit_cost_and_can_be_overridden(
    db: Database, world: World
) -> None:
    """EST-09: no `unit_price` -> `parts.unit_cost`; a given whole-rupee price wins."""
    await start_inspection(db, world)
    result = await edit(
        db,
        world,
        status=INSPECTING,
        actor=world.tech_id,
        lines=[part_line(world.filter_id), part_line(world.filter_id, unit_price="850")],
        now=at(1),
    )
    assert [line.unit_price for line in result.estimate.lines] == [
        Decimal("900.00"),
        Decimal("850.00"),
    ]
    assert result.estimate.parts_total == Decimal("1750.00")


async def test_est_20_line_totals_round_half_up_and_serialise_as_two_places(
    db: Database, world: World
) -> None:
    """EST-20 / EST-06: 1.50 x 999 is stored and sent as `"1499.00"`; totals are the sums of the
    rounded lines; part quantities are whole, labour quantities decimals."""
    await start_inspection(db, world)
    result = await edit(
        db,
        world,
        status=INSPECTING,
        actor=world.tech_id,
        lines=[
            labour_line("Labour", "999", quantity="1.5"),
            labour_line("Half", "1", quantity="0.50"),
            part_line(world.oil_id, quantity="2"),
        ],
        now=at(1),
    )
    body = EstimateEditRead.from_edit(result, booking_version=4).model_dump(mode="json")
    assert [line["line_total"] for line in body["lines"]] == ["1499.00", "1.00", "10400.00"]
    assert [line["quantity"] for line in body["lines"]] == ["1.50", "0.50", "2.00"]
    assert (body["labour_total"], body["parts_total"], body["grand_total"]) == (
        "1500.00",
        "10400.00",
        "11900.00",
    )
    assert (body["booking_version"], body["created_new_version"]) == (4, False)
    await assert_estimate_invariants(db, world.booking_id)


async def test_est_21_amounts_too_large_for_the_database_are_422_not_500(
    db: Database, world: World
) -> None:
    """EST-21: 9 999 x 9 999 999 999 -> 422 `lines.0.quantity` `value_error` "The amount is too
    large."; a grand total above the limit -> `lines`; nothing is written either time."""
    v1 = await start_inspection(db, world)
    with pytest.raises(ValidationFailed) as caught:
        await edit(
            db,
            world,
            status=INSPECTING,
            actor=world.tech_id,
            lines=[part_line(world.filter_id, quantity="9999", unit_price="9999999999")],
            now=at(1),
        )
    assert caught.value.errors == [
        {"field": "lines.0.quantity", "message": "The amount is too large.", "code": "value_error"}
    ]
    with pytest.raises(ValidationFailed) as caught:
        await edit(
            db,
            world,
            status=INSPECTING,
            actor=world.tech_id,
            lines=[labour_line("A", "5000000000"), labour_line("B", "5000000000")],
            now=at(2),
        )
    assert field_codes(caught.value) == [("lines", "value_error")]
    assert await lines_of(db, v1) == []
    largest = await edit(
        db,
        world,
        status=INSPECTING,
        actor=world.tech_id,
        lines=[labour_line("A", "5000000000"), labour_line("B", "4999999999")],
        now=at(3),
    )
    assert largest.estimate.grand_total == Decimal("9999999999.00")


async def test_est_18_part_lines_carry_live_stock(db: Database, world: World) -> None:
    """EST-18: each `PART` line shows the part's live stock - available = on_hand - reserved
    and the Out/Low/OK flag (D40, D45); an out-of-stock part can still be added; labour lines
    have no part."""
    await start_inspection(db, world)
    result = await edit(
        db,
        world,
        status=INSPECTING,
        actor=world.tech_id,
        lines=worked_example_lines(world),
        now=at(1),
    )
    coil, oil_filter, oil, labour = result.estimate.lines
    assert coil.part is not None
    assert (coil.part.id, coil.part.sku, coil.part.name) == (
        world.coil_id,
        "COIL-1",
        "Ignition coil",
    )
    assert (coil.part.on_hand, coil.part.available, coil.part.stock_state) == (0, 0, StockState.OUT)
    assert oil_filter.part is not None
    assert (oil_filter.part.on_hand, oil_filter.part.reserved, oil_filter.part.available) == (
        10,
        1,
        9,
    )
    assert oil_filter.part.stock_state == StockState.OK
    assert oil.part is not None
    assert (oil.part.available, oil.part.reorder_level, oil.part.stock_state) == (
        8,
        8,
        StockState.LOW,
    )
    assert labour.part is None
    assert labour.line_type == EstimateLineType.LABOUR


async def test_est_23_part_descriptions_are_copied_from_the_catalogue_at_save_time(
    db: Database, world: World
) -> None:
    """EST-23: the line stores the catalogue name; renaming the part later leaves the sent and
    approved versions unchanged, and the next draft save shows the new name."""
    await submitted_v1(db, world)
    await write(
        db,
        service.send,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        sent_by_user_id=world.sa_id,
        now=at(3),
    )
    [v1] = await versions_of(db, world.booking_id)
    await write(
        db,
        service.reject,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        estimate_id=v1.id,
        decided_by_user_id=world.customer_id,
        reason=None,
        now=at(4),
    )
    await set_part(db, world.coil_id, name="Ignition coil (OEM)")
    assert (await lines_of(db, v1.id))[0].description == "Ignition coil"
    await write(
        db,
        service.copy_rejected_to_draft,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        created_by_user_id=world.sa_id,
        now=at(5),
    )
    v2 = (await versions_of(db, world.booking_id))[1]
    assert (await lines_of(db, v2.id))[0].description == "Ignition coil"  # verbatim copy
    result = await edit(
        db,
        world,
        status=ESTIMATE_REVIEW,
        actor=world.sa_id,
        lines=worked_example_lines(world),
        now=at(6),
    )
    assert result.estimate.lines[0].description == "Ignition coil (OEM)"
    assert (await lines_of(db, v1.id))[0].description == "Ignition coil"


async def test_a_copied_line_with_a_part_deactivated_meanwhile_fails_the_next_save(
    db: Database, world: World
) -> None:
    """§7.6: the copy keeps the old line verbatim; the next save re-validates it (422)."""
    await insert_version(db, world, version=1, status=REJECTED, lines=worked_example_v1(world))
    await write(
        db,
        service.copy_rejected_to_draft,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        created_by_user_id=world.sa_id,
        now=at(5),
    )
    await set_part(db, world.oil_id, is_active=False)
    with pytest.raises(ValidationFailed) as caught:
        await edit(
            db,
            world,
            status=ESTIMATE_REVIEW,
            actor=world.sa_id,
            lines=worked_example_lines(world),
            now=at(6),
        )
    assert field_codes(caught.value) == [("lines.2.part_id", "invalid_reference")]


# --- T06 submit -----------------------------------------------------------------------------------


async def test_t06_submit_freezes_the_draft_with_recomputed_totals(
    db: Database, world: World
) -> None:
    v1 = await start_inspection(db, world)
    await edit(
        db,
        world,
        status=INSPECTING,
        actor=world.tech_id,
        lines=worked_example_lines(world),
        now=at(1),
    )
    snapshot = await write(
        db,
        service.submit,
        lock=world.booking_id,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        now=at(2),
    )
    assert (snapshot.estimate_id, snapshot.version, snapshot.status) == (v1, 1, SUBMITTED)
    assert snapshot.grand_total == Decimal("16600.00")
    [version] = await versions_of(db, world.booking_id)
    assert (version.submitted_at, version.updated_at) == (at(2), at(2))
    with pytest.raises(EstimateLocked):  # a double submit
        await write(
            db, service.submit, shop_id=world.shop_id, booking_id=world.booking_id, now=at(3)
        )
    with pytest.raises(EstimateLocked):  # SEC-35: the technician's edits are locked from now on
        await edit(
            db,
            world,
            status=INSPECTING,
            actor=world.tech_id,
            lines=[labour_line("Late change", "1")],
            now=at(3),
        )


async def test_t06_submit_recomputes_the_cached_totals_from_the_lines(
    db: Database, world: World
) -> None:
    """Totals are always recomputed on the server (D40, DI-5), even from a stale cache."""
    v1 = await insert_version(db, world, version=1, status=DRAFT, lines=worked_example_v1(world))
    async with db.sessionmaker() as session:
        await session.execute(
            update(Estimate)
            .where(Estimate.id == v1)
            .values(parts_total=0, labour_total=0, grand_total=0)
        )
        await session.commit()
    snapshot = await write(
        db, service.submit, shop_id=world.shop_id, booking_id=world.booking_id, now=at(5)
    )
    assert snapshot.grand_total == Decimal("16600.00")
    [submitted] = await versions_of(db, world.booking_id)
    assert (submitted.status, submitted.parts_total, submitted.labour_total) == (
        SUBMITTED,
        Decimal("12600.00"),
        Decimal("4000.00"),
    )
    assert submitted.grand_total == Decimal("16600.00")


async def test_est_10_submitting_an_empty_draft_is_estimate_empty(
    db: Database, world: World
) -> None:
    """EST-10: the never-saved v1 of `start-inspection` cannot be submitted (field `lines`)."""
    await start_inspection(db, world)
    with pytest.raises(EstimateEmpty) as caught:
        await write(
            db, service.submit, shop_id=world.shop_id, booking_id=world.booking_id, now=at(1)
        )
    assert caught.value.errors is not None
    assert [(e["field"], e["code"]) for e in caught.value.errors] == [("lines", "too_short")]
    [version] = await versions_of(db, world.booking_id)
    assert version.status == DRAFT


async def test_t06_submit_refuses_parts_deactivated_since_they_were_added(
    db: Database, world: World
) -> None:
    """Spec 03 §5.2: every `PART` line whose part was deactivated after the save ->
    `lines.N.part_id` `invalid_reference`, all in one 422; the draft stays a draft."""
    await start_inspection(db, world)
    await edit(
        db,
        world,
        status=INSPECTING,
        actor=world.tech_id,
        lines=worked_example_lines(world),
        now=at(1),
    )
    await set_part(db, world.coil_id, is_active=False)
    await set_part(db, world.oil_id, is_active=False)
    with pytest.raises(ValidationFailed) as caught:
        await write(
            db, service.submit, shop_id=world.shop_id, booking_id=world.booking_id, now=at(2)
        )
    assert field_codes(caught.value) == [
        ("lines.0.part_id", "invalid_reference"),
        ("lines.2.part_id", "invalid_reference"),
    ]
    [version] = await versions_of(db, world.booking_id)
    assert (version.status, version.submitted_at) == (DRAFT, None)
    await set_part(db, world.coil_id, is_active=True)
    await set_part(db, world.oil_id, is_active=True)
    snapshot = await write(
        db, service.submit, shop_id=world.shop_id, booking_id=world.booking_id, now=at(3)
    )
    assert snapshot.status == SUBMITTED


async def test_labour_only_estimates_need_no_parts(db: Database, world: World) -> None:
    """D31: a labour-only job is a normal estimate (no inventory call is needed)."""
    await start_inspection(db, world)
    result = await edit(
        db,
        world,
        status=INSPECTING,
        actor=world.tech_id,
        lines=[labour_line("Four-wheel alignment", "2000")],
        now=at(1),
    )
    assert (result.estimate.parts_total, result.estimate.grand_total) == (
        Decimal("0.00"),
        Decimal("2000.00"),
    )
    snapshot = await write(
        db, service.submit, shop_id=world.shop_id, booking_id=world.booking_id, now=at(2)
    )
    assert snapshot.status == SUBMITTED


async def test_edits_are_scoped_to_the_shop(db: Database, world: World) -> None:
    """D20: Shop B's id never edits Shop A's draft (no version is found -> locked)."""
    await start_inspection(db, world)
    with pytest.raises(EstimateLocked):
        await edit(
            db,
            world,
            status=INSPECTING,
            actor=world.tech_id,
            lines=[labour_line("Diagnosis", "1000")],
            now=at(1),
            shop_id=world.other_shop_id,
        )
    [version] = await versions_of(db, world.booking_id)
    assert await lines_of(db, version.id) == []


async def test_a_put_with_a_negative_zero_price_answers_0_00(db: Database, world: World) -> None:
    """`unit_price` `"-0"` is zero (`app.shared.money` normalises the sign): a `PUT …/estimate`
    answers `"0.00"`, never `"-0.00"`, for the price, the line total and the totals."""
    estimate_id = await start_inspection(db, world)
    app = FastAPI()
    register_error_handlers(app)

    @app.put("/estimate")
    async def put_estimate(body: EstimateUpdate) -> EstimateEditRead:  # as bookings will serve it
        async with db.sessionmaker() as session:
            await lock_booking(session, world.booking_id)
            uow = new_uow(session)
            result = await service.replace_lines(
                uow,
                shop_id=world.shop_id,
                booking_id=world.booking_id,
                booking_status=INSPECTING,
                actor_user_id=world.tech_id,
                lines=body.lines,
                now=at(1),
            )
            await uow.commit()
        return EstimateEditRead.from_edit(result, booking_version=1)

    payload = {
        "lines": [
            {
                "line_type": "LABOUR",
                "description": "Goodwill check",
                "quantity": "1",
                "unit_price": "-0",
            },
            {
                "line_type": "PART",
                "part_id": str(world.filter_id),
                "quantity": "2",
                "unit_price": "-0",
            },
            {
                "line_type": "LABOUR",
                "description": "Labour",
                "quantity": "1.5",
                "unit_price": "1000",
            },
        ]
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put("/estimate", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [(line["unit_price"], line["line_total"]) for line in body["lines"]] == [
        ("0.00", "0.00"),
        ("0.00", "0.00"),
        ("1000.00", "1500.00"),
    ]
    assert (body["parts_total"], body["labour_total"], body["grand_total"]) == (
        "0.00",
        "1500.00",
        "1500.00",
    )
    stored = await lines_of(db, estimate_id)
    assert [str(line.unit_price) for line in stored] == ["0.00", "0.00", "1000.00"]

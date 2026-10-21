"""Staff estimate reads and the T12 part requirements (`modules/estimates.md` §7.6, §7.8): every
version with live stock (EST-18), QC callers without stock (spec 04 §B), fixed query counts, and
`get_approved_part_requirements` (T12, D31)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection

from app.core.database import Database
from app.core.errors import InternalError
from app.modules.estimates import service
from app.modules.inventory.domain.stock import PartQty
from app.shared.enums import EstimateLineType, EstimateStatus, StockState
from tests.modules.estimates.support import (
    World,
    at,
    insert_version,
    labour_spec,
    part_spec,
    read,
    set_part,
    worked_example_v1,
)

pytestmark = pytest.mark.db

SUPERSEDED = EstimateStatus.SUPERSEDED
SENT = EstimateStatus.SENT
APPROVED = EstimateStatus.APPROVED
REJECTED = EstimateStatus.REJECTED


async def decided_history(db: Database, world: World) -> tuple[uuid.UUID, uuid.UUID]:
    """v1 superseded (Imran's 16,600), v2 approved (Bilal's 16,100)."""
    v1 = await insert_version(
        db, world, version=1, status=SUPERSEDED, lines=worked_example_v1(world)
    )
    v2_lines = [*worked_example_v1(world)[:3], labour_spec("Diagnosis and repair labour", "3500")]
    v2 = await insert_version(
        db, world, version=2, status=APPROVED, lines=v2_lines, created_by=world.sa_id
    )
    return v1, v2


async def test_list_versions_returns_every_version_ascending_with_its_people(
    db: Database, world: World
) -> None:
    """`GET …/estimates`: all versions, ascending, with author, sender and decider names and the
    totals the history shows (brief §7.5 "revision count")."""
    v1, v2 = await decided_history(db, world)
    versions = await read(
        db,
        service.list_versions,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        include_stock=True,
    )
    assert [(v.id, v.version, v.status, v.grand_total) for v in versions] == [
        (v1, 1, SUPERSEDED, Decimal("16600.00")),
        (v2, 2, APPROVED, Decimal("16100.00")),
    ]
    first, second = versions
    assert (first.created_by.full_name, first.sent_by, first.decided_by) == ("Imran", None, None)
    assert second.created_by.full_name == "Bilal"
    assert second.sent_by is not None
    assert second.sent_by.full_name == "Bilal"
    assert second.decided_by is not None
    assert (second.decided_by.user_id, second.decided_by.full_name) == (world.customer_id, "Ahmed")
    assert (second.sent_at, second.decided_at) == (at(2), at(2).replace(second=30))
    assert [line.description for line in second.lines] == [
        "Ignition coil",
        "Oil filter",
        "Engine oil 4 L",
        "Diagnosis and repair labour",
    ]
    assert all(line.part is not None for line in second.lines[:3])
    assert second.lines[3].part is None
    body = second.model_dump(mode="json")
    assert body["created_by"] == {"user_id": str(world.sa_id), "full_name": "Bilal"}
    assert body["lines"][1]["part"]["available"] == 9
    assert body["lines"][1]["part"]["unit_cost"] == "900.00"
    assert body["decided_at"] == "2026-10-16T05:02:30Z"


async def test_est_18_stock_is_live_at_read_time_and_hidden_from_qc(
    db: Database, world: World
) -> None:
    """EST-18 / spec 04 §B: stock is read when the response is built (never stored); QC callers
    (`include_stock=False`) get the part without stock fields."""
    await decided_history(db, world)
    await set_part(db, world.filter_id, on_hand=1, reserved=1)
    staff = await read(
        db,
        service.list_versions,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        include_stock=True,
    )
    filter_part = staff[1].lines[1].part
    assert filter_part is not None
    assert (filter_part.on_hand, filter_part.available, filter_part.stock_state) == (
        1,
        0,
        StockState.OUT,
    )
    qc = await read(
        db,
        service.list_versions,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        include_stock=False,
    )
    qc_part = qc[1].lines[1].part
    assert qc_part is not None
    assert (qc_part.id, qc_part.sku, qc_part.name, qc_part.unit_cost) == (
        world.filter_id,
        "FILTER-1",
        "Oil filter",
        Decimal("900.00"),
    )
    assert (
        qc_part.on_hand,
        qc_part.reserved,
        qc_part.available,
        qc_part.reorder_level,
        qc_part.stock_state,
    ) == (None, None, None, None, None)


async def test_a_deactivated_part_still_shows_on_old_versions(db: Database, world: World) -> None:
    await decided_history(db, world)
    await set_part(db, world.coil_id, is_active=False)
    versions = await read(
        db,
        service.list_versions,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
        include_stock=True,
    )
    coil = versions[1].lines[0].part
    assert coil is not None
    assert (coil.id, coil.is_active) == (world.coil_id, False)


async def test_list_versions_of_a_booking_without_estimates_is_empty(
    db: Database, world: World
) -> None:
    for shop_id in (world.shop_id, world.other_shop_id):
        versions = await read(
            db,
            service.list_versions,
            shop_id=shop_id,
            booking_id=world.booking_id,
            include_stock=True,
        )
        assert versions == []


async def test_list_versions_is_scoped_to_the_shop(db: Database, world: World) -> None:
    await decided_history(db, world)
    versions = await read(
        db,
        service.list_versions,
        shop_id=world.other_shop_id,
        booking_id=world.booking_id,
        include_stock=True,
    )
    assert versions == []


async def count_queries(db: Database, booking_id: uuid.UUID, world: World) -> int:
    statements: list[str] = []

    def count(conn: Connection, cursor: object, statement: str, *_: object) -> None:
        statements.append(statement)

    event.listen(db.engine.sync_engine, "before_cursor_execute", count)
    try:
        await read(
            db,
            service.list_versions,
            shop_id=world.shop_id,
            booking_id=booking_id,
            include_stock=True,
        )
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", count)
    return len(statements)


async def test_list_versions_runs_a_fixed_number_of_queries(db: Database, world: World) -> None:
    """§7.8: versions, lines, part refs, users - whatever the number of versions (no N+1)."""
    await insert_version(
        db,
        world,
        version=1,
        status=SENT,
        booking_id=world.second_booking_id,
        lines=worked_example_v1(world),
    )
    one_version = await count_queries(db, world.second_booking_id, world)
    for number, status in enumerate((REJECTED, REJECTED, REJECTED, APPROVED), start=1):
        await insert_version(
            db, world, version=number, status=status, lines=worked_example_v1(world)
        )
    four_versions = await count_queries(db, world.booking_id, world)
    assert one_version == four_versions == 4


# --- T12 get_approved_part_requirements -----------------------------------------------------------


async def test_t12_requirements_sum_the_approved_part_lines_per_part(
    db: Database, world: World
) -> None:
    """T12: the **approved** version's `PART` lines, summed per part (a part on several lines),
    ordered by `part_id`; labour lines and other versions are ignored."""
    await insert_version(
        db,
        world,
        version=1,
        status=REJECTED,
        lines=[part_spec(world.retired_id, "Retired part", "100", quantity="7")],
    )
    await insert_version(
        db,
        world,
        version=2,
        status=APPROVED,
        lines=[
            part_spec(world.coil_id, "Ignition coil", "6500"),
            part_spec(world.oil_id, "Engine oil 4 L", "5200"),
            labour_spec("Labour", "3500", quantity="2"),
            part_spec(world.filter_id, "Oil filter", "900"),
            part_spec(world.oil_id, "Engine oil 4 L", "5000", quantity="2"),
        ],
    )
    requirements = await read(
        db,
        service.get_approved_part_requirements,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
    )
    expected = sorted(
        [PartQty(world.coil_id, 1), PartQty(world.oil_id, 3), PartQty(world.filter_id, 1)],
        key=lambda requirement: requirement.part_id,
    )
    assert requirements == expected
    assert all(isinstance(requirement.qty, int) for requirement in requirements)


async def test_t12_a_labour_only_estimate_requires_no_parts(db: Database, world: World) -> None:
    """D31: zero requirements -> inventory creates zero `booking_parts` rows."""
    await insert_version(
        db, world, version=1, status=APPROVED, lines=[labour_spec("Four-wheel alignment", "2000")]
    )
    requirements = await read(
        db,
        service.get_approved_part_requirements,
        shop_id=world.shop_id,
        booking_id=world.booking_id,
    )
    assert requirements == []


@pytest.mark.parametrize("latest", [None, SENT, REJECTED, SUPERSEDED])
async def test_t12_without_an_approved_version_is_an_invariant_breach(
    db: Database, world: World, latest: EstimateStatus | None
) -> None:
    """T12 only runs from `ESTIMATE_APPROVED`; anything else is a 500 (`modules/estimates.md`
    §10)."""
    if latest is not None:
        await insert_version(db, world, version=1, status=latest, lines=worked_example_v1(world))
    with pytest.raises(InternalError) as caught:
        await read(
            db,
            service.get_approved_part_requirements,
            shop_id=world.shop_id,
            booking_id=world.booking_id,
        )
    assert caught.value.status_code == 500


async def test_t12_requirements_are_scoped_to_the_shop(db: Database, world: World) -> None:
    await insert_version(db, world, version=1, status=APPROVED, lines=worked_example_v1(world))
    with pytest.raises(InternalError):
        await read(
            db,
            service.get_approved_part_requirements,
            shop_id=world.other_shop_id,
            booking_id=world.booking_id,
        )


async def test_customer_projection_of_list_versions_never_exposes_stock(
    db: Database, world: World
) -> None:
    """Spec 04 §C: the customer projection of the same versions has no SKU and no stock."""
    await decided_history(db, world)
    history = await read(
        db, service.list_customer_versions, shop_id=world.shop_id, booking_id=world.booking_id
    )
    assert [version.version for version in history] == [2]
    line = history[0].lines[0]
    assert line.line_type == EstimateLineType.PART
    assert not hasattr(line, "part")
    assert "sku" not in str(history[0].model_dump(mode="json"))

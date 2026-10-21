"""Estimate reads for booking lists and the customer (D39; `modules/estimates.md` §7.7, §7.8):
summaries for staff and customers (incl. the customer's cross-shop list), the customer view and
history - SEC-12, EST-13, EST-22, EST-27 (service halves). Customers never see `DRAFT`,
`SUBMITTED` or `SUPERSEDED` versions."""

import uuid
from collections.abc import Awaitable
from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection

from app.core.database import Database
from app.modules.estimates import service
from app.modules.estimates.schemas import EstimateSummary
from app.shared.enums import EstimateLineType, EstimateStatus, MembershipRole
from tests.modules.estimates.support import (
    World,
    at,
    insert_version,
    labour_spec,
    read,
    worked_example_v1,
    write,
)
from tests.rows import add_rows, make_booking, make_membership, make_shop, make_user, make_vehicle

pytestmark = pytest.mark.db

DRAFT = EstimateStatus.DRAFT
SUBMITTED = EstimateStatus.SUBMITTED
SENT = EstimateStatus.SENT
APPROVED = EstimateStatus.APPROVED
REJECTED = EstimateStatus.REJECTED
SUPERSEDED = EstimateStatus.SUPERSEDED


async def history(db: Database, world: World, *stages: EstimateStatus) -> list[uuid.UUID]:
    """Insert versions 1..n of the booking with the given statuses (worked-example lines)."""
    return [
        await insert_version(
            db, world, version=number, status=status, lines=worked_example_v1(world)
        )
        for number, status in enumerate(stages, start=1)
    ]


async def customer_view(db: Database, world: World) -> tuple[uuid.UUID | None, bool]:
    view = await read(
        db, service.get_customer_view, shop_id=world.shop_id, booking_id=world.booking_id
    )
    return (view.estimate.id if view.estimate else None), view.revision_in_progress


@pytest.mark.parametrize(
    "stages",
    [
        (),
        (DRAFT,),
        (SUBMITTED,),
        (SUPERSEDED, DRAFT),
        (SUPERSEDED, SUBMITTED),  # returned to the technician and resubmitted, never sent
    ],
)
async def test_sec_12_customers_never_see_unsent_versions(
    db: Database, world: World, stages: tuple[EstimateStatus, ...]
) -> None:
    """SEC-12: while nothing was sent the customer gets no estimate and no "revision in
    progress" (the status label "Preparing your estimate" covers it), and an empty history."""
    await history(db, world, *stages)
    assert await customer_view(db, world) == (None, False)
    versions = await read(
        db, service.list_customer_versions, shop_id=world.shop_id, booking_id=world.booking_id
    )
    assert versions == []
    summaries = await read(
        db,
        service.get_estimate_summaries,
        shop_id=world.shop_id,
        booking_ids=[world.booking_id],
        audience="customer",
    )
    assert summaries == {}


async def test_customer_view_shows_the_sent_version_with_its_lines(
    db: Database, world: World
) -> None:
    """C5: itemised parts and labour, totals, `sent_at`; no SKU or stock in the projection."""
    _, v2 = await history(db, world, SUPERSEDED, SENT)
    view = await read(
        db, service.get_customer_view, shop_id=world.shop_id, booking_id=world.booking_id
    )
    assert view.revision_in_progress is False
    estimate = view.estimate
    assert estimate is not None
    assert (estimate.id, estimate.version, estimate.status) == (v2, 2, SENT)
    assert (estimate.sent_at, estimate.decided_at, estimate.customer_note) == (at(2), None, None)
    assert estimate.grand_total == Decimal("16600.00")
    assert [(line.position, line.line_type, line.description) for line in estimate.lines] == [
        (1, EstimateLineType.PART, "Ignition coil"),
        (2, EstimateLineType.PART, "Oil filter"),
        (3, EstimateLineType.PART, "Engine oil 4 L"),
        (4, EstimateLineType.LABOUR, "Diagnosis and repair labour"),
    ]
    body = estimate.model_dump(mode="json")
    assert body["grand_total"] == "16600.00"
    assert body["lines"][0]["quantity"] == "1.00"
    assert set(body["lines"][0]) == {
        "id",
        "position",
        "line_type",
        "description",
        "quantity",
        "unit_price",
        "line_total",
    }


@pytest.mark.parametrize(
    ("stages", "shown", "in_progress"),
    [
        ((SENT,), 1, False),  # awaiting the customer
        ((APPROVED,), 1, False),
        ((REJECTED,), 1, False),  # rejected, the shop has not acted yet
        ((REJECTED, DRAFT), 1, True),  # revise: the SA prepares v2
        ((REJECTED, SUBMITTED), 1, True),  # returned to the technician, resubmitted
        ((REJECTED, SUPERSEDED, DRAFT), 1, True),  # v2 submitted, SA edits v3
        ((REJECTED, SENT), 2, False),  # the revision was sent
        ((REJECTED, SUPERSEDED), 1, False),  # cancelled after the rejection
        ((REJECTED, REJECTED, APPROVED), 3, False),
    ],
)
async def test_est_22_revision_in_progress_truth_table(
    db: Database,
    world: World,
    stages: tuple[EstimateStatus, ...],
    shown: int,
    in_progress: bool,
) -> None:
    """EST-22: `estimate_revision_in_progress` is true only while the customer sees a version and
    a newer `DRAFT` / `SUBMITTED` one is being prepared."""
    ids = await history(db, world, *stages)
    assert await customer_view(db, world) == (ids[shown - 1], in_progress)


async def test_est_22_revision_in_progress_through_the_service_calls(
    db: Database, world: World
) -> None:
    """EST-22 driven by the real transitions: reject -> revise -> send -> cancel."""
    [v1] = await history(db, world, SENT)
    common = {"shop_id": world.shop_id, "booking_id": world.booking_id}
    assert await customer_view(db, world) == (v1, False)
    await write(
        db,
        service.reject,
        estimate_id=v1,
        decided_by_user_id=world.customer_id,
        reason="Too expensive",
        now=at(10),
        **common,
    )
    assert await customer_view(db, world) == (v1, False)
    v2 = await write(
        db, service.copy_rejected_to_draft, created_by_user_id=world.sa_id, now=at(11), **common
    )
    assert await customer_view(db, world) == (v1, True)
    await write(db, service.send, sent_by_user_id=world.sa_id, now=at(12), **common)
    assert await customer_view(db, world) == (v2.estimate_id, False)
    await write(db, service.supersede_open_versions, now=at(13), **common)
    assert await customer_view(db, world) == (v1, False)


async def test_est_27_a_cancelled_sent_version_disappears_for_the_customer(
    db: Database, world: World
) -> None:
    """EST-27: a `SENT` version superseded by a cancellation is absent from the customer view,
    the customer history (P1) and the customer summaries."""
    [v1] = await history(db, world, SENT)
    common = {"shop_id": world.shop_id, "booking_id": world.booking_id}
    assert await customer_view(db, world) == (v1, False)
    await write(db, service.supersede_open_versions, now=at(20), **common)
    assert await customer_view(db, world) == (None, False)
    assert await read(db, service.list_customer_versions, **common) == []
    customer = await read(
        db,
        service.get_estimate_summaries,
        shop_id=world.shop_id,
        booking_ids=[world.booking_id],
        audience="customer",
    )
    assert customer == {}
    staff = await read(
        db,
        service.get_estimate_summaries,
        shop_id=world.shop_id,
        booking_ids=[world.booking_id],
        audience="staff",
    )
    assert staff[world.booking_id].status == SUPERSEDED


async def test_customer_history_lists_only_visible_versions_ascending(
    db: Database, world: World
) -> None:
    """P1 `GET /api/v1/me/bookings/{booking_id}/estimates`: `SENT`, `APPROVED`, `REJECTED` only,
    ascending by `version`, each with its own lines and decision."""
    await insert_version(db, world, version=1, status=SUPERSEDED, lines=worked_example_v1(world))
    v2 = await insert_version(
        db,
        world,
        version=2,
        status=REJECTED,
        lines=worked_example_v1(world),
        customer_note="Labour seems high",
    )
    await insert_version(db, world, version=3, status=SUPERSEDED, lines=worked_example_v1(world))
    v4 = await insert_version(
        db, world, version=4, status=APPROVED, lines=[labour_spec("Diagnosis", "2500")]
    )
    versions = await read(
        db, service.list_customer_versions, shop_id=world.shop_id, booking_id=world.booking_id
    )
    assert [(version.id, version.version, version.status) for version in versions] == [
        (v2, 2, REJECTED),
        (v4, 4, APPROVED),
    ]
    assert versions[0].customer_note == "Labour seems high"
    assert len(versions[0].lines) == 4
    assert [line.description for line in versions[1].lines] == ["Diagnosis"]
    assert versions[1].grand_total == Decimal("2500.00")
    assert versions[1].decided_at is not None


async def test_estimate_summaries_for_staff_and_customers(db: Database, world: World) -> None:
    """`estimate_summary`: staff -> the latest version; customers -> the latest visible one;
    bookings without one are absent (`null`); line counts per version."""
    await insert_version(db, world, version=1, status=REJECTED, lines=worked_example_v1(world))
    v2 = await insert_version(
        db, world, version=2, status=DRAFT, lines=[labour_spec("Diagnosis", "2500")]
    )
    other_sent = await insert_version(
        db,
        world,
        version=1,
        status=SENT,
        booking_id=world.second_booking_id,
        lines=[labour_spec("Wheel alignment", "2000"), labour_spec("Balancing", "800")],
    )
    no_estimate = uuid.uuid4()
    booking_ids = [world.booking_id, world.second_booking_id, no_estimate]

    staff = await read(
        db,
        service.get_estimate_summaries,
        shop_id=world.shop_id,
        booking_ids=booking_ids,
        audience="staff",
    )
    assert staff == {
        world.booking_id: EstimateSummary(
            estimate_id=v2, version=2, status=DRAFT, grand_total=Decimal("2500"), line_count=1
        ),
        world.second_booking_id: EstimateSummary(
            estimate_id=other_sent,
            version=1,
            status=SENT,
            grand_total=Decimal("2800"),
            line_count=2,
        ),
    }
    customer = await read(
        db,
        service.get_estimate_summaries,
        shop_id=world.shop_id,
        booking_ids=booking_ids,
        audience="customer",
    )
    assert customer[world.booking_id].version == 1
    assert customer[world.booking_id].status == REJECTED
    assert customer[world.booking_id].grand_total == Decimal("16600.00")
    assert customer[world.booking_id].line_count == 4
    assert customer[world.second_booking_id].estimate_id == other_sent
    assert no_estimate not in customer
    assert staff[world.booking_id].model_dump(mode="json")["grand_total"] == "2500.00"


async def test_estimate_summaries_of_no_bookings_is_empty(db: Database, world: World) -> None:
    for audience in ("staff", "customer"):
        summaries = await read(
            db,
            service.get_estimate_summaries,
            shop_id=world.shop_id,
            booking_ids=[],
            audience=audience,
        )
        assert summaries == {}


async def test_estimate_summaries_ignore_another_shops_bookings(db: Database, world: World) -> None:
    """D20: Shop A's call never returns Shop B's booking, even when its id is passed."""
    await insert_version(
        db,
        world,
        version=1,
        status=SENT,
        booking_id=world.foreign_booking_id,
        shop_id=world.other_shop_id,
        lines=[labour_spec("Theirs", "1000")],
    )
    summaries = await read(
        db,
        service.get_estimate_summaries,
        shop_id=world.shop_id,
        booking_ids=[world.foreign_booking_id],
        audience="staff",
    )
    assert summaries == {}


async def test_summaries_and_customer_reads_use_a_fixed_number_of_queries(
    db: Database, world: World
) -> None:
    """§7.8: a fixed number of queries whatever the number of versions or bookings (API-11)."""
    for number, status in enumerate((REJECTED, REJECTED, REJECTED, APPROVED), start=1):
        await insert_version(
            db, world, version=number, status=status, lines=worked_example_v1(world)
        )
    await insert_version(
        db,
        world,
        version=1,
        status=SENT,
        booking_id=world.second_booking_id,
        lines=worked_example_v1(world),
    )
    statements: list[str] = []

    def count(conn: Connection, cursor: object, statement: str, *_: object) -> None:
        statements.append(statement)

    event.listen(db.engine.sync_engine, "before_cursor_execute", count)
    try:
        await read(
            db,
            service.get_estimate_summaries,
            shop_id=world.shop_id,
            booking_ids=[world.booking_id, world.second_booking_id],
            audience="staff",
        )
        summaries_queries = len(statements)
        statements.clear()
        await read(
            db, service.list_customer_versions, shop_id=world.shop_id, booking_id=world.booking_id
        )
        history_queries = len(statements)
        statements.clear()
        await read(
            db, service.get_customer_view, shop_id=world.shop_id, booking_id=world.booking_id
        )
        view_queries = len(statements)
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", count)
    assert (summaries_queries, history_queries, view_queries) == (1, 2, 2)


@pytest.mark.parametrize("audience", ["CUSTOMER", "Staff", "customers", ""])
async def test_estimate_summaries_fail_closed_on_an_unknown_audience(
    db: Database, world: World, audience: str
) -> None:
    """An unknown audience raises instead of quietly returning the staff view, which would show
    a customer drafts (SEC-12)."""
    await insert_version(db, world, version=1, status=DRAFT, lines=worked_example_v1(world))
    with pytest.raises(ValueError, match="audience"):
        await read(
            db,
            service.get_estimate_summaries,
            shop_id=world.shop_id,
            booking_ids=[world.booking_id],
            audience=audience,
        )


# --- The customer's booking list spans shops (API-11) --------------------------------------------


async def booking_at_another_shop(db: Database, name: str) -> tuple[uuid.UUID, uuid.UUID]:
    """A further tenant with one booking: `(shop_id, booking_id)`."""
    owner, customer = make_user(), make_user()
    shop = make_shop(name=name)
    vehicle = make_vehicle(customer)
    booking = make_booking(shop, customer, vehicle)
    await add_rows(
        db.sessionmaker,
        owner,
        customer,
        shop,
        make_membership(shop, owner, MembershipRole.OWNER),
        vehicle,
        booking,
    )
    return shop.id, booking.id


async def statements_run_by(db: Database, call: Awaitable[object]) -> int:
    statements: list[str] = []

    def count(conn: Connection, cursor: object, statement: str, *_: object) -> None:
        statements.append(statement)

    event.listen(db.engine.sync_engine, "before_cursor_execute", count)
    try:
        await call
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", count)
    return len(statements)


async def test_customer_summaries_span_shops(db: Database, world: World) -> None:
    """`get_customer_estimate_summaries`: per `(shop_id, booking_id)` key, the latest `SENT`,
    `APPROVED` or `REJECTED` version with its line count; bookings with no visible version are
    absent (`null`)."""
    await insert_version(db, world, version=1, status=REJECTED, lines=worked_example_v1(world))
    await insert_version(db, world, version=2, status=DRAFT, lines=worked_example_v1(world))
    sent_a = await insert_version(
        db,
        world,
        version=1,
        status=SENT,
        booking_id=world.second_booking_id,
        lines=[labour_spec("Wheel alignment", "2000")],
    )
    approved_b = await insert_version(
        db,
        world,
        version=1,
        status=APPROVED,
        shop_id=world.other_shop_id,
        booking_id=world.foreign_booking_id,
        lines=[labour_spec("Diagnosis", "1000"), labour_spec("Balancing", "500")],
    )
    shop_c, booking_c = await booking_at_another_shop(db, "Margalla Motor Works")
    await insert_version(
        db,
        world,
        version=1,
        status=DRAFT,
        shop_id=shop_c,
        booking_id=booking_c,
        lines=[labour_spec("Draft only", "100")],
    )
    shop_d, booking_d = await booking_at_another_shop(db, "Pindi Auto Garage")
    keys = [
        (world.shop_id, world.booking_id),
        (world.shop_id, world.second_booking_id),
        (world.other_shop_id, world.foreign_booking_id),
        (shop_c, booking_c),
        (shop_d, booking_d),
    ]
    summaries = await read(db, service.get_customer_estimate_summaries, booking_keys=keys)
    assert set(summaries) == {world.booking_id, world.second_booking_id, world.foreign_booking_id}
    rejected = summaries[world.booking_id]
    assert (rejected.version, rejected.status, rejected.line_count) == (1, REJECTED, 4)
    assert rejected.grand_total == Decimal("16600.00")
    assert summaries[world.second_booking_id].estimate_id == sent_a
    assert summaries[world.foreign_booking_id] == EstimateSummary(
        estimate_id=approved_b,
        version=1,
        status=APPROVED,
        grand_total=Decimal("1500"),
        line_count=2,
    )
    staff_view = await read(
        db,
        service.get_estimate_summaries,
        shop_id=world.shop_id,
        booking_ids=[world.booking_id],
        audience="customer",
    )
    assert staff_view[world.booking_id] == rejected  # the same rule as the one-shop read


async def test_customer_summaries_match_each_booking_only_with_its_own_shop(
    db: Database, world: World
) -> None:
    """D20: a key pairing Shop A with Shop B's booking finds nothing; the right pair does."""
    await insert_version(
        db,
        world,
        version=1,
        status=SENT,
        shop_id=world.other_shop_id,
        booking_id=world.foreign_booking_id,
        lines=[labour_spec("Theirs", "1000")],
    )
    mismatched = await read(
        db,
        service.get_customer_estimate_summaries,
        booking_keys=[(world.shop_id, world.foreign_booking_id)],
    )
    assert mismatched == {}
    matched = await read(
        db,
        service.get_customer_estimate_summaries,
        booking_keys=[(world.other_shop_id, world.foreign_booking_id)] * 2,  # duplicates are fine
    )
    assert set(matched) == {world.foreign_booking_id}


async def test_customer_summaries_run_one_query_whatever_the_number_of_shops(
    db: Database, world: World
) -> None:
    """API-11: one query for one shop and for six shops; no keys -> no query at all."""
    one_shop = [(world.shop_id, world.booking_id), (world.shop_id, world.second_booking_id)]
    others = ("Raza Auto Works", "Margalla Motor Works", "Pindi Auto Garage", "Lyallpur Motors")
    many_shops = [
        *one_shop,
        (world.other_shop_id, world.foreign_booking_id),
        *[await booking_at_another_shop(db, name) for name in others],
    ]
    for shop_id, booking_id in many_shops:
        await insert_version(
            db,
            world,
            version=1,
            status=SENT,
            shop_id=shop_id,
            booking_id=booking_id,
            lines=[labour_spec("Labour", "1000")],
        )

    async def summaries(keys: list[tuple[uuid.UUID, uuid.UUID]]) -> None:
        result = await read(db, service.get_customer_estimate_summaries, booking_keys=keys)
        assert set(result) == {booking_id for _, booking_id in keys}

    assert await statements_run_by(db, summaries(one_shop)) == 1
    assert await statements_run_by(db, summaries(many_shops)) == 1
    assert len({shop_id for shop_id, _ in many_shops}) == 6
    assert await statements_run_by(db, summaries([])) == 0

"""What the database itself guarantees for estimates, with the service layer bypassed (spec 02
§3.11-§3.12, §7.5; spec 12 §3.3): EST-16, EST-20, EST-25 (integration halves) and SEC-45."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.database import Database
from app.core.errors import ErrorCode
from app.modules.estimates.domain.totals import line_total
from app.modules.estimates.models import Estimate, EstimateLine
from app.shared.enums import EstimateLineType, EstimateStatus
from app.shared.repository import (
    CHECK_VIOLATION,
    FOREIGN_KEY_VIOLATION,
    UNIQUE_VIOLATION,
    constraint_name,
    error_code_for,
    sqlstate,
)
from tests.modules.estimates.support import (
    World,
    at,
    insert_version,
    labour_spec,
    lines_of,
    worked_example_v1,
)
from tests.rows import add_rows

pytestmark = pytest.mark.db


async def expect_violation(
    db: Database, *rows: object, constraint: str, state: str
) -> IntegrityError:
    with pytest.raises(IntegrityError) as caught:
        await add_rows(db.sessionmaker, *rows)
    assert constraint_name(caught.value) == constraint
    assert sqlstate(caught.value) == state
    return caught.value


def estimate(world: World, **overrides: object) -> Estimate:
    values: dict[str, object] = {
        "shop_id": world.shop_id,
        "booking_id": world.booking_id,
        "version": 1,
        "status": EstimateStatus.DRAFT,
        "created_by_user_id": world.tech_id,
    }
    values.update(overrides)
    return Estimate(**values)


def line(world: World, estimate_id: uuid.UUID, **overrides: object) -> EstimateLine:
    values: dict[str, object] = {
        "shop_id": world.shop_id,
        "estimate_id": estimate_id,
        "position": 1,
        "line_type": EstimateLineType.LABOUR,
        "description": "Labour",
        "quantity": Decimal("1.00"),
        "unit_price": Decimal("1000.00"),
        "line_total": Decimal("1000.00"),
    }
    values.update(overrides)
    return EstimateLine(**values)


# Every `.5` tie of quantity x price for quantities 0.01-9.99 against these prices, plus extremes.
TIE_PRICES = ("1", "3", "5", "7", "9", "11", "99", "999", "4997")


def tie_sample() -> list[tuple[Decimal, Decimal]]:
    quantities = [Decimal(hundredths).scaleb(-2) for hundredths in range(1, 1000)]
    prices = [Decimal(price) for price in TIE_PRICES]
    pairs = [(q, p) for q in quantities for p in prices if (q * p) % 1 == Decimal("0.5")]
    return [*pairs, (Decimal("1.50"), Decimal("999")), (Decimal("999.99"), Decimal("9999999"))]


async def test_est_25_line_total_equals_postgresql_round_on_every_tie(db: Database) -> None:
    """EST-25 (integration half): the domain's half-up rule equals PostgreSQL `round(numeric)`
    (ties away from zero) on numeric(10,2) x numeric(12,2), so `ck_estimate_lines_line_total`
    always holds for what the service stores."""
    pairs = tie_sample()
    assert len(pairs) > 100
    statement = text(
        "SELECT round(q * p) AS total FROM unnest("
        "CAST(:quantities AS numeric(10,2)[]), CAST(:prices AS numeric(12,2)[])"
        ") WITH ORDINALITY AS t(q, p, n) ORDER BY n"
    )
    async with db.sessionmaker() as session:
        result = await session.execute(
            statement,
            {"quantities": [q for q, _ in pairs], "prices": [p for _, p in pairs]},
        )
        database_totals = list(result.scalars())
    assert database_totals == [line_total(q, p) for q, p in pairs]


async def test_est_25_the_line_total_check_accepts_half_up_and_refuses_half_even(
    db: Database, world: World
) -> None:
    """EST-20 / EST-25: 1.50 x 999 is stored as 1,499.00; banker's 1,498.00 is refused."""
    version = await insert_version(
        db,
        world,
        version=1,
        status=EstimateStatus.DRAFT,
        lines=[labour_spec("Labour", "999", quantity="1.50"), labour_spec("Half", "1", "0.50")],
    )
    assert [stored.line_total for stored in await lines_of(db, version)] == [
        Decimal("1499.00"),
        Decimal("1.00"),
    ]
    await expect_violation(
        db,
        line(
            world,
            version,
            position=3,
            quantity=Decimal("1.50"),
            unit_price=Decimal("999"),
            line_total=Decimal("1498"),
        ),
        constraint="ck_estimate_lines_line_total",
        state=CHECK_VIOLATION,
    )


async def test_est_20_the_database_refuses_paisa(db: Database, world: World) -> None:
    """EST-20 (integration half): `ck_estimate_lines_whole_rupees` and `ck_estimates_whole_rupees`
    reject paisa even when the services are bypassed."""
    version = await insert_version(db, world, version=1, status=EstimateStatus.DRAFT)
    await expect_violation(
        db,
        line(world, version, unit_price=Decimal("900.50"), line_total=Decimal("901.00")),
        constraint="ck_estimate_lines_whole_rupees",
        state=CHECK_VIOLATION,
    )
    await expect_violation(
        db,
        estimate(
            world,
            booking_id=world.second_booking_id,
            parts_total=Decimal("0.50"),
            grand_total=Decimal("0.50"),
        ),
        constraint="ck_estimates_whole_rupees",
        state=CHECK_VIOLATION,
    )


async def test_estimate_totals_must_add_up(db: Database, world: World) -> None:
    await expect_violation(
        db,
        estimate(
            world, parts_total=Decimal("10"), labour_total=Decimal("5"), grand_total=Decimal("16")
        ),
        constraint="ck_estimates_totals",
        state=CHECK_VIOLATION,
    )


async def test_part_and_labour_line_shapes_are_enforced(db: Database, world: World) -> None:
    version = await insert_version(db, world, version=1, status=EstimateStatus.DRAFT)
    await expect_violation(
        db,
        line(world, version, line_type=EstimateLineType.PART),  # no part_id
        constraint="ck_estimate_lines_part_ref",
        state=CHECK_VIOLATION,
    )
    await expect_violation(
        db,
        line(
            world,
            version,
            line_type=EstimateLineType.PART,
            part_id=world.filter_id,
            quantity=Decimal("1.50"),
            unit_price=Decimal("900"),
            line_total=Decimal("1350"),
        ),
        constraint="ck_estimate_lines_part_quantity",
        state=CHECK_VIOLATION,
    )
    await expect_violation(
        db,
        line(world, version, quantity=Decimal("1000"), line_total=Decimal("1000000")),
        constraint="ck_estimate_lines_labour_quantity",
        state=CHECK_VIOLATION,
    )
    await expect_violation(
        db,
        line(world, version, position=51),
        constraint="ck_estimate_lines_position",
        state=CHECK_VIOLATION,
    )


async def test_sec_45_a_line_cannot_reference_another_shops_part(
    db: Database, world: World
) -> None:
    """SEC-45: the composite FK `(shop_id, part_id)` -> `parts (shop_id, id)` refuses Shop B's
    part on Shop A's estimate (SQLSTATE 23503)."""
    version = await insert_version(db, world, version=1, status=EstimateStatus.DRAFT)
    await expect_violation(
        db,
        line(
            world,
            version,
            line_type=EstimateLineType.PART,
            part_id=world.foreign_part_id,
            unit_price=Decimal("1"),
            line_total=Decimal("1"),
        ),
        constraint="fk_estimate_lines_shop_id_part_id_parts",
        state=FOREIGN_KEY_VIOLATION,
    )


async def test_sec_45_an_estimate_cannot_belong_to_another_shops_booking(
    db: Database, world: World
) -> None:
    """SEC-45: an `estimates` row of Shop A for Shop B's booking violates the composite FK."""
    await expect_violation(
        db,
        estimate(world, booking_id=world.foreign_booking_id),
        constraint="fk_estimates_shop_id_booking_id_bookings",
        state=FOREIGN_KEY_VIOLATION,
    )


async def test_est_16_the_database_allows_one_open_version_per_booking(
    db: Database, world: World
) -> None:
    """EST-16: `uq_estimates_one_open_version_per_booking` is the backstop behind the booking
    lock; a violation maps to 409 `CONCURRENT_UPDATE` (spec 03 §2.4), never a bare 500."""
    await insert_version(
        db, world, version=1, status=EstimateStatus.SUBMITTED, lines=worked_example_v1(world)
    )
    for second_open in (EstimateStatus.DRAFT, EstimateStatus.SUBMITTED, EstimateStatus.SENT):
        error = await expect_violation(
            db,
            estimate(
                world,
                version=2,
                status=second_open,
                submitted_at=at(2),
                sent_at=at(2) if second_open == EstimateStatus.SENT else None,
                sent_by_user_id=world.sa_id if second_open == EstimateStatus.SENT else None,
            ),
            constraint="uq_estimates_one_open_version_per_booking",
            state=UNIQUE_VIOLATION,
        )
        assert error_code_for(error) is ErrorCode.CONCURRENT_UPDATE


async def test_versions_are_unique_per_booking_and_one_approved_at_most(
    db: Database, world: World
) -> None:
    await insert_version(
        db, world, version=1, status=EstimateStatus.APPROVED, lines=worked_example_v1(world)
    )
    error = await expect_violation(
        db,
        estimate(world, version=1, status=EstimateStatus.SUPERSEDED),
        constraint="uq_estimates_booking_id_version",
        state=UNIQUE_VIOLATION,
    )
    assert error_code_for(error) is ErrorCode.CONCURRENT_UPDATE
    error = await expect_violation(
        db,
        estimate(
            world,
            version=2,
            status=EstimateStatus.APPROVED,
            sent_at=at(2),
            sent_by_user_id=world.sa_id,
            decided_at=at(3),
            decided_by_user_id=world.customer_id,
        ),
        constraint="uq_estimates_one_approved_per_booking",
        state=UNIQUE_VIOLATION,
    )
    assert error_code_for(error) is ErrorCode.CONCURRENT_UPDATE


async def test_a_decision_needs_its_audit_fields(db: Database, world: World) -> None:
    """`ck_estimates_decision_fields` / `ck_estimates_sent_fields`: the timestamped acceptance
    cannot exist without who and when (brief §3)."""
    await expect_violation(
        db,
        estimate(world, status=EstimateStatus.APPROVED, sent_at=at(1), sent_by_user_id=world.sa_id),
        constraint="ck_estimates_decision_fields",
        state=CHECK_VIOLATION,
    )
    await expect_violation(
        db,
        estimate(world, status=EstimateStatus.SENT),
        constraint="ck_estimates_sent_fields",
        state=CHECK_VIOLATION,
    )

"""Database-level guarantees, proven with the service layer bypassed (spec 02; spec 12 §3.3).

INV-14 (stock CHECKs), SEC-15 (one OWNER per shop), SEC-45 (composite tenant FKs), the D29 enum
CHECKs, D41 whole rupees, the append-only ledgers (spec 02 §8) and the D79 `seq` identity.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database import Database
from app.modules.bookings.models import BookingEvent
from app.modules.estimates.models import Estimate
from app.modules.identity.models import User
from app.modules.inventory.models import BookingPart
from app.shared.clock import SimulatedClock
from app.shared.enums import ActorRole, BookingAction, BookingStatus, MembershipRole
from app.shared.repository import (
    CHECK_VIOLATION,
    FOREIGN_KEY_VIOLATION,
    UNIQUE_VIOLATION,
    constraint_name,
    sqlstate,
)
from tests.rows import (
    add_rows,
    make_booking,
    make_membership,
    make_part,
    make_shop,
    make_user,
    make_vehicle,
)

pytestmark = pytest.mark.db


async def expect_violation(
    db: Database, *rows: object, constraint: str, state: str
) -> IntegrityError:
    with pytest.raises(IntegrityError) as caught:
        await add_rows(db.sessionmaker, *rows)
    assert constraint_name(caught.value) == constraint
    assert sqlstate(caught.value) == state
    return caught.value


async def two_shops_with_a_booking(db: Database) -> dict[str, object]:
    owner_a, owner_b, customer = make_user(), make_user(), make_user()
    shop_a, shop_b = make_shop(), make_shop()
    vehicle = make_vehicle(customer)
    booking_a = make_booking(shop_a, customer, vehicle)
    part_b = make_part(shop_b)
    await add_rows(
        db.sessionmaker,
        owner_a,
        owner_b,
        customer,
        shop_a,
        shop_b,
        make_membership(shop_a, owner_a, MembershipRole.OWNER),
        make_membership(shop_b, owner_b, MembershipRole.OWNER),
        vehicle,
        booking_a,
        part_b,
    )
    return {
        "shop_a": shop_a,
        "shop_b": shop_b,
        "owner_b": owner_b,
        "customer": customer,
        "vehicle": vehicle,
        "booking_a": booking_a,
        "part_b": part_b,
    }


async def test_reserved_can_never_exceed_on_hand(db: Database) -> None:
    shop = make_shop()
    await add_rows(db.sessionmaker, shop)
    await expect_violation(
        db,
        make_part(shop, on_hand=1, reserved=2),
        constraint="ck_parts_reserved_lte_on_hand",
        state=CHECK_VIOLATION,
    )
    await expect_violation(
        db,
        make_part(shop, on_hand=-1),
        constraint="ck_parts_on_hand_non_negative",
        state=CHECK_VIOLATION,
    )


async def test_money_must_be_whole_rupees(db: Database) -> None:
    shop = make_shop()
    await add_rows(db.sessionmaker, shop)
    await expect_violation(
        db,
        make_part(shop, unit_cost=Decimal("900.50")),
        constraint="ck_parts_whole_rupees",
        state=CHECK_VIOLATION,
    )


async def test_a_shop_has_at_most_one_owner(db: Database) -> None:
    first, second = make_user(), make_user()
    shop = make_shop()
    await add_rows(
        db.sessionmaker, first, second, shop, make_membership(shop, first, MembershipRole.OWNER)
    )
    await expect_violation(
        db,
        make_membership(shop, second, MembershipRole.OWNER, created_by=first),
        constraint="uq_shop_memberships_one_owner_per_shop",
        state=UNIQUE_VIOLATION,
    )
    await expect_violation(
        db,
        make_membership(shop, first, MembershipRole.TECHNICIAN),
        constraint="uq_shop_memberships_shop_id_user_id",
        state=UNIQUE_VIOLATION,
    )


async def test_owner_membership_cannot_be_inactive(db: Database) -> None:
    owner = make_user()
    shop = make_shop()
    await add_rows(db.sessionmaker, owner, shop)
    await expect_violation(
        db,
        make_membership(shop, owner, MembershipRole.OWNER, is_active=False),
        constraint="ck_shop_memberships_owner_active",
        state=CHECK_VIOLATION,
    )


async def test_composite_tenant_fk_rejects_a_cross_shop_estimate(db: Database) -> None:
    world = await two_shops_with_a_booking(db)
    foreign_estimate = Estimate(
        shop_id=world["shop_b"].id,  # type: ignore[attr-defined]
        booking_id=world["booking_a"].id,  # type: ignore[attr-defined]
        version=1,
        created_by_user_id=world["owner_b"].id,  # type: ignore[attr-defined]
    )
    await expect_violation(
        db,
        foreign_estimate,
        constraint="fk_estimates_shop_id_booking_id_bookings",
        state=FOREIGN_KEY_VIOLATION,
    )


async def test_composite_tenant_fk_rejects_another_shops_part(db: Database) -> None:
    world = await two_shops_with_a_booking(db)
    booking_part = BookingPart(
        shop_id=world["shop_a"].id,  # type: ignore[attr-defined]
        booking_id=world["booking_a"].id,  # type: ignore[attr-defined]
        part_id=world["part_b"].id,  # type: ignore[attr-defined]
        required_qty=1,
    )
    await expect_violation(
        db,
        booking_part,
        constraint="fk_booking_parts_shop_id_part_id_parts",
        state=FOREIGN_KEY_VIOLATION,
    )


async def test_assignee_must_be_a_member_of_the_bookings_shop(db: Database) -> None:
    world = await two_shops_with_a_booking(db)
    booking = make_booking(
        world["shop_a"],  # type: ignore[arg-type]
        world["customer"],  # type: ignore[arg-type]
        world["vehicle"],  # type: ignore[arg-type]
        technician_user_id=world["owner_b"].id,  # type: ignore[attr-defined]
    )
    await expect_violation(
        db,
        booking,
        constraint="fk_bookings_shop_id_technician_user_id_shop_memberships",
        state=FOREIGN_KEY_VIOLATION,
    )


async def test_a_booking_uses_its_own_customers_vehicle(db: Database) -> None:
    world = await two_shops_with_a_booking(db)
    stranger = make_user()
    await add_rows(db.sessionmaker, stranger)
    booking = make_booking(world["shop_a"], stranger, world["vehicle"])  # type: ignore[arg-type]
    await expect_violation(
        db,
        booking,
        constraint="fk_bookings_customer_user_id_vehicle_id_vehicles",
        state=FOREIGN_KEY_VIOLATION,
    )


async def test_enum_columns_only_accept_their_values(db: Database) -> None:
    await two_shops_with_a_booking(db)
    async with db.sessionmaker() as session:
        with pytest.raises(IntegrityError) as caught:
            await session.execute(text("UPDATE shop_memberships SET role = 'SUPERUSER'"))
    assert constraint_name(caught.value) == "ck_shop_memberships_role"
    assert sqlstate(caught.value) == CHECK_VIOLATION


async def test_email_is_stored_lower_case_only(db: Database) -> None:
    await expect_violation(
        db,
        make_user(email="Upper.Case@bayflow.test"),
        constraint="ck_users_email_lowercase",
        state=CHECK_VIOLATION,
    )


async def test_booking_events_are_append_only_and_ordered_by_seq(
    db: Database, clock: SimulatedClock
) -> None:
    world = await two_shops_with_a_booking(db)
    booking = world["booking_a"]
    customer = world["customer"]

    def event(
        action: BookingAction, before: BookingStatus | None, after: BookingStatus
    ) -> BookingEvent:
        return BookingEvent(
            shop_id=booking.shop_id,  # type: ignore[attr-defined]
            booking_id=booking.id,  # type: ignore[attr-defined]
            action=action,
            from_status=before,
            to_status=after,
            actor_user_id=customer.id,  # type: ignore[attr-defined]
            actor_role=ActorRole.CUSTOMER,
        )

    # Two rows of one action share one clock instant (D63); `seq` keeps their insert order (D79).
    first = event(BookingAction.CREATE, None, BookingStatus.PENDING)
    second = event(BookingAction.CANCEL, BookingStatus.PENDING, BookingStatus.CANCELLED)
    await add_rows(db.sessionmaker, first, second)
    assert first.created_at == second.created_at == clock.now()
    assert second.seq > first.seq

    async with db.sessionmaker() as session:
        ordered = (
            await session.execute(
                select(BookingEvent.id).order_by(BookingEvent.created_at, BookingEvent.seq)
            )
        ).scalars()
        assert list(ordered) == [first.id, second.id]

    for statement in (
        "UPDATE booking_events SET note = 'rewritten'",
        "DELETE FROM booking_events",
    ):
        async with db.sessionmaker() as session:
            with pytest.raises(DBAPIError) as caught:
                await session.execute(text(statement))
            assert sqlstate(caught.value) == "P0001"
            assert "booking_events is append-only" in str(caught.value.orig)


async def test_stock_movements_are_append_only(db: Database) -> None:
    world = await two_shops_with_a_booking(db)
    async with db.sessionmaker() as session:
        await session.execute(
            text(
                "INSERT INTO stock_movements (id, shop_id, part_id, movement_type, quantity,"
                " on_hand_delta, reserved_delta, actor_user_id, note)"
                " VALUES (gen_random_uuid(), :shop, :part, 'ADJUST', 5, 5, 0, :actor, 'opening')"
            ),
            {
                "shop": world["shop_b"].id,  # type: ignore[attr-defined]
                "part": world["part_b"].id,  # type: ignore[attr-defined]
                "actor": world["owner_b"].id,  # type: ignore[attr-defined]
            },
        )
        await session.commit()
    async with db.sessionmaker() as session:
        with pytest.raises(DBAPIError) as caught:
            await session.execute(text("DELETE FROM stock_movements"))
        assert sqlstate(caught.value) == "P0001"


async def test_seq_is_generated_by_the_database_only(db: Database) -> None:
    world = await two_shops_with_a_booking(db)
    async with db.sessionmaker() as session:
        with pytest.raises(DBAPIError) as caught:
            await session.execute(
                text(
                    "INSERT INTO booking_events (id, seq, shop_id, booking_id, action, to_status,"
                    " actor_user_id, actor_role)"
                    " VALUES (gen_random_uuid(), 42, :shop, :booking, 'CREATE', 'PENDING',"
                    " :actor, 'CUSTOMER')"
                ),
                {
                    "shop": world["shop_a"].id,  # type: ignore[attr-defined]
                    "booking": world["booking_a"].id,  # type: ignore[attr-defined]
                    "actor": world["customer"].id,  # type: ignore[attr-defined]
                },
            )
    assert sqlstate(caught.value) == "428C9"  # generated_always: identity columns are DB-only
    assert 'non-DEFAULT value into column "seq"' in str(caught.value.orig)


async def test_ids_exist_before_flush_and_timestamps_come_from_the_clock(
    db: Database, clock: SimulatedClock
) -> None:
    user = make_user()
    assert user.id is not None  # assigned by the Base constructor (spec 02 §2)
    await add_rows(db.sessionmaker, user)
    clock.advance(timedelta(hours=2))
    async with db.sessionmaker() as session:
        stored = await session.get(User, user.id)
        assert stored is not None
        assert stored.created_at == stored.updated_at == clock.now() - timedelta(hours=2)
        stored.full_name = "Renamed"
        await session.commit()
        assert stored.updated_at == clock.now()  # ORM onupdate reads the same clock (D63)

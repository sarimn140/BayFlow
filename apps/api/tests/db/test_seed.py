"""The seed against a real database (spec 11 "Verification", spec 12 SEED-xx).

Each test runs the real entry function `seed(db, now=...)`, as the pre-deploy step does.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import SecretStr
from sqlalchemy import text

from app.core.database import Database
from app.modules.bookings import service as bookings_service
from app.modules.bookings.schemas import ApproveEstimateRequest
from app.modules.identity import service as identity_service
from app.scripts import seed_data as data
from app.scripts.seed import seed
from app.shared.auth import CurrentUser
from app.shared.enums import BookingAction
from app.shared.event_bus import EventBus
from app.shared.uow import UnitOfWork
from tests.assertions import assert_invariants

FRIDAY_NOON_PKT = datetime(2026, 10, 9, 7, 0, tzinfo=UTC)  # spec 11's example run

STATUSES = {
    "BF-SEED01": "PENDING",
    "BF-SEED02": "AWAITING_CUSTOMER",
    "BF-SEED03": "PARTS_ORDERED",
    "BF-SEED04": "IN_REPAIR",
    "BF-SEED05": "QC_PENDING",
    "BF-SEED06": "READY_FOR_PICKUP",
    "BF-SEED07": "COMPLETED",
    "BF-SEED08": "CANCELLED",
    "BF-SEED09": "CANCELLED",
    "BF-SEED10": "PENDING",
    "BF-SEED11": "COMPLETED",
    "BF-SEED12": "PENDING",
    "BF-SEED13": "PENDING",
    "BF-SEED14": "PENDING",
    "BF-SEED15": "COMPLETED",
}

LAHORE_STOCK = {  # SKU -> (on hand, reserved), spec 11 "Lahore Auto Care — the demo shop"
    "FLT-OIL-01": (10, 0),
    "OIL-4L-01": (8, 0),
    "IGN-COIL-01": (0, 0),
    "SPK-PLG-IR": (8, 0),
    "FLT-AIR-01": (6, 0),
    "FLT-CAB-01": (2, 0),
    "BRK-PAD-F": (2, 1),
    "BRK-DSC-F": (0, 0),
    "BRK-FLD-D4": (7, 1),
    "CLT-1L": (12, 0),
    "WPR-PAIR": (0, 0),
    "BAT-45AH": (3, 0),
    "AC-R134A": (5, 0),
    "SUS-STB-LNK": (6, 0),
    "TIR-185-65-R15": (4, 0),
    "BLB-H4": (10, 0),
}

UNREAD = {  # spec 11 "What each demo account sees on first login" (accounts with unread rows)
    "ayesha.customer@bayflow.test": 1,
    "bilal.sa@bayflow.test": 2,
    "imran.tech@bayflow.test": 1,
    "usman.parts@bayflow.test": 1,
    "sara.qc@bayflow.test": 1,
    "hina.qc@bayflow.test": 1,
    "sa.raza-auto-works@bayflow.test": 1,
    "sa.clifton-car-clinic@bayflow.test": 1,
    "sa.margalla-motor-works@bayflow.test": 1,
    "sa.pindi-auto-garage@bayflow.test": 1,
}

COUNTS = """
    select
        (select count(*) from users) as users,
        (select count(*) from shop_memberships) as memberships,
        (select count(*) from shop_working_hours) as working_hours,
        (select count(*) from services) as services,
        (select count(*) from parts) as parts,
        (select count(*) from vehicles) as vehicles,
        (select count(*) from purchase_orders where po_number like 'PO-SEED%') as general_pos,
        (select count(*) from purchase_orders) as purchase_orders,
        (select count(*) from bookings) as bookings,
        (select count(*) from booking_events) as events,
        (select count(*) from stock_movements) as movements,
        (select count(*) from notifications) as notifications
"""
LAST_WRITES = """
    select
        (select max(updated_at) from users) as users,
        (select max(updated_at) from shop_memberships) as memberships,
        (select max(updated_at) from bookings) as bookings,
        (select max(updated_at) from parts) as parts,
        (select max(read_at) from notifications) as notifications
"""


async def _one(db: Database, sql: str) -> dict[str, Any]:
    async with db.sessionmaker() as session:
        return dict((await session.execute(text(sql))).mappings().one())


async def _pairs(db: Database, sql: str) -> dict[str, Any]:
    async with db.sessionmaker() as session:
        return {row[0]: row[1] for row in (await session.execute(text(sql))).all()}


async def test_seed_builds_the_spec_11_demo_data(db: Database) -> None:
    assert await seed(db, now=FRIDAY_NOON_PKT) == 0

    assert await _one(db, COUNTS) == {  # SEED-11
        "users": 36,
        "memberships": 32,
        "working_hours": 42,
        "services": 52,
        "parts": 96,
        "vehicles": 10,
        "general_pos": 2,
        "purchase_orders": 3,
        "bookings": 15,
        "events": 125,
        "movements": 110,
        "notifications": 97,
    }
    assert await _pairs(db, "select reference, status from bookings") == STATUSES
    system_events = await _one(
        db, "select count(*) as n from booking_events where actor_role = 'SYSTEM'"
    )
    assert system_events == {"n": 0}  # glossary §2.2: the seed acts as real people
    assert await _pairs(db, "select po_number, status from purchase_orders") == {
        "PO-SEED01": "RECEIVED",
        "PO-SEED02": "PARTIALLY_RECEIVED",
        **dict.fromkeys(
            await _pairs(
                db, "select po_number, 1 from purchase_orders where booking_id is not null"
            ),
            "ORDERED",
        ),
    }
    stock = await _pairs(  # SEED-04, SEED-12
        db,
        "select p.sku, array[p.on_hand, p.reserved] from parts p join shops s on s.id = p.shop_id"
        " where s.slug = 'lahore-auto-care'",
    )
    assert {sku: tuple(value) for sku, value in stock.items()} == LAHORE_STOCK
    unread = await _pairs(  # SEED-18
        db,
        "select u.email, count(*) from notifications n join users u on u.id = n.recipient_user_id"
        " where n.read_at is null group by u.email",
    )
    assert unread == UNREAD
    owners = await _pairs(
        db,
        "select s.slug, u.email from shops s join users u on u.id = ("
        " select m.user_id from shop_memberships m where m.shop_id = s.id and m.role = 'OWNER')",
    )
    assert owners["lahore-auto-care"] == owners["raza-auto-works"] == "fatima.owner@bayflow.test"
    assert await _one(db, "select count(*) as n from users where email = 'ahmed@mail.com'") == {
        "n": 0  # SEED-05
    }
    async with db.sessionmaker() as session:
        await assert_invariants(session)  # SEED-06 for every sample booking
    emails = {shop.owner.email for shop in data.SHOPS}
    emails |= {member.email for shop in data.SHOPS for member in shop.staff}
    emails |= {customer.email for customer in data.CUSTOMERS}
    for email in sorted(emails):  # SEED-07, SEED-13
        async with db.sessionmaker() as session:
            user = await identity_service.authenticate(
                UnitOfWork(session, EventBus()),
                email=email,
                password=SecretStr(data.DEMO_PASSWORD),
            )
        assert user.email == email


async def test_a_rerun_keeps_judge_data_and_repairs_the_demo_cast(db: Database) -> None:
    assert await seed(db, now=FRIDAY_NOON_PKT) == 0
    # A judge approves BF-SEED02 as Ayesha and breaks four demo accounts (SEED-14, SEED-19).
    references = await _pairs(db, "select reference, id from bookings")
    ayesha = await _pairs(
        db, "select email, id from users where email = 'ayesha.customer@bayflow.test'"
    )
    customer = CurrentUser(
        id=ayesha["ayesha.customer@bayflow.test"],
        email="ayesha.customer@bayflow.test",
        full_name="Ayesha Khan",
    )
    async with db.sessionmaker() as session:
        detail = await bookings_service.get_customer_booking(
            session, customer, booking_id=references["BF-SEED02"]
        )
        assert detail.estimate is not None
        await bookings_service.apply_customer_action(
            UnitOfWork(session, EventBus()),
            customer,
            booking_id=references["BF-SEED02"],
            action=BookingAction.APPROVE_ESTIMATE,
            payload=ApproveEstimateRequest(estimate_id=detail.estimate.id),
        )
    async with db.engine.begin() as connection:
        for sql in (
            "update shop_memberships set is_active = false where user_id ="
            " (select id from users where email = 'hamza.tech@bayflow.test')",
            "update shop_memberships set role = 'SERVICE_ADVISOR' where user_id ="
            " (select id from users where email = 'imran.tech@bayflow.test')",
            "update users set is_active = false where email = 'sara.qc@bayflow.test'",
            "update users set password_hash = 'not-a-hash'"
            " where email = 'usman.parts@bayflow.test'",
        ):
            await connection.execute(text(sql))
    before = await _one(db, COUNTS)

    assert await seed(db, now=FRIDAY_NOON_PKT + timedelta(days=1)) == 0  # SEED-02: a day later

    assert await _one(db, COUNTS) == before  # nothing new, nothing deleted
    statuses = await _pairs(db, "select reference, status from bookings")
    assert statuses["BF-SEED02"] == "ESTIMATE_APPROVED"  # the judge's action is kept
    cast = await _pairs(
        db,
        "select u.email, array[u.is_active::text, m.role::text, m.is_active::text]"
        " from users u join shop_memberships m on m.user_id = u.id where u.email in"
        " ('hamza.tech@bayflow.test', 'imran.tech@bayflow.test', 'sara.qc@bayflow.test')",
    )
    assert {email: tuple(value) for email, value in cast.items()} == {
        "hamza.tech@bayflow.test": ("true", "TECHNICIAN", "true"),
        "imran.tech@bayflow.test": ("true", "TECHNICIAN", "true"),
        "sara.qc@bayflow.test": ("true", "QC_INSPECTOR", "true"),
    }
    async with db.sessionmaker() as session:
        usman = await identity_service.find_user_by_email(session, "usman.parts@bayflow.test")
        assert usman is not None
        assert await identity_service.password_matches(
            session, user_id=usman.id, password=SecretStr(data.DEMO_PASSWORD)
        )

    last_writes = await _one(db, LAST_WRITES)
    assert await seed(db, now=FRIDAY_NOON_PKT + timedelta(days=2)) == 0
    assert await _one(db, LAST_WRITES) == last_writes  # a run with nothing to repair writes nothing

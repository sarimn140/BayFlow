"""`modules/reporting.md` "Check against the seed": Lahore Auto Care right after seeding.

The seed script (spec 11) is not built yet, so this test rebuilds the state spec 11 documents —
the team of 7, the 9 sample bookings with their assignees (BF-SEED01…09), the 16 parts with their
after-seed on hand / reserved quantities and the three purchase orders — as rows, and checks that
the overview and the owner summary produce exactly the figures `modules/reporting.md` states:
9 bookings by status, open jobs Imran 4 and Usman 3, 16 parts, 3 OUT, 6 LOW or OUT, stock value
286,400.00, 2 open purchase orders and the five low-stock parts in their documented order.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.core.database import Database
from app.modules.bookings.models import Booking
from app.modules.identity.models import User
from app.modules.inventory.models import Part, PurchaseOrder, PurchaseOrderItem
from app.modules.shops.models import Service, Shop
from app.shared.enums import BookingStatus, MembershipRole, PurchaseOrderStatus
from tests.modules.reporting.support import SUMMARY_URL, bearer, overview_url
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

S = BookingStatus
R = MembershipRole
P5 = datetime(2026, 10, 9, 5, 0, tzinfo=UTC)  # a past slot; "today" is not part of this check

# spec 11 "Inventory — Lahore Auto Care": SKU, name, unit cost, reorder level, on hand, reserved.
PARTS = [
    ("FLT-OIL-01", "Oil filter", 900, 3, 10, 0),
    ("OIL-4L-01", "Engine oil 4 L", 5200, 3, 8, 0),
    ("IGN-COIL-01", "Ignition coil", 6500, 2, 0, 0),
    ("SPK-PLG-IR", "Spark plug (iridium)", 1800, 6, 8, 0),
    ("FLT-AIR-01", "Air filter", 1600, 3, 6, 0),
    ("FLT-CAB-01", "Cabin AC filter", 1400, 3, 2, 0),
    ("BRK-PAD-F", "Front brake pads (set)", 6800, 2, 2, 1),
    ("BRK-DSC-F", "Front brake disc", 7500, 2, 0, 0),
    ("BRK-FLD-D4", "Brake fluid DOT 4 (1 L)", 1500, 4, 7, 1),
    ("CLT-1L", "Coolant (1 L)", 1200, 5, 12, 0),
    ("WPR-PAIR", "Wiper blades (pair)", 2200, 2, 0, 0),
    ("BAT-45AH", "Battery 12V 45Ah", 18500, 2, 3, 0),
    ("AC-R134A", "AC gas R134a (can)", 3000, 2, 5, 0),
    ("SUS-STB-LNK", "Front stabilizer link", 4500, 2, 6, 0),
    ("TIR-185-65-R15", "Tire 185/65 R15", 16000, 4, 4, 0),
    ("BLB-H4", "Headlight bulb H4", 900, 4, 10, 0),
]


def booking(  # noqa: PLR0913 - one keyword per assignee column
    shop: Shop,
    customer: User,
    status: BookingStatus,
    *,
    technician: User | None = None,
    parts: User | None = None,
    qc: User | None = None,
    cancelled_by: User | None = None,
) -> list[object]:
    values: dict[str, object] = {
        "status": status,
        "slot_start": P5,
        "technician_user_id": technician.id if technician else None,
        "parts_person_user_id": parts.id if parts else None,
        "qc_inspector_user_id": qc.id if qc else None,
    }
    if status == S.COMPLETED:
        values["completed_at"] = P5 + timedelta(hours=6)
    if status == S.CANCELLED:
        values["cancelled_at"] = P5 - timedelta(days=1)
        values["cancelled_by_user_id"] = (cancelled_by or customer).id
    vehicle = make_vehicle(customer)
    return [vehicle, make_booking(shop, customer, vehicle, **values)]


def purchase_order(
    shop: Shop,
    number: str,
    status: PurchaseOrderStatus,
    by: User,
    items: list[tuple[Part, int, int]],
) -> list[object]:
    order = PurchaseOrder(
        shop_id=shop.id,
        po_number=number,
        status=status,
        created_by_user_id=by.id,
        received_at=P5 if status == PurchaseOrderStatus.RECEIVED else None,
    )
    lines = [
        PurchaseOrderItem(
            shop_id=shop.id,
            purchase_order_id=order.id,
            part_id=part.id,
            ordered_qty=ordered,
            received_qty=received,
            unit_cost=part.unit_cost,
        )
        for part, ordered, received in items
    ]
    return [order, *lines]


@pytest.mark.usefixtures("clock")  # frozen on Wed 14 Oct 2026: no seeded slot is "today"
async def test_the_overview_matches_the_documented_seed_figures(
    api: httpx.AsyncClient, db: Database
) -> None:
    shop = make_shop(name="Lahore Auto Care", slug="lahore-auto-care")
    fatima, bilal = make_user(full_name="Fatima Raza"), make_user(full_name="Bilal")
    imran, hamza = make_user(full_name="Imran"), make_user(full_name="Hamza")
    sara, hina = make_user(full_name="Sara"), make_user(full_name="Hina")
    usman, ayesha = make_user(full_name="Usman"), make_user(full_name="Ayesha Khan")
    parts = {
        sku: make_part(
            shop,
            sku=sku,
            name=name,
            unit_cost=Decimal(cost),
            reorder_level=level,
            on_hand=on_hand,
            reserved=reserved,
        )
        for sku, name, cost, level, on_hand, reserved in PARTS
    }
    seed03 = booking(shop, ayesha, S.PARTS_ORDERED, technician=imran, parts=usman)
    linked_po = purchase_order(
        shop, "PO-AB12CD", PurchaseOrderStatus.ORDERED, usman, [(parts["BRK-DSC-F"], 2, 0)]
    )
    order, seed03_booking = linked_po[0], seed03[1]
    assert isinstance(order, PurchaseOrder)
    assert isinstance(seed03_booking, Booking)
    order.booking_id = seed03_booking.id  # BF-SEED03's own purchase order (D43)
    await add_rows(
        db.sessionmaker,
        fatima,
        bilal,
        imran,
        hamza,
        sara,
        hina,
        usman,
        ayesha,
        shop,
        make_membership(shop, fatima, R.OWNER),
        make_membership(shop, bilal, R.SERVICE_ADVISOR, created_by=fatima),
        make_membership(shop, imran, R.TECHNICIAN, created_by=fatima),
        make_membership(shop, hamza, R.TECHNICIAN, created_by=fatima),
        make_membership(shop, sara, R.QC_INSPECTOR, created_by=fatima),
        make_membership(shop, hina, R.QC_INSPECTOR, created_by=fatima),
        make_membership(shop, usman, R.PARTS_PERSON, created_by=fatima),
        Service(shop_id=shop.id, name="Oil change", estimated_duration_minutes=60),
        *parts.values(),
        *booking(shop, ayesha, S.PENDING),  # BF-SEED01
        *booking(shop, ayesha, S.AWAITING_CUSTOMER, technician=imran),  # BF-SEED02
        *seed03,  # BF-SEED03
        *booking(shop, ayesha, S.IN_REPAIR, technician=imran, parts=usman),  # BF-SEED04
        *booking(shop, ayesha, S.QC_PENDING, technician=imran, parts=usman),  # BF-SEED05
        *booking(shop, ayesha, S.READY_FOR_PICKUP, technician=hamza, parts=usman, qc=sara),
        *booking(shop, ayesha, S.COMPLETED, technician=imran, parts=usman, qc=hina),  # SEED07
        *booking(shop, ayesha, S.CANCELLED, technician=imran, parts=usman),  # BF-SEED08
        *booking(shop, ayesha, S.CANCELLED, cancelled_by=bilal),  # BF-SEED09, declined
        *purchase_order(
            shop,
            "PO-SEED01",
            PurchaseOrderStatus.RECEIVED,
            usman,
            [(parts["SPK-PLG-IR"], 8, 8), (parts["BRK-FLD-D4"], 6, 6)],
        ),
        *purchase_order(
            shop,
            "PO-SEED02",
            PurchaseOrderStatus.PARTIALLY_RECEIVED,
            usman,
            [(parts["TIR-185-65-R15"], 4, 2), (parts["WPR-PAIR"], 4, 0)],
        ),
        *linked_po,
    )

    response = await api.get(overview_url(shop.id), headers=bearer(fatima))
    assert response.status_code == 200, response.text
    body = response.json()

    counts = {item["status"]: item["count"] for item in body["status_counts"] if item["count"]}
    assert counts == {
        "PENDING": 1,
        "AWAITING_CUSTOMER": 1,
        "PARTS_ORDERED": 1,
        "IN_REPAIR": 1,
        "QC_PENDING": 1,
        "READY_FOR_PICKUP": 1,
        "COMPLETED": 1,
        "CANCELLED": 2,
    }
    assert sum(counts.values()) == 9
    assert [(m["full_name"], m["role"], m["open_jobs"]) for m in body["team"]] == [
        ("Fatima Raza", "OWNER", 0),
        ("Bilal", "SERVICE_ADVISOR", 0),
        ("Hamza", "TECHNICIAN", 0),
        ("Imran", "TECHNICIAN", 4),
        ("Usman", "PARTS_PERSON", 3),
        ("Hina", "QC_INSPECTOR", 0),
        ("Sara", "QC_INSPECTOR", 0),
    ]
    assert body["inventory"] == {
        "parts_count": 16,
        "low_stock_count": 6,  # 3 OUT + 3 LOW
        "out_of_stock_count": 3,
        "stock_value": "286400.00",
        "open_purchase_orders": 2,
    }
    assert [
        (part["name"], part["stock_state"], part["available"], part["on_order"])
        for part in body["low_stock"]
    ] == [
        ("Front brake disc", "OUT", 0, 2),
        ("Ignition coil", "OUT", 0, 0),
        ("Wiper blades (pair)", "OUT", 0, 4),
        ("Front brake pads (set)", "LOW", 1, 0),
        ("Cabin AC filter", "LOW", 2, 0),
    ]
    assert body["setup"] == {
        "has_services": True,
        "has_team": True,
        "has_parts": True,
        "is_listed": True,
    }

    summary = await api.get(SUMMARY_URL, headers=bearer(fatima))
    assert summary.status_code == 200, summary.text
    [row] = summary.json()["items"]
    assert {key: value for key, value in row.items() if key != "shop"} == {
        "today_bookings": 0,
        "needs_sa_action": 2,  # PENDING, READY_FOR_PICKUP
        "in_progress": 4,  # AWAITING_CUSTOMER, PARTS_ORDERED, IN_REPAIR, QC_PENDING
        "ready_for_pickup": 1,
        "low_stock_count": 6,
    }

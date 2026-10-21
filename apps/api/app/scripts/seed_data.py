"""The demo data of spec 11, as typed constants (D51, D52, D60).

Data only: `app/scripts/seed.py` turns it into service calls. The demo password lives here and in
the README / login page only (spec 11 principle 7); application logic never sees this module.

Times are symbolic (`At`): `B` is the base-data instant (today - 21 days, 09:00 shop-local);
`P(n)` / `F(n)` are the n-th open day of the shop before / after today (spec 11 "Time anchors").
Payload values that name another record use `User(email)` and `Part(sku)`; the runner resolves
them to ids. A sample booking's steps are listed in script order; `emits_event` marks the steps that
write a `booking_events` row (every action does; a "PUT estimate" only when it creates a version).
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final, Literal

from app.shared.enums import BookingAction, MembershipRole, QcChecklistKey

DEMO_PASSWORD: Final = "BayFlow@2026"  # the published demo password (D52)
SUPPLIER: Final = "City Auto Parts (demo)"

# --- References inside payloads -------------------------------------------------------------------


@dataclass(frozen=True)
class User:
    """A seeded account, by e-mail; resolved to its user id."""

    email: str


@dataclass(frozen=True)
class Part:
    """A part of the booking's shop, by SKU; resolved to its id."""

    sku: str


@dataclass(frozen=True)
class At:
    """A scripted instant: `day` is `B`, `P<n>` or `F<n>`; `time` is shop-local `HH:MM`."""

    day: str
    time: str


def at(day: str, time: str) -> At:
    return At(day, time)


# --- Shops, accounts, catalogues ------------------------------------------------------------------

type Hours = tuple[tuple[str, str] | None, ...]
"""Seven entries, Monday first: `(opens, closes)` or `None` for a closed day."""

MON_SAT_9_18: Final[Hours] = (("09:00", "18:00"),) * 6 + (None,)
MON_SAT_10_19: Final[Hours] = (("10:00", "19:00"),) * 6 + (None,)
PINDI_HOURS: Final[Hours] = (("09:00", "18:00"),) * 6 + (("10:00", "14:00"),)


@dataclass(frozen=True)
class StaffSeed:
    email: str
    full_name: str
    role: MembershipRole


@dataclass(frozen=True)
class OwnerSeed:
    email: str
    full_name: str


@dataclass(frozen=True)
class ShopSeed:
    slug: str
    name: str
    city: str
    address: str
    phone: str
    owner: OwnerSeed
    hours: Hours
    rating: Decimal | None
    staff: tuple[StaffSeed, ...]
    parts_person: str  # e-mail of the Parts Person who creates parts and opening stock
    opening_stock: dict[str, int]


@dataclass(frozen=True)
class CustomerSeed:
    email: str
    full_name: str
    phone: str


@dataclass(frozen=True)
class ServiceSeed:
    name: str
    description: str
    duration_minutes: int
    prices: dict[str, Decimal | None]  # shop slug -> base price (None = "Price after inspection")


@dataclass(frozen=True)
class PartSeed:
    sku: str
    name: str
    unit_cost: Decimal
    reorder_level: int


FATIMA = OwnerSeed("fatima.owner@bayflow.test", "Fatima Raza")


def _team(slug: str, sa: str, tech: str, qc: str, parts: str) -> tuple[StaffSeed, ...]:
    return (
        StaffSeed(f"sa.{slug}@bayflow.test", sa, MembershipRole.SERVICE_ADVISOR),
        StaffSeed(f"tech.{slug}@bayflow.test", tech, MembershipRole.TECHNICIAN),
        StaffSeed(f"qc.{slug}@bayflow.test", qc, MembershipRole.QC_INSPECTOR),
        StaffSeed(f"parts.{slug}@bayflow.test", parts, MembershipRole.PARTS_PERSON),
    )


SKUS: Final = (
    "FLT-OIL-01",
    "OIL-4L-01",
    "IGN-COIL-01",
    "SPK-PLG-IR",
    "FLT-AIR-01",
    "FLT-CAB-01",
    "BRK-PAD-F",
    "BRK-DSC-F",
    "BRK-FLD-D4",
    "CLT-1L",
    "WPR-PAIR",
    "BAT-45AH",
    "AC-R134A",
    "SUS-STB-LNK",
    "TIR-185-65-R15",
    "BLB-H4",
)


def _stock(*quantities: int) -> dict[str, int]:
    return dict(zip(SKUS, quantities, strict=True))


SHOPS: Final[tuple[ShopSeed, ...]] = (
    ShopSeed(
        slug="lahore-auto-care",
        name="Lahore Auto Care",
        city="Lahore",
        address="Plot 12, Main Boulevard, Gulberg III",
        phone="+924200000101",
        owner=FATIMA,
        hours=MON_SAT_9_18,
        rating=Decimal("4.7"),
        staff=(
            StaffSeed("bilal.sa@bayflow.test", "Bilal", MembershipRole.SERVICE_ADVISOR),
            StaffSeed("imran.tech@bayflow.test", "Imran", MembershipRole.TECHNICIAN),
            StaffSeed("hamza.tech@bayflow.test", "Hamza", MembershipRole.TECHNICIAN),
            StaffSeed("sara.qc@bayflow.test", "Sara", MembershipRole.QC_INSPECTOR),
            StaffSeed("hina.qc@bayflow.test", "Hina", MembershipRole.QC_INSPECTOR),
            StaffSeed("usman.parts@bayflow.test", "Usman", MembershipRole.PARTS_PERSON),
        ),
        parts_person="usman.parts@bayflow.test",
        opening_stock=_stock(10, 8, 0, 4, 6, 3, 3, 0, 2, 12, 0, 3, 6, 6, 2, 10),
    ),
    ShopSeed(
        slug="raza-auto-works",
        name="Raza Auto Works",
        city="Lahore",
        address="Plot 8, Commercial Area, DHA Phase 6",
        phone="+924200000102",
        owner=FATIMA,
        hours=MON_SAT_10_19,
        rating=None,
        staff=_team(
            "raza-auto-works", "Adeel Anwar", "Naveed Akhtar", "Rabia Saeed", "Faisal Javed"
        ),
        parts_person="parts.raza-auto-works@bayflow.test",
        opening_stock=_stock(8, 10, 2, 12, 5, 4, 4, 2, 6, 10, 3, 2, 0, 4, 8, 10),
    ),
    ShopSeed(
        slug="clifton-car-clinic",
        name="Clifton Car Clinic",
        city="Karachi",
        address="Shop 3, Block 5, Clifton",
        phone="+922100000201",
        owner=OwnerSeed("owner.clifton-car-clinic@bayflow.test", "Asif Memon"),
        hours=MON_SAT_10_19,
        rating=Decimal("4.5"),
        staff=_team(
            "clifton-car-clinic",
            "Sadia Qureshi",
            "Junaid Baloch",
            "Mehwish Siddiqui",
            "Rizwan Shaikh",
        ),
        parts_person="parts.clifton-car-clinic@bayflow.test",
        opening_stock=_stock(12, 9, 1, 16, 6, 5, 3, 4, 8, 15, 6, 4, 8, 4, 8, 12),
    ),
    ShopSeed(
        slug="margalla-motor-works",
        name="Margalla Motor Works",
        city="Islamabad",
        address="Plot 21, I-9 Markaz",
        phone="+925100000301",
        owner=OwnerSeed("owner.margalla-motor-works@bayflow.test", "Nida Abbasi"),
        hours=MON_SAT_9_18,
        rating=Decimal("4.6"),
        staff=_team(
            "margalla-motor-works", "Waqas Kiani", "Zubair Satti", "Amna Rehman", "Fahad Mirza"
        ),
        parts_person="parts.margalla-motor-works@bayflow.test",
        opening_stock=_stock(10, 12, 3, 8, 4, 3, 5, 2, 6, 10, 2, 3, 6, 4, 4, 8),
    ),
    ShopSeed(
        slug="pindi-auto-garage",
        name="Pindi Auto Garage",
        city="Rawalpindi",
        address="Shop 14, Murree Road, Satellite Town",
        phone="+925100000401",
        owner=OwnerSeed("owner.pindi-auto-garage@bayflow.test", "Tariq Mehmood"),
        hours=PINDI_HOURS,
        rating=Decimal("4.2"),
        staff=_team(
            "pindi-auto-garage", "Saima Bashir", "Arshad Hussain", "Kiran Aslam", "Shoaib Haider"
        ),
        parts_person="parts.pindi-auto-garage@bayflow.test",
        opening_stock=_stock(6, 5, 0, 4, 2, 0, 2, 0, 3, 6, 1, 1, 3, 2, 4, 4),
    ),
    ShopSeed(
        slug="lyallpur-motors",
        name="Lyallpur Motors",
        city="Faisalabad",
        address="Plot 5, Susan Road, Madina Town",
        phone="+924100000501",
        owner=OwnerSeed("owner.lyallpur-motors@bayflow.test", "Khalid Chaudhry"),
        hours=MON_SAT_9_18,
        rating=Decimal("4.4"),
        staff=_team(
            "lyallpur-motors", "Mariam Yousaf", "Asad Latif", "Huma Zafar", "Danish Saleem"
        ),
        parts_person="parts.lyallpur-motors@bayflow.test",
        opening_stock=_stock(9, 7, 2, 12, 6, 4, 3, 2, 5, 8, 4, 2, 5, 4, 12, 10),
    ),
)

CUSTOMERS: Final[tuple[CustomerSeed, ...]] = (
    CustomerSeed("ayesha.customer@bayflow.test", "Ayesha Khan", "+923000000101"),
    CustomerSeed("kamran.customer@bayflow.test", "Kamran Shah", "+923000000102"),
    CustomerSeed("zainab.customer@bayflow.test", "Zainab Malik", "+923000000103"),
    CustomerSeed("nadia.customer@bayflow.test", "Nadia Iqbal", "+923000000104"),
    CustomerSeed("omar.customer@bayflow.test", "Omar Farooq", "+923000000105"),
)

_SLUGS = tuple(shop.slug for shop in SHOPS)


def _prices(*values: int | None, skip: tuple[str, ...] = ()) -> dict[str, Decimal | None]:
    """Prices in `SHOPS` order; shops in `skip` do not offer the service."""
    offered = [slug for slug in _SLUGS if slug not in skip]
    return {
        slug: None if value is None else Decimal(value)
        for slug, value in zip(offered, values, strict=True)
    }


_RAZA = ("raza-auto-works",)

SERVICES: Final[tuple[ServiceSeed, ...]] = (
    ServiceSeed(
        "Oil change",
        "Drain and refill engine oil, replace the oil filter, top up fluids. "
        "Oil and filter are quoted on the estimate.",
        45,
        _prices(1000, 1100, 1100, 1150, 950, 900),
    ),
    ServiceSeed(
        "Brake failure",
        "Diagnose and repair brake problems: pads, discs, fluid, lines and handbrake.",
        120,
        _prices(2500, 2750, 2750, 2900, 2400, 2250),
    ),
    ServiceSeed(
        "Check engine light",
        "OBD-II scan, fault-code reading, sensor checks and a road test.",
        60,
        _prices(2000, 2200, 2200, 2300, 1900, 1800),
    ),
    ServiceSeed(
        "Tire rotation",
        "Rotate tires, set pressures and check tread depth.",
        30,
        _prices(800, 900, 900, 900, 750, 700),
    ),
    ServiceSeed(
        "General inspection",
        "40-point check: brakes, suspension, fluids, lights, battery and tires.",
        60,
        _prices(1500, 1650, 1650, 1750, 1450, 1350),
    ),
    ServiceSeed(
        "AC service",
        "Leak test, gas recharge, cabin filter check and condenser cleaning.",
        90,
        _prices(4500, 4950, 5200, 4300, 4050, skip=_RAZA),
    ),
    ServiceSeed(
        "Battery replacement",
        "Battery and charging-system test; fit a new battery (battery quoted on the estimate).",
        30,
        _prices(500, 550, 550, 600, 500, 450),
    ),
    ServiceSeed(
        "Wheel alignment",
        "Computerised four-wheel alignment and steering check.",
        45,
        _prices(2000, 2200, 2200, 2300, 1900, 1800),
    ),
    ServiceSeed(
        "Suspension repair",
        "Diagnose knocks and vibration; replace links, bushes or shocks. Priced after inspection.",
        180,
        _prices(None, None, None, None, None, skip=_RAZA),
    ),
)


def _part(sku: str, name: str, cost: int, reorder: int) -> PartSeed:
    return PartSeed(sku, name, Decimal(cost), reorder)


PARTS: Final[tuple[PartSeed, ...]] = (
    _part("FLT-OIL-01", "Oil filter", 900, 3),
    _part("OIL-4L-01", "Engine oil 4 L", 5200, 3),
    _part("IGN-COIL-01", "Ignition coil", 6500, 2),
    _part("SPK-PLG-IR", "Spark plug (iridium)", 1800, 6),
    _part("FLT-AIR-01", "Air filter", 1600, 3),
    _part("FLT-CAB-01", "Cabin AC filter", 1400, 3),
    _part("BRK-PAD-F", "Front brake pads (set)", 6800, 2),
    _part("BRK-DSC-F", "Front brake disc", 7500, 2),
    _part("BRK-FLD-D4", "Brake fluid DOT 4 (1 L)", 1500, 4),
    _part("CLT-1L", "Coolant (1 L)", 1200, 5),
    _part("WPR-PAIR", "Wiper blades (pair)", 2200, 2),
    _part("BAT-45AH", "Battery 12V 45Ah", 18500, 2),
    _part("AC-R134A", "AC gas R134a (can)", 3000, 2),
    _part("SUS-STB-LNK", "Front stabilizer link", 4500, 2),
    _part("TIR-185-65-R15", "Tire 185/65 R15", 16000, 4),
    _part("BLB-H4", "Headlight bulb H4", 900, 4),
)

# --- General purchase orders (Lahore Auto Care, by Usman) -----------------------------------------


@dataclass(frozen=True)
class ReceiptSeed:
    at: At
    quantities: dict[str, int]  # SKU -> quantity received in this receipt


@dataclass(frozen=True)
class PurchaseOrderSeed:
    po_number: str
    shop_slug: str
    actor: str
    created_at: At
    items: dict[str, int]  # SKU -> ordered quantity (unit cost = the part's cost)
    receipts: tuple[ReceiptSeed, ...]


PURCHASE_ORDERS: Final[tuple[PurchaseOrderSeed, ...]] = (
    PurchaseOrderSeed(
        po_number="PO-SEED01",
        shop_slug="lahore-auto-care",
        actor="usman.parts@bayflow.test",
        created_at=at("P10", "10:00"),
        items={"SPK-PLG-IR": 8, "BRK-FLD-D4": 6},
        receipts=(ReceiptSeed(at("P9", "15:00"), {"SPK-PLG-IR": 8, "BRK-FLD-D4": 6}),),
    ),
    PurchaseOrderSeed(
        po_number="PO-SEED02",
        shop_slug="lahore-auto-care",
        actor="usman.parts@bayflow.test",
        created_at=at("P3", "15:00"),
        items={"TIR-185-65-R15": 4, "WPR-PAIR": 4},
        receipts=(ReceiptSeed(at("P1", "11:00"), {"TIR-185-65-R15": 2}),),
    ),
)

# --- Vehicles -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class VehicleSeed:
    plate: str
    make: str
    model: str
    year: int
    color: str


VEHICLES: Final[dict[str, VehicleSeed]] = {
    v.plate: v
    for v in (
        VehicleSeed("LEC-4521", "Toyota", "Corolla GLi", 2018, "White"),
        VehicleSeed("LEF-7809", "Suzuki", "Cultus VXL", 2021, "Silver"),
        VehicleSeed("LEB-3307", "Honda", "City 1.5 Aspire", 2019, "Grey"),
        VehicleSeed("LES-8842", "Toyota", "Hilux Revo", 2020, "Black"),
        VehicleSeed("LEH-2210", "Suzuki", "Alto VXR", 2022, "Red"),
        VehicleSeed("LEJ-5512", "Kia", "Sportage AWD", 2022, "White"),
        VehicleSeed("LEG-9146", "Toyota", "Yaris ATIV", 2021, "Black"),
        VehicleSeed("LEK-7731", "Honda", "BR-V", 2019, "Blue"),
        VehicleSeed("BKR-482", "Toyota", "Corolla Altis", 2020, "Silver"),
        VehicleSeed("BTA-317", "Suzuki", "Wagon R", 2019, "White"),
    )
}

# --- Sample bookings ------------------------------------------------------------------------------

StepKind = Literal["staff", "customer", "estimate"]


@dataclass(frozen=True)
class Step:
    at: At
    actor: str  # e-mail
    kind: StepKind
    action: BookingAction | None  # None for "PUT estimate"
    payload: dict[str, Any] = field(default_factory=dict)
    emits_event: bool = True


@dataclass(frozen=True)
class BookingScript:
    reference: str
    shop_slug: str
    customer: str  # e-mail
    plate: str
    mileage_km: int
    services: tuple[str, ...]
    notes: str | None
    slot: At
    created_at: At
    steps: tuple[Step, ...]


CHECKLIST_ALL_PASSED: Final = [{"key": key.value, "passed": True} for key in QcChecklistKey]


def staff(when: At, actor: str, action: BookingAction, **payload: Any) -> Step:
    return Step(when, actor, "staff", action, payload)


def customer(when: At, actor: str, action: BookingAction, **payload: Any) -> Step:
    return Step(when, actor, "customer", action, payload)


def estimate(when: At, actor: str, *lines: dict[str, Any], new_version: bool = False) -> Step:
    """A "PUT estimate" (spec 08 O1); it writes an event only when it creates a new version."""
    return Step(when, actor, "estimate", None, {"lines": list(lines)}, emits_event=new_version)


def part_line(sku: str, quantity: int) -> dict[str, Any]:
    return {"line_type": "PART", "part_id": Part(sku), "quantity": str(quantity)}


def labour(description: str, price: int) -> dict[str, Any]:
    return {
        "line_type": "LABOUR",
        "description": description,
        "quantity": "1",
        "unit_price": str(price),
    }


A = BookingAction
BILAL = "bilal.sa@bayflow.test"
IMRAN = "imran.tech@bayflow.test"
HAMZA = "hamza.tech@bayflow.test"
SARA = "sara.qc@bayflow.test"
HINA = "hina.qc@bayflow.test"
USMAN = "usman.parts@bayflow.test"
AYESHA = "ayesha.customer@bayflow.test"
KAMRAN = "kamran.customer@bayflow.test"
ZAINAB = "zainab.customer@bayflow.test"
NADIA = "nadia.customer@bayflow.test"
OMAR = "omar.customer@bayflow.test"

_PASS = {"checklist": CHECKLIST_ALL_PASSED}


def _full_job(  # noqa: PLR0913 - one argument per actor and scripted value
    *,
    sa: str,
    tech: str,
    parts: str,
    qc: str,
    cust: str,
    day_create: str,
    day_work: str,
    times: tuple[str, ...],
    lines: tuple[dict[str, Any], ...],
    complete_by_staff: bool,
) -> tuple[Step, ...]:
    """The compact path of BF-SEED11 / BF-SEED15 (spec 11 "Scripts — other shops").

    `times`: confirm, assign, start-inspection, PUT, submit, send, approve, assign-parts,
    mark-ready, allocate, start-repair, send-to-qc, pick, pass, notify, complete; the first two
    are on `day_create`, the rest on `day_work`.
    """
    t = iter(times[:-1])
    c, w = day_create, day_work
    finish = at(w, times[-1])
    done = (
        staff(finish, sa, A.COMPLETE) if complete_by_staff else customer(finish, cust, A.COMPLETE)
    )
    return (
        staff(at(c, next(t)), sa, A.CONFIRM),
        staff(at(c, next(t)), sa, A.ASSIGN_TECHNICIAN, technician_user_id=User(tech)),
        staff(at(w, next(t)), tech, A.START_INSPECTION),
        estimate(at(w, next(t)), tech, *lines),
        staff(at(w, next(t)), tech, A.SUBMIT_ESTIMATE),
        staff(at(w, next(t)), sa, A.SEND_ESTIMATE),
        customer(at(w, next(t)), cust, A.APPROVE_ESTIMATE),
        staff(at(w, next(t)), sa, A.ASSIGN_PARTS_PERSON, parts_person_user_id=User(parts)),
        staff(at(w, next(t)), parts, A.MARK_PARTS_READY),
        staff(at(w, next(t)), parts, A.ALLOCATE_PARTS),
        staff(at(w, next(t)), tech, A.START_REPAIR),
        staff(at(w, next(t)), tech, A.SEND_TO_QC),
        staff(at(w, next(t)), qc, A.PICK_QC),
        staff(at(w, next(t)), qc, A.PASS_QC, **_PASS),
        staff(at(w, next(t)), sa, A.NOTIFY_READY),
        done,
    )


BOOKINGS: Final[tuple[BookingScript, ...]] = (
    BookingScript(
        reference="BF-SEED07",
        shop_slug="lahore-auto-care",
        customer=AYESHA,
        plate="LEC-4521",
        mileage_km=67_900,
        services=("Brake failure",),
        notes="Brakes squeal and the car pulls to the left when braking.",
        slot=at("P8", "09:00"),
        created_at=at("P9", "11:20"),
        steps=(
            staff(at("P9", "11:45"), BILAL, A.CONFIRM),
            staff(at("P9", "11:46"), BILAL, A.ASSIGN_TECHNICIAN, technician_user_id=User(IMRAN)),
            staff(at("P8", "09:20"), IMRAN, A.START_INSPECTION),
            estimate(
                at("P8", "10:25"),
                IMRAN,
                part_line("BRK-PAD-F", 1),
                part_line("BRK-FLD-D4", 1),
                labour("Replace front pads and bleed brakes", 3000),
            ),
            staff(
                at("P8", "10:30"),
                IMRAN,
                A.SUBMIT_ESTIMATE,
                inspection_notes="Front pads worn to 2 mm; brake fluid dark; discs within limits.",
            ),
            staff(at("P8", "11:00"), BILAL, A.SEND_ESTIMATE),
            customer(at("P8", "11:30"), AYESHA, A.APPROVE_ESTIMATE),
            staff(
                at("P8", "11:40"), BILAL, A.ASSIGN_PARTS_PERSON, parts_person_user_id=User(USMAN)
            ),
            staff(at("P8", "12:00"), USMAN, A.MARK_PARTS_READY),
            staff(at("P8", "12:10"), USMAN, A.ALLOCATE_PARTS),
            staff(at("P8", "12:30"), IMRAN, A.START_REPAIR),
            staff(
                at("P8", "15:30"), IMRAN, A.SEND_TO_QC, repair_notes="Pads replaced, system bled."
            ),
            staff(at("P8", "15:45"), SARA, A.PICK_QC),
            staff(
                at("P8", "16:15"),
                SARA,
                A.FAIL_QC,
                issue_title="Soft brake pedal",
                issue_description=(
                    "Pedal travel too long on the road test; air still in the brake lines."
                ),
            ),
            staff(at("P8", "16:30"), IMRAN, A.START_REPAIR),
            staff(
                at("P8", "17:15"),
                IMRAN,
                A.SEND_TO_QC,
                repair_notes="Re-bled all four wheels; pedal firm.",
            ),
            staff(at("P8", "17:20"), HINA, A.PICK_QC),
            staff(at("P8", "17:45"), HINA, A.PASS_QC, **_PASS),
            staff(at("P8", "17:50"), BILAL, A.NOTIFY_READY),
            customer(at("P7", "10:15"), AYESHA, A.COMPLETE),
        ),
    ),
    BookingScript(
        reference="BF-SEED08",
        shop_slug="lahore-auto-care",
        customer=AYESHA,
        plate="LEF-7809",
        mileage_km=31_050,
        services=("Battery replacement",),
        notes="Car won't start on cold mornings.",
        slot=at("P5", "11:00"),
        created_at=at("P6", "09:10"),
        steps=(
            staff(at("P6", "09:30"), BILAL, A.CONFIRM),
            staff(at("P6", "09:31"), BILAL, A.ASSIGN_TECHNICIAN, technician_user_id=User(IMRAN)),
            staff(at("P5", "11:15"), IMRAN, A.START_INSPECTION),
            estimate(
                at("P5", "11:35"),
                IMRAN,
                part_line("BAT-45AH", 1),
                labour("Battery and charging test, fit new battery", 500),
            ),
            staff(
                at("P5", "11:40"),
                IMRAN,
                A.SUBMIT_ESTIMATE,
                inspection_notes="Battery fails the load test (9.6 V); alternator charging OK.",
            ),
            staff(at("P5", "12:00"), BILAL, A.SEND_ESTIMATE),
            customer(at("P5", "12:20"), AYESHA, A.APPROVE_ESTIMATE),
            staff(
                at("P5", "12:25"), BILAL, A.ASSIGN_PARTS_PERSON, parts_person_user_id=User(USMAN)
            ),
            staff(at("P5", "12:40"), USMAN, A.MARK_PARTS_READY),
            customer(
                at("P5", "13:05"),
                AYESHA,
                A.CANCEL,
                reason="I got a battery under warranty from the dealer.",
            ),
        ),
    ),
    BookingScript(
        reference="BF-SEED09",
        shop_slug="lahore-auto-care",
        customer=KAMRAN,
        plate="LEB-3307",
        mileage_km=54_700,
        services=("Brake failure",),
        notes="Grinding noise when braking.",
        slot=at("P5", "09:00"),
        created_at=at("P6", "10:00"),
        steps=(
            staff(
                at("P6", "10:30"),
                BILAL,
                A.DECLINE,
                reason=(
                    "Both bays are booked for an engine job that morning — "
                    "please choose another day."
                ),
            ),
        ),
    ),
    BookingScript(
        reference="BF-SEED03",
        shop_slug="lahore-auto-care",
        customer=KAMRAN,
        plate="LEB-3307",
        mileage_km=54_900,
        services=("Brake failure",),
        notes="Grinding noise when braking; pedal vibrates.",
        slot=at("P3", "09:00"),
        created_at=at("P4", "12:00"),
        steps=(
            staff(at("P4", "12:30"), BILAL, A.CONFIRM),
            staff(at("P4", "12:31"), BILAL, A.ASSIGN_TECHNICIAN, technician_user_id=User(IMRAN)),
            staff(at("P3", "09:15"), IMRAN, A.START_INSPECTION),
            estimate(
                at("P3", "10:25"),
                IMRAN,
                part_line("BRK-PAD-F", 1),
                part_line("BRK-DSC-F", 2),
                part_line("BRK-FLD-D4", 1),
                labour("Replace front discs and pads, bleed brakes", 5000),
            ),
            staff(
                at("P3", "10:30"),
                IMRAN,
                A.SUBMIT_ESTIMATE,
                inspection_notes=(
                    "Front discs below minimum thickness; pads worn to the backing plate."
                ),
            ),
            staff(at("P3", "11:00"), BILAL, A.SEND_ESTIMATE),
            customer(
                at("P3", "12:10"),
                KAMRAN,
                A.REJECT_ESTIMATE,
                reason="Labour seems high compared to other quotes.",
            ),
            staff(at("P3", "12:30"), BILAL, A.REVISE_ESTIMATE),
            estimate(
                at("P3", "12:35"),
                BILAL,
                part_line("BRK-PAD-F", 1),
                part_line("BRK-DSC-F", 2),
                part_line("BRK-FLD-D4", 1),
                labour("Replace front discs and pads, bleed brakes", 4000),
            ),
            staff(at("P3", "12:40"), BILAL, A.SEND_ESTIMATE),
            customer(at("P3", "13:15"), KAMRAN, A.APPROVE_ESTIMATE),
            staff(
                at("P3", "13:20"), BILAL, A.ASSIGN_PARTS_PERSON, parts_person_user_id=User(USMAN)
            ),
            staff(at("P3", "13:40"), USMAN, A.ORDER_PARTS, supplier_name=SUPPLIER),
        ),
    ),
    BookingScript(
        reference="BF-SEED05",
        shop_slug="lahore-auto-care",
        customer=NADIA,
        plate="LEG-9146",
        mileage_km=36_800,
        services=("Check engine light",),
        notes="Engine light came on after refuelling; hesitates when accelerating.",
        slot=at("P2", "11:00"),
        created_at=at("P3", "10:00"),
        steps=(
            staff(at("P3", "10:20"), BILAL, A.CONFIRM),
            staff(at("P3", "10:21"), BILAL, A.ASSIGN_TECHNICIAN, technician_user_id=User(IMRAN)),
            staff(at("P2", "11:10"), IMRAN, A.START_INSPECTION),
            estimate(
                at("P2", "11:55"),
                IMRAN,
                part_line("SPK-PLG-IR", 4),
                labour("OBD scan, spark plug replacement, throttle body cleaning", 2500),
            ),
            staff(
                at("P2", "12:00"),
                IMRAN,
                A.SUBMIT_ESTIMATE,
                inspection_notes="Code P0302 (misfire, cylinder 2); plugs worn.",
            ),
            staff(at("P2", "12:15"), BILAL, A.SEND_ESTIMATE),
            customer(at("P2", "13:00"), NADIA, A.APPROVE_ESTIMATE),
            staff(
                at("P2", "13:05"), BILAL, A.ASSIGN_PARTS_PERSON, parts_person_user_id=User(USMAN)
            ),
            staff(at("P2", "13:20"), USMAN, A.MARK_PARTS_READY),
            staff(at("P2", "13:25"), USMAN, A.ALLOCATE_PARTS),
            staff(at("P2", "14:00"), IMRAN, A.START_REPAIR),
            staff(
                at("P1", "16:40"),
                IMRAN,
                A.SEND_TO_QC,
                repair_notes="Plugs replaced, codes cleared, no misfire on a 10 km test.",
            ),
        ),
    ),
    BookingScript(
        reference="BF-SEED06",
        shop_slug="lahore-auto-care",
        customer=AYESHA,
        plate="LEF-7809",
        mileage_km=31_200,
        services=("AC service",),
        notes="AC blows warm air in the afternoon.",
        slot=at("P2", "12:00"),
        created_at=at("P3", "21:10"),
        steps=(
            staff(at("P2", "09:05"), BILAL, A.CONFIRM),
            staff(at("P2", "09:06"), BILAL, A.ASSIGN_TECHNICIAN, technician_user_id=User(HAMZA)),
            staff(at("P2", "12:10"), HAMZA, A.START_INSPECTION),
            estimate(
                at("P2", "12:45"),
                HAMZA,
                part_line("AC-R134A", 1),
                part_line("FLT-CAB-01", 1),
                labour("AC leak test, recharge and condenser cleaning", 4500),
            ),
            staff(
                at("P2", "12:50"),
                HAMZA,
                A.SUBMIT_ESTIMATE,
                inspection_notes=(
                    "Low gas pressure; no leak found with UV dye; cabin filter clogged."
                ),
            ),
            staff(at("P2", "13:10"), BILAL, A.SEND_ESTIMATE),
            customer(at("P2", "13:30"), AYESHA, A.APPROVE_ESTIMATE),
            staff(
                at("P2", "13:35"), BILAL, A.ASSIGN_PARTS_PERSON, parts_person_user_id=User(USMAN)
            ),
            staff(at("P2", "13:50"), USMAN, A.MARK_PARTS_READY),
            staff(at("P2", "14:00"), USMAN, A.ALLOCATE_PARTS),
            staff(at("P2", "14:10"), HAMZA, A.START_REPAIR),
            staff(
                at("P2", "16:30"),
                HAMZA,
                A.SEND_TO_QC,
                repair_notes="Recharged to spec; vent temperature 6 °C.",
            ),
            staff(at("P1", "09:20"), SARA, A.PICK_QC),
            staff(
                at("P1", "09:50"),
                SARA,
                A.PASS_QC,
                notes="Cooling OK after a 20-minute road test.",
                **_PASS,
            ),
        ),
    ),
    BookingScript(
        reference="BF-SEED02",
        shop_slug="lahore-auto-care",
        customer=AYESHA,
        plate="LEC-4521",
        mileage_km=68_400,
        services=("Suspension repair",),
        notes="Knocking from the front left over speed breakers.",
        slot=at("P1", "11:00"),
        created_at=at("P2", "09:30"),
        steps=(
            staff(at("P2", "10:00"), BILAL, A.CONFIRM),
            staff(at("P2", "10:01"), BILAL, A.ASSIGN_TECHNICIAN, technician_user_id=User(IMRAN)),
            staff(at("P1", "11:10"), IMRAN, A.START_INSPECTION),
            estimate(
                at("P1", "11:55"),
                IMRAN,
                part_line("SUS-STB-LNK", 2),
                labour("Replace both front stabilizer links + alignment check", 3500),
            ),
            staff(
                at("P1", "12:00"),
                IMRAN,
                A.SUBMIT_ESTIMATE,
                inspection_notes="Both front stabilizer links have play; bushes OK.",
            ),
            estimate(
                at("P1", "12:20"),
                BILAL,
                part_line("SUS-STB-LNK", 2),
                labour("Replace both front stabilizer links + alignment check", 3000),
                new_version=True,
            ),
            staff(at("P1", "12:25"), BILAL, A.SEND_ESTIMATE),
        ),
    ),
    BookingScript(
        reference="BF-SEED04",
        shop_slug="lahore-auto-care",
        customer=ZAINAB,
        plate="LEJ-5512",
        mileage_km=27_300,
        services=("Wheel alignment", "Tire rotation"),
        notes="Steering wheel off-centre after a pothole; car pulls left.",
        slot=at("P1", "09:00"),
        created_at=at("P2", "16:00"),
        steps=(
            staff(at("P2", "16:20"), BILAL, A.CONFIRM),
            staff(at("P2", "16:21"), BILAL, A.ASSIGN_TECHNICIAN, technician_user_id=User(IMRAN)),
            staff(at("P1", "09:10"), IMRAN, A.START_INSPECTION),
            estimate(
                at("P1", "09:35"),
                IMRAN,
                labour("Four-wheel alignment", 2000),
                labour("Tire rotation", 800),
            ),
            staff(
                at("P1", "09:40"),
                IMRAN,
                A.SUBMIT_ESTIMATE,
                inspection_notes="Front toe out of spec; no suspension damage.",
            ),
            staff(at("P1", "09:50"), BILAL, A.SEND_ESTIMATE),
            customer(at("P1", "10:05"), ZAINAB, A.APPROVE_ESTIMATE),
            staff(
                at("P1", "10:10"), BILAL, A.ASSIGN_PARTS_PERSON, parts_person_user_id=User(USMAN)
            ),
            staff(at("P1", "10:15"), USMAN, A.MARK_PARTS_READY),
            staff(at("P1", "10:16"), USMAN, A.ALLOCATE_PARTS),
            staff(at("P1", "10:30"), IMRAN, A.START_REPAIR),
        ),
    ),
    BookingScript(
        reference="BF-SEED01",
        shop_slug="lahore-auto-care",
        customer=ZAINAB,
        plate="LEH-2210",
        mileage_km=18_500,
        services=("AC service", "General inspection"),
        notes="AC not cooling well; want a full check before a trip to Murree.",
        slot=at("F2", "11:00"),
        created_at=at("P1", "20:15"),
        steps=(),
    ),
    BookingScript(
        reference="BF-SEED15",
        shop_slug="lyallpur-motors",
        customer=NADIA,
        plate="LEG-9146",
        mileage_km=35_600,
        services=("Tire rotation",),
        notes=None,
        slot=at("P11", "10:00"),
        created_at=at("P12", "10:00"),
        steps=_full_job(
            sa="sa.lyallpur-motors@bayflow.test",
            tech="tech.lyallpur-motors@bayflow.test",
            parts="parts.lyallpur-motors@bayflow.test",
            qc="qc.lyallpur-motors@bayflow.test",
            cust=NADIA,
            day_create="P12",
            day_work="P11",
            times=(
                "10:30",
                "10:31",
                "10:05",
                "10:15",
                "10:20",
                "10:25",
                "10:40",
                "10:45",
                "10:46",
                "10:47",
                "10:50",
                "11:20",
                "11:25",
                "11:35",
                "11:40",
                "17:00",
            ),
            lines=(labour("Tire rotation", 700),),
            complete_by_staff=False,
        ),
    ),
    BookingScript(
        reference="BF-SEED11",
        shop_slug="raza-auto-works",
        customer=KAMRAN,
        plate="LES-8842",
        mileage_km=86_900,
        services=("Oil change",),
        notes=None,
        slot=at("P10", "11:00"),
        created_at=at("P11", "18:00"),
        steps=_full_job(
            sa="sa.raza-auto-works@bayflow.test",
            tech="tech.raza-auto-works@bayflow.test",
            parts="parts.raza-auto-works@bayflow.test",
            qc="qc.raza-auto-works@bayflow.test",
            cust=KAMRAN,
            day_create="P10",
            day_work="P10",
            times=(
                "10:05",
                "10:06",
                "11:10",
                "11:25",
                "11:30",
                "11:40",
                "11:55",
                "12:00",
                "12:05",
                "12:10",
                "12:15",
                "13:00",
                "13:10",
                "13:30",
                "13:35",
                "16:00",
            ),
            lines=(
                part_line("FLT-OIL-01", 1),
                part_line("OIL-4L-01", 2),
                labour("Oil change", 1100),
            ),
            complete_by_staff=True,
        ),
    ),
    BookingScript(
        reference="BF-SEED10",
        shop_slug="raza-auto-works",
        customer=KAMRAN,
        plate="LES-8842",
        mileage_km=88_000,
        services=("Oil change", "General inspection"),
        notes="Due for the 90,000 km service.",
        slot=at("F1", "12:00"),
        created_at=at("P1", "17:30"),
        steps=(),
    ),
    BookingScript(
        reference="BF-SEED12",
        shop_slug="clifton-car-clinic",
        customer=OMAR,
        plate="BKR-482",
        mileage_km=45_600,
        services=("Check engine light",),
        notes="Engine light on since the weekend.",
        slot=at("F1", "15:00"),
        created_at=at("P1", "21:00"),
        steps=(),
    ),
    BookingScript(
        reference="BF-SEED13",
        shop_slug="margalla-motor-works",
        customer=NADIA,
        plate="LEK-7731",
        mileage_km=61_000,
        services=("Brake failure",),
        notes="Brake warning light flickers on downhill roads.",
        slot=at("F3", "11:00"),
        created_at=at("P1", "19:00"),
        steps=(),
    ),
    BookingScript(
        reference="BF-SEED14",
        shop_slug="pindi-auto-garage",
        customer=OMAR,
        plate="BTA-317",
        mileage_km=72_100,
        services=("Tire rotation", "Wheel alignment"),
        notes="Car pulls to the right.",
        slot=at("F2", "12:00"),
        created_at=at("P1", "18:30"),
        steps=(),
    ),
)

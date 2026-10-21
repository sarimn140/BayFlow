"""`POST /api/v1/bookings`, the booking wizard (T01; spec 03 §4.6; `modules/bookings.md` §7.1-7.3).

BK-01…BK-09, BK-13…BK-15, BK-20, BK-26, BK-28, BK-32, SEC-17 (booking create), SEC-18, SEC-19,
SEC-20, SEC-27 (wizard half), the D32 account rule (cases A-D), D33 phones, D35 vehicles, D65
mileage, §7.3 references (incl. the seed's reserved references) and the `CREATE` event contract.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text

from app.core.database import Database
from app.core.errors import Conflict
from app.core.security import issue_token
from app.modules.bookings import service as bookings_service
from app.modules.bookings.events import BookingActionApplied
from app.modules.bookings.models import BookingService, Vehicle
from app.modules.bookings.schemas import BookingCreate
from app.modules.identity.models import User
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import ServiceUpdate
from app.shared.auth import CurrentUser
from app.shared.clock import SimulatedClock, utcnow
from app.shared.enums import ActorRole, BookingAction, BookingStatus
from app.shared.event_bus import Event
from tests.modules.bookings.support import (
    FRIDAY_1000,
    Desk,
    World,
    booking_row,
    count_rows,
    events_of,
    field_codes,
    new_customer,
    problem,
    slot_count,
    vehicle,
)
from tests.modules.identity.builders import (
    TEST_PASSWORD,
    bearer,
    make_user,
    unique_email,
    unit_of_work,
)
from tests.modules.shops.builders import make_services, make_shop

pytestmark = pytest.mark.db

PKT_10_30_FRIDAY = datetime(2026, 10, 16, 5, 30, tzinfo=UTC)
CREATED_TABLES = (
    "users",
    "vehicles",
    "bookings",
    "booking_services",
    "booking_events",
    "notifications",
)
WRONG_PASSWORD_DETAIL = (
    "There's already a BayFlow account for this e-mail and the password didn't match. "
    "Log in to finish your booking."
)


def anonymous(desk: Desk, email: str | None = None, **overrides: Any) -> dict[str, Any]:
    body = desk.booking_body(**overrides)
    body["customer"] = {
        "full_name": "Ahmed",
        "email": email or unique_email("ahmed"),
        "password": TEST_PASSWORD,
    }
    return body


async def table_counts(db: Database) -> dict[str, int]:
    return {table: await count_rows(db, table) for table in CREATED_TABLES}


async def stored_user(db: Database, email: str) -> User:
    async with db.sessionmaker() as session:
        return (await session.execute(select(User).where(User.email == email))).scalar_one()


def session_cookie(response: httpx.Response) -> str:
    cookie = response.headers.get("set-cookie", "")
    assert cookie.startswith("bf_session="), response.headers
    for attribute in ("HttpOnly", "Max-Age=604800", "Path=/", "SameSite=lax"):
        assert attribute in cookie, cookie
    return cookie


# --- D32: the account rule ------------------------------------------------------------------------


async def test_bk01_a_new_email_creates_the_account_vehicle_and_booking_and_logs_in(
    desk: Desk, world: World, db: Database, clock: SimulatedClock
) -> None:
    email = "Ahmed.Demo@BayFlow.TEST"
    body = anonymous(desk, email, slot=FRIDAY_1000, customer_notes="  Light came on.  ")
    body["customer"]["phone"] = "+92 300 1234567"
    response = await desk.wizard(body)
    assert response.status_code == 201, response.text
    session_cookie(response)
    created = response.json()
    assert created["token_type"] == "bearer"
    assert created["expires_in"] == 604_800
    assert created["account_created"] is True
    booking = created["booking"]
    assert booking["status"] == "PENDING"
    assert booking["version"] == 1
    assert booking["allowed_actions"] == ["cancel"]
    assert booking["slot_start"] == "2026-10-16T05:00:00Z"
    assert booking["slot_end"] == "2026-10-16T06:00:00Z"
    assert booking["status_changed_at"] == booking["created_at"] == "2026-10-14T04:00:00Z"
    assert booking["customer_notes"] == "Light came on."
    assert booking["estimate"] is None
    assert booking["estimate_revision_in_progress"] is False
    assert booking["cancelled_by_customer"] is None
    assert [s["name"] for s in booking["services"]] == ["Check engine light", "Oil change"]
    assert {s["base_price"] for s in booking["services"]} == {"2000.00"}
    assert booking["shop"] == {
        "id": str(world.shop_id),
        "slug": world.shop.slug,
        "name": "Lahore Auto Care",
        "city": "Lahore",
        "phone": world.shop.shop.phone,
        "timezone": "Asia/Karachi",
        "address": world.shop.shop.address,
    }
    assert booking["vehicle"]["registration_number"] == "LEA-1234"
    user = await stored_user(db, "ahmed.demo@bayflow.test")
    assert user.full_name == "Ahmed"
    assert user.phone == "+923001234567"
    assert user.last_login_at == clock.now()  # the booking logs the new customer in
    row = await booking_row(db, booking["id"])
    assert row.customer_user_id == user.id
    assert row.mileage_km is None
    assert await slot_count(db, world.shop_id, FRIDAY_1000) == 1
    (event,) = await events_of(db, booking["id"])
    assert (event.action, event.from_status, event.to_status) == (
        BookingAction.CREATE,
        None,
        BookingStatus.PENDING,
    )
    assert (event.actor_user_id, event.actor_role, event.metadata_) == (
        user.id,
        ActorRole.CUSTOMER,
        {},
    )
    # SEC-19: the body token works as a Bearer token; the same e-mail and password log in later.
    mine = await desk.api.get(
        "/api/v1/me/bookings", headers={"Authorization": f"Bearer {created['access_token']}"}
    )
    assert [item["id"] for item in mine.json()["items"]] == [booking["id"]]
    login = await desk.api.post(
        "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    assert login.status_code == 200, login.text


async def test_bk02_an_existing_email_with_the_right_password_reuses_the_account(
    desk: Desk, db: Database, clock: SimulatedClock
) -> None:
    user = await make_user(db, full_name="Ayesha Khan")
    before = await count_rows(db, "users")
    clock.advance(timedelta(minutes=5))
    body = anonymous(desk, user.email.upper())
    body["customer"]["full_name"] = "Someone Else"
    response = await desk.wizard(body)
    assert response.status_code == 201, response.text
    session_cookie(response)
    assert response.json()["account_created"] is False
    assert await count_rows(db, "users") == before
    row = await booking_row(db, response.json()["booking"]["id"])
    assert row.customer_user_id == user.id
    stored = await stored_user(db, user.email)
    assert stored.full_name == "Ayesha Khan"  # the account is never changed by the wizard
    assert stored.last_login_at == clock.now()


async def test_bk03_sec18_an_existing_email_with_a_wrong_password_creates_nothing(
    desk: Desk, world: World, db: Database
) -> None:
    user = await make_user(db)
    before = await table_counts(db)
    body = anonymous(desk, user.email, slot=FRIDAY_1000)
    body["customer"]["password"] = "not-the-right-password"
    response = await desk.wizard(body)
    detail = problem(response, 409, "EMAIL_ALREADY_REGISTERED")["detail"]
    assert detail == WRONG_PASSWORD_DETAIL
    assert "set-cookie" not in response.headers
    assert await table_counts(db) == before
    assert await slot_count(db, world.shop_id, FRIDAY_1000) is None


async def test_an_inactive_account_is_409_even_with_the_right_password(
    desk: Desk, db: Database
) -> None:
    user = await make_user(db, active=False)
    before = await table_counts(db)
    response = await desk.wizard(anonymous(desk, user.email))
    problem(response, 409, "EMAIL_ALREADY_REGISTERED")
    assert await table_counts(db) == before


async def test_bk04_sec20_a_session_books_for_its_user_and_ignores_the_body_identity(
    desk: Desk, db: Database, clock: SimulatedClock
) -> None:
    customer = await new_customer(db)
    stranger = await make_user(db, email=unique_email("stranger"))
    before = await count_rows(db, "users")
    body = anonymous(desk, stranger.email)
    body["customer"]["password"] = "wrong-but-ignored"
    clock.advance(timedelta(minutes=1))
    response = await desk.wizard(body, headers=customer.headers)
    assert response.status_code == 201, response.text
    session_cookie(response)  # the session is re-issued
    assert response.json()["account_created"] is False
    assert await count_rows(db, "users") == before
    assert (await booking_row(db, response.json()["booking"]["id"])).customer_user_id == (
        customer.user_id
    )
    stored = await stored_user(db, customer.email)
    assert stored.last_login_at is None  # case A never touches it


async def test_sec20_credentials_present_but_invalid_are_401_never_anonymous(
    desk: Desk, db: Database, clock: SimulatedClock
) -> None:
    customer = await new_customer(db)
    inactive = await make_user(db, active=False)
    before = await table_counts(db)
    garbage = await desk.wizard(anonymous(desk), headers={"Authorization": "Bearer garbage"})
    problem(garbage, 401, "UNAUTHENTICATED")
    expired_token = issue_token(customer.user_id, "session", utcnow() - timedelta(days=8))
    desk.api.cookies.set("bf_session", expired_token)
    try:
        expired = await desk.wizard(anonymous(desk))
    finally:
        desk.api.cookies.clear()
    problem(expired, 401, "UNAUTHENTICATED")
    assert "bf_session=" in expired.headers["set-cookie"]  # the stale cookie is cleared
    deactivated = await desk.wizard(anonymous(desk), headers=bearer(inactive.id))
    problem(deactivated, 401, "UNAUTHENTICATED")
    assert await table_counts(db) == before


async def test_bk05_the_phone_fills_only_an_empty_phone(desk: Desk, db: Database) -> None:
    customer = await new_customer(db)
    first = desk.booking_body()
    first["customer"] = {"phone": "0300-1234567"}
    assert (await desk.wizard(first, headers=customer.headers)).status_code == 201
    assert (await stored_user(db, customer.email)).phone == "03001234567"
    second = desk.booking_body()
    second["customer"] = {"phone": "+92 311 7654321"}
    assert (await desk.wizard(second, headers=customer.headers)).status_code == 201
    assert (await stored_user(db, customer.email)).phone == "03001234567"  # never overwritten
    returning = await make_user(db, phone="+923339999999")
    body = anonymous(desk, returning.email)
    body["customer"]["phone"] = "+92 300 0000000"
    assert (await desk.wizard(body)).status_code == 201  # case C
    assert (await stored_user(db, returning.email)).phone == "+923339999999"


# --- Services, slots, shops -----------------------------------------------------------------------


async def test_bk06_services_must_be_active_services_of_this_shop(
    desk: Desk, world: World, db: Database
) -> None:
    before = await table_counts(db)
    (inactive,) = await make_services(db, world.shop, ["Retired service"], active=False)
    other_service = (await make_services(db, world.other, ["Their service"]))[0]
    body = anonymous(desk, services=[world.services[0], inactive, other_service])
    response = await desk.wizard(body)
    body_problem = problem(response, 422, "VALIDATION_ERROR")
    assert field_codes(body_problem) == [
        ("service_ids.1", "invalid_reference"),
        ("service_ids.2", "invalid_reference"),
    ]
    empty = await desk.wizard(anonymous(desk, service_ids=[]))
    assert field_codes(problem(empty, 422, "VALIDATION_ERROR")) == [("service_ids", "too_short")]
    duplicated = anonymous(desk, services=[world.services[0], world.services[0]])
    response = await desk.wizard(duplicated)
    assert field_codes(problem(response, 422, "VALIDATION_ERROR")) == [
        ("service_ids.1", "duplicate")
    ]
    assert await table_counts(db) == before
    several = anonymous(desk, services=world.services, customer_notes="Please check the brakes.")
    created = await desk.wizard(several)
    assert created.status_code == 201, created.text
    names = [service["name"] for service in created.json()["booking"]["services"]]
    assert names == ["Check engine light", "Oil change", "Wheel alignment"]


async def test_bk07_services_are_snapshotted(desk: Desk, world: World, db: Database) -> None:
    journey = await desk.book()
    async with unit_of_work(db) as uow:
        await shops_service.update_service(
            uow,
            shop_id=world.shop_id,
            actor_user_id=world.owner.id,
            service_id=world.services[0].id,
            data=ServiceUpdate(name="Engine diagnostics", base_price="3500"),
        )
    detail = await desk.my_detail(journey.customer, journey.id)
    assert detail["services"][0] == {
        "service_id": str(world.services[0].id),
        "name": "Check engine light",
        "base_price": "2000.00",
    }
    async with db.sessionmaker() as session:
        rows = (
            await session.execute(
                select(BookingService).where(BookingService.booking_id == uuid.UUID(journey.id))
            )
        ).scalars()
        assert {row.name_snapshot for row in rows} == {"Check engine light", "Oil change"}


@pytest.mark.parametrize(
    ("slot_start", "reason"),
    [
        (PKT_10_30_FRIDAY, "off_grid"),
        (datetime(2026, 10, 14, 4, 0, tzinfo=UTC), "in_past"),  # exactly now (Wed 09:00 PKT)
        (datetime(2026, 10, 13, 5, 0, tzinfo=UTC), "in_past"),
        (datetime(2026, 11, 14, 5, 0, tzinfo=UTC), "beyond_horizon"),  # today + 31 days
        (datetime(2026, 10, 18, 5, 0, tzinfo=UTC), "closed_day"),  # Sunday
        (datetime(2026, 10, 16, 3, 0, tzinfo=UTC), "outside_hours"),  # 08:00 local
        (datetime(2026, 10, 16, 13, 0, tzinfo=UTC), "outside_hours"),  # 18:00 ends after closing
    ],
)
async def test_bk08_invalid_slots_are_422_and_create_nothing(
    desk: Desk, db: Database, slot_start: datetime, reason: str
) -> None:
    before = await table_counts(db)
    response = await desk.wizard(anonymous(desk, slot=slot_start))
    body = problem(response, 422, "INVALID_SLOT")
    assert field_codes(body) == [("slot_start", reason)]
    assert await table_counts(db) == before


async def test_bk09_a_full_slot_is_409_and_other_slots_are_unaffected(
    desk: Desk, world: World, db: Database
) -> None:
    small = await make_shop(db, owner=world.owner, name="Raza Auto Works", capacity=2)
    services = await make_services(db, small, ["Oil change"])
    for _ in range(2):
        body = anonymous(desk, slot=FRIDAY_1000, shop_id=small.id, services=services)
        assert (await desk.wizard(body)).status_code == 201
    before = await table_counts(db)
    third = await desk.wizard(
        anonymous(desk, slot=FRIDAY_1000, shop_id=small.id, services=services)
    )
    problem(third, 409, "SLOT_FULL")
    assert await table_counts(db) == before  # no account, vehicle or booking for the loser
    assert await slot_count(db, small.id, FRIDAY_1000) == 2
    later = anonymous(
        desk, slot=FRIDAY_1000 + timedelta(hours=1), shop_id=small.id, services=services
    )
    assert (await desk.wizard(later)).status_code == 201


async def test_bk15_bk26_unknown_unlisted_or_serviceless_shops_are_404(
    desk: Desk, world: World, db: Database
) -> None:
    unlisted = await make_shop(db, owner=world.owner, listed=False)
    await make_services(db, unlisted, ["Oil change"])
    empty = await make_shop(db, owner=world.owner)
    retired = await make_shop(db, owner=world.owner)
    await make_services(db, retired, ["Old"], active=False)
    before = await table_counts(db)
    for shop_id in (uuid.uuid4(), unlisted.id, empty.id, retired.id):
        response = await desk.wizard(anonymous(desk, shop_id=shop_id))
        problem(response, 404, "NOT_FOUND")
    assert await table_counts(db) == before


# --- Vehicles (D35, D65) and field rules ----------------------------------------------------------


async def test_bk13_the_same_plate_reuses_the_customers_vehicle_and_updates_it(
    desk: Desk, db: Database
) -> None:
    customer = await new_customer(db)
    first = desk.booking_body()
    first["vehicle"] = vehicle("LEA-1234", color="Silver", mileage_km=50_000)
    one = await desk.wizard(first, headers=customer.headers)
    second = desk.booking_body()
    second["vehicle"] = vehicle("lea 1234", make="Honda", model="Civic Reborn", year=2017)
    two = await desk.wizard(second, headers=customer.headers)
    assert one.status_code == two.status_code == 201
    vehicle_one, vehicle_two = one.json()["booking"]["vehicle"], two.json()["booking"]["vehicle"]
    assert vehicle_one["id"] == vehicle_two["id"]
    assert vehicle_two["registration_number"] == "lea 1234"
    assert (vehicle_two["model"], vehicle_two["year"]) == ("Civic Reborn", 2017)
    assert (vehicle_two["color"], vehicle_two["mileage_km"]) == ("Silver", 50_000)  # kept
    other = await new_customer(db, full_name="Kamran")
    theirs = await desk.wizard(desk.booking_body(registration="LEA1234"), headers=other.headers)
    assert theirs.json()["booking"]["vehicle"]["id"] != vehicle_one["id"]
    async with db.sessionmaker() as session:
        keys = (await session.execute(select(Vehicle.registration_key))).scalars().all()
    assert sorted(keys) == ["LEA1234", "LEA1234"]  # one per customer
    vehicles = await desk.get(customer.user_id, "/api/v1/me/vehicles")
    assert [item["id"] for item in vehicles["items"]] == [vehicle_one["id"]]


async def test_bk28_the_mileage_is_snapshotted_on_each_booking(desk: Desk, db: Database) -> None:
    customer = await new_customer(db)
    first = desk.booking_body()
    first["vehicle"] = vehicle(mileage_km=50_000)
    second = desk.booking_body()
    second["vehicle"] = vehicle(mileage_km=52_000)
    third = desk.booking_body()  # no mileage this time
    ids = []
    for body in (first, second, third):
        response = await desk.wizard(body, headers=customer.headers)
        assert response.status_code == 201, response.text
        ids.append(response.json()["booking"]["id"])
    mileages = [(await booking_row(db, booking_id)).mileage_km for booking_id in ids]
    assert mileages == [50_000, 52_000, None]
    detail = await desk.my_detail(customer, ids[2])
    assert detail["mileage_km"] is None
    assert detail["vehicle"]["mileage_km"] == 52_000  # the vehicle keeps its last value


async def test_the_registration_key_always_agrees_with_the_database(
    desk: Desk, db: Database
) -> None:
    customer = await new_customer(db)
    for number in ("lea-12 34", "LEA\t1234", "  ab-9  "):
        body = desk.booking_body()
        body["vehicle"] = vehicle(number)
        response = await desk.wizard(body, headers=customer.headers)
        assert response.status_code == 201, (number, response.text)
    async with db.sessionmaker() as session:
        mismatches = (
            await session.execute(
                text(
                    "SELECT count(*) FROM vehicles WHERE registration_key <> "
                    "upper(regexp_replace(registration_number, '[[:space:]-]', '', 'g'))"
                )
            )
        ).scalar_one()
    assert mismatches == 0
    for bad in ("LEA_1234", "LÉA-1234", "LEA\u20031234", "-"):
        body = desk.booking_body()
        body["vehicle"] = vehicle(bad)
        response = await desk.wizard(body, headers=customer.headers)
        codes = field_codes(problem(response, 422, "VALIDATION_ERROR"))
        assert codes[0][0] == "vehicle.registration_number", bad


async def test_bk20_vehicle_fields_and_the_year_up_to_next_year(desk: Desk, db: Database) -> None:
    customer = await new_customer(db)
    body = desk.booking_body()
    body["vehicle"] = {"registration_number": "LEA-1234", "make": "Honda"}
    response = await desk.wizard(body, headers=customer.headers)
    assert set(field_codes(problem(response, 422, "VALIDATION_ERROR"))) == {
        ("vehicle.model", "missing"),
        ("vehicle.year", "missing"),
    }
    next_year = desk.booking_body()
    next_year["vehicle"] = vehicle(year=2027)  # the clock says 2026
    assert (await desk.wizard(next_year, headers=customer.headers)).status_code == 201
    too_new = desk.booking_body()
    too_new["vehicle"] = vehicle(year=2028)
    response = await desk.wizard(too_new, headers=customer.headers)
    found = problem(response, 422, "VALIDATION_ERROR")
    assert found["errors"] == [
        {
            "field": "vehicle.year",
            "message": "Year must be between 1900 and 2027.",
            "code": "value_error",
        }
    ]


async def test_anonymous_callers_must_send_name_email_and_password(
    desk: Desk, db: Database
) -> None:
    before = await table_counts(db)
    missing = await desk.wizard(desk.booking_body())
    assert field_codes(problem(missing, 422, "VALIDATION_ERROR")) == [
        ("customer.full_name", "missing"),
        ("customer.email", "missing"),
        ("customer.password", "missing"),
    ]
    partial = desk.booking_body(customer={"full_name": "Ahmed", "email": unique_email()})
    partial["vehicle"] = vehicle(year=2030)  # reported together with the account field
    response = await desk.wizard(partial)
    assert field_codes(problem(response, 422, "VALIDATION_ERROR")) == [
        ("customer.password", "missing"),
        ("vehicle.year", "value_error"),
    ]
    assert await table_counts(db) == before


@pytest.mark.parametrize("field", ["status", "customer_user_id", "reference", "version"])
async def test_sec17_server_owned_booking_fields_are_refused(
    desk: Desk, db: Database, field: str
) -> None:
    before = await table_counts(db)
    response = await desk.wizard(anonymous(desk, **{field: "COMPLETED"}))
    assert (field, "extra_forbidden") in field_codes(problem(response, 422, "VALIDATION_ERROR"))
    assert await table_counts(db) == before


async def test_text_the_database_cannot_store_is_422_and_rolls_everything_back(
    desk: Desk, db: Database
) -> None:
    before = await table_counts(db)
    response = await desk.wizard(anonymous(desk, customer_notes="Light\u0000on"))
    problem(response, 422, "VALIDATION_ERROR")
    assert await table_counts(db) == before  # the case-B account is rolled back too (SEC-18)


# --- References (§7.3) ----------------------------------------------------------------------------


async def test_bk14_references_are_crockford_codes_never_in_the_seed_range(
    desk: Desk, db: Database
) -> None:
    references = {(await desk.book()).reference for _ in range(5)}
    assert len(references) == 5
    for reference in references:
        assert reference.startswith("BF-")
        assert not reference.startswith("BF-SEED")
        assert len(reference) == 9


async def test_a_reference_collision_is_retried_with_a_new_code(
    desk: Desk, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    taken = (await desk.book()).reference
    codes = iter([taken, taken, "BF-7K2M9Q"])
    monkeypatch.setattr(bookings_service, "new_booking_reference", lambda: next(codes))
    journey = await desk.book()
    assert journey.reference == "BF-7K2M9Q"
    assert await count_rows(db, "bookings") == 2


async def test_five_collisions_in_a_row_are_a_500_and_nothing_is_kept(
    desk: Desk, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    taken = (await desk.book()).reference
    monkeypatch.setattr(bookings_service, "new_booking_reference", lambda: taken)
    before = await table_counts(db)
    response = await desk.wizard(anonymous(desk))
    problem(response, 500, "INTERNAL_ERROR")
    assert await table_counts(db) == before


async def test_the_seed_passes_a_reserved_reference_internally(
    desk: Desk, world: World, db: Database
) -> None:
    customer = await new_customer(db)
    caller = CurrentUser(id=customer.user_id, email=customer.email, full_name=customer.full_name)
    data = BookingCreate.model_validate(desk.booking_body())
    async with unit_of_work(db) as uow:
        created = await bookings_service.create_booking(
            uow, caller=caller, data=data, reference="BF-SEED07"
        )
    assert created.booking.reference == "BF-SEED07"
    again = BookingCreate.model_validate(desk.booking_body())
    with pytest.raises(Conflict, match="BF-SEED07 already exists"):
        async with unit_of_work(db) as uow:
            await bookings_service.create_booking(
                uow, caller=caller, data=again, reference="BF-SEED07"
            )
    for invalid in ("BF-7K2M9Q", "BF-SEED7", "SEED07"):
        with pytest.raises(ValueError, match="reserved BF-SEED reference"):
            async with unit_of_work(db) as uow:
                await bookings_service.create_booking(
                    uow, caller=caller, data=again, reference=invalid
                )
    assert await count_rows(db, "bookings") == 1


# --- The CREATE event contract (`modules/bookings.md` §8) -----------------------------------------


async def test_create_publishes_booking_action_applied(
    desk: Desk, world: World, db: Database, published: list[Event], clock: SimulatedClock
) -> None:
    journey = await desk.book(slot=FRIDAY_1000)
    (event,) = published
    assert event == BookingActionApplied(
        occurred_at=clock.now(),
        shop_id=world.shop_id,
        booking_id=uuid.UUID(journey.id),
        reference=journey.reference,
        action=BookingAction.CREATE,
        from_status=None,
        to_status=BookingStatus.PENDING,
        version=1,
        actor_user_id=journey.customer.user_id,
        actor_role=ActorRole.CUSTOMER,
        customer_user_id=journey.customer.user_id,
        technician_user_id=None,
        parts_person_user_id=None,
        qc_inspector_user_id=None,
        note=None,
        metadata={},
    )


# --- Rate limits (D69; BK-32, SEC-27 wizard half) -------------------------------------------------


async def test_bk32_anonymous_bookings_are_limited_per_ip(desk: Desk, db: Database) -> None:
    past = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)  # cheap requests: 422 after the limiter
    ip = {"X-Real-IP": "203.0.113.7"}
    for _ in range(20):
        response = await desk.api.post(
            "/api/v1/bookings", json=anonymous(desk, slot=past), headers=ip
        )
        assert response.status_code == 422
    before = await table_counts(db)
    blocked = await desk.api.post("/api/v1/bookings", json=anonymous(desk), headers=ip)
    problem(blocked, 429, "RATE_LIMITED")
    assert int(blocked.headers["Retry-After"]) >= 1
    assert await table_counts(db) == before
    other_ip = await desk.api.post(
        "/api/v1/bookings", json=anonymous(desk), headers={"X-Real-IP": "203.0.113.8"}
    )
    assert other_ip.status_code == 201
    customer = await new_customer(db)
    with_session = await desk.api.post(
        "/api/v1/bookings", json=desk.booking_body(), headers={**ip, **customer.headers}
    )
    assert with_session.status_code == 201  # a session is limited per user, not per IP


async def test_bk32_bookings_with_a_session_are_limited_per_user(desk: Desk, db: Database) -> None:
    customer = await new_customer(db)
    past = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)
    for _ in range(30):
        response = await desk.wizard(desk.booking_body(slot=past), headers=customer.headers)
        assert response.status_code == 422
    before = await table_counts(db)
    blocked = await desk.wizard(desk.booking_body(slot=FRIDAY_1000), headers=customer.headers)
    problem(blocked, 429, "RATE_LIMITED")
    assert int(blocked.headers["Retry-After"]) >= 1
    assert await table_counts(db) == before
    assert await slot_count(db, desk.world.shop_id, FRIDAY_1000) is None
    other = await new_customer(db, full_name="Zainab")
    assert (await desk.wizard(desk.booking_body(), headers=other.headers)).status_code == 201


async def test_sec27_wizard_failures_count_for_the_account_and_block_it(
    desk: Desk, db: Database
) -> None:
    user = await make_user(db)
    for index in range(5):
        body = anonymous(desk, user.email)
        body["customer"]["password"] = f"wrong-password-{index}"
        headers = {"X-Real-IP": f"198.51.100.{index}"}  # the account limit ignores the IP
        response = await desk.api.post("/api/v1/bookings", json=body, headers=headers)
        problem(response, 409, "EMAIL_ALREADY_REGISTERED")
    before = await table_counts(db)
    right = await desk.wizard(anonymous(desk, user.email))  # even the right password
    problem(right, 429, "RATE_LIMITED")
    assert int(right.headers["Retry-After"]) >= 1
    login = await desk.api.post(
        "/api/v1/auth/login", json={"email": user.email, "password": TEST_PASSWORD}
    )
    problem(login, 429, "RATE_LIMITED")  # one limiter for login and the wizard
    assert await table_counts(db) == before


async def test_case_b_applies_the_d10_password_policy(desk: Desk, db: Database) -> None:
    body = anonymous(desk)
    body["customer"]["password"] = "tiny-pw"
    response = await desk.wizard(body)
    assert ("customer.password", "string_too_short") in field_codes(
        problem(response, 422, "VALIDATION_ERROR")
    )
    assert "tiny-pw" not in response.text  # the password is never echoed (spec 04)

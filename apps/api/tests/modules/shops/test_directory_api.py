"""The public directory, cities and shop pages by slug (spec 03 §4.5; D64, D68).

Covers BK-16, BK-26 (directory half; booking creation's 404 is `get_bookable_shop`), BK-27 (shop
page by slug), SHP-08, the public half of SEC-04 and API-05's limits.
"""

from decimal import Decimal

import httpx
import pytest

from app.core.database import Database
from app.modules.shops import service as shops_service
from app.modules.shops.schemas import ServiceUpdate
from tests.assertions import assert_problem
from tests.modules.identity.builders import bearer, unit_of_work
from tests.modules.shops.builders import ShopCtx, make_services, make_shop, week

pytestmark = pytest.mark.db

DIRECTORY = "/api/v1/public/shops"
CITIES = "/api/v1/public/cities"


async def deactivate(db: Database, ctx: ShopCtx, service_id: object) -> None:
    async with unit_of_work(db) as uow:
        await shops_service.update_service(
            uow,
            shop_id=ctx.id,
            actor_user_id=ctx.owner.id,
            service_id=service_id,  # type: ignore[arg-type]
            data=ServiceUpdate(is_active=False),
        )


async def names(client: httpx.AsyncClient, **params: object) -> list[str]:
    response = await client.get(DIRECTORY, params=params)
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


async def test_bk16_the_directory_lists_listed_shops_with_an_active_service(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    lahore = await make_shop(db, name="Lahore Auto Care", city="Lahore")
    await make_services(db, lahore, ["Oil change", "brake failure", "Check engine light"])
    async with unit_of_work(db) as uow:
        await shops_service.set_rating(uow, shop_id=lahore.id, rating=Decimal("4.7"))
    karachi = await make_shop(db, name="Clifton Car Clinic", city="Karachi")
    await make_services(db, karachi, ["AC service"])
    unlisted = await make_shop(db, name="Hidden Garage", listed=False)
    await make_services(db, unlisted, ["Oil change"])
    await make_shop(db, name="Empty Garage")  # no services: not bookable, not listed (D64)

    response = await db_client.get(DIRECTORY)
    page = response.json()
    assert (page["total"], page["limit"], page["offset"]) == (2, 20, 0)
    assert [item["name"] for item in page["items"]] == ["Clifton Car Clinic", "Lahore Auto Care"]
    item = page["items"][1]
    assert item == {
        "id": str(lahore.id),
        "slug": "lahore-auto-care",
        "name": "Lahore Auto Care",
        "city": "Lahore",
        "logo_url": None,
        "rating": 4.7,
        "services": [
            {"id": item["services"][0]["id"], "name": "brake failure"},
            {"id": item["services"][1]["id"], "name": "Check engine light"},
            {"id": item["services"][2]["id"], "name": "Oil change"},
        ],
        "services_count": 3,
    }
    assert page["items"][0]["rating"] is None  # shown as "New" (D56)


async def test_bk16_city_filter_and_text_search(db_client: httpx.AsyncClient, db: Database) -> None:
    for name, city, services in (
        ("Lahore Auto Care", "Lahore", ["Oil change"]),
        ("Raza Auto Works", "lahore", ["Wheel alignment"]),
        ("Clifton Car Clinic", "Karachi", ["AC service"]),
        ("50% Off Garage", "Multan", ["Tire_rotation"]),
    ):
        ctx = await make_shop(db, name=name, city=city)
        await make_services(db, ctx, services)
    assert await names(db_client, city="LAHORE") == ["Lahore Auto Care", "Raza Auto Works"]
    assert await names(db_client, city="  Karachi ") == ["Clifton Car Clinic"]
    assert await names(db_client, city="Lah") == []  # exact match only
    assert await names(db_client, q="auto") == ["Lahore Auto Care", "Raza Auto Works"]
    assert await names(db_client, q="karach") == ["Clifton Car Clinic"]  # matches the city
    assert await names(db_client, q="ALIGN") == ["Raza Auto Works"]  # matches a service
    assert await names(db_client, q="%") == ["50% Off Garage"]  # wildcards are literal
    assert await names(db_client, q="e_r") == ["50% Off Garage"]
    assert await names(db_client, q="l_c") == []  # unescaped, `_` would match "Oil change"
    assert await names(db_client, q="o'brien") == []  # quotes are plain text (SEC-29)
    assert await names(db_client, q="auto", city="lahore") == [
        "Lahore Auto Care",
        "Raza Auto Works",
    ]
    assert await names(db_client, q="", city="") == [
        "50% Off Garage",
        "Clifton Car Clinic",
        "Lahore Auto Care",
        "Raza Auto Works",
    ]
    second = await db_client.get(DIRECTORY, params={"limit": 2, "offset": 2})
    assert [item["name"] for item in second.json()["items"]] == [
        "Lahore Auto Care",
        "Raza Auto Works",
    ]
    assert second.json()["total"] == 4


async def test_api05_directory_query_limits(db_client: httpx.AsyncClient) -> None:
    for params in (
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"q": "x" * 101},
        {"city": "x" * 81},
    ):
        assert_problem(await db_client.get(DIRECTORY, params=params), 422, "VALIDATION_ERROR")
    assert (await db_client.get(DIRECTORY, params={"limit": 100})).status_code == 200


async def test_shp08_cities_of_directory_shops_only(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    for name, city, listed, with_service in (
        ("Lahore Auto Care", "Lahore", True, True),
        ("Raza Auto Works", "LAHORE", True, True),
        ("Clifton Car Clinic", "Karachi", True, True),
        ("Margalla Motor Works", "Islamabad", False, True),  # unlisted
        ("Pindi Auto Garage", "Rawalpindi", True, False),  # no service
    ):
        ctx = await make_shop(db, name=name, city=city, listed=listed)
        if with_service:
            await make_services(db, ctx, ["Oil change"])
    response = await db_client.get(CITIES)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert items[0] == "Karachi"
    assert items[1] in {"Lahore", "LAHORE"}  # one spelling per case-insensitive city


async def test_bk26_a_shop_without_an_active_service(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db, name="Lyallpur Motors", city="Faisalabad")
    (service,) = await make_services(db, ctx, ["Oil change"])
    assert await names(db_client) == ["Lyallpur Motors"]

    await deactivate(db, ctx, service.id)  # its last active service
    assert await names(db_client) == []
    assert (await db_client.get(CITIES)).json()["items"] == []
    detail = await db_client.get(f"{DIRECTORY}/{ctx.slug}")
    assert detail.status_code == 200
    assert (detail.json()["services"], detail.json()["is_bookable"]) == ([], False)
    async with db.sessionmaker() as session:
        assert await shops_service.get_bookable_shop(session, shop_id=ctx.id) is None

    await make_services(db, ctx, ["Battery replacement"])
    assert await names(db_client) == ["Lyallpur Motors"]  # back once a service is active
    async with db.sessionmaker() as session:
        bookable = await shops_service.get_bookable_shop(session, shop_id=ctx.id)
    assert bookable is not None
    assert bookable.slug == ctx.slug


async def test_bk27_public_shop_page_by_slug(db_client: httpx.AsyncClient, db: Database) -> None:
    hours = week("09:00", "18:00")
    hours[6] = {"weekday": 6, "is_closed": False, "opens_at": "10:00", "closes_at": "14:00"}
    ctx = await make_shop(db, name="Pindi Auto Garage", city="Rawalpindi", hours=hours)
    oil, ac = await make_services(db, ctx, ["Oil change", "AC service"])
    await deactivate(db, ctx, ac.id)
    response = await db_client.get(f"{DIRECTORY}/pindi-auto-garage")
    assert response.status_code == 200
    detail = response.json()
    assert set(detail) == {
        "id",
        "slug",
        "name",
        "address",
        "city",
        "phone",
        "logo_url",
        "rating",
        "timezone",
        "slot_duration_minutes",
        "working_hours",
        "services",
        "is_bookable",
    }
    assert (detail["slug"], detail["timezone"], detail["slot_duration_minutes"]) == (
        "pindi-auto-garage",
        "Asia/Karachi",
        60,
    )
    assert detail["working_hours"][6] == {
        "weekday": 6,
        "is_closed": False,
        "opens_at": "10:00",
        "closes_at": "14:00",
    }
    assert [service["id"] for service in detail["services"]] == [str(oil.id)]  # active only
    assert detail["services"][0]["base_price"] == "2000.00"
    assert detail["is_bookable"] is True
    assert "slot_capacity" not in detail  # staff data stays in ShopRead


async def test_bk27_unknown_unlisted_or_uuid_slugs_are_404(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    hidden = await make_shop(db, name="Hidden Garage", listed=False)
    await make_services(db, hidden)
    for slug in ("no-such-shop", hidden.slug, str(hidden.id), "Hidden-Garage"):
        response = await db_client.get(f"{DIRECTORY}/{slug}")
        problem = assert_problem(response, 404, "NOT_FOUND")
        assert problem["detail"] == "The requested resource was not found."
    async with db.sessionmaker() as session:
        assert await shops_service.get_listed_shop(session, shop_slug=hidden.slug) is None


async def test_sec04_public_routes_are_anonymous_never_cached_and_ignore_credentials(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    await make_services(db, ctx)
    for path in (DIRECTORY, CITIES, f"{DIRECTORY}/{ctx.slug}"):
        anonymous = await db_client.get(path)
        assert anonymous.status_code == 200
        assert anonymous.headers["cache-control"] == "no-store"  # D61, public included
        garbage = await db_client.get(path, headers={"Authorization": "Bearer not-a-jwt"})
        assert garbage.status_code == 200  # public routes never read credentials
        logged_in = await db_client.get(path, headers=bearer(ctx.owner.id))
        assert logged_in.json() == anonymous.json()

"""The service catalogue over HTTP (spec 03 §4.9, `modules/shops.md` §7.7; SHP-05, D34, D41)."""

import uuid

import httpx
import pytest

from app.core.database import Database
from app.shared.clock import SimulatedClock
from app.shared.enums import MembershipRole
from tests.assertions import assert_problem
from tests.modules.identity.builders import bearer, field_errors
from tests.modules.shops.builders import ShopCtx, add_member, make_services, make_shop

pytestmark = pytest.mark.db


def services_url(ctx: ShopCtx, suffix: str = "") -> str:
    return f"/api/v1/shops/{ctx.id}/services{suffix}"


async def create(client: httpx.AsyncClient, ctx: ShopCtx, **body: object) -> httpx.Response:
    payload: dict[str, object] = {"estimated_duration_minutes": 60}
    payload.update(body)
    return await client.post(services_url(ctx), json=payload, headers=bearer(ctx.owner.id))


async def test_create_and_list_services(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    oil = await create(
        db_client,
        ctx,
        name="  Oil change ",
        description="Drain and refill engine oil.",
        estimated_duration_minutes=45,
        base_price="1000",
    )
    assert oil.status_code == 201, oil.text
    assert oil.json() == {
        "id": oil.json()["id"],
        "name": "Oil change",
        "description": "Drain and refill engine oil.",
        "estimated_duration_minutes": 45,
        "base_price": "1000.00",  # whole rupees, two decimals (D41)
        "is_active": True,
        "created_at": "2026-10-14T04:00:00Z",
        "updated_at": "2026-10-14T04:00:00Z",
    }
    suspension = await create(
        db_client, ctx, name="suspension repair", description="  ", is_active=None, base_price=None
    )
    assert suspension.status_code == 201  # `null` optional fields take their defaults (§1.5)
    assert (
        suspension.json()["base_price"],
        suspension.json()["description"],
        suspension.json()["is_active"],
    ) == (None, None, True)
    await create(db_client, ctx, name="AC service", is_active=False, base_price=4500)

    listed = await db_client.get(services_url(ctx), headers=bearer(ctx.owner.id))
    assert [item["name"] for item in listed.json()["items"]] == ["Oil change", "suspension repair"]
    assert listed.json()["total"] == 2
    everything = await db_client.get(
        services_url(ctx), params={"include_inactive": "true"}, headers=bearer(ctx.owner.id)
    )
    assert [item["name"] for item in everything.json()["items"]] == [
        "AC service",
        "Oil change",
        "suspension repair",
    ]
    window = await db_client.get(
        services_url(ctx),
        params={"include_inactive": "true", "limit": 1, "offset": 1},
        headers=bearer(ctx.owner.id),
    )
    assert [item["name"] for item in window.json()["items"]] == ["Oil change"]
    assert (window.json()["total"], window.json()["limit"]) == (3, 1)


async def test_every_member_reads_the_catalogue(db_client: httpx.AsyncClient, db: Database) -> None:
    ctx = await make_shop(db)
    await make_services(db, ctx)
    for role in (MembershipRole.TECHNICIAN, MembershipRole.QC_INSPECTOR):
        member = await add_member(db, ctx, role)
        response = await db_client.get(services_url(ctx), headers=bearer(member.id))
        assert response.json()["total"] == 2


async def test_shp05_duplicate_active_names(db_client: httpx.AsyncClient, db: Database) -> None:
    ctx = await make_shop(db)
    other = await make_shop(db)
    original = await create(db_client, ctx, name="Oil change")
    duplicate = await create(db_client, ctx, name="OIL CHANGE")
    problem = assert_problem(duplicate, 409, "CONFLICT")
    assert problem["detail"] == "This shop already has an active service with this name."
    inactive_copy = await create(db_client, ctx, name="oil change", is_active=False)
    assert inactive_copy.status_code == 201  # a deactivated duplicate is allowed
    reactivate = await db_client.patch(
        services_url(ctx, f"/{inactive_copy.json()['id']}"),
        json={"is_active": True},
        headers=bearer(ctx.owner.id),
    )
    assert_problem(reactivate, 409, "CONFLICT")
    elsewhere = await create(db_client, other, name="Oil change")
    assert elsewhere.status_code == 201  # another shop may reuse the name

    rename_into = await create(db_client, ctx, name="Brake failure")
    renamed = await db_client.patch(
        services_url(ctx, f"/{rename_into.json()['id']}"),
        json={"name": "oil Change"},
        headers=bearer(ctx.owner.id),
    )
    assert_problem(renamed, 409, "CONFLICT")
    own_case = await db_client.patch(
        services_url(ctx, f"/{original.json()['id']}"),
        json={"name": "Oil Change"},
        headers=bearer(ctx.owner.id),
    )
    assert own_case.status_code == 200  # renaming itself is not a duplicate
    assert own_case.json()["name"] == "Oil Change"


async def test_update_service(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    created = await create(
        db_client, ctx, name="Wheel alignment", description="Four wheels.", base_price=2000
    )
    url = services_url(ctx, f"/{created.json()['id']}")
    clock.set(clock.now().replace(hour=6))
    updated = await db_client.patch(
        url,
        json={"estimated_duration_minutes": 45, "base_price": None, "description": None},
        headers=bearer(ctx.owner.id),
    )
    assert updated.status_code == 200
    body = updated.json()
    assert (body["estimated_duration_minutes"], body["base_price"], body["description"]) == (
        45,
        None,
        None,
    )
    assert body["updated_at"] == "2026-10-14T06:00:00Z"
    deactivated = await db_client.patch(
        url, json={"is_active": False}, headers=bearer(ctx.owner.id)
    )
    assert deactivated.json()["is_active"] is False
    listed = await db_client.get(services_url(ctx), headers=bearer(ctx.owner.id))
    assert listed.json()["items"] == []  # hidden from the default list (and the directory)
    clock.set(clock.now().replace(hour=7))
    unchanged = await db_client.patch(url, json={"is_active": False}, headers=bearer(ctx.owner.id))
    assert unchanged.json()["updated_at"] == "2026-10-14T06:00:00Z"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"name": ""}, [("name", "string_too_short")]),
        ({"name": "x" * 121}, [("name", "string_too_long")]),
        ({"description": "x" * 1001}, [("description", "string_too_long")]),
        ({"estimated_duration_minutes": 4}, [("estimated_duration_minutes", "greater_than_equal")]),
        ({"base_price": "99.50"}, [("base_price", "not_whole_rupees")]),
        ({"base_price": 12.5}, [("base_price", "not_whole_rupees")]),
        ({"base_price": -1}, [("base_price", "greater_than_equal")]),
        ({"shop_id": str(uuid.uuid4())}, [("shop_id", "extra_forbidden")]),
    ],
)
async def test_service_validation(
    db_client: httpx.AsyncClient,
    db: Database,
    body: dict[str, object],
    expected: list[tuple[str, str]],
) -> None:
    ctx = await make_shop(db)
    payload: dict[str, object] = {"name": "Valid"}
    payload.update(body)
    response = await create(db_client, ctx, **payload)
    assert field_errors(assert_problem(response, 422, "VALIDATION_ERROR")) == expected


async def test_another_shops_service_is_404(db_client: httpx.AsyncClient, db: Database) -> None:
    ctx = await make_shop(db)
    other = await make_shop(db)
    (theirs,) = await make_services(db, other, ["Battery replacement"])
    for service_id in (theirs.id, uuid.uuid4()):
        response = await db_client.patch(
            services_url(ctx, f"/{service_id}"),
            json={"is_active": False},
            headers=bearer(ctx.owner.id),
        )
        assert_problem(response, 404, "NOT_FOUND")


async def test_only_the_owner_manages_the_catalogue(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    (service,) = await make_services(db, ctx, ["Tire rotation"])
    for role in (
        MembershipRole.SERVICE_ADVISOR,
        MembershipRole.TECHNICIAN,
        MembershipRole.PARTS_PERSON,
        MembershipRole.QC_INSPECTOR,
    ):
        member = await add_member(db, ctx, role)
        create_response = await db_client.post(
            services_url(ctx),
            json={"name": "Nope", "estimated_duration_minutes": 30},
            headers=bearer(member.id),
        )
        assert_problem(create_response, 403, "FORBIDDEN")
        patch_response = await db_client.patch(
            services_url(ctx, f"/{service.id}"), json={"name": "Nope"}, headers=bearer(member.id)
        )
        assert_problem(patch_response, 403, "FORBIDDEN")

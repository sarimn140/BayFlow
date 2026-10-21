"""Parts catalogue over HTTP (spec 03 §4.10; D44, D45): INV-15, INV-17, INV-22, INV-23, INV-31,
SEC-03, SEC-04, SEC-06 (catalogue half), SEC-17 and the QC half of INV-32."""

from datetime import timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.core.database import Database
from app.shared.clock import SimulatedClock
from tests.modules.inventory.support import (
    Team,
    World,
    assert_ledger_invariants,
    assert_problem,
    bearer,
    field_codes,
    new_part,
    url,
)

pytestmark = pytest.mark.db


async def list_parts(api: httpx.AsyncClient, team: Team, **params: Any) -> dict[str, Any]:
    response = await api.get(url(team.id, "/parts"), params=params, headers=bearer(team.parts))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --- Create (INV-17, INV-22, INV-23, SEC-17) -----------------------------------------------------


async def test_inv22_inventory_table_fields(
    api: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    created = await new_part(api, world.a, " oil-flt-01 ", name="Oil filter", reorder_level=2)
    assert created == {
        "id": created["id"],
        "sku": "OIL-FLT-01",
        "name": "Oil filter",
        "unit_cost": "900.00",
        "is_active": True,
        "on_hand": 0,
        "reserved": 0,
        "available": 0,
        "reorder_level": 2,
        "stock_state": "OUT",
        "on_order": 0,
        "created_at": "2026-10-14T04:00:00Z",
        "updated_at": "2026-10-14T04:00:00Z",
    }
    page = await list_parts(api, world.a)
    assert page == {"items": [created], "total": 1, "limit": 20, "offset": 0}


async def test_inv23_new_parts_start_at_zero_whoever_creates_them(
    api: httpx.AsyncClient, world: World, db: Database
) -> None:
    for creator, sku in ((world.a.owner, "OWNER-PART"), (world.a.parts, "PP-PART")):
        response = await api.post(
            url(world.a.id, "/parts"),
            json={"sku": sku, "name": "Spark plug", "unit_cost": 1800},
            headers=bearer(creator),
        )
        assert response.status_code == 201, response.text
        assert (response.json()["on_hand"], response.json()["reserved"]) == (0, 0)
    await assert_ledger_invariants(db)


@pytest.mark.parametrize("field", ["on_hand", "reserved", "available", "shop_id", "stock_state"])
async def test_sec17_stock_and_tenant_fields_are_refused_on_create(
    api: httpx.AsyncClient, world: World, field: str
) -> None:
    response = await api.post(
        url(world.a.id, "/parts"),
        json={"sku": "X1", "name": "X", "unit_cost": "100", field: 5},
        headers=bearer(world.a.owner),
    )
    assert field_codes(response) == [(field, "extra_forbidden")]
    assert (await list_parts(api, world.a, include_inactive=True))["total"] == 0


async def test_sec17_stock_fields_are_refused_on_update(
    api: httpx.AsyncClient, world: World
) -> None:
    part = await new_part(api, world.a, "X1", stock=3)
    response = await api.patch(
        url(world.a.id, f"/parts/{part['id']}"),
        json={"on_hand": 50, "reserved": 0},
        headers=bearer(world.a.parts),
    )
    assert sorted(field_codes(response)) == [
        ("on_hand", "extra_forbidden"),
        ("reserved", "extra_forbidden"),
    ]
    assert (await list_parts(api, world.a))["items"][0]["on_hand"] == 3


async def test_inv17_duplicate_sku_in_one_shop_is_conflict_but_another_shop_may_reuse_it(
    api: httpx.AsyncClient, world: World
) -> None:
    await new_part(api, world.a, "IGN-COIL-01")
    duplicate = await api.post(
        url(world.a.id, "/parts"),
        json={"sku": "ign-coil-01", "name": "Another coil", "unit_cost": "6500"},
        headers=bearer(world.a.owner),
    )
    body = assert_problem(duplicate, 409, "CONFLICT")
    assert "IGN-COIL-01" in body["detail"]
    other_shop = await new_part(api, world.b, "IGN-COIL-01")
    assert other_shop["sku"] == "IGN-COIL-01"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"sku": "", "name": "x", "unit_cost": "1"}, [("sku", "string_too_short")]),
        ({"sku": "A" * 41, "name": "x", "unit_cost": "1"}, [("sku", "string_too_long")]),
        ({"sku": "BAD SKU", "name": "x", "unit_cost": "1"}, [("sku", "string_pattern_mismatch")]),
        ({"sku": "OK", "name": " ", "unit_cost": "1"}, [("name", "string_too_short")]),
        ({"sku": "OK", "name": "x" * 121, "unit_cost": "1"}, [("name", "string_too_long")]),
        ({"sku": "OK", "name": "x", "unit_cost": "900.50"}, [("unit_cost", "not_whole_rupees")]),
        ({"sku": "OK", "name": "x", "unit_cost": -1}, [("unit_cost", "greater_than_equal")]),
        (
            {"sku": "OK", "name": "x", "unit_cost": "1", "reorder_level": 100_001},
            [("reorder_level", "less_than_equal")],
        ),
        ({"sku": "OK", "name": "x"}, [("unit_cost", "missing")]),
    ],
)
async def test_create_part_validation(
    api: httpx.AsyncClient, world: World, payload: dict[str, Any], expected: list[tuple[str, str]]
) -> None:
    response = await api.post(
        url(world.a.id, "/parts"), json=payload, headers=bearer(world.a.parts)
    )
    assert field_codes(response) == expected


# --- Update (INV-17) ------------------------------------------------------------------------------


async def test_inv17_owner_and_parts_person_edit_the_catalogue(
    api: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    part = await new_part(api, world.a, "OIL-4L", name="Engine oil", unit_cost="5200", stock=8)
    clock.advance(timedelta(minutes=5))
    by_owner = await api.patch(
        url(world.a.id, f"/parts/{part['id']}"),
        json={"name": " Engine oil 4 L ", "unit_cost": "5300"},
        headers=bearer(world.a.owner),
    )
    assert by_owner.status_code == 200, by_owner.text
    edited = by_owner.json()
    assert (edited["name"], edited["unit_cost"], edited["on_hand"]) == (
        "Engine oil 4 L",
        "5300.00",
        8,
    )
    assert edited["updated_at"] == "2026-10-14T04:05:00Z"
    assert edited["created_at"] == part["created_at"]
    by_parts = await api.patch(
        url(world.a.id, f"/parts/{part['id']}"),
        json={"sku": "oil-4l-a", "reorder_level": 9},
        headers=bearer(world.a.parts),
    )
    assert by_parts.status_code == 200
    assert (by_parts.json()["sku"], by_parts.json()["stock_state"]) == ("OIL-4L-A", "LOW")


async def test_update_to_a_taken_sku_is_conflict_and_keeping_the_own_sku_is_fine(
    api: httpx.AsyncClient, world: World
) -> None:
    first = await new_part(api, world.a, "AAA")
    await new_part(api, world.a, "BBB")
    taken = await api.patch(
        url(world.a.id, f"/parts/{first['id']}"), json={"sku": "bbb"}, headers=bearer(world.a.parts)
    )
    assert_problem(taken, 409, "CONFLICT")
    same = await api.patch(
        url(world.a.id, f"/parts/{first['id']}"), json={"sku": "aaa"}, headers=bearer(world.a.parts)
    )
    assert same.status_code == 200
    assert same.json()["sku"] == "AAA"


async def test_update_needs_a_field_and_refuses_null(api: httpx.AsyncClient, world: World) -> None:
    part = await new_part(api, world.a, "AAA")
    path = url(world.a.id, f"/parts/{part['id']}")
    assert field_codes(await api.patch(path, json={}, headers=bearer(world.a.parts))) == [
        ("", "value_error")
    ]
    assert field_codes(
        await api.patch(path, json={"sku": None}, headers=bearer(world.a.parts))
    ) == [("sku", "value_error")]


async def test_deactivated_parts_are_hidden_unless_asked_for(
    api: httpx.AsyncClient, world: World
) -> None:
    active = await new_part(api, world.a, "ACTIVE")
    retired = await new_part(api, world.a, "RETIRED")
    response = await api.patch(
        url(world.a.id, f"/parts/{retired['id']}"),
        json={"is_active": False},
        headers=bearer(world.a.owner),
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert [p["sku"] for p in (await list_parts(api, world.a))["items"]] == [active["sku"]]
    everything = await list_parts(api, world.a, include_inactive="true")
    assert [p["sku"] for p in everything["items"]] == ["ACTIVE", "RETIRED"]


async def test_update_of_an_unknown_or_other_shops_part_is_404(
    api: httpx.AsyncClient, world: World
) -> None:
    theirs = await new_part(api, world.b, "THEIRS")
    for part_id in (theirs["id"], str(uuid4())):
        response = await api.patch(
            url(world.a.id, f"/parts/{part_id}"),
            json={"name": "Mine now"},
            headers=bearer(world.a.parts),
        )
        assert_problem(response, 404, "NOT_FOUND")
    not_a_uuid = await api.patch(
        url(world.a.id, "/parts/not-a-uuid"), json={"name": "x"}, headers=bearer(world.a.parts)
    )
    assert field_codes(not_a_uuid) == [("path.part_id", "uuid_parsing")]
    assert (await list_parts(api, world.b))["items"][0]["name"] == "Part THEIRS"


# --- Roles and tenancy (SEC-03, SEC-04, SEC-06, INV-32) -----------------------------------------


async def test_sec06_only_owner_and_parts_person_edit_the_catalogue(
    api: httpx.AsyncClient, world: World
) -> None:
    part = await new_part(api, world.a, "AAA")
    for user in (world.a.advisor, world.a.technician, world.a.qc):
        create = await api.post(
            url(world.a.id, "/parts"),
            json={"sku": "NEW", "name": "x", "unit_cost": "1"},
            headers=bearer(user),
        )
        assert_problem(create, 403, "FORBIDDEN")
        update = await api.patch(
            url(world.a.id, f"/parts/{part['id']}"), json={"name": "x"}, headers=bearer(user)
        )
        assert_problem(update, 403, "FORBIDDEN")
    assert (await list_parts(api, world.a))["total"] == 1


async def test_inv32_parts_list_roles_and_qc_inspectors_get_403(
    api: httpx.AsyncClient, world: World
) -> None:
    await new_part(api, world.a, "AAA", stock=2)
    for user in (world.a.owner, world.a.advisor, world.a.technician, world.a.parts):
        response = await api.get(url(world.a.id, "/parts"), headers=bearer(user))
        assert response.status_code == 200, user.email
        assert response.json()["items"][0]["on_hand"] == 2
    qc = await api.get(url(world.a.id, "/parts"), headers=bearer(world.a.qc))
    assert_problem(qc, 403, "FORBIDDEN")


async def test_sec03_non_members_and_inactive_members_get_404(
    api: httpx.AsyncClient, world: World
) -> None:
    part = await new_part(api, world.a, "AAA")
    strangers = (world.customer, world.b.owner, world.b.parts, world.a.former_parts)
    for user in strangers:
        listed = await api.get(url(world.a.id, "/parts"), headers=bearer(user))
        assert_problem(listed, 404, "NOT_FOUND")
        created = await api.post(
            url(world.a.id, "/parts"),
            json={"sku": "Z", "name": "z", "unit_cost": "1"},
            headers=bearer(user),
        )
        assert_problem(created, 404, "NOT_FOUND")
        updated = await api.patch(
            url(world.a.id, f"/parts/{part['id']}"), json={"name": "z"}, headers=bearer(user)
        )
        assert_problem(updated, 404, "NOT_FOUND")
    unknown_shop = await api.get(url(uuid4(), "/parts"), headers=bearer(world.a.parts))
    assert_problem(unknown_shop, 404, "NOT_FOUND")


async def test_sec04_missing_or_bad_tokens_are_401(api: httpx.AsyncClient, world: World) -> None:
    for headers in ({}, {"Authorization": "Bearer not-a-jwt"}):
        response = await api.get(url(world.a.id, "/parts"), headers=headers)
        assert_problem(response, 401, "UNAUTHENTICATED")
        assert response.headers["www-authenticate"] == "Bearer"


async def test_a_member_with_a_forbidden_role_gets_403_before_body_validation(
    api: httpx.AsyncClient, world: World
) -> None:
    response = await api.post(url(world.a.id, "/parts"), json={}, headers=bearer(world.a.qc))
    assert_problem(response, 403, "FORBIDDEN")


# --- Stock state, on order and filters (INV-15, INV-31) -------------------------------------------


async def test_inv15_inv31_stock_state_and_on_order(api: httpx.AsyncClient, world: World) -> None:
    out_zero = await new_part(api, world.a, "OUT-ZERO", reorder_level=0)  # available 0, reorder 0
    out_low = await new_part(api, world.a, "OUT-LOW", reorder_level=5)  # available 0: OUT wins
    low = await new_part(api, world.a, "LOW", reorder_level=5, stock=5)
    ok = await new_part(api, world.a, "OK", reorder_level=5, stock=6)
    assert [p["stock_state"] for p in (out_zero, out_low, low, ok)] == ["OUT", "OUT", "LOW", "OK"]
    assert (low["available"], ok["available"]) == (5, 6)
    order = await api.post(
        url(world.a.id, "/purchase-orders"),
        json={
            "items": [
                {"part_id": out_low["id"], "quantity": 4},
                {"part_id": ok["id"], "quantity": 2},
            ]
        },
        headers=bearer(world.a.parts),
    )
    assert order.status_code == 201, order.text
    items = {p["sku"]: p for p in (await list_parts(api, world.a))["items"]}
    assert {sku: p["on_order"] for sku, p in items.items()} == {
        "LOW": 0,
        "OK": 2,
        "OUT-LOW": 4,
        "OUT-ZERO": 0,
    }
    receive = await api.post(
        url(world.a.id, f"/purchase-orders/{order.json()['id']}/receive"),
        json={"items": [{"item_id": item["id"], "quantity": 1} for item in order.json()["items"]]},
        headers=bearer(world.a.parts),
    )
    assert receive.status_code == 200, receive.text
    items = {p["sku"]: p for p in (await list_parts(api, world.a))["items"]}
    assert (items["OUT-LOW"]["on_order"], items["OUT-LOW"]["stock_state"]) == (3, "LOW")
    assert (items["OK"]["on_order"], items["OK"]["available"]) == (1, 7)


async def test_inv31_stock_state_filter_is_repeatable(api: httpx.AsyncClient, world: World) -> None:
    await new_part(api, world.a, "OUT", reorder_level=3)
    await new_part(api, world.a, "LOW", reorder_level=3, stock=3)
    await new_part(api, world.a, "OK", reorder_level=3, stock=4)

    async def skus(*states: str) -> list[str]:
        page = await list_parts(api, world.a, stock_state=list(states))
        return [p["sku"] for p in page["items"]]

    assert await skus("OUT") == ["OUT"]
    assert await skus("LOW") == ["LOW"]
    assert await skus("LOW", "OUT") == ["LOW", "OUT"]
    assert await skus("OK") == ["OK"]
    bad = await api.get(
        url(world.a.id, "/parts"), params={"stock_state": "EMPTY"}, headers=bearer(world.a.parts)
    )
    assert field_codes(bad) == [("query.stock_state.0", "enum")]


async def test_search_matches_sku_or_name_case_insensitively_with_wildcards_escaped(
    api: httpx.AsyncClient, world: World
) -> None:
    await new_part(api, world.a, "OIL-FLT-01", name="Oil filter")
    await new_part(api, world.a, "BRK_PAD", name="Brake pads 50%")
    await new_part(api, world.a, "WPR-PAIR", name="Wiper blades")

    async def search(q: str) -> list[str]:
        return [p["sku"] for p in (await list_parts(api, world.a, q=q))["items"]]

    assert await search("flt") == ["OIL-FLT-01"]
    assert await search("FILTER") == ["OIL-FLT-01"]
    assert await search("%") == ["BRK_PAD"]  # a literal percent sign, not "anything"
    assert await search("_") == ["BRK_PAD"]  # a literal underscore
    assert await search("  ") == ["BRK_PAD", "OIL-FLT-01", "WPR-PAIR"]  # blank = no filter
    too_long = await api.get(
        url(world.a.id, "/parts"), params={"q": "x" * 101}, headers=bearer(world.a.parts)
    )
    assert field_codes(too_long) == [("query.q", "string_too_long")]


async def test_sorting_and_pagination(api: httpx.AsyncClient, world: World) -> None:
    await new_part(api, world.a, "CCC", name="alpha", stock=5)
    await new_part(api, world.a, "AAA", name="charlie", stock=1)
    await new_part(api, world.a, "BBB", name="bravo", stock=9)

    async def order(sort: str) -> list[str]:
        return [p["sku"] for p in (await list_parts(api, world.a, sort=sort))["items"]]

    assert await order("sku") == ["AAA", "BBB", "CCC"]
    assert await order("-sku") == ["CCC", "BBB", "AAA"]
    assert await order("name") == ["CCC", "BBB", "AAA"]
    assert await order("available") == ["AAA", "CCC", "BBB"]
    assert await order("-available") == ["BBB", "CCC", "AAA"]
    page = await list_parts(api, world.a, limit=2, offset=1)
    assert ([p["sku"] for p in page["items"]], page["total"], page["limit"], page["offset"]) == (
        ["BBB", "CCC"],
        3,
        2,
        1,
    )
    for params in ({"sort": "price"}, {"limit": 101}, {"limit": 0}, {"offset": -1}):
        response = await api.get(
            url(world.a.id, "/parts"), params=params, headers=bearer(world.a.parts)
        )
        assert_problem(response, 422, "VALIDATION_ERROR")


async def test_another_shops_parts_never_appear(api: httpx.AsyncClient, world: World) -> None:
    await new_part(api, world.a, "MINE")
    await new_part(api, world.b, "THEIRS")
    assert [p["sku"] for p in (await list_parts(api, world.a))["items"]] == ["MINE"]
    assert [p["sku"] for p in (await list_parts(api, world.b))["items"]] == ["THEIRS"]

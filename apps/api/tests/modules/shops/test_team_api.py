"""The team over HTTP: list, add, change role, deactivate, reactivate (spec 03 §4.9, D15-D19).

Covers SHP-06, SHP-07 (with a fake read port), SEC-13, SEC-14, SEC-15, SEC-17 (member PATCH),
SEC-21, SEC-27 (member creation) and API-12 (member creation).
"""

import uuid

import httpx
import pytest
from sqlalchemy import func, select

from app.core.database import Database
from app.modules.identity.models import User
from app.modules.shops.models import ShopMembership
from app.shared.clock import SimulatedClock
from app.shared.enums import MembershipRole
from tests.assertions import assert_problem
from tests.modules.identity.builders import (
    TEST_PASSWORD,
    bearer,
    field_errors,
    make_user,
    unique_email,
)
from tests.modules.shops.builders import (
    ShopCtx,
    add_member,
    make_shop,
    make_team,
    set_member_active,
)
from tests.modules.shops.fakes import FakeActivityReader

pytestmark = pytest.mark.db

LOGIN = "/api/v1/auth/login"


def members_url(ctx: ShopCtx, suffix: str = "") -> str:
    return f"/api/v1/shops/{ctx.id}/members{suffix}"


async def password_hash_of(db: Database, user_id: uuid.UUID) -> str:
    async with db.sessionmaker() as session:
        return str(await session.scalar(select(User.password_hash).where(User.id == user_id)))


async def membership_count(db: Database) -> int:
    async with db.sessionmaker() as session:
        return int(await session.scalar(select(func.count()).select_from(ShopMembership)) or 0)


# --- Add ------------------------------------------------------------------------------------------


async def test_add_member_with_a_new_email_creates_the_account(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    body = {
        "email": unique_email("bilal"),
        "full_name": "  Bilal  ",
        "role": "SERVICE_ADVISOR",
        "password": "Initial-Pass-2026",
        "phone": "0300 1234567",
    }
    response = await db_client.post(members_url(ctx), json=body, headers=bearer(ctx.owner.id))
    assert response.status_code == 201, response.text
    member = response.json()
    assert member["account_created"] is True
    assert member["role"] == "SERVICE_ADVISOR"
    assert (member["is_active"], member["open_jobs"]) == (True, 0)
    assert member["user"] == {
        "id": member["user"]["id"],
        "email": body["email"],
        "full_name": "Bilal",
        "phone": "03001234567",
    }
    assert member["created_at"] == member["updated_at"] == "2026-10-14T04:00:00Z"
    async with db.sessionmaker() as session:
        last_login = await session.scalar(
            select(User.last_login_at).where(User.email == body["email"])
        )
    assert last_login is None  # adding staff starts no session (identity open question 2)
    login = await db_client.post(LOGIN, json={"email": body["email"], "password": body["password"]})
    assert login.status_code == 200  # the Owner hands this password over (D18)


async def test_sec21_an_existing_email_only_gets_a_membership(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    existing = await make_user(db, full_name="Imran Ali", phone="+923000000999")
    hash_before = await password_hash_of(db, existing.id)
    body = {
        "email": existing.email.upper(),
        "full_name": "Somebody Else",
        "role": "TECHNICIAN",
        "password": "Owner-Chosen-Pass-1",
        "phone": "0311 7654321",
    }
    response = await db_client.post(members_url(ctx), json=body, headers=bearer(ctx.owner.id))
    assert response.status_code == 201
    member = response.json()
    assert member["account_created"] is False
    assert member["user"] == {
        "id": str(existing.id),
        "email": existing.email,
        "full_name": "Imran Ali",  # never modified (D18)
        "phone": "+923000000999",
    }
    assert await password_hash_of(db, existing.id) == hash_before  # byte-identical
    owner_password = await db_client.post(
        LOGIN, json={"email": existing.email, "password": "Owner-Chosen-Pass-1"}
    )
    assert owner_password.status_code == 401
    own_password = await db_client.post(
        LOGIN, json={"email": existing.email, "password": TEST_PASSWORD}
    )
    assert own_password.status_code == 200

    again = await db_client.post(members_url(ctx), json=body, headers=bearer(ctx.owner.id))
    problem = assert_problem(again, 409, "CONFLICT")
    assert problem["detail"] == (
        "Already a member of this shop — change the role or reactivate instead."
    )


async def test_an_inactive_membership_still_blocks_a_second_add(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    member = await add_member(db, ctx, MembershipRole.TECHNICIAN, active=False)
    response = await db_client.post(
        members_url(ctx),
        json={"email": member.user.email, "full_name": "X", "role": "QC_INSPECTOR"},
        headers=bearer(ctx.owner.id),
    )
    assert_problem(response, 409, "CONFLICT")  # use PATCH to reactivate or re-role


async def test_the_owner_cannot_add_themselves_again(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    response = await db_client.post(
        members_url(ctx),
        json={"email": ctx.owner.email, "full_name": "Me", "role": "SERVICE_ADVISOR"},
        headers=bearer(ctx.owner.id),
    )
    assert_problem(response, 409, "CONFLICT")


async def test_a_new_email_needs_a_password(db_client: httpx.AsyncClient, db: Database) -> None:
    ctx = await make_shop(db)
    before = await membership_count(db)
    response = await db_client.post(
        members_url(ctx),
        json={"email": unique_email(), "full_name": "No Password", "role": "TECHNICIAN"},
        headers=bearer(ctx.owner.id),
    )
    problem = assert_problem(response, 422, "VALIDATION_ERROR")
    assert field_errors(problem) == [("password", "missing")]
    assert await membership_count(db) == before


async def test_a_deactivated_account_can_be_attached_but_cannot_log_in(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    dormant = await make_user(db, active=False)
    response = await db_client.post(
        members_url(ctx),
        json={"email": dormant.email, "full_name": "Dormant", "role": "PARTS_PERSON"},
        headers=bearer(ctx.owner.id),
    )
    assert response.status_code == 201
    assert response.json()["account_created"] is False
    login = await db_client.post(LOGIN, json={"email": dormant.email, "password": TEST_PASSWORD})
    assert_problem(login, 401, "INVALID_CREDENTIALS")


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"role": "OWNER"}, [("role", "enum")]),  # a second owner is impossible (SEC-15)
        ({"email": "x@localhost"}, [("email", "value_error")]),
        ({"full_name": " "}, [("full_name", "string_too_short")]),
        ({"password": "A" * 11}, [("password", "string_too_short")]),
        ({"phone": "abc"}, [("phone", "string_too_short")]),
        ({"is_active": False}, [("is_active", "extra_forbidden")]),
        ({"shop_id": str(uuid.uuid4())}, [("shop_id", "extra_forbidden")]),
    ],
)
async def test_add_member_validation(
    db_client: httpx.AsyncClient,
    db: Database,
    body: dict[str, object],
    expected: list[tuple[str, str]],
) -> None:
    ctx = await make_shop(db)
    payload: dict[str, object] = {
        "email": unique_email(),
        "full_name": "New Member",
        "role": "TECHNICIAN",
        "password": TEST_PASSWORD,
    }
    payload.update(body)
    response = await db_client.post(members_url(ctx), json=payload, headers=bearer(ctx.owner.id))
    assert field_errors(assert_problem(response, 422, "VALIDATION_ERROR")) == expected


@pytest.mark.parametrize(
    ("email", "stored"),
    [
        ("ahmed@mail.com", "ahmed@mail.com"),
        ("Fatima.Owner@BayFlow.TEST", "fatima.owner@bayflow.test"),
        ("smoke+42@bayflow.test", "smoke+42@bayflow.test"),
    ],
)
async def test_api12_member_creation_accepts_demo_and_real_addresses(
    db_client: httpx.AsyncClient, db: Database, email: str, stored: str
) -> None:
    ctx = await make_shop(db)
    response = await db_client.post(
        members_url(ctx),
        json={
            "email": email,
            "full_name": "Member",
            "role": "QC_INSPECTOR",
            "password": TEST_PASSWORD,
        },
        headers=bearer(ctx.owner.id),
    )
    assert response.status_code == 201
    assert response.json()["user"]["email"] == stored


async def test_sec27_member_creation_is_limited_per_shop(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    other = await make_shop(db)
    member = await add_member(db, ctx, MembershipRole.TECHNICIAN)  # 1 attempt used
    duplicate = {"email": member.user.email, "full_name": "X", "role": "TECHNICIAN"}
    for _ in range(29):  # every attempt counts, also a refused one (30 per hour per shop)
        response = await db_client.post(
            members_url(ctx), json=duplicate, headers=bearer(ctx.owner.id)
        )
        assert response.status_code == 409
    fresh = {
        "email": unique_email(),
        "full_name": "Over The Limit",
        "role": "TECHNICIAN",
        "password": TEST_PASSWORD,
    }
    blocked = await db_client.post(members_url(ctx), json=fresh, headers=bearer(ctx.owner.id))
    assert_problem(blocked, 429, "RATE_LIMITED")
    assert int(blocked.headers["retry-after"]) >= 1
    elsewhere = await db_client.post(members_url(other), json=fresh, headers=bearer(other.owner.id))
    assert elsewhere.status_code == 201  # the limit is per shop


# --- List -----------------------------------------------------------------------------------------


async def test_shp06_the_owner_sees_everyone_in_role_then_name_order(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    team = await make_team(db, ctx)  # Bilal SA, Imran T, Usman PP, Sara QC, Hina QC
    zaid = await add_member(db, ctx, MembershipRole.TECHNICIAN, full_name="Zaid", active=False)
    adeel = await add_member(db, ctx, MembershipRole.TECHNICIAN, full_name="adeel")
    response = await db_client.get(members_url(ctx), headers=bearer(ctx.owner.id))
    assert response.status_code == 200
    page = response.json()
    assert (page["total"], page["limit"], page["offset"]) == (8, 20, 0)
    assert [(item["role"], item["user"]["full_name"]) for item in page["items"]] == [
        ("OWNER", "Fatima Raza"),
        ("SERVICE_ADVISOR", "Bilal"),
        ("TECHNICIAN", "adeel"),
        ("TECHNICIAN", "Imran"),
        ("TECHNICIAN", "Zaid"),
        ("PARTS_PERSON", "Usman"),
        ("QC_INSPECTOR", "Hina"),
        ("QC_INSPECTOR", "Sara"),
    ]
    by_name = {item["user"]["full_name"]: item for item in page["items"]}
    assert by_name["Zaid"]["is_active"] is False
    assert by_name["Zaid"]["membership_id"] == str(zaid.membership_id)
    assert by_name["adeel"]["membership_id"] == str(adeel.membership_id)
    assert by_name["Bilal"]["user"]["email"] == team.advisor.user.email

    filtered = await db_client.get(
        members_url(ctx),
        params=[("role", "TECHNICIAN"), ("role", "QC_INSPECTOR"), ("is_active", "true")],
        headers=bearer(ctx.owner.id),
    )
    assert [item["user"]["full_name"] for item in filtered.json()["items"]] == [
        "adeel",
        "Imran",
        "Hina",
        "Sara",
    ]
    window = await db_client.get(
        members_url(ctx), params={"limit": 2, "offset": 1}, headers=bearer(ctx.owner.id)
    )
    assert [item["user"]["full_name"] for item in window.json()["items"]] == ["Bilal", "adeel"]
    assert window.json()["total"] == 8


async def test_shp06_a_service_advisor_sees_only_active_technicians_and_parts_persons(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    team = await make_team(db, ctx)
    await add_member(db, ctx, MembershipRole.TECHNICIAN, full_name="Inactive Tech", active=False)
    disabled_account = await make_user(db, full_name="Disabled Account", active=False)
    await add_member(db, ctx, MembershipRole.TECHNICIAN, user=disabled_account)
    headers = bearer(team.advisor.id)
    response = await db_client.get(members_url(ctx), headers=headers)
    assert [(i["role"], i["user"]["full_name"]) for i in response.json()["items"]] == [
        ("TECHNICIAN", "Imran"),
        ("PARTS_PERSON", "Usman"),
    ]
    assert response.json()["total"] == 2
    qc_only = await db_client.get(
        members_url(ctx), params={"role": "QC_INSPECTOR"}, headers=headers
    )
    assert qc_only.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
    inactive = await db_client.get(members_url(ctx), params={"is_active": "false"}, headers=headers)
    assert inactive.json()["items"] == []
    parts = await db_client.get(members_url(ctx), params={"role": "PARTS_PERSON"}, headers=headers)
    assert [i["user"]["full_name"] for i in parts.json()["items"]] == ["Usman"]


async def test_shp06_other_roles_may_not_list_the_team(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    team = await make_team(db, ctx)
    for member in (team.technician, team.parts, team.qc):
        response = await db_client.get(members_url(ctx), headers=bearer(member.id))
        assert_problem(response, 403, "FORBIDDEN")


async def test_members_list_validation(db_client: httpx.AsyncClient, db: Database) -> None:
    ctx = await make_shop(db)
    headers = bearer(ctx.owner.id)
    for params in ({"role": "CUSTOMER"}, {"limit": 0}, {"limit": 101}, {"offset": -1}):
        response = await db_client.get(members_url(ctx), params=params, headers=headers)
        assert_problem(response, 422, "VALIDATION_ERROR")


async def test_shp07_open_jobs_come_from_the_bookings_read_port(
    db_client: httpx.AsyncClient, db: Database, activity_reader: FakeActivityReader
) -> None:
    ctx = await make_shop(db)
    team = await make_team(db, ctx)
    activity_reader.open_jobs = {team.technician.id: 3, team.parts.id: 1}
    response = await db_client.get(members_url(ctx), headers=bearer(ctx.owner.id))
    open_jobs = {item["user"]["id"]: item["open_jobs"] for item in response.json()["items"]}
    assert open_jobs[str(team.technician.id)] == 3
    assert open_jobs[str(team.parts.id)] == 1
    assert open_jobs[str(team.qc.id)] == 0
    patched = await db_client.patch(
        members_url(ctx, f"/{team.technician.membership_id}"),
        json={"is_active": False},
        headers=bearer(ctx.owner.id),
    )
    assert patched.json()["open_jobs"] == 3  # O-02 can warn before the jobs are moved


# --- Update ---------------------------------------------------------------------------------------


async def test_update_member_changes_the_role_and_activation(
    db_client: httpx.AsyncClient, db: Database, clock: SimulatedClock
) -> None:
    ctx = await make_shop(db)
    member = await add_member(db, ctx, MembershipRole.TECHNICIAN)
    url = members_url(ctx, f"/{member.membership_id}")
    headers = bearer(ctx.owner.id)
    clock.set(clock.now().replace(hour=5))
    role = await db_client.patch(url, json={"role": "QC_INSPECTOR"}, headers=headers)
    assert role.status_code == 200
    assert (role.json()["role"], role.json()["is_active"]) == ("QC_INSPECTOR", True)
    assert role.json()["updated_at"] == "2026-10-14T05:00:00Z"
    both = await db_client.patch(
        url, json={"role": "PARTS_PERSON", "is_active": False}, headers=headers
    )
    assert (both.json()["role"], both.json()["is_active"]) == ("PARTS_PERSON", False)
    clock.set(clock.now().replace(hour=6))
    same = await db_client.patch(url, json={"is_active": False}, headers=headers)
    assert same.json()["updated_at"] == "2026-10-14T05:00:00Z"  # nothing changed, nothing written


async def test_sec15_the_owner_membership_is_immutable(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    owner_row = (await db_client.get(members_url(ctx), headers=bearer(ctx.owner.id))).json()[
        "items"
    ][0]
    assert owner_row["role"] == "OWNER"
    url = members_url(ctx, f"/{owner_row['membership_id']}")
    for body in ({"is_active": False}, {"role": "TECHNICIAN"}, {"is_active": True}):
        response = await db_client.patch(url, json=body, headers=bearer(ctx.owner.id))
        problem = assert_problem(response, 403, "FORBIDDEN")
        assert problem["detail"] == "The owner's membership cannot be changed or deactivated."
    owner_again = (await db_client.get(members_url(ctx), headers=bearer(ctx.owner.id))).json()
    assert owner_again["items"][0] == owner_row
    to_owner = await db_client.patch(url, json={"role": "OWNER"}, headers=bearer(ctx.owner.id))
    assert field_errors(assert_problem(to_owner, 422, "VALIDATION_ERROR")) == [("role", "enum")]


async def test_sec17_member_patch_refuses_other_fields(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    member = await add_member(db, ctx, MembershipRole.TECHNICIAN)
    url = members_url(ctx, f"/{member.membership_id}")
    for body, field in (
        ({"user_id": str(uuid.uuid4())}, "user_id"),
        ({"shop_id": str(uuid.uuid4())}, "shop_id"),
        ({"full_name": "New Name"}, "full_name"),
    ):
        response = await db_client.patch(url, json=body, headers=bearer(ctx.owner.id))
        assert field_errors(assert_problem(response, 422, "VALIDATION_ERROR")) == [
            (field, "extra_forbidden")
        ]
    empty = await db_client.patch(url, json={}, headers=bearer(ctx.owner.id))
    assert field_errors(assert_problem(empty, 422, "VALIDATION_ERROR")) == [("", "value_error")]


async def test_another_shops_or_an_unknown_membership_is_404(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    other = await make_shop(db)
    theirs = await add_member(db, other, MembershipRole.TECHNICIAN)
    for membership_id in (theirs.membership_id, uuid.uuid4()):
        response = await db_client.patch(
            members_url(ctx, f"/{membership_id}"),
            json={"is_active": False},
            headers=bearer(ctx.owner.id),
        )
        assert_problem(response, 404, "NOT_FOUND")
    bad_id = await db_client.patch(
        members_url(ctx, "/not-a-uuid"), json={"is_active": False}, headers=bearer(ctx.owner.id)
    )
    assert field_errors(assert_problem(bad_id, 422, "VALIDATION_ERROR")) == [
        ("path.membership_id", "uuid_parsing")
    ]


async def test_sec13_sec14_deactivation_and_reactivation_apply_on_the_next_request(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    imran = await add_member(db, ctx, MembershipRole.TECHNICIAN)
    token = bearer(imran.id)  # the same token throughout (D9)
    shop_url = f"/api/v1/shops/{ctx.id}"
    assert (await db_client.get(shop_url, headers=token)).status_code == 200

    await set_member_active(db, ctx, imran.membership_id, active=False)
    assert_problem(await db_client.get(shop_url, headers=token), 404, "NOT_FOUND")
    services = await db_client.get(f"{shop_url}/services", headers=token)
    assert_problem(services, 404, "NOT_FOUND")
    me = await db_client.get("/api/v1/me", headers=token)
    assert me.status_code == 200  # the account itself is still active
    assert me.json()["memberships"] == []

    await set_member_active(db, ctx, imran.membership_id, active=True)
    assert (await db_client.get(shop_url, headers=token)).status_code == 200
    me_again = (await db_client.get("/api/v1/me", headers=token)).json()
    assert [item["shop_id"] for item in me_again["memberships"]] == [str(ctx.id)]


async def test_a_role_change_applies_on_the_next_request(
    db_client: httpx.AsyncClient, db: Database
) -> None:
    ctx = await make_shop(db)
    member = await add_member(db, ctx, MembershipRole.TECHNICIAN)
    token = bearer(member.id)
    assert_problem(await db_client.get(members_url(ctx), headers=token), 403, "FORBIDDEN")
    await db_client.patch(
        members_url(ctx, f"/{member.membership_id}"),
        json={"role": "SERVICE_ADVISOR"},
        headers=bearer(ctx.owner.id),
    )
    assert (await db_client.get(members_url(ctx), headers=token)).status_code == 200

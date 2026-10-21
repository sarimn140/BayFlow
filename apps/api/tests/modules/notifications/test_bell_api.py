"""The bell API over HTTP (spec 03 §4.12): `GET /api/v1/me/notifications`, `…/unread-count`,
`POST …/{notification_id}/read`, `POST …/read-all`.

NOT-05 (own unread count, drops after mark-read), NOT-06 (mark one / all; another user's → 404),
NOT-10 (own rows, newest first, paginated), NOT-21 (mark-read twice → 204, `read_at` unchanged),
SEC-34 (foreign ids invisible), API-13 (`Cache-Control: no-store` on every response) and the
`NotificationRead` wire shape (spec 03 §3.7).
"""

from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest

from app.core.security import issue_token
from app.modules.identity.models import User
from app.shared.clock import SimulatedClock, utcnow
from app.shared.enums import ActorRole, BookingAction, BookingStatus
from app.shared.timestamps import format_timestamp
from tests.assertions import assert_problem
from tests.modules.notifications.support import World, applied, publish

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("booking_reads")]

A = BookingAction
R = ActorRole
BELL = "/api/v1/me/notifications"
NOTIFICATION_READ_FIELDS = [
    "id",
    "type",
    "title",
    "body",
    "recipient_role",
    "link",
    "shop_id",
    "shop_name",
    "booking_id",
    "booking_reference",
    "read_at",
    "created_at",
]


def bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(user.id, 'session', utcnow())}"}


async def seed_bell(world: World) -> None:
    """Fatima: 3 rows as the Owner of Raza Auto Works (no SA there, D26); Ayesha: 1 customer
    row (`BOOKING_CONFIRMED` at Lahore Auto Care); Bilal and Kashif: 1 `ESTIMATE_APPROVED` each."""
    raza = [await world.booking(world.c, status=BookingStatus.PENDING) for _ in range(3)]
    for booking in raza:
        await publish(
            world.db, applied(booking, A.CREATE, actor=world.ayesha, actor_role=R.CUSTOMER)
        )
    lahore = await world.job(world.a)
    await publish(
        world.db,
        applied(lahore, A.CONFIRM, actor=world.a.advisor, actor_role=R.SERVICE_ADVISOR),
    )
    await publish(
        world.db, applied(lahore, A.APPROVE_ESTIMATE, actor=world.ayesha, actor_role=R.CUSTOMER)
    )


async def get_list(client: httpx.AsyncClient, user: User, **params: object) -> httpx.Response:
    return await client.get(BELL, params=params, headers=bearer(user))


async def unread(client: httpx.AsyncClient, user: User) -> int:
    response = await client.get(f"{BELL}/unread-count", headers=bearer(user))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    count: int = response.json()["count"]
    return count


async def test_not10_lists_only_my_notifications_newest_first(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    await seed_bell(world)
    fatima = world.a.owner

    response = await get_list(db_client, fatima)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    page = response.json()
    assert page["total"] == 3
    assert (page["limit"], page["offset"]) == (20, 0)
    created = [item["created_at"] for item in page["items"]]
    assert created == sorted(created, reverse=True)
    rows = await world.notifications()
    mine = sorted(
        (row for row in rows if row.recipient_user_id == fatima.id),
        key=lambda row: (row.created_at, row.id),
        reverse=True,
    )
    assert [item["id"] for item in page["items"]] == [str(row.id) for row in mine]
    for item in page["items"]:
        assert list(item) == NOTIFICATION_READ_FIELDS  # no recipient_user_id on the wire
        assert item["recipient_role"] == "OWNER"
        assert item["shop_name"] == "Raza Auto Works"
        assert item["shop_id"] == str(world.c.id)
        assert item["booking_reference"].startswith("BF-")
        assert item["link"] == f"/pos/shops/{world.c.id}/bookings/{item['booking_id']}"
        assert item["read_at"] is None
        assert item["created_at"].endswith("Z")


async def test_not10_ties_are_ordered_by_id_and_pages_are_stable(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    """25 rows of one instant: `created_at DESC, id DESC`, cut into pages without overlap."""
    booking = await world.job(world.a)
    occurred_at = utcnow()
    for _ in range(25):
        await publish(
            world.db,
            applied(
                booking,
                A.NOTIFY_READY,
                actor=world.a.advisor,
                actor_role=R.SERVICE_ADVISOR,
                occurred_at=occurred_at,
            ),
        )

    first = (await get_list(db_client, world.ayesha)).json()
    second = (await get_list(db_client, world.ayesha, limit=20, offset=20)).json()
    beyond = (await get_list(db_client, world.ayesha, limit=5, offset=40)).json()

    ids = [item["id"] for item in first["items"]] + [item["id"] for item in second["items"]]
    assert (first["total"], second["total"], beyond["total"]) == (25, 25, 25)
    assert (len(first["items"]), len(second["items"]), beyond["items"]) == (20, 5, [])
    assert ids == sorted(ids, key=UUID, reverse=True)
    assert len(set(ids)) == 25


async def test_list_spans_every_shop_and_role_of_the_user(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    """Bilal is an SA at Lahore Auto Care and a customer at Clifton Car Clinic."""
    lahore = await world.job(world.a)
    clifton = await world.booking(world.b, customer=world.a.advisor, status=BookingStatus.PENDING)
    await publish(world.db, applied(lahore, A.CREATE, actor=world.ayesha, actor_role=R.CUSTOMER))
    await publish(
        world.db,
        applied(clifton, A.CONFIRM, actor=world.b.advisor, actor_role=R.SERVICE_ADVISOR),
    )

    items = (await get_list(db_client, world.a.advisor)).json()["items"]

    assert {(item["shop_name"], item["recipient_role"], item["link"]) for item in items} == {
        ("Lahore Auto Care", "SERVICE_ADVISOR", f"/pos/shops/{world.a.id}/bookings/{lahore.id}"),
        ("Clifton Car Clinic", "CUSTOMER", f"/bookings/{clifton.id}"),
    }
    assert {item["booking_reference"] for item in items} == {lahore.reference, clifton.reference}


async def test_unread_only_lists_and_counts_the_unread_ones(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    await seed_bell(world)
    fatima = world.a.owner
    first = (await get_list(db_client, fatima)).json()["items"][0]
    response = await db_client.post(f"{BELL}/{first['id']}/read", headers=bearer(fatima))
    assert response.status_code == 204

    unread_page = (await get_list(db_client, fatima, unread_only="true")).json()
    all_page = (await get_list(db_client, fatima, unread_only="false")).json()

    assert unread_page["total"] == 2
    assert first["id"] not in {item["id"] for item in unread_page["items"]}
    assert all(item["read_at"] is None for item in unread_page["items"])
    assert all_page["total"] == 3


async def test_not05_unread_count_is_my_own_and_drops_after_mark_read(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    await seed_bell(world)
    fatima, ayesha = world.a.owner, world.ayesha
    assert await unread(db_client, fatima) == 3
    assert await unread(db_client, ayesha) == 1  # BOOKING_CONFIRMED
    assert await unread(db_client, world.b.owner) == 0

    item = (await get_list(db_client, fatima)).json()["items"][0]
    await db_client.post(f"{BELL}/{item['id']}/read", headers=bearer(fatima))

    assert await unread(db_client, fatima) == 2
    assert await unread(db_client, ayesha) == 1


async def test_not06_mark_one_and_mark_all(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    await seed_bell(world)
    fatima = world.a.owner
    items = (await get_list(db_client, fatima)).json()["items"]

    one = await db_client.post(f"{BELL}/{items[1]['id']}/read", headers=bearer(fatima))
    read_one_at = format_timestamp(utcnow())
    clock.advance(timedelta(minutes=5))
    everything = await db_client.post(f"{BELL}/read-all", headers=bearer(fatima))
    read_all_at = format_timestamp(utcnow())

    assert (one.status_code, one.content) == (204, b"")
    assert (everything.status_code, everything.content) == (204, b"")
    assert one.headers["cache-control"] == everything.headers["cache-control"] == "no-store"
    after = {
        item["id"]: item["read_at"] for item in (await get_list(db_client, fatima)).json()["items"]
    }
    assert after[items[1]["id"]] == read_one_at  # mark-all keeps an existing read_at
    assert after[items[0]["id"]] == after[items[2]["id"]] == read_all_at  # one instant (D63)
    assert await unread(db_client, fatima) == 0
    assert await unread(db_client, world.ayesha) == 1  # nobody else's rows changed


async def test_read_all_without_unread_rows_is_still_204(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    for _ in range(2):
        response = await db_client.post(f"{BELL}/read-all", headers=bearer(world.b.owner))
        assert response.status_code == 204


async def test_not21_mark_read_twice_keeps_the_first_read_at(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    await seed_bell(world)
    fatima = world.a.owner
    item_id = (await get_list(db_client, fatima)).json()["items"][0]["id"]

    first = await db_client.post(f"{BELL}/{item_id}/read", headers=bearer(fatima))
    first_read_at = format_timestamp(utcnow())
    clock.advance(timedelta(hours=1))
    second = await db_client.post(f"{BELL}/{item_id}/read", headers=bearer(fatima))

    assert (first.status_code, second.status_code) == (204, 204)
    items = (await get_list(db_client, fatima)).json()["items"]
    assert next(item for item in items if item["id"] == item_id)["read_at"] == first_read_at


async def test_sec34_another_users_notification_is_invisible(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    await seed_bell(world)
    fatima, intruder = world.a.owner, world.b.owner
    item_id = (await get_list(db_client, fatima)).json()["items"][0]["id"]

    foreign = await db_client.post(f"{BELL}/{item_id}/read", headers=bearer(intruder))
    unknown = await db_client.post(f"{BELL}/{uuid4()}/read", headers=bearer(intruder))
    listed = (await get_list(db_client, intruder)).json()

    foreign_body = assert_problem(foreign, 404, "NOT_FOUND")
    unknown_body = assert_problem(unknown, 404, "NOT_FOUND")
    assert foreign_body["detail"] == unknown_body["detail"]  # identical: nothing leaks
    assert foreign.headers["cache-control"] == "no-store"
    assert listed == {"items": [], "total": 0, "limit": 20, "offset": 0}
    assert await unread(db_client, fatima) == 3  # the foreign attempt changed nothing


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", BELL),
        ("GET", f"{BELL}/unread-count"),
        ("POST", f"{BELL}/read-all"),
        ("POST", f"{BELL}/{uuid4()}/read"),
    ],
)
async def test_every_bell_route_needs_a_session(
    db_client: httpx.AsyncClient, world: World, method: str, path: str
) -> None:
    anonymous = await db_client.request(method, path)
    ticket = issue_token(world.ayesha.id, "ws", utcnow())  # a WebSocket ticket is no session
    with_ticket = await db_client.request(
        method, path, headers={"Authorization": f"Bearer {ticket}"}
    )
    await world.set_user_active(world.ayesha, active=False)
    deactivated = await db_client.request(method, path, headers=bearer(world.ayesha))

    for response in (anonymous, with_ticket, deactivated):
        assert_problem(response, 401, "UNAUTHENTICATED")
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("method", "path", "params"),
    [
        ("POST", f"{BELL}/not-a-uuid/read", {}),
        ("GET", BELL, {"limit": 0}),
        ("GET", BELL, {"limit": 101}),
        ("GET", BELL, {"offset": -1}),
        ("GET", BELL, {"unread_only": "maybe"}),
    ],
)
async def test_malformed_input_is_422(
    db_client: httpx.AsyncClient,
    world: World,
    method: str,
    path: str,
    params: dict[str, object],
) -> None:
    response = await db_client.request(method, path, params=params, headers=bearer(world.ayesha))
    body = assert_problem(response, 422, "VALIDATION_ERROR")
    assert body["errors"]
    assert response.headers["cache-control"] == "no-store"


async def test_unread_count_shape(
    db_client: httpx.AsyncClient, world: World, clock: SimulatedClock
) -> None:
    response = await db_client.get(f"{BELL}/unread-count", headers=bearer(world.ayesha))
    assert response.status_code == 200
    assert response.json() == {"count": 0}

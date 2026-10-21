"""The audit log in the admin console: E-74 (list) and E-75 (CSV export) (spec 19 §4, §7, §9).

Rows are written through `audit.service.record` with hand-made entries, so every filter has a
known answer; the 10 000-row cap test inserts its rows in one statement instead (the service
would take minutes), bypassing the services on purpose like `tests/rows.py`.
"""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.core.database import Database
from app.modules.audit import service as audit_service
from app.modules.audit.schemas import AuditEntry
from app.modules.identity.schemas import UserRecord
from app.shared.enums import AuditActorRole, AuditCategory, AuditTargetType
from tests.assertions import assert_problem
from tests.modules.admin.support import ADMIN, admin_get, audit_rows
from tests.modules.bookings.support import Desk, World
from tests.modules.identity.builders import bearer, unit_of_work

T0 = datetime(2026, 10, 1, 4, 0, tzinfo=UTC)
EXPORT_HEADER = [
    "occurred_at",
    "category",
    "action",
    "summary",
    "actor_user_id",
    "actor_name",
    "actor_role",
    "shop_id",
    "shop_name",
    "target_type",
    "target_id",
    "target_label",
    "metadata",
    "ip",
    "user_agent",
    "request_id",
]


async def write(db: Database, *entries: AuditEntry) -> None:
    async with unit_of_work(db) as uow:
        for entry in entries:
            await audit_service.record(uow, entry)
        await uow.commit()


def entry(minutes: int, action: str = "auth.login_failed", **fields: Any) -> AuditEntry:
    category = fields.pop("category", AuditCategory(action.split(".", maxsplit=1)[0].upper()))
    return AuditEntry(
        occurred_at=T0 + timedelta(minutes=minutes),
        action=action,
        summary=fields.pop("summary", f"Row at minute {minutes}."),
        category=category,
        **fields,
    )


async def listing(desk: Desk, admin: UserRecord, **params: Any) -> list[str]:
    page = await admin_get(desk.api, admin, "/audit-events", limit=100, **params)
    return [item["summary"] for item in page["items"]]


async def test_e74_filters_sorts_and_names(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    booking_id = uuid.uuid4()
    await write(
        db,
        entry(
            1,
            "auth.login_failed",
            summary="Failed sign-in for a@bayflow.test.",
            metadata={"email": "a@bayflow.test"},
        ),
        entry(
            2,
            "shop.updated",
            summary="Fatima Raza updated Lahore Auto Care (name).",
            actor_user_id=world.owner.id,
            actor_role=AuditActorRole.OWNER,
            shop_id=world.shop_id,
            target_type=AuditTargetType.SHOP,
            target_id=world.shop_id,
            target_label="Lahore Auto Care",
        ),
        entry(
            3,
            "booking.confirm",
            summary="Bilal confirmed BF-7K2M9Q at Lahore Auto Care.",
            actor_user_id=world.advisor.id,
            actor_role=AuditActorRole.SERVICE_ADVISOR,
            shop_id=world.shop_id,
            target_type=AuditTargetType.BOOKING,
            target_id=booking_id,
            target_label="BF-7K2M9Q",
        ),
        entry(
            4,
            "user.deactivated",
            summary="Areeba Hashmi deactivated the account of Bilal.",
            actor_user_id=admin.id,
            actor_role=AuditActorRole.PLATFORM_ADMIN,
            target_type=AuditTargetType.USER,
            target_id=world.advisor.id,
            target_label="100%_off@bayflow.test",
        ),
    )
    page = await admin_get(desk.api, admin, "/audit-events")
    assert page["total"] == 4
    newest = page["items"][0]
    assert (newest["action"], newest["actor_name"], newest["actor_role"]) == (
        "user.deactivated",
        "Areeba Hashmi",
        "PLATFORM_ADMIN",
    )
    assert newest["occurred_at"] == "2026-10-01T04:04:00Z"
    shop_row = page["items"][2]
    assert (shop_row["shop_name"], shop_row["target_type"]) == ("Lahore Auto Care", "SHOP")
    assert set(newest) == {
        "id",
        "occurred_at",
        "category",
        "action",
        "summary",
        "actor_user_id",
        "actor_name",
        "actor_role",
        "shop_id",
        "shop_name",
        "target_type",
        "target_id",
        "target_label",
        "metadata",
        "ip",
        "user_agent",
        "request_id",
    }
    oldest_first = await listing(desk, admin, sort="occurred_at")
    assert oldest_first[0] == "Failed sign-in for a@bayflow.test."
    assert len(await listing(desk, admin, category=["AUTH", "USER"])) == 2
    assert await listing(desk, admin, category="SHOP") == [
        "Fatima Raza updated Lahore Auto Care (name)."
    ]
    assert await listing(desk, admin, action="booking.confirm") == [
        "Bilal confirmed BF-7K2M9Q at Lahore Auto Care."
    ]
    assert len(await listing(desk, admin, actor_user_id=str(world.owner.id))) == 1
    assert len(await listing(desk, admin, shop_id=str(world.shop_id))) == 2
    assert len(await listing(desk, admin, target_type="BOOKING", target_id=str(booking_id))) == 1
    window = {"from": "2026-10-01T04:02:00Z", "to": "2026-10-01T09:04:00+05:00"}
    assert len(await listing(desk, admin, **window)) == 2  # from inclusive, to exclusive
    assert len(await listing(desk, admin, q="lahore auto")) == 2  # summary or label
    assert len(await listing(desk, admin, q="bf-7k2")) == 1  # the target label
    assert len(await listing(desk, admin, q="100%_")) == 1  # literal % and _
    second = await admin_get(desk.api, admin, "/audit-events", limit=1, offset=1)
    assert (second["total"], second["items"][0]["action"]) == (4, "booking.confirm")
    for bad in (
        {"category": "NOPE"},
        {"target_type": "PART"},
        {"from": "2026-10-01T04:00:00"},  # naive
        {"sort": "action"},
        {"limit": 0},
        {"actor_user_id": "x"},
    ):
        response = await desk.api.get(f"{ADMIN}/audit-events", headers=bearer(admin.id), params=bad)
        assert_problem(response, 422, "VALIDATION_ERROR")
    inverted = await desk.api.get(
        f"{ADMIN}/audit-events",
        headers=bearer(admin.id),
        params={"from": "2026-10-02T00:00:00Z", "to": "2026-10-01T00:00:00Z"},
    )
    body = assert_problem(inverted, 422, "VALIDATION_ERROR")
    assert [(e["field"], e["code"]) for e in body["errors"]] == [("query.to", "invalid_range")]


def parse_csv(content: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(content, newline="")))


async def insert_raw(db: Database, minutes: int, summary: str, label: str | None = None) -> None:
    """A row written straight into the table: the service keeps summaries on one line, but the
    export must quote whatever a row holds (spec 19 §7)."""
    async with db.engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO audit_events"
                " (id, occurred_at, category, action, summary, target_label) VALUES"
                " (gen_random_uuid(), :at, 'AUTH', 'auth.login_failed', :summary, :label)"
            ),
            {"at": T0 + timedelta(minutes=minutes), "summary": summary, "label": label},
        )


async def test_e75_exports_rfc4180_csv_with_formulas_neutralised(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    tricky = 'Comma, "quotes" and a\r\nline break.'
    await insert_raw(db, 1, tricky)
    await write(
        db,
        entry(2, summary='=HYPERLINK("https://evil.example","click")'),
        entry(3, summary="+1+2", metadata={"email": "a@bayflow.test"}),
        entry(4, summary="-3-4"),
        entry(5, summary="@SUM(A1:A2)"),
    )
    await insert_raw(db, 6, "\tTabbed")
    await write(
        db, entry(7, "shop.updated", target_label="=1+1", shop_id=world.shop_id, summary="Plain.")
    )
    response = await desk.api.get(f"{ADMIN}/audit-events/export", headers=bearer(admin.id))
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="bayflow-audit-')
    assert disposition.endswith('.csv"')
    assert response.headers["cache-control"] == "no-store"
    raw = response.content.decode("utf-8")
    assert raw.endswith("\r\n")
    rows = parse_csv(raw)
    assert rows[0] == EXPORT_HEADER
    by_column = [dict(zip(EXPORT_HEADER, row, strict=True)) for row in rows[1:]]
    assert [row["summary"] for row in by_column] == [  # newest first
        "Plain.",
        "'\tTabbed",
        "'@SUM(A1:A2)",
        "'-3-4",
        "'+1+2",
        '\'=HYPERLINK("https://evil.example","click")',
        tricky,  # quoted by RFC 4180 and read back intact
    ]
    assert '"Comma, ""quotes"" and a\r\nline break."' in raw  # the RFC 4180 quoting itself
    assert by_column[0]["target_label"] == "'=1+1"
    assert by_column[0]["shop_name"] == "Lahore Auto Care"
    assert by_column[4]["metadata"] == '{"email":"a@bayflow.test"}'
    assert by_column[-1]["occurred_at"] == "2026-10-01T04:01:00Z"
    assert by_column[-1]["actor_user_id"] == by_column[-1]["ip"] == ""  # None is an empty cell
    (exported,) = await audit_rows(db, action="admin.audit_exported")
    assert exported.metadata_ == {"filters": {}, "rows": 7}
    assert exported.summary == "Areeba Hashmi exported 7 audit events."
    second = await desk.api.get(f"{ADMIN}/audit-events/export", headers=bearer(admin.id))
    again = parse_csv(second.text)
    assert "admin.audit_exported" in {row[2] for row in again[1:]}  # the earlier export
    assert len(again) == 1 + 8  # never its own row


async def test_e75_applies_the_filters_and_records_them(
    desk: Desk, world: World, db: Database, admin: UserRecord
) -> None:
    await write(db, entry(1), entry(2, "shop.created", shop_id=world.shop_id), entry(3))
    response = await desk.api.get(
        f"{ADMIN}/audit-events/export",
        headers=bearer(admin.id),
        params={"category": "AUTH", "q": "minute"},
    )
    rows = parse_csv(response.text)
    assert [row[2] for row in rows[1:]] == ["auth.login_failed", "auth.login_failed"]
    (exported,) = await audit_rows(db, action="admin.audit_exported")
    assert exported.metadata_ == {"filters": {"category": ["AUTH"], "q": "minute"}, "rows": 2}
    inverted = await desk.api.get(
        f"{ADMIN}/audit-events/export",
        headers=bearer(admin.id),
        params={"from": "2026-10-02T00:00:00Z", "to": "2026-10-02T00:00:00Z"},
    )
    assert_problem(inverted, 422, "VALIDATION_ERROR")
    assert len(await audit_rows(db, action="admin.audit_exported")) == 1  # a refused export


async def test_e75_exports_at_most_10000_rows_newest_first(
    desk: Desk, db: Database, admin: UserRecord
) -> None:
    async with db.engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO audit_events (id, occurred_at, category, action, summary)"
                " SELECT gen_random_uuid(),"
                " CAST(:t0 AS timestamptz) + make_interval(secs => n),"
                " 'AUTH', 'auth.login_failed', 'Bulk row ' || n"
                " FROM generate_series(1, 10005) AS n"
            ),
            {"t0": T0},
        )
    response = await desk.api.get(f"{ADMIN}/audit-events/export", headers=bearer(admin.id))
    assert response.status_code == 200
    rows = parse_csv(response.text)
    assert len(rows) == 1 + 10_000
    assert rows[1][3] == "Bulk row 10005"  # newest first
    assert rows[-1][3] == "Bulk row 6"  # the 5 oldest are cut
    assert len({row[3] for row in rows[1:]}) == 10_000
    (exported,) = await audit_rows(db, action="admin.audit_exported")
    assert exported.metadata_ == {"filters": {}, "rows": 10_000}

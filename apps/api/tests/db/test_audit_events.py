"""`audit_events` and the platform-admin columns at the database level (spec 19 §3.1, spec 02
§3.22, §8; D29, D94-D96), proven with the service layer bypassed where it matters.

- The trigger `trg_audit_events_append_only` rejects `UPDATE` and `DELETE` (SQLSTATE `P0001`) for
  every client, while `TRUNCATE` (test clean-up) still works.
- The stored enums, the action format and the JSON shape are CHECKs.
- `ck_shops_suspension_complete`: a suspension is all three columns or none.
- The revision of this feature downgrades and upgrades cleanly (spec 02 §9).
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.database import Database
from app.modules.audit import service as audit_service
from app.modules.audit.models import AuditEvent
from app.modules.audit.schemas import AuditEntry
from app.modules.shops.models import Shop
from app.shared.enums import AuditCategory
from app.shared.event_bus import EventBus
from app.shared.repository import CHECK_VIOLATION, constraint_name, sqlstate
from app.shared.uow import UnitOfWork
from tests.rows import add_rows, make_shop, make_user

pytestmark = pytest.mark.db

AlembicCli = Callable[..., Awaitable[str]]
RAISE_EXCEPTION = "P0001"
WHEN = datetime(2026, 10, 14, 4, 0, tzinfo=UTC)
FEATURE_REVISION = "339df51b764d"
BASELINE_REVISION = "23165172278b"


async def one_row(db: Database) -> AuditEvent:
    async with db.sessionmaker() as session:
        uow = UnitOfWork(session, EventBus())
        await audit_service.record(
            uow,
            AuditEntry(
                occurred_at=WHEN,
                action="auth.login_failed",
                summary="Failed sign-in for a@bayflow.test.",
                category=AuditCategory.AUTH,
                metadata={"email": "a@bayflow.test"},
            ),
        )
        await uow.commit()
    async with db.sessionmaker() as session:
        return (await session.execute(select(AuditEvent))).scalar_one()


async def test_audit_rows_cannot_be_updated_or_deleted(db: Database) -> None:
    row = await one_row(db)
    for statement in (
        update(AuditEvent).where(AuditEvent.id == row.id).values(summary="Tampered."),
        text("DELETE FROM audit_events"),
        text("UPDATE audit_events SET metadata = '{}'::jsonb"),
    ):
        async with db.sessionmaker() as session:
            with pytest.raises(DBAPIError) as caught:
                await session.execute(statement)
            assert sqlstate(caught.value) == RAISE_EXCEPTION
            assert "audit_events is append-only" in str(caught.value.orig)
    async with db.sessionmaker() as session:
        unchanged = (await session.execute(select(AuditEvent))).scalar_one()
    assert (unchanged.summary, unchanged.metadata_) == (row.summary, {"email": "a@bayflow.test"})


async def test_the_trigger_is_installed_and_truncate_still_works(db: Database) -> None:
    await one_row(db)
    async with db.engine.begin() as connection:
        triggers = await connection.execute(
            text(
                "SELECT tgname FROM pg_trigger WHERE tgrelid = 'audit_events'::regclass"
                " AND NOT tgisinternal"
            )
        )
        assert [name for (name,) in triggers] == ["trg_audit_events_append_only"]
        await connection.execute(text("TRUNCATE audit_events"))
        count = await connection.execute(text("SELECT count(*) FROM audit_events"))
        assert count.scalar_one() == 0


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("category", "'NOPE'", "ck_audit_events_category"),
        ("actor_role", "'ROOT'", "ck_audit_events_actor_role"),
        ("target_type", "'PART'", "ck_audit_events_target_type"),
        ("action", "'Shop.Suspended'", "ck_audit_events_action_format"),
        ("action", "'suspended'", "ck_audit_events_action_format"),
        ("metadata", "'[]'::jsonb", "ck_audit_events_metadata_object"),
    ],
)
async def test_audit_checks(db: Database, column: str, value: str, constraint: str) -> None:
    values = {
        "category": "'AUTH'",
        "action": "'auth.login_failed'",
        "summary": "'x'",
        column: value,
    }
    columns = ", ".join(values)
    async with db.engine.begin() as connection:
        with pytest.raises(IntegrityError) as caught:
            await connection.execute(
                text(
                    f"INSERT INTO audit_events (id, occurred_at, {columns})"  # noqa: S608 - test literals
                    f" VALUES (gen_random_uuid(), now(), {', '.join(values.values())})"
                )
            )
    assert (constraint_name(caught.value), sqlstate(caught.value)) == (constraint, CHECK_VIOLATION)


@pytest.mark.parametrize(
    "fields",
    [
        {"suspended_at": WHEN},
        {"suspended_at": WHEN, "suspended_reason": "No reason by"},
        {"suspended_reason": "Reason only"},
    ],
)
async def test_a_suspension_is_complete_or_absent(db: Database, fields: dict[str, object]) -> None:
    admin = make_user()
    await add_rows(db.sessionmaker, admin)
    with pytest.raises(IntegrityError) as caught:
        await add_rows(db.sessionmaker, make_shop(**fields))
    assert constraint_name(caught.value) == "ck_shops_suspension_complete"
    complete = make_shop(
        suspended_at=WHEN, suspended_reason="Fraud report", suspended_by_user_id=admin.id
    )
    await add_rows(db.sessionmaker, complete)
    async with db.sessionmaker() as session:
        stored = await session.get(Shop, complete.id)
    assert stored is not None
    assert stored.is_suspended


async def test_users_default_to_not_platform_admin(db: Database) -> None:
    user = make_user()
    await add_rows(db.sessionmaker, user)
    async with db.engine.begin() as connection:
        flag = await connection.execute(
            text("SELECT is_platform_admin FROM users WHERE id = :id"), {"id": user.id}
        )
        assert flag.scalar_one() is False


async def test_the_platform_admin_revision_round_trips(
    db: Database, alembic_cli: AlembicCli
) -> None:
    # By name, not "-1": later expand-only revisions (e.g. 90a856e17478, text AI) sit on top.
    assert FEATURE_REVISION in await alembic_cli("history")
    downgraded = await alembic_cli("downgrade", BASELINE_REVISION)
    assert f"Running downgrade {FEATURE_REVISION} -> {BASELINE_REVISION}" in downgraded
    async with db.engine.begin() as connection:
        gone = await connection.execute(
            text(
                "SELECT to_regclass('public.audit_events') IS NULL,"
                " NOT EXISTS (SELECT 1 FROM information_schema.columns"
                "  WHERE table_name = 'users' AND column_name = 'is_platform_admin'),"
                " NOT EXISTS (SELECT 1 FROM information_schema.columns"
                "  WHERE table_name = 'shops' AND column_name LIKE 'suspended%')"
            )
        )
        assert tuple(gone.one()) == (True, True, True)
    upgraded = await alembic_cli("upgrade", "head")
    assert f"Running upgrade {BASELINE_REVISION} -> {FEATURE_REVISION}" in upgraded
    checked = await alembic_cli("check")
    assert "No new upgrade operations detected" in checked

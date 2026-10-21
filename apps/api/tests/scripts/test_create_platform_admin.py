"""`python -m app.scripts.create_platform_admin` (spec 19 §1, §9; D10, D94).

Idempotent bootstrap: a missing account is created and made a platform admin; an existing one is
only promoted (password, name and status untouched); a second run changes nothing. The password
comes from `PLATFORM_ADMIN_PASSWORD` or a prompt, follows the D10 policy and is never printed.
"""

import asyncio
import logging
import os
import sys
import uuid

import pytest
from pydantic import SecretStr

from app.core.database import Database
from app.core.errors import ValidationFailed
from app.modules.identity import service as identity_service
from app.modules.identity.schemas import UserRecord
from app.scripts import create_platform_admin as script
from tests.conftest import API_DIR, TEST_DATABASE_URL_STR
from tests.modules.admin.support import audit_rows
from tests.modules.identity.builders import TEST_PASSWORD, make_user, unique_email

ADMIN_PASSWORD = "Bootstrap-Secret-2026"


class Source:
    """A password source that counts how often the script asked for the password."""

    def __init__(self, password: str = ADMIN_PASSWORD) -> None:
        self.password = password
        self.calls = 0

    def __call__(self) -> SecretStr:
        self.calls += 1
        return SecretStr(self.password)


async def stored(db: Database, email: str) -> UserRecord | None:
    async with db.sessionmaker() as session:
        return await identity_service.find_user_by_email(session, email)


async def matches(db: Database, user_id: uuid.UUID, password: str) -> bool:
    async with db.sessionmaker() as session:
        return await identity_service.password_matches(
            session, user_id=user_id, password=SecretStr(password)
        )


@pytest.mark.db
async def test_creates_a_platform_admin_then_changes_nothing(
    db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    email = unique_email("zainab")
    with caplog.at_level(logging.INFO):
        assert (
            await script.run(email=email, full_name="Areeba Hashmi", password_source=Source()) == 0
        )
    admin = await stored(db, email)
    assert admin is not None
    assert (admin.full_name, admin.is_active, admin.is_platform_admin) == (
        "Areeba Hashmi",
        True,
        True,
    )
    assert await matches(db, admin.id, ADMIN_PASSWORD)
    (granted,) = await audit_rows(db)
    assert (granted.action, granted.actor_user_id, granted.actor_role) == (
        "user.platform_admin_granted",
        None,
        "SYSTEM",
    )
    assert (granted.ip, granted.user_agent, granted.request_id) == (None, None, None)
    second = Source()
    assert await script.run(email=email, full_name="Someone Else", password_source=second) == 0
    assert second.calls == 0  # an existing account needs no password
    assert len(await audit_rows(db)) == 1
    again = await stored(db, email)
    assert again is not None
    assert again.full_name == "Areeba Hashmi"
    assert ADMIN_PASSWORD not in caplog.text
    assert f"platform admin created: {email}" in caplog.text
    assert "already is a platform admin" in caplog.text


@pytest.mark.db
async def test_promotes_an_existing_account_without_touching_anything_else(db: Database) -> None:
    user = await make_user(db, full_name="Ali Raza", phone="+923001112233")
    assert (
        await script.run(email=user.email.upper(), full_name="Renamed", password_source=Source())
        == 0
    )
    promoted = await stored(db, user.email)
    assert promoted is not None
    assert (promoted.full_name, promoted.phone, promoted.is_platform_admin) == (
        "Ali Raza",
        "+923001112233",
        True,
    )
    assert await matches(db, user.id, TEST_PASSWORD)  # the old password still works
    assert not await matches(db, user.id, ADMIN_PASSWORD)


@pytest.mark.db
async def test_a_password_outside_the_policy_creates_nothing(
    db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    email = unique_email("weak")
    with pytest.raises(ValidationFailed) as caught:
        await script.run(email=email, full_name="Weak Password", password_source=Source("short"))
    assert caught.value.errors is not None
    assert caught.value.errors[0]["field"] == "password"
    assert await stored(db, email) is None
    assert await audit_rows(db) == []


@pytest.mark.db
async def test_the_cli_reads_the_environment_and_never_prints_the_password(db: Database) -> None:
    email = unique_email("cli")
    environment = {
        **os.environ,
        "DATABASE_URL": TEST_DATABASE_URL_STR,
        "PLATFORM_ADMIN_PASSWORD": ADMIN_PASSWORD,
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.scripts.create_platform_admin",
        "--email",
        email,
        "--full-name",
        "Cli Admin",
        cwd=API_DIR,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await process.communicate()
    text = output.decode()
    assert process.returncode == 0, text
    assert ADMIN_PASSWORD not in text
    assert "platform admin created" in text
    admin = await stored(db, email)
    assert admin is not None
    assert admin.is_platform_admin
    weak = {**environment, "PLATFORM_ADMIN_PASSWORD": "tiny"}
    failing = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.scripts.create_platform_admin",
        "--email",
        unique_email("cli-weak"),
        "--full-name",
        "Weak",
        cwd=API_DIR,
        env=weak,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    failed_output, _ = await failing.communicate()
    assert failing.returncode == 1
    assert "tiny" not in failed_output.decode()
    assert "at least 12 characters" in failed_output.decode()


def test_the_password_comes_from_the_environment_or_a_double_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLATFORM_ADMIN_PASSWORD", ADMIN_PASSWORD)
    assert script.read_password(lambda _: "unused").get_secret_value() == ADMIN_PASSWORD
    monkeypatch.delenv("PLATFORM_ADMIN_PASSWORD")
    answers = iter(["typed-password-1", "typed-password-1"])
    assert script.read_password(lambda _: next(answers)).get_secret_value() == "typed-password-1"
    different = iter(["typed-password-1", "typed-password-2"])
    with pytest.raises(script.PasswordMismatchError):
        script.read_password(lambda _: next(different))


def test_an_invalid_email_is_a_usage_error() -> None:
    assert script.main(["--email", "not-an-email", "--full-name", "Nobody"]) == script.EXIT_USAGE

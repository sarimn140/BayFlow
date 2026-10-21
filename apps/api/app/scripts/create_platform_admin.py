"""Bootstrap a platform admin (D94, spec 19 §1):
`python -m app.scripts.create_platform_admin --email … --full-name …`.

Idempotent. A missing account is created and made a platform admin; an existing account is only
promoted — its password, name and status never change; an account that already is an admin is
left alone. The password is needed only to create an account: it comes from the
`PLATFORM_ADMIN_PASSWORD` environment variable, else from a hidden prompt (asked twice), and must
follow the D10 policy (12-128 characters). It is never printed or logged.

Everything goes through the identity service (`seed-through-services`), on a unit of work wired
like the API (`create_app()`), so the grant is recorded in the audit log as a `SYSTEM` action;
a script has no request, so the row's IP, user agent and request id are empty (spec 19 §3.2).
Exit code 0 on success, 1 on any failure, 2 for invalid arguments.
"""

import argparse
import asyncio
import getpass
import logging
import os
import sys
from collections.abc import Callable, Sequence

from pydantic import SecretStr

from app.core.config import get_settings
from app.core.database import Database
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.main import create_app
from app.modules.identity import service as identity_service
from app.shared.email import normalize_email
from app.shared.uow import UnitOfWork

PASSWORD_ENV = "PLATFORM_ADMIN_PASSWORD"  # noqa: S105 - the variable's name, not a password
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

logger = logging.getLogger("app.scripts.create_platform_admin")

type PasswordSource = Callable[[], SecretStr]


class PasswordMismatchError(ValueError):
    """The two prompted passwords differ."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.create_platform_admin",
        description=(
            "Create a BayFlow platform admin, or promote an existing account (D94). The password "
            f"of a new account is read from {PASSWORD_ENV} or prompted for."
        ),
    )
    parser.add_argument("--email", required=True, help="the admin's e-mail (login)")
    parser.add_argument("--full-name", required=True, help="the admin's full name")
    return parser.parse_args(argv)


def read_password(prompt: Callable[[str], str] = getpass.getpass) -> SecretStr:
    """`PLATFORM_ADMIN_PASSWORD`, else a hidden prompt asked twice (never echoed)."""
    from_env = os.environ.get(PASSWORD_ENV)
    if from_env:
        return SecretStr(from_env)
    first = prompt("Password for the new platform admin: ")
    if prompt("Repeat the password: ") != first:
        msg = "the two passwords differ"
        raise PasswordMismatchError(msg)
    return SecretStr(first)


def _problem(error: AppError) -> str:
    """The error's detail and field messages; never the submitted values."""
    fields = "; ".join(f"{item['field']}: {item['message']}" for item in error.errors or [])
    return f"{error.detail} {fields}".strip()


async def run(*, email: str, full_name: str, password_source: PasswordSource) -> int:
    """Create or promote the account (one transaction) and log what happened."""
    settings = get_settings()
    bus = create_app(settings).state.event_bus  # ports and handlers wired like the API (D89)
    database = Database.from_settings(settings)
    try:
        async with database.sessionmaker() as session:
            existing = await identity_service.find_user_by_email(session, email)
        password = None if existing is not None else password_source()
        async with database.sessionmaker() as session:
            user, created, promoted = await identity_service.bootstrap_platform_admin(
                UnitOfWork(session, bus), email=email, full_name=full_name, password=password
            )
    finally:
        await database.dispose()
    if created:
        logger.info("platform admin created: %s", user.email)
    elif promoted:
        logger.info("existing account promoted to platform admin: %s", user.email)
    else:
        logger.info("%s already is a platform admin; nothing changed", user.email)
    if not user.is_active:
        logger.warning("%s is deactivated and cannot sign in until reactivated", user.email)
    return EXIT_OK


def main(argv: Sequence[str] | None = None, *, prompt: PasswordSource | None = None) -> int:
    args = parse_args(argv)
    configure_logging(get_settings().log_level)
    try:
        email = normalize_email(args.email.strip())
    except ValueError as exc:
        logger.error("invalid --email: %s", exc)
        return EXIT_USAGE
    try:
        return asyncio.run(
            run(email=email, full_name=args.full_name, password_source=prompt or read_password)
        )
    except PasswordMismatchError as exc:
        logger.error("%s; nothing was created", exc)
    except AppError as exc:
        logger.error("platform admin not created: %s", _problem(exc))
    except Exception:
        logger.exception("platform admin bootstrap failed")
    return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())

"""Events the identity module publishes (spec 19 §3.3, D95).

They exist for the platform audit log: the `audit` module subscribes to every one of them and
writes one `audit_events` row **in the publisher's transaction**, so the row commits with the
change or not at all (spec 01 "Event bus"). Identity never imports `audit` (spec 19 §3.2).

- `LoginSucceeded`, `LoginFailed`, `LoginRateLimited`: `POST /api/v1/auth/login`. A failed or
  rate-limited attempt is committed on its own before the 401 / 429 is raised, so it is recorded
  although the login fails (`service.login`); the booking wizard's nested credential check
  (`authenticate`) publishes nothing and never commits.
- `LoggedOut`: `POST /api/v1/auth/logout` when its cookie or Bearer token names an active user.
- `OwnerRegistered`, `CustomerAccountCreated`: owner sign-up and the wizard's new account (D32).
- `UserActiveChanged`, `PlatformAdminChanged`: a platform admin's account levers (D94); the
  seed's reconciliation (D60) and the bootstrap script publish them with no actor (`SYSTEM`).

Payloads are ids, enums and primitives only (spec 01 event rule 8); e-mails are the normalised,
lower-cased form (D62). Never a password, a token or a hash.
"""

from dataclasses import dataclass
from uuid import UUID

from app.shared.event_bus import Event


@dataclass(frozen=True, slots=True, kw_only=True)
class LoginSucceeded(Event):
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class LoginFailed(Event):
    """Unknown e-mail, wrong password or inactive account (identical 401s, spec 04)."""

    email: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LoginRateLimited(Event):
    """The per-account failure limiter refused the attempt (429, D69)."""

    email: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LoggedOut(Event):
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class OwnerRegistered(Event):
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomerAccountCreated(Event):
    """The booking wizard created the account of a new customer (D32 case B)."""

    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class UserActiveChanged(Event):
    """`actor_user_id` is the platform admin, or None for the seed's reconciliation (SYSTEM);
    `reason` is set when an admin deactivates the account."""

    user_id: UUID
    is_active: bool
    actor_user_id: UUID | None
    reason: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PlatformAdminChanged(Event):
    """`actor_user_id` is the granting or revoking admin, or None for the bootstrap script."""

    user_id: UUID
    is_platform_admin: bool
    actor_user_id: UUID | None

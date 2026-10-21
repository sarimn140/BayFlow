"""Schemas of the identity module (spec 03 §3.1, §3.2, §4.3; `modules/identity.md` §4).

Wire schemas: `OwnerRegistrationCreate` and `SessionCreate` (requests, `extra="forbid"`, so `role`,
`shop_id` or `memberships` can never be smuggled in, SEC-16/SEC-17), `UserRead` (the account
without memberships, D81), `SessionToken` and `SessionRead` (login and owner registration), and
the reference `UserRef` other modules use for actors and authors.

Internal: `UserRecord` = `UserRead` + `is_active` + `is_platform_admin` (D94), the user other
modules (and `app.shared.auth`) receive from the look-ups; `UserAdminRecord` adds the timestamps
the platform admin lists show, `UserAdminQuery` / `UserStats` are the admin ports' query and
counts (spec 19 §4 E-61, E-66). `password_hash` never leaves this module.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, Secret, StringConstraints

from app.core.security import MAX_PASSWORD_LENGTH, Password
from app.shared.email import Email
from app.shared.phone import Phone

FULL_NAME_MAX_LENGTH = 120

FullName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=FULL_NAME_MAX_LENGTH),
]
"""A person's name: trimmed, not blank, at most 120 characters (`users.full_name`)."""

LoginPassword = Annotated[
    Secret[Annotated[str, StringConstraints(min_length=1, max_length=MAX_PASSWORD_LENGTH)]],
    Field(json_schema_extra={"format": "password", "writeOnly": True}),
]
"""The password typed at login: 1-128 characters, never trimmed (the D10 policy applies to new
passwords only, spec 03 §4.3)."""


# --- Requests -------------------------------------------------------------------------------------


class OwnerRegistrationCreate(BaseModel):
    """`POST /api/v1/auth/register-owner` (D17): creates a bare user, never a membership."""

    model_config = ConfigDict(extra="forbid")

    full_name: FullName
    email: Email
    password: Password
    phone: Phone | None = None


class SessionCreate(BaseModel):
    """`POST /api/v1/auth/login`."""

    model_config = ConfigDict(extra="forbid")

    email: Email
    password: LoginPassword


# --- Responses ------------------------------------------------------------------------------------


class UserRead(BaseModel):
    """The account itself, without memberships (spec 03 §3.2, D81). Never `password_hash`."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None


class SessionToken(BaseModel):
    """The token part of a session response (D8): also embedded by the booking wizard (D32)."""

    access_token: str
    token_type: Literal["bearer"]
    expires_in: int = Field(description="Token lifetime in seconds (`JWT_EXPIRES_IN`).")


class SessionRead(SessionToken):
    """Login and owner registration (D81): the token fields and the `user`, no memberships."""

    user: UserRead


class UserRef(BaseModel):
    """An actor or author (spec 03 §3.1)."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    full_name: str


# --- Internal -------------------------------------------------------------------------------------


class UserRecord(UserRead):
    """A user as other modules see it: the wire fields plus `is_active` and `is_platform_admin`
    (internal, never sent as such).

    A subclass of `UserRead`, so a record can be passed wherever the wire type is expected; Pydantic
    serialises a field typed `UserRead` with the parent's fields only.
    """

    is_active: bool
    is_platform_admin: bool = False  # the safe default for records built by hand (D94)


class UserAdminRecord(UserRecord):
    """A user as the platform admin console lists it (spec 19 §4 E-66): the record plus its
    creation and last sign-in instants."""

    created_at: datetime
    last_login_at: datetime | None


UserAdminSort = Literal["-created_at", "name", "-last_login_at"]
"""E-66's sort allowlist: newest first (default), name (case-insensitive), latest sign-in first."""


@dataclass(frozen=True, slots=True)
class UserAdminQuery:
    """One page of the admin's user list (E-66). `q` matches the name, the e-mail or the phone;
    `only_ids` / `excluded_ids` restrict the users to, or exclude, a set of ids (the admin module
    passes the users with an active membership: identity never reads memberships, D81)."""

    q: str | None = None
    is_active: bool | None = None
    is_platform_admin: bool | None = None
    only_ids: frozenset[uuid.UUID] | None = None
    excluded_ids: frozenset[uuid.UUID] | None = None
    sort: UserAdminSort = "-created_at"
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True, slots=True)
class UserStats:
    """Platform-wide account counts (E-61): every account, those with the platform-admin flag,
    the deactivated ones and those created at or after the given instant."""

    total: int
    platform_admins: int
    inactive: int
    created_since: int


def to_user_read(user: UserRead) -> UserRead:
    """The wire `UserRead` of a record (drops the internal fields explicitly)."""
    return UserRead(id=user.id, email=user.email, full_name=user.full_name, phone=user.phone)

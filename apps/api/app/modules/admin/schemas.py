"""Schemas of the admin module (spec 19 §4, E-61…E-75; D94-D97).

Requests (`extra="forbid"`): `ShopSuspendRequest`, `UserDeactivateRequest` — a reason of 5-500
characters for every lever that restricts someone (spec 19 §1).

Responses: `PlatformOverviewRead` (E-61), `AdminShopRow` (E-62), `AdminShopDetail` (E-63-E-65),
`AdminUserRow` (E-66), `AdminUserDetail` (E-67-E-71). The booking and audit projections belong to
their modules and are re-exported here for the router: `AdminBookingSummary`,
`AdminBookingDetail`, `AdminBookingFilters`, `AdminBookingSort` (bookings), `AuditEventRead`,
`AuditFilters`, `AuditSort` (audit), `ShopRead` (shops), `UserAdminSort` (identity), and the
query `QueryDate` (scheduling, through bookings).

The admin module owns no table (D97): these are compositions of the other modules' records.
"""

import datetime as dt
from enum import StrEnum
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.modules.admin.domain.phases import StatusPhase
from app.modules.audit.schemas import AuditEventRead, AuditFilters, AuditSort
from app.modules.bookings.schemas import (
    AdminBookingDetail,
    AdminBookingFilters,
    AdminBookingSort,
    AdminBookingSummary,
    QueryDate,
)
from app.modules.identity.schemas import UserAdminSort
from app.modules.shops.schemas import ShopRead
from app.shared.enums import MembershipRole
from app.shared.timestamps import Timestamp

__all__ = [
    "REASON_MAX_LENGTH",
    "REASON_MIN_LENGTH",
    "SEARCH_MAX_LENGTH",
    "AdminBookingDetail",
    "AdminBookingFilters",
    "AdminBookingSort",
    "AdminBookingSummary",
    "AdminMemberRead",
    "AdminMembershipRead",
    "AdminShopDetail",
    "AdminShopRef",
    "AdminShopRow",
    "AdminShopSort",
    "AdminShopStatus",
    "AdminUserDetail",
    "AdminUserKind",
    "AdminUserRef",
    "AdminUserRow",
    "AdminUserStatus",
    "AuditEventRead",
    "AuditFilters",
    "AuditSort",
    "BookingCounts",
    "CustomerBookings",
    "DayCount",
    "PhaseCount",
    "PlatformOverviewRead",
    "QueryDate",
    "RoleMembers",
    "ShopCounts",
    "ShopRead",
    "ShopSuspendRequest",
    "ShopSuspensionRead",
    "TopShop",
    "UserAdminSort",
    "UserCounts",
    "UserDeactivateRequest",
]

REASON_MIN_LENGTH: Final = 5
REASON_MAX_LENGTH: Final = 500
SEARCH_MAX_LENGTH: Final = 100

Reason = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=REASON_MIN_LENGTH, max_length=REASON_MAX_LENGTH
    ),
]
"""Why a shop is suspended or an account deactivated: 5-500 characters, trimmed (spec 19 §1)."""


class AdminShopStatus(StrEnum):
    """E-62 `status` filter: suspended or not (D96)."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class AdminUserKind(StrEnum):
    """E-66 `kind` filter: `CUSTOMER` = no active membership, `STAFF` = at least one,
    `PLATFORM_ADMIN` = the flag (D94). A platform admin without memberships is also a customer."""

    CUSTOMER = "CUSTOMER"
    STAFF = "STAFF"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"


class AdminUserStatus(StrEnum):
    """E-66 `status` filter: the account's `is_active` (D9)."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


AdminShopSort = Literal["-created_at", "name", "-bookings_30d"]
"""E-62's sorts: newest first (default), name, most bookings in the last 30 days first."""


# --- Requests -----------------------------------------------------------------------------------


class ShopSuspendRequest(BaseModel):
    """E-64: suspend a shop (D96). Its staff are locked out at their next request."""

    model_config = ConfigDict(extra="forbid")

    reason: Reason


class UserDeactivateRequest(BaseModel):
    """E-68: deactivate an account; its tokens stop working at its next request (D9)."""

    model_config = ConfigDict(extra="forbid")

    reason: Reason


# --- References ---------------------------------------------------------------------------------


class AdminShopRef(BaseModel):
    """A shop in admin lists."""

    id: UUID
    slug: str
    name: str


class AdminUserRef(BaseModel):
    """A person in admin views: name and e-mail."""

    user_id: UUID
    full_name: str
    email: str


class ShopSuspensionRead(BaseModel):
    """A shop's suspension (D96): when, why and by which platform admin."""

    at: Timestamp
    reason: str
    by: AdminUserRef | None


# --- E-61 ----------------------------------------------------------------------------------------


class ShopCounts(BaseModel):
    """`active` = not suspended; `listed` = the `is_listed` flag; `new_30d` = created in the last 30
    local days."""

    total: int
    active: int
    suspended: int
    listed: int
    new_30d: int


class UserCounts(BaseModel):
    """`customers` = accounts without an active membership, `staff` = with one, `platform_admins`
    = the flag (any status), `inactive` = deactivated accounts, `new_30d` = created in the last 30
    local days."""

    total: int
    customers: int
    staff: int
    platform_admins: int
    inactive: int
    new_30d: int


class PhaseCount(BaseModel):
    phase: StatusPhase
    count: int


class BookingCounts(BaseModel):
    """`today`, `last_7_days`, `last_30_days`: bookings **placed** (created) on those local days;
    `open`: not completed or cancelled, now; `completed_30d` / `cancelled_30d`: completed /
    cancelled in the last 30 local days; `open_by_phase`: open bookings per phase, every phase."""

    today: int
    last_7_days: int
    last_30_days: int
    open: int
    completed_30d: int
    cancelled_30d: int
    open_by_phase: list[PhaseCount]


class DayCount(BaseModel):
    date: dt.date
    count: int


class TopShop(BaseModel):
    shop: AdminShopRef
    bookings_30d: int


class PlatformOverviewRead(BaseModel):
    """E-61 (A-01): platform KPIs. "Today" and the 14-day series are local dates in the shops'
    default time zone (`Asia/Karachi`, D38); `bookings_per_day` runs oldest first to today."""

    generated_at: Timestamp
    timezone: str
    today: dt.date
    shops: ShopCounts
    users: UserCounts
    bookings: BookingCounts
    bookings_per_day: list[DayCount]
    top_shops: list[TopShop]
    latest_audit_events: list[AuditEventRead]


# --- E-62 - E-65 ---------------------------------------------------------------------------------


class AdminShopRow(BaseModel):
    """An E-62 row (A-02)."""

    shop: AdminShopRef
    city: str
    created_at: Timestamp
    is_listed: bool
    suspension: ShopSuspensionRead | None
    owners: list[AdminUserRef]
    active_members: int
    bookings_30d: int


class AdminMemberRead(BaseModel):
    membership_id: UUID
    user_id: UUID
    full_name: str
    email: str
    is_active: bool


class RoleMembers(BaseModel):
    """The shop's memberships of one role, active or not, by name."""

    role: MembershipRole
    members: list[AdminMemberRead]


class AdminShopDetail(BaseModel):
    """E-63 (A-03), also the answer of E-64 / E-65: the profile, the suspension, the team by role
    (every role, glossary order), all bookings per phase, the 10 newest bookings and the 10 newest
    audit events of the shop."""

    shop: ShopRead
    suspension: ShopSuspensionRead | None
    owners: list[AdminUserRef]
    members_by_role: list[RoleMembers]
    booking_counts_by_phase: list[PhaseCount]
    latest_bookings: list[AdminBookingSummary]
    latest_audit_events: list[AuditEventRead]


# --- E-66 - E-71 ---------------------------------------------------------------------------------


class AdminMembershipRead(BaseModel):
    membership_id: UUID
    shop: AdminShopRef
    role: MembershipRole
    is_active: bool


class AdminUserRow(BaseModel):
    """An E-66 row (A-04): the account and every membership, active or not."""

    id: UUID
    full_name: str
    email: str
    phone: str | None
    is_active: bool
    is_platform_admin: bool
    created_at: Timestamp
    last_login_at: Timestamp | None
    memberships: list[AdminMembershipRead]


class CustomerBookings(BaseModel):
    """The person's bookings as a customer: how many, and the 10 newest."""

    count: int
    latest: list[AdminBookingSummary]


class AdminUserDetail(BaseModel):
    """E-67 (A-05), also the answer of E-68 - E-71: the account, its bookings as a customer and
    the 10 newest audit events done by or about it."""

    user: AdminUserRow
    bookings_as_customer: CustomerBookings
    latest_audit_events: list[AuditEventRead]

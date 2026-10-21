"""Schemas of the shops module (spec 03 §3.1, §3.2, §4.4, §4.5, §4.9; `modules/shops.md` §4).

Requests (`extra="forbid"`, SEC-17): `ShopCreate`, `ShopUpdate`, `WorkingHoursWrite`,
`WorkingHoursUpdate`, `MemberCreate`, `MemberUpdate`, `ServiceCreate`, `ServiceUpdate`. Text is
trimmed; required text must not be blank; a blank optional text becomes `null` (spec 03 §1.5). In a
PATCH an omitted field is unchanged, `null` clears a nullable field and is refused for the others.

Responses: `ShopRead`, `WorkingHoursRead`, `ShopPublicSummary`, `ServiceBrief`, `ShopPublicDetail`,
`ServiceRead`, `MemberRead`, `MemberCreatedRead`, `MeRead`, `MembershipRead`, `MemberRef` (list
envelopes `Page` and `ItemList` are the shared ones of `app.shared.pagination`).

Internal records other modules receive: `MembershipRecord`, `ShopBrief`, `ServiceSnapshot`,
`TeamMember`, `SetupFlags`; for the platform admin (spec 19, D94-D96): `ShopSuspension`,
`UserContact`, `AdminShopQuery`, `AdminShopRecord`, `AdminMembershipRecord`, `ShopStats`.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from app.core.security import Password
from app.modules.identity.schemas import FullName, UserRead
from app.modules.shops.domain.capabilities import Capability
from app.modules.shops.domain.grid import DEFAULT_TIMEZONE, WorkingDay, is_valid_timezone
from app.shared.email import Email
from app.shared.enums import MembershipRole
from app.shared.money import Money
from app.shared.phone import Phone
from app.shared.timestamps import Timestamp

# Limits = column sizes (spec 02 §3.2-§3.5, spec 03 §4.9).
SHOP_NAME_MAX_LENGTH = 120
ADDRESS_MAX_LENGTH = 255
CITY_MAX_LENGTH = 80
TIMEZONE_MAX_LENGTH = 64
LOGO_URL_MAX_LENGTH = 2048
SERVICE_NAME_MAX_LENGTH = 120
SERVICE_DESCRIPTION_MAX_LENGTH = 1000
SEARCH_MAX_LENGTH = 100

HHMM_PATTERN = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
_HHMM = re.compile(HHMM_PATTERN)
_HTTPS_PREFIX = "https://"
_NULL_REFUSED = "This field cannot be null."
_NOTHING_TO_CHANGE = "Send at least one field to change."


def _blank_to_none(value: str | None) -> str | None:
    """After trimming, an empty optional text means "no value" (spec 03 §1.5)."""
    return value or None


def _null_means_default(default: object) -> BeforeValidator:
    """Spec 03 §1.5: an optional request field may be omitted or sent as `null`; both mean
    "use the default", so the validated value is never None."""

    def replace(value: object) -> object:
        return default if value is None else value

    return BeforeValidator(replace)


def _nullable_in_schema(schema: dict[str, Any]) -> None:
    """Document `null` as accepted next to the field's own type (the default stays)."""
    kept = {"default", "title", "description", "examples"}
    own_type = {key: schema.pop(key) for key in list(schema) if key not in kept}
    schema["anyOf"] = [own_type, {"type": "null"}]


def _known_timezone(value: str) -> str:
    if not is_valid_timezone(value):
        msg = "Unknown time zone: use an IANA name such as Asia/Karachi."
        raise ValueError(msg)
    return value


def _https_url(value: str) -> str:
    """D55: an absolute `https://` URL, scheme stored lower-case (`ck_shops_logo_url_https`)."""
    if value[: len(_HTTPS_PREFIX)].lower() == _HTTPS_PREFIX:
        value = _HTTPS_PREFIX + value[len(_HTTPS_PREFIX) :]
    if not value.startswith(_HTTPS_PREFIX) or any(char.isspace() for char in value):
        msg = "Use an absolute https:// URL."
        raise ValueError(msg)
    if not urlsplit(value).netloc:
        msg = "Use an absolute https:// URL with a host name."
        raise ValueError(msg)
    return value


def _parse_wall_clock(value: object) -> object:
    """`HH:MM`, 24-hour, no seconds (spec 03 §1.5) → `datetime.time`."""
    if value is None or isinstance(value, time):
        return value
    if isinstance(value, str) and _HHMM.fullmatch(value):
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    msg = "Use the 24-hour HH:MM format, e.g. 09:00."
    raise ValueError(msg)


def format_wall_clock(moment: time | None) -> str | None:
    """The wire form of a working-hours time: `"09:00"`."""
    return None if moment is None else f"{moment.hour:02d}:{moment.minute:02d}"


ShopName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=SHOP_NAME_MAX_LENGTH),
]
Address = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ADDRESS_MAX_LENGTH)
]
City = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=CITY_MAX_LENGTH)
]
Timezone = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=TIMEZONE_MAX_LENGTH),
    AfterValidator(_known_timezone),
    Field(examples=[DEFAULT_TIMEZONE], description="IANA time-zone name (D38)."),
]
SlotDuration = Annotated[
    int,
    Field(ge=15, le=240, multiple_of=15, description="Slot length; the grid starts at midnight."),
]
SlotCapacity = Annotated[int, Field(ge=1, le=50, description="Bookings allowed per slot.")]
LogoUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=LOGO_URL_MAX_LENGTH),
    AfterValidator(_https_url),
]
WallClock = Annotated[
    time | None,
    BeforeValidator(_parse_wall_clock),
    WithJsonSchema(
        {
            "anyOf": [
                {"type": "string", "pattern": HHMM_PATTERN, "examples": ["09:00"]},
                {"type": "null"},
            ]
        }
    ),
]
"""A shop-local wall-clock time `HH:MM` (24-hour) or null."""

ServiceName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=SERVICE_NAME_MAX_LENGTH),
]
ServiceDescription = Annotated[
    Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=SERVICE_DESCRIPTION_MAX_LENGTH)
    ]
    | None,
    AfterValidator(_blank_to_none),
]
ServiceDuration = Annotated[
    int, Field(ge=5, le=10_080, description="Estimated duration in minutes (informational).")
]
SearchText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=SEARCH_MAX_LENGTH)]


class StaffRole(StrEnum):
    """`MembershipRole` without `OWNER`: the roles an Owner can assign (glossary §2.1, D19)."""

    SERVICE_ADVISOR = "SERVICE_ADVISOR"
    TECHNICIAN = "TECHNICIAN"
    PARTS_PERSON = "PARTS_PERSON"
    QC_INSPECTOR = "QC_INSPECTOR"

    @property
    def membership_role(self) -> MembershipRole:
        return MembershipRole(self.value)


# --- Requests -------------------------------------------------------------------------------------


class WorkingHoursWrite(BaseModel):
    """One weekday of a week (request). Open day: both times, on the slot grid, closing after
    opening (checked against the shop's slot duration by the service). Closed day: times ignored."""

    model_config = ConfigDict(extra="forbid")

    weekday: Annotated[int, Field(ge=0, le=6, description="0 = Monday … 6 = Sunday.")]
    is_closed: bool
    opens_at: WallClock = None
    closes_at: WallClock = None

    def to_working_day(self) -> WorkingDay:
        if self.is_closed:
            return WorkingDay.closed(self.weekday)
        return WorkingDay(
            weekday=self.weekday,
            is_closed=False,
            opens_at=self.opens_at,
            closes_at=self.closes_at,
        )


WeekWrite = Annotated[
    list[WorkingHoursWrite],
    Field(min_length=7, max_length=7, description="Exactly 7 entries, one per weekday."),
]


class WorkingHoursUpdate(BaseModel):
    """`PUT /api/v1/shops/{shop_id}/working-hours`: replaces the whole week."""

    model_config = ConfigDict(extra="forbid")

    working_hours: WeekWrite


class ShopCreate(BaseModel):
    """`POST /api/v1/shops`: the shop, its 7 working-hours rows and the caller's `OWNER`
    membership, in one transaction. `slug` and `rating` are not accepted (D56, D68). `timezone`
    and `is_listed` omitted or `null` take their defaults (`Asia/Karachi`, D38; `true`)."""

    model_config = ConfigDict(extra="forbid")

    name: ShopName
    address: Address
    city: City
    phone: Phone
    logo_url: LogoUrl | None = None
    timezone: Annotated[Timezone, _null_means_default(DEFAULT_TIMEZONE)] = Field(
        default=DEFAULT_TIMEZONE, json_schema_extra=_nullable_in_schema
    )
    slot_duration_minutes: SlotDuration
    slot_capacity: SlotCapacity
    is_listed: Annotated[bool, _null_means_default(True)] = Field(
        default=True, json_schema_extra=_nullable_in_schema
    )
    working_hours: WeekWrite


class ShopUpdate(BaseModel):
    """`PATCH /api/v1/shops/{shop_id}` (at least one field). `logo_url: null` clears the logo.

    Changing `slot_duration_minutes` or `timezone` is refused with 409 while the shop has future
    bookings (D37); capacity and listing changes are always allowed.
    """

    model_config = ConfigDict(extra="forbid")

    name: ShopName | None = None
    address: Address | None = None
    city: City | None = None
    phone: Phone | None = None
    logo_url: LogoUrl | None = None
    is_listed: bool | None = None
    slot_duration_minutes: SlotDuration | None = None
    slot_capacity: SlotCapacity | None = None
    timezone: Timezone | None = None

    @field_validator(
        "name",
        "address",
        "city",
        "phone",
        "is_listed",
        "slot_duration_minutes",
        "slot_capacity",
        "timezone",
    )
    @classmethod
    def _refuse_null(cls, value: object) -> object:
        if value is None:
            raise ValueError(_NULL_REFUSED)
        return value

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(_NOTHING_TO_CHANGE)
        return self


class MemberCreate(BaseModel):
    """`POST /api/v1/shops/{shop_id}/members` (D18). New e-mail: `password` is required and the
    account is created. Existing e-mail: only the membership is created; the password, name and
    phone in the body are ignored and the account is never modified."""

    model_config = ConfigDict(extra="forbid")

    email: Email
    full_name: FullName
    role: StaffRole
    password: Password | None = None
    phone: Phone | None = None


class MemberUpdate(BaseModel):
    """`PATCH /api/v1/shops/{shop_id}/members/{membership_id}` (D19, at least one field)."""

    model_config = ConfigDict(extra="forbid")

    role: StaffRole | None = None
    is_active: bool | None = None

    @field_validator("role", "is_active")
    @classmethod
    def _refuse_null(cls, value: object) -> object:
        if value is None:
            raise ValueError(_NULL_REFUSED)
        return value

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(_NOTHING_TO_CHANGE)
        return self


class ServiceCreate(BaseModel):
    """`POST /api/v1/shops/{shop_id}/services`. `base_price` null = "Price after inspection";
    `is_active` omitted or `null` = `true`."""

    model_config = ConfigDict(extra="forbid")

    name: ServiceName
    description: ServiceDescription = None
    estimated_duration_minutes: ServiceDuration
    base_price: Money | None = None
    is_active: Annotated[bool, _null_means_default(True)] = Field(
        default=True, json_schema_extra=_nullable_in_schema
    )


class ServiceUpdate(BaseModel):
    """`PATCH /api/v1/shops/{shop_id}/services/{service_id}` (at least one field).

    `description` and `base_price` are nullable; deactivating hides the service from the
    directory and the wizard, and existing bookings keep their snapshot (D34).
    """

    model_config = ConfigDict(extra="forbid")

    name: ServiceName | None = None
    description: ServiceDescription = None
    estimated_duration_minutes: ServiceDuration | None = None
    base_price: Money | None = None
    is_active: bool | None = None

    @field_validator("name", "estimated_duration_minutes", "is_active")
    @classmethod
    def _refuse_null(cls, value: object) -> object:
        if value is None:
            raise ValueError(_NULL_REFUSED)
        return value

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(_NOTHING_TO_CHANGE)
        return self


# --- Responses ------------------------------------------------------------------------------------


class WorkingHoursRead(BaseModel):
    """One weekday, Monday (0) first; times `HH:MM` shop-local, `null` on closed days."""

    weekday: int
    is_closed: bool
    opens_at: str | None
    closes_at: str | None


class ShopRead(BaseModel):
    """The staff view of a shop (spec 03 §3.2). `has_future_bookings` tells the settings form that
    slot duration and timezone are locked (D37)."""

    id: uuid.UUID
    slug: str
    name: str
    address: str
    city: str
    phone: str
    timezone: str
    slot_duration_minutes: int
    slot_capacity: int
    logo_url: str | None
    rating: float | None = Field(description="Placeholder rating, one decimal; null = New (D56).")
    is_listed: bool
    has_future_bookings: bool
    working_hours: list[WorkingHoursRead]
    created_at: Timestamp
    updated_at: Timestamp


class ServiceBrief(BaseModel):
    """An active service as the directory lists it."""

    id: uuid.UUID
    name: str


class ShopPublicSummary(BaseModel):
    """A directory entry (D64): listed shops with at least one active service."""

    id: uuid.UUID
    slug: str
    name: str
    city: str
    logo_url: str | None
    rating: float | None
    services: list[ServiceBrief]
    services_count: int


class ServiceRead(BaseModel):
    """A catalogue entry; `base_price` null = "Price after inspection"."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    estimated_duration_minutes: int
    base_price: Money | None
    is_active: bool
    created_at: Timestamp
    updated_at: Timestamp


class ShopPublicDetail(BaseModel):
    """The public page of a listed shop; `is_bookable` = at least one active service (D64)."""

    id: uuid.UUID
    slug: str
    name: str
    address: str
    city: str
    phone: str
    logo_url: str | None
    rating: float | None
    timezone: str
    slot_duration_minutes: int
    working_hours: list[WorkingHoursRead]
    services: list[ServiceRead]
    is_bookable: bool


class MemberRead(BaseModel):
    """A membership with its account (spec 03 §3.2). `open_jobs` = bookings not ready, completed
    or cancelled where the member is the technician, the parts person or the current QC picker."""

    membership_id: uuid.UUID
    user: UserRead
    role: MembershipRole
    is_active: bool
    open_jobs: int
    created_at: Timestamp
    updated_at: Timestamp


class MemberCreatedRead(MemberRead):
    """`account_created: false` = an existing account was attached; only the membership was
    created and the person signs in with their existing password (D18)."""

    account_created: bool


class MembershipRead(BaseModel):
    """One active membership of the caller (spec 04 `/me`, D66). `shop_suspended`: the shop is
    suspended by BayFlow (D96), so the POS can show it without calling a blocked route."""

    membership_id: uuid.UUID
    shop_id: uuid.UUID
    shop_name: str
    shop_slug: str
    shop_suspended: bool
    role: MembershipRole
    capabilities: list[Capability]


class MeRead(UserRead):
    """`GET /api/v1/me`: the account and its **active** memberships, sorted by shop name (D66).
    `is_platform_admin` opens the admin console (D94, spec 19 §4)."""

    is_platform_admin: bool
    memberships: list[MembershipRead]


class MemberRef(BaseModel):
    """An assignee (spec 03 §3.1); `is_active` is the membership in this shop (D19)."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    full_name: str
    is_active: bool


# --- Internal records (other modules; never on the wire) -----------------------------------------


class MembershipRecord(BaseModel):
    """A user's membership (one role) in one shop."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    shop_id: uuid.UUID
    user_id: uuid.UUID
    role: MembershipRole
    is_active: bool


class ShopBrief(BaseModel):
    """The shop facts other modules show (names, contact, timezone, listing, suspension)."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: uuid.UUID
    slug: str
    name: str
    address: str
    city: str
    phone: str
    timezone: str
    is_listed: bool
    is_suspended: bool = False  # D96: closed by BayFlow (the model's property)


class ServiceSnapshot(BaseModel):
    """What a booking snapshots of a selected service (D34)."""

    model_config = ConfigDict(frozen=True)

    service_id: uuid.UUID
    name: str
    base_price: Decimal | None


class TeamMember(BaseModel):
    """A membership with the member's name (reporting overview `team`)."""

    model_config = ConfigDict(frozen=True)

    membership_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    role: MembershipRole
    is_active: bool


class SetupFlags(BaseModel):
    """Reporting overview `setup` facts owned by shops."""

    model_config = ConfigDict(frozen=True)

    has_services: bool  # at least one active service
    has_team: bool  # at least one active non-owner membership
    is_listed: bool


# --- Platform admin records (spec 19 §2, §4; D94-D96) ---------------------------------------------


class ShopSuspension(BaseModel):
    """A shop's suspension (D96): when, why and by which platform admin."""

    model_config = ConfigDict(frozen=True)

    suspended_at: datetime
    reason: str
    suspended_by_user_id: uuid.UUID


class UserContact(BaseModel):
    """A person as the admin console lists them: name and e-mail."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID
    full_name: str
    email: str


AdminShopSqlSort = Literal["-created_at", "name"]
"""The E-62 sorts shops orders itself; `-bookings_30d` needs bookings and is the admin's job."""


@dataclass(frozen=True, slots=True)
class AdminShopQuery:
    """E-62's filters: `q` (name, slug, city or the owner's e-mail), suspended or not, listed or
    not, `city` (case-insensitive exact match)."""

    q: str | None = None
    suspended: bool | None = None
    listed: bool | None = None
    city: str | None = None


class AdminShopRecord(BaseModel):
    """One shop as the admin console lists it (E-62), without its bookings count."""

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID
    slug: str
    name: str
    city: str
    created_at: datetime
    is_listed: bool
    suspension: ShopSuspension | None
    owners: list[UserContact]
    active_members: int


class AdminMembershipRecord(BaseModel):
    """One membership of a user, active or not, with its shop (E-66, E-67)."""

    model_config = ConfigDict(frozen=True)

    membership_id: uuid.UUID
    shop: ShopBrief
    role: MembershipRole
    is_active: bool


class ShopStats(BaseModel):
    """Platform-wide shop counts (E-61): every shop, not suspended, suspended, `is_listed` set,
    created at or after the given instant."""

    model_config = ConfigDict(frozen=True)

    total: int
    active: int
    suspended: int
    listed: int
    created_since: int

"""Events published by the shops module (glossary §7.1, spec 01 "Event catalogue", spec 19 §3.3).

`ShopGridChanging` (D37): `update_shop` is about to change `slot_duration_minutes` or `timezone`;
the shop row is already locked `FOR UPDATE` and nothing is written yet. The bookings module vetoes
the change with 409 `CONFLICT` while the shop has a future non-cancelled booking; the exception
rolls the whole change back. With no subscriber the change proceeds.

The other events feed the platform audit log (D95): each is published by the use case that made
the change, inside its transaction and only when something really changed, and the `audit`
module writes one row for it in the same transaction (shops never imports `audit`). Payloads are
ids, enums and primitives only (spec 01 event rule 8).
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.shared.enums import MembershipRole
from app.shared.event_bus import Event

GRID_FIELDS: tuple[str, ...] = ("slot_duration_minutes", "timezone")
"""The shop fields whose change moves the slot grid (D37), in this order."""

type FieldValue = str | int | bool | None
"""A JSON-safe value of a `ShopUpdate` field (every field the PATCH accepts is one of these)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ShopGridChanging(Event):
    shop_id: uuid.UUID
    changed_fields: tuple[str, ...]  # a non-empty subset of GRID_FIELDS, in GRID_FIELDS order
    actor_user_id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ShopCreated(Event):
    """`create_shop`: the shop, its hours and the actor's `OWNER` membership exist (D17)."""

    shop_id: uuid.UUID
    actor_user_id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ShopUpdated(Event):
    """`update_shop` changed at least one field; `changes` holds only those, as
    `{field: {"from": old, "to": new}}`."""

    shop_id: uuid.UUID
    actor_user_id: uuid.UUID
    changes: Mapping[str, Mapping[str, FieldValue]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkingHoursReplaced(Event):
    """`replace_working_hours` changed at least one weekday."""

    shop_id: uuid.UUID
    actor_user_id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ShopSuspensionChanged(Event):
    """A platform admin suspended (`suspended`, with the reason) or reactivated the shop (D96)."""

    shop_id: uuid.UUID
    actor_user_id: uuid.UUID
    suspended: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipAdded(Event):
    """`add_member`: a staff membership for `user_id` (new or existing account, D18)."""

    shop_id: uuid.UUID
    membership_id: uuid.UUID
    user_id: uuid.UUID
    role: MembershipRole
    actor_user_id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipRoleChanged(Event):
    shop_id: uuid.UUID
    membership_id: uuid.UUID
    user_id: uuid.UUID
    from_role: MembershipRole
    to_role: MembershipRole
    actor_user_id: uuid.UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class MembershipActiveChanged(Event):
    shop_id: uuid.UUID
    membership_id: uuid.UUID
    user_id: uuid.UUID
    is_active: bool
    actor_user_id: uuid.UUID

"""Schemas of the audit module (spec 19 §3, §4 E-74/E-75; D95).

- `AuditEventRead`: one audit row on the wire, with the actor's and the shop's current names
  resolved at read time (the row itself keeps only their ids).
- `AuditFilters`: E-74's filters (also E-75's, and the shop / user trails of E-61, E-63, E-67).
- `AuditEntry`: what the service writes, before the request context (IP, user agent, request id)
  is added. Internal, never on the wire.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.shared.enums import AuditActorRole, AuditCategory, AuditTargetType
from app.shared.timestamps import Timestamp

AuditSort = Literal["-occurred_at", "occurred_at"]
"""E-74's sorts: newest first (the default) or oldest first, `id` breaking ties."""


class AuditEventRead(BaseModel):
    """One `audit_events` row (spec 19 §3.1). `actor_name` and `shop_name` are today's names;
    `metadata` never holds a password, a token or a hash."""

    id: UUID
    occurred_at: Timestamp
    category: AuditCategory
    action: str
    summary: str
    actor_user_id: UUID | None
    actor_name: str | None
    actor_role: AuditActorRole | None
    shop_id: UUID | None
    shop_name: str | None
    target_type: AuditTargetType | None
    target_id: UUID | None
    target_label: str | None
    metadata: dict[str, Any]
    ip: str | None
    user_agent: str | None
    request_id: str | None


@dataclass(frozen=True, slots=True)
class AuditFilters:
    """E-74 / E-75 filters (spec 19 §4); unset filters do not narrow.

    `occurred_from` is inclusive and `occurred_to` exclusive; `q` is a case-insensitive substring
    of the summary or the target label; `involving_user_id` keeps the rows done by **or** about a
    user (E-67's trail: actor, or a `USER` target).
    """

    categories: tuple[AuditCategory, ...] = ()
    action: str | None = None
    actor_user_id: UUID | None = None
    shop_id: UUID | None = None
    target_type: AuditTargetType | None = None
    target_id: UUID | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    q: str | None = None
    involving_user_id: UUID | None = None

    def as_metadata(self) -> dict[str, str | list[str]]:
        """The filters that are set, as JSON for `admin.audit_exported` (spec 19 §3.3)."""
        values: dict[str, str | list[str]] = {}
        if self.categories:
            values["category"] = [category.value for category in self.categories]
        for name, value in (
            ("action", self.action),
            ("actor_user_id", self.actor_user_id),
            ("shop_id", self.shop_id),
            ("target_type", self.target_type),
            ("target_id", self.target_id),
            ("q", self.q),
            ("involving_user_id", self.involving_user_id),
        ):
            if value is not None:
                values[name] = str(value)
        if self.occurred_from is not None:
            values["from"] = self.occurred_from.isoformat()
        if self.occurred_to is not None:
            values["to"] = self.occurred_to.isoformat()
        return values


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One row to write (internal). `metadata` holds JSON-safe values only (str, int, bool, None,
    lists and objects of them) and never a secret."""

    occurred_at: datetime
    action: str
    summary: str
    category: AuditCategory
    actor_user_id: UUID | None = None
    actor_role: AuditActorRole | None = None
    shop_id: UUID | None = None
    target_type: AuditTargetType | None = None
    target_id: UUID | None = None
    target_label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

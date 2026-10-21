"""Capabilities: the non-booking permissions of a membership (D66, glossary §2.4, spec 04).

`CAPABILITY_ROLES` is the single role table: `GET /api/v1/me` derives each membership's
`capabilities` from it, and every non-booking route guard (shops, inventory, bonus calls) is
written as `require_roles(*CAPABILITY_ROLES[Capability.X])`, so a capability the UI shows always
matches a route the server allows (SEC-46). Capabilities are hints: routes still re-check the
membership and the role on every request (D9). Pure Python (enums from `app.shared.enums`, D74).
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from app.shared.enums import MembershipRole


class Capability(StrEnum):
    """Glossary §2.4, in glossary order; the wire values are dotted."""

    SHOP_MANAGE = "shop.manage"
    TEAM_MANAGE = "team.manage"
    SERVICES_MANAGE = "services.manage"
    PARTS_MANAGE = "parts.manage"
    STOCK_MANAGE = "stock.manage"
    TASKS_MANAGE = "tasks.manage"  # bonus: only while the calls module is enabled


CAPABILITY_ROLES: Mapping[Capability, frozenset[MembershipRole]] = MappingProxyType(
    {
        Capability.SHOP_MANAGE: frozenset({MembershipRole.OWNER}),
        Capability.TEAM_MANAGE: frozenset({MembershipRole.OWNER}),
        Capability.SERVICES_MANAGE: frozenset({MembershipRole.OWNER}),
        Capability.PARTS_MANAGE: frozenset({MembershipRole.OWNER, MembershipRole.PARTS_PERSON}),
        Capability.STOCK_MANAGE: frozenset({MembershipRole.PARTS_PERSON}),
        Capability.TASKS_MANAGE: frozenset({MembershipRole.OWNER, MembershipRole.SERVICE_ADVISOR}),
    }
)
"""Who holds each capability (spec 04 "Capabilities", D16, D44)."""

TEAM_VIEW_ROLES: frozenset[MembershipRole] = frozenset(
    {MembershipRole.OWNER, MembershipRole.SERVICE_ADVISOR}
)
"""Who may list members: the Owner (everyone) and SAs (assign pickers only, spec 04 RBAC A)."""

SA_VISIBLE_ROLES: frozenset[MembershipRole] = frozenset(
    {MembershipRole.TECHNICIAN, MembershipRole.PARTS_PERSON}
)
"""The members a Service Advisor sees: active technicians and parts persons (the assign pickers)."""

ROLE_ORDER: Mapping[MembershipRole, int] = MappingProxyType(
    {role: position for position, role in enumerate(MembershipRole)}
)
"""Glossary order (`OWNER`, `SERVICE_ADVISOR`, `TECHNICIAN`, `PARTS_PERSON`, `QC_INSPECTOR`)."""


def capabilities_for(role: MembershipRole, *, tasks_enabled: bool) -> list[Capability]:
    """The capabilities of `role`, sorted alphabetically by value (spec 03 §3.2).

    `tasks.manage` is included only when the bonus calls module is enabled (glossary §2.4).
    """
    granted = (
        capability
        for capability, roles in CAPABILITY_ROLES.items()
        if role in roles and (tasks_enabled or capability is not Capability.TASKS_MANAGE)
    )
    return sorted(granted, key=lambda capability: capability.value)

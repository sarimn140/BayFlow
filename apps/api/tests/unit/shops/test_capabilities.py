"""The capability table (D66, glossary §2.4, spec 04 "Capabilities"): SEC-46/SHP-09 domain half."""

import pytest

from app.modules.shops.domain.capabilities import (
    CAPABILITY_ROLES,
    ROLE_ORDER,
    SA_VISIBLE_ROLES,
    TEAM_VIEW_ROLES,
    Capability,
    capabilities_for,
)
from app.shared.enums import MembershipRole

OWN, SA, T, PP, QC = (
    MembershipRole.OWNER,
    MembershipRole.SERVICE_ADVISOR,
    MembershipRole.TECHNICIAN,
    MembershipRole.PARTS_PERSON,
    MembershipRole.QC_INSPECTOR,
)


def test_shp09_capability_values_are_the_glossary_names() -> None:
    assert [capability.value for capability in Capability] == [
        "shop.manage",
        "team.manage",
        "services.manage",
        "parts.manage",
        "stock.manage",
        "tasks.manage",
    ]


def test_shp09_the_role_table_matches_spec_04() -> None:
    assert dict(CAPABILITY_ROLES) == {
        Capability.SHOP_MANAGE: {OWN},
        Capability.TEAM_MANAGE: {OWN},
        Capability.SERVICES_MANAGE: {OWN},
        Capability.PARTS_MANAGE: {OWN, PP},
        Capability.STOCK_MANAGE: {PP},
        Capability.TASKS_MANAGE: {OWN, SA},
    }


@pytest.mark.parametrize(
    ("role", "core", "with_tasks"),
    [
        (
            OWN,
            ["parts.manage", "services.manage", "shop.manage", "team.manage"],
            ["parts.manage", "services.manage", "shop.manage", "tasks.manage", "team.manage"],
        ),
        (SA, [], ["tasks.manage"]),
        (PP, ["parts.manage", "stock.manage"], ["parts.manage", "stock.manage"]),
        (T, [], []),
        (QC, [], []),
    ],
)
def test_shp09_capabilities_per_role_sorted_alphabetically(
    role: MembershipRole, core: list[str], with_tasks: list[str]
) -> None:
    assert capabilities_for(role, tasks_enabled=False) == core
    assert capabilities_for(role, tasks_enabled=True) == with_tasks


def test_team_view_and_role_order() -> None:
    assert set(TEAM_VIEW_ROLES) == {OWN, SA}
    assert set(SA_VISIBLE_ROLES) == {T, PP}
    assert sorted(MembershipRole, key=ROLE_ORDER.__getitem__) == [OWN, SA, T, PP, QC]

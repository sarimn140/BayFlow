"""NOT-14: `link_for` for every `recipient_role` and `AI_TASK_CREATED` (D67, spec 03 §3.7); every
link satisfies `ck_notifications_link_relative` (the DB half is in the module's DB tests)."""

import uuid

import pytest

from app.modules.notifications.domain.links import LINK_MAX_LENGTH, is_relative_link, link_for
from app.shared.enums import ActorRole, NotificationType

SHOP = uuid.UUID("3f2c9a1e-6b4d-4c8e-9a7f-1d2e3f4a5b6c")
BOOKING = uuid.UUID("8d1e4b6a-2c3f-4e5a-b7c8-9d0e1f2a3b4c")

EXPECTED = {
    ActorRole.CUSTOMER: f"/bookings/{BOOKING}",
    ActorRole.SERVICE_ADVISOR: f"/pos/shops/{SHOP}/bookings/{BOOKING}",
    ActorRole.OWNER: f"/pos/shops/{SHOP}/bookings/{BOOKING}",
    ActorRole.TECHNICIAN: f"/pos/shops/{SHOP}/jobs/{BOOKING}",
    ActorRole.PARTS_PERSON: f"/pos/shops/{SHOP}/parts/{BOOKING}",
    ActorRole.QC_INSPECTOR: f"/pos/shops/{SHOP}/qc/{BOOKING}",
}
BOOKING_TYPES = [t for t in NotificationType if t != NotificationType.AI_TASK_CREATED]


def test_every_recipient_role_but_system_has_a_link() -> None:
    assert set(EXPECTED) == set(ActorRole) - {ActorRole.SYSTEM}


@pytest.mark.parametrize("role", list(EXPECTED))
@pytest.mark.parametrize("notification_type", BOOKING_TYPES)
def test_the_link_depends_on_the_recipient_role_only(
    role: ActorRole, notification_type: NotificationType
) -> None:
    link = link_for(role, notification_type, shop_id=SHOP, booking_id=BOOKING)
    assert link == EXPECTED[role]
    assert is_relative_link(link)


@pytest.mark.parametrize("role", list(EXPECTED))
def test_ai_task_links_to_the_calls_page_for_any_role(role: ActorRole) -> None:
    for booking_id in (BOOKING, None):
        link = link_for(role, NotificationType.AI_TASK_CREATED, shop_id=SHOP, booking_id=booking_id)
        assert link == f"/pos/shops/{SHOP}/calls"
        assert is_relative_link(link)


def test_system_is_never_a_recipient() -> None:
    with pytest.raises(ValueError, match="SYSTEM"):
        link_for(
            ActorRole.SYSTEM, NotificationType.BOOKING_CREATED, shop_id=SHOP, booking_id=BOOKING
        )


def test_the_documented_positional_signature() -> None:
    """`link_for(recipient_role, type, shop_id, booking_id)` (modules/notifications.md)."""
    assert (
        link_for(ActorRole.TECHNICIAN, NotificationType.QC_FAILED, SHOP, BOOKING)
        == (EXPECTED[ActorRole.TECHNICIAN])
    )


def test_a_booking_link_needs_a_booking() -> None:
    with pytest.raises(ValueError, match="needs a booking"):
        link_for(ActorRole.CUSTOMER, NotificationType.VEHICLE_READY, shop_id=SHOP, booking_id=None)


def test_links_are_built_from_ids_only() -> None:
    """Random ids can never produce `//`, a backslash or an absolute URL."""
    for _ in range(200):
        shop_id, booking_id = uuid.uuid4(), uuid.uuid4()
        for role in EXPECTED:
            link = link_for(
                role, NotificationType.QC_FAILED, shop_id=shop_id, booking_id=booking_id
            )
            assert is_relative_link(link)
            assert link.count("//") == 0
            assert len(link) < LINK_MAX_LENGTH


@pytest.mark.parametrize(
    ("link", "relative"),
    [
        ("/bookings/x", True),
        ("/", True),
        ("//evil.example/x", False),
        ("/\\evil.example", False),
        ("https://evil.example", False),
        ("bookings/x", False),
        ("", False),
        ("/" + "a" * LINK_MAX_LENGTH, False),
    ],
)
def test_the_relative_link_rule_mirrors_the_database_check(link: str, relative: bool) -> None:
    assert is_relative_link(link) is relative

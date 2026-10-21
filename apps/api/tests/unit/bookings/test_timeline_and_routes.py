"""The customer projection of a timeline (spec 03 §3.3, BK-36 unit half), `status_changed_at`'s
rule, and the two generated action-route families (D48, spec 03 §5.1; BK-42 unit half)."""

import pytest

from app.modules.bookings.domain.state_machine import ACTION_TO_SLUG, RULES
from app.modules.bookings.domain.timeline import (
    CUSTOMER_HIDDEN_ACTIONS,
    CUSTOMER_NOTE_ACTIONS,
    UNROUTED_SLUGS,
    customer_note,
    customer_route_actions,
    is_customer_visible,
    is_status_change,
    routed,
    staff_route_actions,
)
from app.modules.bookings.schemas import (
    CUSTOMER_ACTION_REQUESTS,
    STAFF_ACTION_REQUESTS,
    BookingActionSlug,
)
from app.shared.enums import ActorRole, BookingAction, BookingStatus

STAFF_SLUGS = [
    "confirm",
    "decline",
    "assign-technician",
    "start-inspection",
    "submit-estimate",
    "send-estimate",
    "revise-estimate",
    "return-to-technician",
    "assign-parts-person",
    "order-parts",
    "mark-parts-ready",
    "allocate-parts",
    "start-repair",
    "send-to-qc",
    "pick-qc",
    "pass-qc",
    "fail-qc",
    "notify-ready",
    "complete",
    "cancel",
    "reassign-technician",
    "reassign-parts-person",
]
CUSTOMER_SLUGS = ["approve-estimate", "reject-estimate", "complete", "cancel"]


def test_bk42_the_staff_family_has_exactly_22_slugs() -> None:
    assert [ACTION_TO_SLUG[action] for action in staff_route_actions()] == STAFF_SLUGS


def test_bk42_the_customer_family_has_exactly_4_slugs() -> None:
    assert [ACTION_TO_SLUG[action] for action in customer_route_actions()] == CUSTOMER_SLUGS


def test_edit_estimate_create_and_receive_parts_are_never_action_routes() -> None:
    routes = set(staff_route_actions()) | set(customer_route_actions())
    assert BookingAction.EDIT_ESTIMATE not in routes
    assert BookingAction.CREATE not in routes
    assert BookingAction.RECEIVE_PARTS not in routes


def test_every_route_has_its_own_request_body() -> None:
    assert list(STAFF_ACTION_REQUESTS) == list(staff_route_actions())
    assert list(CUSTOMER_ACTION_REQUESTS) == list(customer_route_actions())
    for requests in (STAFF_ACTION_REQUESTS, CUSTOMER_ACTION_REQUESTS):
        for action, model in requests.items():
            pascal = "".join(part.title() for part in ACTION_TO_SLUG[action].split("-"))
            assert model.__name__ in {f"{pascal}Request", f"Customer{pascal}Request"}
    assert CUSTOMER_ACTION_REQUESTS[BookingAction.CANCEL].__name__ == "CustomerCancelRequest"


def test_p1_reassign_routes_ship_so_no_slug_is_unrouted() -> None:
    assert frozenset() == UNROUTED_SLUGS
    assert routed(["confirm", "reassign-technician"]) == ["confirm", "reassign-technician"]


def test_every_listable_slug_has_a_route_or_is_the_estimate_editor() -> None:
    """Spec 03 §3.3: a slug in `allowed_actions` always has a route in the caller's family."""
    staff = {ACTION_TO_SLUG[action] for action in staff_route_actions()}
    customer = {ACTION_TO_SLUG[action] for action in customer_route_actions()}
    for action, rule in RULES.items():
        if not rule.listable:
            continue
        slug = ACTION_TO_SLUG[action]
        if ActorRole.CUSTOMER in rule.actors:
            assert slug in customer, slug
        if rule.actors - {ActorRole.CUSTOMER}:
            assert slug in staff or slug == "edit-estimate", slug


def test_the_wire_enum_lists_the_25_slugs_in_glossary_order() -> None:
    assert [slug.value for slug in BookingActionSlug] == list(ACTION_TO_SLUG.values())
    assert len(BookingActionSlug) == 25


def test_customer_projection_constants() -> None:
    assert (
        frozenset(
            {
                BookingAction.EDIT_ESTIMATE,
                BookingAction.REASSIGN_TECHNICIAN,
                BookingAction.REASSIGN_PARTS_PERSON,
            }
        )
        == CUSTOMER_HIDDEN_ACTIONS
    )
    assert (
        frozenset({BookingAction.DECLINE, BookingAction.CANCEL, BookingAction.REJECT_ESTIMATE})
        == CUSTOMER_NOTE_ACTIONS
    )


@pytest.mark.parametrize("action", list(BookingAction))
def test_bk36_projection_per_action(action: BookingAction) -> None:
    assert is_customer_visible(action) is (action not in CUSTOMER_HIDDEN_ACTIONS)
    expected = "a reason" if action in CUSTOMER_NOTE_ACTIONS else None
    assert customer_note(action, "a reason") == expected
    assert customer_note(action, None) is None


def test_status_changes() -> None:
    assert is_status_change(None, BookingStatus.PENDING)  # CREATE counts
    assert is_status_change(BookingStatus.PENDING, BookingStatus.CONFIRMED)
    assert not is_status_change(BookingStatus.IN_REPAIR, BookingStatus.IN_REPAIR)

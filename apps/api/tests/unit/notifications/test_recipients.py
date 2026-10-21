"""The trigger table and the recipient rules (pure; glossary §6, D9, D26, D91).

The table is stated here a second time, independently, and compared with the implementation for
every `BookingAction` and `ActorRole` (27 x 7 cases), as SM-01 does for the state machine.
"""

import uuid

import pytest

from app.modules.notifications.domain.recipients import (
    EMAILED_TYPES,
    Audience,
    Recipient,
    RecipientFacts,
    Trigger,
    named_staff_ids,
    resolve_recipients,
    trigger_for,
)
from app.shared.enums import ActorRole, BookingAction, NotificationType

A = BookingAction
R = ActorRole
T = NotificationType
SAS = (Audience.SHOP_ADVISORS,)

# Glossary §6 / spec 08, restated: action -> (type, audiences); CANCEL is split below.
TABLE: dict[BookingAction, tuple[NotificationType, tuple[Audience, ...]] | None] = {
    A.CREATE: (T.BOOKING_CREATED, SAS),
    A.CONFIRM: (T.BOOKING_CONFIRMED, (Audience.CUSTOMER,)),
    A.DECLINE: (T.BOOKING_CANCELLED, (Audience.CUSTOMER,)),
    A.ASSIGN_TECHNICIAN: (T.TECHNICIAN_ASSIGNED, (Audience.TECHNICIAN,)),
    A.REASSIGN_TECHNICIAN: (T.TECHNICIAN_ASSIGNED, (Audience.TECHNICIAN,)),
    A.START_INSPECTION: None,
    A.EDIT_ESTIMATE: None,
    A.SUBMIT_ESTIMATE: (T.ESTIMATE_SUBMITTED, SAS),
    A.SEND_ESTIMATE: (T.ESTIMATE_SENT, (Audience.CUSTOMER,)),
    A.APPROVE_ESTIMATE: (T.ESTIMATE_APPROVED, SAS),
    A.REJECT_ESTIMATE: (T.ESTIMATE_REJECTED, SAS),
    A.REVISE_ESTIMATE: None,
    A.RETURN_TO_TECHNICIAN: (T.ESTIMATE_RETURNED, (Audience.TECHNICIAN,)),
    A.ASSIGN_PARTS_PERSON: (T.PARTS_NEEDED, (Audience.PARTS_PERSON,)),
    A.REASSIGN_PARTS_PERSON: (T.PARTS_NEEDED, (Audience.PARTS_PERSON,)),
    A.ORDER_PARTS: None,
    A.MARK_PARTS_READY: None,
    A.RECEIVE_PARTS: None,
    A.ALLOCATE_PARTS: (T.PARTS_READY, (Audience.TECHNICIAN,)),
    A.START_REPAIR: None,
    A.SEND_TO_QC: (T.QC_REQUESTED, (Audience.QC_INSPECTORS,)),
    A.PICK_QC: None,
    A.PASS_QC: (T.QC_PASSED, SAS),
    A.FAIL_QC: (T.QC_FAILED, (Audience.TECHNICIAN,)),
    A.NOTIFY_READY: (T.VEHICLE_READY, (Audience.CUSTOMER,)),
    A.COMPLETE: None,
}


def expected_trigger(action: BookingAction, role: ActorRole) -> Trigger | None:
    if action == A.CANCEL:
        if role == R.CUSTOMER:
            audiences = (Audience.SHOP_ADVISORS, Audience.TECHNICIAN, Audience.PARTS_PERSON)
            return Trigger(T.BOOKING_CANCELLED, audiences)
        return Trigger(T.BOOKING_CANCELLED, (Audience.CUSTOMER,))
    row = TABLE[action]
    return None if row is None else Trigger(*row)


def test_the_restated_table_covers_every_action() -> None:
    assert set(TABLE) | {A.CANCEL} == set(BookingAction)


@pytest.mark.parametrize("role", list(ActorRole))
@pytest.mark.parametrize("action", list(BookingAction))
def test_trigger_for_every_action_and_actor(action: BookingAction, role: ActorRole) -> None:
    assert trigger_for(action, role) == expected_trigger(action, role)


def test_plain_strings_are_understood_like_the_enums() -> None:
    """The event carries enums, but a value that arrives as a plain string behaves the same."""
    assert trigger_for("CANCEL", "CUSTOMER") == trigger_for(A.CANCEL, R.CUSTOMER)  # type: ignore[arg-type]
    assert trigger_for("NOTIFY_READY", "OWNER") == trigger_for(A.NOTIFY_READY, R.OWNER)  # type: ignore[arg-type]


def test_every_minimum_and_extra_type_has_a_trigger() -> None:
    fired = {trigger.type for trigger in filter(None, (trigger_for(a, R.OWNER) for a in A))}
    fired |= {trigger_for(A.CANCEL, R.CUSTOMER).type}  # type: ignore[union-attr]
    assert fired == set(T) - {T.CALL_MISSED, T.AI_TASK_CREATED}


def test_only_estimate_sent_and_vehicle_ready_are_emailed() -> None:
    assert frozenset({T.ESTIMATE_SENT, T.VEHICLE_READY}) == EMAILED_TYPES


# --- Resolution -----------------------------------------------------------------------------------

CUSTOMER, TECH, TECH_2, PARTS = (uuid.uuid4() for _ in range(4))
SA_1, SA_2, OWNER, QC_1, QC_2 = (uuid.uuid4() for _ in range(5))


def facts(**overrides: object) -> RecipientFacts:
    values: dict[str, object] = {
        "customer_user_id": CUSTOMER,
        "technician_user_id": TECH,
        "parts_person_user_id": PARTS,
        "service_advisor_ids": [SA_1, SA_2],
        "owner_user_id": None,
        "qc_inspector_ids": [QC_1, QC_2],
        "active_member_ids": frozenset({SA_1, SA_2, OWNER, TECH, TECH_2, PARTS, QC_1, QC_2}),
    }
    values.update(overrides)
    return RecipientFacts(**values)  # type: ignore[arg-type]


def resolve(action: BookingAction, role: ActorRole, **overrides: object) -> list[Recipient]:
    trigger = trigger_for(action, role)
    assert trigger is not None
    return resolve_recipients(trigger, facts(**overrides))


def test_sas_of_the_shop_are_every_active_sa_in_order() -> None:
    assert resolve(A.CREATE, R.CUSTOMER) == [
        Recipient(SA_1, R.SERVICE_ADVISOR),
        Recipient(SA_2, R.SERVICE_ADVISOR),
    ]


def test_without_an_sa_the_owner_is_notified_as_owner() -> None:
    assert resolve(A.PASS_QC, R.QC_INSPECTOR, service_advisor_ids=[], owner_user_id=OWNER) == [
        Recipient(OWNER, R.OWNER)
    ]


def test_without_an_sa_or_an_owner_nobody_is_notified() -> None:
    assert resolve(A.SUBMIT_ESTIMATE, R.TECHNICIAN, service_advisor_ids=[]) == []


def test_the_owner_is_ignored_while_an_sa_exists() -> None:
    assert Recipient(OWNER, R.OWNER) not in resolve(
        A.APPROVE_ESTIMATE, R.CUSTOMER, owner_user_id=OWNER
    )


def test_the_customer_is_always_notified_without_a_membership_check() -> None:
    assert resolve(A.NOTIFY_READY, R.SERVICE_ADVISOR, active_member_ids=frozenset()) == [
        Recipient(CUSTOMER, R.CUSTOMER)
    ]


def test_named_staff_only_while_active_members() -> None:
    assert resolve(A.ALLOCATE_PARTS, R.PARTS_PERSON) == [Recipient(TECH, R.TECHNICIAN)]
    assert resolve(A.ALLOCATE_PARTS, R.PARTS_PERSON, active_member_ids=frozenset({PARTS})) == []
    assert resolve(A.ASSIGN_PARTS_PERSON, R.OWNER, parts_person_user_id=None) == []


def test_reassign_notifies_the_assignee_after_the_action() -> None:
    assert resolve(A.REASSIGN_TECHNICIAN, R.OWNER, technician_user_id=TECH_2) == [
        Recipient(TECH_2, R.TECHNICIAN)
    ]


def test_qc_inspectors_have_no_fallback() -> None:
    assert resolve(A.SEND_TO_QC, R.TECHNICIAN, qc_inspector_ids=[], owner_user_id=OWNER) == []


def test_customer_cancel_reaches_sas_technician_and_parts_person_in_table_order() -> None:
    assert resolve(A.CANCEL, R.CUSTOMER) == [
        Recipient(SA_1, R.SERVICE_ADVISOR),
        Recipient(SA_2, R.SERVICE_ADVISOR),
        Recipient(TECH, R.TECHNICIAN),
        Recipient(PARTS, R.PARTS_PERSON),
    ]
    assert resolve(A.CANCEL, R.CUSTOMER, technician_user_id=None, parts_person_user_id=None) == [
        Recipient(SA_1, R.SERVICE_ADVISOR),
        Recipient(SA_2, R.SERVICE_ADVISOR),
    ]


@pytest.mark.parametrize("role", [R.SERVICE_ADVISOR, R.OWNER, R.SYSTEM])
def test_any_other_cancel_reaches_the_customer(role: ActorRole) -> None:
    assert resolve(A.CANCEL, role) == [Recipient(CUSTOMER, R.CUSTOMER)]


def test_d91_one_row_per_user_first_role_wins() -> None:
    """The technician is also an SA (re-roled while assigned): one recipient, as SA."""
    assert resolve(A.CANCEL, R.CUSTOMER, service_advisor_ids=[SA_1, TECH]) == [
        Recipient(SA_1, R.SERVICE_ADVISOR),
        Recipient(TECH, R.SERVICE_ADVISOR),
        Recipient(PARTS, R.PARTS_PERSON),
    ]
    assert resolve(A.CANCEL, R.CUSTOMER, parts_person_user_id=TECH) == [
        Recipient(SA_1, R.SERVICE_ADVISOR),
        Recipient(SA_2, R.SERVICE_ADVISOR),
        Recipient(TECH, R.TECHNICIAN),
    ]


def test_d91_the_actor_is_not_excluded() -> None:
    """An SA who is the booking's customer gets the staff row when the shop is notified."""
    assert resolve(A.CREATE, R.CUSTOMER, customer_user_id=SA_1)[0] == Recipient(
        SA_1, R.SERVICE_ADVISOR
    )


def test_system_is_never_a_recipient() -> None:
    trigger = Trigger(T.BOOKING_CREATED, (Audience.SHOP_ADVISORS,))
    assert all(r.role != R.SYSTEM for r in resolve_recipients(trigger, facts()))


def test_named_staff_ids() -> None:
    cancel = trigger_for(A.CANCEL, R.CUSTOMER)
    assert cancel is not None
    assert named_staff_ids(cancel, technician_user_id=TECH, parts_person_user_id=PARTS) == {
        TECH,
        PARTS,
    }
    assert named_staff_ids(cancel, technician_user_id=None, parts_person_user_id=None) == set()
    created = trigger_for(A.CREATE, R.CUSTOMER)
    assert created is not None
    assert named_staff_ids(created, technician_user_id=TECH, parts_person_user_id=PARTS) == set()

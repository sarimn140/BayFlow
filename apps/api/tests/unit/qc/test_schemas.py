"""qc schemas, DB-free (spec 03 §1.5, §2.3, §3.6, §5.2).

QC-13 (an unknown key is `enum` at `checklist.N.key`, schema half), QC-02 (issue field limits,
schema half), the wrong-type cases of the checklist items, and the wire shape of the reads.
FastAPI 0.143 validates a parsed JSON body with `validate_python(value, from_attributes=True)`
(`fastapi/_compat/v2.py`), so checklist bodies are validated exactly that way here
(`as_fastapi`): a non-object item is then `model_attributes_type`, as on the wire. For dict input
`from_attributes` changes nothing, so the single-item cases use plain `model_validate`.
"""

import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.modules.identity.schemas import UserRef
from app.modules.qc import service
from app.modules.qc.domain.checklist import validate_checklist
from app.modules.qc.schemas import (
    CHECKLIST_MAX_ITEMS,
    FailRecorded,
    QcChecklistItemRead,
    QcChecklistItemWrite,
    QcChecklistTemplateItem,
    QcChecklistWrite,
    QcInspectionRead,
    QcIssueDescription,
    QcIssueRead,
    QcIssueTitle,
    QcNotes,
    QcSummary,
)
from app.shared.enums import BookingStatus, QcChecklistKey, QcIssueStatus, QcResult
from app.shared.pagination import ItemList

CHECKLIST = TypeAdapter(QcChecklistWrite)


def as_fastapi(body: object) -> list[QcChecklistItemWrite]:
    """Validate a parsed JSON `checklist` the way FastAPI validates request bodies."""
    return CHECKLIST.validate_python(body, from_attributes=True)


def items(**overrides: dict[str, Any]) -> list[dict[str, Any]]:
    """The five keys, all passed; `overrides` replaces fields of the item with that key."""
    return [
        {"key": key.value, "passed": True, **overrides.get(key.value, {})} for key in QcChecklistKey
    ]


def errors_of(exc: pytest.ExceptionInfo[ValidationError]) -> list[tuple[tuple[Any, ...], str]]:
    return [(tuple(error["loc"]), error["type"]) for error in exc.value.errors()]


# --- QcChecklistItemWrite / QcChecklistWrite ------------------------------------------------------


def test_a_valid_checklist_parses_into_enum_keys() -> None:
    parsed = as_fastapi(items(no_leaks={"note": "  dry  "}))
    assert [item.key for item in parsed] == list(QcChecklistKey)
    assert all(item.passed is True for item in parsed)
    assert parsed[2].note == "dry"
    assert parsed[0].note is None
    assert validate_checklist(parsed, require_all_passed=True) == []


def test_qc13_an_unknown_key_is_enum_at_its_index() -> None:
    body = [*items(), {"key": "brakes", "passed": True}]
    with pytest.raises(ValidationError) as caught:
        as_fastapi(body)
    assert errors_of(caught) == [((5, "key"), "enum")]


def test_the_domain_and_the_schema_word_an_unknown_key_alike() -> None:
    with pytest.raises(ValidationError) as caught:
        QcChecklistItemWrite.model_validate({"key": "ROAD_TEST", "passed": True})
    schema_message = caught.value.errors()[0]["msg"]

    class Raw:
        key = "ROAD_TEST"
        passed = True
        note = None

    domain_errors = validate_checklist([Raw()], require_all_passed=False)  # type: ignore[list-item]
    assert domain_errors[0]["message"] == schema_message


@pytest.mark.parametrize(
    ("item", "loc", "code"),
    [
        ({"key": "road_test", "passed": "yes"}, ("passed",), "bool_type"),
        ({"key": "road_test", "passed": 1}, ("passed",), "bool_type"),
        ({"key": "road_test", "passed": "true"}, ("passed",), "bool_type"),
        ({"key": "road_test", "passed": None}, ("passed",), "bool_type"),
        ({"key": "road_test"}, ("passed",), "missing"),
        ({"passed": True}, ("key",), "missing"),
        ({"key": 5, "passed": True}, ("key",), "enum"),
        ({"key": None, "passed": True}, ("key",), "enum"),
        ({"key": "road_test", "passed": True, "note": 7}, ("note",), "string_type"),
        ({"key": "road_test", "passed": True, "note": "n" * 501}, ("note",), "string_too_long"),
        ({"key": "road_test", "passed": True, "label": "Road test"}, ("label",), "extra_forbidden"),
    ],
    ids=[
        "passed-yes",
        "passed-1",
        "passed-true-string",
        "passed-null",
        "passed-missing",
        "key-missing",
        "key-number",
        "key-null",
        "note-number",
        "note-too-long",
        "unknown-field",
    ],
)
def test_wrong_item_shapes_are_refused(
    item: dict[str, Any], loc: tuple[str, ...], code: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        QcChecklistItemWrite.model_validate(item)
    assert errors_of(caught) == [(loc, code)]


def test_an_item_note_is_trimmed_and_blank_is_none() -> None:
    assert (
        QcChecklistItemWrite.model_validate(
            {"key": "no_leaks", "passed": False, "note": "   "}
        ).note
        is None
    )
    exactly = QcChecklistItemWrite.model_validate(
        {"key": "no_leaks", "passed": False, "note": " " + "n" * 500 + " "}
    )
    assert exactly.note == "n" * 500


def test_json_booleans_are_accepted_in_json_mode_too() -> None:
    parsed = QcChecklistItemWrite.model_validate_json('{"key": "no_leaks", "passed": false}')
    assert parsed.passed is False
    with pytest.raises(ValidationError):
        QcChecklistItemWrite.model_validate_json('{"key": "no_leaks", "passed": "false"}')


@pytest.mark.parametrize(
    ("body", "loc", "code"),
    [
        ("road_test", (), "list_type"),
        (None, (), "list_type"),
        (["road_test"], (0,), "model_attributes_type"),
        ([items()[0], 3], (1,), "model_attributes_type"),
    ],
    ids=["a-string", "null", "a-list-of-strings", "a-number-item"],
)
def test_wrong_checklist_shapes_are_refused(body: object, loc: tuple[Any, ...], code: str) -> None:
    with pytest.raises(ValidationError) as caught:
        as_fastapi(body)
    assert errors_of(caught) == [(loc, code)]


def test_the_checklist_array_is_bounded() -> None:
    """Spec 03 §1.10; up to 20 items still reach the `checklist_incomplete` answer."""
    repeated = [{"key": "road_test", "passed": True}] * CHECKLIST_MAX_ITEMS
    assert len(as_fastapi(repeated)) == CHECKLIST_MAX_ITEMS
    with pytest.raises(ValidationError) as caught:
        as_fastapi([*repeated, {"key": "road_test", "passed": True}])
    assert errors_of(caught) == [((), "too_long")]


def test_an_empty_checklist_passes_the_schema_and_is_incomplete_for_the_rules() -> None:
    assert as_fastapi([]) == []
    assert validate_checklist([], require_all_passed=True)[0]["code"] == "checklist_incomplete"


# --- Issue and notes field types (bookings' FailQcRequest / PassQcRequest) ------------------------


@pytest.mark.parametrize(
    ("adapter", "value", "code"),
    [
        (QcIssueTitle, "", "string_too_short"),
        (QcIssueTitle, "    ", "string_too_short"),
        (QcIssueTitle, "t" * 121, "string_too_long"),
        (QcIssueTitle, None, "string_type"),
        (QcIssueDescription, "", "string_too_short"),
        (QcIssueDescription, " \n ", "string_too_short"),
        (QcIssueDescription, "d" * 2001, "string_too_long"),
        (QcNotes, "n" * 2001, "string_too_long"),
        (QcNotes, 12, "string_type"),
    ],
    ids=[
        "title-empty",
        "title-blank",
        "title-121",
        "title-null",
        "description-empty",
        "description-blank",
        "description-2001",
        "notes-2001",
        "notes-number",
    ],
)
def test_qc02_issue_and_notes_limits(adapter: object, value: object, code: str) -> None:
    with pytest.raises(ValidationError) as caught:
        TypeAdapter(adapter).validate_python(value)
    assert [error["type"] for error in caught.value.errors()][-1] == code


def test_issue_fields_and_notes_are_trimmed() -> None:
    assert (
        TypeAdapter(QcIssueTitle).validate_python("  Oil leak at filter ") == "Oil leak at filter"
    )
    assert TypeAdapter(QcIssueTitle).validate_python("t" * 120) == "t" * 120
    assert TypeAdapter(QcIssueDescription).validate_python("d" * 2000) == "d" * 2000
    assert TypeAdapter(QcNotes).validate_python("  ok ") == "ok"
    assert TypeAdapter(QcNotes).validate_python("   ") is None
    assert TypeAdapter(QcNotes).validate_python(None) is None


# --- Reads ----------------------------------------------------------------------------------------


def test_default_checklist_is_the_template_as_wire_items() -> None:
    template = service.default_checklist()
    assert all(isinstance(item, QcChecklistTemplateItem) for item in template)
    assert ItemList[QcChecklistTemplateItem](items=template).model_dump(mode="json") == {
        "items": [
            {"key": "road_test", "label": "Road test"},
            {"key": "no_warning_lights", "label": "No warning lights"},
            {"key": "no_leaks", "label": "No leaks"},
            {"key": "fluid_levels", "label": "Fluid levels OK"},
            {"key": "complaint_resolved", "label": "Customer complaint resolved"},
        ]
    }
    assert service.default_checklist() is not template  # a fresh list per call


def test_inspection_read_has_exactly_the_spec_03_fields_and_utc_z_timestamps() -> None:
    sara, imran = (
        UserRef(user_id=uuid.uuid4(), full_name="Sara"),
        UserRef(user_id=uuid.uuid4(), full_name="Imran"),
    )
    picked = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
    issue = QcIssueRead(
        id=uuid.uuid4(),
        qc_inspection_id=uuid.uuid4(),
        title="Oil leak at filter",
        description="Seal is weeping.",
        status=QcIssueStatus.RESOLVED,
        created_by=sara,
        created_at=picked,
        resolved_at=datetime(2026, 10, 16, 11, 30, 0, 123000, tzinfo=UTC),
        resolved_by=imran,
    )
    inspection = QcInspectionRead(
        id=uuid.uuid4(),
        round=1,
        inspector=sara,
        picked_at=picked,
        completed_at=None,
        result=None,
        checklist=None,
        notes=None,
        issues=[issue],
    )
    body = inspection.model_dump(mode="json")
    assert list(body) == [
        "id",
        "round",
        "inspector",
        "picked_at",
        "completed_at",
        "result",
        "checklist",
        "notes",
        "issues",
    ]
    assert body["picked_at"] == "2026-10-16T09:00:00Z"
    assert list(body["issues"][0]) == [
        "id",
        "qc_inspection_id",
        "title",
        "description",
        "status",
        "created_by",
        "created_at",
        "resolved_at",
        "resolved_by",
    ]
    assert body["issues"][0]["resolved_at"] == "2026-10-16T11:30:00.123Z"
    assert body["inspector"] == {"user_id": str(sara.user_id), "full_name": "Sara"}


def test_a_round_number_starts_at_one() -> None:
    with pytest.raises(ValidationError):
        QcInspectionRead(
            id=uuid.uuid4(),
            round=0,
            inspector=UserRef(user_id=uuid.uuid4(), full_name="Sara"),
            picked_at=datetime(2026, 10, 16, 9, 0, tzinfo=UTC),
            completed_at=None,
            result=QcResult.PASS,
            checklist=[
                QcChecklistItemRead(
                    key=QcChecklistKey.ROAD_TEST, label="Road test", passed=True, note=None
                )
            ],
            notes=None,
            issues=[],
        )


def test_response_fields_are_always_present_in_the_json_schema() -> None:
    """Spec 03 §1.5: response fields are always present; "no value" is null."""
    for model in (QcInspectionRead, QcIssueRead, QcChecklistItemRead, UserRef):
        schema = model.model_json_schema(mode="serialization")
        assert set(schema["required"]) == set(schema["properties"]), model.__name__


# --- Internal values ------------------------------------------------------------------------------


def test_qc_summary_derives_qc_round_and_is_immutable() -> None:
    summary = QcSummary(inspections=1, open_issues=1)
    assert summary.qc_round(BookingStatus.QC_PENDING) == 2
    assert summary.qc_round(BookingStatus.IN_REPAIR) == 1
    assert QcSummary(inspections=0, open_issues=0).qc_round(BookingStatus.CONFIRMED) == 0
    with pytest.raises(FrozenInstanceError):
        summary.inspections = 2  # type: ignore[misc]


def test_fail_recorded_carries_the_fail_qc_metadata_ids() -> None:
    recorded = FailRecorded(qc_inspection_id=uuid.uuid4(), qc_issue_id=uuid.uuid4())
    assert recorded == FailRecorded(
        qc_inspection_id=recorded.qc_inspection_id, qc_issue_id=recorded.qc_issue_id
    )
    with pytest.raises(FrozenInstanceError):
        recorded.qc_issue_id = uuid.uuid4()  # type: ignore[misc]

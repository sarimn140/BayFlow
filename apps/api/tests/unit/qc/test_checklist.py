"""The default QC checklist and its rules, DB-free (D46; spec 03 §3.6; `modules/qc.md`).

QC-12 (template, unit half), QC-13 (missing / repeated / unknown keys, failed items on pass),
QC-15 (stored form: template order, labels, item notes).
"""

import itertools
from dataclasses import dataclass

import pytest

from app.modules.qc.domain.checklist import (
    CHECKLIST,
    CHECKLIST_INCOMPLETE,
    CHECKLIST_ITEM_FAILED,
    CHECKLIST_LABELS,
    ITEM_FAILED_MESSAGE,
    ITEM_NOTE_MAX_LENGTH,
    stored_checklist,
    validate_checklist,
)
from app.shared.enums import QcChecklistKey

K = QcChecklistKey
SPEC_03_TEMPLATE = [
    ("road_test", "Road test"),
    ("no_warning_lights", "No warning lights"),
    ("no_leaks", "No leaks"),
    ("fluid_levels", "Fluid levels OK"),
    ("complaint_resolved", "Customer complaint resolved"),
]


@dataclass(frozen=True)
class Item:
    """Any object with `key`, `passed` and `note` satisfies the domain's `ChecklistEntry`."""

    key: QcChecklistKey
    passed: bool = True
    note: str | None = None


def full(*, failed: frozenset[QcChecklistKey] = frozenset()) -> list[Item]:
    return [Item(key, passed=key not in failed) for key in QcChecklistKey]


# --- Template (QC-12) -----------------------------------------------------------------------------


def test_qc12_template_is_the_five_d46_items_in_order_with_spec_03_labels() -> None:
    assert [(item.key.value, item.label) for item in CHECKLIST] == SPEC_03_TEMPLATE
    assert [item.key for item in CHECKLIST] == list(QcChecklistKey)  # glossary §5 order
    assert dict(CHECKLIST_LABELS) == {K(key): label for key, label in SPEC_03_TEMPLATE}


def test_template_is_immutable() -> None:
    with pytest.raises(TypeError):
        CHECKLIST_LABELS[K.ROAD_TEST] = "changed"  # type: ignore[index]


# --- Valid checklists -----------------------------------------------------------------------------


@pytest.mark.parametrize("order", list(itertools.permutations(range(5)))[::17])
@pytest.mark.parametrize("require_all_passed", [True, False])
def test_qc13_every_key_once_in_any_order_is_valid(
    order: tuple[int, ...], require_all_passed: bool
) -> None:
    items = full()
    shuffled = [items[index] for index in order]
    assert validate_checklist(shuffled, require_all_passed=require_all_passed) == []


def test_failed_items_are_allowed_when_not_every_item_must_pass() -> None:
    """fail-qc: a sent checklist needs the five keys, each once; any values (spec 03 §5.2)."""
    items = full(failed=frozenset(QcChecklistKey))
    assert validate_checklist(items, require_all_passed=False) == []


# --- Missing and repeated keys (QC-13) ------------------------------------------------------------


@pytest.mark.parametrize("missing", list(QcChecklistKey))
@pytest.mark.parametrize("require_all_passed", [True, False])
def test_qc13_a_missing_key_is_checklist_incomplete(
    missing: QcChecklistKey, require_all_passed: bool
) -> None:
    items = [item for item in full() if item.key != missing]
    errors = validate_checklist(items, require_all_passed=require_all_passed)
    assert len(errors) == 1
    assert errors[0]["field"] == "checklist"
    assert errors[0]["code"] == CHECKLIST_INCOMPLETE
    assert f"missing: {missing.value}" in errors[0]["message"]


def test_qc13_an_empty_checklist_misses_every_key() -> None:
    errors = validate_checklist([], require_all_passed=True)
    assert [(error["field"], error["code"]) for error in errors] == [
        ("checklist", CHECKLIST_INCOMPLETE)
    ]
    assert errors[0]["message"] == (
        "The checklist must list each of the 5 items exactly once (missing: road_test, "
        "no_warning_lights, no_leaks, fluid_levels, complaint_resolved)."
    )


@pytest.mark.parametrize("repeated", list(QcChecklistKey))
def test_qc13_a_repeated_key_is_checklist_incomplete(repeated: QcChecklistKey) -> None:
    items = [*full(), Item(repeated)]
    errors = validate_checklist(items, require_all_passed=True)
    assert [(error["field"], error["code"]) for error in errors] == [
        ("checklist", CHECKLIST_INCOMPLETE)
    ]
    assert f"repeated: {repeated.value}" in errors[0]["message"]


def test_qc13_missing_and_repeated_keys_are_named_in_one_error() -> None:
    items = [Item(K.ROAD_TEST), Item(K.ROAD_TEST), Item(K.NO_LEAKS), Item(K.FLUID_LEVELS)]
    errors = validate_checklist(items, require_all_passed=False)
    assert len(errors) == 1
    assert errors[0]["message"] == (
        "The checklist must list each of the 5 items exactly once "
        "(missing: no_warning_lights, complaint_resolved; repeated: road_test)."
    )


def test_a_key_given_as_its_plain_string_value_counts() -> None:
    items = [Item(key.value) for key in QcChecklistKey]  # type: ignore[arg-type]
    assert validate_checklist(items, require_all_passed=True) == []
    assert stored_checklist(items)[0]["key"] == "road_test"


# --- Failed items on pass (QC-13, QC-01 unit half) ------------------------------------------------


def test_qc13_every_failed_item_is_reported_at_its_own_index_on_pass() -> None:
    items = full(failed=frozenset({K.NO_LEAKS, K.COMPLAINT_RESOLVED}))
    errors = validate_checklist(items, require_all_passed=True)
    assert errors == [
        {
            "field": "checklist.2.passed",
            "message": ITEM_FAILED_MESSAGE,
            "code": "checklist_item_failed",
        },
        {
            "field": "checklist.4.passed",
            "message": ITEM_FAILED_MESSAGE,
            "code": "checklist_item_failed",
        },
    ]
    assert ITEM_FAILED_MESSAGE == "This item failed — use fail-qc."


def test_indexes_follow_the_order_the_items_were_sent() -> None:
    items = [Item(K.COMPLAINT_RESOLVED, passed=False), *full()[:4]]
    errors = validate_checklist(items, require_all_passed=True)
    assert [error["field"] for error in errors] == ["checklist.0.passed"]


def test_incomplete_and_failed_items_are_reported_together() -> None:
    items = [Item(K.ROAD_TEST, passed=False), Item(K.NO_LEAKS)]
    errors = validate_checklist(items, require_all_passed=True)
    assert [(error["field"], error["code"]) for error in errors] == [
        ("checklist", CHECKLIST_INCOMPLETE),
        ("checklist.0.passed", CHECKLIST_ITEM_FAILED),
    ]


def test_a_non_boolean_passed_never_counts_as_passed() -> None:
    items = [Item(key, passed=1) for key in QcChecklistKey]  # type: ignore[arg-type]
    errors = validate_checklist(items, require_all_passed=True)
    assert len(errors) == 5
    assert {error["code"] for error in errors} == {CHECKLIST_ITEM_FAILED}


# --- Defence for direct callers (the schema answers these first) ----------------------------------


def test_an_unknown_key_from_a_direct_caller_is_enum_at_its_index() -> None:
    items = [*full(), Item("brakes")]  # type: ignore[arg-type]
    errors = validate_checklist(items, require_all_passed=False)
    assert errors == [
        {
            "field": "checklist.5.key",
            "message": (
                "Input should be 'road_test', 'no_warning_lights', 'no_leaks', 'fluid_levels' "
                "or 'complaint_resolved'"
            ),
            "code": "enum",
        }
    ]


def test_an_unknown_key_does_not_fill_a_missing_one() -> None:
    items = [*full()[:4], Item("brakes")]  # type: ignore[arg-type]
    codes = [error["code"] for error in validate_checklist(items, require_all_passed=False)]
    assert codes == ["enum", CHECKLIST_INCOMPLETE]


def test_an_item_note_over_500_characters_is_too_long() -> None:
    items = full()
    items[1] = Item(K.NO_WARNING_LIGHTS, note="x" * (ITEM_NOTE_MAX_LENGTH + 1))
    items[2] = Item(K.NO_LEAKS, note="  " + "y" * ITEM_NOTE_MAX_LENGTH + "  ")  # trimmed: fits
    errors = validate_checklist(items, require_all_passed=False)
    assert errors == [
        {
            "field": "checklist.1.note",
            "message": "String should have at most 500 characters",
            "code": "string_too_long",
        }
    ]


# --- Stored form (QC-15) --------------------------------------------------------------------------


def test_qc15_stored_form_is_in_template_order_with_labels_and_notes() -> None:
    items = [
        Item(K.COMPLAINT_RESOLVED, note="  Customer's noise is gone  "),
        Item(K.FLUID_LEVELS),
        Item(K.NO_LEAKS, passed=False, note="Oil leak at the filter"),
        Item(K.NO_WARNING_LIGHTS, note="   "),
        Item(K.ROAD_TEST),
    ]
    assert stored_checklist(items) == [
        {"key": "road_test", "label": "Road test", "passed": True},
        {"key": "no_warning_lights", "label": "No warning lights", "passed": True},
        {
            "key": "no_leaks",
            "label": "No leaks",
            "passed": False,
            "note": "Oil leak at the filter",
        },
        {"key": "fluid_levels", "label": "Fluid levels OK", "passed": True},
        {
            "key": "complaint_resolved",
            "label": "Customer complaint resolved",
            "passed": True,
            "note": "Customer's noise is gone",
        },
    ]


def test_stored_values_are_plain_json_types() -> None:
    stored = stored_checklist(full())
    for entry in stored:
        assert type(entry["key"]) is str
        assert type(entry["passed"]) is bool


@pytest.mark.parametrize(
    "items",
    [
        [],
        full()[:4],
        [*full(), Item(K.ROAD_TEST)],
        [*full()[:4], Item(K.ROAD_TEST)],
    ],
    ids=["empty", "missing", "repeated", "repeated-instead-of-missing"],
)
def test_stored_checklist_refuses_an_unvalidated_checklist(items: list[Item]) -> None:
    with pytest.raises(ValueError, match="validated checklist"):
        stored_checklist(items)

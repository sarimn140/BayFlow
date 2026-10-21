"""The default QC checklist (D46) and its rules — pure Python, no I/O (spec 01 domain row).

- `CHECKLIST`: the five template items in D46 order with their spec 03 §3.6 labels.
- `validate_checklist(items, *, require_all_passed)`: returns field errors, never raises
  (`modules/qc.md` "The checklist"). Exactly the five keys, each once, in any order; a missing or
  repeated key -> `checklist` / `checklist_incomplete`. With `require_all_passed` (`pass-qc`), every
  failed item -> `checklist.N.passed` / `checklist_item_failed`, all reported together. An unknown
  key normally never gets here (the request schema types `key` as `QcChecklistKey` and answers
  `enum` at `checklist.N.key`); direct callers get the same answer from this function.
- `stored_checklist(items)`: the JSON stored on `qc_inspections.checklist` (spec 02 §3.18): the
  five items in template order, each `{"key", "label", "passed"}` plus `"note"` when given. The
  label is copied at write time, so a finished round keeps its wording if a label changes later.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

from app.core.errors import FieldError
from app.shared.enums import QcChecklistKey

CHECKLIST_FIELD = "checklist"
CHECKLIST_INCOMPLETE = "checklist_incomplete"
CHECKLIST_ITEM_FAILED = "checklist_item_failed"
UNKNOWN_KEY_CODE = "enum"  # the code Pydantic gives an unknown `QcChecklistKey` (spec 03 §2.3)
ITEM_FAILED_MESSAGE = "This item failed — use fail-qc."
ITEM_NOTE_MAX_LENGTH = 500  # spec 03 §3.6: `note` string? <= 500


@dataclass(frozen=True, slots=True)
class ChecklistTemplateItem:
    """One item of the default checklist."""

    key: QcChecklistKey
    label: str


# D46 order; labels from spec 03 §3.6 (`QcChecklistTemplateItem`).
CHECKLIST: tuple[ChecklistTemplateItem, ...] = (
    ChecklistTemplateItem(QcChecklistKey.ROAD_TEST, "Road test"),
    ChecklistTemplateItem(QcChecklistKey.NO_WARNING_LIGHTS, "No warning lights"),
    ChecklistTemplateItem(QcChecklistKey.NO_LEAKS, "No leaks"),
    ChecklistTemplateItem(QcChecklistKey.FLUID_LEVELS, "Fluid levels OK"),
    ChecklistTemplateItem(QcChecklistKey.COMPLAINT_RESOLVED, "Customer complaint resolved"),
)
CHECKLIST_LABELS: Mapping[QcChecklistKey, str] = MappingProxyType(
    {item.key: item.label for item in CHECKLIST}
)


class ChecklistEntry(Protocol):
    """What the rules need from one submitted item (`schemas.QcChecklistItemWrite` fits)."""

    @property
    def key(self) -> QcChecklistKey: ...

    @property
    def passed(self) -> bool: ...

    @property
    def note(self) -> str | None: ...


def _is_template_key(key: object) -> bool:
    return isinstance(key, str) and key in CHECKLIST_LABELS


def _unknown_key_message() -> str:
    """The wording Pydantic uses for an invalid enum member, so both layers read the same."""
    quoted = [f"'{item.key.value}'" for item in CHECKLIST]
    return f"Input should be {', '.join(quoted[:-1])} or {quoted[-1]}"


def _incomplete_message(missing: Sequence[str], repeated: Sequence[str]) -> str:
    problems: list[str] = []
    if missing:
        problems.append(f"missing: {', '.join(missing)}")
    if repeated:
        problems.append(f"repeated: {', '.join(repeated)}")
    return (
        f"The checklist must list each of the {len(CHECKLIST)} items exactly once "
        f"({'; '.join(problems)})."
    )


def _note_too_long(note: object) -> bool:
    return isinstance(note, str) and len(note.strip()) > ITEM_NOTE_MAX_LENGTH


def validate_checklist(
    items: Sequence[ChecklistEntry], *, require_all_passed: bool
) -> list[FieldError]:
    """Field errors for a submitted checklist (empty list = valid). Never raises."""
    errors: list[FieldError] = []
    known_keys: list[str] = []
    for index, item in enumerate(items):
        if _is_template_key(item.key):
            known_keys.append(str(item.key))
        else:
            errors.append(
                FieldError(
                    field=f"{CHECKLIST_FIELD}.{index}.key",
                    message=_unknown_key_message(),
                    code=UNKNOWN_KEY_CODE,
                )
            )
        if _note_too_long(item.note):
            errors.append(
                FieldError(
                    field=f"{CHECKLIST_FIELD}.{index}.note",
                    message=f"String should have at most {ITEM_NOTE_MAX_LENGTH} characters",
                    code="string_too_long",
                )
            )

    counts = Counter(known_keys)
    missing = [item.key.value for item in CHECKLIST if counts[item.key.value] == 0]
    repeated = [item.key.value for item in CHECKLIST if counts[item.key.value] > 1]
    if missing or repeated:
        errors.append(
            FieldError(
                field=CHECKLIST_FIELD,
                message=_incomplete_message(missing, repeated),
                code=CHECKLIST_INCOMPLETE,
            )
        )

    if require_all_passed:
        errors.extend(
            FieldError(
                field=f"{CHECKLIST_FIELD}.{index}.passed",
                message=ITEM_FAILED_MESSAGE,
                code=CHECKLIST_ITEM_FAILED,
            )
            for index, item in enumerate(items)
            if item.passed is not True
        )
    return errors


def _clean_note(note: str | None) -> str | None:
    if note is None:
        return None
    return note.strip() or None


def stored_checklist(items: Sequence[ChecklistEntry]) -> list[dict[str, Any]]:
    """The JSON array stored on the inspection, in template order with each label snapshotted.

    Precondition: `validate_checklist(items, ...)` returned no error (each key exactly once).
    """
    by_key = {str(item.key): item for item in items}
    if len(by_key) != len(items) or set(by_key) != set(CHECKLIST_LABELS):
        msg = "stored_checklist() needs a validated checklist (each template key exactly once)"
        raise ValueError(msg)
    stored: list[dict[str, Any]] = []
    for template in CHECKLIST:
        entry = by_key[template.key.value]
        value: dict[str, Any] = {
            "key": template.key.value,
            "label": template.label,
            "passed": entry.passed is True,
        }
        note = _clean_note(entry.note)
        if note is not None:
            value["note"] = note
        stored.append(value)
    return stored

"""QC text limits and the round count, DB-free (spec 03 §3.3, §5.2; spec 02 §3.18-§3.19).

QC-02 (issue title 1-120, description 1-2000; unit half) and QC-14 (`qc_round`, unit half).
"""

import pytest

from app.modules.qc.domain.rules import (
    ISSUE_DESCRIPTION_MAX_LENGTH,
    ISSUE_TITLE_MAX_LENGTH,
    NOTES_MAX_LENGTH,
    check_optional_text,
    check_required_text,
    qc_round,
)
from app.shared.enums import BookingStatus


def test_limits_equal_the_column_sizes() -> None:
    assert (ISSUE_TITLE_MAX_LENGTH, ISSUE_DESCRIPTION_MAX_LENGTH, NOTES_MAX_LENGTH) == (
        120,
        2000,
        2000,
    )


# --- Required text (issue title and description) --------------------------------------------------


def test_required_text_is_trimmed() -> None:
    assert check_required_text("  Oil leak at filter  ", field="issue_title", max_length=120) == (
        "Oil leak at filter",
        [],
    )


@pytest.mark.parametrize(
    ("value", "code", "message"),
    [
        (None, "missing", "Field required"),
        ("", "string_too_short", "String should have at least 1 character"),
        ("   \n\t ", "string_too_short", "String should have at least 1 character"),
        ("x" * 121, "string_too_long", "String should have at most 120 characters"),
        (42, "string_type", "Input should be a valid string"),
    ],
    ids=["none", "empty", "blank", "too-long", "not-a-string"],
)
def test_qc02_required_text_errors_mirror_pydantic(value: object, code: str, message: str) -> None:
    _, errors = check_required_text(value, field="issue_title", max_length=120)
    assert errors == [{"field": "issue_title", "message": message, "code": code}]


def test_required_text_at_the_limit_after_trimming_is_accepted() -> None:
    value, errors = check_required_text(" " + "d" * 2000 + " ", field="d", max_length=2000)
    assert errors == []
    assert value == "d" * 2000


# --- Optional text (notes) ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("", None), ("   ", None), ("  Road test fine  ", "Road test fine")],
)
def test_optional_text_is_trimmed_and_blank_is_no_value(
    value: str | None, expected: str | None
) -> None:
    assert check_optional_text(value, field="notes", max_length=2000) == (expected, [])


def test_optional_text_over_the_limit_is_too_long() -> None:
    _, errors = check_optional_text("n" * 2001, field="notes", max_length=2000)
    assert errors == [
        {
            "field": "notes",
            "message": "String should have at most 2000 characters",
            "code": "string_too_long",
        }
    ]


def test_optional_text_of_another_type_is_refused() -> None:
    assert check_optional_text(["notes"], field="notes", max_length=10) == (
        None,
        [{"field": "notes", "message": "Input should be a valid string", "code": "string_type"}],
    )


# --- qc_round (spec 03 §3.3) ----------------------------------------------------------------------


@pytest.mark.parametrize("status", list(BookingStatus))
def test_qc14_qc_round_adds_the_waiting_round_only_while_qc_pending(status: BookingStatus) -> None:
    waiting = 1 if status is BookingStatus.QC_PENDING else 0
    assert qc_round(0, status) == waiting
    assert qc_round(2, status) == 2 + waiting


def test_qc14_qc_round_through_a_fail_loop() -> None:
    """0 before QC, 1 at QC_PENDING, 1 while picked and after the fail, 2 at the re-test."""
    steps = [
        (0, BookingStatus.IN_REPAIR, 0),
        (0, BookingStatus.QC_PENDING, 1),
        (1, BookingStatus.QC_IN_PROGRESS, 1),
        (1, BookingStatus.IN_REPAIR, 1),
        (1, BookingStatus.QC_PENDING, 2),
        (2, BookingStatus.QC_IN_PROGRESS, 2),
        (2, BookingStatus.READY_FOR_PICKUP, 2),
    ]
    assert [qc_round(inspections, status) for inspections, status, _ in steps] == [
        expected for _, _, expected in steps
    ]

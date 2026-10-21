"""QC field limits and the round count — pure Python (spec 03 §3.6, §5.2; spec 02 §3.18-§3.19).

The request schemas enforce the same limits first (422 before any service runs); the service
re-checks them through these functions so that a direct caller (the seed, a test, a future
module) gets the same 422 instead of a database error. The limits equal the column sizes:
`qc_issues.title` varchar(120), `description` varchar(2000), `qc_inspections.notes`
varchar(2000), plus `ck_qc_issues_title_not_blank` / `ck_qc_issues_description_not_blank`.
Error codes and messages mirror Pydantic's, so both layers answer alike (spec 03 §2.3).
"""

from app.core.errors import FieldError
from app.shared.enums import BookingStatus

NOTES_MAX_LENGTH = 2000  # `notes`? <= 2000 (pass-qc, fail-qc)
ISSUE_TITLE_MAX_LENGTH = 120  # `issue_title` 1-120
ISSUE_DESCRIPTION_MAX_LENGTH = 2000  # `issue_description` 1-2000

# The field names of spec 03 §5.2's `PassQcRequest` / `FailQcRequest` bodies.
NOTES_FIELD = "notes"
ISSUE_TITLE_FIELD = "issue_title"
ISSUE_DESCRIPTION_FIELD = "issue_description"


def _wrong_type(field: str) -> FieldError:
    return FieldError(field=field, message="Input should be a valid string", code="string_type")


def _too_long(field: str, max_length: int) -> FieldError:
    return FieldError(
        field=field,
        message=f"String should have at most {max_length} characters",
        code="string_too_long",
    )


def check_optional_text(
    value: object, *, field: str, max_length: int
) -> tuple[str | None, list[FieldError]]:
    """An optional free text: trimmed (spec 03 §1.5), blank -> None, at most `max_length`."""
    if value is None:
        return None, []
    if not isinstance(value, str):
        return None, [_wrong_type(field)]
    cleaned = value.strip()
    if not cleaned:
        return None, []
    if len(cleaned) > max_length:
        return cleaned, [_too_long(field, max_length)]
    return cleaned, []


def check_required_text(
    value: object, *, field: str, max_length: int
) -> tuple[str, list[FieldError]]:
    """A required free text: trimmed, 1..`max_length` characters, never blank."""
    if value is None:
        return "", [FieldError(field=field, message="Field required", code="missing")]
    if not isinstance(value, str):
        return "", [_wrong_type(field)]
    cleaned = value.strip()
    if not cleaned:
        return "", [
            FieldError(
                field=field,
                message="String should have at least 1 character",
                code="string_too_short",
            )
        ]
    if len(cleaned) > max_length:
        return cleaned, [_too_long(field, max_length)]
    return cleaned, []


def qc_round(inspections: int, status: BookingStatus) -> int:
    """`qc_round` (spec 03 §3.3): the booking's QC rounds so far, plus the one waiting while
    `QC_PENDING`; 0 when it never reached QC (`modules/qc.md` "Public service interface")."""
    return inspections + (1 if status == BookingStatus.QC_PENDING else 0)

"""Application errors (D49, glossary §10). Plain Python: no framework imports.

Services and the domain raise these; `app.core.error_handlers` renders them as RFC 9457
`application/problem+json` with the extension member `code`. Because this module imports nothing
from FastAPI, the pure domain layer may raise them too (spec 01 layer table).
"""

from collections.abc import Mapping, Sequence
from enum import StrEnum
from http import HTTPStatus
from typing import ClassVar, TypedDict


class ErrorCode(StrEnum):
    """Every `code` an error response can carry (glossary §10). Values equal the names."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_SLOT = "INVALID_SLOT"
    ESTIMATE_EMPTY = "ESTIMATE_EMPTY"
    MEMBER_NOT_ELIGIBLE = "MEMBER_NOT_ELIGIBLE"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    FORBIDDEN = "FORBIDDEN"
    NOT_ASSIGNED = "NOT_ASSIGNED"
    IDENTITY_NOT_VERIFIED = "IDENTITY_NOT_VERIFIED"  # bonus
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    EMAIL_ALREADY_REGISTERED = "EMAIL_ALREADY_REGISTERED"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    CONCURRENT_UPDATE = "CONCURRENT_UPDATE"
    SLOT_FULL = "SLOT_FULL"
    ALREADY_PICKED = "ALREADY_PICKED"
    STALE_ESTIMATE = "STALE_ESTIMATE"
    ESTIMATE_LOCKED = "ESTIMATE_LOCKED"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    CALL_BUSY = "CALL_BUSY"  # bonus
    CALL_ALREADY_ANSWERED = "CALL_ALREADY_ANSWERED"  # bonus
    CALL_NOT_ACTIVE = "CALL_NOT_ACTIVE"  # bonus
    CONFLICT = "CONFLICT"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    SHOP_SUSPENDED = "SHOP_SUSPENDED"  # D96, spec 19 §2
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    CALLING_DISABLED = "CALLING_DISABLED"  # bonus
    AI_DISABLED = "AI_DISABLED"  # bonus, D103
    AI_LIMIT_REACHED = "AI_LIMIT_REACHED"  # bonus, D103
    AI_UNAVAILABLE = "AI_UNAVAILABLE"  # bonus, D103

    @property
    def http_status(self) -> int:
        """The HTTP status the glossary assigns to this code."""
        return _HTTP_STATUS[self]

    @property
    def default_detail(self) -> str:
        """A safe, human-readable default message (no internals)."""
        return _DEFAULT_DETAIL[self]


_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.INVALID_SLOT: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.ESTIMATE_EMPTY: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.MEMBER_NOT_ELIGIBLE: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.UNAUTHENTICATED: HTTPStatus.UNAUTHORIZED,
    ErrorCode.INVALID_CREDENTIALS: HTTPStatus.UNAUTHORIZED,
    ErrorCode.FORBIDDEN: HTTPStatus.FORBIDDEN,
    ErrorCode.NOT_ASSIGNED: HTTPStatus.FORBIDDEN,
    ErrorCode.IDENTITY_NOT_VERIFIED: HTTPStatus.FORBIDDEN,
    ErrorCode.NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.METHOD_NOT_ALLOWED: HTTPStatus.METHOD_NOT_ALLOWED,
    ErrorCode.EMAIL_ALREADY_REGISTERED: HTTPStatus.CONFLICT,
    ErrorCode.INVALID_TRANSITION: HTTPStatus.CONFLICT,
    ErrorCode.CONCURRENT_UPDATE: HTTPStatus.CONFLICT,
    ErrorCode.SLOT_FULL: HTTPStatus.CONFLICT,
    ErrorCode.ALREADY_PICKED: HTTPStatus.CONFLICT,
    ErrorCode.STALE_ESTIMATE: HTTPStatus.CONFLICT,
    ErrorCode.ESTIMATE_LOCKED: HTTPStatus.CONFLICT,
    ErrorCode.INSUFFICIENT_STOCK: HTTPStatus.CONFLICT,
    ErrorCode.CALL_BUSY: HTTPStatus.CONFLICT,
    ErrorCode.CALL_ALREADY_ANSWERED: HTTPStatus.CONFLICT,
    ErrorCode.CALL_NOT_ACTIVE: HTTPStatus.CONFLICT,
    ErrorCode.CONFLICT: HTTPStatus.CONFLICT,
    ErrorCode.PAYLOAD_TOO_LARGE: HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    ErrorCode.SHOP_SUSPENDED: HTTPStatus.FORBIDDEN,
    ErrorCode.RATE_LIMITED: HTTPStatus.TOO_MANY_REQUESTS,
    ErrorCode.INTERNAL_ERROR: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.CALLING_DISABLED: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.AI_DISABLED: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.AI_LIMIT_REACHED: HTTPStatus.TOO_MANY_REQUESTS,
    ErrorCode.AI_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
}

_DEFAULT_DETAIL: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "The request contains invalid fields.",
    ErrorCode.INVALID_SLOT: "This time slot cannot be booked.",
    ErrorCode.ESTIMATE_EMPTY: "The estimate has no lines.",
    ErrorCode.MEMBER_NOT_ELIGIBLE: (
        "That person is not an active member of this shop with the required role."
    ),
    ErrorCode.UNAUTHENTICATED: "Authentication required.",
    ErrorCode.INVALID_CREDENTIALS: "The e-mail or password is incorrect.",
    ErrorCode.FORBIDDEN: "You are not allowed to do this.",
    ErrorCode.NOT_ASSIGNED: "This job is not assigned to you.",
    ErrorCode.IDENTITY_NOT_VERIFIED: "The caller's identity has not been verified yet.",
    ErrorCode.NOT_FOUND: "The requested resource was not found.",
    ErrorCode.METHOD_NOT_ALLOWED: "This HTTP method is not supported on this path.",
    ErrorCode.EMAIL_ALREADY_REGISTERED: "This e-mail address already has a BayFlow account.",
    ErrorCode.INVALID_TRANSITION: "This action is not allowed in the booking's current status.",
    ErrorCode.CONCURRENT_UPDATE: "The record was changed by someone else. Reload and try again.",
    ErrorCode.SLOT_FULL: "This time slot is fully booked. Please choose another slot.",
    ErrorCode.ALREADY_PICKED: "Another QC inspector already picked this job.",
    ErrorCode.STALE_ESTIMATE: "This estimate version is no longer the current one.",
    ErrorCode.ESTIMATE_LOCKED: "The estimate cannot be edited in the booking's current status.",
    ErrorCode.INSUFFICIENT_STOCK: "There is not enough stock available.",
    ErrorCode.CALL_BUSY: "There is already an active call for this booking.",
    ErrorCode.CALL_ALREADY_ANSWERED: "Someone else already answered this call.",
    ErrorCode.CALL_NOT_ACTIVE: "This call is no longer active.",
    ErrorCode.CONFLICT: "The request conflicts with the current state of the resource.",
    ErrorCode.PAYLOAD_TOO_LARGE: "The request body is too large.",
    ErrorCode.SHOP_SUSPENDED: "This shop is suspended. Contact BayFlow support.",
    ErrorCode.RATE_LIMITED: "Too many attempts. Please wait and try again.",
    ErrorCode.INTERNAL_ERROR: "An unexpected error occurred. Please try again.",
    ErrorCode.CALLING_DISABLED: "Calling is not available right now.",
    ErrorCode.AI_DISABLED: "This AI feature is not enabled.",
    ErrorCode.AI_LIMIT_REACHED: "This shop has reached its AI usage limit for now.",
    ErrorCode.AI_UNAVAILABLE: "AI is unavailable right now. Please carry on without it.",
}


class FieldError(TypedDict):
    """One invalid input field of a 422 response (`errors[]`)."""

    field: str
    message: str
    code: str


class AppError(Exception):
    """An expected, client-facing error carrying a glossary §10 code.

    `detail` is shown to the user and must never contain internals. `headers` are added to the
    response (e.g. `Retry-After`, a cookie-clearing `Set-Cookie`). `errors` lists invalid fields for
    `VALIDATION_ERROR`-style responses.
    """

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        detail: str | None = None,
        *,
        headers: Mapping[str, str] | None = None,
        errors: Sequence[FieldError] | None = None,
    ) -> None:
        self.detail = detail if detail is not None else self.code.default_detail
        self.headers: dict[str, str] = dict(headers or {})
        self.errors: list[FieldError] | None = list(errors) if errors is not None else None
        super().__init__(self.detail)

    @property
    def status_code(self) -> int:
        return self.code.http_status

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code.value!r}, detail={self.detail!r})"


class ValidationFailed(AppError):
    code = ErrorCode.VALIDATION_ERROR


class InvalidSlot(AppError):
    code = ErrorCode.INVALID_SLOT


class EstimateEmpty(AppError):
    code = ErrorCode.ESTIMATE_EMPTY


class MemberNotEligible(AppError):
    code = ErrorCode.MEMBER_NOT_ELIGIBLE


class Unauthenticated(AppError):
    code = ErrorCode.UNAUTHENTICATED


class InvalidCredentials(AppError):
    code = ErrorCode.INVALID_CREDENTIALS


class Forbidden(AppError):
    code = ErrorCode.FORBIDDEN


class NotAssigned(AppError):
    code = ErrorCode.NOT_ASSIGNED


class IdentityNotVerified(AppError):
    code = ErrorCode.IDENTITY_NOT_VERIFIED


class NotFound(AppError):
    code = ErrorCode.NOT_FOUND


class MethodNotAllowed(AppError):
    code = ErrorCode.METHOD_NOT_ALLOWED


class EmailAlreadyRegistered(AppError):
    code = ErrorCode.EMAIL_ALREADY_REGISTERED


class InvalidTransition(AppError):
    code = ErrorCode.INVALID_TRANSITION


class ConcurrentUpdate(AppError):
    code = ErrorCode.CONCURRENT_UPDATE


class SlotFull(AppError):
    code = ErrorCode.SLOT_FULL


class AlreadyPicked(AppError):
    code = ErrorCode.ALREADY_PICKED


class StaleEstimate(AppError):
    code = ErrorCode.STALE_ESTIMATE


class EstimateLocked(AppError):
    code = ErrorCode.ESTIMATE_LOCKED


class InsufficientStock(AppError):
    code = ErrorCode.INSUFFICIENT_STOCK


class CallBusy(AppError):
    code = ErrorCode.CALL_BUSY


class CallAlreadyAnswered(AppError):
    code = ErrorCode.CALL_ALREADY_ANSWERED


class CallNotActive(AppError):
    code = ErrorCode.CALL_NOT_ACTIVE


class Conflict(AppError):
    code = ErrorCode.CONFLICT


class PayloadTooLarge(AppError):
    code = ErrorCode.PAYLOAD_TOO_LARGE


class ShopSuspended(AppError):
    """A platform admin suspended the shop (D96): every staff route, and customer booking actions
    except `cancel` (spec 19 §2)."""

    code = ErrorCode.SHOP_SUSPENDED


class RateLimited(AppError):
    code = ErrorCode.RATE_LIMITED


class InternalError(AppError):
    code = ErrorCode.INTERNAL_ERROR


class CallingDisabled(AppError):
    code = ErrorCode.CALLING_DISABLED


class AiDisabled(AppError):
    code = ErrorCode.AI_DISABLED


class AiLimitReached(AppError):
    code = ErrorCode.AI_LIMIT_REACHED


class AiUnavailable(AppError):
    code = ErrorCode.AI_UNAVAILABLE

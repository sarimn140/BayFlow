"""RFC 9457 problem details for every error response (D49; spec 03 §2; spec 04).

Body: `type` (`about:blank`), `title` (the HTTP reason phrase), `status`, `detail`, `instance` (the
path, no query string) and the extension member `code` (glossary §10); 422 adds
`errors: [{field, message, code}]`. Nothing internal is ever rendered: no stack trace, exception
text, SQL or submitted input (pydantic's `input` and `ctx` are dropped). Every 401 carries
`WWW-Authenticate: Bearer`, every 405 `Allow`, every 429 `Retry-After`.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.db_errors import INVALID_TEXT_DETAIL, constraint_name, error_code_for, sqlstate
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.http_headers import REQUEST_ID_HEADER, resolve_request_id, standard_headers
from app.core.logging import request_id_var
from app.core.security import ip_retry_after_seconds

logger = logging.getLogger("app.errors")

PROBLEM_JSON = "application/problem+json"
PROBLEM_TYPE = "about:blank"

# RFC 9110 reason phrases (Python 3.12's HTTPStatus still uses the older 413/422 names).
_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    413: "Content Too Large",
    422: "Unprocessable Content",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}

# spec 03 §2.4: framework HTTP errors that keep their status; any other 4xx becomes
# 422 VALIDATION_ERROR and any 5xx becomes 500 INTERNAL_ERROR.
_KEPT_HTTP_STATUSES: dict[int, ErrorCode] = {
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    429: ErrorCode.RATE_LIMITED,
}

_VALUE_ERROR_PREFIX = "Value error, "
_DEFAULT_RETRY_AFTER_SECONDS = 60


# --- Response bodies -----------------------------------------------------------------------------


class Problem(BaseModel):
    """RFC 9457 problem details (media type `application/problem+json`, spec 03 §2.1)."""

    type: str = PROBLEM_TYPE
    title: str
    status: int
    detail: str
    instance: str
    code: ErrorCode


class ValidationProblem(Problem):
    """A 422 problem listing the offending fields (spec 03 §2.3)."""

    errors: list[FieldError]


def problem_title(status: int) -> str:
    if status in _TITLES:
        return _TITLES[status]
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def problem_response(
    code: ErrorCode,
    *,
    instance: str,
    detail: str | None = None,
    status_code: int | None = None,
    headers: Mapping[str, str] | None = None,
    errors: Sequence[FieldError] | None = None,
) -> JSONResponse:
    """Build an `application/problem+json` response for `code`."""
    status = status_code if status_code is not None else code.http_status
    body: dict[str, object] = {
        "type": PROBLEM_TYPE,
        "title": problem_title(status),
        "status": status,
        "detail": detail if detail is not None else code.default_detail,
        "instance": instance,
        "code": code.value,
    }
    if errors is not None:
        body["errors"] = list(errors)
    response_headers = dict(headers or {})
    if status == HTTPStatus.UNAUTHORIZED:
        # RFC 9110 §15.5.2 requires a challenge; `Bearer` never opens a browser login prompt.
        response_headers.setdefault("WWW-Authenticate", "Bearer")
    return JSONResponse(body, status_code=status, headers=response_headers, media_type=PROBLEM_JSON)


def internal_error_response(instance: str) -> JSONResponse:
    return problem_response(ErrorCode.INTERNAL_ERROR, instance=instance)


def _field_name(loc: Sequence[object], error_type: str) -> str:
    """spec 03 §2.3: a dot path into the body (`vehicle.year`); query and path parameters keep
    their prefix (`query.limit`); `""` is the body as a whole (missing or not JSON)."""
    if error_type == "json_invalid":
        return ""
    parts = [str(part) for part in loc]
    if parts and parts[0] == "body":
        parts = parts[1:]
    return ".".join(parts)


def validation_field_errors(exc: RequestValidationError) -> list[FieldError]:
    """Pydantic errors as `{field, message, code}`, without the submitted `input` or `ctx`.

    Identical errors are reported once, in first-seen order. FastAPI caches a dependency's result
    only when it succeeds, so on a route with both `require_shop_member` and `require_roles` a
    malformed `shop_id` is validated twice and would otherwise be listed twice.
    """
    field_errors: list[FieldError] = []
    seen: set[tuple[str, str, str]] = set()
    for error in exc.errors():
        error_type = str(error.get("type", "value_error"))
        message = str(error.get("msg", "Invalid value.")).removeprefix(_VALUE_ERROR_PREFIX)
        field = _field_name(tuple(error.get("loc", ())), error_type)
        if (field, message, error_type) in seen:
            continue
        seen.add((field, message, error_type))
        field_errors.append(FieldError(field=field, message=message, code=error_type))
    return field_errors


# --- Exception handlers --------------------------------------------------------------------------


async def app_error_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, AppError):  # pragma: no cover - registered for AppError only
        return internal_error_response(request.url.path)
    if exc.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        logger.warning("application error %s", exc.code.value)
    return problem_response(
        exc.code,
        instance=request.url.path,
        detail=exc.detail,
        headers=exc.headers,
        errors=exc.errors,
    )


async def request_validation_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RequestValidationError):  # pragma: no cover
        return internal_error_response(request.url.path)
    return problem_response(
        ErrorCode.VALIDATION_ERROR,
        instance=request.url.path,
        errors=validation_field_errors(exc),
    )


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, StarletteHTTPException):  # pragma: no cover
        return internal_error_response(request.url.path)
    if exc.status_code in _KEPT_HTTP_STATUSES:
        return problem_response(
            _KEPT_HTTP_STATUSES[exc.status_code],
            instance=request.url.path,
            status_code=exc.status_code,
            headers=exc.headers,  # e.g. `Allow` on 405
        )
    if exc.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        return internal_error_response(request.url.path)
    return problem_response(ErrorCode.VALIDATION_ERROR, instance=request.url.path, errors=[])


async def database_error_handler(request: Request, exc: Exception) -> Response:
    """Constraint backstops -> their codes by constraint name (spec 03 §2.4); others -> 500."""
    if not isinstance(exc, DBAPIError):  # pragma: no cover - registered for DBAPIError only
        return internal_error_response(request.url.path)
    code = error_code_for(exc)
    if code is None:
        logger.error(
            "unmapped database error (sqlstate=%s, constraint=%s)",
            sqlstate(exc),
            constraint_name(exc),
            exc_info=exc,
        )
        return internal_error_response(request.url.path)
    if code is ErrorCode.VALIDATION_ERROR:  # text the database cannot store (NUL, lone surrogate)
        logger.info("database rejected client text (sqlstate=%s)", sqlstate(exc))
        return problem_response(
            code, instance=request.url.path, detail=INVALID_TEXT_DETAIL, errors=[]
        )
    logger.warning("database constraint %s -> %s", constraint_name(exc) or sqlstate(exc), code)
    return problem_response(code, instance=request.url.path)


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    """slowapi's per-IP ceilings (D69): 429 problem+json with `Retry-After`."""
    retry_after = ip_retry_after_seconds(request)
    if retry_after is None:
        retry_after = _DEFAULT_RETRY_AFTER_SECONDS
        if isinstance(exc, RateLimitExceeded) and exc.limit is not None:
            retry_after = max(1, int(exc.limit.limit.get_expiry()))
    return problem_response(
        ErrorCode.RATE_LIMITED,
        instance=request.url.path,
        detail=f"Too many attempts. Try again in {retry_after} seconds.",
        headers={"Retry-After": str(retry_after)},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    """Backstop run by Starlette's `ServerErrorMiddleware`, outside every other middleware.

    The request-context middleware normally renders unhandled errors itself (spec 03 §1.8); this
    handler only runs if that is impossible, so it sets the same headers on its own.
    """
    logger.error("unhandled error", exc_info=exc)
    request_id = request_id_var.get() or resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
    response = internal_error_response(request.url.path)
    for name, value in standard_headers(request.url.path, request_id):
        response.headers[name] = value
    return response


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(DBAPIError, database_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


# --- OpenAPI --------------------------------------------------------------------------------------

_SCHEMA_REF_PREFIX = "#/components/schemas/"
_PROBLEM_SCHEMAS = frozenset({"Problem", "ValidationProblem"})
_FASTAPI_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """`responses=` entries for routers: `ValidationProblem` for 422, `Problem` otherwise."""
    return {
        status: {
            "model": ValidationProblem if status == HTTPStatus.UNPROCESSABLE_ENTITY else Problem,
            "description": problem_title(status),
        }
        for status in statuses
    }


def _problem_component_schemas() -> dict[str, Any]:
    _, definitions = models_json_schema(
        [(Problem, "serialization"), (ValidationProblem, "serialization")],
        ref_template=_SCHEMA_REF_PREFIX + "{model}",
    )
    schemas: dict[str, Any] = definitions.get("$defs", {})
    return schemas


def _rewrite_error_content(response: dict[str, Any]) -> None:
    content = response.get("content", {})
    media = content.get("application/json")
    if media is None:
        return
    reference = str(media.get("schema", {}).get("$ref", ""))
    name = reference.removeprefix(_SCHEMA_REF_PREFIX)
    if name == "HTTPValidationError":
        media = {"schema": {"$ref": _SCHEMA_REF_PREFIX + "ValidationProblem"}}
    elif name not in _PROBLEM_SCHEMAS:
        return  # e.g. /health's 503 HealthRead body is not a problem (spec 03 §4.2)
    del content["application/json"]
    content[PROBLEM_JSON] = media


def add_problem_details_to_openapi(schema: dict[str, Any]) -> dict[str, Any]:
    """Document error bodies as `application/problem+json` (spec 03 §1.11), idempotently.

    FastAPI places response models under `application/json` and documents its own
    `HTTPValidationError` for 422; both are rewritten to the problem schemas the API returns.
    """
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            for status, response in operation.get("responses", {}).items():
                if str(status).isdigit() and int(status) >= HTTPStatus.BAD_REQUEST:
                    _rewrite_error_content(response)
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for name, definition in _problem_component_schemas().items():
        components.setdefault(name, definition)
    for name in _FASTAPI_VALIDATION_SCHEMAS:
        components.pop(name, None)
    return schema


def install_problem_openapi(app: FastAPI) -> None:
    """Post-process the generated schema with `add_problem_details_to_openapi`."""
    generate: Callable[[], dict[str, Any]] = app.openapi

    def openapi() -> dict[str, Any]:
        return add_problem_details_to_openapi(generate())

    # FastAPI documents replacing `app.openapi`; mypy sees it as assigning to a method.
    app.openapi = openapi  # type: ignore[method-assign]

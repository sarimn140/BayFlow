"""Structured JSON logs on stdout with a per-request id (spec 01 "Logging and request IDs").

One JSON object per line: `ts` (UTC), `level`, `logger`, `msg`, `request_id`, request context
fields (`user_id`, `shop_id` once known) and any `extra=` fields. WebSocket tickets in query strings
are redacted from every record, including uvicorn's own (spec 04 "Logging, errors and secrets").
Never pass passwords, tokens, cookies or request bodies to a logger.
"""

import json
import logging
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
# A mutable dict per request: dependencies add fields (user_id, shop_id) that the access log line
# and every later record of the request pick up, even across copied contexts.
_log_context_var: ContextVar[dict[str, str] | None] = ContextVar("log_context", default=None)

_HANDLER_NAME = "bayflow-json"
_TICKET_RE = re.compile(r"(ticket=)[^&\s\"']+")
_STANDARD_RECORD_ATTRS = frozenset(
    {
        *vars(logging.LogRecord("", logging.INFO, "", 0, "", (), None)),
        "message",
        "asctime",
        "taskName",
        "color_message",  # uvicorn's ANSI-coloured duplicate of `msg`
    }
)


def redact(text: str) -> str:
    """Replace the value of every `ticket=` query parameter with `[redacted]`."""
    return _TICKET_RE.sub(r"\1[redacted]", text)


class RedactingFilter(logging.Filter):
    """Rewrites a record's message so credentials in URLs never reach a handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


class JsonFormatter(logging.Formatter):
    """Formats a record as one line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        created = datetime.fromtimestamp(record.created, tz=UTC)
        payload: dict[str, object] = {
            "ts": created.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        request_id = request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id
        context = _log_context_var.get()
        if context:
            payload.update(context)
        payload.update(
            {
                key: value
                for key, value in vars(record).items()
                if key not in _STANDARD_RECORD_ATTRS and not key.startswith("_")
            }
        )
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON handler on the root logger (idempotent).

    Only the handler installed by this function is replaced, so test log capture keeps working.
    uvicorn's loggers propagate to the root handler; its access log is silenced because the
    request-context middleware writes one structured access line per request.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler.get_name() == _HANDLER_NAME:
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = True
    access_logger.setLevel(logging.WARNING)


@contextmanager
def request_log_context(request_id: str) -> Iterator[dict[str, str]]:
    """Bind `request_id` (and an empty field dict) to every log record inside the block."""
    fields: dict[str, str] = {}
    request_id_token = request_id_var.set(request_id)
    context_token = _log_context_var.set(fields)
    try:
        yield fields
    finally:
        _log_context_var.reset(context_token)
        request_id_var.reset(request_id_token)


def bind_log_context(**fields: object) -> None:
    """Add fields (e.g. `user_id`, `shop_id`) to the current request's log context."""
    context = _log_context_var.get()
    if context is not None:
        context.update({key: str(value) for key, value in fields.items() if value is not None})

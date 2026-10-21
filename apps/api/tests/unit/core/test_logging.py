"""Structured JSON logs with request ids and ticket redaction (spec 01, spec 04, D70)."""

import json
import logging

from app.core.logging import (
    JsonFormatter,
    RedactingFilter,
    bind_log_context,
    redact,
    request_log_context,
)


def make_record(message: str, *args: object, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("uvicorn.error", logging.INFO, __file__, 1, message, args, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_redact_hides_ticket_values_only() -> None:
    line = 'GET /api/v1/ws?ticket=eyJhbGciOi.abc.def&x=1 "ok"'
    assert redact(line) == 'GET /api/v1/ws?ticket=[redacted]&x=1 "ok"'
    assert redact("/api/v1/me?limit=20") == "/api/v1/me?limit=20"


def test_filter_rewrites_uvicorns_websocket_accept_line() -> None:
    record = make_record(
        '%s - "WebSocket %s" [accepted]', "127.0.0.1:5000", "/api/v1/ws?ticket=eyJ.secret.sig"
    )
    assert RedactingFilter().filter(record)
    assert record.getMessage() == (
        '127.0.0.1:5000 - "WebSocket /api/v1/ws?ticket=[redacted]" [accepted]'
    )


def test_json_formatter_emits_one_object_with_context_and_extras() -> None:
    formatter = JsonFormatter()
    with request_log_context("req-123"):
        bind_log_context(user_id="u-1", shop_id=None)
        line = formatter.format(make_record("hello %s", "world", status=200))
    payload = json.loads(line)
    assert payload["msg"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "uvicorn.error"
    assert payload["request_id"] == "req-123"
    assert payload["user_id"] == "u-1"
    assert "shop_id" not in payload
    assert payload["status"] == 200
    assert payload["ts"].endswith("Z")


def test_request_context_is_reset_after_the_block() -> None:
    with request_log_context("req-1"):
        pass
    payload = json.loads(JsonFormatter().format(make_record("outside")))
    assert "request_id" not in payload

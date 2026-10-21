"""History items → transcript entries for the summary POST (spec 05 §6.1).

Works on anything shaped like LiveKit's `ChatMessage`, `FunctionCall` and `FunctionCallOutput`
(read by `type`), so it is unit-tested without a live session.
"""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

MAX_TOOL_OUTPUT = 1000
MAX_ENTRIES = 300


def _at(item: Any) -> str | None:
    created = getattr(item, "created_at", None)
    if created is None:
        return None
    moment = (
        datetime.fromtimestamp(created, tz=UTC) if isinstance(created, int | float) else created
    )
    return moment.isoformat().replace("+00:00", "Z")


def _text(item: Any) -> str:
    text = getattr(item, "text_content", None)
    if text is not None:
        return str(text)
    return " ".join(part for part in getattr(item, "content", []) if isinstance(part, str))


def build_transcript(items: Iterable[Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in items:
        kind = getattr(item, "type", None)
        if kind == "message":
            role = getattr(item, "role", None)
            if role == "user":
                entries.append({"role": "customer", "text": _text(item), "at": _at(item)})
            elif role == "assistant":
                entries.append(
                    {
                        "role": "assistant",
                        "text": _text(item),
                        "interrupted": bool(getattr(item, "interrupted", False)),
                        "at": _at(item),
                    }
                )
        elif kind == "function_call":
            entries.append(
                {
                    "role": "tool_call",
                    "tool": item.name,
                    "text": str(item.arguments),
                    "at": _at(item),
                }
            )
        elif kind == "function_call_output":
            entries.append(
                {
                    "role": "tool_result",
                    "tool": item.name,
                    "text": str(item.output)[:MAX_TOOL_OUTPUT],
                    "is_error": bool(item.is_error),
                    "at": _at(item),
                }
            )
    return [{k: v for k, v in entry.items() if v is not None} for entry in entries][-MAX_ENTRIES:]

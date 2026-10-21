"""AG-02 (transcript builder) and AG-03 (summary: success, refusal → null + error)."""

from dataclasses import dataclass, field
from typing import Any

import pytest

from bayflow_agent import summary as summary_module
from bayflow_agent.config import Settings
from bayflow_agent.summary import CallSummary, summarise
from bayflow_agent.transcript import MAX_TOOL_OUTPUT, build_transcript


@dataclass
class Message:
    role: str
    text_content: str
    interrupted: bool = False
    created_at: float = 1_790_000_000.0
    type: str = "message"


@dataclass
class Call:
    name: str
    arguments: str
    type: str = "function_call"
    created_at: float = 1_790_000_001.0


@dataclass
class Output:
    name: str
    output: str
    is_error: bool = False
    type: str = "function_call_output"
    created_at: float = 1_790_000_002.0
    extra: dict[str, Any] = field(default_factory=dict)


def test_history_maps_to_transcript_entries() -> None:
    entries = build_transcript(
        [
            Message("system", "rules"),
            Message("user", "Hi, this is Ahmed"),
            Message("assistant", "Hello Ahmed", interrupted=True),
            Call("get_estimate", '{"booking_reference": "BF-7K2M9Q"}'),
            Output("get_estimate", "x" * 5000),
        ]
    )
    assert [entry["role"] for entry in entries] == [
        "customer",
        "assistant",
        "tool_call",
        "tool_result",
    ]
    assert entries[1]["interrupted"] is True
    assert entries[2]["tool"] == "get_estimate"
    assert len(entries[3]["text"]) == MAX_TOOL_OUTPUT
    assert entries[0]["at"].endswith("Z")


SETTINGS = Settings.model_validate({"llm_api_key": "k", "ai_provider": "gemini"})
GOOD = CallSummary.model_validate(
    {
        "intent": "Asked about the estimate",
        "intent_category": "ESTIMATE_INQUIRY",
        "details": "Told version 2 is 16,100 rupees.",
        "sentiment": "NEUTRAL",
        "follow_up_task_title": "Customer Ahmed asked about estimate",
        "urgent": False,
        "language": "en",
    }
)


async def test_a_valid_summary_is_posted(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(*_: object) -> CallSummary:
        return GOOD

    monkeypatch.setattr(summary_module, "_gemini", fake)
    payload = await summarise(SETTINGS, "Lahore Auto Care", [])
    assert payload["summary"]["intent_category"] == "ESTIMATE_INQUIRY"
    assert payload["summary_error"] is None
    assert payload["model"] == "gemini-2.5-flash"


async def test_a_failed_summary_posts_null_and_the_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def refuse(*_: object) -> CallSummary:
        msg = "refused"
        raise ValueError(msg)

    monkeypatch.setattr(summary_module, "_gemini", refuse)
    payload = await summarise(SETTINGS, "Lahore Auto Care", [{"role": "customer", "text": "hi"}])
    assert payload["summary"] is None
    assert payload["summary_error"] == "ValueError"
    assert payload["transcript"] == [{"role": "customer", "text": "hi"}]

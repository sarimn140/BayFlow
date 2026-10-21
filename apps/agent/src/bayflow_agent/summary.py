"""The post-call summary (spec 05 §6.2), with structured output from the selected provider.

The API re-validates everything (§6.3); a failure here posts `summary: null` with an error, and the
API stores a fallback summary and a task.
"""

import json
import logging
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel

from bayflow_agent.config import Settings
from bayflow_agent.prompts import SUMMARY_INSTRUCTIONS

logger = logging.getLogger("bayflow_agent.summary")


class CallIntent(StrEnum):  # mirror of the API's enum (glossary §5); the API re-validates
    STATUS_INQUIRY = "STATUS_INQUIRY"
    ESTIMATE_INQUIRY = "ESTIMATE_INQUIRY"
    APPOINTMENT_INQUIRY = "APPOINTMENT_INQUIRY"
    RESCHEDULE_REQUEST = "RESCHEDULE_REQUEST"
    PICKUP_INQUIRY = "PICKUP_INQUIRY"
    CALLBACK_REQUEST = "CALLBACK_REQUEST"
    COMPLAINT = "COMPLAINT"
    SAFETY_CONCERN = "SAFETY_CONCERN"
    OTHER = "OTHER"


class Sentiment(StrEnum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"


class CallSummary(BaseModel):
    intent: str
    intent_category: CallIntent
    details: str
    sentiment: Sentiment
    follow_up_task_title: str
    urgent: bool
    language: Literal["en", "ur", "mixed"]


def _input(transcript: list[dict[str, Any]]) -> str:
    return "Transcript (JSON lines):\n" + "\n".join(json.dumps(entry) for entry in transcript)


async def _gemini(settings: Settings, instructions: str, text: str) -> CallSummary:
    from google import genai  # noqa: PLC0415 - the selected provider only
    from google.genai import types  # noqa: PLC0415

    assert settings.llm_api_key is not None  # noqa: S101 - checked at start-up
    client = genai.Client(api_key=settings.llm_api_key.get_secret_value())
    response = await client.aio.models.generate_content(
        model=settings.summary_model,
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=instructions,
            response_mime_type="application/json",
            response_json_schema=CallSummary.model_json_schema(),
            temperature=0.2,
        ),
    )
    return CallSummary.model_validate_json(response.text or "")


async def _openai(settings: Settings, instructions: str, text: str) -> CallSummary:
    from openai import AsyncOpenAI  # noqa: PLC0415 - the selected provider only

    assert settings.llm_api_key is not None  # noqa: S101 - checked at start-up
    client = AsyncOpenAI(api_key=settings.llm_api_key.get_secret_value())
    response = await client.responses.parse(
        model=settings.summary_model,
        input=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": text},
        ],
        text_format=CallSummary,
    )
    if response.output_parsed is None:
        msg = "no parsed output (refusal)"
        raise ValueError(msg)
    return response.output_parsed


async def summarise(
    settings: Settings, shop_name: str, transcript: list[dict[str, Any]]
) -> dict[str, Any]:
    """The `/summary` body: transcript, summary (or null) and the error when there is none."""
    instructions = SUMMARY_INSTRUCTIONS.format(shop_name=shop_name)
    payload: dict[str, Any] = {
        "transcript": transcript,
        "summary": None,
        "summary_error": None,
        "model": settings.summary_model,
    }
    try:
        call = _gemini if settings.ai_provider == "gemini" else _openai
        summary = await call(settings, instructions, _input(transcript))
        payload["summary"] = summary.model_dump(mode="json")
    except Exception as exc:  # any failure → the API's fallback summary
        logger.warning("summary.failed", extra={"error": type(exc).__name__})
        payload["summary_error"] = f"{type(exc).__name__}"
    return payload

"""Gemini adapter of the `LlmProvider` port (D103), on the official `google-genai` SDK.

The answer is requested as JSON matching the output model's JSON Schema and is validated by
Pydantic here, never trusted as is. Every SDK failure becomes `LlmError` with a short, safe
message (no prompt, no key).
"""

import asyncio

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.modules.ai.providers.base import LlmError, LlmInvalidOutputError, LlmRequest, LlmResponse


class GeminiProvider:
    def __init__(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self._model

    async def generate[T: BaseModel](self, request: LlmRequest[T]) -> LlmResponse[T]:
        config = types.GenerateContentConfig(
            system_instruction=request.system,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            response_mime_type="application/json",
            response_json_schema=request.output_type.model_json_schema(),
        )
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model, contents=request.prompt, config=config
                ),
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            msg = f"timed out after {self._timeout:g} s"
            raise LlmError(msg) from exc
        except genai_errors.APIError as exc:
            msg = f"provider error {exc.code}: {exc.status or 'unknown'}"
            raise LlmError(msg) from exc
        except Exception as exc:  # network and SDK failures
            msg = f"provider call failed: {type(exc).__name__}"
            raise LlmError(msg) from exc
        text = response.text
        if not text:
            msg = "empty answer (blocked or no candidates)"
            raise LlmInvalidOutputError(msg)
        try:
            output = request.output_type.model_validate_json(text)
        except ValidationError as exc:
            msg = f"answer does not match {request.output_type.__name__}"
            raise LlmInvalidOutputError(msg) from exc
        usage = response.usage_metadata
        return LlmResponse(
            output=output,
            model=self._model,
            input_tokens=usage.prompt_token_count if usage else None,
            output_tokens=usage.candidates_token_count if usage else None,
        )

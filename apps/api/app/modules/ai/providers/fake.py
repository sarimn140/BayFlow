"""A scripted `LlmProvider` for tests and key-less local demos (`AI_TEXT_PROVIDER=fake`, D103).

`answer` decides each reply: a model instance or a dict (validated against the requested output
type, like a real answer), or an exception to raise. Every request is recorded, so tests can check
exactly what would have left the API. Production never builds it (`Settings.text_ai_configured`).
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from app.modules.ai.providers.base import LlmInvalidOutputError, LlmRequest, LlmResponse

type FakeAnswer = BaseModel | dict[str, Any] | Exception
type Answerer = Callable[[LlmRequest[Any]], FakeAnswer]


def _empty_answer(request: LlmRequest[Any]) -> FakeAnswer:
    """The default: the output type built from its defaults (fails for required fields)."""
    answer: BaseModel = request.output_type.model_construct()
    return answer


class FakeLlmProvider:
    def __init__(self, answer: Answerer | FakeAnswer | None = None, *, model: str = "fake-1"):
        self._answer = answer
        self._model = model
        self.requests: list[LlmRequest[Any]] = []

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return self._model

    async def generate[T: BaseModel](self, request: LlmRequest[T]) -> LlmResponse[T]:
        self.requests.append(request)
        if self._answer is None:
            answer = _empty_answer(request)
        elif callable(self._answer) and not isinstance(self._answer, BaseModel):
            answer = self._answer(request)
        else:
            answer = self._answer
        if isinstance(answer, Exception):
            raise answer
        payload = answer.model_dump(mode="json") if isinstance(answer, BaseModel) else answer
        try:
            output = request.output_type.model_validate(payload)
        except ValidationError as exc:
            msg = f"answer does not match {request.output_type.__name__}"
            raise LlmInvalidOutputError(msg) from exc
        return LlmResponse(output=output, model=self._model, input_tokens=0, output_tokens=0)

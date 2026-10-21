"""The language-model port (D103): one async call, structured output only.

A provider gets a system instruction, a prompt and the Pydantic model the answer must match, and
returns an instance of that model. It never returns free text for the caller to parse. Transport
and provider failures raise `LlmError`; an answer that does not validate raises
`LlmInvalidOutputError`.
"""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


class LlmError(Exception):
    """The provider failed (network, quota, timeout, refusal); the message is safe to log."""


class LlmInvalidOutputError(LlmError):
    """The provider answered, but not with valid output for the requested model."""


@dataclass(frozen=True, slots=True, kw_only=True)
class LlmRequest[T: BaseModel]:
    system: str
    prompt: str
    output_type: type[T]
    temperature: float = 0.2
    max_output_tokens: int = 2048


@dataclass(frozen=True, slots=True, kw_only=True)
class LlmResponse[T: BaseModel]:
    output: T
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LlmProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def generate[T: BaseModel](self, request: LlmRequest[T]) -> LlmResponse[T]: ...

"""The golden-set harness for text AI features (AI-43, modules/ai.md "Evaluation").

A golden case is one feature input with the facts it carries and what a good answer must (and must
not) say. `evaluate` runs every case through `run_feature` with the given runtime — the fake
provider in CI, the real one on demand — and returns one `CaseResult` per case. A case fails on:

1. no valid output (the model failed, answered invalid output, or the guard blocked it);
2. an amount or booking reference that is not in the case's facts (invented data);
3. another customer's reference or personal data (`forbidden` strings);
4. a missing `must_mention` string.

Features add a golden set (a list of `GoldenCase`) when they are built and assert
`all(result.passed for result in await evaluate(...))` in their tests.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel

from app.core.errors import AppError
from app.modules.ai.domain.grounding import GroundingFacts, texts_of, ungrounded
from app.modules.ai.service import AiActor, AiRun, AiRuntime, AiSubject, run_feature
from app.shared.enums import AiFeature


@dataclass(frozen=True)
class GoldenCase:
    name: str
    prompt: str
    facts: GroundingFacts
    must_mention: Sequence[str] = ()
    forbidden: Sequence[str] = ()  # e.g. another customer's reference, name or phone


@dataclass
class CaseResult:
    name: str
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


async def evaluate[T: BaseModel](  # noqa: PLR0913 - one argument per part of a feature run
    runtime: AiRuntime,
    *,
    feature: AiFeature,
    actor: AiActor,
    subject: AiSubject,
    system: str,
    output_type: type[T],
    cases: Sequence[GoldenCase],
) -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in cases:
        result = CaseResult(case.name)
        run = AiRun(
            feature=feature,
            actor=actor,
            subject=subject,
            system=system,
            prompt=case.prompt,
            output_type=output_type,
        )  # no runtime guard here: the harness reports every problem instead of blocking
        try:
            output = (await run_feature(runtime, run)).output.model_dump(mode="json")
        except AppError as exc:
            result.failures.append(f"no valid output ({exc.code.value})")
            results.append(result)
            continue
        result.failures += ungrounded(output, case.facts)
        text = "\n".join(texts_of(output)).lower()
        leaked = [item for item in case.forbidden if item.lower() in text]
        missing = [item for item in case.must_mention if item.lower() not in text]
        result.failures += [f"mentions forbidden {item!r}" for item in leaked]
        result.failures += [f"does not mention {item!r}" for item in missing]
        results.append(result)
    return results

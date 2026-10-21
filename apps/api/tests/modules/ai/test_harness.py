"""The AI-43 harness catches invented data and leaks (modules/ai.md "Evaluation", AI-12)."""

import uuid

from app.core.database import Database
from app.modules.ai.domain.grounding import GroundingFacts
from app.modules.ai.providers.base import LlmRequest
from app.modules.ai.service import AiSubject
from app.shared.enums import AiFeature, AiSubjectType
from tests.modules.ai.harness import GoldenCase, evaluate
from tests.modules.ai.support import Explanation, build_ai_world, runtime

FACTS = GroundingFacts.of(amounts=[16100, 6500, 900, 5200], references=["BF-7K2M9Q"])
CASES = [
    GoldenCase(
        name="honest",
        prompt="honest",
        facts=FACTS,
        must_mention=["16,100"],
        forbidden=["BF-AAAAAA", "Zainab"],
    ),
    GoldenCase(name="invents a total", prompt="invent", facts=FACTS),
    GoldenCase(name="leaks another customer", prompt="leak", facts=FACTS, forbidden=["Zainab"]),
    GoldenCase(name="model fails", prompt="fail", facts=FACTS),
]

ANSWERS = {
    "honest": Explanation(summary="Version 2 totals 16,100 rupees for BF-7K2M9Q.", lines=[]),
    "invent": Explanation(summary="With tax it comes to 18,000 rupees.", lines=[]),
    "leak": Explanation(summary="Zainab's car BF-AAAAAA is also in.", lines=[]),
    "fail": {"summary": None},
}


def scripted(request: LlmRequest[Explanation]) -> object:
    return ANSWERS[request.prompt]


async def test_the_harness_reports_each_kind_of_failure(db: Database) -> None:
    world = await build_ai_world(db)
    results = await evaluate(
        runtime(db, scripted),
        feature=AiFeature.ESTIMATE_CHECKER,
        actor=world.actor(world.advisor),
        subject=AiSubject(AiSubjectType.ESTIMATE, uuid.uuid4()),
        system="Check estimates.",
        output_type=Explanation,
        cases=CASES,
    )
    assert {result.name: result.failures for result in results} == {
        "honest": [],
        "invents a total": ["amount 18,000 is not in the facts"],
        "leaks another customer": [
            "reference BF-AAAAAA is not in the facts",
            "mentions forbidden 'Zainab'",
        ],
        "model fails": ["no valid output (AI_UNAVAILABLE)"],
    }

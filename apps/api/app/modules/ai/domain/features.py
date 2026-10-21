"""The text-AI feature registry (modules/ai.md "Feature registry", D103).

Pure data: who may run each feature, who may decide its output, and the prompt version that audit
rows and evaluations are compared by. Bump `prompt_version` whenever a feature's prompt changes.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from app.shared.enums import ActorRole, AiFeature

_SA_OWNER: Final = frozenset({ActorRole.SERVICE_ADVISOR, ActorRole.OWNER})


@dataclass(frozen=True, slots=True, kw_only=True)
class FeatureSpec:
    """One feature: `approvers` empty = its output is shown as is and needs no decision."""

    feature: AiFeature
    backlog_id: str
    prompt_version: str
    callers: frozenset[ActorRole]
    approvers: frozenset[ActorRole] = frozenset()

    @property
    def needs_decision(self) -> bool:
        return bool(self.approvers)


FEATURES: Final[Mapping[AiFeature, FeatureSpec]] = MappingProxyType(
    {
        spec.feature: spec
        for spec in (
            FeatureSpec(
                feature=AiFeature.ESTIMATE_EXPLAINER,
                backlog_id="AI-05",
                prompt_version="v1",
                callers=_SA_OWNER,
                approvers=_SA_OWNER,  # the text reaches the customer only after an SA accepts it
            ),
            FeatureSpec(
                feature=AiFeature.ESTIMATE_CHECKER,
                backlog_id="AI-14",
                prompt_version="v1",
                callers=_SA_OWNER,
            ),
            FeatureSpec(
                feature=AiFeature.VOICE_TO_ESTIMATE,
                backlog_id="AI-18",
                prompt_version="v1",
                callers=frozenset({ActorRole.TECHNICIAN}),
                approvers=frozenset({ActorRole.TECHNICIAN, *_SA_OWNER}),  # money: AI-42
            ),
            FeatureSpec(
                feature=AiFeature.SYMPTOM_TRIAGE,
                backlog_id="AI-01",
                prompt_version="v1",
                callers=frozenset({ActorRole.CUSTOMER}),
            ),
            FeatureSpec(
                feature=AiFeature.ASK_YOUR_SHOP,
                backlog_id="AI-33",
                prompt_version="v1",
                callers=frozenset({ActorRole.OWNER}),
            ),
        )
    }
)


def is_enabled(feature: AiFeature, enabled_names: frozenset[str]) -> bool:
    """`AI_FEATURES` lists the feature by name, or is `*`."""
    return "*" in enabled_names or feature.value in enabled_names


def enabled_features(enabled_names: frozenset[str]) -> list[AiFeature]:
    return [feature for feature in AiFeature if is_enabled(feature, enabled_names)]


def decidable_by(role: ActorRole) -> frozenset[AiFeature]:
    """The features whose drafts `role` may see and decide."""
    return frozenset(spec.feature for spec in FEATURES.values() if role in spec.approvers)

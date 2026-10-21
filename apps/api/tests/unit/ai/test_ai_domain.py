"""The ai module's pure parts (modules/ai.md): masking, grounding, the registry, caps, settings."""

from datetime import UTC, datetime

import pytest

from app.modules.ai.domain.caps import Usage, cap_reached, day_start, month_start
from app.modules.ai.domain.features import FEATURES, decidable_by, enabled_features, is_enabled
from app.modules.ai.domain.grounding import (
    GroundingFacts,
    amounts_in,
    references_in,
    texts_of,
    ungrounded,
)
from app.modules.ai.domain.masking import mask_pii
from app.shared.enums import ActorRole, AiFeature
from tests.conftest import make_settings

# --- Masking --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Mail ahmed.k+cars@mail.com today", "Mail [email] today"),
        ("Call 0300-1234567 or +92 300 1234567", "Call [phone] or [phone]"),
        ("Number +923000000101 on file", "Number [phone] on file"),
        ("CNIC 35202-1234567-1 checked", "CNIC [cnic] checked"),
        ("Plate LEA-1234 and BKR 482", "Plate [plate] and [plate]"),
    ],
)
def test_personal_data_is_masked(text: str, expected: str) -> None:
    assert mask_pii(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Total 16,100 rupees for BF-7K2M9Q",
        "Rs 900 + Rs 5,200, version 2",
        "Booked 2026-10-16 at 10:00; Corolla 2018, 67,900 km",
        "Parts TIR-185-65-R15, OIL-4L-01, BLB-H4 and PO-SEED01",
        "Labour 1 x 3000",
    ],
)
def test_facts_a_feature_needs_are_kept(text: str) -> None:
    assert mask_pii(text) == text


def test_plates_can_be_kept_when_the_task_needs_them() -> None:
    assert mask_pii("LEA-1234, 0300-1234567", plates=False) == "LEA-1234, [phone]"


# --- Grounding ------------------------------------------------------------------------------------


def test_amounts_are_money_in_context_or_thousands_grouped() -> None:
    text = "Rs 900, PKR 5,200, 16,100 rupees, 12,500.00 total; 2 plugs, year 2018, 67,900 km"
    assert amounts_in(text) == {900, 5200, 16100, 12500}


def test_references_are_normalised() -> None:
    assert references_in("bf-7k2m9q and BF7K2M9R and BF-SEED02") == {
        "BF-7K2M9Q",
        "BF-7K2M9R",
        "BF-SEED02",
    }


def test_grounded_output_passes_and_invented_facts_are_reported() -> None:
    facts = GroundingFacts.of(amounts=[6500, 16100], references=["bf-7k2m9q"])
    good = {"summary": "Version 2 is 16,100 rupees for BF-7K2M9Q", "lines": ["Coil Rs 6,500"]}
    assert ungrounded(good, facts) == []
    bad = {"summary": "Total Rs 17,000 for BF-7K2M9Q", "other": ["See BF-AAAAAA"]}
    assert ungrounded(bad, facts) == [
        "amount 17,000 is not in the facts",
        "reference BF-AAAAAA is not in the facts",
    ]


def test_texts_of_flattens_json() -> None:
    assert texts_of({"a": "x", "b": [1, "y", {"c": "z"}], "d": None}) == ["x", "y", "z"]


# --- Registry, flags, caps, settings --------------------------------------------------------------


def test_every_feature_is_registered_with_callers() -> None:
    assert set(FEATURES) == set(AiFeature)
    assert all(spec.callers and spec.prompt_version for spec in FEATURES.values())


def test_money_and_customer_facing_features_need_a_decision() -> None:
    needs = {feature for feature, spec in FEATURES.items() if spec.needs_decision}
    assert needs == {AiFeature.ESTIMATE_EXPLAINER, AiFeature.VOICE_TO_ESTIMATE}
    assert decidable_by(ActorRole.TECHNICIAN) == {AiFeature.VOICE_TO_ESTIMATE}
    assert decidable_by(ActorRole.PARTS_PERSON) == frozenset()
    assert decidable_by(ActorRole.CUSTOMER) == frozenset()


def test_feature_flags() -> None:
    assert is_enabled(AiFeature.ASK_YOUR_SHOP, frozenset({"*"}))
    assert not is_enabled(AiFeature.ASK_YOUR_SHOP, frozenset({"ESTIMATE_CHECKER"}))
    assert enabled_features(frozenset()) == []


def test_settings_parse_features_and_key_fallback() -> None:
    settings = make_settings(ai_features=" estimate_checker, ASK_YOUR_SHOP ,", llm_api_key="k")
    assert settings.enabled_ai_features == {"ESTIMATE_CHECKER", "ASK_YOUR_SHOP"}
    assert settings.text_ai_configured
    key = settings.text_ai_key()
    assert key is not None
    assert key.get_secret_value() == "k"
    assert not make_settings().text_ai_configured  # no key: AI off
    assert make_settings(ai_text_provider="fake").text_ai_configured


def test_caps_use_utc_day_and_month_windows() -> None:
    now = datetime(2026, 10, 9, 19, 30, tzinfo=UTC)
    assert day_start(now) == datetime(2026, 10, 9, tzinfo=UTC)
    assert month_start(now) == datetime(2026, 10, 1, tzinfo=UTC)
    assert not cap_reached(Usage(today=1, this_month=5), daily_cap=2, monthly_cap=10)
    assert cap_reached(Usage(today=2, this_month=5), daily_cap=2, monthly_cap=10)
    assert cap_reached(Usage(today=0, this_month=10), daily_cap=2, monthly_cap=10)

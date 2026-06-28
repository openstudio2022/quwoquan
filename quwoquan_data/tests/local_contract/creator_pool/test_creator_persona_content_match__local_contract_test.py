"""Persona ↔ content semantic pairing contract.

Covers Phase 1 of the no-breakpoint E2E closure:
  1. preferredBlueprintIds participates in match_creator scoring (soft preference).
  2. creator_assignment_issues blocks vertical/topic/region mismatch before publish.
"""
from __future__ import annotations

from _common.creator_assignment import creator_assignment_from_profile, creator_assignment_issues
from template.creator import _creator_match_score, blueprint_preference_fit, match_creator
from template.registry import TemplateRegistry

PREF_BLUEPRINT = "景区_体验"
REGIONAL_CREATOR = "qwq_creator_travel_casual_tourist_001"


class _FakeRegistry:
    """Minimal registry surface used by match_creator (creators + by-archetype)."""

    def __init__(self, creators: list[dict]) -> None:
        self.creators = {c["creatorProfileId"]: c for c in creators}

    def creators_by_archetype(self, archetype: str) -> list[dict]:
        return [c for c in self.creators.values() if c.get("creatorArchetype") == archetype]


def _creator(profile_id: str, *, prefers: list[str]) -> dict:
    return {
        "creatorProfileId": profile_id,
        "authorId": f"author_{profile_id}",
        "creatorArchetype": "casual_tourist",
        "status": "active",
        "verticalRefs": ["travel"],
        "qualityScore": 0.80,
        "fatigueScore": 0.20,
        "preferredBlueprintIds": prefers,
        "carrierAffinity": {"article": 0.7, "image": 0.2, "video": 0.1},
        "coverageScope": {"kind": "nationwide"},
    }


def test_blueprint_preference_fit_hits_only_preferred() -> None:
    creator = _creator("c_pref", prefers=[PREF_BLUEPRINT])
    assert blueprint_preference_fit(creator, PREF_BLUEPRINT) == 1.0
    assert blueprint_preference_fit(creator, "线路_深度探险") == 0.0
    assert blueprint_preference_fit(creator, None) == 0.0


def test_match_score_rewards_preferred_blueprint() -> None:
    creator = _creator("c_pref", prefers=[PREF_BLUEPRINT])
    base = dict(carrier="article", tag_refs=None, region=None, vertical="travel", seed="s")
    with_pref = _creator_match_score(creator, blueprint_id=PREF_BLUEPRINT, **base)
    without = _creator_match_score(creator, blueprint_id=None, **base)
    assert with_pref > without


def test_match_creator_prefers_blueprint_over_tie() -> None:
    prefers = _creator("c_prefers", prefers=[PREF_BLUEPRINT])
    neutral = _creator("c_neutral", prefers=["线路_深度探险"])
    registry = _FakeRegistry([neutral, prefers])
    blueprint = {"templateId": PREF_BLUEPRINT, "creatorPersona": {"archetype": "casual_tourist"}}
    chosen = match_creator(registry, blueprint, carrier="article", vertical="travel", seed="seed-1")
    assert chosen["creatorProfileId"] == "c_prefers"


def test_real_registry_preferred_blueprint_routes() -> None:
    registry = TemplateRegistry.load()
    blueprint = {"templateId": PREF_BLUEPRINT, "creatorPersona": {"archetype": "casual_tourist"}}
    chosen = match_creator(
        registry, blueprint, carrier="article", region="西南", vertical="travel", seed="real"
    )
    assert chosen.get("creatorArchetype") == "casual_tourist"
    assert str(chosen.get("status")) == "active"


def test_assignment_base_passes_for_registered_creator() -> None:
    registry = TemplateRegistry.load()
    profile = registry.creators[REGIONAL_CREATOR]
    payload = creator_assignment_from_profile(profile)
    assert creator_assignment_issues(payload, carrier="article") == []


def test_assignment_blocks_region_topic_mismatch() -> None:
    registry = TemplateRegistry.load()
    profile = registry.creators[REGIONAL_CREATOR]
    payload = creator_assignment_from_profile(profile)
    issues = creator_assignment_issues(
        payload,
        carrier="article",
        content_region="华东",
        content_tag_refs=["Topic/旅行/华东/沿海"],
    )
    assert any("semanticFit" in i for i in issues), issues
    # Matching region must not raise a semantic-fit issue.
    ok = creator_assignment_issues(payload, carrier="article", content_region="西南")
    assert ok == []


def test_assignment_blocks_vertical_mismatch() -> None:
    registry = TemplateRegistry.load()
    profile = registry.creators[REGIONAL_CREATOR]
    payload = creator_assignment_from_profile(profile)
    issues = creator_assignment_issues(payload, carrier="article", content_vertical="campus")
    assert any("verticalRefs" in i for i in issues), issues
    assert creator_assignment_issues(payload, carrier="article", content_vertical="travel") == []

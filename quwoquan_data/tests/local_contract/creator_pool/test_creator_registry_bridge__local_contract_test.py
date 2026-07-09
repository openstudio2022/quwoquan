from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from _common.creator_pool.registry_bridge import author_pool_profile_from_batch, load_travel_batch_creators
from task.content_supply import _author_profile
from template.registry import TemplateRegistry


def test_travel_batch_registry_loads_1000_creators() -> None:
    creators, _ = load_travel_batch_creators("travel_photo_1k_v1")
    assert len(creators) == 1200


def test_template_registry_includes_travel_batch() -> None:
    registry = TemplateRegistry.load()
    batch_creators, _ = load_travel_batch_creators("travel_photo_1k_v1")
    assert len(batch_creators) == 1200
    sample_id = next(iter(batch_creators))
    assert sample_id in registry.creators


def test_author_pool_sample_20_handles() -> None:
    creators, _ = load_travel_batch_creators("travel_photo_1k_v1")
    ordered = sorted(creators.values(), key=lambda row: str(row.get("creatorProfileId") or ""))
    sample = ordered[:20]
    assert len(sample) == 20
    for profile in sample:
        assert profile.get("displayName")
        assert profile.get("userHandle")
        assert profile.get("bio")


def test_batch_compact_profiles_normalize_to_publishable_creators() -> None:
    creators, _ = load_travel_batch_creators("travel_photo_1k_v1")
    profile = creators["sys_photo_0001"]

    assert profile["authorId"] == profile["subAccountId"]
    assert profile["isSystemBuiltin"] is False
    assert profile["scenarioRefs"] == ["cold_start", "long_tail_fill", "refresh_stale"]
    assert profile["disclosure"]["type"] == "platform_virtual_creator"
    assert profile["disclosure"]["visible"] is True
    assert profile["claimPolicy"]["experienceClaimMode"] == "editorial_synthesis"
    assert profile["claimPolicy"]["mustCiteEvidenceForClaims"] is True
    assert profile["publishCadence"]["maxDailyPosts"] == 1
    assert isinstance(profile["recommendationTagRefs"], list)
    assert profile["voiceStyle"]["narrativePointOfView"] == "资料整理"
    assert profile["profileVersion"] == "1.0.0"


def test_content_supply_author_pool_uses_batch_profile() -> None:
    spec = {
        "supplyTaskId": "travel_supply_smoke",
        "vertical": "travel",
        "authorPool": {"creatorBatchId": "travel_photo_1k_v1", "size": 1000},
        "scenarios": ["cold_start"],
    }
    author = _author_profile(spec, 0)
    batch_author = author_pool_profile_from_batch("travel_photo_1k_v1", 0)
    assert batch_author is not None
    assert author["creatorProfileId"] == batch_author["creatorProfileId"]
    assert author["authorId"] == batch_author["authorId"]

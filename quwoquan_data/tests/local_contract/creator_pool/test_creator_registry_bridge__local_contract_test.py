from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from _common.creator_pool.registry_bridge import author_pool_profile_from_batch, load_travel_batch_creators
from task.content_supply import _author_profile
from template.registry import TemplateRegistry


def test_travel_batch_registry_loads_100_creators() -> None:
    creators, _ = load_travel_batch_creators("travel_batch_100_v1")
    assert len(creators) == 100


def test_template_registry_includes_travel_batch() -> None:
    registry = TemplateRegistry.load()
    batch_creators, _ = load_travel_batch_creators("travel_batch_100_v1")
    assert len(batch_creators) == 100
    sample_id = next(iter(batch_creators))
    assert sample_id in registry.creators


def test_author_pool_sample_20_handles() -> None:
    creators, _ = load_travel_batch_creators("travel_batch_100_v1")
    ordered = sorted(creators.values(), key=lambda row: str(row.get("creatorProfileId") or ""))
    sample = ordered[:20]
    assert len(sample) == 20
    for profile in sample:
        assert profile.get("displayName")
        assert profile.get("userHandle")
        assert profile.get("bio")


def test_content_supply_author_pool_uses_batch_profile() -> None:
    spec = {
        "supplyTaskId": "travel_supply_smoke",
        "vertical": "travel",
        "authorPool": {"creatorBatchId": "travel_batch_100_v1", "size": 100},
        "scenarios": ["cold_start"],
    }
    author = _author_profile(spec, 0)
    batch_author = author_pool_profile_from_batch("travel_batch_100_v1", 0)
    assert batch_author is not None
    assert author["creatorProfileId"] == batch_author["creatorProfileId"]
    assert author["authorId"] == batch_author["authorId"]

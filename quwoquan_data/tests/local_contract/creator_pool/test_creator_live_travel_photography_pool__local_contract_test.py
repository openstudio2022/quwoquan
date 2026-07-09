from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from _common.creator_pool.batch_policy import expected_view_contract, segment_counts

REPO = Path(__file__).resolve().parents[4]
CLI = REPO / "quwoquan_data/scripts/cli.py"
PYTHON = sys.executable
TARGET = 120
SEGMENTS = segment_counts("travel_photo_1k_v1", TARGET)
VIEWS = expected_view_contract("travel_photo_1k_v1", TARGET)


@pytest.fixture()
def isolated_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["QWQ_DATA_ROOT"] = str(tmp_path / "data")
    env["QWQ_RUNTIME_ROOT"] = str(tmp_path / "runtime")
    env["QWQ_PUBLISH_ROOT"] = str(tmp_path / "publish")
    env["QWQ_SERVICE_CONTRACTS_METADATA_ROOT"] = str(tmp_path / "service_contracts")
    return env


def test_live_travel_photography_pool_uses_real_registry_and_cross_contract(isolated_env: dict[str, str]) -> None:
    batch = "travel_photo_1k_v1_shard_01_live"
    cmd = [
        PYTHON,
        str(CLI),
        "governance",
        "creator-pool",
        "workflow",
        "run",
        "--vertical",
        "travel",
        "--batch",
        batch,
        "--target",
        str(TARGET),
        "--through",
        "validate",
        "--dry-run",
    ]
    proc = subprocess.run(cmd, cwd=REPO, env=isolated_env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout

    shared = Path(isolated_env["QWQ_RUNTIME_ROOT"]) / "creator_pools" / "travel" / batch / "_shared"
    plan = json.loads((shared / "creator_pool_plan.json").read_text(encoding="utf-8"))
    candidate_pool = json.loads((shared / "candidate_pool.json").read_text(encoding="utf-8"))
    assert plan["liveMode"] is True
    assert plan["candidatePoolSize"] == 600
    candidates = candidate_pool["candidates"]
    assert len(candidates) >= 420
    assert not any("example." in str(item.get("sourceUrl") or "") for item in candidates)
    assert not any("example." in str(item.get("sourceDomain") or "") for item in candidates)
    assert Counter(item["verticalSegment"] for item in candidates) == {
        "travel_primary": 100,
        "photography_primary": 100,
        "travel_photography_cross": 400,
    }

    index = json.loads((shared / "creator_object_index.json").read_text(encoding="utf-8"))
    objects = index["objects"]
    assert Counter(obj["verticalSegment"] for obj in objects) == SEGMENTS

    creators_root = Path(isolated_env["QWQ_RUNTIME_ROOT"]) / "creator_pools" / "travel" / batch / "creators"
    cross_bundles = []
    for obj in objects:
        bundle_path = creators_root / obj["creatorRef"] / "4.materialize" / "creator_bundle.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        source_url = str((bundle.get("provenance") or {}).get("sourceUrl") or "")
        assert "example." not in source_url
        identity = bundle.get("identity") or {}
        profile = bundle.get("profile") or {}
        operations = bundle.get("operations") or {}
        relations = bundle.get("relations") or {}
        assert identity.get("personaVersion") == "derivative_persona_v1"
        assert identity.get("sourceClonePolicy") == "no_real_name_no_avatar_no_bio_copy"
        assert profile.get("slogan")
        assert profile.get("avatarObjectKey")
        assert profile.get("backgroundObjectKey")
        assert (profile.get("ipLocation") or {}).get("source") == "derived_from_region_bucket"
        assert operations.get("envEligibility") == ["alpha", "beta", "gamma", "prod"]
        assert operations.get("importVersion") == "creator_pool_profile_import/1"
        assert relations.get("relationSeedPolicy") == "deterministic_v1"
        assert relations.get("entityAffinityRefs")
        assert relations.get("circleAffinityRefs")
        extracted = (bundle.get("provenance") or {}).get("extractedSignals") or {}
        assert extracted.get("sourceProfileKey")
        if obj["verticalSegment"] == "travel_photography_cross":
            cross_bundles.append(bundle)
            vertical_refs = set((bundle.get("content") or {}).get("verticalRefs") or [])
            interest_refs = [str(ref) for ref in (bundle.get("tags") or {}).get("interestTagRefs") or []]
            assert {"travel", "photography"}.issubset(vertical_refs)
            assert any(ref.startswith("Topic/旅行/") for ref in interest_refs)
            assert any(ref.startswith("Topic/摄影/") for ref in interest_refs)
    assert len(cross_bundles) == SEGMENTS["travel_photography_cross"]

    gate = json.loads((shared / "gate_report.json").read_text(encoding="utf-8"))
    diversity = json.loads((shared / "diversity_report.json").read_text(encoding="utf-8"))
    assert gate["decision"] == "passed", gate.get("issues")
    assert diversity["quotaFillRate"] == 1.0
    assert diversity["crossSegmentRatio"] == VIEWS["crossSegmentRatio"]
    assert diversity["crossDualTagCoverageRate"] == 1.0
    assert diversity["travelViewCount"] == VIEWS["travelViewCount"]
    assert diversity["photographyViewCount"] == VIEWS["photographyViewCount"]
    assert diversity["viewOverlapCount"] == VIEWS["viewOverlapCount"]
    assert diversity["viewOverlapRate"] == VIEWS["viewOverlapRate"]
    assert diversity["platformMaxShare"] <= 0.15
    assert diversity["sourceProfileMaxCount"] <= 3
    assert diversity["nonChinaSourceRatio"] >= 0.45
    assert diversity["chinaSourceRatio"] >= 0.35

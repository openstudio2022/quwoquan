"""Commercial readiness and diversity quota tests for creator pool (travel_photo_1k_v1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.creator_pool.readiness import build_creator_readiness_report
from governance.creator_pool.workflow import run_workflow
from governance.creator_pool.merge_user_fixtures import run_merge_user_fixtures
from governance.creator_pool.seed import run_seed
from _common.creator_pool.batch_policy import expected_view_contract, segment_counts
from _common.creator_pool.io import artifacts_readiness_path
from _common.paths import creator_pool_shared_dir

BATCH = "travel_photo_1k_v1_shard_01_live"
VERTICAL = "travel"
TARGET = 120
SEGMENTS = segment_counts(BATCH, TARGET)
VIEWS = expected_view_contract(BATCH, TARGET)


@pytest.fixture(scope="module")
def batch_ready() -> dict:
    run_workflow(vertical=VERTICAL, batch_id=BATCH, target=TARGET, through="validate", dry_run=True)
    return {"batchId": BATCH}


def test_workflow_validates_100(batch_ready: dict) -> None:
    shared = creator_pool_shared_dir(VERTICAL, BATCH)
    rollup = json.loads((shared / "creator_rollup_report.json").read_text(encoding="utf-8"))
    assert rollup["counts"]["validated"] == TARGET


def test_diversity_quotas(batch_ready: dict) -> None:
    shared = creator_pool_shared_dir(VERTICAL, BATCH)
    div = json.loads((shared / "diversity_report.json").read_text(encoding="utf-8"))
    assert div["quotaFillRate"] >= 1.0
    assert div["entropy"] >= 0.85
    assert div["topicCoverageCount"] >= 12
    assert div["travelViewCount"] == VIEWS["travelViewCount"]
    assert div["photographyViewCount"] == VIEWS["photographyViewCount"]
    assert div["viewOverlapCount"] == VIEWS["viewOverlapCount"]


def test_commercial_readiness_go(batch_ready: dict) -> None:
    run_seed(vertical=VERTICAL, batch_id=BATCH, env="beta", dry_run=True)
    run_merge_user_fixtures(vertical=VERTICAL, batch_id=BATCH, dry_run=True)
    scale10 = artifacts_readiness_path("creator_scale10_readiness.json")
    scale10.parent.mkdir(parents=True, exist_ok=True)
    scale10.write_text(
        json.dumps({"schemaVersion": "test", "decision": "go"}, ensure_ascii=False),
        encoding="utf-8",
    )
    report = build_creator_readiness_report(
        vertical=VERTICAL,
        batch_id=BATCH,
        target=TARGET,
        mode="commercial",
    )
    out = artifacts_readiness_path("creator_travel_photo_1k_v1_shard_01_live_readiness.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    assert report["decision"] == "go", report.get("issues")
    assert report["checks"]["crossSegmentRatio"] == VIEWS["crossSegmentRatio"]

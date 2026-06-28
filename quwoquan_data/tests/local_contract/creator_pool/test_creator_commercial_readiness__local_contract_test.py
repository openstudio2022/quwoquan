"""Commercial readiness and diversity quota tests for creator pool (travel_batch_100_v1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.creator_pool.readiness import build_creator_readiness_report
from governance.creator_pool.workflow import run_workflow
from governance.creator_pool.merge_user_fixtures import run_merge_user_fixtures
from governance.creator_pool.seed import run_seed
from _common.paths import REPO_ROOT, creator_pool_shared_dir

BATCH = "travel_batch_100_v1"
VERTICAL = "travel"


@pytest.fixture(scope="module")
def batch_ready() -> dict:
    run_workflow(vertical=VERTICAL, batch_id=BATCH, target=100, through="validate")
    return {"batchId": BATCH}


def test_workflow_validates_100(batch_ready: dict) -> None:
    shared = creator_pool_shared_dir(VERTICAL, BATCH)
    rollup = json.loads((shared / "creator_rollup_report.json").read_text(encoding="utf-8"))
    assert rollup["counts"]["validated"] == 100


def test_diversity_quotas(batch_ready: dict) -> None:
    shared = creator_pool_shared_dir(VERTICAL, BATCH)
    div = json.loads((shared / "diversity_report.json").read_text(encoding="utf-8"))
    assert div["quotaFillRate"] >= 1.0
    assert div["entropy"] >= 0.85
    assert div["topicCoverageCount"] >= 12


def test_commercial_readiness_go(batch_ready: dict) -> None:
    run_seed(vertical=VERTICAL, batch_id=BATCH, env="beta", dry_run=False)
    run_merge_user_fixtures(vertical=VERTICAL, batch_id=BATCH, dry_run=False)
    report = build_creator_readiness_report(
        vertical=VERTICAL,
        batch_id=BATCH,
        target=100,
        mode="commercial",
    )
    out = REPO_ROOT / "artifacts/creator_batch100_commercial_readiness.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    assert report["decision"] == "go", report.get("issues")

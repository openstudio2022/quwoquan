from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
CLI = REPO / "quwoquan_data/scripts/cli.py"
GOLDEN = REPO / "quwoquan_data/tests/fixtures/creator_pool/travel_scale10_verify/golden_creator_bundle.json"
PYTHON = sys.executable


@pytest.fixture()
def isolated_roots(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QWQ_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("QWQ_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("QWQ_PUBLISH_ROOT", str(tmp_path / "publish"))
    return tmp_path


def test_golden_fixture_derivation_policy() -> None:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert data["provenance"]["derivationPolicy"] == "derivative_persona_v1"


def test_scale10_workflow_produces_ten_objects(isolated_roots: Path) -> None:
    batch = "travel_scale10_verify_fixtures"
    fixture = REPO / "quwoquan_data/tests/fixtures/creator_pool/travel_scale10_verify"
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
        "10",
        "--through",
        "validate",
        "--dry-run",
        "--fixture",
        str(fixture),
    ]
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    plan = json.loads((isolated_roots / "runtime/creator_pools/travel" / batch / "_shared/creator_pool_plan.json").read_text())
    assert plan["targetCount"] == 10
    assert len(plan["creatorRefs"]) == 10

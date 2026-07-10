from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
CLI = REPO / "quwoquan_data/scripts/cli.py"
PYTHON = sys.executable


@pytest.fixture()
def isolated_roots(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("QWQ_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("QWQ_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("QWQ_PUBLISH_ROOT", str(tmp_path / "publish"))
    monkeypatch.setenv("QWQ_SERVICE_CONTRACTS_METADATA_ROOT", str(tmp_path / "service_contracts"))
    return tmp_path


def test_creator_pool_workflow_dry_run(isolated_roots: Path) -> None:
    batch = "travel_scale10_verify_fixtures"
    fixture = REPO / "quwoquan_data/tests/support/fixtures/creator_pool/travel_scale10_verify"
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
    runtime = isolated_roots / "runtime/creator_pools/travel" / batch
    assert (runtime / "_shared/creator_pool_plan.json").is_file()
    plan = json.loads((runtime / "_shared/creator_pool_plan.json").read_text(encoding="utf-8"))
    assert len(plan["creatorRefs"]) == 10
    gates = list((runtime / "creators").rglob("review_gate.json"))
    assert len(gates) == 10

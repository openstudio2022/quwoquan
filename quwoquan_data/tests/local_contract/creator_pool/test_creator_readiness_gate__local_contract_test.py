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


def _run_scale10(isolated_roots: Path) -> str:
    batch = "travel_scale10_readiness_test"
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
        "--fixture",
        str(fixture),
        "--dry-run",
    ]
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return batch


def test_creator_readiness_gate_scale10_go(isolated_roots: Path, tmp_path: Path) -> None:
    batch = _run_scale10(isolated_roots)
    report_out = tmp_path / "creator_scale10_readiness.json"
    cmd = [
        PYTHON,
        str(CLI),
        "verify",
        "creator-scale-readiness",
        "--vertical",
        "travel",
        "--batch",
        batch,
        "--target",
        "10",
        "--mode",
        "trial",
        "--min-pass-rate",
        "1.0",
        "--report-out",
        str(report_out),
    ]
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    report = json.loads(report_out.read_text(encoding="utf-8"))
    assert report["decision"] == "go"
    assert report["checks"]["reviewGatePassRate"] >= 1.0

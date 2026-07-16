from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _run_gate(relative_path: str) -> None:
    result = subprocess.run(
        ["bash", relative_path],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_app_cloud_story_traceability_contract() -> None:
    _run_gate("quwoquan_ops/gate/scaffold/verify_feature_tree_refactor.sh")
    _run_gate("quwoquan_ops/gate/scaffold/verify_acceptance_standard.sh")

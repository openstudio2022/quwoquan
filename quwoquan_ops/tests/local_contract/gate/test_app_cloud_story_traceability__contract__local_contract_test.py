from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


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
    result = subprocess.run(
        [sys.executable, "quwoquan_ops/cli/feature_tree.py", "verify"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

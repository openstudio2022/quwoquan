"""Operator journey for one readable, resumable content execution work package."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "quwoquan_data").is_dir())
CLI = REPO_ROOT / "quwoquan_data/scripts/cli.py"
EXECUTION_ID = "20260711--travel-homepage-coverage--cn-zhejiang--canary-981"
RETRY_ID = "20260711--travel-homepage-coverage--cn-zhejiang--canary-982"


def _run(
    output_root: Path,
    execution_id: str,
    *,
    forbidden_limit_override: int | None = None,
    retry_of: str = "",
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(CLI),
        "task",
        "geo-homepages",
        "--execution-id",
        execution_id,
        "--rollout",
        "travel-homepage-coverage",
        "--stage",
        "plan-only",
    ]
    if forbidden_limit_override is not None:
        command.extend(["--limit", str(forbidden_limit_override)])
    if retry_of:
        command.extend(["--retry-of", retry_of])
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env={**os.environ, "QWQ_OUTPUT_ROOT": str(output_root)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_operator_creates_resumes_and_retries_one_work_package(tmp_path: Path):
    first = _run(tmp_path, EXECUTION_ID)
    assert first.returncode == 0, first.stdout + first.stderr

    root = tmp_path / "data/tasks" / EXECUTION_ID
    assert {path.name for path in root.iterdir()} == {
        "0.plan",
        "sources",
        "entities",
        "posts",
        "_shared",
        "evidence",
        "execution_manifest.json",
    }
    manifest = json.loads((root / "execution_manifest.json").read_text(encoding="utf-8"))
    assert manifest["executionId"] == EXECUTION_ID
    assert manifest["scope"] == "cn-zhejiang"
    assert manifest["retryOf"] is None
    assert (root / "0.plan/execution_spec.yaml").is_file()
    assert (root / "_shared/target_selection.json").is_file()
    assert not list(root.rglob("*.recipe.yaml"))
    assert not list(root.rglob("*.schema.json"))
    assert not (tmp_path / "data/runs").exists()

    resumed = _run(tmp_path, EXECUTION_ID)
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    assert json.loads((root / "execution_manifest.json").read_text(encoding="utf-8")) == manifest

    drifted = _run(tmp_path, EXECUTION_ID, forbidden_limit_override=1)
    assert drifted.returncode != 0
    assert "governed rollout rejects selection overrides: limit" in drifted.stderr + drifted.stdout

    retried = _run(tmp_path, RETRY_ID, retry_of=EXECUTION_ID)
    assert retried.returncode == 0, retried.stdout + retried.stderr
    retry_manifest = json.loads(
        (tmp_path / "data/tasks" / RETRY_ID / "execution_manifest.json").read_text(encoding="utf-8")
    )
    assert retry_manifest["retryOf"] == EXECUTION_ID

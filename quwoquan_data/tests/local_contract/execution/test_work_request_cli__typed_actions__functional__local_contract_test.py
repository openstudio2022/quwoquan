# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-001.t2
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from core.io import write_json


def _run(repo: Path, output_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["QWQ_OUTPUT_ROOT"] = str(output_root)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPYCACHEPREFIX"] = str(
        output_root / "env/repo/local/test-runtime/cache/bytecode/work-request-cli"
    )
    return subprocess.run(
        [sys.executable, "quwoquan_data/scripts/cli.py", *args],
        cwd=repo,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_real_cli_returns_typed_needs_input_without_artifacts(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[4]
    intent_path = tmp_path / "intent.json"
    output_root = tmp_path / "output"
    write_json(intent_path, {"regionRef": "china", "workloads": {"homepage": 1}})

    result = _run(
        repo,
        output_root,
        "task",
        "compile-intent",
        "preview",
        "--intent-file",
        str(intent_path),
    )

    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["outcome"] == "needs_input"
    # demand facts 归 confirmed handoff 所有：调用方独立提供即 unknown 输入。
    assert "unknown:regionRef" in document["missingFields"]
    assert "unknown:workloads" in document["missingFields"]
    assert "preAcquisitionHandoffRef" in document["missingFields"]
    assert "mode" in document["missingFields"]
    assert not (output_root / "data/local/workspace/content-campaign-envelopes").exists()


def test_real_cli_show_returns_typed_not_found(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[4]
    digest = "sha256:" + "a" * 64

    result = _run(
        repo,
        tmp_path / "output",
        "task",
        "compile-intent",
        "show",
        "--work-request-digest",
        digest,
    )

    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["outcome"] == "blocked"
    assert document["error"]["code"] == "DATA.WORK_REQUEST.NOT_FOUND"

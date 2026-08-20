# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-019
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
CLI = DATA_ROOT / "scripts/cli.py"
DIGEST = "sha256:" + "b" * 64


def _invoke(
    output_root: Path, publish_root: Path, *args: str
) -> dict[str, object]:
    env = dict(os.environ)
    env["QWQ_OUTPUT_ROOT"] = str(output_root)
    env["QWQ_PUBLISH_ROOT"] = str(publish_root)
    result = subprocess.run(
        [sys.executable, "-B", str(CLI), "task", "capacity-bootstrap", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_real_cli_process_only_advances_bootstrap_state_and_never_writes_success_planes(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    publish_root = tmp_path / "publish"

    prepared = _invoke(
        output_root,
        publish_root,
        "prepare",
        "--bootstrap-run-id", "bootstrap-api-001",
        "--host-class", "local-apple-silicon",
        "--provider-tier", "cursor_grok",
        "--semantic-selection-id", "cursor_grok",
        "--workload-digest", DIGEST,
    )
    assert prepared["status"] == "prepared"
    assert _invoke(
        output_root, publish_root, "run", "--bootstrap-run-id", "bootstrap-api-001"
    )["status"] == "running"
    assert _invoke(
        output_root, publish_root, "status", "--bootstrap-run-id", "bootstrap-api-001"
    )["status"] == "running"
    assert _invoke(
        output_root,
        publish_root,
        "cancel",
        "--bootstrap-run-id", "bootstrap-api-001",
        "--reason", "controlled_provider_unavailable",
    )["status"] == "canceled"

    assert not publish_root.exists()
    assert not (output_root / "data/releases").exists()
    assert not (output_root / "env").exists()
    assert not tuple((output_root / "data").rglob("governed_capacity_calibration_receipt.json"))

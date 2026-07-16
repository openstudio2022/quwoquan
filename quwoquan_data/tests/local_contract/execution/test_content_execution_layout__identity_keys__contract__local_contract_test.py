"""Execution layout rejects retired identities without rejecting executionId."""
from __future__ import annotations

import json
import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from verify import verify_content_execution_layout as layout  # noqa: E402


def test_execution_id_is_the_allowed_runtime_identity(monkeypatch, tmp_path):
    root = tmp_path / "tasks" / "20260715--travel-homepage-coverage--cn-zhejiang--canary-001"
    root.mkdir(parents=True)
    source = root / "execution_manifest.json"
    source.write_text(json.dumps({"executionId": root.name}), encoding="utf-8")
    monkeypatch.setattr(layout, "REPO_ROOT", tmp_path)

    assert layout._identity_issues(root) == []


def test_retired_task_and_batch_identities_fail_layout(monkeypatch, tmp_path):
    root = tmp_path / "tasks" / "20260715--travel-homepage-coverage--cn-zhejiang--canary-001"
    root.mkdir(parents=True)
    source = root / "execution_manifest.json"
    source.write_text(json.dumps({"taskId": "old", "batchId": "old"}), encoding="utf-8")
    monkeypatch.setattr(layout, "REPO_ROOT", tmp_path)

    issues = layout._identity_issues(root)

    assert len(issues) == 2
    assert all("retired identity; use executionId" in issue for issue in issues)

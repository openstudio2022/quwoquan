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
    root = tmp_path / "tasks" / "20260715--travel-homepage-coverage--test-region-a--pilot-001"
    root.mkdir(parents=True)
    source = root / "execution_manifest.json"
    source.write_text(json.dumps({"executionId": root.name}), encoding="utf-8")
    monkeypatch.setattr(layout, "REPO_ROOT", tmp_path)

    assert layout._identity_issues(root) == []


def test_retired_task_and_batch_identities_fail_layout(monkeypatch, tmp_path):
    root = tmp_path / "tasks" / "20260715--travel-homepage-coverage--test-region-a--pilot-001"
    root.mkdir(parents=True)
    source = root / "execution_manifest.json"
    source.write_text(json.dumps({"taskId": "old", "batchId": "old"}), encoding="utf-8")
    monkeypatch.setattr(layout, "REPO_ROOT", tmp_path)

    issues = layout._identity_issues(root)

    assert len(issues) == 2
    assert all("retired identity; use executionId" in issue for issue in issues)


def test_named_execution_layout_ignores_other_disposable_work_packages(monkeypatch, tmp_path):
    execution_id = "20260715--travel-homepage-coverage--test-region-a--pilot-001"
    tasks_root = tmp_path / "tasks"
    current = tasks_root / execution_id
    current.mkdir(parents=True)
    (current / "execution_manifest.json").write_text(
        json.dumps({"executionId": execution_id}), encoding="utf-8"
    )
    (tasks_root / "20260715--travel-homepage-coverage--test-region-b--pilot-002").mkdir()
    monkeypatch.setattr(layout, "DATA_EXECUTIONS_ROOT", tasks_root)
    monkeypatch.setattr(layout, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        layout,
        "load_execution_manifest",
        lambda value: {
            "executionId": value,
            "requestRef": "0.plan/request.json",
            "targetSetRef": "0.plan/target_set.json",
        },
    )
    monkeypatch.setattr(
        layout,
        "load_frozen_target_set",
        lambda _value: {"selectionPolicy": "frozen", "targets": []},
    )

    assert layout.content_execution_layout_issues(execution_id=execution_id) == []
    assert any("execution_manifest.json missing" in issue for issue in layout.content_execution_layout_issues())

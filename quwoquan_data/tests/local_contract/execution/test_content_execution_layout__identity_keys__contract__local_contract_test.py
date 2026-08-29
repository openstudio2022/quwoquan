# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""Execution layout rejects retired identities without rejecting executionId."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution.execution_terminal import (  # noqa: E402
    TerminalExecutionEvidence,
)
from core.control_types import ContentType  # noqa: E402
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
    monkeypatch.setattr(layout, "load_spec", lambda _value: {})
    monkeypatch.setattr(
        layout,
        "ExecutionSpec",
        SimpleNamespace(
            from_mapping=lambda _value: SimpleNamespace(
                scope=SimpleNamespace(coverage_targets=()),
                content=SimpleNamespace(carriers=(ContentType.HOMEPAGE,)),
            )
        ),
    )

    assert layout.content_execution_layout_issues(execution_id=execution_id) == []
    assert any("execution_manifest.json missing" in issue for issue in layout.content_execution_layout_issues())


@pytest.mark.parametrize("decision", ["succeeded", "interrupted", "superseded"])
def test_capsule_external_terminal_execution_keeps_protection_issue(
    monkeypatch,
    tmp_path,
    decision,
):
    execution_id = "20260715--travel-article-capsule--test-region-a--pilot-003"
    capsule_root = tmp_path / "capsule"
    execution_root = tmp_path / "runtime-output" / "data" / "tasks" / execution_id
    capsule_root.mkdir()
    execution_root.mkdir(parents=True)
    monkeypatch.setattr(layout, "REPO_ROOT", capsule_root)
    monkeypatch.setattr(layout, "DATA_EXECUTIONS_ROOT", execution_root.parent)
    monkeypatch.setattr(
        layout,
        "load_terminal_execution_evidence",
        lambda root: TerminalExecutionEvidence(
            decision=decision,
            receipt={"decision": decision},
            path=root / "_shared" / "execution_state.json",
        ),
    )

    issues = layout.content_execution_layout_issues(execution_id=execution_id)

    assert issues == [
        f"{execution_root}: execution is protected and non-resumable; create retryOf"
    ]


def test_readiness_opt_in_validates_succeeded_terminal_layout(
    monkeypatch,
    tmp_path,
):
    execution_id = "20260715--travel-article-capsule--test-region-a--pilot-004"
    execution_root = tmp_path / "tasks" / execution_id
    execution_root.mkdir(parents=True)
    monkeypatch.setattr(layout, "DATA_EXECUTIONS_ROOT", execution_root.parent)
    monkeypatch.setattr(
        layout,
        "load_terminal_execution_evidence",
        lambda root: TerminalExecutionEvidence(
            decision="succeeded",
            receipt={"status": "succeeded"},
            path=root / "_shared" / "execution_state.json",
        ),
    )
    observed = []

    def validate(entry):
        observed.append(entry)
        return ["layout-sentinel"]

    monkeypatch.setattr(layout, "_execution_work_package_issues", validate)

    issues = layout.content_execution_layout_issues(
        execution_id=execution_id,
        allow_succeeded_terminal=True,
    )

    assert issues == ["layout-sentinel"]
    assert observed == [execution_root]


@pytest.mark.parametrize("decision", ["interrupted", "superseded"])
def test_readiness_opt_in_never_reopens_failed_terminal_execution(
    monkeypatch,
    tmp_path,
    decision,
):
    execution_id = "20260715--travel-article-capsule--test-region-a--pilot-005"
    execution_root = tmp_path / "tasks" / execution_id
    execution_root.mkdir(parents=True)
    monkeypatch.setattr(layout, "DATA_EXECUTIONS_ROOT", execution_root.parent)
    monkeypatch.setattr(
        layout,
        "load_terminal_execution_evidence",
        lambda root: TerminalExecutionEvidence(
            decision=decision,
            receipt={"decision": decision},
            path=root / "_shared" / "execution_state.json",
        ),
    )
    monkeypatch.setattr(
        layout,
        "_execution_work_package_issues",
        lambda _entry: (_ for _ in ()).throw(
            AssertionError("failed terminal execution must remain protected")
        ),
    )

    issues = layout.content_execution_layout_issues(
        execution_id=execution_id,
        allow_succeeded_terminal=True,
    )

    assert len(issues) == 1
    assert "protected and non-resumable" in issues[0]


def test_readiness_opt_in_preserves_invalid_terminal_evidence_issue(
    monkeypatch,
    tmp_path,
):
    execution_id = "20260715--travel-article-capsule--test-region-a--pilot-006"
    execution_root = tmp_path / "tasks" / execution_id
    execution_root.mkdir(parents=True)
    monkeypatch.setattr(layout, "DATA_EXECUTIONS_ROOT", execution_root.parent)
    monkeypatch.setattr(
        layout,
        "load_terminal_execution_evidence",
        lambda _root: (_ for _ in ()).throw(ValueError("terminal digest drift")),
    )
    monkeypatch.setattr(layout, "_execution_work_package_issues", lambda _entry: [])

    issues = layout.content_execution_layout_issues(
        execution_id=execution_id,
        allow_succeeded_terminal=True,
    )

    assert len(issues) == 1
    assert "invalid terminal execution evidence: terminal digest drift" in issues[0]

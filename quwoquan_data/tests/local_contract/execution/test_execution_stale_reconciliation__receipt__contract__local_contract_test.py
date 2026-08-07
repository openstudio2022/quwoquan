from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from content.execution import context, execution_supersession, execution_terminal
from content.execution.controller.execute import reconcile
from content.execution.execution_terminal import load_terminal_execution_evidence
from core.control_types import ExecutionStateStatus
from core.io import read_json, write_json
from core.source_digest import SourceDigest, current_source_digest
from verify import (
    verify_content_execution_layout,
    verify_runtime_input_ownership,
    verify_source_digest,
)

EXECUTION_ID = "20260805--travel-article-reconcile--china--pilot-001"


def _old_time() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()


def _fixture(tmp_path: Path, monkeypatch, *, pid: int = 999_999) -> Path:
    root = tmp_path / EXECUTION_ID
    state_path = root / "_shared" / "execution_state.json"
    monkeypatch.setattr(reconcile, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(context, "_state_path", lambda _execution_id: state_path)
    state = context.load_execution_state(EXECUTION_ID)
    state.status = ExecutionStateStatus.RUNNING
    state.heartbeat_at = _old_time()
    state.controller = {"pid": pid, "controllerRunId": "old-run"}
    context.save_execution_state(state)
    write_json(
        root / "_shared" / "controller_lease.json",
        {
            "schema": "quwoquan_data.controller_lease",
            "status": "active",
            "executionId": EXECUTION_ID,
            "hostname": socket.gethostname(),
            "pid": pid,
            "pgid": 999_998,
            "heartbeatAt": _old_time(),
            "expiresAfterSeconds": 900,
        },
    )
    return root


def _drift_manifest(root: Path) -> None:
    source = current_source_digest().to_document()
    source["digest"] = "sha256:" + "f" * 64
    write_json(
        root / "execution_manifest.json",
        {
            "schema": "historical-fixture",
            "executionId": root.name,
            "sourceDigest": source,
        },
    )


def _assert_global_gates_accept_only_as_historical(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executions_root = root.parent
    repo_root = executions_root.parent
    assert (
        verify_source_digest.source_digest_issues(
            executions_root=executions_root,
            release_root=repo_root / "releases",
        )
        == []
    )
    monkeypatch.setattr(
        verify_content_execution_layout,
        "DATA_EXECUTIONS_ROOT",
        executions_root,
    )
    monkeypatch.setattr(verify_content_execution_layout, "REPO_ROOT", repo_root)
    assert verify_content_execution_layout.content_execution_layout_issues() == []
    explicit = verify_content_execution_layout.content_execution_layout_issues(
        execution_id=root.name
    )
    assert any("protected and non-resumable" in issue for issue in explicit)
    monkeypatch.setattr(
        verify_runtime_input_ownership,
        "DATA_EXECUTIONS_ROOT",
        executions_root,
    )
    monkeypatch.setattr(verify_runtime_input_ownership, "REPO_ROOT", repo_root)
    monkeypatch.setattr(
        verify_runtime_input_ownership,
        "orphaned_transaction_workspaces",
        list,
    )
    assert verify_runtime_input_ownership.runtime_input_ownership_issues() == []


def test_stale_execution_writes_create_once_receipt_and_terminal_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _fixture(tmp_path, monkeypatch)

    receipt, receipt_path = reconcile.reconcile_stale_execution(EXECUTION_ID)

    assert receipt["decision"] == "interrupted"
    assert receipt["previousState"]["status"] == "running"
    assert receipt["processEvidence"]["pidAlive"] is False
    assert receipt_path.is_file()
    terminal = read_json(root / "_shared" / "execution_state.json")
    assert terminal["status"] == "interrupted"
    assert terminal["interruptReason"]["receiptRef"].startswith(
        "_shared/reconciliation/stale-"
    )

    repeated, repeated_path = reconcile.reconcile_stale_execution(EXECUTION_ID)
    assert repeated == receipt
    assert repeated_path == receipt_path


def test_stale_receipt_closes_global_historical_gates_but_not_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _fixture(tmp_path, monkeypatch)
    _drift_manifest(root)
    reconcile.reconcile_stale_execution(EXECUTION_ID)

    terminal = load_terminal_execution_evidence(root)
    assert terminal is not None
    assert terminal.decision == "interrupted"
    _assert_global_gates_accept_only_as_historical(root, monkeypatch)


def test_terminal_receipt_uses_byte_integrity_not_current_runtime_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _fixture(tmp_path, monkeypatch)
    reconcile.reconcile_stale_execution(EXECUTION_ID)

    def _current_schema_must_not_run(_state_path: Path) -> None:
        raise AssertionError(
            "historical terminal state was reinterpreted as live runtime"
        )

    monkeypatch.setattr(
        execution_terminal,
        "verify_execution_state_journal",
        _current_schema_must_not_run,
    )

    terminal = execution_terminal.load_terminal_execution_evidence(root)
    assert terminal is not None
    assert terminal.decision == "interrupted"


def test_stale_terminal_snapshot_tamper_is_not_hidden_by_valid_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _fixture(tmp_path, monkeypatch)
    reconcile.reconcile_stale_execution(EXECUTION_ID)
    state_path = root / "_shared" / "execution_state.json"
    state = read_json(state_path)
    state["owner"] = "tampered-owner"
    write_json(state_path, state)

    with pytest.raises(ValueError, match="protected field drift"):
        load_terminal_execution_evidence(root)


def test_source_drift_supersession_is_create_once_and_anchor_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tasks" / EXECUTION_ID
    root.mkdir(parents=True)
    _drift_manifest(root)
    frozen_source = SourceDigest.from_document(current_source_digest().to_document())
    monkeypatch.setattr(
        execution_supersession,
        "current_source_digest",
        lambda **_kwargs: frozen_source,
    )

    receipt, path = execution_supersession.supersede_execution(
        EXECUTION_ID,
        reason="source_drift",
        executions_root=root.parent,
    )
    repeated, repeated_path = execution_supersession.supersede_execution(
        EXECUTION_ID,
        reason="source_drift",
        executions_root=root.parent,
    )

    assert repeated == receipt
    assert repeated_path == path
    assert receipt["decision"] == "superseded"
    assert receipt["evidenceDisposition"] == "protected_read_only"
    before_files = {item.relative_to(root) for item in root.rglob("*")}
    terminal = load_terminal_execution_evidence(root)
    assert terminal is not None
    assert terminal.decision == "superseded"
    assert {item.relative_to(root) for item in root.rglob("*")} == before_files
    _assert_global_gates_accept_only_as_historical(root, monkeypatch)

    manifest = read_json(root / "execution_manifest.json")
    manifest["executionId"] = "tampered"
    write_json(root / "execution_manifest.json", manifest)
    with pytest.raises(ValueError, match="anchor drift"):
        load_terminal_execution_evidence(root)


def test_stale_reconciliation_refuses_live_controller(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _fixture(tmp_path, monkeypatch, pid=os.getpid())

    with pytest.raises(ValueError, match="still alive"):
        reconcile.reconcile_stale_execution(EXECUTION_ID)


def test_stale_reconciliation_refuses_fresh_heartbeat(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    state = context.load_execution_state(EXECUTION_ID)
    state.heartbeat_at = datetime.now(timezone.utc).isoformat()
    context.save_execution_state(state)

    with pytest.raises(ValueError, match="heartbeat is not stale"):
        reconcile.reconcile_stale_execution(EXECUTION_ID)

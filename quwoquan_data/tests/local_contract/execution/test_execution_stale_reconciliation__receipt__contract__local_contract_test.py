from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from content.execution import context, execution_supersession, execution_terminal
from content.execution.controller.execute import reconcile
from content.execution.execution_terminal import load_terminal_execution_evidence
from content.execution import workspace
from core.control_types import ExecutionStateStatus
from core.io import read_json, write_json
from core.source_digest import (
    SourceDefinitionSnapshot,
    SourceDigest,
    current_source_definition_snapshot,
    current_source_digest,
)
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


def _pre_controller_fixture(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _drift_manifest(root)
    documents = {
        "0.plan/request.json": {"topic": "travel"},
        "0.plan/target_set.json": {
            "executionId": root.name,
            "targetCount": 1,
        },
        "0.plan/queue_backend_envelope.json": {
            "executionId": root.name,
            "queueBackend": "reliabletask",
        },
        "_shared/execution_progress.json": {
            "executionId": root.name,
            "lastRunId": None,
            "counts": {"entities": 0, "posts": 0},
        },
        "_shared/target_selection.json": {"executionId": root.name},
        "evidence/model_readiness.json": {"executionId": root.name},
        "evidence/runtime_preflight.json": {"ready": True},
        "sources/qualification/request.json": {"executionId": root.name},
    }
    for relative, document in documents.items():
        write_json(root / relative, document)
    specification = root / "0.plan/execution_spec.yaml"
    specification.parent.mkdir(parents=True, exist_ok=True)
    specification.write_text("status: active\n", encoding="utf-8")
    catalog = root / "_shared/catalog.ndjson"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text('{"entityRef":"地点/景区/杭州西湖"}\n', encoding="utf-8")
    (root / "_shared/execution_state.lock").touch()


def _freeze_supersession_source(monkeypatch: pytest.MonkeyPatch) -> None:
    frozen_source = SourceDigest.from_document(current_source_digest().to_document())
    monkeypatch.setattr(
        execution_supersession,
        "current_source_digest",
        lambda **_kwargs: frozen_source,
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


def test_legacy_terminal_manifest_is_read_only_but_nonterminal_requires_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _fixture(tmp_path, monkeypatch)
    _drift_manifest(root)
    monkeypatch.setattr(workspace, "execution_manifest_path", lambda _value: root / "execution_manifest.json")
    monkeypatch.setattr(workspace, "frozen_target_set_digest", lambda _value: "unused")

    with pytest.raises(
        workspace.ExecutionSourceDigestDriftError,
        match="DATA.EXECUTION.SOURCE_IDENTITY_MIGRATION_REQUIRED",
    ):
        workspace.load_frozen_execution_manifest(EXECUTION_ID)

    reconcile.reconcile_stale_execution(EXECUTION_ID)
    frozen = workspace.load_frozen_execution_manifest(EXECUTION_ID)
    assert frozen["schema"] == "historical-fixture"

    with pytest.raises(
        workspace.ExecutionSourceDigestDriftError,
        match="DATA.EXECUTION.SOURCE_IDENTITY_MIGRATION_REQUIRED",
    ):
        workspace.load_execution_manifest(EXECUTION_ID)


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
    _pre_controller_fixture(root)
    _freeze_supersession_source(monkeypatch)

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
    assert receipt["stateEvidence"] == "missing_pre_controller"
    assert receipt["processEvidence"]["livenessProbe"] == "pid_pgid_only_no_argv"
    assert receipt["rootInventoryEntryCount"] > 0
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


def test_source_drift_supersession_accepts_v2_source_definition_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tasks" / EXECUTION_ID
    _pre_controller_fixture(root)
    observed = current_source_definition_snapshot().to_document()
    frozen = {**observed, "digest": "sha256:" + "e" * 64}
    manifest = read_json(root / "execution_manifest.json")
    manifest["sourceDigest"] = frozen
    write_json(root / "execution_manifest.json", manifest)
    stable = SourceDefinitionSnapshot.from_document(observed)
    monkeypatch.setattr(
        execution_supersession,
        "current_source_definition_snapshot",
        lambda **_kwargs: stable,
    )

    receipt, _path = execution_supersession.supersede_execution(
        EXECUTION_ID,
        reason="source_drift",
        executions_root=root.parent,
    )

    assert receipt["manifestSourceDigest"] == frozen
    assert receipt["observedSourceDigest"] == observed


@pytest.mark.parametrize("fragment", ["head", "events"])
def test_source_drift_supersession_refuses_missing_state_journal_fragments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fragment: str,
) -> None:
    root = tmp_path / "tasks" / EXECUTION_ID
    _pre_controller_fixture(root)
    _freeze_supersession_source(monkeypatch)
    if fragment == "head":
        write_json(root / "_shared/execution_state_head.json", {"sequence": 0})
    else:
        write_json(
            root / "_shared/execution_state_events/00000000000000000001.json",
            {"fragment": True},
        )

    with pytest.raises(ValueError, match="journal fragments"):
        execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="source_drift",
            executions_root=root.parent,
        )

    assert not tuple((root / "_shared/reconciliation").glob("supersession-*.json"))


def test_source_drift_supersession_refuses_active_lease_without_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tasks" / EXECUTION_ID
    _pre_controller_fixture(root)
    _freeze_supersession_source(monkeypatch)
    write_json(
        root / "_shared/controller_lease.json",
        {
            "executionId": root.name,
            "status": "active",
            "pid": None,
            "pgid": None,
        },
    )

    with pytest.raises(ValueError, match="controller lease is active"):
        execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="source_drift",
            executions_root=root.parent,
        )


@pytest.mark.parametrize("live_field", ["pid", "pgid"])
def test_source_drift_supersession_refuses_live_recorded_identity_without_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    live_field: str,
) -> None:
    root = tmp_path / "tasks" / EXECUTION_ID
    _pre_controller_fixture(root)
    _freeze_supersession_source(monkeypatch)
    lease = {
        "executionId": root.name,
        "status": "released",
        "pid": 43210 if live_field == "pid" else None,
        "pgid": 43210 if live_field == "pgid" else None,
    }
    write_json(root / "_shared/controller_lease.json", lease)
    monkeypatch.setattr(
        execution_supersession,
        "_pid_alive",
        lambda _pid: live_field == "pid",
    )
    monkeypatch.setattr(
        execution_supersession,
        "_pgid_alive",
        lambda _pgid: live_field == "pgid",
    )

    with pytest.raises(ValueError, match="process group is still alive"):
        execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="source_drift",
            executions_root=root.parent,
        )

    assert not hasattr(execution_supersession, "_process_command")
    assert not hasattr(execution_supersession, "_group_commands")


def test_source_drift_supersession_refuses_active_state_without_live_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _fixture(tmp_path, monkeypatch)
    _drift_manifest(root)
    (root / "_shared/controller_lease.json").unlink()
    _freeze_supersession_source(monkeypatch)

    with pytest.raises(ValueError, match="state is not supersession-eligible: running"):
        execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="source_drift",
            executions_root=root.parent,
        )


def test_source_drift_supersession_refuses_unexpected_pre_controller_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tasks" / EXECUTION_ID
    _pre_controller_fixture(root)
    _freeze_supersession_source(monkeypatch)
    write_json(root / "posts/article/partial.json", {"partial": True})

    with pytest.raises(ValueError, match="not an exact pre-controller closure"):
        execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="source_drift",
            executions_root=root.parent,
        )


@pytest.mark.parametrize("corruption", ["nonempty_lock", "symlink"])
def test_source_drift_supersession_refuses_pre_controller_root_corruption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    root = tmp_path / "tasks" / EXECUTION_ID
    _pre_controller_fixture(root)
    _freeze_supersession_source(monkeypatch)
    if corruption == "nonempty_lock":
        (root / "_shared/execution_state.lock").write_text("owned", encoding="utf-8")
        expected = "state lock must be empty"
    else:
        (root / "unexpected-link").symlink_to(root / "0.plan", target_is_directory=True)
        expected = "root contains a symlink"

    with pytest.raises(ValueError, match=expected):
        execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="source_drift",
            executions_root=root.parent,
        )


def test_source_drift_supersession_receipt_detects_root_inventory_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "tasks" / EXECUTION_ID
    _pre_controller_fixture(root)
    _freeze_supersession_source(monkeypatch)
    execution_supersession.supersede_execution(
        EXECUTION_ID,
        reason="source_drift",
        executions_root=root.parent,
    )
    (root / "unexpected-empty-directory").mkdir()

    with pytest.raises(ValueError, match="root inventory drift"):
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

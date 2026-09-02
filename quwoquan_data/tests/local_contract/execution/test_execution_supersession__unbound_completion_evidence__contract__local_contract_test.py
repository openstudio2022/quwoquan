"""A `succeeded` execution whose completion evidence belongs to another release.

The delete admission counts executions that reached `ship`. That count is only
trustworthy if a `succeeded` verdict standing on someone else's import receipt
can be retracted, and if the retraction has to prove the borrowing rather than
assert it.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from content.execution import context, execution_supersession, stage_receipt
from content.execution.closure import execution_supersession_admission
from content.execution import workspace as execution_workspace
from content.execution.controller.execute import reconcile
from core.control_types import ExecutionStateStatus
from core.io import read_json, write_json
from core.source_digest import SourceDigest, current_source_digest


EXECUTION_ID = "20260828--travel-homepage-unbound--sichuan--pilot-001"
BUILT_RELEASE = "release-20260828-own-001"
SHIPPED_RELEASE = "release-20260825-someone-else-001"


def _freeze_source(monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = SourceDigest.from_document(current_source_digest().to_document())
    monkeypatch.setattr(
        execution_supersession,
        "current_source_digest",
        lambda **_kwargs: frozen,
    )


def _write_fixture_receipt(execution_id: str, payload: dict) -> Path:
    return stage_receipt._write_current_receipt_create_once(
        execution_id, payload, writer_token=stage_receipt._stage_authority_writer_token()
    )


def _digest(label: str) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _record_stage_receipt(
    root: Path,
    *,
    stage: str,
    verdict: str,
    command: str,
    next_stage: str,
) -> Path:
    sequence = len(stage_receipt.list_receipt_files(root.name)) + 1
    release_id = command.split("--release-id ", 1)[1].split()[0] if "--release-id " in command else command.split("--release ", 1)[1].split()[0]
    payload = {
        "schema": "quwoquan_data.stage_receipt", "executionId": root.name,
        "stage": stage, "sequence": sequence, "verdict": verdict,
        "actor": {"host": "fixture", "modelFamily": "deterministic", "sessionId": f"fixture-{sequence}", "invocation": None},
        "typedIssues": [] if verdict == "pass" else [{
            "code": "DATA.TEST.SHIP_BLOCKED", "message": "fixture ship blocked",
            "recoveryStage": next_stage,
        }],
        "next": next_stage,
        "authority": {
            "openRequest": {"scope": "execution", "ref": f"authority/{sequence}/open.json", "digest": _digest(f"open-{sequence}")},
            "machineGate": {"scope": "execution", "ref": f"authority/{sequence}/gate.json", "digest": _digest(f"gate-{sequence}")},
            "workflowContract": {"scope": "repo", "ref": "policy.json", "digest": _digest("workflow")},
            "semanticResult": None,
            "artifacts": [],
            "releaseBinding": {"releaseId": release_id, "releaseDigest": _digest(release_id)},
            "acceptanceBinding": ({"scope": "output", "ref": f"acceptance/{release_id}.json",
                                    "digest": _digest(f"acceptance-{release_id}"), "environment": "gamma"}
                                   if stage == "ship" else None),
        },
        "recordedAt": f"2026-09-01T00:00:{sequence:02d}Z",
    }
    path = _write_fixture_receipt(root.name, payload)
    state_path = root / "_shared/execution_state.json"
    existing_state = read_json(state_path) if state_path.is_file() else {}
    completed = list(existing_state.get("completed") or [])
    if verdict == "pass" and stage not in completed:
        completed.append(stage)
    status = (
        "manual_required"
        if verdict == "blocked"
        else "succeeded"
        if stage == "ship"
        else "running"
    )
    receipt_digest = "sha256:" + __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    write_json(
        state_path,
        {
            "schema": "quwoquan.content.execution_state_projection",
            "executionId": root.name,
            "completed": completed,
            "status": status,
            "latestStage": stage,
            "next": next_stage,
            "latestReceiptRef": f"_shared/receipts/{path.name}",
            "latestReceiptDigest": receipt_digest,
            "updatedAt": payload["recordedAt"],
        },
    )
    return path


def _succeeded_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    built: str | None = BUILT_RELEASE,
    shipped: str | None = SHIPPED_RELEASE,
    ship_verdict: str = "pass",
    status: ExecutionStateStatus = ExecutionStateStatus.SUCCEEDED,
) -> Path:
    root = tmp_path / "tasks" / EXECUTION_ID
    state_path = root / "_shared" / "execution_state.json"
    monkeypatch.setattr(reconcile, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(context, "_state_path", lambda _execution_id: state_path)
    monkeypatch.setattr(stage_receipt, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(
        execution_workspace, "execution_root", lambda _execution_id: root
    )
    write_json(
        root / "execution_manifest.json",
        {
            "schema": "historical-fixture",
            "executionId": EXECUTION_ID,
            "sourceDigest": current_source_digest().to_document(),
        },
    )
    write_json(root / "0.plan/request.json", {"topic": "travel"})
    write_json(
        root / "0.plan/target_set.json",
        {"executionId": EXECUTION_ID, "targetCount": 1},
    )
    write_json(
        root / "_shared" / "controller_lease.json",
        {
            "schema": "quwoquan_data.controller_lease",
            "status": "released",
            "executionId": EXECUTION_ID,
            "hostname": socket.gethostname(),
            "pid": 999_999,
            "pgid": 999_998,
            "heartbeatAt": "2026-08-28T00:00:00Z",
            "expiresAfterSeconds": 900,
        },
    )
    if built is not None:
        _record_stage_receipt(
            root,
            stage="release",
            verdict="pass",
            command=(
                "python3 quwoquan_data/scripts/cli.py release pool-build "
                f"--release-id {built} --all-publishable --release-class research"
            ),
            next_stage="ship",
        )

    terminal_release = shipped or "release-fixture-terminal-success-001"
    if ship_verdict == "blocked":
        _record_stage_receipt(
            root,
            stage="ship",
            verdict="blocked",
            command=(
                "python3 quwoquan_data/scripts/cli.py ship apply --env gamma "
                f"--release {terminal_release}"
            ),
            next_stage="ship",
        )
    terminal_receipt_path = _record_stage_receipt(
        root,
        stage="ship",
        verdict="pass",
        command=(
            "python3 quwoquan_data/scripts/cli.py ship apply --env gamma "
            f"--release {terminal_release}"
        ),
        next_stage="END",
    )

    # These negative cases model corrupt historical completion evidence only after
    # the canonical producer has established the terminal succeeded state.
    if shipped is None or ship_verdict != "pass":
        terminal_receipt_path.unlink()
    if status is ExecutionStateStatus.MANUAL_REQUIRED:
        # execution_state 只能由 receipt reducer 派生：追加一个 blocked ship
        # receipt，让投影回到 manual_required，而不是手写状态。
        _record_stage_receipt(
            root,
            stage="ship",
            verdict="blocked",
            command=(
                "python3 quwoquan_data/scripts/cli.py ship verify --env gamma "
                f"--release {terminal_release}"
            ),
            next_stage="ship",
        )
    elif status is not ExecutionStateStatus.SUCCEEDED:
        raise AssertionError(f"fixture does not model status={status}")
    return root


class TestSucceededWithBorrowedEvidenceIsRetractable:
    def test_supersedes_and_records_both_release_identities(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _succeeded_fixture(tmp_path, monkeypatch)
        _freeze_source(monkeypatch)

        receipt, path = execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="unbound_completion_evidence",
            executions_root=root.parent,
        )

        assert receipt["decision"] == "superseded"
        assert receipt["previousStatus"] == "succeeded"
        assert (
            receipt["errorCode"]
            == "DATA.EXECUTION.UNBOUND_COMPLETION_EVIDENCE_SUPERSEDED"
        )
        binding = receipt["completionEvidenceBinding"]
        assert binding["builtReleaseId"] == BUILT_RELEASE
        assert binding["shippedReleaseId"] == SHIPPED_RELEASE
        assert binding["builtReleaseReceiptRef"] == "001-release.json"
        assert binding["shippedReleaseReceiptRef"] == "002-ship.json"
        assert path.is_file()

    def test_is_create_once_and_leaves_the_old_evidence_byte_intact(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _succeeded_fixture(tmp_path, monkeypatch)
        _freeze_source(monkeypatch)
        ship_before = read_json(root / "_shared/receipts/002-ship.json")

        first, first_path = execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="unbound_completion_evidence",
            executions_root=root.parent,
        )
        repeated, repeated_path = execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="unbound_completion_evidence",
            executions_root=root.parent,
        )

        assert repeated == first
        assert repeated_path == first_path
        assert read_json(root / "_shared/receipts/002-ship.json") == ship_before
        assert first["evidenceDisposition"] == "protected_read_only"
        assert first["retryPolicy"] == "new_execution_with_retryOf"

    def test_refuses_a_reason_collision_on_the_same_execution(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _succeeded_fixture(tmp_path, monkeypatch)
        _freeze_source(monkeypatch)
        execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="unbound_completion_evidence",
            executions_root=root.parent,
        )

        with pytest.raises(ValueError, match="create-once reason collision"):
            execution_supersession.supersede_execution(
                EXECUTION_ID,
                reason="source_drift",
                executions_root=root.parent,
            )


class TestTheReasonMustProveTheBorrowing:
    def test_refuses_when_the_shipped_release_is_the_execution_own(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _succeeded_fixture(
            tmp_path, monkeypatch, built=BUILT_RELEASE, shipped=BUILT_RELEASE
        )
        _freeze_source(monkeypatch)

        with pytest.raises(ValueError, match="differ from the built one"):
            execution_supersession.supersede_execution(
                EXECUTION_ID,
                reason="unbound_completion_evidence",
                executions_root=root.parent,
            )
        assert not tuple((root / "_shared/reconciliation").glob("supersession-*.json"))

    def test_refuses_when_no_ship_receipt_names_a_release(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _succeeded_fixture(tmp_path, monkeypatch, shipped=None)
        _freeze_source(monkeypatch)

        with pytest.raises(ValueError, match="requires both a passing"):
            execution_supersession.supersede_execution(
                EXECUTION_ID,
                reason="unbound_completion_evidence",
                executions_root=root.parent,
            )

    def test_refuses_when_no_release_receipt_names_a_release(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _succeeded_fixture(tmp_path, monkeypatch, built=None)
        _freeze_source(monkeypatch)

        with pytest.raises(ValueError, match="requires both a passing"):
            execution_supersession.supersede_execution(
                EXECUTION_ID,
                reason="unbound_completion_evidence",
                executions_root=root.parent,
            )

    def test_a_blocked_ship_attempt_cannot_supply_the_shipped_identity(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _succeeded_fixture(tmp_path, monkeypatch, ship_verdict="blocked")
        _freeze_source(monkeypatch)

        with pytest.raises(ValueError, match="requires both a passing"):
            execution_supersession.supersede_execution(
                EXECUTION_ID,
                reason="unbound_completion_evidence",
                executions_root=root.parent,
            )


class TestTerminalProtectionStaysClosedForEveryOtherReason:
    def test_succeeded_is_not_reachable_by_source_drift(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _succeeded_fixture(tmp_path, monkeypatch)
        manifest = read_json(root / "execution_manifest.json")
        drifted = current_source_digest().to_document()
        drifted["digest"] = "sha256:" + "f" * 64
        manifest["sourceDigest"] = drifted
        write_json(root / "execution_manifest.json", manifest)
        _freeze_source(monkeypatch)

        with pytest.raises(ValueError, match="not supersession-eligible: succeeded"):
            execution_supersession.supersede_execution(
                EXECUTION_ID,
                reason="source_drift",
                executions_root=root.parent,
            )

    def test_unbound_reason_is_not_a_door_for_manual_required(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _succeeded_fixture(
            tmp_path,
            monkeypatch,
            status=ExecutionStateStatus.MANUAL_REQUIRED,
        )
        _freeze_source(monkeypatch)

        with pytest.raises(
            ValueError, match="not supersession-eligible: manual_required"
        ):
            execution_supersession.supersede_execution(
                EXECUTION_ID,
                reason="unbound_completion_evidence",
                executions_root=root.parent,
            )


def _resealed(receipt: dict[str, object], **overrides: object) -> dict[str, object]:
    """Rebuild a receipt with a self-consistent digest.

    The digest guard already catches careless edits. What has to be refused on
    top of that is a receipt whose digest was recomputed to match the tampered
    body, since that is what a hand-written one would look like.
    """
    stable = {
        key: value
        for key, value in {**receipt, **overrides}.items()
        if key != "receiptDigest"
    }
    return {**stable, "receiptDigest": execution_supersession._digest(stable)}


class TestTheReceiptCannotBeHandWritten:
    def test_validator_recomputes_the_binding_from_disk(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _succeeded_fixture(tmp_path, monkeypatch)
        _freeze_source(monkeypatch)
        receipt, path = execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="unbound_completion_evidence",
            executions_root=root.parent,
        )
        tampered = _resealed(
            receipt,
            completionEvidenceBinding={
                **receipt["completionEvidenceBinding"],
                "shippedReleaseId": "release-invented-001",
            },
        )

        with pytest.raises(ValueError, match="completion evidence binding drift"):
            execution_supersession.validate_execution_supersession_receipt(
                tampered, path=path, execution_root=root
            )

    def test_a_binding_without_its_reason_is_refused(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _succeeded_fixture(tmp_path, monkeypatch)
        _freeze_source(monkeypatch)
        receipt, path = execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="unbound_completion_evidence",
            executions_root=root.parent,
        )
        mismatched = _resealed(
            receipt,
            reason="source_drift",
            errorCode="DATA.EXECUTION.SOURCE_DRIFT_SUPERSEDED",
        )

        with pytest.raises(ValueError, match="without the reason that proves it"):
            execution_supersession.validate_execution_supersession_receipt(
                mismatched, path=path, execution_root=root
            )

    def test_an_error_code_from_another_reason_is_refused(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _succeeded_fixture(tmp_path, monkeypatch)
        _freeze_source(monkeypatch)
        receipt, path = execution_supersession.supersede_execution(
            EXECUTION_ID,
            reason="unbound_completion_evidence",
            executions_root=root.parent,
        )
        mismatched = _resealed(
            receipt,
            errorCode="DATA.EXECUTION.SOURCE_DRIFT_SUPERSEDED",
        )

        with pytest.raises(ValueError, match="does not match its reason"):
            execution_supersession.validate_execution_supersession_receipt(
                mismatched, path=path, execution_root=root
            )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-030
WORKFLOW_EXECUTION_ID = "20260901--travel-article-workflow-drift--china--scale-016"
OLD_WORKFLOW = "sha256:" + "1" * 64
CURRENT_WORKFLOW = "sha256:" + "2" * 64


def _workflow_drift_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: str = "running",
) -> Path:
    root = tmp_path / "tasks" / WORKFLOW_EXECUTION_ID
    receipt_path = root / "_shared/receipts/006-4.draft.json"
    receipt_path.parent.mkdir(parents=True)
    for sequence, stage in enumerate(stage_receipt.RECEIPT_STAGES[:5], start=1):
        predecessor = {
            "schema": "quwoquan_data.stage_receipt",
            "executionId": WORKFLOW_EXECUTION_ID,
            "stage": stage,
            "sequence": sequence,
            "verdict": "pass",
            "actor": {
                "host": "fixture",
                "modelFamily": "deterministic",
                "sessionId": f"workflow-drift-fixture-{sequence}",
                "invocation": None,
            },
            "typedIssues": [],
            "next": stage_receipt.RECEIPT_STAGES[sequence],
            "authority": {
                "openRequest": {"scope": "execution", "ref": f"open-{sequence}.json", "digest": _digest(f"open-{sequence}")},
                "machineGate": {"scope": "execution", "ref": f"gate-{sequence}.json", "digest": _digest(f"gate-{sequence}")},
                "workflowContract": {"scope": "repo", "ref": "policy.json", "digest": OLD_WORKFLOW},
                "semanticResult": None,
                "artifacts": [],
                "releaseBinding": None,
                "acceptanceBinding": None,
            },
            "recordedAt": f"2026-09-01T00:00:0{sequence}Z",
        }
        predecessor_path = root / "_shared/receipts" / f"{sequence:03d}-{stage}.json"
        predecessor_path.write_text(
            json.dumps(predecessor, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    receipt = {
        "schema": "quwoquan_data.stage_receipt",
        "executionId": WORKFLOW_EXECUTION_ID,
        "stage": "4.draft",
        "sequence": 6,
        "verdict": "pass",
        "actor": {
            "host": "fixture",
            "modelFamily": "deterministic",
            "sessionId": "workflow-drift-fixture",
            "invocation": None,
        },
        "typedIssues": [],
        "next": "5.review",
        "authority": {
            "openRequest": {"scope": "execution", "ref": "open.json", "digest": _digest("open")},
            "machineGate": {"scope": "execution", "ref": "gate.json", "digest": _digest("gate")},
            "workflowContract": {"scope": "repo", "ref": "policy.json", "digest": OLD_WORKFLOW},
            "semanticResult": {"scope": "execution", "ref": "semantic.json", "digest": _digest("semantic")},
            "artifacts": [],
            "releaseBinding": None,
            "acceptanceBinding": None,
        },
        "recordedAt": "2026-09-01T00:00:06Z",
    }
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False) + "\n", encoding="utf-8")
    source = current_source_digest().to_document()
    write_json(
        root / "execution_manifest.json",
        {
            "schema": "workflow-drift-fixture",
            "executionId": WORKFLOW_EXECUTION_ID,
            "sourceDigest": source,
            "operationalFingerprint": OLD_WORKFLOW,
        },
    )
    write_json(root / "0.plan/request.json", {"executionId": WORKFLOW_EXECUTION_ID})
    write_json(root / "0.plan/target_set.json", {"executionId": WORKFLOW_EXECUTION_ID})
    state = {
        "schema": "quwoquan.content.execution_state_projection",
        "executionId": WORKFLOW_EXECUTION_ID,
        "completed": list(stage_receipt.RECEIPT_STAGES[:6]),
        "status": status,
        "latestStage": "4.draft",
        "next": "5.review",
        "latestReceiptRef": "_shared/receipts/006-4.draft.json",
        "latestReceiptDigest": "sha256:" + __import__("hashlib").sha256(receipt_path.read_bytes()).hexdigest(),
        "updatedAt": receipt["recordedAt"],
    }
    write_json(root / "_shared/execution_state.json", state)
    write_json(
        root / "_shared/controller_lease.json",
        {
            "schema": "quwoquan_data.controller_lease",
            "status": "released",
            "executionId": WORKFLOW_EXECUTION_ID,
            "hostname": socket.gethostname(),
            "pid": 999_999,
            "pgid": 999_998,
            "heartbeatAt": "2026-09-01T00:00:00Z",
            "expiresAfterSeconds": 900,
        },
    )
    frozen = SourceDigest.from_document(source)
    monkeypatch.setattr(
        execution_supersession_admission,
        "validate_stage_receipt_authority",
        lambda _execution_id, candidate, *, verify_current_workflow: read_json(candidate),
    )
    monkeypatch.setattr(execution_supersession, "current_source_digest", lambda **_kwargs: frozen)
    monkeypatch.setattr(execution_supersession, "operational_fingerprint", lambda **_kwargs: CURRENT_WORKFLOW)
    return root


def test_workflow_drift_supersession_is_create_once_and_binds_exact_fingerprints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workflow_drift_fixture(tmp_path, monkeypatch)
    receipt_before = (root / "_shared/receipts/006-4.draft.json").read_bytes()

    first, path = execution_supersession.supersede_execution(
        WORKFLOW_EXECUTION_ID,
        reason="workflow_drift",
        executions_root=root.parent,
        repo_root=tmp_path,
    )
    repeated, repeated_path = execution_supersession.supersede_execution(
        WORKFLOW_EXECUTION_ID,
        reason="workflow_drift",
        executions_root=root.parent,
        repo_root=tmp_path,
    )

    assert repeated == first
    assert repeated_path == path
    assert first["manifestOperationalFingerprint"] == OLD_WORKFLOW
    assert first["observedOperationalFingerprint"] == CURRENT_WORKFLOW
    assert first["errorCode"] == "DATA.EXECUTION.WORKFLOW_DRIFT_SUPERSEDED"
    assert first["previousStatus"] == "running"
    assert (root / "_shared/receipts/006-4.draft.json").read_bytes() == receipt_before


def test_workflow_drift_refuses_invalid_manifest_fingerprint_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workflow_drift_fixture(tmp_path, monkeypatch)
    manifest = read_json(root / "execution_manifest.json")
    manifest["operationalFingerprint"] = "bc0f7cc"
    write_json(root / "execution_manifest.json", manifest)

    with pytest.raises(ValueError, match="must be sha256"):
        execution_supersession.supersede_execution(
            WORKFLOW_EXECUTION_ID,
            reason="workflow_drift",
            executions_root=root.parent,
            repo_root=tmp_path,
        )


def test_workflow_drift_refuses_equal_fingerprint_and_missing_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workflow_drift_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(execution_supersession, "operational_fingerprint", lambda **_kwargs: OLD_WORKFLOW)
    with pytest.raises(ValueError, match="requires operational drift"):
        execution_supersession.supersede_execution(
            WORKFLOW_EXECUTION_ID,
            reason="workflow_drift",
            executions_root=root.parent,
            repo_root=tmp_path,
        )

    (root / "_shared/execution_state.json").unlink()
    monkeypatch.setattr(execution_supersession, "operational_fingerprint", lambda **_kwargs: CURRENT_WORKFLOW)
    with pytest.raises(ValueError, match="requires execution state"):
        execution_supersession.supersede_execution(
            WORKFLOW_EXECUTION_ID,
            reason="workflow_drift",
            executions_root=root.parent,
            repo_root=tmp_path,
        )


@pytest.mark.parametrize("reason", ["source_drift", "missing_canonical_input"])
def test_running_state_is_reserved_for_workflow_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    root = _workflow_drift_fixture(tmp_path, monkeypatch)
    if reason == "source_drift":
        manifest = read_json(root / "execution_manifest.json")
        manifest["sourceDigest"] = {
            **manifest["sourceDigest"],
            "digest": "sha256:" + "f" * 64,
        }
        write_json(root / "execution_manifest.json", manifest)
    else:
        (root / "0.plan/request.json").unlink()
    with pytest.raises(ValueError, match="not supersession-eligible: running"):
        execution_supersession.supersede_execution(
            WORKFLOW_EXECUTION_ID,
            reason=reason,
            executions_root=root.parent,
            repo_root=tmp_path,
        )


def test_workflow_drift_refuses_succeeded_and_resealed_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workflow_drift_fixture(tmp_path, monkeypatch)
    state = read_json(root / "_shared/execution_state.json")
    state["status"] = "succeeded"
    write_json(root / "_shared/execution_state.json", state)
    with pytest.raises(ValueError, match="not supersession-eligible: succeeded"):
        execution_supersession.supersede_execution(
            WORKFLOW_EXECUTION_ID,
            reason="workflow_drift",
            executions_root=root.parent,
            repo_root=tmp_path,
        )

    state["status"] = "running"
    write_json(root / "_shared/execution_state.json", state)
    receipt, path = execution_supersession.supersede_execution(
        WORKFLOW_EXECUTION_ID,
        reason="workflow_drift",
        executions_root=root.parent,
        repo_root=tmp_path,
    )
    tampered = _resealed(receipt, observedOperationalFingerprint="sha256:" + "3" * 64)
    with pytest.raises(ValueError, match="workflow fingerprint binding drift"):
        execution_supersession.validate_execution_supersession_receipt(
            tampered,
            path=path,
            execution_root=root,
            repo_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("remove_field", "add_field"),
    [
        ("manifestOperationalFingerprint", None),
        (None, "manifestOperationalFingerprint"),
        (None, "observedOperationalFingerprint"),
    ],
)
def test_workflow_binding_fields_fail_closed_by_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remove_field: str | None,
    add_field: str | None,
) -> None:
    root = _workflow_drift_fixture(tmp_path, monkeypatch)
    receipt, path = execution_supersession.supersede_execution(
        WORKFLOW_EXECUTION_ID,
        reason="workflow_drift",
        executions_root=root.parent,
        repo_root=tmp_path,
    )
    candidate = dict(receipt)
    if remove_field is not None:
        candidate.pop(remove_field)
    if add_field is not None:
        candidate["reason"] = "source_drift"
        candidate["errorCode"] = "DATA.EXECUTION.SOURCE_DRIFT_SUPERSEDED"
        candidate[add_field] = CURRENT_WORKFLOW
    candidate = _resealed(candidate)
    with pytest.raises(ValueError):
        execution_supersession.validate_execution_supersession_receipt(
            candidate,
            path=path,
            execution_root=root,
            repo_root=tmp_path,
        )



def test_workflow_drift_detects_manifest_toctou_before_create_once_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workflow_drift_fixture(tmp_path, monkeypatch)
    calls = 0

    def changing_fingerprint(**_kwargs: object) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            manifest = read_json(root / "execution_manifest.json")
            manifest["operationalFingerprint"] = "sha256:" + "4" * 64
            write_json(root / "execution_manifest.json", manifest)
        return CURRENT_WORKFLOW

    monkeypatch.setattr(
        execution_supersession,
        "operational_fingerprint",
        changing_fingerprint,
    )
    with pytest.raises(
        ValueError,
        match="workflow fingerprint changed|execution root changed",
    ):
        execution_supersession.supersede_execution(
            WORKFLOW_EXECUTION_ID,
            reason="workflow_drift",
            executions_root=root.parent,
            repo_root=tmp_path,
        )
    assert not tuple((root / "_shared/reconciliation").glob("supersession-*.json"))

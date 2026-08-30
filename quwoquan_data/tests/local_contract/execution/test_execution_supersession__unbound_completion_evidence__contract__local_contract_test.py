"""A `succeeded` execution whose completion evidence belongs to another release.

The delete admission counts executions that reached `ship`. That count is only
trustworthy if a `succeeded` verdict standing on someone else's import receipt
can be retracted, and if the retraction has to prove the borrowing rather than
assert it.
"""
from __future__ import annotations

import socket
from pathlib import Path

import pytest
from content.execution import context, execution_supersession, stage_receipt
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


def _record_stage_receipt(
    root: Path,
    *,
    stage: str,
    verdict: str,
    command: str,
    next_stage: str,
) -> Path:
    return stage_receipt.record_stage_receipt(
        execution_id=root.name,
        stage=stage,
        verdict=verdict,
        actor_host="cursor",
        actor_model_family="claude",
        actor_session="supersession-contract-fixture",
        artifacts=[],
        open_items=(
            []
            if verdict == "pass"
            else [{"item": "fixture ship blocked", "disposition": "gate_block"}]
        ),
        next_stage=next_stage,
        evidence_commands=[{"command": command, "exitCode": 0}],
        issue_count=0 if verdict == "pass" else 1,
        repair_rounds=0,
    )


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
    if status is not ExecutionStateStatus.SUCCEEDED:
        state = context.load_execution_state(EXECUTION_ID)
        state.status = status
        context.save_execution_state(state)
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

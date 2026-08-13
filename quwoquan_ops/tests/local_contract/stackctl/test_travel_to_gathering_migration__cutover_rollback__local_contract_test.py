"""M6 travel-service -> Gathering target-only 迁移控制面契约（cutover 与 rollback 证据链）。

由 1000 行硬顶拆分自根目录
test_travel_to_gathering_migration__local_contract_test.py；测试逐字搬移，
共享构造 helper 见 quwoquan_ops/tests/support/travel_to_gathering_migration_test_support.py。

spec_ref: specs/feature-tree/travel-journey/spec.md#dom-001
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.migrations.travel_to_gathering import control_plane
from quwoquan_ops.tests.support.travel_to_gathering_migration_test_support import (
    DIGEST_A,
    DIGEST_B,
    DIGEST_C,
    _cutover_evidence,
    _operational_evidence,
    _reseal_evidence,
    _reseal_migration_receipt,
    _target_contract,
    _write_cutover_inputs,
    _write_json,
)


def test_cutover_requires_upstream_receipts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "alpha",
            "--phase",
            "cutover",
            "--report-dir",
            str(output / "cutover"),
        ]
    )

    result = control_plane.command(args)

    assert result["exitCode"] == 2
    report = json.loads(
        (output / "cutover/report.json").read_text(encoding="utf-8")
    )
    assert report["errorCode"] == "REQUIRED_RECEIPT_MISSING"
    assert report["writeSet"] == []
    assert not (output / "cutover/receipt.json").exists()


def test_cutover_validates_receipt_chain_and_emits_target_only_write_set(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence = _cutover_evidence()
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "alpha",
            "--phase",
            "cutover",
            "--report-dir",
            str(output / "cutover"),
            *_write_cutover_inputs(inputs, evidence),
        ]
    )

    result = control_plane.command(args)
    receipt = json.loads(
        (output / "cutover/receipt.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 0
    assert receipt["status"] == "passed"
    assert receipt["executionMode"] == "external_evidence_only"
    assert receipt["cutover"]["status"] == "externally_executed"
    assert receipt["cutover"]["sourceWriteState"] == "frozen_permanently"
    assert receipt["cutover"]["sourceWriteRecoveryAllowed"] is False
    assert receipt["cutover"]["sourceFallbackAllowed"] is False
    assert receipt["cutover"]["configActivationPlan"] == {
        "candidateDigest": DIGEST_B,
        "writeSetDigest": control_plane.canonical_digest(receipt["writeSet"]),
        "activateTargetReads": True,
        "decommissionSourceRuntime": True,
        "sourceTrafficMode": "disabled",
        "sourceFallbackAllowed": False,
        "sourceWriteRecoveryAllowed": False,
        "executedByControlPlane": False,
    }
    assert receipt["writeSet"] == [
        {
            "stepId": "cutover.activate-target-only-config",
            "plane": "target_config",
            "service": "circle-service",
            "operation": "activate_target_only_candidate",
            "candidateDigest": DIGEST_B,
            "executionMode": "external_approval_only",
        }
    ]
    assert "travel-service" not in json.dumps(receipt["writeSet"])


def test_prod_cutover_without_approval_remains_gate_block(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence = _cutover_evidence("prod")
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "prod",
            "--phase",
            "cutover",
            "--report-dir",
            str(output / "prod-cutover"),
            *_write_cutover_inputs(
                inputs,
                evidence,
                include_approval=False,
                include_activation=False,
            ),
        ]
    )

    result = control_plane.command(args)
    receipt = json.loads(
        (output / "prod-cutover/receipt.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 2
    assert receipt["status"] == "GATE_BLOCK"
    assert receipt["executionMode"] == "approval_plan"
    assert receipt["cutover"]["approvalRequirement"]["status"] == "missing"
    assert {
        blocker["code"] for blocker in receipt["blockers"]
    } == {
        "PROTECTED_ENVIRONMENT_APPROVAL_REQUIRED",
        "TARGET_CONFIG_ACTIVATION_EVIDENCE_REQUIRED",
    }
    assert len(receipt["writeSet"]) == 1


def test_cutover_rejects_external_evidence_digest_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence = _cutover_evidence()
    evidence["backup"]["subjectDigests"]["sourceSnapshotDigest"] = DIGEST_C
    _reseal_evidence(evidence["backup"])
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "alpha",
            "--phase",
            "cutover",
            "--report-dir",
            str(output / "digest-mismatch"),
            *_write_cutover_inputs(inputs, evidence),
        ]
    )

    result = control_plane.command(args)
    report = json.loads(
        (output / "digest-mismatch/report.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 2
    assert report["errorCode"] == "EXTERNAL_EVIDENCE_DIGEST_MISMATCH"


@pytest.mark.parametrize(
    ("plane", "service", "operation_id", "expected_code"),
    (
        (
            "source_command",
            "travel-service",
            "travel.TripPlan.Update",
            "SOURCE_WRITE_FORBIDDEN",
        ),
        (
            "target_database",
            "circle-service",
            "direct_database_write",
            "DIRECT_TARGET_WRITE_FORBIDDEN",
        ),
    ),
)
def test_cutover_rejects_source_and_direct_target_database_writes(
    monkeypatch,
    tmp_path: Path,
    plane: str,
    service: str,
    operation_id: str,
    expected_code: str,
) -> None:
    output = tmp_path / ".qwq_output"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence = _cutover_evidence()
    write = evidence["targetCommand"]["writeSet"][0]
    write.update(
        {
            "plane": plane,
            "service": service,
            "operationId": operation_id,
        }
    )
    _reseal_evidence(evidence["targetCommand"])
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "alpha",
            "--phase",
            "cutover",
            "--report-dir",
            str(output / expected_code),
            *_write_cutover_inputs(inputs, evidence),
        ]
    )

    result = control_plane.command(args)
    report = json.loads(
        (output / expected_code / "report.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 2
    assert report["errorCode"] == expected_code


def test_cutover_rejects_quarantined_upstream_receipt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence = _cutover_evidence()
    evidence["inventory"]["dispositions"]["counts"]["quarantined"] = 1
    evidence["inventory"] = _reseal_migration_receipt(evidence["inventory"])
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "alpha",
            "--phase",
            "cutover",
            "--report-dir",
            str(output / "quarantined"),
            *_write_cutover_inputs(inputs, evidence),
        ]
    )

    result = control_plane.command(args)
    report = json.loads(
        (output / "quarantined/report.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 2
    assert report["errorCode"] == "QUARANTINED_SOURCE_OBJECTS"


def test_rollback_only_restores_target_snapshot_and_requires_post_parity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / ".qwq_output"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    evidence = _cutover_evidence()
    cutover = control_plane.build_cutover_receipt(
        environment="alpha",
        inventory_receipt=evidence["inventory"],
        parity_receipt=evidence["parity"],
        target_contract=_target_contract(),
        target_backup_evidence=evidence["backup"],
        source_freeze_evidence=evidence["freeze"],
        target_command_evidence=evidence["targetCommand"],
        config_candidate_digest=DIGEST_B,
        approval_evidence=evidence["approval"],
        activation_evidence=evidence["activation"],
    )
    cutover_path = inputs / "cutover.json"
    parity_path = inputs / "post-restore-parity.json"
    _write_json(cutover_path, cutover)
    _write_json(parity_path, evidence["parity"])
    planned_write_set = [
        {
            "stepId": "rollback.target_snapshot",
            "plane": "target_snapshot",
            "service": "circle-service",
            "operation": "restore_target_snapshot",
            "candidateDigest": DIGEST_C,
            "executionMode": "external_approval_only",
        }
    ]
    rollback_subject = {
        "cutoverReceiptDigest": cutover["receiptDigest"],
        "targetContractDigest": DIGEST_A,
        "crosswalkDigest": cutover["crosswalkDigest"],
        "sourceSnapshotDigest": cutover["source"]["snapshotDigest"],
        "rollbackCandidateDigest": DIGEST_C,
        "plannedWriteSetDigest": control_plane.canonical_digest(
            planned_write_set
        ),
    }
    approval = _operational_evidence(
        "protected_environment_approval",
        environment="alpha",
        subject_digests=dict(rollback_subject),
        claims={
            "decision": "approved",
            "protectedEnvironmentWritesApproved": True,
        },
    )
    restore = _operational_evidence(
        "target_restore",
        environment="alpha",
        subject_digests={
            **rollback_subject,
            "approvalEvidenceDigest": approval["evidenceDigest"],
            "restoredTargetSnapshotDigest": evidence["parity"]["target"][
                "snapshotDigest"
            ],
        },
        claims={
            "targetRestored": True,
            "sourceWrite": False,
            "directDatabaseWrite": False,
            "derivedProjectionWrite": False,
        },
        write_set=[
            {
                "plane": "target_snapshot",
                "service": "circle-service",
                "operationId": "restore_target_snapshot",
                "targetObjectId": "circle.gathering",
                "commandReceiptDigest": DIGEST_C,
            }
        ],
    )
    approval_path = inputs / "rollback-approval.json"
    restore_path = inputs / "restore.json"
    _write_json(approval_path, approval)
    _write_json(restore_path, restore)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        control_plane,
        "resolve_target_contract",
        lambda _root: _target_contract(),
    )
    args = stackctl.build_parser().parse_args(
        [
            "migration",
            "travel-to-gathering",
            "--env",
            "alpha",
            "--phase",
            "rollback",
            "--report-dir",
            str(output / "rollback"),
            "--cutover-receipt",
            str(cutover_path),
            "--post-restore-parity-receipt",
            str(parity_path),
            "--approval-receipt",
            str(approval_path),
            "--target-restore-receipt",
            str(restore_path),
            "--rollback-mode",
            "target_snapshot",
            "--rollback-candidate-digest",
            DIGEST_C,
        ]
    )

    result = control_plane.command(args)
    receipt = json.loads(
        (output / "rollback/receipt.json").read_text(encoding="utf-8")
    )

    assert result["exitCode"] == 0
    assert receipt["rollback"]["status"] == (
        "externally_restored_and_parity_passed"
    )
    assert receipt["rollback"]["sourceWriteRecoveryAllowed"] is False
    assert receipt["writeSet"][0]["plane"] == "target_snapshot"
    assert receipt["writeSet"][0]["executionMode"] == "externally_executed"
    assert "travel-service" not in json.dumps(receipt["writeSet"])


def test_rollback_restore_evidence_cannot_recover_travel_source_writes(
    tmp_path: Path,
) -> None:
    evidence = _operational_evidence(
        "target_restore",
        environment="alpha",
        subject_digests={"cutoverReceiptDigest": DIGEST_A},
        claims={
            "targetRestored": True,
            "sourceWrite": False,
            "directDatabaseWrite": False,
            "derivedProjectionWrite": False,
        },
        write_set=[
            {
                "plane": "source_write_recovery",
                "service": "travel-service",
                "operationId": "restore_travel_writes",
                "targetObjectId": "travel.TripPlan",
                "commandReceiptDigest": DIGEST_B,
            }
        ],
    )
    path = tmp_path / "restore.json"
    _write_json(path, evidence)

    with pytest.raises(control_plane.MigrationControlError) as raised:
        control_plane._load_operational_evidence(
            path,
            environment="alpha",
            evidence_type="target_restore",
            expected_digests={"cutoverReceiptDigest": DIGEST_A},
            target_contract=_target_contract(),
        )

    assert raised.value.code == "SOURCE_WRITE_FORBIDDEN"

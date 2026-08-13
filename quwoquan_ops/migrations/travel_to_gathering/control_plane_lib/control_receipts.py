"""cutover / rollback 控制阶段回执构建（逐字来自原 ``control_plane.py``）。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.codec import (
    _require_digest,
    canonical_digest,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.constants import (
    COMMAND_NAME,
    MIGRATION_ID,
    RECEIPT_SCHEMA,
    ROLLBACK_MODES,
    MigrationControlError,
    TargetContractBinding,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.evidence import (
    _evidence_ref,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.mapping_support import (
    _dedupe_blockers,
    _safe_blocker,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.receipts import (
    _assert_receipt_chain,
    _availability_sections,
    _seal_receipt,
    validate_receipt,
)


def _control_receipt_base(
    upstream: Mapping[str, Any],
    *,
    phase: str,
    status: str,
    blockers: Sequence[Mapping[str, Any]],
    write_set: Sequence[Mapping[str, Any]],
    cutover: Mapping[str, Any],
    rollback: Mapping[str, Any],
) -> dict[str, Any]:
    stable = {
        "schema": RECEIPT_SCHEMA,
        "migrationId": MIGRATION_ID,
        "command": COMMAND_NAME,
        "environment": upstream["environment"],
        "phase": phase,
        "status": status,
        "executionMode": (
            "approval_plan" if status == "GATE_BLOCK" else "external_evidence_only"
        ),
        "source": upstream["source"],
        "target": upstream["target"],
        "crosswalkDigest": upstream["crosswalkDigest"],
        "inventory": upstream["inventory"],
        "mapping": upstream["mapping"],
        "dispositions": upstream["dispositions"],
        "conflicts": upstream["conflicts"],
        "blockers": list(_dedupe_blockers(dict(value) for value in blockers)),
        "piiRedaction": upstream["piiRedaction"],
        "validation": upstream["validation"],
        "parity": upstream["parity"],
        "writeSet": [dict(value) for value in write_set],
        "cutover": dict(cutover),
        "rollback": dict(rollback),
    }
    receipt = _seal_receipt(stable)
    validate_receipt(receipt)
    return receipt


def build_cutover_receipt(
    *,
    environment: str,
    inventory_receipt: Mapping[str, Any],
    parity_receipt: Mapping[str, Any],
    target_contract: TargetContractBinding,
    target_backup_evidence: Mapping[str, Any],
    source_freeze_evidence: Mapping[str, Any],
    target_command_evidence: Mapping[str, Any],
    config_candidate_digest: str,
    approval_evidence: Mapping[str, Any] | None,
    activation_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if (
        inventory_receipt.get("environment") != environment
        or parity_receipt.get("environment") != environment
        or any(
            evidence.get("environment") != environment
            for evidence in (
                target_backup_evidence,
                source_freeze_evidence,
                target_command_evidence,
            )
        )
        or (
            approval_evidence is not None
            and approval_evidence.get("environment") != environment
        )
        or (
            activation_evidence is not None
            and activation_evidence.get("environment") != environment
        )
    ):
        raise MigrationControlError(
            "RECEIPT_ENV_MISMATCH",
            "cutover receipt/evidence environments must match",
        )
    _assert_receipt_chain(inventory_receipt, parity_receipt)
    if parity_receipt["target"].get("generatedContractDigest") != target_contract.digest:
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISMATCH",
            "parity target contract differs from current canonical contracts",
        )
    config_candidate_digest = _require_digest(
        config_candidate_digest,
        label="config candidate digest",
    )
    write_set = [
        {
            "stepId": "cutover.activate-target-only-config",
            "plane": "target_config",
            "service": "circle-service",
            "operation": "activate_target_only_candidate",
            "candidateDigest": config_candidate_digest,
            "executionMode": "external_approval_only",
        }
    ]
    write_set_digest = canonical_digest(write_set)
    blockers: list[dict[str, Any]] = []
    approval_ref: dict[str, Any] | None = None
    activation_ref: dict[str, Any] | None = None
    if approval_evidence is None:
        blockers.append(
            _safe_blocker(
                "PROTECTED_ENVIRONMENT_APPROVAL_REQUIRED",
                reason="target config activation requires signed external approval",
            )
        )
    else:
        approval_ref = _evidence_ref(approval_evidence)
    if activation_evidence is None:
        blockers.append(
            _safe_blocker(
                "TARGET_CONFIG_ACTIVATION_EVIDENCE_REQUIRED",
                reason="control plane never executes protected target config writes",
            )
        )
    else:
        activation_ref = _evidence_ref(activation_evidence)
    cutover = {
        "status": (
            "externally_executed"
            if not blockers
            else "external_execution_required"
        ),
        "targetOnly": True,
        "sourceWriteState": "frozen_permanently",
        "sourceWriteRecoveryAllowed": False,
        "sourceFallbackAllowed": False,
        "sourceTrafficMode": "disabled",
        "sourceRuntimeRecoveryAllowed": False,
        "dualReadAllowed": False,
        "dualWriteAllowed": False,
        "targetDataApplication": _evidence_ref(target_command_evidence),
        "evidence": {
            "inventoryReceiptDigest": inventory_receipt["receiptDigest"],
            "parityReceiptDigest": parity_receipt["receiptDigest"],
            "targetBackup": _evidence_ref(target_backup_evidence),
            "sourceWriteFreeze": _evidence_ref(source_freeze_evidence),
            "protectedEnvironmentApproval": approval_ref,
            "targetConfigActivation": activation_ref,
        },
        "configActivationPlan": {
            "candidateDigest": config_candidate_digest,
            "writeSetDigest": write_set_digest,
            "activateTargetReads": True,
            "decommissionSourceRuntime": True,
            "sourceTrafficMode": "disabled",
            "sourceFallbackAllowed": False,
            "sourceWriteRecoveryAllowed": False,
            "executedByControlPlane": False,
        },
        "approvalRequirement": {
            "required": True,
            "status": "approved" if approval_ref else "missing",
            "writeSetDigest": write_set_digest,
            "bypassSupported": False,
        },
    }
    _, rollback = _availability_sections()
    return _control_receipt_base(
        parity_receipt,
        phase="cutover",
        status="GATE_BLOCK" if blockers else "passed",
        blockers=blockers,
        write_set=write_set,
        cutover=cutover,
        rollback=rollback,
    )


def build_rollback_receipt(
    *,
    cutover_receipt: Mapping[str, Any],
    post_restore_parity_receipt: Mapping[str, Any],
    target_contract: TargetContractBinding,
    rollback_mode: str,
    rollback_candidate_digest: str,
    approval_evidence: Mapping[str, Any],
    restore_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if rollback_mode not in ROLLBACK_MODES:
        raise MigrationControlError(
            "ROLLBACK_MODE_INVALID",
            f"rollback mode must be one of {ROLLBACK_MODES}",
        )
    if (
        cutover_receipt.get("status") != "passed"
        or cutover_receipt.get("cutover", {}).get("status")
        != "externally_executed"
    ):
        raise MigrationControlError(
            "CUTOVER_RECEIPT_NOT_EXECUTED",
            "rollback requires a passed externally-executed cutover receipt",
        )
    if (
        post_restore_parity_receipt["source"].get("snapshotDigest")
        != cutover_receipt["source"].get("snapshotDigest")
        or post_restore_parity_receipt["target"].get("generatedContractDigest")
        != cutover_receipt["target"].get("generatedContractDigest")
        or post_restore_parity_receipt.get("crosswalkDigest")
        != cutover_receipt.get("crosswalkDigest")
        or post_restore_parity_receipt["mapping"].get("targetDocumentDigest")
        != cutover_receipt["mapping"].get("targetDocumentDigest")
    ):
        raise MigrationControlError(
            "POST_RESTORE_PARITY_DIGEST_MISMATCH",
            "post-restore parity does not reconcile the approved cutover data set",
        )
    if cutover_receipt["target"].get("generatedContractDigest") != target_contract.digest:
        raise MigrationControlError(
            "TARGET_CONTRACT_DIGEST_MISMATCH",
            "rollback target contract differs from current canonical contracts",
        )
    rollback_candidate_digest = _require_digest(
        rollback_candidate_digest,
        label="rollback candidate digest",
    )
    if rollback_mode == "target_application_config":
        plane = "target_config"
        operation = "restore_target_application_config"
    else:
        plane = "target_snapshot"
        operation = "restore_target_snapshot"
    write_set = [
        {
            "stepId": f"rollback.{rollback_mode}",
            "plane": plane,
            "service": "circle-service",
            "operation": operation,
            "candidateDigest": rollback_candidate_digest,
            "executionMode": "externally_executed",
        }
    ]
    write_set_digest = canonical_digest(
        [
            {
                **write_set[0],
                "executionMode": "external_approval_only",
            }
        ]
    )
    cutover, _ = _availability_sections()
    rollback = {
        "status": "externally_restored_and_parity_passed",
        "mode": rollback_mode,
        "targetOnly": True,
        "sourceWriteRecoveryAllowed": False,
        "sourceRuntimeRecoveryAllowed": False,
        "sourceFallbackAllowed": False,
        "restorePlan": {
            "candidateDigest": rollback_candidate_digest,
            "writeSetDigest": write_set_digest,
            "executedByControlPlane": False,
        },
        "approvalRequirement": {
            "required": True,
            "status": "approved",
            "writeSetDigest": write_set_digest,
            "bypassSupported": False,
        },
        "evidence": {
            "cutoverReceiptDigest": cutover_receipt["receiptDigest"],
            "protectedEnvironmentApproval": _evidence_ref(approval_evidence),
            "targetRestore": _evidence_ref(restore_evidence),
            "postRestoreParityReceiptDigest": post_restore_parity_receipt[
                "receiptDigest"
            ],
            "postRestoreTargetSnapshotDigest": post_restore_parity_receipt[
                "target"
            ].get("snapshotDigest"),
        },
    }
    return _control_receipt_base(
        post_restore_parity_receipt,
        phase="rollback",
        status="passed",
        blockers=(),
        write_set=write_set,
        cutover=cutover,
        rollback=rollback,
    )

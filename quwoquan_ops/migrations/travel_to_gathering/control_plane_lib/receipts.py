"""迁移回执的封存、校验、链路断言与证据阶段回执构建。

内容逐字来自原 ``control_plane.py``。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.codec import (
    _load_object,
    canonical_digest,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.constants import (
    COMMAND_NAME,
    CONTROL_PHASES,
    CROSSWALK_PATH,
    ENVIRONMENTS,
    EVIDENCE_PHASES,
    MIGRATION_ID,
    PHASES,
    RECEIPT_SCHEMA,
    MappingResult,
    MigrationControlError,
    TargetContractBinding,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.evidence import (
    _validate_control_write_set,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.mapping_support import (
    _dedupe_blockers,
    _safe_blocker,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.parity import (
    _disposition_summary,
    build_parity,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.snapshots import (
    _pii_redaction_report,
    build_inventory,
)


def _availability_sections() -> tuple[dict[str, Any], dict[str, Any]]:
    cutover = {
        "status": "available",
        "gate": "external_approval_required",
        "requiredEvidence": [
            "passed inventory migration receipt",
            "passed 100% parity migration receipt",
            "signed target_backup evidence",
            "signed source_write_freeze evidence",
            "signed target_command_import evidence",
            "signed protected_environment_approval evidence",
            "configuration candidate digest",
        ],
        "bypassSupported": False,
        "environmentWritesExecutedByControlPlane": False,
        "sourceWriteRecoveryAllowed": False,
    }
    rollback = {
        "status": "available",
        "gate": "external_approval_required",
        "requiredEvidence": [
            "approved cutover migration receipt",
            "signed protected_environment_approval evidence",
            "signed target_restore evidence",
            "passed post-restore parity migration receipt",
            "rollback candidate digest",
        ],
        "bypassSupported": False,
        "environmentWritesExecutedByControlPlane": False,
        "sourceWriteRecoveryAllowed": False,
    }
    return cutover, rollback


def _load_migration_receipt(
    path: Path,
    *,
    environment: str,
    phase: str,
) -> dict[str, Any]:
    receipt = _load_object(path, label=f"{phase} migration receipt")
    validate_receipt(receipt)
    if receipt.get("environment") != environment:
        raise MigrationControlError(
            "RECEIPT_ENV_MISMATCH",
            f"{phase} receipt environment does not match --env",
        )
    if receipt.get("phase") != phase:
        raise MigrationControlError(
            "RECEIPT_PHASE_MISMATCH",
            f"expected {phase} migration receipt",
        )
    if receipt.get("status") != "passed":
        raise MigrationControlError(
            "UPSTREAM_RECEIPT_BLOCKED",
            f"{phase} migration receipt is not passed",
        )
    if receipt.get("blockers"):
        raise MigrationControlError(
            "UPSTREAM_RECEIPT_BLOCKED",
            f"{phase} migration receipt contains blockers",
        )
    conflicts = receipt.get("conflicts")
    if not isinstance(conflicts, dict) or conflicts.get("totalCount") != 0:
        raise MigrationControlError(
            "MIGRATION_COLLISION",
            f"{phase} migration receipt contains collisions",
        )
    dispositions = receipt.get("dispositions")
    counts = dispositions.get("counts") if isinstance(dispositions, dict) else None
    if not isinstance(counts, dict) or counts.get("quarantined") != 0:
        raise MigrationControlError(
            "QUARANTINED_SOURCE_OBJECTS",
            f"{phase} migration receipt contains quarantined objects",
        )
    if phase == "parity":
        parity = receipt.get("parity")
        if (
            not isinstance(parity, dict)
            or parity.get("status") != "passed"
            or parity.get("percentage") != 100
        ):
            raise MigrationControlError(
                "PARITY_NOT_100_PERCENT",
                "parity receipt must prove 100% parity",
            )
    return receipt


def _assert_receipt_chain(
    inventory_receipt: Mapping[str, Any],
    parity_receipt: Mapping[str, Any],
) -> None:
    comparisons = (
        ("source.snapshotDigest", inventory_receipt["source"], parity_receipt["source"]),
        (
            "target.generatedContractDigest",
            inventory_receipt["target"],
            parity_receipt["target"],
        ),
        ("mapping.targetDocumentDigest", inventory_receipt["mapping"], parity_receipt["mapping"]),
    )
    keys = {
        "source.snapshotDigest": "snapshotDigest",
        "target.generatedContractDigest": "generatedContractDigest",
        "mapping.targetDocumentDigest": "targetDocumentDigest",
    }
    for label, left, right in comparisons:
        key = keys[label]
        if left.get(key) != right.get(key):
            raise MigrationControlError(
                "RECEIPT_CHAIN_DIGEST_MISMATCH",
                f"{label} differs between inventory and parity receipts",
            )
    if inventory_receipt.get("crosswalkDigest") != parity_receipt.get(
        "crosswalkDigest"
    ):
        raise MigrationControlError(
            "RECEIPT_CHAIN_DIGEST_MISMATCH",
            "crosswalkDigest differs between inventory and parity receipts",
        )
    if canonical_digest(inventory_receipt.get("inventory")) != canonical_digest(
        parity_receipt.get("inventory")
    ):
        raise MigrationControlError(
            "RECEIPT_CHAIN_DIGEST_MISMATCH",
            "inventory evidence differs between inventory and parity receipts",
        )


def _seal_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    stable = dict(payload)
    seed = canonical_digest(stable).removeprefix("sha256:")
    receipt_id = f"{MIGRATION_ID}:{stable['environment']}:{stable['phase']}:{seed}"
    with_id = {**stable, "receiptId": receipt_id}
    return {**with_id, "receiptDigest": canonical_digest(with_id)}


def validate_receipt(receipt: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "migrationId",
        "command",
        "environment",
        "phase",
        "status",
        "executionMode",
        "source",
        "target",
        "crosswalkDigest",
        "inventory",
        "mapping",
        "dispositions",
        "conflicts",
        "blockers",
        "piiRedaction",
        "validation",
        "parity",
        "writeSet",
        "cutover",
        "rollback",
        "receiptId",
        "receiptDigest",
    }
    if set(receipt) != required:
        raise MigrationControlError(
            "RECEIPT_INVALID",
            "migration receipt fields do not match canonical schema",
        )
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise MigrationControlError(
            "RECEIPT_INVALID", "migration receipt schema mismatch"
        )
    if receipt.get("migrationId") != MIGRATION_ID:
        raise MigrationControlError("RECEIPT_INVALID", "migration receipt id mismatch")
    if receipt.get("environment") not in ENVIRONMENTS:
        raise MigrationControlError(
            "RECEIPT_INVALID",
            "migration receipt environment is invalid",
        )
    if receipt.get("phase") not in PHASES:
        raise MigrationControlError(
            "RECEIPT_INVALID", "migration receipt phase is invalid"
        )
    if receipt.get("status") not in {"passed", "GATE_BLOCK"}:
        raise MigrationControlError(
            "RECEIPT_INVALID", "migration receipt status is invalid"
        )
    execution_mode = receipt.get("executionMode")
    if execution_mode not in {
        "read_only",
        "zero_write",
        "approval_plan",
        "external_evidence_only",
    }:
        raise MigrationControlError(
            "RECEIPT_INVALID",
            "migration receipt executionMode is invalid",
        )
    _validate_control_write_set(
        receipt.get("writeSet"),
        phase=str(receipt["phase"]),
    )
    if receipt["phase"] in EVIDENCE_PHASES and execution_mode not in {
        "read_only",
        "zero_write",
    }:
        raise MigrationControlError(
            "RECEIPT_INVALID",
            "evidence receipt executionMode is invalid",
        )
    if receipt["phase"] in CONTROL_PHASES and execution_mode not in {
        "approval_plan",
        "external_evidence_only",
    }:
        raise MigrationControlError(
            "RECEIPT_INVALID",
            "control receipt executionMode is invalid",
        )
    expected_digest = canonical_digest(
        {key: value for key, value in receipt.items() if key != "receiptDigest"}
    )
    if receipt.get("receiptDigest") != expected_digest:
        raise MigrationControlError(
            "RECEIPT_INVALID", "migration receipt digest mismatch"
        )


def build_receipt(
    *,
    environment: str,
    phase: str,
    snapshot: Mapping[str, Any],
    target_contract: TargetContractBinding,
    mapping: MappingResult,
    target_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    crosswalk = _load_object(CROSSWALK_PATH, label="travel-to-gathering crosswalk")
    inventory = build_inventory(snapshot)
    parity = build_parity(
        mapping.documents,
        (
            target_snapshot.get("documents")
            if isinstance(target_snapshot, dict)
            else None
        ),
    )
    blockers = list(mapping.blockers)
    if phase == "parity" and parity["percentage"] != 100:
        blockers.append(
            _safe_blocker(
                "PARITY_NOT_100_PERCENT",
                reason="all identity/count/state/host/membership/plan/contentRefs/outcome dimensions must match",
            )
        )
    quarantined_count = sum(
        1 for record in mapping.records if record["disposition"] == "quarantined"
    )
    gate_blocked = bool(blockers) or quarantined_count > 0
    if phase == "parity" and parity["percentage"] != 100:
        gate_blocked = True
    cutover, rollback = _availability_sections()
    source = snapshot["source"]
    stable = {
        "schema": RECEIPT_SCHEMA,
        "migrationId": MIGRATION_ID,
        "command": COMMAND_NAME,
        "environment": environment,
        "phase": phase,
        "status": "GATE_BLOCK" if gate_blocked else "passed",
        "executionMode": "read_only"
        if phase in {"inventory", "parity"}
        else "zero_write",
        "source": {
            "service": source["service"],
            "releaseId": source["releaseId"],
            "serviceImageDigest": source["serviceImageDigest"],
            "configDigest": source["configDigest"],
            "snapshotDigest": snapshot["snapshotDigest"],
            "capturedAt": snapshot["capturedAt"],
        },
        "target": {
            "services": [
                "chat-service",
                "circle-service",
                "content-service",
            ],
            "objectIds": list(target_contract.object_ids),
            "generatedContractDigest": target_contract.digest,
            "contractGraphDigest": target_contract.graph_digest,
            "generatedArtifactDigest": target_contract.generated_artifact_digest,
            "contractSources": list(target_contract.sources),
            "snapshotDigest": (
                target_snapshot.get("snapshotDigest")
                if isinstance(target_snapshot, dict)
                else ""
            ),
        },
        "crosswalkDigest": canonical_digest(crosswalk),
        "inventory": inventory,
        "mapping": {
            "recordCount": len(mapping.records),
            "records": list(mapping.records),
            "targetDocumentCount": len(mapping.documents),
            "targetDocumentDigest": canonical_digest(mapping.documents),
            "targetDocumentsEmitted": False,
        },
        "dispositions": _disposition_summary(mapping.records),
        "conflicts": {
            "totalCount": sum(value["count"] for value in mapping.conflicts.values()),
            "categories": mapping.conflicts,
        },
        "blockers": list(_dedupe_blockers(blockers)),
        "piiRedaction": _pii_redaction_report(snapshot),
        "validation": mapping.validation,
        "parity": parity,
        "writeSet": [],
        "cutover": cutover,
        "rollback": rollback,
    }
    receipt = _seal_receipt(stable)
    validate_receipt(receipt)
    return receipt

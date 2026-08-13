"""外部签名运维证据与 target-only writeSet 校验（逐字来自原 ``control_plane.py``）。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.codec import (
    _load_object,
    _parse_timestamp,
    _require_digest,
    _require_nonblank,
    canonical_digest,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.constants import (
    CONTROL_PHASES,
    EVIDENCE_PHASES,
    MIGRATION_ID,
    OPERATIONAL_EVIDENCE_SCHEMA,
    REQUIRED_TARGET_OPERATION_IDS,
    SAFE_WRITE_PLANES,
    TARGET_WRITE_SERVICES,
    MigrationControlError,
    TargetContractBinding,
)


def _validate_control_write_set(
    write_set: Any,
    *,
    phase: str,
) -> list[dict[str, Any]]:
    if not isinstance(write_set, list):
        raise MigrationControlError(
            "WRITE_SET_INVALID",
            "writeSet must be a list",
        )
    normalized: list[dict[str, Any]] = []
    expected_fields = {
        "stepId",
        "plane",
        "service",
        "operation",
        "candidateDigest",
        "executionMode",
    }
    for index, value in enumerate(write_set):
        if not isinstance(value, dict) or set(value) != expected_fields:
            raise MigrationControlError(
                "WRITE_SET_INVALID",
                f"writeSet[{index}] fields are invalid",
            )
        plane = str(value.get("plane") or "")
        service = str(value.get("service") or "")
        operation = str(value.get("operation") or "")
        if plane not in SAFE_WRITE_PLANES:
            raise MigrationControlError(
                "DIRECT_TARGET_WRITE_FORBIDDEN",
                f"writeSet[{index}] plane {plane!r} is forbidden",
            )
        if service == "travel-service" or "source" in plane:
            raise MigrationControlError(
                "SOURCE_WRITE_FORBIDDEN",
                "travel source writes and source write recovery are forbidden",
            )
        if service not in TARGET_WRITE_SERVICES:
            raise MigrationControlError(
                "DIRECT_TARGET_WRITE_FORBIDDEN",
                f"writeSet[{index}] service {service!r} is not a target owner",
            )
        lowered = f"{plane} {service} {operation}".lower()
        if any(
            token in lowered
            for token in (
                "database",
                "direct_db",
                "mongo",
                "projection_write",
                "raw_sql",
                "dual_write",
            )
        ):
            raise MigrationControlError(
                "DIRECT_TARGET_WRITE_FORBIDDEN",
                "direct target database/projection and dual writes are forbidden",
            )
        _require_nonblank(value.get("stepId"), label=f"writeSet[{index}].stepId")
        _require_nonblank(service, label=f"writeSet[{index}].service")
        _require_nonblank(operation, label=f"writeSet[{index}].operation")
        _require_digest(
            value.get("candidateDigest"),
            label=f"writeSet[{index}].candidateDigest",
        )
        execution_mode = str(value.get("executionMode") or "")
        if execution_mode not in {
            "external_approval_only",
            "externally_executed",
        }:
            raise MigrationControlError(
                "WRITE_SET_INVALID",
                f"writeSet[{index}].executionMode is invalid",
            )
        normalized.append(dict(value))
    if phase in EVIDENCE_PHASES and normalized:
        raise MigrationControlError(
            "WRITE_SET_INVALID",
            f"{phase} receipts may not contain environment writes",
        )
    if phase in CONTROL_PHASES and not normalized:
        raise MigrationControlError(
            "WRITE_SET_INVALID",
            f"{phase} receipt must declare its target-only writeSet",
        )
    return normalized


def _validate_external_evidence_write_set(
    evidence: Mapping[str, Any],
    *,
    target_contract: TargetContractBinding,
) -> None:
    evidence_type = str(evidence.get("evidenceType") or "")
    write_set = evidence.get("writeSet")
    if not isinstance(write_set, list):
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type}.writeSet must be a list",
        )
    if evidence_type not in {
        "target_command_import",
        "target_config_activation",
        "target_restore",
    }:
        if write_set:
            raise MigrationControlError(
                "EXTERNAL_EVIDENCE_INVALID",
                f"{evidence_type} evidence may not declare writes",
            )
        return
    if not write_set:
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type} evidence must declare its externally executed writeSet",
        )
    canonical_objects = set(target_contract.object_ids)
    for index, value in enumerate(write_set):
        if not isinstance(value, dict):
            raise MigrationControlError(
                "EXTERNAL_EVIDENCE_INVALID",
                f"{evidence_type}.writeSet[{index}] must be an object",
            )
        plane = str(value.get("plane") or "")
        service = str(value.get("service") or "")
        operation_id = str(value.get("operationId") or "")
        target_object_id = str(value.get("targetObjectId") or "")
        lowered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).lower()
        if service == "travel-service" or plane.startswith("source"):
            raise MigrationControlError(
                "SOURCE_WRITE_FORBIDDEN",
                "external evidence contains a travel source write",
            )
        if service not in TARGET_WRITE_SERVICES:
            raise MigrationControlError(
                "DIRECT_TARGET_WRITE_FORBIDDEN",
                f"external write service {service!r} is not a target owner",
            )
        if any(
            token in lowered
            for token in (
                "database",
                "direct_db",
                "mongo",
                "projection_write",
                "raw_sql",
                "dual_write",
            )
        ):
            raise MigrationControlError(
                "DIRECT_TARGET_WRITE_FORBIDDEN",
                "external evidence contains direct database/projection or dual write",
            )
        if evidence_type == "target_command_import":
            if plane not in {"target_command", "target_import"}:
                raise MigrationControlError(
                    "DIRECT_TARGET_WRITE_FORBIDDEN",
                    "target data may only be applied through canonical command/import",
                )
            if target_object_id not in canonical_objects:
                raise MigrationControlError(
                    "NON_CANONICAL_TARGET_KIND",
                    f"external target kind {target_object_id!r} is not canonical",
                )
            expected_service = {
                "chat": "chat-service",
                "circle": "circle-service",
                "content": "content-service",
            }.get(target_object_id.partition(".")[0])
            if service != expected_service:
                raise MigrationControlError(
                    "NON_CANONICAL_TARGET_OPERATION",
                    "external target service does not own targetObjectId",
                )
            if plane == "target_command" and operation_id not in set(
                REQUIRED_TARGET_OPERATION_IDS
            ):
                raise MigrationControlError(
                    "NON_CANONICAL_TARGET_OPERATION",
                    f"external target operation {operation_id!r} is not canonical",
                )
        elif evidence_type == "target_config_activation":
            if plane != "target_config" or target_object_id not in canonical_objects:
                raise MigrationControlError(
                    "CONFIG_ACTIVATION_WRITE_SET_MISMATCH",
                    "config activation evidence must target canonical target config",
                )
        else:
            if plane not in SAFE_WRITE_PLANES:
                raise MigrationControlError(
                    "DIRECT_TARGET_WRITE_FORBIDDEN",
                    "rollback restore may only target app/config/snapshot planes",
                )
            if target_object_id and target_object_id not in canonical_objects:
                raise MigrationControlError(
                    "NON_CANONICAL_TARGET_KIND",
                    f"rollback target kind {target_object_id!r} is not canonical",
                )
        _require_nonblank(service, label=f"{evidence_type}.writeSet[{index}].service")
        _require_nonblank(
            operation_id,
            label=f"{evidence_type}.writeSet[{index}].operationId",
        )
        _require_digest(
            value.get("commandReceiptDigest"),
            label=f"{evidence_type}.writeSet[{index}].commandReceiptDigest",
        )


def _load_operational_evidence(
    path: Path,
    *,
    environment: str,
    evidence_type: str,
    expected_digests: Mapping[str, str],
    target_contract: TargetContractBinding,
) -> dict[str, Any]:
    evidence = _load_object(path, label=f"{evidence_type} operational evidence")
    required = {
        "schema",
        "migrationId",
        "environment",
        "evidenceType",
        "status",
        "issuedAt",
        "subjectDigests",
        "writeSet",
        "claims",
        "signature",
        "evidenceDigest",
    }
    if set(evidence) != required:
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type} evidence fields are invalid",
        )
    if (
        evidence.get("schema") != OPERATIONAL_EVIDENCE_SCHEMA
        or evidence.get("migrationId") != MIGRATION_ID
        or evidence.get("environment") != environment
        or evidence.get("evidenceType") != evidence_type
        or evidence.get("status") != "passed"
    ):
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type} evidence identity/status is invalid",
        )
    _parse_timestamp(evidence.get("issuedAt"), label=f"{evidence_type}.issuedAt")
    subject_digests = evidence.get("subjectDigests")
    if not isinstance(subject_digests, dict):
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type}.subjectDigests must be an object",
        )
    for key, value in subject_digests.items():
        _require_digest(value, label=f"{evidence_type}.subjectDigests.{key}")
    for key, expected in expected_digests.items():
        if subject_digests.get(key) != expected:
            raise MigrationControlError(
                "EXTERNAL_EVIDENCE_DIGEST_MISMATCH",
                f"{evidence_type} evidence digest mismatch: {key}",
            )
    signature = evidence.get("signature")
    if not isinstance(signature, dict) or set(signature) != {
        "algorithm",
        "keyId",
        "signatureDigest",
        "verificationReceiptDigest",
    }:
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type}.signature is invalid",
        )
    if signature.get("algorithm") not in {
        "ed25519",
        "ecdsa_p256_sha256",
        "rsa_pss_sha256",
    }:
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type}.signature algorithm is invalid",
        )
    _require_nonblank(signature.get("keyId"), label=f"{evidence_type}.signature.keyId")
    _require_digest(
        signature.get("signatureDigest"),
        label=f"{evidence_type}.signature.signatureDigest",
    )
    _require_digest(
        signature.get("verificationReceiptDigest"),
        label=f"{evidence_type}.signature.verificationReceiptDigest",
    )
    expected_evidence_digest = canonical_digest(
        {key: value for key, value in evidence.items() if key != "evidenceDigest"}
    )
    if evidence.get("evidenceDigest") != expected_evidence_digest:
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_DIGEST_MISMATCH",
            f"{evidence_type} canonical evidence digest mismatch",
        )
    claims = evidence.get("claims")
    if not isinstance(claims, dict):
        raise MigrationControlError(
            "EXTERNAL_EVIDENCE_INVALID",
            f"{evidence_type}.claims must be an object",
        )
    required_claims: dict[str, Any] = {
        "target_backup": {
            "backupScope": "target_only",
            "restorable": True,
        },
        "source_write_freeze": {
            "sourceWriteState": "frozen_permanently",
            "sourceWriteRecoveryAllowed": False,
            "dualWriteEnabled": False,
        },
        "target_command_import": {
            "executionPath": {"canonical_commands", "canonical_importer"},
            "directDatabaseWrite": False,
            "derivedProjectionWrite": False,
            "sourceWrite": False,
        },
        "protected_environment_approval": {
            "decision": "approved",
            "protectedEnvironmentWritesApproved": True,
        },
        "target_config_activation": {
            "targetActivated": True,
            "sourceRuntimeDecommissioned": True,
            "sourceTrafficMode": "disabled",
            "sourceFallbackEnabled": False,
            "sourceWriteRecoveryAllowed": False,
        },
        "target_restore": {
            "targetRestored": True,
            "sourceWrite": False,
            "directDatabaseWrite": False,
            "derivedProjectionWrite": False,
        },
    }[evidence_type]
    for key, expected in required_claims.items():
        actual = claims.get(key)
        if isinstance(expected, set):
            matched = actual in expected
        else:
            matched = actual == expected
        if not matched:
            raise MigrationControlError(
                "EXTERNAL_EVIDENCE_INVALID",
                f"{evidence_type} claim is invalid: {key}",
            )
    _validate_external_evidence_write_set(
        evidence,
        target_contract=target_contract,
    )
    return evidence


def _evidence_ref(evidence: Mapping[str, Any]) -> dict[str, Any]:
    signature = evidence["signature"]
    return {
        "evidenceType": evidence["evidenceType"],
        "evidenceDigest": evidence["evidenceDigest"],
        "issuedAt": evidence["issuedAt"],
        "signatureDigest": signature["signatureDigest"],
        "verificationReceiptDigest": signature["verificationReceiptDigest"],
        "writeSetDigest": canonical_digest(evidence["writeSet"]),
    }

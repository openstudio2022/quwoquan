"""发布证据校验：hosted 基线回执、兼容窗口与 quiesced 存储迁移计划。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .primitives import (
    HOSTED_AUTHORITY,
    HOSTED_READBACK_SCHEMA,
    HOSTED_RECEIPT_SCHEMA,
    InputError,
    MIGRATION_SCHEMA,
    RECEIPT_ID_RE,
    SHA256_RE,
    WINDOW_SCHEMA,
    _digest_value,
    _file_digest,
    _list,
    _mapping,
    _read_json,
    _receipt_id,
)
from .graph_view import _index_records


def _validate_baseline_receipt(
    readback: Mapping[str, Any], baseline_graph_digest: str
) -> dict[str, Any]:
    if readback.get("schema") != HOSTED_READBACK_SCHEMA:
        raise InputError(
            f"baseline receipt must be {HOSTED_READBACK_SCHEMA}; arbitrary local receipts are forbidden"
        )
    if readback.get("authority") != HOSTED_AUTHORITY:
        raise InputError("baseline receipt readback authority is invalid")
    receipt = _mapping(readback.get("receipt"), "baselineReceipt.receipt")
    if receipt.get("schema") != HOSTED_RECEIPT_SCHEMA:
        raise InputError("baseline hosted receipt schema is invalid")
    if receipt.get("authority") != HOSTED_AUTHORITY:
        raise InputError("baseline hosted receipt authority is invalid")
    if str(receipt.get("stage")) not in {"full", "100"}:
        raise InputError("baseline hosted receipt must be a Prod full/100 stage")
    if str(receipt.get("triggerStage")) not in {"full", "100"}:
        raise InputError("baseline hosted receipt triggerStage must be full/100")
    if receipt.get("decision") != "continue" or receipt.get("rollbackOutcome") != "not_triggered":
        raise InputError("baseline hosted receipt must be a successful non-rollback decision")
    receipt_id = receipt.get("receiptId")
    if not isinstance(receipt_id, str) or RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        raise InputError("baseline hosted receiptId is invalid")
    if _receipt_id(receipt) != receipt_id:
        raise InputError("baseline hosted receiptId does not match immutable bytes")
    if readback.get("receiptRef") != f"receipt:hosted:{receipt_id}":
        raise InputError("baseline hosted receiptRef does not match receiptId")
    if _digest_value(receipt.get("contractGraphDigest"), "contractGraphDigest") != baseline_graph_digest:
        raise InputError("baseline ContractGraph bytes do not match hosted receipt digest")
    return dict(receipt)


def _load_window(
    path: Path | None, baseline_digest: str
) -> tuple[dict[str, dict[str, Any]], str | None]:
    if path is None:
        return {}, None
    document = _read_json(path)
    if document.get("schema") != WINDOW_SCHEMA:
        raise InputError(f"compatibility window schema must be {WINDOW_SCHEMA}")
    if _digest_value(document.get("baselineContractGraphDigest"), "baselineContractGraphDigest") != baseline_digest:
        raise InputError("compatibility window is stale for the baseline ContractGraph")
    minimum_builds = _mapping(document.get("minimumSupportedBuilds"), "minimumSupportedBuilds")
    if not minimum_builds or any(
        not isinstance(platform, str)
        or not isinstance(build, int)
        or isinstance(build, bool)
        or build < 1
        for platform, build in minimum_builds.items()
    ):
        raise InputError("minimumSupportedBuilds must contain positive integer platform builds")
    operations = _index_records(
        _list(document.get("operations"), "compatibilityWindow.operations"),
        "operationId",
        "compatibilityWindow.operations",
    )
    expected_platforms = set(minimum_builds)
    for operation_id, operation in operations.items():
        if not isinstance(operation.get("windowClosed"), bool):
            raise InputError(
                f"compatibilityWindow.operations[{operation_id}].windowClosed must be boolean"
            )
        usage_count = operation.get("usageCount")
        if (
            not isinstance(usage_count, int)
            or isinstance(usage_count, bool)
            or usage_count < 0
        ):
            raise InputError(
                f"compatibilityWindow.operations[{operation_id}].usageCount must be non-negative integer"
            )
        affected = _mapping(
            operation.get("affectedAppBuilds"),
            f"compatibilityWindow.operations[{operation_id}].affectedAppBuilds",
        )
        if set(affected) != expected_platforms:
            raise InputError(
                f"compatibilityWindow.operations[{operation_id}].affectedAppBuilds must cover exactly {sorted(expected_platforms)}"
            )
        for platform, builds in affected.items():
            if (
                not isinstance(builds, list)
                or any(
                    not isinstance(build, int)
                    or isinstance(build, bool)
                    or build < 1
                    for build in builds
                )
                or len(builds) != len(set(builds))
            ):
                raise InputError(
                    f"compatibilityWindow.operations[{operation_id}].affectedAppBuilds.{platform} must contain unique positive builds"
                )
    return operations, _file_digest(path)


def _load_migration_plan(
    path: Path | None, current_digest: str
) -> tuple[dict[str, dict[str, Any]], str | None]:
    if path is None:
        return {}, None
    document = _read_json(path)
    if document.get("schema") != MIGRATION_SCHEMA:
        raise InputError(f"storage migration schema must be {MIGRATION_SCHEMA}")
    if _digest_value(document.get("currentContractGraphDigest"), "currentContractGraphDigest") != current_digest:
        raise InputError("storage migration plan is stale for the current ContractGraph")
    objects = _index_records(
        _list(document.get("objects"), "storageMigration.objects"),
        "objectId",
        "storageMigration.objects",
    )
    return objects, _file_digest(path)


def _window_closed(
    operation_id: str,
    window: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, dict[str, Any]]:
    evidence = window.get(operation_id)
    if evidence is None:
        return False, {"operationId": operation_id, "reason": "evidence_missing"}
    usage_count = evidence.get("usageCount")
    affected = evidence.get("affectedAppBuilds")
    builds_empty = isinstance(affected, dict) and all(
        isinstance(values, list) and not values for values in affected.values()
    )
    closed = (
        evidence.get("windowClosed") is True
        and isinstance(usage_count, int)
        and not isinstance(usage_count, bool)
        and usage_count == 0
        and builds_empty
    )
    return closed, {
        "operationId": operation_id,
        "windowClosed": evidence.get("windowClosed") is True,
        "usageCount": usage_count,
        "affectedAppBuilds": affected,
    }


def _migration_valid(
    object_id: str,
    plans: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, str]:
    plan = plans.get(object_id)
    if plan is None:
        return False, "migration_plan_missing"
    required_true = (
        "commandsPaused",
        "backupVerified",
        "validationVerified",
        "atomicCutover",
        "singleReaderWriter",
    )
    if plan.get("mode") != "quiesced_atomic":
        return False, "migration_mode_must_be_quiesced_atomic"
    if any(plan.get(field_name) is not True for field_name in required_true):
        return False, "migration_quiescence_or_verification_missing"
    if plan.get("dualRead") is not False or plan.get("dualWrite") is not False:
        return False, "dual_read_or_dual_write_forbidden"
    for field_name in ("backupDigest", "validationDigest"):
        value = plan.get(field_name)
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            return False, f"{field_name}_invalid"
    return True, "validated"

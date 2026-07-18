"""Apply and rollback lifecycle for an audited canonical object transaction."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from core.tree_integrity import tree_integrity_stats
from content.release.canonical.object_transaction_contract import (
    APPLY_SCHEMA,
    LAYOUT_SCHEMA,
    ROLLBACK_SCHEMA,
    ObjectTransactionError,
    _now,
    _read_json,
    _safe_id,
    _verify_package,
    _write_json,
)


def apply_object_transaction(
    *,
    publish_root: Path,
    output_root: Path,
    package_root: Path,
    transaction_id: str,
    dry_run_attestation_sha256: str,
) -> dict[str, Any]:
    """Atomically replace canonical publish only after the immutable audit attestation."""
    from content.release.canonical.object_transaction_audit import (
        _transaction_root,
        _verify_attestation,
        validate_canonical_publish,
    )

    transaction_id = _safe_id(transaction_id, label="transactionId")
    run_root = _transaction_root(output_root, transaction_id)
    report_path, apply_path = run_root / "audit_report.json", run_root / "apply_report.json"
    if apply_path.is_file():
        applied = _read_json(apply_path)
        if applied.get("schema") == APPLY_SCHEMA and tree_integrity_stats(publish_root)["merkleRoot"] == applied.get("afterMerkle"):
            return {**applied, "idempotent": True}
        raise ObjectTransactionError("已有 apply 记录但 canonical 已漂移")
    if not report_path.is_file():
        raise ObjectTransactionError("apply 前必须完成 audit")
    report = _read_json(report_path)
    _verify_attestation(report, dry_run_attestation_sha256)
    if report.get("transactionId") != transaction_id or report.get("targetLayout") != LAYOUT_SCHEMA:
        raise ObjectTransactionError("audit transaction/layout binding 不匹配")
    before = tree_integrity_stats(publish_root)
    if before["merkleRoot"] != report.get("beforeCanonical", {}).get("merkleRoot"):
        raise ObjectTransactionError("audit 后 canonical 已变化")
    package = _verify_package(
        package_root,
        canonical_root=publish_root,
        require_target_absent=True,
    )
    if any(package[key] != report.get(key) for key in ("packageSha256", "objectClosureDigest", "executionId")):
        raise ObjectTransactionError("对象包在 audit 后发生变化")
    staging = run_root / "staging/canonical"
    if not staging.is_dir() or tree_integrity_stats(staging)["merkleRoot"] != report.get("afterCanonical", {}).get("merkleRoot"):
        raise ObjectTransactionError("staging canonical digest mismatch")
    rollback = run_root / "rollback/canonical_before"
    if rollback.exists():
        raise ObjectTransactionError(f"rollback snapshot 已存在：{rollback}")
    run_root.mkdir(parents=True, exist_ok=True)
    lock = run_root / ".apply.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ObjectTransactionError("object transaction 正在执行") from exc
    os.close(fd)
    try:
        rollback.parent.mkdir(parents=True, exist_ok=True)
        os.replace(publish_root, rollback)
        try:
            os.replace(staging, publish_root)
        except BaseException:
            os.replace(rollback, publish_root)
            raise
        try:
            closure, actual_after = validate_canonical_publish(publish_root), tree_integrity_stats(publish_root)
            if closure["status"] != "passed" or actual_after["merkleRoot"] != report["afterCanonical"]["merkleRoot"]:
                raise ObjectTransactionError("post-apply canonical proof 失败")
        except BaseException:
            failed = run_root / "rollback/failed_after"
            if publish_root.exists():
                os.replace(publish_root, failed)
            shutil.copytree(rollback, publish_root)
            raise
    finally:
        lock.unlink(missing_ok=True)
    applied = {
        "schema": APPLY_SCHEMA,
        "transactionId": transaction_id,
        "executionId": report["executionId"],
        "status": "applied",
        "appliedAt": _now(),
        "beforeMerkle": report["beforeCanonical"]["merkleRoot"],
        "afterMerkle": report["afterCanonical"]["merkleRoot"],
        "objectKind": report["objectKind"],
        "objectRef": report["objectRef"],
        "objectClosureDigest": report["objectClosureDigest"],
        "dryRunAttestationSha256": dry_run_attestation_sha256,
        "rollbackRef": str(rollback),
        "idempotent": False,
    }
    _write_json(apply_path, applied)
    return applied


def rollback_object_transaction(*, publish_root: Path, output_root: Path, transaction_id: str) -> dict[str, Any]:
    """Restore the exact immutable pre-apply snapshot, preserving audit evidence."""
    from content.release.canonical.object_transaction_audit import _transaction_root

    transaction_id = _safe_id(transaction_id, label="transactionId")
    run_root = _transaction_root(output_root, transaction_id)
    apply_report = _read_json(run_root / "apply_report.json")
    if apply_report.get("schema") != APPLY_SCHEMA:
        raise ObjectTransactionError("apply report schema 不匹配")
    rollback = Path(str(apply_report.get("rollbackRef") or ""))
    if not rollback.is_dir():
        raise ObjectTransactionError("immutable rollback snapshot 不存在")
    report_path = run_root / "rollback_report.json"
    if report_path.is_file():
        persisted = _read_json(report_path)
        if tree_integrity_stats(publish_root)["merkleRoot"] == persisted.get("restoredMerkle"):
            return {**persisted, "idempotent": True}
        raise ObjectTransactionError("已有 rollback 记录但 canonical 已漂移")
    if tree_integrity_stats(publish_root)["merkleRoot"] != apply_report.get("afterMerkle"):
        raise ObjectTransactionError("rollback 前 canonical Merkle 已漂移")
    restore_staging = run_root / "rollback/restore_staging"
    if restore_staging.exists():
        raise ObjectTransactionError("stale rollback restore staging")
    shutil.copytree(rollback, restore_staging)
    displaced = run_root / "rollback/displaced_after_transaction"
    if displaced.exists():
        raise ObjectTransactionError("rollback displaced snapshot 已存在")
    os.replace(publish_root, displaced)
    try:
        os.replace(restore_staging, publish_root)
    except BaseException:
        os.replace(displaced, publish_root)
        raise
    restored = tree_integrity_stats(publish_root)
    if restored["merkleRoot"] != apply_report.get("beforeMerkle"):
        failed = run_root / "rollback/failed_restore"
        os.replace(publish_root, failed)
        os.replace(displaced, publish_root)
        raise ObjectTransactionError("rollback restore Merkle 不匹配")
    result = {
        "schema": ROLLBACK_SCHEMA,
        "transactionId": transaction_id,
        "status": "rolled_back",
        "rolledBackAt": _now(),
        "restoredMerkle": restored["merkleRoot"],
        "rollbackRefPreserved": str(rollback),
        "displacedCanonicalRef": str(displaced),
        "idempotent": False,
    }
    _write_json(report_path, result)
    return result

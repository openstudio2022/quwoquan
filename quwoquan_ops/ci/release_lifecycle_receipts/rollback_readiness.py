"""Prod rollback readiness（release-rollback-receipt, ready）的封版逻辑。

原单文件 ``render_release_lifecycle_receipts.py`` 拆分出的回滚就绪子模块。
``validate_manifest`` 为被测试 monkeypatch 的薄入口模块属性，消费点经
``_pkg.`` 访问。
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import quwoquan_ops.ci.render_release_lifecycle_receipts as _pkg
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import DIGEST_PATTERN

from .hosted_readback import _validate_ledger_readback, _validate_receipt_readback
from .receipt_codec import (
    _canonical_receipt,
    _digest_file,
    _utc_now,
    _validate_archive_prefix,
    _validate_timestamp,
)


def render_rollback_readiness(
    *,
    manifest: dict[str, Any],
    service: str,
    from_candidate_digest: str,
    current_ledger_path: Path,
    current_ledger: dict[str, Any],
    rollback_drill_path: Path,
    rollback_drill: dict[str, Any],
    backup_validation_path: Path,
    backup_validation: dict[str, Any],
    archive_prefix: str,
    rollback_drill_max_age_seconds: int,
) -> dict[str, Any]:
    _pkg.validate_manifest(manifest, allowed_statuses={"qualified"})
    if set(manifest.get("environmentReceipts") or {}) != {
        "alpha",
        "beta",
        "gamma",
    }:
        raise ValueError("rollback readiness requires exact Alpha/Beta/Gamma receipts")
    if DIGEST_PATTERN.fullmatch(from_candidate_digest) is None:
        raise ValueError("from candidate digest is invalid")

    current = _validate_ledger_readback(current_ledger, service=service)
    stable_current = (
        current.get("stage") == "100"
        and current.get("lastGoodCandidateDigest") == from_candidate_digest
        and current.get("toCandidateDigest") == from_candidate_digest
        and (
            (
                current.get("decision") == "continue"
                and current.get("rollbackOutcome") == "not_triggered"
            )
            or (
                current.get("decision") == "rolled_back"
                and current.get("rollbackOutcome") == "rolled_back"
            )
        )
    )
    if not stable_current:
        raise ValueError("hosted ledger does not prove the requested stable from candidate")

    drill = _validate_receipt_readback(rollback_drill, service=service)
    if not (
        drill.get("stage") == "100"
        and drill.get("decision") == "rolled_back"
        and drill.get("rollbackOutcome") == "rolled_back"
        and drill.get("lastGoodCandidateDigest") == drill.get("toCandidateDigest")
        and drill.get("toCandidateDigest") == from_candidate_digest
    ):
        raise ValueError(
            "hosted rollback drill receipt does not recover the current stable candidate"
        )
    if rollback_drill_max_age_seconds <= 0:
        raise ValueError("rollback drill freshness policy is invalid")
    drill_verified = dt.datetime.fromisoformat(
        _validate_timestamp(drill.get("verifiedAt"), "rollback drill").replace(
            "Z", "+00:00"
        )
    )
    drill_age_seconds = int(
        (dt.datetime.now(dt.timezone.utc) - drill_verified).total_seconds()
    )
    if drill_age_seconds < -300 or drill_age_seconds > rollback_drill_max_age_seconds:
        raise ValueError("hosted rollback drill receipt is outside the freshness policy")

    if (
        set(backup_validation)
        != {"schema", "status", "planDigest", "receiptDigest", "issues"}
        or backup_validation.get("schema")
        != "quwoquan-prod-backup-recovery-validation"
        or backup_validation.get("status") != "ok"
        or backup_validation.get("issues") != []
        or DIGEST_PATTERN.fullmatch(str(backup_validation.get("planDigest") or ""))
        is None
        or DIGEST_PATTERN.fullmatch(
            str(backup_validation.get("receiptDigest") or "")
        )
        is None
    ):
        raise ValueError("backup recovery validation is not passed and immutable")

    normalized_prefix = _validate_archive_prefix(archive_prefix)
    evidence = {
        "releaseCompositionId": manifest["releaseCompositionId"],
        "fromCandidateDigest": from_candidate_digest,
        "hostedLedger": {
            "receiptId": current["receiptId"],
            "path": f"{normalized_prefix}/current-ledger.json",
            "digest": _digest_file(current_ledger_path),
        },
        "rollbackDrill": {
            "receiptId": drill["receiptId"],
            "path": f"{normalized_prefix}/rollback-drill.json",
            "digest": _digest_file(rollback_drill_path),
            "ageSeconds": max(0, drill_age_seconds),
            "maximumAgeSeconds": rollback_drill_max_age_seconds,
        },
        "backupRecovery": {
            "planDigest": backup_validation["planDigest"],
            "receiptDigest": backup_validation["receiptDigest"],
            "path": f"{normalized_prefix}/backup-validation.json",
            "digest": _digest_file(backup_validation_path),
        },
    }
    return _canonical_receipt(
        schema="release-rollback-receipt",
        status="ready",
        manifest=manifest,
        evidence_projection=evidence,
        verified_at=_utc_now(),
    )

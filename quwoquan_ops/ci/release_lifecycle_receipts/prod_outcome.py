"""Prod 分阶段放量结局（environment/rollout/rollback receipt）的封版逻辑。

原单文件 ``render_release_lifecycle_receipts.py`` 拆分出的放量结局子模块。
``validate_manifest`` 为被测试 monkeypatch 的薄入口模块属性，消费点经
``_pkg.`` 访问。
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import quwoquan_ops.ci.render_release_lifecycle_receipts as _pkg
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import DIGEST_PATTERN

from .constants import HOSTED_AUTHORITY, STAGES
from .hosted_readback import _validate_receipt_readback
from .receipt_codec import (
    _canonical_receipt,
    _digest_file,
    _validate_archive_prefix,
    _validate_timestamp,
)


def render_prod_outcome(
    *,
    manifest: dict[str, Any],
    service: str,
    from_candidate_digest: str,
    reports: dict[str, tuple[Path, dict[str, Any]]],
    readbacks: dict[str, tuple[Path, dict[str, Any]]],
    archive_prefix: str,
    hard_deadline_epoch: int,
    rollback_budget_seconds: int,
) -> dict[str, dict[str, Any]]:
    _pkg.validate_manifest(manifest, allowed_statuses={"main-admitted"})
    if DIGEST_PATTERN.fullmatch(from_candidate_digest) is None:
        raise ValueError("from candidate digest is invalid")
    if not reports or set(reports) != set(readbacks):
        raise ValueError("Prod stage reports and hosted readbacks must be paired")
    if hard_deadline_epoch <= 0 or rollback_budget_seconds <= 0:
        raise ValueError("Prod release deadline policy is invalid")
    ordered = [stage for stage in STAGES if stage in reports]
    if ordered != list(STAGES[: len(ordered)]):
        raise ValueError("Prod stage evidence must be a contiguous rollout prefix")

    normalized_prefix = _validate_archive_prefix(archive_prefix)
    candidate = str(manifest["releaseCompositionId"])
    artifact = str(manifest["artifactDigest"])
    evidence_files: dict[str, dict[str, str]] = {}
    receipts: list[dict[str, Any]] = []
    for index, stage in enumerate(ordered):
        report_path, report = reports[stage]
        readback_path, readback = readbacks[stage]
        receipt = _validate_receipt_readback(readback, service=service)
        if (
            report.get("command") != "deploy"
            or report.get("target") != "prod-hosted"
            or report.get("rolloutStage") != stage
            or report.get("triggerStage") != stage
            or report.get("terminalStage") != receipt.get("stage")
            or report.get("dryRun") is not False
            or report.get("releaseCompositionId") != candidate
            or report.get("artifactDigest") != artifact
            or report.get("releaseReceiptId") != receipt["receiptId"]
            or report.get("releaseReceiptRef")
            != f"receipt:hosted:{receipt['receiptId']}"
            or report.get("releaseReceiptAuthority") != HOSTED_AUTHORITY
            or receipt.get("artifactDigest") != artifact
            or receipt.get("triggerStage") != stage
        ):
            raise ValueError(f"Prod {stage} report and hosted receipt binding is invalid")
        if index < len(ordered) - 1 and not (
            report.get("exitCode") == 0
            and report.get("rolloutDecision") == "continue"
            and receipt.get("decision") == "continue"
            and receipt.get("rollbackOutcome") == "not_triggered"
            and receipt.get("fromCandidateDigest") == from_candidate_digest
            and receipt.get("toCandidateDigest") == candidate
        ):
            raise ValueError(f"Prod {stage} did not complete before the next stage")
        evidence_files[stage] = {
            "report": {
                "path": f"{normalized_prefix}/{stage}-report.json",
                "digest": _digest_file(report_path),
            },
            "readback": {
                "path": f"{normalized_prefix}/{stage}-readback.json",
                "digest": _digest_file(readback_path),
            },
            "receiptId": receipt["receiptId"],
        }
        receipts.append(receipt)

    final_stage = ordered[-1]
    final_report = reports[final_stage][1]
    final_receipt = receipts[-1]
    rollback_outcome = str(final_receipt.get("rollbackOutcome") or "")
    if rollback_outcome == "not_triggered":
        if not (
            ordered == list(STAGES)
            and final_stage == "100"
            and final_report.get("exitCode") == 0
            and final_report.get("rolloutDecision") == "continue"
            and final_receipt.get("decision") == "continue"
            and final_receipt.get("fromCandidateDigest") == from_candidate_digest
            and final_receipt.get("toCandidateDigest") == candidate
            and final_receipt.get("lastGoodCandidateDigest") == candidate
            and final_report.get("postDeployFailures") in (None, [])
            and (final_report.get("rollback") or {}).get("triggered") is False
        ):
            raise ValueError("Prod full rollout evidence is incomplete")
        environment_status = "passed"
        rollout_status = "passed"
        rollback_status = "not_triggered"
    elif rollback_outcome == "rolled_back":
        rollback_checks = final_report.get("rollbackPostChecks")
        if not (
            final_report.get("exitCode") != 0
            and (final_report.get("rollback") or {}).get("triggered") is True
            and final_receipt.get("decision") == "rolled_back"
            and final_receipt.get("fromCandidateDigest") == candidate
            and final_receipt.get("toCandidateDigest") == from_candidate_digest
            and final_receipt.get("lastGoodCandidateDigest") == from_candidate_digest
            and isinstance(rollback_checks, list)
            and bool(rollback_checks)
            and all(
                isinstance(check, dict) and check.get("exitCode") == 0
                for check in rollback_checks
            )
        ):
            raise ValueError("Prod rollback recovery evidence is incomplete")
        environment_status = "passed"
        rollout_status = "failed"
        rollback_status = "rolled_back"
    elif rollback_outcome == "rollback_failed":
        if not (
            final_report.get("exitCode") != 0
            and (final_report.get("rollback") or {}).get("triggered") is True
            and final_receipt.get("decision") == "rollback_failed"
            and final_receipt.get("fromCandidateDigest") == from_candidate_digest
            and final_receipt.get("toCandidateDigest") == candidate
            and final_receipt.get("lastGoodCandidateDigest") == from_candidate_digest
        ):
            raise ValueError("Prod rollback failure evidence is incomplete")
        environment_status = "failed"
        rollout_status = "failed"
        rollback_status = "rollback_failed"
    else:
        raise ValueError("paused or unknown Prod outcome cannot seal release evidence")

    projection = {
        "releaseCompositionId": candidate,
        "fromCandidateDigest": from_candidate_digest,
        "outcome": rollback_status,
        "stages": evidence_files,
    }
    verified_at = _validate_timestamp(
        final_receipt.get("verifiedAt"), "final hosted receipt"
    )
    verified_epoch = dt.datetime.fromisoformat(
        verified_at.replace("Z", "+00:00")
    ).timestamp()
    if verified_epoch > hard_deadline_epoch:
        raise ValueError("Prod outcome completed after the 1800-second hard deadline")
    if rollback_outcome in {"rolled_back", "rollback_failed"}:
        rollback_timing = final_report.get("rollback")
        if not isinstance(rollback_timing, dict):
            raise ValueError("Prod rollback timing evidence is missing")
        rollback_duration_ms = rollback_timing.get("durationMs")
        rollback_started = rollback_timing.get("startedAt")
        rollback_ended = rollback_timing.get("endedAt")
        if (
            not isinstance(rollback_duration_ms, int)
            or rollback_duration_ms < 0
            or rollback_duration_ms > rollback_budget_seconds * 1000
            or not isinstance(rollback_started, str)
            or not isinstance(rollback_ended, str)
        ):
            raise ValueError("Prod rollback recovery exceeded the 300-second budget")
        rollback_end_epoch = dt.datetime.fromisoformat(
            rollback_ended.replace("Z", "+00:00")
        ).timestamp()
        if rollback_end_epoch > hard_deadline_epoch:
            raise ValueError("Prod rollback recovery completed after the hard deadline")
    return {
        "environment": _canonical_receipt(
            schema="release-environment-receipt",
            status=environment_status,
            manifest=manifest,
            evidence_projection={**projection, "receiptKind": "environment"},
            verified_at=verified_at,
        ),
        "rollout": _canonical_receipt(
            schema="release-rollout-receipt",
            status=rollout_status,
            manifest=manifest,
            evidence_projection={**projection, "receiptKind": "rollout"},
            verified_at=verified_at,
        ),
        "rollback": _canonical_receipt(
            schema="release-rollback-receipt",
            status=rollback_status,
            manifest=manifest,
            evidence_projection={**projection, "receiptKind": "rollback"},
            verified_at=verified_at,
        ),
    }

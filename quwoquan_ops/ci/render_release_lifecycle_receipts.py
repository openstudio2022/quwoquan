#!/usr/bin/env python3
"""Render canonical Prod readiness and outcome receipts from hosted evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.prod import hosted_release_ledger
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    DIGEST_PATTERN,
    validate_manifest,
)

HOSTED_AUTHORITY = hosted_release_ledger.AUTHORITY
HOSTED_READBACK_SCHEMA = hosted_release_ledger.READBACK_SCHEMA
HOSTED_RECEIPT_READBACK_SCHEMA = hosted_release_ledger.RECEIPT_READBACK_SCHEMA
HOSTED_RECEIPT_SCHEMA = hosted_release_ledger.RECEIPT_SCHEMA
HOSTED_STATE_SCHEMA = hosted_release_ledger.STATE_SCHEMA
HOSTED_SOAK_REQUEST_SCHEMA = hosted_release_ledger.SOAK_REQUEST_SCHEMA
HOSTED_SOAK_RECEIPT_SCHEMA = hosted_release_ledger.SOAK_RECEIPT_SCHEMA
HOSTED_SOAK_READBACK_SCHEMA = hosted_release_ledger.SOAK_RECEIPT_READBACK_SCHEMA
STAGES = ("canary", "5", "20", "50", "100")
RECEIPT_ID_PATTERN = re.compile(r"[0-9a-f]{64}")
HOSTED_RECEIPT_FIELDS = hosted_release_ledger.RECEIPT_FIELDS
HOSTED_STATE_FIELDS = hosted_release_ledger.STATE_FIELDS


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _receipt_id(receipt: dict[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receiptId", None)
    return hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} timestamp is missing")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} timestamp has no timezone")
    return value


def _validate_hosted_receipt(value: Any, *, service: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != HOSTED_RECEIPT_FIELDS:
        raise ValueError("hosted release receipt shape is not canonical")
    receipt_id = str(value.get("receiptId") or "")
    if (
        value.get("schema") != HOSTED_RECEIPT_SCHEMA
        or value.get("authority") != HOSTED_AUTHORITY
        or value.get("service") != service
        or RECEIPT_ID_PATTERN.fullmatch(receipt_id) is None
        or _receipt_id(value) != receipt_id
    ):
        raise ValueError("hosted release receipt identity is invalid")
    for field in (
        "fromCandidateDigest",
        "toCandidateDigest",
        "artifactDigest",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
    ):
        if DIGEST_PATTERN.fullmatch(str(value.get(field) or "")) is None:
            raise ValueError(f"hosted release receipt {field} is not immutable")
    if value.get("stage") not in STAGES:
        raise ValueError("hosted release receipt stage is invalid")
    if value.get("triggerStage") not in STAGES:
        raise ValueError("hosted release receipt triggerStage is invalid")
    for field in ("fromReleaseEvidenceRef", "toReleaseEvidenceRef"):
        ref = str(value.get(field) or "")
        if re.fullmatch(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}", ref) is None:
            raise ValueError(f"hosted release receipt {field} is not exact OCI")
    for field in ("fromImageTransportTag", "toImageTransportTag"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ValueError(f"hosted release receipt {field} is missing")
    if value.get("decision") not in {
        "continue",
        "pause",
        "rolled_back",
        "rollback_failed",
    }:
        raise ValueError("hosted release receipt decision is invalid")
    if value.get("rollbackOutcome") not in {
        "not_triggered",
        "rolled_back",
        "rollback_failed",
    }:
        raise ValueError("hosted release receipt rollback outcome is invalid")
    if (
        not isinstance(value.get("expectedGeneration"), int)
        or not isinstance(value.get("committedGeneration"), int)
        or value["expectedGeneration"] < 0
        or value["committedGeneration"] != value["expectedGeneration"] + 1
        or not isinstance(value.get("sloReadback"), dict)
    ):
        raise ValueError("hosted release receipt generation or SLO evidence is invalid")
    if service == "prod-stack" and value.get("decision") == "continue":
        hosted_release_ledger.validate_promotion_evidence(
            value["sloReadback"].get("promotionEvidence"),
            candidate_id=value.get("toCandidateDigest"),
            artifact_digest=value.get("artifactDigest"),
            stage=value.get("triggerStage"),
        )
    post_checks = value.get("postChecks")
    if not isinstance(post_checks, list) or not all(
        isinstance(item, dict)
        and set(item) == {"name", "status", "receiptDigest"}
        and isinstance(item.get("name"), str)
        and bool(item["name"])
        and item.get("status") in {"passed", "failed"}
        and DIGEST_PATTERN.fullmatch(str(item.get("receiptDigest") or ""))
        is not None
        for item in post_checks
    ):
        raise ValueError("hosted release receipt post-check evidence is invalid")
    _validate_timestamp(value.get("verifiedAt"), "hosted release receipt")
    return value


def _validate_receipt_readback(
    payload: dict[str, Any], *, service: str
) -> dict[str, Any]:
    if (
        set(payload) != {"schema", "authority", "receipt", "receiptRef"}
        or payload.get("schema") != HOSTED_RECEIPT_READBACK_SCHEMA
        or payload.get("authority") != HOSTED_AUTHORITY
    ):
        raise ValueError("hosted receipt readback shape is invalid")
    receipt = _validate_hosted_receipt(payload.get("receipt"), service=service)
    if payload.get("receiptRef") != f"receipt:hosted:{receipt['receiptId']}":
        raise ValueError("hosted receipt readback reference is invalid")
    return receipt


def _validate_soak_readback(
    payload: dict[str, Any], *, service: str
) -> dict[str, Any]:
    if (
        set(payload) != {"schema", "authority", "receipt", "receiptRef"}
        or payload.get("schema") != HOSTED_SOAK_READBACK_SCHEMA
        or payload.get("authority") != HOSTED_AUTHORITY
    ):
        raise ValueError("hosted prod soak readback shape is invalid")
    receipt = payload.get("receipt")
    if (
        not isinstance(receipt, dict)
        or set(receipt) != hosted_release_ledger.SOAK_RECEIPT_FIELDS
        or receipt.get("schema") != HOSTED_SOAK_RECEIPT_SCHEMA
        or receipt.get("authority") != HOSTED_AUTHORITY
        or receipt.get("service") != service
        or RECEIPT_ID_PATTERN.fullmatch(str(receipt.get("receiptId") or "")) is None
        or _receipt_id(receipt) != receipt.get("receiptId")
        or payload.get("receiptRef")
        != f"receipt:hosted-soak:{receipt.get('receiptId')}"
    ):
        raise ValueError("hosted prod soak receipt identity is invalid")
    request = {
        field: receipt[field]
        for field in hosted_release_ledger.SOAK_REQUEST_FIELDS
        if field != "schema"
    }
    request["schema"] = hosted_release_ledger.SOAK_REQUEST_SCHEMA
    hosted_release_ledger._validate_soak_request(request)
    started_at = dt.datetime.fromisoformat(
        _validate_timestamp(receipt.get("soakStartedAt"), "prod soak start").replace(
            "Z", "+00:00"
        )
    )
    ended_at = dt.datetime.fromisoformat(
        _validate_timestamp(receipt.get("soakEndedAt"), "prod soak end").replace(
            "Z", "+00:00"
        )
    )
    verified_at = dt.datetime.fromisoformat(
        _validate_timestamp(receipt.get("verifiedAt"), "prod soak receipt").replace(
            "Z", "+00:00"
        )
    )
    duration = receipt.get("soakDurationSeconds")
    if (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration != int((ended_at - started_at).total_seconds())
        or duration < receipt["requiredSoakSeconds"]
        or ended_at > verified_at
    ):
        raise ValueError("hosted prod soak receipt duration is invalid")
    return receipt


def _validate_ledger_readback(
    payload: dict[str, Any], *, service: str
) -> dict[str, Any]:
    if (
        set(payload) != {"schema", "authority", "state", "receipt", "receiptRef"}
        or payload.get("schema") != HOSTED_READBACK_SCHEMA
        or payload.get("authority") != HOSTED_AUTHORITY
        or not isinstance(payload.get("state"), dict)
    ):
        raise ValueError("hosted ledger readback shape is invalid")
    state = payload["state"]
    receipt = _validate_hosted_receipt(payload.get("receipt"), service=service)
    history_is_invalid = any(
        not isinstance(state.get(field), str)
        or (
            bool(state.get(field))
            and RECEIPT_ID_PATTERN.fullmatch(str(state[field])) is None
        )
        for field in hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.values()
    )
    active_history_field = hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.get(
        str(state.get("trigger_stage") or "")
    )
    if (
        set(state) != HOSTED_STATE_FIELDS
        or state.get("schema") != HOSTED_STATE_SCHEMA
        or state.get("authority") != HOSTED_AUTHORITY
        or state.get("service") != service
        or state.get("receipt_id") != receipt["receiptId"]
        or payload.get("receiptRef") != f"receipt:hosted:{receipt['receiptId']}"
        or str(receipt["committedGeneration"]) != state.get("generation")
        or receipt["fromCandidateDigest"] != state.get("from_candidate_digest")
        or receipt["toCandidateDigest"] != state.get("to_candidate_digest")
        or receipt["artifactDigest"] != state.get("artifact_digest")
        or receipt["rollbackOutcome"] != state.get("rollback_outcome")
        or receipt["triggerStage"] != state.get("trigger_stage")
        or receipt["fromReleaseEvidenceRef"]
        != state.get("from_release_evidence_ref")
        or receipt["toReleaseEvidenceRef"] != state.get("to_release_evidence_ref")
        or receipt["fromImageTransportTag"]
        != state.get("from_image_transport_tag")
        or receipt["toImageTransportTag"] != state.get("to_image_transport_tag")
        or receipt["lastGoodCandidateDigest"]
        != state.get("last_good_candidate_digest")
        or history_is_invalid
        or active_history_field is None
        or state.get(active_history_field) != receipt["receiptId"]
    ):
        raise ValueError("hosted ledger state and receipt binding is invalid")
    return receipt


def _manifest_source(manifest: dict[str, Any]) -> tuple[str, str, str]:
    candidate = str(manifest["candidateId"])
    source = manifest["source"]
    return candidate, str(source["gitSha"]), str(source["treeDigest"])


def _canonical_receipt(
    *,
    schema: str,
    status: str,
    manifest: dict[str, Any],
    evidence_projection: dict[str, Any],
    verified_at: str,
) -> dict[str, Any]:
    candidate, git_sha, tree_digest = _manifest_source(manifest)
    return {
        "schema": schema,
        "environment": "prod",
        "status": status,
        "candidateId": candidate,
        "sourceGitSha": git_sha,
        "sourceTreeDigest": tree_digest,
        "evidenceDigest": _digest_bytes(_canonical_bytes(evidence_projection)),
        "evidence": evidence_projection,
        "verifiedAt": verified_at,
    }


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
    validate_manifest(manifest, allowed_statuses={"candidate-ready"})
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
        "candidateId": manifest["candidateId"],
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


def _parse_binding(values: list[str], label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for raw in values:
        stage, separator, path = raw.partition("=")
        if not separator or stage not in STAGES or not path:
            raise ValueError(f"{label} must use STAGE=PATH")
        if stage in result:
            raise ValueError(f"duplicate {label} stage: {stage}")
        result[stage] = Path(path).expanduser().resolve()
    return result


def _validate_archive_prefix(value: str) -> str:
    normalized = value.strip().strip("/")
    if (
        not normalized
        or normalized.startswith(".")
        or ".." in Path(normalized).parts
        or Path(normalized).is_absolute()
    ):
        raise ValueError("release evidence archive prefix is unsafe")
    return normalized


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
    validate_manifest(manifest, allowed_statuses={"deployable"})
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
    candidate = str(manifest["candidateId"])
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
            or report.get("candidateId") != candidate
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
        "candidateId": candidate,
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


def _window_seconds(value: object) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)([smh])", str(value or "").strip())
    if match is None:
        raise ValueError("SLO soak window is invalid")
    multiplier = {"s": 1, "m": 60, "h": 3600}[match.group(2)]
    return int(match.group(1)) * multiplier


def render_prod_soak_request(
    *,
    manifest: dict[str, Any],
    service: str,
    full_readback: dict[str, Any],
    slo: dict[str, Any],
    slo_path: Path,
    alerts: dict[str, Any],
    alerts_path: Path,
    health: dict[str, Any],
    health_path: Path,
    credential_evidence: dict[str, Any],
    credential_policy: dict[str, Any],
    credential_policy_path: Path,
    governance: dict[str, Any],
    governance_path: Path,
    soak_policy: dict[str, Any],
    soak_policy_path: Path,
) -> dict[str, Any]:
    validate_manifest(manifest, allowed_statuses={"released"})
    full = _validate_receipt_readback(full_readback, service=service)
    candidate = str(manifest["candidateId"])
    source = manifest["source"]
    if not (
        full.get("triggerStage") == "100"
        and full.get("stage") == "100"
        and full.get("decision") == "continue"
        and full.get("rollbackOutcome") == "not_triggered"
        and full.get("toCandidateDigest") == candidate
        and full.get("lastGoodCandidateDigest") == candidate
        and full.get("contractGraphDigest") == manifest["contractGraphDigest"]
    ):
        raise ValueError("full hosted rollout receipt is not a released candidate")

    readback = soak_policy.get("readback")
    thresholds = soak_policy.get("thresholds")
    if not isinstance(readback, dict) or not isinstance(thresholds, dict):
        raise ValueError("soak policy is invalid")
    required_soak_seconds = _window_seconds(
        readback.get("post_100_soak_window")
    )
    minimum_samples = int(readback.get("minimum_samples") or 0)
    if minimum_samples < 1:
        raise ValueError("soak policy requirements are invalid")

    slo_values = slo.get("values")
    if not (
        set(slo)
        >= {
            "source",
            "queriedAt",
            "window",
            "minimumSamples",
            "values",
        }
        and slo.get("source") == "prometheus"
        and _window_seconds(slo.get("window")) == required_soak_seconds
        and slo.get("minimumSamples") == minimum_samples
        and isinstance(slo_values, dict)
        and set(slo_values)
        >= {"errorRate", "p95Ms", "redisErrorRate", "sampleCount"}
    ):
        raise ValueError("Prometheus soak evidence shape or policy binding is invalid")
    sample_count = int(float(slo_values["sampleCount"]))
    if sample_count < minimum_samples:
        raise ValueError("Prometheus soak evidence has insufficient samples")
    threshold_bindings = {
        "errorRate": "error_rate",
        "p95Ms": "p95_ms",
        "redisErrorRate": "redis_error_rate",
    }
    for evidence_field, policy_field in threshold_bindings.items():
        raw = slo_values[evidence_field]
        policy_threshold = thresholds.get(policy_field)
        limit = (
            policy_threshold.get("warn")
            if isinstance(policy_threshold, dict)
            else None
        )
        if (
            not isinstance(raw, (int, float))
            or isinstance(raw, bool)
            or not isinstance(limit, (int, float))
            or isinstance(limit, bool)
            or float(raw) >= float(limit)
        ):
            raise ValueError(f"Prometheus soak evidence breached {policy_field}")
    slo_observed_at = _validate_timestamp(slo.get("queriedAt"), "Prometheus soak")

    if (
        set(alerts)
        != {"schema", "source", "queriedAt", "status", "activeFiring"}
        or alerts.get("schema") != "prod-alertmanager-soak-observation"
        or alerts.get("source") != "alertmanager"
        or alerts.get("status") != "passed"
        or alerts.get("activeFiring") != 0
    ):
        raise ValueError("Alertmanager soak evidence is not clear")
    alert_observed_at = _validate_timestamp(
        alerts.get("queriedAt"), "Alertmanager soak"
    )

    checks = health.get("checks")
    if not (
        health.get("command") == "health"
        and health.get("target") == "prod-hosted"
        and health.get("scope") == "full"
        and health.get("readOnly") is False
        and health.get("findings") == []
        and isinstance(checks, list)
        and bool(checks)
        and all(isinstance(check, dict) and check.get("ok") is True for check in checks)
    ):
        raise ValueError("full prod-hosted health evidence did not pass")
    health_observed_at = _validate_timestamp(health.get("timestamp"), "prod health")

    planes = credential_policy.get("planes")
    if not isinstance(planes, list) or not planes:
        raise ValueError("prod credential policy has no planes")
    expected_credentials: set[tuple[str, str]] = set()
    for plane in planes:
        if (
            not isinstance(plane, dict)
            or plane.get("access") != "read-write"
            or "100" not in (plane.get("appliesToStages") or [])
        ):
            continue
        governed = plane.get("rootlessGovernedComposeServices") or []
        support = plane.get("rootlessSupportComposeServices") or []
        if (
            "rootlessGovernedComposeServices" in plane
            or "rootlessSupportComposeServices" in plane
        ) and not (governed or support):
            continue
        expected_credentials.add(
            (str(plane.get("plane") or ""), str(plane.get("account") or ""))
        )
    credentials = credential_evidence.get("credentials")
    if not (
        set(credential_evidence)
        == {"schema", "stage", "verifiedAt", "credentials"}
        and credential_evidence.get("schema") == "prod-plane-credential-evidence"
        and credential_evidence.get("stage") == "100"
        and isinstance(credentials, list)
        and bool(credentials)
    ):
        raise ValueError("prod credential evidence is invalid")
    _validate_timestamp(
        credential_evidence.get("verifiedAt"), "prod credential evidence"
    )
    actual_credentials = {
        (str(item.get("plane") or ""), str(item.get("account") or ""))
        for item in credentials
        if isinstance(item, dict)
    }
    if actual_credentials != expected_credentials:
        raise ValueError("prod credential evidence does not cover canonical remote planes")
    credential_projection: list[dict[str, Any]] = []
    for item in credentials:
        if set(item) != {
            "plane",
            "account",
            "reference",
            "publicDigest",
            "issuer",
            "expiresAt",
            "verifiedAt",
        }:
            raise ValueError("prod credential evidence contains a non-canonical item")
        if "PRIVATE KEY" in str(item["reference"]) or "\n" in str(item["reference"]):
            raise ValueError("prod credential evidence contains secret material")
        if DIGEST_PATTERN.fullmatch(str(item["publicDigest"])) is None:
            raise ValueError("prod credential public digest is invalid")
        _validate_timestamp(item["expiresAt"], "prod credential expiry")
        _validate_timestamp(item["verifiedAt"], "prod credential verification")
        credential_projection.append(dict(item))

    expected_governance_fields = {
        "schema",
        "repository",
        "gitSha",
        "artifactDigest",
        "pullRequest",
        "author",
        "mergedBy",
        "approvers",
        "distinctPrincipals",
        "verifiedAt",
    }
    if not (
        set(governance) == expected_governance_fields
        and governance.get("schema") == "prod-release-governance-receipt"
        and governance.get("artifactDigest") == manifest["artifactDigest"]
        and governance.get("gitSha") == source["gitSha"]
        and isinstance(governance.get("approvers"), list)
        and bool(governance["approvers"])
        and isinstance(governance.get("distinctPrincipals"), list)
        and len(governance["distinctPrincipals"]) >= 2
    ):
        raise ValueError("canonical reviewed-mainline approval is invalid")
    approval_verified_at = _validate_timestamp(
        governance.get("verifiedAt"), "release governance"
    )

    return {
        "schema": HOSTED_SOAK_REQUEST_SCHEMA,
        "service": service,
        "environment": "prod",
        "target": "prod-hosted",
        "fullRolloutReceiptId": full["receiptId"],
        "candidateId": candidate,
        "rolloutArtifactDigest": full["artifactDigest"],
        "artifactDigest": manifest["artifactDigest"],
        "sourceGitSha": source["gitSha"],
        "sourceTreeDigest": source["treeDigest"],
        "rolloutConfigDigest": full["configDigest"],
        "configGraphDigest": _digest_bytes(
            _canonical_bytes(manifest["configurationPackages"])
        ),
        "contractGraphDigest": manifest["contractGraphDigest"],
        "requiredSoakSeconds": required_soak_seconds,
        "soakPolicyDigest": _digest_file(soak_policy_path),
        "credentialPolicyDigest": _digest_file(credential_policy_path),
        "slo": {
            "source": "prometheus",
            "observedAt": slo_observed_at,
            "windowSeconds": required_soak_seconds,
            "minimumSamples": minimum_samples,
            "sampleCount": sample_count,
            "status": "passed",
            "decision": "continue",
            "values": {
                field: float(slo_values[field]) for field in threshold_bindings
            },
            "receiptDigest": _digest_file(slo_path),
        },
        "alerts": {
            "source": "alertmanager",
            "observedAt": alert_observed_at,
            "status": "passed",
            "activeFiring": 0,
            "receiptDigest": _digest_file(alerts_path),
        },
        "health": {
            "source": "stackctl",
            "observedAt": health_observed_at,
            "target": "prod-hosted",
            "scope": "full",
            "status": "passed",
            "receiptDigest": _digest_file(health_path),
        },
        "credentials": credential_projection,
        "approval": {
            "kind": "github-reviewed-mainline",
            "repository": governance["repository"],
            "sourceGitSha": source["gitSha"],
            "artifactDigest": manifest["artifactDigest"],
            "pullRequest": governance["pullRequest"],
            "approvers": list(governance["approvers"]),
            "distinctPrincipals": len(governance["distinctPrincipals"]),
            "receiptDigest": _digest_file(governance_path),
            "verifiedAt": approval_verified_at,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    readiness = subparsers.add_parser("rollback-readiness")
    readiness.add_argument("--manifest", required=True, type=Path)
    readiness.add_argument("--service", required=True)
    readiness.add_argument("--from-candidate-digest", required=True)
    readiness.add_argument("--current-ledger-readback", required=True, type=Path)
    readiness.add_argument("--rollback-drill-readback", required=True, type=Path)
    readiness.add_argument("--backup-validation", required=True, type=Path)
    readiness.add_argument("--archive-prefix", required=True)
    readiness.add_argument(
        "--rollback-drill-max-age-seconds", required=True, type=int
    )
    readiness.add_argument("--output", required=True, type=Path)

    outcome = subparsers.add_parser("prod-outcome")
    outcome.add_argument("--manifest", required=True, type=Path)
    outcome.add_argument("--service", required=True)
    outcome.add_argument("--from-candidate-digest", required=True)
    outcome.add_argument("--stage-report", action="append", default=[])
    outcome.add_argument("--stage-readback", action="append", default=[])
    outcome.add_argument("--archive-prefix", required=True)
    outcome.add_argument("--hard-deadline-epoch", required=True, type=int)
    outcome.add_argument("--rollback-budget-seconds", required=True, type=int)
    outcome.add_argument("--output-dir", required=True, type=Path)

    soak = subparsers.add_parser("prod-soak-request")
    soak.add_argument("--manifest", required=True, type=Path)
    soak.add_argument("--service", required=True)
    soak.add_argument("--full-readback", required=True, type=Path)
    soak.add_argument("--slo-observation", required=True, type=Path)
    soak.add_argument("--alerts-observation", required=True, type=Path)
    soak.add_argument("--health-report", required=True, type=Path)
    soak.add_argument("--credential-evidence", required=True, type=Path)
    soak.add_argument("--credential-policy", required=True, type=Path)
    soak.add_argument("--governance-receipt", required=True, type=Path)
    soak.add_argument("--soak-policy", required=True, type=Path)
    soak.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        manifest = _load_json(args.manifest, "ReleaseEvidenceManifest")
        if args.command == "rollback-readiness":
            result = render_rollback_readiness(
                manifest=manifest,
                service=args.service,
                from_candidate_digest=args.from_candidate_digest,
                current_ledger_path=args.current_ledger_readback,
                current_ledger=_load_json(
                    args.current_ledger_readback, "current hosted ledger"
                ),
                rollback_drill_path=args.rollback_drill_readback,
                rollback_drill=_load_json(
                    args.rollback_drill_readback, "rollback drill readback"
                ),
                backup_validation_path=args.backup_validation,
                backup_validation=_load_json(
                    args.backup_validation, "backup recovery validation"
                ),
                archive_prefix=args.archive_prefix,
                rollback_drill_max_age_seconds=args.rollback_drill_max_age_seconds,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
        elif args.command == "prod-outcome":
            report_paths = _parse_binding(args.stage_report, "stage report")
            readback_paths = _parse_binding(args.stage_readback, "stage readback")
            result = render_prod_outcome(
                manifest=manifest,
                service=args.service,
                from_candidate_digest=args.from_candidate_digest,
                reports={
                    stage: (path, _load_json(path, f"{stage} report"))
                    for stage, path in report_paths.items()
                },
                readbacks={
                    stage: (path, _load_json(path, f"{stage} readback"))
                    for stage, path in readback_paths.items()
                },
                archive_prefix=args.archive_prefix,
                hard_deadline_epoch=args.hard_deadline_epoch,
                rollback_budget_seconds=args.rollback_budget_seconds,
            )
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for key, filename in (
                ("environment", "prod.json"),
                ("rollout", "rollout.json"),
                ("rollback", "rollback.json"),
            ):
                (args.output_dir / filename).write_text(
                    json.dumps(
                        result[key], ensure_ascii=False, indent=2, sort_keys=True
                    )
                    + "\n",
                    encoding="utf-8",
                )
        else:
            result = render_prod_soak_request(
                manifest=manifest,
                service=args.service,
                full_readback=_load_json(args.full_readback, "full hosted readback"),
                slo=_load_json(args.slo_observation, "Prometheus soak observation"),
                slo_path=args.slo_observation,
                alerts=_load_json(
                    args.alerts_observation, "Alertmanager soak observation"
                ),
                alerts_path=args.alerts_observation,
                health=_load_json(args.health_report, "prod health report"),
                health_path=args.health_report,
                credential_evidence=_load_json(
                    args.credential_evidence, "prod credential evidence"
                ),
                credential_policy=yaml.safe_load(
                    args.credential_policy.read_text(encoding="utf-8")
                ),
                credential_policy_path=args.credential_policy,
                governance=_load_json(
                    args.governance_receipt, "release governance receipt"
                ),
                governance_path=args.governance_receipt,
                soak_policy=yaml.safe_load(
                    args.soak_policy.read_text(encoding="utf-8")
                ),
                soak_policy_path=args.soak_policy,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"render_release_lifecycle_receipts: FAIL: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""transition/soak 请求与晋级/回滚证据校验（stdlib-only）。"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from .contract import (
    DECISIONS,
    OCI_REF_RE,
    PROMOTION_EVIDENCE_FIELDS,
    PROMOTION_THRESHOLDS,
    RECEIPT_ID_RE,
    REQUEST_FIELDS,
    REQUEST_SCHEMA,
    ROLLBACK_OUTCOMES,
    SERVICE_RE,
    SHA256_RE,
    SOAK_APPROVAL_FIELDS,
    SOAK_CREDENTIAL_FIELDS,
    SOAK_EVIDENCE_FIELDS,
    SOAK_REQUEST_FIELDS,
    SOAK_REQUEST_SCHEMA,
    STAGES,
    STAGE_STEPS,
    _canonical_bytes,
    _require_non_negative_integer,
    _require_safe_string,
    _require_timestamp,
)


def validate_promotion_evidence(
    value: object,
    *,
    candidate_id: object,
    artifact_digest: object,
    stage: object,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != PROMOTION_EVIDENCE_FIELDS:
        raise ValueError("promotionEvidence has an invalid shape")
    if (
        value.get("schema") != "prod-rollout-stage-promotion-evidence"
        or value.get("authority") != "protected-prod-runner"
        or value.get("candidateId") != candidate_id
        or value.get("artifactDigest") != artifact_digest
        or value.get("stage") != stage
        or not _require_safe_string(value.get("campaignId"), field="campaignId")
        or not isinstance(value.get("routingPolicyDigest"), str)
        or SHA256_RE.fullmatch(value["routingPolicyDigest"]) is None
        or not isinstance(value.get("evidenceDigest"), str)
        or SHA256_RE.fullmatch(value["evidenceDigest"]) is None
    ):
        raise ValueError("promotionEvidence binding is invalid")
    unsigned = dict(value)
    evidence_digest = unsigned.pop("evidenceDigest")
    if "sha256:" + hashlib.sha256(_canonical_bytes(unsigned)).hexdigest() != evidence_digest:
        raise ValueError("promotionEvidence digest is invalid")

    observed_from = _require_timestamp(
        value.get("observedFrom"), field="promotionEvidence.observedFrom"
    )
    observed_until = _require_timestamp(
        value.get("observedUntil"), field="promotionEvidence.observedUntil"
    )
    duration = _require_non_negative_integer(
        value.get("durationSeconds"), field="promotionEvidence.durationSeconds"
    )
    if observed_until < observed_from or duration != int(
        (observed_until - observed_from).total_seconds()
    ):
        raise ValueError("promotionEvidence observation interval is invalid")
    minimum_duration, minimum_requests, minimum_installations, per_platform, synthetic = (
        PROMOTION_THRESHOLDS[str(stage)]
    )
    requests = _require_non_negative_integer(
        value.get("candidateRequestCount"),
        field="promotionEvidence.candidateRequestCount",
    )
    installations = _require_non_negative_integer(
        value.get("uniqueCandidateInstallations"),
        field="promotionEvidence.uniqueCandidateInstallations",
    )
    synthetic_requests = _require_non_negative_integer(
        value.get("syntheticRequestCount"),
        field="promotionEvidence.syntheticRequestCount",
    )
    if (
        duration < minimum_duration
        or requests < minimum_requests
        or installations < minimum_installations
        or synthetic_requests < synthetic
    ):
        raise ValueError("promotionEvidence does not satisfy the stage threshold")

    platforms = value.get("platforms")
    allowed_platforms = {"android", "ios", "web"}
    if (
        not isinstance(platforms, dict)
        or not platforms
        or not set(platforms).issubset(allowed_platforms)
        or (stage in {"canary", "100"} and set(platforms) != allowed_platforms)
    ):
        raise ValueError("promotionEvidence platforms are invalid")
    platform_requests = 0
    platform_installations = 0
    for platform, item in platforms.items():
        if not isinstance(item, dict) or set(item) != {
            "candidateRequestCount",
            "uniqueCandidateInstallations",
        }:
            raise ValueError(f"promotionEvidence platform {platform} is invalid")
        platform_requests += _require_non_negative_integer(
            item.get("candidateRequestCount"), field=f"platforms.{platform}.requests"
        )
        platform_count = _require_non_negative_integer(
            item.get("uniqueCandidateInstallations"),
            field=f"platforms.{platform}.installations",
        )
        if platform_count < per_platform:
            raise ValueError(
                f"promotionEvidence platform {platform} lacks required installations"
            )
        platform_installations += platform_count
    if platform_requests != requests or platform_installations != installations:
        raise ValueError("promotionEvidence platform totals are inconsistent")

    audiences = value.get("audiences")
    if not isinstance(audiences, dict) or set(audiences) != {"regions", "carriers"}:
        raise ValueError("promotionEvidence audiences are invalid")
    for dimension in ("regions", "carriers"):
        audience = audiences[dimension]
        if not isinstance(audience, dict) or set(audience) != {"mode", "observations"}:
            raise ValueError(f"promotionEvidence {dimension} is invalid")
        observations = audience.get("observations")
        if not isinstance(observations, list) or not observations:
            raise ValueError(f"promotionEvidence {dimension} observations are missing")
        seen: set[str] = set()
        has_unknown = False
        has_top = False
        for item in observations:
            if not isinstance(item, dict) or set(item) != {
                "value",
                "top",
                "candidateRequestCount",
                "uniqueCandidateInstallations",
            }:
                raise ValueError(f"promotionEvidence {dimension} observation is invalid")
            segment = _require_safe_string(
                item.get("value"), field=f"promotionEvidence.{dimension}.value"
            )
            if segment in seen or not isinstance(item.get("top"), bool):
                raise ValueError(f"promotionEvidence {dimension} segment is invalid")
            seen.add(segment)
            segment_requests = _require_non_negative_integer(
                item.get("candidateRequestCount"),
                field=f"promotionEvidence.{dimension}.requests",
            )
            segment_installations = _require_non_negative_integer(
                item.get("uniqueCandidateInstallations"),
                field=f"promotionEvidence.{dimension}.installations",
            )
            has_unknown = has_unknown or segment == "unknown"
            has_top = has_top or (item["top"] and segment != "unknown")
            if audience.get("mode") == "include" and (
                segment_requests < 100 or segment_installations < 10
            ):
                raise ValueError(
                    f"promotionEvidence directed {dimension} lacks required samples"
                )
        if audience.get("mode") == "all":
            if not has_unknown or not has_top:
                raise ValueError(
                    f"promotionEvidence all-mode {dimension} lacks top/unknown observations"
                )
        elif audience.get("mode") != "include":
            raise ValueError(f"promotionEvidence {dimension} mode is invalid")

    coverage = value.get("supportedAppCoverage")
    if (
        not isinstance(coverage, dict)
        or set(coverage) != {"mode", "complete"}
        or not isinstance(coverage.get("complete"), bool)
        or (stage == "100" and coverage.get("complete") is not True)
    ):
        raise ValueError("promotionEvidence supported App coverage is invalid")
    source = value.get("source")
    if (
        not isinstance(source, dict)
        or set(source) != {"authority", "queryDigest", "receiptDigest", "generatedAt"}
        or source.get("authority") != "prod-observability-plane"
        or any(
            not isinstance(source.get(field), str)
            or SHA256_RE.fullmatch(source[field]) is None
            for field in ("queryDigest", "receiptDigest")
        )
        or _require_timestamp(source.get("generatedAt"), field="source.generatedAt")
        < observed_until
    ):
        raise ValueError("promotionEvidence source is invalid")
    return dict(value)


def _validate_check_summaries(
    value: object, *, field: str
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(
        isinstance(item, dict)
        and set(item) == {"name", "status", "receiptDigest"}
        and _require_safe_string(item.get("name"), field=f"{field}.name")
        and item.get("status") in {"passed", "failed"}
        and isinstance(item.get("receiptDigest"), str)
        and SHA256_RE.fullmatch(item["receiptDigest"]) is not None
        for item in value
    ):
        raise ValueError(f"{field} must contain canonical digest-bound checks")
    return [dict(item) for item in value]


def validate_rollback_evidence(
    value: object,
    *,
    decision: object,
    rollback_outcome: object,
    verified_at: object,
) -> dict[str, Any]:
    """Validate the exact hosted rollback fact persisted with one transition."""

    expected_decisions = {
        "not_triggered": {"continue", "pause"},
        "rolled_back": {"rolled_back"},
        "rollback_failed": {"rollback_failed"},
    }.get(rollback_outcome)
    if expected_decisions is None or decision not in expected_decisions:
        raise ValueError("rollback outcome and decision are not canonically bound")
    verified = _require_timestamp(verified_at, field="verifiedAt")
    if rollback_outcome == "not_triggered":
        if not isinstance(value, dict) or value != {"triggered": False}:
            raise ValueError(
                "non-triggered rollbackEvidence must contain only triggered=false"
            )
        return dict(value)

    expected_fields = {
        "triggered",
        "startedAt",
        "endedAt",
        "durationMs",
        "postChecks",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected_fields
        or value.get("triggered") is not True
    ):
        raise ValueError("triggered rollbackEvidence has a non-canonical shape")
    started = _require_timestamp(
        value.get("startedAt"), field="rollbackEvidence.startedAt"
    )
    ended = _require_timestamp(
        value.get("endedAt"), field="rollbackEvidence.endedAt"
    )
    duration_ms = value.get("durationMs")
    if (
        ended < started
        or ended > verified
        or not isinstance(duration_ms, int)
        or isinstance(duration_ms, bool)
        or duration_ms < 0
    ):
        raise ValueError("rollbackEvidence timing is invalid")
    checks = _validate_check_summaries(
        value.get("postChecks"), field="rollbackEvidence.postChecks"
    )
    if rollback_outcome == "rolled_back" and (
        not checks or any(item["status"] != "passed" for item in checks)
    ):
        raise ValueError(
            "successful rollbackEvidence requires non-empty passed post-checks"
        )
    return dict(value)


def _validate_request(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != REQUEST_FIELDS:
        raise ValueError("hosted release transition request has an invalid shape")
    if value.get("schema") != REQUEST_SCHEMA:
        raise ValueError("hosted release transition request schema is invalid")
    service = str(value.get("service") or "")
    if SERVICE_RE.fullmatch(service) is None:
        raise ValueError("service is invalid")
    _require_safe_string(value.get("step"), field="step")
    if value.get("stage") not in STAGES:
        raise ValueError("stage is invalid")
    if value.get("triggerStage") not in STAGES:
        raise ValueError("triggerStage is invalid")
    if value.get("step") != STAGE_STEPS[value["stage"]]:
        raise ValueError("step does not match stage")
    for field in ("fromReleaseEvidenceRef", "toReleaseEvidenceRef"):
        if not isinstance(value.get(field), str) or OCI_REF_RE.fullmatch(value[field]) is None:
            raise ValueError(f"{field} must be an exact immutable OCI ref")
    for field in ("fromImageTransportTag", "toImageTransportTag"):
        _require_safe_string(value.get(field), field=field)
    decision = value.get("decision")
    if decision not in DECISIONS:
        raise ValueError("decision is invalid")
    rollback_outcome = value.get("rollbackOutcome")
    if rollback_outcome not in ROLLBACK_OUTCOMES:
        raise ValueError("rollbackOutcome is invalid")
    for field in (
        "artifactDigest",
        "fromCandidateDigest",
        "toCandidateDigest",
        "environmentAcceptanceDigest",
        "environmentAcceptanceFactId",
        "gammaPredecessorFactId",
        "gammaPredecessorDigest",
        "engineeringEligibilityDigest",
        "durableApprovalDigest",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
    ):
        if not isinstance(value.get(field), str) or SHA256_RE.fullmatch(value[field]) is None:
            raise ValueError(f"{field} must be sha256")
    for field in (
        "environmentAcceptanceRef",
        "engineeringEligibilityRef",
        "durableApprovalRef",
    ):
        _require_safe_string(value.get(field), field=field)
    generation = value.get("expectedGeneration")
    if (
        not isinstance(generation, int)
        or isinstance(generation, bool)
        or generation < 0
    ):
        raise ValueError("expectedGeneration must be a non-negative integer")
    if not isinstance(value.get("sloReadback"), dict):
        raise ValueError("sloReadback must be an object")
    if service == "prod-stack" and decision == "continue":
        validate_promotion_evidence(
            value["sloReadback"].get("promotionEvidence"),
            candidate_id=value.get("toCandidateDigest"),
            artifact_digest=value.get("artifactDigest"),
            stage=value.get("triggerStage"),
        )
    _validate_check_summaries(value.get("postChecks"), field="postChecks")
    last_good = value.get("lastGoodCandidateDigest")
    if not isinstance(last_good, str) or SHA256_RE.fullmatch(last_good) is None:
        raise ValueError("lastGoodCandidateDigest must be sha256")
    validate_rollback_evidence(
        value.get("rollbackEvidence"),
        decision=decision,
        rollback_outcome=rollback_outcome,
        verified_at=value.get("verifiedAt"),
    )
    return dict(value)


def _validate_soak_request(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SOAK_REQUEST_FIELDS:
        raise ValueError("hosted prod soak request has an invalid shape")
    if value.get("schema") != SOAK_REQUEST_SCHEMA:
        raise ValueError("hosted prod soak request schema is invalid")
    if (
        not isinstance(value.get("service"), str)
        or SERVICE_RE.fullmatch(value["service"]) is None
        or value.get("environment") != "prod"
        or value.get("target") != "prod-hosted"
    ):
        raise ValueError("hosted prod soak request target is invalid")
    if (
        not isinstance(value.get("fullRolloutReceiptId"), str)
        or RECEIPT_ID_RE.fullmatch(value["fullRolloutReceiptId"]) is None
    ):
        raise ValueError("fullRolloutReceiptId is invalid")
    for field in (
        "candidateId",
        "rolloutArtifactDigest",
        "artifactDigest",
        "rolloutConfigDigest",
        "configGraphDigest",
        "contractGraphDigest",
        "soakPolicyDigest",
        "credentialPolicyDigest",
    ):
        if (
            not isinstance(value.get(field), str)
            or SHA256_RE.fullmatch(value[field]) is None
        ):
            raise ValueError(f"{field} must be sha256")
    if (
        not isinstance(value.get("sourceGitSha"), str)
        or re.fullmatch(r"[0-9a-f]{40}", value["sourceGitSha"]) is None
    ):
        raise ValueError("sourceGitSha must be a lowercase 40-character Git SHA")
    if (
        not isinstance(value.get("sourceTreeDigest"), str)
        or re.fullmatch(
            r"(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})",
            value["sourceTreeDigest"],
        )
        is None
    ):
        raise ValueError("sourceTreeDigest must be immutable")
    required_soak = value.get("requiredSoakSeconds")
    if (
        not isinstance(required_soak, int)
        or isinstance(required_soak, bool)
        or required_soak < 60
    ):
        raise ValueError("requiredSoakSeconds must be an integer >= 60")

    for name, fields in SOAK_EVIDENCE_FIELDS.items():
        evidence = value.get(name)
        if not isinstance(evidence, dict) or set(evidence) != fields:
            raise ValueError(f"{name} evidence has an invalid shape")
        _require_timestamp(evidence.get("observedAt"), field=f"{name}.observedAt")
        if (
            not isinstance(evidence.get("receiptDigest"), str)
            or SHA256_RE.fullmatch(evidence["receiptDigest"]) is None
        ):
            raise ValueError(f"{name}.receiptDigest must be sha256")
        if evidence.get("status") != "passed":
            raise ValueError(f"{name} evidence did not pass")

    slo = value["slo"]
    if slo.get("source") != "prometheus" or slo.get("decision") != "continue":
        raise ValueError("SLO evidence must be a continuing Prometheus decision")
    for field in ("windowSeconds", "minimumSamples", "sampleCount"):
        raw = slo.get(field)
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 1:
            raise ValueError(f"slo.{field} must be a positive integer")
    if slo["windowSeconds"] < required_soak:
        raise ValueError("SLO observation window is shorter than required soak")
    if slo["sampleCount"] < slo["minimumSamples"]:
        raise ValueError("SLO sample count is below the required minimum")
    values = slo.get("values")
    if not isinstance(values, dict) or set(values) != {
        "errorRate",
        "p95Ms",
        "redisErrorRate",
    }:
        raise ValueError("SLO values have an invalid shape")
    for field, raw in values.items():
        if (
            not isinstance(raw, (int, float))
            or isinstance(raw, bool)
            or float(raw) < 0
        ):
            raise ValueError(f"slo.values.{field} must be non-negative")

    alerts = value["alerts"]
    if alerts.get("source") != "alertmanager" or alerts.get("activeFiring") != 0:
        raise ValueError("alerts evidence must prove no active firing alerts")
    health = value["health"]
    if (
        health.get("source") != "stackctl"
        or health.get("target") != "prod-hosted"
        or health.get("scope") != "full"
    ):
        raise ValueError("health evidence must be full prod-hosted stackctl health")

    credentials = value.get("credentials")
    if not isinstance(credentials, list) or not credentials:
        raise ValueError("credentials evidence is missing")
    seen_credentials: set[tuple[str, str]] = set()
    for index, credential in enumerate(credentials):
        if not isinstance(credential, dict) or set(credential) != SOAK_CREDENTIAL_FIELDS:
            raise ValueError(f"credentials[{index}] has an invalid shape")
        plane = _require_safe_string(
            credential.get("plane"), field=f"credentials[{index}].plane"
        )
        account = _require_safe_string(
            credential.get("account"), field=f"credentials[{index}].account"
        )
        reference = _require_safe_string(
            credential.get("reference"), field=f"credentials[{index}].reference"
        )
        if "PRIVATE KEY" in reference or "\n" in reference:
            raise ValueError("credential reference contains secret material")
        if (
            not isinstance(credential.get("publicDigest"), str)
            or SHA256_RE.fullmatch(credential["publicDigest"]) is None
        ):
            raise ValueError("credential public digest is invalid")
        _require_safe_string(
            credential.get("issuer"), field=f"credentials[{index}].issuer"
        )
        _require_timestamp(
            credential.get("expiresAt"), field=f"credentials[{index}].expiresAt"
        )
        _require_timestamp(
            credential.get("verifiedAt"), field=f"credentials[{index}].verifiedAt"
        )
        identity = (plane, account)
        if identity in seen_credentials:
            raise ValueError(f"duplicate credential identity: {plane}/{account}")
        seen_credentials.add(identity)

    approval = value.get("approval")
    if not isinstance(approval, dict) or set(approval) != SOAK_APPROVAL_FIELDS:
        raise ValueError("approval evidence has an invalid shape")
    if approval.get("kind") != "github-reviewed-mainline":
        raise ValueError("approval must use canonical reviewed-mainline authority")
    _require_safe_string(approval.get("repository"), field="approval.repository")
    if approval.get("sourceGitSha") != value["sourceGitSha"]:
        raise ValueError("approval sourceGitSha differs from soak source")
    if approval.get("artifactDigest") != value["artifactDigest"]:
        raise ValueError("approval artifactDigest differs from soak artifact")
    if (
        not isinstance(approval.get("pullRequest"), int)
        or isinstance(approval.get("pullRequest"), bool)
        or approval["pullRequest"] < 1
    ):
        raise ValueError("approval pullRequest must be positive")
    approvers = approval.get("approvers")
    if (
        not isinstance(approvers, list)
        or not approvers
        or any(not isinstance(item, str) or not item.strip() for item in approvers)
    ):
        raise ValueError("approval approvers must be non-empty identities")
    if (
        not isinstance(approval.get("distinctPrincipals"), int)
        or isinstance(approval.get("distinctPrincipals"), bool)
        or approval["distinctPrincipals"] < 2
    ):
        raise ValueError("approval lacks author/approver separation")
    if (
        not isinstance(approval.get("receiptDigest"), str)
        or SHA256_RE.fullmatch(approval["receiptDigest"]) is None
    ):
        raise ValueError("approval receipt digest is invalid")
    _require_timestamp(approval.get("verifiedAt"), field="approval.verifiedAt")
    return dict(value)

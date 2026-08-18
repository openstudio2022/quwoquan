"""Prod 全量放量后的 soak 请求（hosted soak request）封版逻辑。

原单文件 ``render_release_lifecycle_receipts.py`` 拆分出的 soak 子模块。
``validate_manifest`` 为被测试 monkeypatch 的薄入口模块属性，消费点经
``_pkg.`` 访问。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import quwoquan_ops.ci.render_release_lifecycle_receipts as _pkg
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import DIGEST_PATTERN

from .constants import HOSTED_SOAK_REQUEST_SCHEMA
from .hosted_readback import _validate_receipt_readback
from .receipt_codec import (
    _canonical_bytes,
    _digest_bytes,
    _digest_file,
    _validate_timestamp,
    _window_seconds,
)


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
    _pkg.validate_manifest(manifest, allowed_statuses={"released"})
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
            _canonical_bytes(
                manifest["environmentArtifacts"]["prod"]["configurationPackages"]
            )
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

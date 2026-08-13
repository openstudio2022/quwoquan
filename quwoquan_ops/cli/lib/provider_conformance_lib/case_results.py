"""CaseResult 工件与不可变执行报告的字段级校验。

可被测试 patch 的符号（ci_attestation_authority_available）一律经薄入口
`_pc` 在调用时读取。
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import hmac
import json
from pathlib import Path
import re
from typing import Any

from quwoquan_ops.cli.lib import provider_conformance as _pc

from .attestation import _commit_digest, sign_execution_report
from .constants import (
    ARTIFACT_ATTESTATION_PATTERN,
    CASE_RESULT_RELEASE_FIELDS,
    CASE_RESULT_REMOTE_FIELDS,
    CASE_RESULT_REQUIRED_FIELDS,
    CASE_RESULT_SCHEMA,
    EXECUTION_REPORT_REQUIRED_FIELDS,
    EXECUTION_REPORT_SCHEMA,
    NATIVE_READBACK_ARTIFACT_RE,
    RELEASE_READINESS_FIELDS,
    REMOTE_READBACK_SCHEMA,
    SHA256_PATTERN,
    requires_release_readiness,
)
from .evidence_store import _issue
from .governance_bindings import _is_non_empty_string, _valid_receipt_ref

def _observability_refs_valid(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"logs", "traces", "metrics"}
        and all(
            isinstance(value[facet], list)
            and value[facet]
            and all(_is_non_empty_string(ref) for ref in value[facet])
            for facet in ("logs", "traces", "metrics")
        )
    )


def _native_readback_valid(
    value: object,
    *,
    case_result_path: Path,
) -> bool:
    """Verify the Provider two-device device readback sidecar is present and content-bound."""
    if not isinstance(value, Mapping) or set(value) != {
        "schema",
        "artifactName",
        "artifactDigest",
    }:
        return False
    if value.get("schema") != REMOTE_READBACK_SCHEMA:
        return False
    artifact_name = value.get("artifactName")
    artifact_digest = value.get("artifactDigest")
    if (
        not isinstance(artifact_name, str)
        or not NATIVE_READBACK_ARTIFACT_RE.fullmatch(artifact_name)
        or not isinstance(artifact_digest, str)
        or not SHA256_PATTERN.fullmatch(artifact_digest)
    ):
        return False
    artifact_path = case_result_path.parent / artifact_name
    try:
        actual_digest = f"sha256:{hashlib.sha256(artifact_path.read_bytes()).hexdigest()}"
    except OSError:
        return False
    return hmac.compare_digest(artifact_digest, actual_digest)


def load_case_results(
    artifact_path: Path,
    *,
    source: Mapping[str, Any],
    environment: str,
    config_digest: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate the real test-owned CaseResult artifact for one execution cell."""
    issues: list[str] = []
    try:
        result = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [_issue(str(artifact_path), f"invalid CaseResult artifact: {exc}")]
    if not isinstance(result, dict):
        return None, [_issue(str(artifact_path), "CaseResult artifact root must be an object")]
    is_release_case = requires_release_readiness(
        environment,
        str(source.get("testLayer") or ""),
    )
    is_remote_release_case = is_release_case and str(source.get("target") or "").startswith(
        "provider-remote-"
    )
    expected_fields = (
        CASE_RESULT_REQUIRED_FIELDS | CASE_RESULT_RELEASE_FIELDS
        if is_release_case
        else CASE_RESULT_REQUIRED_FIELDS
    )
    allowed_fields = expected_fields | (
        CASE_RESULT_REMOTE_FIELDS if is_remote_release_case else frozenset()
    )
    missing = expected_fields - set(result)
    unknown = set(result) - allowed_fields
    if missing or unknown:
        if missing:
            issues.append(
                _issue(str(artifact_path), f"CaseResult missing fields {sorted(missing)}")
            )
        if unknown:
            issues.append(
                _issue(str(artifact_path), f"CaseResult contains unknown fields {sorted(unknown)}")
            )
        return None, issues
    if result.get("schema") != CASE_RESULT_SCHEMA:
        issues.append(_issue(str(artifact_path), "CaseResult has unsupported schema"))
    expected = {
        "adapterId": source.get("adapterId"),
        "capabilityId": source.get("capabilityId"),
        "environment": environment,
        "testLayer": source.get("testLayer"),
        "typedPort": source.get("typedPort"),
        "contractRef": source.get("contractRef"),
        "networkBoundary": source.get("networkBoundary"),
        "testTarget": source.get("target"),
        "configDigest": config_digest,
    }
    for field, value in expected.items():
        if result.get(field) != value:
            issues.append(
                _issue(
                    str(artifact_path),
                    f"CaseResult {field} does not match the executed source/binding",
                )
            )
    if result.get("status") != "passed":
        issues.append(_issue(str(artifact_path), "CaseResult status must be passed"))
    assertion_ids = result.get("assertionIds")
    expected_assertion_ids = source.get("assertionIds")
    if (
        not isinstance(assertion_ids, list)
        or not assertion_ids
        or len(assertion_ids) != len(set(assertion_ids))
        or tuple(sorted(assertion_ids)) != tuple(sorted(expected_assertion_ids or []))
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult assertionIds must exactly match its source-declared assertion set",
            )
        )
    cases = result.get("caseResults")
    if not isinstance(cases, list) or len(cases) != len(assertion_ids or []):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult must contain exactly one result for every assertionId",
            )
        )
    else:
        case_ids: list[str] = []
        for case in cases:
            if (
                not isinstance(case, Mapping)
                or set(case) != {"assertionId", "status", "logRef", "traceRef", "metricRefs"}
                or not _is_non_empty_string(case.get("assertionId"))
                or case.get("status") != "passed"
                or not _is_non_empty_string(case.get("logRef"))
                or not _is_non_empty_string(case.get("traceRef"))
                or not isinstance(case.get("metricRefs"), list)
                or not case["metricRefs"]
                or not all(_is_non_empty_string(ref) for ref in case["metricRefs"])
            ):
                issues.append(
                    _issue(
                        str(artifact_path),
                        "every CaseResult must be a passed assertion with log/trace/metric references",
                    )
                )
                break
            case_ids.append(str(case["assertionId"]))
        if sorted(case_ids) != sorted(assertion_ids or []):
            issues.append(
                _issue(
                    str(artifact_path),
                    "CaseResult assertion records must exactly cover assertionIds",
                )
            )
    if not isinstance(result.get("configDigest"), str) or not SHA256_PATTERN.fullmatch(
        str(result.get("configDigest"))
    ):
        issues.append(_issue(str(artifact_path), "CaseResult configDigest must be sha256"))
    if not isinstance(result.get("dataDigest"), str) or not SHA256_PATTERN.fullmatch(
        str(result.get("dataDigest"))
    ):
        issues.append(_issue(str(artifact_path), "CaseResult dataDigest must be sha256"))
    if not _valid_receipt_ref(result.get("cleanupReceipt")):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult cleanupReceipt must be a non-sensitive receipt reference",
            )
        )
    if not _observability_refs_valid(result.get("observabilityRefs")):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult observabilityRefs must contain logs/traces/metrics",
            )
        )
    elif isinstance(cases, list):
        observability_refs = result["observabilityRefs"]
        for case in cases:
            if not isinstance(case, Mapping):
                continue
            if (
                case.get("logRef") not in observability_refs["logs"]
                or case.get("traceRef") not in observability_refs["traces"]
                or not set(case.get("metricRefs", [])).issubset(
                    set(observability_refs["metrics"])
                )
            ):
                issues.append(
                    _issue(
                        str(artifact_path),
                        "CaseResult observabilityRefs must include each assertion's log/trace/metric references",
                    )
                )
                break
    if is_release_case and not _release_readiness_valid(result):
        issues.append(
            _issue(
                str(artifact_path),
                "release Provider CaseResult must contain test-owned release "
                "readiness receipts",
            )
        )
    if (
        is_remote_release_case
        and "nativeReadback" in result
        and not _native_readback_valid(
            result.get("nativeReadback"),
            case_result_path=artifact_path,
        )
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "Provider two-device Remote CaseResult must bind an existing native-device readback "
                "sidecar with a matching digest",
            )
        )
    if re.search(
        r"(?:endpoint|secret|credential|token|password|https?://)",
        json.dumps(result, sort_keys=True),
        re.IGNORECASE,
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "CaseResult must not contain endpoint, credential, token or URL values",
            )
        )
    return result, issues


def _validate_execution_report(
    *,
    artifact_path: Path,
    evidence: Mapping[str, Any],
    expected_source: Mapping[str, Any] | None,
) -> list[str]:
    issues: list[str] = []
    try:
        raw = artifact_path.read_bytes()
        report = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return [_issue(str(artifact_path), f"invalid execution report: {exc}")]
    if not isinstance(report, Mapping):
        return [_issue(str(artifact_path), "execution report root must be an object")]
    fields = set(report)
    missing = EXECUTION_REPORT_REQUIRED_FIELDS - fields
    unknown = fields - EXECUTION_REPORT_REQUIRED_FIELDS
    if missing or unknown:
        if missing:
            issues.append(
                _issue(
                    str(artifact_path),
                    f"execution report missing fields {sorted(missing)}",
                )
            )
        if unknown:
            issues.append(
                _issue(
                    str(artifact_path),
                    f"execution report contains unknown fields {sorted(unknown)}",
                )
            )
        return issues
    if report.get("schema") != EXECUTION_REPORT_SCHEMA:
        issues.append(
            _issue(
                str(artifact_path),
                "execution report has unsupported schema",
            )
        )
    expected_digest = evidence.get("artifactDigest")
    actual_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if expected_digest != actual_digest:
        issues.append(
            _issue(
                str(artifact_path),
                "artifactDigest does not match the immutable execution report bytes",
            )
        )
    supplied_attestation = evidence.get("artifactAttestation")
    if (
        not isinstance(supplied_attestation, str)
        or not ARTIFACT_ATTESTATION_PATTERN.fullmatch(supplied_attestation)
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "artifactAttestation must be an HMAC-SHA256 or local-SHA256 value",
            )
        )
    elif evidence.get("attestationAuthority") == "local":
        expected_attestation = "local-sha256:" + hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(supplied_attestation, expected_attestation):
            issues.append(
                _issue(
                    str(artifact_path),
                    "local artifactAttestation does not match the execution report checksum",
                )
            )
    elif evidence.get("attestationAuthority") == "ci":
        if not _pc.ci_attestation_authority_available(
            commit=_commit_digest(evidence.get("commit"))
        ):
            issues.append(
                _issue(
                    str(artifact_path),
                    "CI attestation authority is unavailable; protected HMAC "
                    "verification was not performed",
                )
            )
        else:
            try:
                expected_attestation = sign_execution_report(raw)
            except ValueError as exc:
                issues.append(_issue(str(artifact_path), str(exc)))
            else:
                if not hmac.compare_digest(supplied_attestation, expected_attestation):
                    issues.append(
                        _issue(
                            str(artifact_path),
                            "artifactAttestation is not trusted for the immutable execution report",
                        )
                    )
    for field in (
        "adapterId",
        "capabilityId",
        "environment",
        "testLayer",
        "executionProfile",
        "status",
        "executedAt",
        "commit",
        "nonPromotable",
        "sourceTreeState",
        "commitReview",
        "candidateStatus",
        "candidateReceiptRef",
        "candidateReceiptDigest",
        "attestationAuthority",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "bindingRoots",
        "testArtifactRef",
        "testArtifactDigest",
        "testSourceDigest",
        "testTarget",
        "typedPort",
        "contractRef",
        "assertionIds",
        "networkBoundary",
        "dataDigest",
    ):
        if report.get(field) != evidence.get(field):
            issues.append(
                _issue(
                    str(artifact_path),
                    f"execution report {field} does not match evidence",
                )
            )
    if report.get("testSource") != (
        expected_source.get("testSource") if expected_source is not None else None
    ):
        issues.append(
            _issue(
                str(artifact_path),
                "execution report testSource does not match the discovered source contract",
            )
        )
    if not _is_non_empty_string(report.get("testCommand")):
        issues.append(_issue(str(artifact_path), "execution report testCommand is required"))
    if report.get("exitCode") != 0:
        issues.append(_issue(str(artifact_path), "execution report exitCode must be zero"))
    return issues


def _release_readiness_valid(item: Mapping[str, Any]) -> bool:
    release_readiness = item.get("releaseReadiness")
    return (
        isinstance(release_readiness, Mapping)
        and set(release_readiness) == RELEASE_READINESS_FIELDS
        and all(_valid_receipt_ref(release_readiness[field]) for field in RELEASE_READINESS_FIELDS)
    )

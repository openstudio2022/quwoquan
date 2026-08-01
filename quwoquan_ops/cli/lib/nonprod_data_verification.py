"""Run the canonical Alpha/Beta/Gamma API-only data recipes.

The input is evidence from already executed Provider/fault gates. It contains
no business objects and cannot override recipe shape, operation paths, or IDs.

spec_ref: specs/feature-tree/spec.md#uat-009
spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .common import write_json
from .nonprod_business_data import NONPROD_TARGETS
from .nonprod_data_provisioner import (
    NonprodCandidateIdentity,
    NonprodDataProvisioner,
)


INPUT_SCHEMA = "qwq.nonprod_acceptance_gate_evidence"
CASE_RESULT_SCHEMA = "qwq.case_result"
SPEC_REFS = (
    "specs/feature-tree/spec.md#uat-009",
    "specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001",
    "specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003",
)
_INPUT_FIELDS = {
    "schema",
    "baselineId",
    "packageDigest",
    "releaseDigest",
    "shareProviderReceiptIds",
    "providerConformance",
    "reliabilityEvidence",
}


def run_nonprod_business_data_verification(
    *,
    environment: str,
    target: str,
    base_url: str,
    candidate_manifest: Mapping[str, Any],
    release_readiness: Mapping[str, Any],
    evidence_path: Path,
    report_dir: Path,
) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    try:
        evidence = _load_gate_evidence(
            evidence_path,
            candidate_manifest=candidate_manifest,
        )
        candidate = _candidate_identity(
            environment=environment,
            target=target,
            manifest=candidate_manifest,
            readiness=release_readiness,
        )
        _validate_bound_gate_group(
            evidence["providerConformance"],
            required=("identityOtp", "assistantModel", "pushDelivery", "rtcMedia"),
            candidate=candidate,
            label="Provider conformance",
            require_provider=True,
        )
        _validate_bound_gate_group(
            evidence["reliabilityEvidence"],
            required=("expiredSession", "projectionDelay", "cleanupRecovery"),
            candidate=candidate,
            label="reliability fault",
            require_provider=False,
        )
        provisioner = NonprodDataProvisioner(
            base_url=base_url,
            candidate=candidate,
            share_provider_receipt_ids=tuple(evidence["shareProviderReceiptIds"]),
            provider_conformance_evidence=evidence["providerConformance"],
            reliability_evidence=evidence["reliabilityEvidence"],
        )
        receipts = [
            provisioner.provision_reference_identity(),
            provisioner.provision_reference_content_interaction(),
            provisioner.provision_reference_circle_chat(),
            provisioner.provision_reference_assistant_notification_rtc(),
            provisioner.run_paging_boundary(),
            provisioner.run_reliability_recovery(),
        ]
        _validate_receipt_closure(receipts, candidate)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        result = {
            "schema": CASE_RESULT_SCHEMA,
            "caseId": "alpha-beta-gamma-nonprod-business-data",
            "status": "GATE_BLOCK",
            "executed": 0,
            "skipped": 0,
            "target": target,
            "environment": environment,
            "specRefs": list(SPEC_REFS),
            "issues": [str(exc)],
        }
        write_json(report_dir / "case-result.json", result)
        return result

    result = {
        "schema": CASE_RESULT_SCHEMA,
        "caseId": "alpha-beta-gamma-nonprod-business-data",
        "status": "passed",
        "executed": len(receipts),
        "skipped": 0,
        "target": target,
        "environment": environment,
        "baselineId": candidate.baseline_id,
        "packageDigest": candidate.package_digest,
        "releaseId": candidate.release_id,
        "releaseDigest": candidate.release_digest,
        "datasetReceipts": [
            {
                "datasetId": str(receipt["datasetId"]),
                "datasetEpoch": str(receipt["datasetEpoch"]),
                "retentionClass": str(receipt["retentionClass"]),
                "cleanupState": str(receipt["cleanupState"]),
            }
            for receipt in receipts
        ],
        "specRefs": list(SPEC_REFS),
        "issues": [],
    }
    write_json(report_dir / "case-result.json", result)
    return result


def _load_gate_evidence(
    path: Path,
    *,
    candidate_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != _INPUT_FIELDS:
        raise ValueError("nonprod gate evidence fields mismatch")
    expected = {
        "schema": INPUT_SCHEMA,
        "baselineId": candidate_manifest.get("baselineId"),
        "packageDigest": candidate_manifest.get("packageDigest"),
        "releaseDigest": (
            (candidate_manifest.get("release") or {}).get("candidate") or {}
        ).get("releaseDigest"),
    }
    for name, value in expected.items():
        if payload.get(name) != value:
            raise ValueError(f"nonprod gate evidence {name} mismatch")
    share_receipts = payload.get("shareProviderReceiptIds")
    if (
        not isinstance(share_receipts, list)
        or len(share_receipts) != 3
        or len({str(item).strip() for item in share_receipts}) != 3
        or any(not str(item).strip() for item in share_receipts)
    ):
        raise ValueError("nonprod gate evidence requires three provider share receipts")
    for name in ("providerConformance", "reliabilityEvidence"):
        if not isinstance(payload.get(name), dict):
            raise ValueError(f"nonprod gate evidence {name} must be an object")
    forbidden = {
        "accesstoken",
        "refreshtoken",
        "authorization",
        "otpcode",
        "otpvalue",
        "phone",
        "phonenumber",
        "providersecret",
        "apisecret",
        "clientsecret",
    }
    for key in _walk_keys(payload):
        normalized = key.lower().replace("_", "")
        if normalized in forbidden:
            raise ValueError("nonprod gate evidence contains a forbidden secret field")
    return payload


def _candidate_identity(
    *,
    environment: str,
    target: str,
    manifest: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> NonprodCandidateIdentity:
    if NONPROD_TARGETS.get(target) != environment:
        raise ValueError("nonprod verification target/environment mismatch")
    release = (manifest.get("release") or {}).get("candidate") or {}
    release_id = str(release.get("releaseId") or "").strip()
    release_digest = str(release.get("releaseDigest") or "").strip()
    if (
        readiness.get("passed") is not True
        or readiness.get("environment") != environment
        or readiness.get("releaseId") != release_id
        or readiness.get("manifestDigest") != release_digest
    ):
        raise ValueError("Data readiness is not bound to the package candidate release")
    post_ids = readiness.get("postIds")
    if not isinstance(post_ids, list) or len(post_ids) != 3:
        raise ValueError("Data readiness must expose exactly three release post IDs")
    return NonprodCandidateIdentity(
        environment=environment,
        target=target,
        baseline_id=str(manifest.get("baselineId") or ""),
        source_revision=str(manifest.get("sourceRevision") or ""),
        package_digest=str(manifest.get("packageDigest") or ""),
        runtime_config_digest=str(manifest.get("runtimeConfigDigest") or ""),
        release_id=release_id,
        release_digest=release_digest,
        import_run_id=str(readiness.get("importRunId") or ""),
        release_post_ids=tuple(str(item).strip() for item in post_ids),
    )


def _validate_bound_gate_group(
    payload: Mapping[str, Any],
    *,
    required: tuple[str, ...],
    candidate: NonprodCandidateIdentity,
    label: str,
    require_provider: bool,
) -> None:
    for name in required:
        item = payload.get(name)
        if not isinstance(item, Mapping):
            raise ValueError(f"{label} evidence is required: {name}")
        attempt_id = str(item.get("attemptId") or "").strip()
        if (
            item.get("status") != "passed"
            or not attempt_id
            or attempt_id == "unknown"
            or item.get("baselineId") != candidate.baseline_id
            or item.get("packageDigest") != candidate.package_digest
            or not str(item.get("caseResultRef") or "").strip()
        ):
            raise ValueError(f"{label} evidence is invalid: {name}")
        network_boundary = str(item.get("networkBoundary") or "").strip()
        if network_boundary in {"", "in_process", "memory"}:
            raise ValueError(
                f"{label} evidence does not prove a real remote boundary: {name}"
            )
        if require_provider:
            adapter_id = str(item.get("adapterId") or "").strip()
            implementation_status = str(
                item.get("implementationStatus") or ""
            ).strip()
            if (
                not adapter_id
                or any(
                    token in adapter_id.lower()
                    for token in (
                        "fixture",
                        "mock",
                        "local_capture",
                        "local_recorder",
                    )
                )
                or implementation_status not in {"ready", "production", "sandbox"}
            ):
                raise ValueError(
                    f"{label} evidence does not prove a real non-memory Provider: {name}"
                )


def _validate_receipt_closure(
    receipts: list[dict[str, Any]],
    candidate: NonprodCandidateIdentity,
) -> None:
    if len(receipts) != 6:
        raise RuntimeError("nonprod dataset receipt closure is incomplete")
    for receipt in receipts:
        if (
            receipt.get("status") != "passed"
            or receipt.get("baselineId") != candidate.baseline_id
            or receipt.get("packageDigest") != candidate.package_digest
            or receipt.get("releaseDigest") != candidate.release_digest
        ):
            raise RuntimeError("nonprod dataset receipt candidate binding drift")
        retention = str(receipt.get("retentionClass") or "")
        cleanup = str(receipt.get("cleanupState") or "")
        if retention == "candidate_bound" and cleanup != "retained":
            raise RuntimeError("candidate-bound dataset was not retained")
        if retention == "run_bound" and cleanup != "cleaned":
            raise RuntimeError("run-bound dataset cleanup is incomplete")


def _walk_keys(value: object):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key)
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)

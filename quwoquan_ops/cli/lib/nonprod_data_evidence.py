"""Assemble candidate-bound non-production data prerequisites from real receipts.

The output is a disposable evidence bundle consumed by ``stackctl verify``. It
does not define business objects or copy wire schemas; every pass/fail claim is
revalidated from an explicit test-owned or Provider Conformance artifact.

spec_ref: specs/feature-tree/spec.md#uat-009
spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import external_provider_governance as governance
from . import provider_conformance
from .common import write_json
from .nonprod_data_verification import INPUT_SCHEMA


PROVIDER_CAPABILITIES = {
    "identityOtp": "identity.sms.otp",
    "assistantModel": "assistant.model.generation",
    "pushDelivery": "integration.push.delivery",
    "rtcMedia": "rtc.room.transport",
}
RELIABILITY_CASE_IDS = {
    "expiredSession": "nonprod-reliability-expired-session",
    "projectionDelay": "nonprod-reliability-projection-delay",
    "cleanupRecovery": "nonprod-reliability-cleanup-recovery",
}
SHARE_CASE_SCHEMA = "qwq.nonprod_share_delivery_case_result"
RELIABILITY_CASE_SCHEMA = "qwq.nonprod_reliability_case_result"
_BOUND_CASE_FIELDS = {
    "schema",
    "caseId",
    "status",
    "executed",
    "skipped",
    "target",
    "baselineId",
    "packageDigest",
    "releaseDigest",
    "attemptId",
    "networkBoundary",
    "specRefs",
    "telemetryReceipt",
}


def assemble_nonprod_gate_evidence(
    *,
    target: str,
    environment: str,
    candidate_manifest: Mapping[str, Any],
    share_receipt_refs: Sequence[str],
    provider_receipt_refs: Mapping[str, str],
    reliability_receipt_refs: Mapping[str, str],
    evidence_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Validate explicit receipts and write the sole integration input bundle."""

    expected = _candidate_binding(
        target=target,
        environment=environment,
        manifest=candidate_manifest,
    )
    if len(share_receipt_refs) != 3:
        raise ValueError("exactly three outbound-share delivery receipts are required")
    if set(provider_receipt_refs) != set(PROVIDER_CAPABILITIES):
        raise ValueError(
            "Provider receipt bindings must be exactly "
            + ",".join(PROVIDER_CAPABILITIES)
        )
    if set(reliability_receipt_refs) != set(RELIABILITY_CASE_IDS):
        raise ValueError(
            "reliability receipt bindings must be exactly "
            + ",".join(RELIABILITY_CASE_IDS)
        )

    share_receipts = [
        _load_bound_case(
            reference,
            expected=expected,
            evidence_root=evidence_root,
            schema=SHARE_CASE_SCHEMA,
            case_id="nonprod-outbound-share-delivery",
            require_provider_receipt=True,
        )
        for reference in share_receipt_refs
    ]
    provider_receipts = {
        name: _load_provider_receipt(
            reference,
            name=name,
            expected=expected,
            evidence_root=evidence_root,
        )
        for name, reference in provider_receipt_refs.items()
    }
    reliability_receipts = {
        name: _load_bound_case(
            reference,
            expected=expected,
            evidence_root=evidence_root,
            schema=RELIABILITY_CASE_SCHEMA,
            case_id=RELIABILITY_CASE_IDS[name],
            require_provider_receipt=False,
        )
        for name, reference in reliability_receipt_refs.items()
    }

    provider_receipt_ids = [
        str(receipt["providerReceiptId"]).strip() for receipt in share_receipts
    ]
    if len(set(provider_receipt_ids)) != 3:
        raise ValueError("outbound-share provider receipt IDs must be distinct")
    payload = {
        "schema": INPUT_SCHEMA,
        "baselineId": expected["baselineId"],
        "packageDigest": expected["packageDigest"],
        "releaseDigest": expected["releaseDigest"],
        "shareProviderReceiptIds": provider_receipt_ids,
        "providerConformance": provider_receipts,
        "reliabilityEvidence": reliability_receipts,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, payload)
    return payload


def _candidate_binding(
    *,
    target: str,
    environment: str,
    manifest: Mapping[str, Any],
) -> dict[str, str]:
    release = (manifest.get("release") or {}).get("candidate") or {}
    expected = {
        "target": target,
        "environment": environment,
        "baselineId": str(manifest.get("baselineId") or "").strip(),
        "packageDigest": str(manifest.get("packageDigest") or "").strip(),
        "releaseDigest": str(release.get("releaseDigest") or "").strip(),
        "sourceRevision": str(manifest.get("sourceRevision") or "").strip(),
        "imageDigest": str(manifest.get("imageDigest") or "").strip(),
    }
    if manifest.get("target") != target or manifest.get("environment") != environment:
        raise ValueError("candidate manifest target/environment mismatch")
    if any(not value for value in expected.values()):
        raise ValueError("candidate manifest is missing nonprod evidence identity")
    return expected


def _load_reference(reference: str, *, evidence_root: Path) -> tuple[Path, dict[str, Any]]:
    raw = str(reference or "").strip()
    if not raw:
        raise ValueError("evidence reference is required")
    root = evidence_root.expanduser().resolve()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        parts = path.parts
        if parts and parts[0] == ".qwq_output" and root.name == ".qwq_output":
            path = root.joinpath(*parts[1:])
        else:
            path = root / path
    path = path.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("evidence reference escapes QWQ_OUTPUT_ROOT") from exc
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"evidence root must be an object: {path}")
    return path, payload


def _reference(path: Path, *, evidence_root: Path) -> str:
    root = evidence_root.expanduser().resolve()
    return str(Path(".qwq_output") / path.resolve().relative_to(root))


def _validate_common_case(
    payload: Mapping[str, Any],
    *,
    expected: Mapping[str, str],
    schema: str,
    case_id: str,
) -> None:
    expected_fields = set(_BOUND_CASE_FIELDS)
    if schema == SHARE_CASE_SCHEMA:
        expected_fields.add("providerReceiptId")
    if set(payload) != expected_fields:
        raise ValueError(f"{case_id} CaseResult fields mismatch")
    if payload.get("schema") != schema or payload.get("caseId") != case_id:
        raise ValueError(f"{case_id} CaseResult schema/identity mismatch")
    for field in ("target", "baselineId", "packageDigest", "releaseDigest"):
        if payload.get(field) != expected[field]:
            raise ValueError(f"{case_id} CaseResult {field} mismatch")
    attempt_id = str(payload.get("attemptId") or "").strip()
    if (
        payload.get("status") != "passed"
        or int(payload.get("executed") or 0) <= 0
        or int(payload.get("skipped") or 0) != 0
        or not attempt_id
        or attempt_id == "unknown"
        or payload.get("networkBoundary") not in {"remote_protocol", "user_journey"}
        or not isinstance(payload.get("specRefs"), list)
        or not payload.get("specRefs")
        or not str(payload.get("telemetryReceipt") or "").strip()
    ):
        raise ValueError(f"{case_id} CaseResult did not execute a real remote case")


def _load_bound_case(
    reference: str,
    *,
    expected: Mapping[str, str],
    evidence_root: Path,
    schema: str,
    case_id: str,
    require_provider_receipt: bool,
) -> dict[str, Any]:
    path, payload = _load_reference(reference, evidence_root=evidence_root)
    _validate_common_case(
        payload,
        expected=expected,
        schema=schema,
        case_id=case_id,
    )
    provider_receipt_id = str(payload.get("providerReceiptId") or "").strip()
    if require_provider_receipt and not provider_receipt_id:
        raise ValueError("outbound-share CaseResult has no provider receipt ID")
    result = {
        "status": "passed",
        "attemptId": str(payload["attemptId"]),
        "baselineId": expected["baselineId"],
        "packageDigest": expected["packageDigest"],
        "caseResultRef": _reference(path, evidence_root=evidence_root),
        "networkBoundary": str(payload["networkBoundary"]),
    }
    if require_provider_receipt:
        result["providerReceiptId"] = provider_receipt_id
    return result


def _load_provider_receipt(
    reference: str,
    *,
    name: str,
    expected: Mapping[str, str],
    evidence_root: Path,
) -> dict[str, Any]:
    path, payload = _load_reference(reference, evidence_root=evidence_root)
    capability_id = PROVIDER_CAPABILITIES[name]
    if (
        payload.get("capabilityId") != capability_id
        or payload.get("environment") != expected["environment"]
        or payload.get("testLayer") != "user_acceptance"
        or payload.get("dataDigest") != expected["releaseDigest"]
    ):
        raise ValueError(f"Provider Conformance receipt identity mismatch: {name}")
    compiled, compile_issues = governance.load_and_compile()
    if compile_issues:
        raise ValueError("Provider governance is not compilable")
    sources, source_issues = provider_conformance.discover_test_sources()
    if source_issues:
        raise ValueError("Provider Conformance source catalog is invalid")
    evidence = {**payload, "_source": path}
    issues = provider_conformance.validate_evidence(
        [evidence],
        registry=governance.load_registry(),
        root=evidence_root,
        current_commit=expected["sourceRevision"],
        compiled=compiled,
        source_catalog=sources,
        expected_image_digest=expected["imageDigest"],
    )
    if issues:
        raise ValueError(f"Provider Conformance receipt invalid for {name}: {issues[0]}")
    adapter_id = str(payload.get("adapterId") or "")
    adapter = next(
        (
            row
            for row in governance.load_registry().get("adapters", [])
            if isinstance(row, Mapping) and row.get("adapter_id") == adapter_id
        ),
        None,
    )
    implementation_status = str((adapter or {}).get("implementation_status") or "")
    return {
        "status": "passed",
        "attemptId": str(payload.get("artifactDigest") or ""),
        "baselineId": expected["baselineId"],
        "packageDigest": expected["packageDigest"],
        "caseResultRef": str(payload.get("testArtifactRef") or ""),
        "adapterId": adapter_id,
        "implementationStatus": implementation_status,
        "networkBoundary": str(payload.get("networkBoundary") or ""),
        "sourceRef": _reference(path, evidence_root=evidence_root),
    }

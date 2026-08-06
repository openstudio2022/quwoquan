"""Bind scale evidence to one fenced runtime session and its receipts."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from content.release.canonical.campaign_scale_contract import (
    CampaignScaleEvidenceError,
    _canonical_digest,
    _file_sha256,
    _load_plan,
    _resolve_ref,
    _safe_ref,
    _timestamp,
    _validated,
    _write_create_once,
    campaign_source_revision,
)
from content.release.canonical.runtime_scale_resource_binding import (
    validate_resource_receipt,
)

FAULT_TYPES = (
    "worker_termination",
    "lease_expiry",
    "redis_restart",
    "mongo_reconnect",
    "provider_timeout",
    "provider_rate_limit",
)
_SESSION_KEYS = ("rootExecutionId", "runId", "generation", "fencingToken")
_SOURCE_KEYS = ("sourceRevision", "sourceDigest", "entityCatalogDigest")


def _receipt(
    path: Path,
    *,
    schema_name: str,
    digest_field: str,
    label: str,
) -> dict[str, Any]:
    payload = _validated(path, "execution", schema_name, label=label)
    if payload.get(digest_field) != _canonical_digest(
        payload, excluded=digest_field
    ):
        raise CampaignScaleEvidenceError(f"{label} digest drift")
    return payload


def _assert_exact_session_path(
    path: Path,
    *,
    plan_path: Path,
    session_id: str,
) -> None:
    if (
        path.name != "session.json"
        or path.parent.name != session_id
        or path.parent.parent.name != "evidence"
        or path.parent.parent.parent.name != "runtime"
        or path.parent.parent.parent.parent.resolve() != plan_path.parent.resolve()
    ):
        raise CampaignScaleEvidenceError(
            "runtime evidence session path is non-canonical for campaign plan"
        )


def _validate_hook_attestation(
    session: Mapping[str, Any], *, output_root: Path
) -> None:
    hook_ref = session.get("providerFaultTestHookAttestationRef")
    hook_sha = session.get("providerFaultTestHookAttestationSha256")
    provider_rows = [
        dict(row)
        for row in session.get("faultProviders") or []
        if isinstance(row, Mapping)
        and row.get("faultType") in {"provider_timeout", "provider_rate_limit"}
    ]
    if session.get("providerFaultTestHooksEnabled") is not True:
        raise CampaignScaleEvidenceError(
            "runtime scale session requires provider fault test-hook attestation"
        )
    if not hook_ref or not hook_sha:
        raise CampaignScaleEvidenceError("runtime provider fault attestation is missing")
    path = _resolve_ref(
        str(hook_ref), output_root=output_root, label="provider fault attestation"
    )
    if _file_sha256(path) != hook_sha:
        raise CampaignScaleEvidenceError("provider fault attestation file digest drift")
    attestation = _receipt(
        path,
        schema_name="runtime_provider_fault_test_hook_attestation",
        digest_field="attestationDigest",
        label="provider fault attestation",
    )
    if any(attestation.get(key) != session.get(key) for key in _SESSION_KEYS):
        raise CampaignScaleEvidenceError("provider fault attestation session drift")
    observed = sorted(
        attestation.get("providerBindings") or [],
        key=lambda row: str(row.get("faultType") or ""),
    )
    expected = sorted(provider_rows, key=lambda row: str(row["faultType"]))
    if observed != expected:
        raise CampaignScaleEvidenceError("provider fault attestation binding drift")
    issued = _timestamp(attestation["issuedAt"], label="provider hook issuedAt")
    expires = _timestamp(attestation["expiresAt"], label="provider hook expiresAt")
    created = _timestamp(session["createdAt"], label="runtime session createdAt")
    if not issued <= created < expires:
        raise CampaignScaleEvidenceError(
            "provider fault attestation was not valid when session was created"
        )


def _load_session(
    *,
    runtime_session_path: Path,
    campaign_plan_path: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    session = _receipt(
        runtime_session_path,
        schema_name="runtime_evidence_session",
        digest_field="receiptDigest",
        label="runtime evidence session",
    )
    _safe_ref(
        runtime_session_path,
        output_root=output_root,
        label="runtime evidence session",
    )
    _assert_exact_session_path(
        runtime_session_path,
        plan_path=campaign_plan_path,
        session_id=str(session["sessionId"]),
    )
    plan = _load_plan(campaign_plan_path)
    plan_ref = _resolve_ref(
        str(session["campaignPlanRef"]),
        output_root=output_root,
        label="runtime session campaign plan ref",
    )
    if (
        plan_ref.resolve() != campaign_plan_path.resolve()
        or _file_sha256(campaign_plan_path) != session.get("campaignPlanSha256")
    ):
        raise CampaignScaleEvidenceError("runtime session campaign plan binding drift")
    expected = {
        "rootExecutionId": plan["rootExecutionId"],
        "sourceRevision": campaign_source_revision(plan),
        "sourceDigest": plan["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
    }
    if any(session.get(key) != value for key, value in expected.items()):
        raise CampaignScaleEvidenceError("runtime session campaign identity drift")
    controller = session.get("controller")
    if (
        not isinstance(controller, Mapping)
        or controller.get("role") != "controller"
        or controller.get("executionId") != plan["rootExecutionId"]
    ):
        raise CampaignScaleEvidenceError("runtime session controller binding drift")
    workers = {
        str(row.get("carrier")): str(row.get("executionId"))
        for row in session.get("workers") or []
        if isinstance(row, Mapping)
    }
    if workers != plan.get("executionIds"):
        raise CampaignScaleEvidenceError("runtime session lane binding drift")
    fault_types = [
        str(row.get("faultType"))
        for row in session.get("faultProviders") or []
        if isinstance(row, Mapping)
    ]
    if len(fault_types) != len(set(fault_types)) or set(fault_types) != set(
        FAULT_TYPES
    ):
        raise CampaignScaleEvidenceError(
            "runtime scale session must freeze all six unique fault providers"
        )
    _validate_hook_attestation(session, output_root=output_root)
    return session, plan


def _expected_receipt_identity(
    session: Mapping[str, Any], *, session_ref: str
) -> dict[str, Any]:
    return {
        "sessionRef": session_ref,
        "sessionDigest": session["receiptDigest"],
        **{key: session[key] for key in _SESSION_KEYS},
    }


def _sample_projection(
    *,
    session: Mapping[str, Any],
    session_path: Path,
    plan: Mapping[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    session_ref = _safe_ref(
        session_path, output_root=output_root, label="runtime evidence session"
    )
    expected_identity = _expected_receipt_identity(session, session_ref=session_ref)
    receipts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_digests: set[str] = set()
    seen_instants: set[datetime] = set()
    for path in sorted((session_path.parent / "samples").glob("*.json")):
        receipt = _receipt(
            path,
            schema_name="runtime_resource_sample_receipt",
            digest_field="receiptDigest",
            label=f"runtime resource sample:{path}",
        )
        sample_id = str(receipt["sampleId"])
        instant = _timestamp(receipt["capturedAt"], label=f"sample:{sample_id}")
        digest = str(receipt["receiptDigest"])
        if (
            path.stem != sample_id
            or any(receipt.get(key) != value for key, value in expected_identity.items())
        ):
            raise CampaignScaleEvidenceError("resource sample/session identity drift")
        if sample_id in seen_ids or digest in seen_digests or instant in seen_instants:
            raise CampaignScaleEvidenceError(
                "resource sample receipts contain duplicate identity or timestamp"
            )
        validate_resource_receipt(receipt, session=session, plan=plan)
        seen_ids.add(sample_id)
        seen_digests.add(digest)
        seen_instants.add(instant)
        receipts.append(
            {
                "sampleId": sample_id,
                "capturedAt": receipt["capturedAt"],
                "receiptRef": _safe_ref(
                    path, output_root=output_root, label=f"resource sample:{sample_id}"
                ),
                "receiptDigest": digest,
            }
        )
    if len(receipts) < 2:
        raise CampaignScaleEvidenceError("runtime session has fewer than two samples")
    ordered = sorted(receipts, key=lambda row: _timestamp(row["capturedAt"], label="sample"))
    receipt_by_id = {
        str(row["sampleId"]): _receipt(
            _resolve_ref(
                str(row["receiptRef"]), output_root=output_root, label="sample receipt"
            ),
            schema_name="runtime_resource_sample_receipt",
            digest_field="receiptDigest",
            label=f"runtime sample:{row['sampleId']}",
        )
        for row in ordered
    }
    return {
        "schema": "quwoquan_data.resource_soak_samples",
        "runtimeSessionId": session["sessionId"],
        "runtimeSessionRef": session_ref,
        "runtimeSessionDigest": session["receiptDigest"],
        **{key: session[key] for key in _SESSION_KEYS},
        **{key: session[key] for key in _SOURCE_KEYS},
        "sampleReceipts": ordered,
        "samples": [receipt_by_id[str(row["sampleId"])]["rawSample"] for row in ordered],
    }


def _validate_fault_request(
    receipt: Mapping[str, Any],
    *,
    case_root: Path,
    session: Mapping[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    request_path = _resolve_ref(
        str(receipt["requestRef"]), output_root=output_root, label="fault request"
    )
    if request_path.resolve() != (case_root / "request.json").resolve():
        raise CampaignScaleEvidenceError("fault request path is non-canonical")
    request = _receipt(
        request_path,
        schema_name="runtime_fault_request",
        digest_field="requestDigest",
        label=f"runtime fault request:{receipt['caseId']}",
    )
    expected = {
        "caseId": receipt["caseId"],
        "sessionRef": receipt["sessionRef"],
        "sessionDigest": session["receiptDigest"],
        **{key: session[key] for key in _SESSION_KEYS},
        "faultType": receipt["faultType"],
        "carrier": receipt["carrier"],
        "executionId": receipt["executionId"],
        "jobId": receipt["jobId"],
    }
    if receipt.get("requestDigest") != request.get("requestDigest") or any(
        request.get(key) != value for key, value in expected.items()
    ):
        raise CampaignScaleEvidenceError("fault request/receipt identity drift")
    bindings = [
        row
        for row in session["faultProviders"]
        if row["faultType"] == receipt["faultType"]
    ]
    if (
        len(bindings) != 1
        or request.get("providerId") != bindings[0]["providerId"]
        or request.get("providerConfigurationDigest")
        != bindings[0]["configurationDigest"]
    ):
        raise CampaignScaleEvidenceError("fault request provider binding drift")
    return request


def _validate_triggered_fault(
    receipt: Mapping[str, Any], *, case_root: Path, output_root: Path
) -> dict[str, Any]:
    event_path = _resolve_ref(
        str(receipt["eventRef"]), output_root=output_root, label="fault event"
    )
    if event_path.resolve() != (case_root / "event.json").resolve():
        raise CampaignScaleEvidenceError("fault event path is non-canonical")
    if _file_sha256(event_path) != receipt.get("eventSha256"):
        raise CampaignScaleEvidenceError("fault injection event digest drift")
    event = _validated(
        event_path,
        "release",
        "fault_injection_event",
        label=f"runtime fault event:{receipt['caseId']}",
    )
    expected = {
        "schema": "quwoquan_data.fault_injection_event",
        "caseId": receipt["caseId"],
        "faultType": receipt["faultType"],
        "carrier": receipt["carrier"],
        "executionId": receipt["executionId"],
        "jobId": receipt["jobId"],
        "triggeredAt": receipt["faultEventAt"],
    }
    if event != expected or receipt.get("queueEventEvidenceDigest") is None:
        raise CampaignScaleEvidenceError("fault event/receipt identity drift")
    provider_ref = receipt.get("providerEvidenceRef")
    provider_sha = receipt.get("providerEvidenceSha256")
    if receipt["faultType"] != "worker_termination" and not provider_ref:
        raise CampaignScaleEvidenceError("fault provider evidence is missing")
    if (provider_ref is None) != (provider_sha is None):
        raise CampaignScaleEvidenceError("fault provider evidence binding drift")
    if provider_ref is not None:
        provider_path = _resolve_ref(
            str(provider_ref), output_root=output_root, label="fault provider evidence"
        )
        if _file_sha256(provider_path) != provider_sha:
            raise CampaignScaleEvidenceError("fault provider evidence digest drift")
    return {
        "caseId": receipt["caseId"],
        "faultType": receipt["faultType"],
        "carrier": receipt["carrier"],
        "executionId": receipt["executionId"],
        "jobId": receipt["jobId"],
        "faultEventAt": receipt["faultEventAt"],
        "injectionEvidenceRef": receipt["eventRef"],
        "injectionEvidenceSha256": receipt["eventSha256"],
    }


def _fault_projection(
    *, session: Mapping[str, Any], session_path: Path, output_root: Path
) -> dict[str, Any]:
    session_ref = _safe_ref(
        session_path, output_root=output_root, label="runtime evidence session"
    )
    expected_identity = _expected_receipt_identity(session, session_ref=session_ref)
    execution_ids = {
        str(row["carrier"]): str(row["executionId"]) for row in session["workers"]
    }
    rows: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_receipts: set[str] = set()
    seen_requests: set[str] = set()
    seen_events: set[tuple[str, str]] = set()
    for path in sorted((session_path.parent / "faults").glob("*/receipt.json")):
        receipt = _receipt(
            path,
            schema_name="runtime_fault_case_receipt",
            digest_field="receiptDigest",
            label=f"runtime fault case:{path}",
        )
        case_id = str(receipt["caseId"])
        receipt_digest = str(receipt["receiptDigest"])
        if (
            path.parent.name != case_id
            or any(receipt.get(key) != value for key, value in expected_identity.items())
            or receipt.get("executionId") != execution_ids.get(str(receipt["carrier"]))
        ):
            raise CampaignScaleEvidenceError("fault case/session identity drift")
        _validate_fault_request(
            receipt,
            case_root=path.parent,
            session=session,
            output_root=output_root,
        )
        request_digest = str(receipt["requestDigest"])
        if (
            case_id in seen_ids
            or receipt_digest in seen_receipts
            or request_digest in seen_requests
        ):
            raise CampaignScaleEvidenceError("fault receipts contain duplicate identity")
        seen_ids.add(case_id)
        seen_receipts.add(receipt_digest)
        seen_requests.add(request_digest)
        if receipt["actionStatus"] == "triggered":
            case = _validate_triggered_fault(
                receipt, case_root=path.parent, output_root=output_root
            )
            event_key = (str(case["jobId"]), str(case["faultEventAt"]))
            if event_key in seen_events:
                raise CampaignScaleEvidenceError("fault cases reuse one queue event")
            seen_events.add(event_key)
            cases.append(case)
        elif any(
            receipt.get(key) is not None
            for key in (
                "faultEventAt",
                "eventRef",
                "eventSha256",
                "queueEventEvidenceDigest",
            )
        ):
            raise CampaignScaleEvidenceError("failed fault receipt contains success evidence")
        rows.append(
            {
                "caseId": case_id,
                "actionStatus": receipt["actionStatus"],
                "receiptRef": _safe_ref(
                    path, output_root=output_root, label=f"fault receipt:{case_id}"
                ),
                "receiptDigest": receipt_digest,
                "requestDigest": request_digest,
            }
        )
    return {
        "schema": "quwoquan_data.fault_injection_cases",
        "runtimeSessionId": session["sessionId"],
        "runtimeSessionRef": session_ref,
        "runtimeSessionDigest": session["receiptDigest"],
        **{key: session[key] for key in _SESSION_KEYS},
        **{key: session[key] for key in _SOURCE_KEYS},
        "faultCaseReceipts": rows,
        "cases": cases,
    }


def materialize_bound_runtime_inputs(
    *,
    runtime_session_path: Path,
    campaign_plan_path: Path,
    evidence_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], Path, Path]:
    """Create immutable release-facing projections from exact runtime receipts."""
    session, plan = _load_session(
        runtime_session_path=runtime_session_path,
        campaign_plan_path=campaign_plan_path,
        output_root=output_root,
    )
    samples = _sample_projection(
        session=session,
        session_path=runtime_session_path,
        plan=plan,
        output_root=output_root,
    )
    faults = _fault_projection(
        session=session,
        session_path=runtime_session_path,
        output_root=output_root,
    )
    input_root = evidence_root / "runtime-input"
    _sample_document, sample_path = _write_create_once(
        path=input_root / "resource-soak-samples.json",
        stable=samples,
        schema_name="resource_soak_samples",
    )
    _fault_document, fault_path = _write_create_once(
        path=input_root / "fault-injection-cases.json",
        stable=faults,
        schema_name="fault_injection_cases",
    )
    return session, sample_path, fault_path


def runtime_binding_fields(
    session: Mapping[str, Any], *, session_path: Path, output_root: Path
) -> dict[str, Any]:
    """Project the exact fenced session identity into canonical evidence."""
    return {
        "runtimeSessionId": session["sessionId"],
        "runtimeSessionRef": _safe_ref(
            session_path, output_root=output_root, label="runtime session"
        ),
        "runtimeSessionDigest": session["receiptDigest"],
        "runId": session["runId"],
        "generation": session["generation"],
        "fencingToken": session["fencingToken"],
    }


def documents_match_runtime_binding(
    documents: tuple[Mapping[str, Any], ...],
    session: Mapping[str, Any],
    *,
    session_path: Path,
    output_root: Path,
) -> bool:
    expected = runtime_binding_fields(
        session, session_path=session_path, output_root=output_root
    )
    return all(
        document.get(key) == value
        for document in documents
        for key, value in expected.items()
    )


__all__ = ["FAULT_TYPES", "documents_match_runtime_binding", "materialize_bound_runtime_inputs", "runtime_binding_fields"]

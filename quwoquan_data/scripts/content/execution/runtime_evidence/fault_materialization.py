"""Validate typed fault receipts and freeze release-facing raw cases."""
from __future__ import annotations

import fcntl
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.runtime_evidence.contract import (
    RuntimeEvidenceError,
    RuntimeEvidenceIdentity,
    canonical_digest,
    file_digest,
    load_runtime_evidence_session,
    resolve_ref,
    session_root,
)


def load_fault_receipt(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise RuntimeEvidenceError(f"fault case receipt must be an object: {path}")
    assert_valid(
        payload,
        "execution",
        "runtime_fault_case_receipt",
        label=f"runtime fault case:{path}",
    )
    if payload.get("receiptDigest") != canonical_digest(
        payload, excluded="receiptDigest"
    ):
        raise RuntimeEvidenceError(f"fault case receipt digest drift: {path}")
    return payload


def _write_raw_cases_once(path: Path, raw: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / f".{path.name}.lock").open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if path.is_file():
            if read_json(path) != dict(raw):
                raise RuntimeEvidenceError(f"raw fault cases collision: {path}")
            return
        assert_valid(raw, "release", "fault_injection_cases", label=str(path))
        write_json(path, dict(raw))


def _validate_event(
    receipt: Mapping[str, Any], *, output_root: Path
) -> None:
    event_path = resolve_ref(str(receipt["eventRef"]), output_root=output_root)
    if file_digest(event_path) != receipt["eventSha256"]:
        raise RuntimeEvidenceError("fault event digest drift")
    event = read_json(event_path)
    assert_valid(
        event,
        "release",
        "fault_injection_event",
        label=f"runtime fault event:{event_path}",
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
    if event != expected:
        raise RuntimeEvidenceError("fault event/receipt identity drift")


def _validate_request(
    receipt: Mapping[str, Any],
    *,
    session: Mapping[str, Any],
    identity: RuntimeEvidenceIdentity,
    output_root: Path,
) -> None:
    request_path = resolve_ref(str(receipt["requestRef"]), output_root=output_root)
    request = read_json(request_path)
    assert_valid(
        request,
        "execution",
        "runtime_fault_request",
        label=f"runtime fault request:{request_path}",
    )
    if request.get("requestDigest") != receipt["requestDigest"] or request.get(
        "requestDigest"
    ) != canonical_digest(request, excluded="requestDigest"):
        raise RuntimeEvidenceError("fault request digest drift")
    expected = {
        "caseId": receipt["caseId"],
        "sessionRef": receipt["sessionRef"],
        "sessionDigest": session["receiptDigest"],
        **identity.as_document(),
        "faultType": receipt["faultType"],
        "carrier": receipt["carrier"],
        "executionId": receipt["executionId"],
        "jobId": receipt["jobId"],
    }
    if any(request.get(key) != value for key, value in expected.items()):
        raise RuntimeEvidenceError("fault request/receipt identity drift")
    bindings = [
        row
        for row in session["faultProviders"]
        if row["faultType"] == receipt["faultType"]
    ]
    if len(bindings) != 1 or request.get("providerId") != bindings[0][
        "providerId"
    ] or request.get("providerConfigurationDigest") != bindings[0][
        "configurationDigest"
    ]:
        raise RuntimeEvidenceError("fault request provider binding drift")


def _validate_provider_evidence(
    receipt: Mapping[str, Any], *, output_root: Path
) -> None:
    provider_ref = receipt.get("providerEvidenceRef")
    provider_sha = receipt.get("providerEvidenceSha256")
    if (provider_ref is None) != (provider_sha is None):
        raise RuntimeEvidenceError("fault provider evidence ref/digest mismatch")
    if provider_ref is None:
        return
    provider_path = resolve_ref(str(provider_ref), output_root=output_root)
    if file_digest(provider_path) != provider_sha:
        raise RuntimeEvidenceError("fault provider evidence digest drift")


def validate_fault_receipt_binding(
    receipt: Mapping[str, Any],
    *,
    session: Mapping[str, Any],
    identity: RuntimeEvidenceIdentity,
    output_root: Path,
) -> None:
    """Revalidate an existing case before treating create-once replay as success."""
    if receipt.get("sessionDigest") != session.get("receiptDigest") or any(
        receipt.get(key) != value for key, value in identity.as_document().items()
    ):
        raise RuntimeEvidenceError("fault case/session identity drift")
    _validate_request(
        receipt,
        session=session,
        identity=identity,
        output_root=output_root,
    )
    _validate_provider_evidence(receipt, output_root=output_root)
    if receipt.get("actionStatus") == "triggered":
        _validate_event(receipt, output_root=output_root)


def finalize_fault_cases(
    *,
    runtime: CampaignRuntimePaths,
    identity: RuntimeEvidenceIdentity,
    session_id: str,
) -> tuple[dict[str, Any], Path]:
    """Project successful case receipts into the existing raw release schema."""
    session = load_runtime_evidence_session(
        runtime, identity, session_id, require_active_lease=False
    )
    case_root = session_root(runtime, identity, session_id) / "faults"
    receipts = [
        load_fault_receipt(path)
        for path in sorted(case_root.glob("*/receipt.json"))
    ]
    cases: list[dict[str, Any]] = []
    seen_events: set[tuple[str, str]] = set()
    for receipt in (row for row in receipts if row["actionStatus"] == "triggered"):
        validate_fault_receipt_binding(
            receipt,
            session=session,
            identity=identity,
            output_root=runtime.output_root,
        )
        event_key = (str(receipt["jobId"]), str(receipt["faultEventAt"]))
        if event_key in seen_events:
            raise RuntimeEvidenceError("fault cases reuse one queue event")
        seen_events.add(event_key)
        cases.append(
            {
                "caseId": receipt["caseId"],
                "faultType": receipt["faultType"],
                "carrier": receipt["carrier"],
                "executionId": receipt["executionId"],
                "jobId": receipt["jobId"],
                "faultEventAt": receipt["faultEventAt"],
                "injectionEvidenceRef": receipt["eventRef"],
                "injectionEvidenceSha256": receipt["eventSha256"],
            }
        )
    raw = {
        "schema": "quwoquan_data.fault_injection_cases",
        "rootExecutionId": identity.root_execution_id,
        "sourceRevision": session["sourceRevision"],
        "sourceDigest": session["sourceDigest"],
        "entityCatalogDigest": session["entityCatalogDigest"],
        "cases": cases,
    }
    path = session_root(runtime, identity, session_id) / "raw/fault-injection-cases.json"
    _write_raw_cases_once(path, raw)
    return raw, path


__all__ = [
    "finalize_fault_cases",
    "load_fault_receipt",
    "validate_fault_receipt_binding",
]

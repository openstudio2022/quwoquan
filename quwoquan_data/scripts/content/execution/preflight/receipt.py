"""Create-once, digest-bound evidence for one semantic preflight selection."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid

from content.execution.preflight.evidence import compact_ready_evidence
from content.execution.preflight.selection import (
    SemanticPreflightSelection,
    semantic_selection_document_digest,
)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _create_once_intent(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Project the immutable probe intent without writer-owned timestamps."""

    return {
        key: value
        for key, value in receipt.items()
        if key not in {"receiptId", "recordedAt", "validUntil"}
    }


def build_semantic_preflight_receipt(
    *,
    selection: SemanticPreflightSelection,
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind readiness to the exact policy/profile/provider/model/runtime tuple."""

    evidence = compact_ready_evidence(report)
    expected_selection = selection.document()
    if any(evidence.get(key) != value for key, value in expected_selection.items()):
        raise ValueError("semantic preflight evidence selection does not match resolver")
    if evidence.get("selectionDigest") != selection.selection_digest:
        raise ValueError("semantic preflight evidence selectionDigest does not match resolver")
    if evidence.get("fallbackPolicy") != "forbidden":
        raise ValueError("semantic preflight evidence fallbackPolicy must be forbidden")
    soak_requested = bool(report.get("soakRequested"))
    workspace_requested = bool(report.get("workspaceSmokeRequested"))
    preflight_ready = bool((report.get("preflight") or {}).get("ready"))
    capacity_ready = bool((report.get("capacitySoak") or {}).get("ready"))
    workspace_ready = bool((report.get("workspaceSmoke") or {}).get("ready"))
    fleet = evidence.get("reliableTaskFleet")
    fleet_ready = bool(
        isinstance(fleet, Mapping)
        and fleet.get("checked") is True
        and fleet.get("ready") is True
        and fleet.get("mongo") is True
        and fleet.get("redis") is True
        and fleet.get("owned") is True
    )
    overall_ready = bool(report.get("ready"))
    if overall_ready and not fleet_ready:
        raise ValueError(
            "semantic preflight overall ready requires writable ReliableTask fleet"
        )
    if overall_ready and not preflight_ready:
        raise ValueError(
            "semantic preflight overall ready requires preflightReady"
        )
    if overall_ready and soak_requested and not capacity_ready:
        raise ValueError(
            "semantic preflight overall ready requires capacitySoakReady"
        )
    if overall_ready and workspace_requested and not workspace_ready:
        raise ValueError(
            "semantic preflight overall ready requires workspaceSmokeReady"
        )
    recorded_at = datetime.now(timezone.utc).replace(microsecond=0)
    valid_until = recorded_at + timedelta(
        seconds=active_runtime_policy().semantic_capacity.receipt_ttl_seconds
    )
    stable = {
        "schema": "quwoquan_data.semantic_preflight_receipt",
        "recordedAt": recorded_at.isoformat().replace("+00:00", "Z"),
        "validUntil": valid_until.isoformat().replace("+00:00", "Z"),
        **selection.document(),
        "selectionDigest": selection.selection_digest,
        "fallbackPolicy": "forbidden",
        "startupRequested": bool(report.get("startupRequested")),
        "soakRequested": soak_requested,
        "workspaceSmokeRequested": workspace_requested,
        "preflightReady": preflight_ready,
        "capacitySoakReady": capacity_ready,
        "workspaceSmokeReady": workspace_ready,
        "ready": overall_ready,
        "executionAdmissionReady": (
            overall_ready
            and preflight_ready
            and fleet_ready
            and soak_requested
            and capacity_ready
        ),
        "evidenceDigest": _digest(evidence),
        "evidence": evidence,
    }
    receipt = {"receiptId": _digest(stable), **stable}
    assert_valid(
        receipt,
        "execution",
        "semantic_preflight_receipt",
        label=f"semantic preflight receipt:{selection.selection_id}",
    )
    return receipt


def validate_semantic_preflight_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_selection: SemanticPreflightSelection | None = None,
    require_execution_admission: bool = False,
    now: datetime | None = None,
) -> None:
    payload = dict(receipt)
    assert_valid(
        payload,
        "execution",
        "semantic_preflight_receipt",
        label="semantic preflight receipt",
    )
    evidence = payload["evidence"]
    if _digest(evidence) != payload["evidenceDigest"]:
        raise ValueError("semantic preflight receipt evidenceDigest mismatch")
    selection_document = {
        key: payload[key]
        for key in (
            "semanticSelectionId",
            "provider",
            "model",
            "modelParameters",
            "semanticRuntime",
            "runtimeProfileId",
            "runtimeProfileDigest",
            "requiresNewRetryOf",
        )
    }
    if semantic_selection_document_digest(selection_document) != payload["selectionDigest"]:
        raise ValueError("semantic preflight receipt selectionDigest mismatch")
    stable = {key: value for key, value in payload.items() if key != "receiptId"}
    if _digest(stable) != payload["receiptId"]:
        raise ValueError("semantic preflight receipt receiptId mismatch")
    recorded_at = _timestamp(payload["recordedAt"], label="recordedAt")
    valid_until = _timestamp(payload["validUntil"], label="validUntil")
    if valid_until <= recorded_at:
        raise ValueError("semantic preflight receipt validity window is invalid")
    if require_execution_admission:
        observed_now = now or datetime.now(timezone.utc)
        if observed_now < recorded_at or observed_now > valid_until:
            raise ValueError("semantic preflight receipt is outside its validity window")
    if any(evidence.get(key) != value for key, value in selection_document.items()):
        raise ValueError("semantic preflight receipt evidence selection mismatch")
    if evidence.get("selectionDigest") != payload["selectionDigest"]:
        raise ValueError("semantic preflight receipt evidence selectionDigest mismatch")
    if evidence.get("fallbackPolicy") != "forbidden":
        raise ValueError("semantic preflight receipt evidence fallbackPolicy mismatch")
    startup = evidence.get("semanticAgentStartup")
    if payload["startupRequested"] and (
        not isinstance(startup, Mapping)
        or (
            startup.get("provider") != payload["provider"]
            or startup.get("model") != payload["model"]
            or startup.get("runtime") != payload["semanticRuntime"]
            or not startup.get("checked")
            or (bool(payload["preflightReady"]) and not bool(startup.get("ready")))
        )
    ):
        raise ValueError("semantic preflight receipt startup binding mismatch")
    capacity = evidence.get("capacitySoak")
    if payload["soakRequested"] and (
        not isinstance(capacity, Mapping)
        or (
            capacity.get("semanticSelectionId") != payload["semanticSelectionId"]
            or capacity.get("selectionDigest") != payload["selectionDigest"]
            or capacity.get("provider") != payload["provider"]
            or capacity.get("model") != payload["model"]
            or capacity.get("modelParameters") != payload["modelParameters"]
            or capacity.get("runtimeProfileDigest") != payload["runtimeProfileDigest"]
            or bool(capacity.get("ready")) is not bool(payload["capacitySoakReady"])
        )
    ):
        raise ValueError("semantic preflight receipt capacity binding mismatch")
    fleet = evidence.get("reliableTaskFleet")
    fleet_ready = bool(
        isinstance(fleet, Mapping)
        and fleet.get("checked") is True
        and fleet.get("ready") is True
        and fleet.get("mongo") is True
        and fleet.get("redis") is True
        and fleet.get("owned") is True
    )
    if payload["ready"] and (
        not payload["preflightReady"]
        or not fleet_ready
        or (payload["soakRequested"] and not payload["capacitySoakReady"])
        or (
            payload["workspaceSmokeRequested"]
            and not payload["workspaceSmokeReady"]
        )
    ):
        raise ValueError("semantic preflight receipt overall readiness is inconsistent")
    expected_admission = bool(
        payload["ready"]
        and payload["preflightReady"]
        and fleet_ready
        and payload["soakRequested"]
        and payload["capacitySoakReady"]
    )
    if payload["executionAdmissionReady"] is not expected_admission:
        raise ValueError("semantic preflight receipt execution admission is inconsistent")
    if expected_selection is not None:
        if selection_document != expected_selection.document():
            raise ValueError("semantic preflight receipt does not match expected selection")
        if payload["selectionDigest"] != expected_selection.selection_digest:
            raise ValueError("semantic preflight receipt selection is stale")
    if require_execution_admission and not payload["executionAdmissionReady"]:
        raise ValueError("semantic preflight receipt is not execution-admission ready")


def _timestamp(value: object, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"semantic preflight receipt {label} is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"semantic preflight receipt {label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def write_semantic_preflight_receipt(
    path: Path,
    receipt: Mapping[str, Any],
) -> Path:
    """Write once atomically; an existing path must contain the exact receipt."""

    destination = path.expanduser().resolve()
    validate_semantic_preflight_receipt(receipt)
    body = _canonical_bytes(receipt)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if destination.read_bytes() != body:
            try:
                existing = json.loads(destination.read_text(encoding="utf-8"))
                if not isinstance(existing, Mapping):
                    raise TypeError("existing receipt must be an object")
                validate_semantic_preflight_receipt(existing)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                raise FileExistsError(
                    "semantic preflight receipt create-once conflict with invalid "
                    f"existing evidence: {destination}"
                ) from None
            if _create_once_intent(existing) != _create_once_intent(receipt):
                raise FileExistsError(
                    f"semantic preflight receipt create-once conflict: {destination}"
                ) from None
        return destination
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


__all__ = [
    "build_semantic_preflight_receipt",
    "validate_semantic_preflight_receipt",
    "write_semantic_preflight_receipt",
]

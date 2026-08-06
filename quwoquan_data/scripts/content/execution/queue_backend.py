"""Create-once queue backend binding for immutable execution inputs."""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.control_types import QueueBackend
from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution import store
from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.runtime_evidence_reliabletask_process import (
    load_frozen_observer_binary_binding,
    prepare_controller_observer_binary,
)
from content.execution.workspace import (
    execution_root,
    load_frozen_execution_manifest,
)

QUEUE_BACKEND_ENVELOPE_SCHEMA = "quwoquan_data.execution_queue_backend_envelope"
QUEUE_BACKEND_ENVELOPE_REF = "0.plan/queue_backend_envelope.json"
_M_SCALE_RE = re.compile(r"^m(?P<count>[0-9]+)$")


def queue_backend_envelope_path(execution_id: str) -> Path:
    return execution_root(validate_execution_id(execution_id)) / QUEUE_BACKEND_ENVELOPE_REF


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _approved_quota(spec: Mapping[str, Any]) -> int:
    policy = spec.get("executionPolicy")
    policy = policy if isinstance(policy, Mapping) else {}
    value = policy.get("approvedQuota")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("executionPolicy.approvedQuota is required for queue binding")
    return value


def _m100_plus(execution_id: str, spec: Mapping[str, Any]) -> bool:
    identity = parse_execution_id(execution_id)
    match = _M_SCALE_RE.fullmatch(identity.intent)
    intent_scale = int(match.group("count")) if match else 0
    return max(intent_scale, _approved_quota(spec)) >= 100


def _queue_policy(spec: Mapping[str, Any]) -> dict[str, Any]:
    policy = spec.get("queuePolicy")
    if not isinstance(policy, Mapping):
        raise TypeError("execution queuePolicy is required")
    backend = str(policy.get("backend") or "").strip()
    try:
        QueueBackend(backend)
    except ValueError as exc:
        raise ValueError(f"execution queuePolicy.backend is invalid: {backend}") from exc
    return dict(policy)


def freeze_execution_queue_backend(
    execution_id: str,
    *,
    spec: Mapping[str, Any] | None = None,
    manifest: Mapping[str, Any] | None = None,
) -> Path:
    """Bind the effective queue policy to the immutable execution manifest."""
    normalized = validate_execution_id(execution_id)
    effective_spec = dict(spec) if spec is not None else store.load_spec(normalized)
    frozen_manifest = (
        dict(manifest)
        if manifest is not None
        else load_frozen_execution_manifest(normalized)
    )
    if str(frozen_manifest.get("executionId") or "") != normalized:
        raise ValueError("queue backend manifest executionId mismatch")
    policy = _queue_policy(effective_spec)
    backend = QueueBackend(str(policy["backend"]))
    approved_quota = _approved_quota(effective_spec)
    scale_class = "M100_PLUS" if _m100_plus(normalized, effective_spec) else "BELOW_M100"
    if scale_class == "M100_PLUS" and backend is not QueueBackend.RELIABLE_TASK:
        raise ValueError(
            "M100+ immutable queue backend must be reliabletask; "
            f"observed {backend.value}"
        )
    observer_binding: dict[str, str] = {}
    if backend is QueueBackend.RELIABLE_TASK:
        if str(os.environ.get("QWQ_CAMPAIGN_ROOT_EXECUTION_ID") or "").strip():
            binding = load_frozen_observer_binary_binding()
        else:
            binding = prepare_controller_observer_binary().binding
        observer_binding = binding.as_document()
    stable = {
        "schema": QUEUE_BACKEND_ENVELOPE_SCHEMA,
        "executionId": normalized,
        "scaleClass": scale_class,
        "approvedQuota": approved_quota,
        "queueBackend": backend.value,
        "queuePolicyDigest": _digest(policy),
        "executionManifestDigest": _digest(frozen_manifest),
        "sourceDigest": frozen_manifest.get("sourceDigest"),
        "targetSetDigest": str(frozen_manifest.get("targetSetDigest") or ""),
        **observer_binding,
    }
    envelope = {**stable, "envelopeDigest": _digest(stable)}
    assert_valid(
        envelope,
        "execution",
        "execution_queue_backend_envelope",
        label=f"queue backend envelope:{normalized}",
    )
    path = queue_backend_envelope_path(normalized)
    if path.is_file():
        existing = read_json(path)
        if existing != envelope:
            raise ValueError(
                "immutable queue backend envelope drift; create a new sequence with retryOf"
            )
        return path
    write_json(path, envelope)
    return path


def load_execution_queue_backend(
    execution_id: str,
    *,
    verify_inputs: bool = True,
) -> dict[str, Any]:
    normalized = validate_execution_id(execution_id)
    path = queue_backend_envelope_path(normalized)
    if not path.is_file():
        raise ValueError(
            "immutable queue backend envelope is missing; "
            "recreate the execution via the canonical task facade"
        )
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise TypeError("queue backend envelope must be an object")
    if payload.get("schema") != QUEUE_BACKEND_ENVELOPE_SCHEMA:
        raise ValueError("queue backend envelope schema mismatch")
    if str(payload.get("executionId") or "") != normalized:
        raise ValueError("queue backend envelope executionId mismatch")
    stable = {key: value for key, value in payload.items() if key != "envelopeDigest"}
    if str(payload.get("envelopeDigest") or "") != _digest(stable):
        raise ValueError("queue backend envelope digest mismatch")
    assert_valid(
        payload,
        "execution",
        "execution_queue_backend_envelope",
        label=f"queue backend envelope:{normalized}",
    )
    try:
        backend = QueueBackend(str(payload.get("queueBackend") or ""))
    except ValueError as exc:
        raise ValueError("queue backend envelope backend is invalid") from exc
    if payload.get("scaleClass") == "M100_PLUS" and backend is not QueueBackend.RELIABLE_TASK:
        raise ValueError("M100+ queue backend envelope must bind reliabletask")
    if verify_inputs:
        spec = store.load_spec(normalized)
        manifest = load_frozen_execution_manifest(normalized)
        policy = _queue_policy(spec)
        expected = {
            "scaleClass": "M100_PLUS" if _m100_plus(normalized, spec) else "BELOW_M100",
            "approvedQuota": _approved_quota(spec),
            "queueBackend": str(policy["backend"]),
            "queuePolicyDigest": _digest(policy),
            "executionManifestDigest": _digest(manifest),
            "sourceDigest": manifest.get("sourceDigest"),
            "targetSetDigest": str(manifest.get("targetSetDigest") or ""),
        }
        if backend is QueueBackend.RELIABLE_TASK:
            expected.update(
                {
                    "observerBinaryRef": payload.get("observerBinaryRef"),
                    "observerBinarySha256": payload.get("observerBinarySha256"),
                }
            )
        drift = [key for key, value in expected.items() if payload.get(key) != value]
        if drift:
            raise ValueError(
                "queue backend envelope immutable input drift: " + ", ".join(drift)
            )
    return payload


def resolve_execution_queue_backend(
    execution_id: str,
    *,
    requested: str | QueueBackend | None,
    metadata_backend: object = None,
) -> QueueBackend:
    """Resolve every runtime job only from its immutable execution envelope."""
    normalized = validate_execution_id(execution_id)
    envelope = load_execution_queue_backend(normalized)
    backend = QueueBackend(str(envelope["queueBackend"]))
    environment_override = str(
        os.environ.get("QWQ_OBJECT_QUEUE_BACKEND") or ""
    ).strip()
    if environment_override:
        raise ValueError(
            "queue backend environment override is forbidden; "
            "the immutable execution envelope is authoritative"
        )
    candidates = {
        "requested": str(requested.value if isinstance(requested, QueueBackend) else requested or "").strip(),
        "metadata.queueBackend": str(metadata_backend or "").strip(),
    }
    drift = [
        f"{label}={value}"
        for label, value in candidates.items()
        if value and value != backend.value
    ]
    if drift:
        raise ValueError(
            "queue backend tamper: "
            + ", ".join(drift)
            + f"; frozen={backend.value}"
        )
    return backend


__all__ = [
    "QUEUE_BACKEND_ENVELOPE_REF",
    "freeze_execution_queue_backend",
    "load_execution_queue_backend",
    "queue_backend_envelope_path",
    "resolve_execution_queue_backend",
]

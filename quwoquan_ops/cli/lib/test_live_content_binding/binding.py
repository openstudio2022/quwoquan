"""test-live content binding 的 payload 组装、create-once 落盘与加载校验。

原单文件 ``test_live_content_binding.py`` 拆分出的绑定生命周期子模块。
``target_process_dir`` / ``test_live_startup_attempt_path`` / ``_load_evidence``
为被测试 monkeypatch 的包属性，消费点一律经 ``_pkg.`` 访问。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import quwoquan_ops.cli.lib.test_live_content_binding as _pkg
from quwoquan_ops.cli.lib.app_content_uat_plan import build_app_content_uat_plan
from quwoquan_ops.cli.lib.test_live_startup_attempt_receipt import (
    validate_test_live_startup_attempt,
)

from .constants import (
    SCHEMA,
    _BINDING_FIELDS,
    _STARTUP_IDENTITY_FIELDS,
    UnsafeTestLiveContentBindingPath,
)
from .evidence import (
    _Evidence,
    _canonical_digest,
    _copy_source_identity,
    _document_checksum,
    _safe_segment,
)
from .safe_io import _create_once, _read_regular_json


def test_live_content_binding_path(target: str, startup_attempt_id: str) -> Path:
    """Return one target-and-attempt-scoped binding path without creating it."""

    attempt_id = _safe_segment(startup_attempt_id, label="startupAttemptId")
    return _pkg.target_process_dir(target) / f"test_live_content_binding.{attempt_id}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _startup_identity(startup: Mapping[str, Any]) -> dict[str, str]:
    return {field: str(startup.get(field) or "") for field in _STARTUP_IDENTITY_FIELDS}


def _evidence_token(evidence: _Evidence) -> tuple[object, ...]:
    return (
        evidence.startup,
        evidence.startup_snapshot.identity,
        evidence.startup_snapshot.digest,
        evidence.attestation,
        evidence.attestation_snapshot.identity,
        evidence.attestation_snapshot.digest,
        evidence.readiness,
        evidence.readiness_snapshot.identity,
        evidence.readiness_snapshot.digest,
        evidence.lifecycle,
        evidence.lifecycle_snapshot.identity if evidence.lifecycle_snapshot else None,
        evidence.lifecycle_snapshot.digest if evidence.lifecycle_snapshot else "",
    )


def _binding_payload(
    *,
    evidence: _Evidence,
    environment: str,
    target: str,
) -> dict[str, Any]:
    app_uat_plan = build_app_content_uat_plan(evidence.readiness)
    return {
        "schema": SCHEMA,
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "bound",
        "retentionClass": "run_bound",
        "environment": environment,
        "target": target,
        "startupAttemptId": evidence.startup["attemptId"],
        "startupIdentity": _startup_identity(evidence.startup),
        "releaseId": evidence.readiness["releaseId"],
        "verifyRunId": evidence.readiness["verifyRunId"],
        "manifestDigest": evidence.readiness["manifestDigest"],
        "readinessPhase": evidence.readiness_phase,
        "releaseAttestationRef": evidence.attestation_ref,
        "releaseAttestationDigest": evidence.attestation_snapshot.digest,
        "readinessReceiptRef": evidence.readiness_ref,
        "readinessReceiptDigest": evidence.readiness_snapshot.digest,
        "dataSourceIdentity": _copy_source_identity(evidence.source_identity),
        "appUatEnvelope": dict(evidence.readiness["appUatEnvelope"]),
        "appUatEnvelopeDigest": evidence.readiness["appUatEnvelopeDigest"],
        "appUatPlan": app_uat_plan,
        "appUatPlanDigest": _document_checksum(app_uat_plan),
        "activationEnvelope": dict(evidence.readiness["activationEnvelope"]),
        "activationEnvelopeDigest": evidence.readiness[
            "activationEnvelopeDigest"
        ],
        "lifecycleExitRef": evidence.lifecycle_ref,
        "lifecycleExitDigest": (
            evidence.lifecycle_snapshot.digest if evidence.lifecycle_snapshot else ""
        ),
        "boundAt": _utc_now(),
    }


def _validate_timestamp(value: object) -> None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("test-live content binding boundAt is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("test-live content binding boundAt is invalid")


def _validate_binding(value: object, *, evidence: _Evidence, target: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _BINDING_FIELDS:
        raise ValueError("test-live content binding fields mismatch")
    app_uat_plan = build_app_content_uat_plan(evidence.readiness)
    expected = {
        "schema": SCHEMA,
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "bound",
        "retentionClass": "run_bound",
        "environment": evidence.startup["environment"],
        "target": target,
        "startupAttemptId": evidence.startup["attemptId"],
        "startupIdentity": _startup_identity(evidence.startup),
        "releaseId": evidence.readiness["releaseId"],
        "verifyRunId": evidence.readiness["verifyRunId"],
        "manifestDigest": evidence.readiness["manifestDigest"],
        "readinessPhase": evidence.readiness_phase,
        "releaseAttestationRef": evidence.attestation_ref,
        "releaseAttestationDigest": evidence.attestation_snapshot.digest,
        "readinessReceiptRef": evidence.readiness_ref,
        "readinessReceiptDigest": evidence.readiness_snapshot.digest,
        "dataSourceIdentity": _copy_source_identity(evidence.source_identity),
        "appUatEnvelope": dict(evidence.readiness["appUatEnvelope"]),
        "appUatEnvelopeDigest": evidence.readiness["appUatEnvelopeDigest"],
        "appUatPlan": app_uat_plan,
        "appUatPlanDigest": _document_checksum(app_uat_plan),
        "activationEnvelope": dict(evidence.readiness["activationEnvelope"]),
        "activationEnvelopeDigest": evidence.readiness[
            "activationEnvelopeDigest"
        ],
        "lifecycleExitRef": evidence.lifecycle_ref,
        "lifecycleExitDigest": (
            evidence.lifecycle_snapshot.digest if evidence.lifecycle_snapshot else ""
        ),
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            raise ValueError(f"test-live content binding {field} drift")
    _validate_timestamp(value.get("boundAt"))
    return dict(value)


def load_test_live_content_binding(target: str) -> dict[str, Any] | None:
    """Load a binding and prove it still names the current running attempt/evidence."""

    startup_snapshot = _read_regular_json(
        _pkg.test_live_startup_attempt_path(target),
        label="test-live startup receipt",
        optional=True,
    )
    if startup_snapshot is None:
        return None
    startup = validate_test_live_startup_attempt(
        startup_snapshot.value,
        expected_target=target,
    )
    path = test_live_content_binding_path(target, str(startup["attemptId"]))
    first = _read_regular_json(path, label="test-live content binding", optional=True)
    if first is None:
        return None
    raw = first.value
    environment = str(raw.get("environment") or "")
    evidence = _pkg._load_evidence(
        environment=environment,
        target=target,
        startup_attempt_id=str(raw.get("startupAttemptId") or ""),
        release_id=str(raw.get("releaseId") or ""),
        verify_run_id=str(raw.get("verifyRunId") or ""),
        manifest_digest=str(raw.get("manifestDigest") or ""),
        lifecycle_exit_ref=str(raw.get("lifecycleExitRef") or ""),
    )
    validated = _validate_binding(raw, evidence=evidence, target=target)
    second = _read_regular_json(path, label="test-live content binding")
    assert second is not None
    if first != second:
        raise UnsafeTestLiveContentBindingPath(
            "test-live content binding changed during validation"
        )
    return validated


def create_test_live_content_binding(
    *,
    environment: str,
    target: str,
    startup_attempt_id: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
    expected_readiness_receipt_digest: str = "",
    lifecycle_exit_ref: str = "",
) -> dict[str, Any]:
    """Create exactly one binding for the current mutable startup attempt."""

    first = _pkg._load_evidence(
        environment=environment,
        target=target,
        startup_attempt_id=startup_attempt_id,
        release_id=release_id,
        verify_run_id=verify_run_id,
        manifest_digest=manifest_digest,
        lifecycle_exit_ref=lifecycle_exit_ref,
    )
    expected_readiness_digest = str(expected_readiness_receipt_digest or "").strip()
    if expected_readiness_digest:
        _canonical_digest(
            expected_readiness_digest,
            label="readiness receipt digest",
        )
        if first.readiness_snapshot.digest != expected_readiness_digest:
            raise ValueError("test-live content binding readiness receipt digest mismatch")
    existing = load_test_live_content_binding(target)
    if existing is not None:
        requested = (
            first.startup["attemptId"],
            first.readiness["releaseId"],
            first.readiness["verifyRunId"],
            first.readiness["manifestDigest"],
            str(lifecycle_exit_ref or "").strip(),
        )
        observed = (
            existing["startupAttemptId"],
            existing["releaseId"],
            existing["verifyRunId"],
            existing["manifestDigest"],
            existing["lifecycleExitRef"],
        )
        if requested != observed:
            raise ValueError("test-live content binding is create-once and cannot be rebound")
        return existing

    second = _pkg._load_evidence(
        environment=environment,
        target=target,
        startup_attempt_id=startup_attempt_id,
        release_id=release_id,
        verify_run_id=verify_run_id,
        manifest_digest=manifest_digest,
        lifecycle_exit_ref=lifecycle_exit_ref,
    )
    if (
        expected_readiness_digest
        and second.readiness_snapshot.digest != expected_readiness_digest
    ):
        raise ValueError("test-live content binding readiness receipt digest mismatch")
    if _evidence_token(first) != _evidence_token(second):
        raise UnsafeTestLiveContentBindingPath(
            "test-live content evidence changed before binding"
        )
    payload = _binding_payload(
        evidence=second,
        environment=environment,
        target=target,
    )
    path = test_live_content_binding_path(
        target,
        str(second.startup["attemptId"]),
    )
    try:
        _create_once(path, payload)
    except FileExistsError:
        existing = load_test_live_content_binding(target)
        if existing is None:
            raise UnsafeTestLiveContentBindingPath(
                "test-live content binding raced with an invalid writer"
            )
        requested = (
            second.startup["attemptId"],
            second.readiness["releaseId"],
            second.readiness["verifyRunId"],
            second.readiness["manifestDigest"],
            str(lifecycle_exit_ref or "").strip(),
        )
        observed = (
            existing["startupAttemptId"],
            existing["releaseId"],
            existing["verifyRunId"],
            existing["manifestDigest"],
            existing["lifecycleExitRef"],
        )
        if requested != observed:
            raise ValueError("test-live content binding is create-once and cannot be rebound")
        return existing
    loaded = load_test_live_content_binding(target)
    if loaded is None:
        raise UnsafeTestLiveContentBindingPath("test-live content binding was not committed")
    return loaded

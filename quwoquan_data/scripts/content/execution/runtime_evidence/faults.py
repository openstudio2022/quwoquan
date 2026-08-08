"""Governed fault actions and create-once raw fault case materialization."""
from __future__ import annotations

import fcntl
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign.runtime import lane_checkpoint_path
from content.execution.campaign.runtime_process import terminate_lane_process
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.runtime_evidence.contract import (
    FAULT_TYPES,
    FaultProviderBinding,
    ProcessInspector,
    RuntimeEvidenceError,
    RuntimeEvidenceIdentity,
    canonical_digest,
    file_digest,
    load_runtime_evidence_session,
    resolve_ref,
    safe_ref,
    session_root,
    validate_provider_fault_test_hook_attestation,
    write_create_once,
)
from content.execution.runtime_evidence.fault_materialization import (
    finalize_fault_cases,
    load_fault_receipt,
    validate_fault_receipt_binding,
)
from content.execution.runtime_evidence.sampling import QueueEvidenceProvider

_SAFE_CASE_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)
FAULT_EVENT_CLOCK_SKEW_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class FaultActionTarget:
    fault_type: str
    carrier: str
    execution_id: str
    job_id: str
    requested_at: str
    worker_checkpoint: Mapping[str, Any] | None
    identity: RuntimeEvidenceIdentity | None = None
    request_digest: str | None = None


@dataclass(frozen=True, slots=True)
class FaultActionResult:
    result_code: str
    triggered_at: str
    provider_evidence_path: Path | None = None


class FaultActionProvider(Protocol):
    @property
    def binding(self) -> FaultProviderBinding:
        """Frozen adapter identity; command strings are never accepted."""

    def trigger(self, target: FaultActionTarget) -> FaultActionResult:
        """Trigger one typed fault through a governed in-process adapter."""


class CampaignWorkerTerminator:
    """The only built-in destructive action: one registered lane process group."""

    def __init__(self, *, grace_seconds: float = 5.0) -> None:
        if grace_seconds <= 0:
            raise ValueError("worker termination grace must be positive")
        self._grace_seconds = grace_seconds

    @property
    def binding(self) -> FaultProviderBinding:
        return FaultProviderBinding(
            provider_id="campaign_worker_terminator_v1",
            configuration_digest=canonical_digest(
                {
                    "schema": "quwoquan_data.campaign_worker_terminator",
                    "version": 1,
                    "identityChecks": ["pid", "pgid", "command", "executionId"],
                    "graceSeconds": self._grace_seconds,
                }
            ),
            fault_type="worker_termination",
        )

    def trigger(self, target: FaultActionTarget) -> FaultActionResult:
        checkpoint = target.worker_checkpoint
        if target.fault_type != "worker_termination" or checkpoint is None:
            raise RuntimeEvidenceError("worker terminator received a non-worker target")
        outcome = terminate_lane_process(
            checkpoint, grace_seconds=self._grace_seconds
        )
        if outcome not in {"terminated", "killed"}:
            raise RuntimeEvidenceError(
                f"registered worker termination was refused: {outcome}"
            )
        return FaultActionResult(
            result_code=f"DATA.RUNTIME_EVIDENCE.WORKER_{outcome.upper()}",
            triggered_at=_now().isoformat(),
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: object, *, label: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RuntimeEvidenceError(f"{label} must be RFC3339 date-time") from exc
    if parsed.tzinfo is None:
        raise RuntimeEvidenceError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


def _safe_case_id(value: str) -> str:
    if (
        len(value) < 3
        or len(value) > 128
        or value[0] not in _SAFE_CASE_CHARS - {".", "_", "-"}
        or any(char not in _SAFE_CASE_CHARS for char in value)
    ):
        raise RuntimeEvidenceError("fault caseId is unsafe")
    return value


def _fault_binding(
    session: Mapping[str, Any], fault_type: str
) -> dict[str, str]:
    rows = [
        dict(row)
        for row in session["faultProviders"]
        if row.get("faultType") == fault_type
    ]
    if len(rows) != 1:
        raise RuntimeEvidenceError(
            f"fault type has no unique governed provider: {fault_type}"
        )
    return rows[0]


def _assert_hook_attestation(
    session: Mapping[str, Any], *, output_root: Path, fault_type: str
) -> None:
    if fault_type not in {"provider_timeout", "provider_rate_limit"}:
        return
    from content.execution.runtime_evidence.fault_adapters import (
        is_unavailable_fault_binding_document,
    )

    if is_unavailable_fault_binding_document(_fault_binding(session, fault_type)):
        return
    if session.get("providerFaultTestHooksEnabled") is not True:
        raise RuntimeEvidenceError(
            "provider timeout/rate-limit faults are production-denied by default"
        )
    ref = str(session.get("providerFaultTestHookAttestationRef") or "")
    path = resolve_ref(ref, output_root=output_root)
    if file_digest(path) != session.get("providerFaultTestHookAttestationSha256"):
        raise RuntimeEvidenceError("provider fault test-hook attestation drift")
    validate_provider_fault_test_hook_attestation(
        path,
        identity=RuntimeEvidenceIdentity(
            root_execution_id=str(session["rootExecutionId"]),
            run_id=str(session["runId"]),
            generation=int(session["generation"]),
            fencing_token=str(session["fencingToken"]),
        ),
        provider_rows=[dict(row) for row in session["faultProviders"]],
    )


def _target_worker(
    session: Mapping[str, Any],
    *,
    runtime: CampaignRuntimePaths,
    identity: RuntimeEvidenceIdentity,
    carrier: str,
    execution_id: str,
    inspector: ProcessInspector,
) -> dict[str, Any]:
    matches = [
        dict(row)
        for row in session["workers"]
        if row.get("carrier") == carrier and row.get("executionId") == execution_id
    ]
    if len(matches) != 1:
        raise RuntimeEvidenceError("fault target is not a registered campaign lane")
    registration = matches[0]
    checkpoint_path = lane_checkpoint_path(
        runtime, identity.root_execution_id, carrier
    )
    checkpoint = read_json(checkpoint_path)
    expected = {
        **identity.as_document(),
        "carrier": carrier,
        "executionId": execution_id,
        "status": "running",
        "pid": registration["pid"],
        "pgid": registration["pgid"],
    }
    if not isinstance(checkpoint, Mapping) or any(
        checkpoint.get(key) != value for key, value in expected.items()
    ):
        raise RuntimeEvidenceError("fault target checkpoint is stale or reassigned")
    observed = inspector.observe(int(registration["pid"]))
    if (
        observed.pgid != int(registration["pgid"])
        or observed.identity_digest != registration["processIdentityDigest"]
        or observed.pid != observed.pgid
    ):
        raise RuntimeEvidenceError("fault worker process identity changed")
    return dict(checkpoint)


def _write_event_once(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / f".{path.name}.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if path.is_file():
            if read_json(path) != dict(payload):
                raise RuntimeEvidenceError(f"fault event create-once collision: {path}")
            return
        assert_valid(
            payload,
            "release",
            "fault_injection_event",
            label=f"runtime fault event:{path}",
        )
        write_json(path, dict(payload))


def _failed_receipt(
    *,
    path: Path,
    request: Mapping[str, Any],
    request_path: Path,
    session: Mapping[str, Any],
    output_root: Path,
    result_code: str,
    action_triggered_at: str,
    provider_evidence_path: Path | None = None,
) -> dict[str, Any]:
    provider_ref = None
    provider_digest = None
    if provider_evidence_path is not None:
        provider_ref = safe_ref(provider_evidence_path, output_root=output_root)
        provider_digest = file_digest(provider_evidence_path)
    stable = {
        "schema": "quwoquan_data.runtime_fault_case_receipt",
        "caseId": request["caseId"],
        "requestRef": safe_ref(request_path, output_root=output_root),
        "requestDigest": request["requestDigest"],
        "sessionRef": request["sessionRef"],
        "sessionDigest": session["receiptDigest"],
        "rootExecutionId": request["rootExecutionId"],
        "runId": request["runId"],
        "generation": request["generation"],
        "fencingToken": request["fencingToken"],
        "faultType": request["faultType"],
        "carrier": request["carrier"],
        "executionId": request["executionId"],
        "jobId": request["jobId"],
        "actionStatus": "failed",
        "actionResultCode": result_code,
        "actionTriggeredAt": action_triggered_at,
        "faultEventAt": None,
        "eventRef": None,
        "eventSha256": None,
        "queueEventEvidenceDigest": None,
        "providerEvidenceRef": provider_ref,
        "providerEvidenceSha256": provider_digest,
    }
    return write_create_once(
        path,
        stable=stable,
        schema_name="runtime_fault_case_receipt",
        digest_field="receiptDigest",
        recorded_at_field="recordedAt",
    )


def _provider_failure_code(exc: Exception) -> str:
    code = str(getattr(exc, "code", "") or "")
    if code.startswith("DATA.RUNTIME_EVIDENCE."):
        return code
    return f"DATA.RUNTIME_EVIDENCE.FAULT_PROVIDER_FAILED.{type(exc).__name__}"


def inject_fault(
    *,
    runtime: CampaignRuntimePaths,
    identity: RuntimeEvidenceIdentity,
    session_id: str,
    case_id: str,
    fault_type: str,
    carrier: str,
    execution_id: str,
    job_id: str,
    inspector: ProcessInspector,
    queue_provider: QueueEvidenceProvider,
    providers: Mapping[str, FaultActionProvider],
    queue_event_timeout_seconds: float,
) -> tuple[dict[str, Any], Path]:
    """Execute one typed action exactly once; shell/argv input is impossible."""
    if queue_event_timeout_seconds <= 0:
        raise ValueError("queue fault-event timeout must be positive")
    case_id = _safe_case_id(case_id)
    if fault_type not in FAULT_TYPES or carrier not in {
        str(row) for row in ("homepage", "article", "image", "video")
    }:
        raise RuntimeEvidenceError("fault type or carrier is invalid")
    session = load_runtime_evidence_session(runtime, identity, session_id)
    if session.get("queueEvidenceProvider") != queue_provider.binding.as_document():
        raise RuntimeEvidenceError("fault queue evidence provider identity drift")
    matches = [
        row
        for row in session["workers"]
        if row.get("carrier") == carrier and row.get("executionId") == execution_id
    ]
    if len(matches) != 1:
        raise RuntimeEvidenceError("fault execution does not belong to the carrier")
    binding = _fault_binding(session, fault_type)
    provider = providers.get(fault_type)
    case_root = session_root(runtime, identity, session_id) / "faults" / case_id
    request_path = case_root / "request.json"
    event_path = case_root / "event.json"
    receipt_path = case_root / "receipt.json"
    case_root.mkdir(parents=True, exist_ok=True)
    with (case_root / ".case.lock").open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if receipt_path.is_file():
            receipt = load_fault_receipt(receipt_path)
            validate_fault_receipt_binding(
                receipt,
                session=session,
                identity=identity,
                output_root=runtime.output_root,
            )
            expected = {
                "caseId": case_id,
                "sessionRef": safe_ref(
                    session_root(runtime, identity, session_id) / "session.json",
                    output_root=runtime.output_root,
                ),
                "sessionDigest": session["receiptDigest"],
                **identity.as_document(),
                "faultType": fault_type,
                "carrier": carrier,
                "executionId": execution_id,
                "jobId": job_id,
            }
            if any(receipt.get(key) != value for key, value in expected.items()):
                raise RuntimeEvidenceError(
                    "DATA.RUNTIME_EVIDENCE.FAULT_CASE_CREATE_ONCE_COLLISION: "
                    f"{case_id} already binds a different fault intent"
                )
            return receipt, receipt_path
        if request_path.is_file():
            raise RuntimeEvidenceError(
                "DATA.RUNTIME_EVIDENCE.INDETERMINATE_FAULT_REQUEST: "
                f"{case_id} has an intent without terminal receipt"
            )
        queue_provider.assert_job_target(execution_id=execution_id, job_id=job_id)
        worker_checkpoint = None
        if fault_type == "worker_termination":
            worker_checkpoint = _target_worker(
                session,
                runtime=runtime,
                identity=identity,
                carrier=carrier,
                execution_id=execution_id,
                inspector=inspector,
            )
        requested_at = _now().isoformat()
        request = write_create_once(
            request_path,
            stable={
                "schema": "quwoquan_data.runtime_fault_request",
                "caseId": case_id,
                "sessionRef": safe_ref(
                    session_root(runtime, identity, session_id) / "session.json",
                    output_root=runtime.output_root,
                ),
                "sessionDigest": session["receiptDigest"],
                **identity.as_document(),
                "faultType": fault_type,
                "carrier": carrier,
                "executionId": execution_id,
                "jobId": job_id,
                "providerId": binding["providerId"],
                "providerConfigurationDigest": binding["configurationDigest"],
                "requestedAt": requested_at,
            },
            schema_name="runtime_fault_request",
            digest_field="requestDigest",
        )
        target = FaultActionTarget(
            fault_type=fault_type,
            carrier=carrier,
            execution_id=execution_id,
            job_id=job_id,
            requested_at=requested_at,
            worker_checkpoint=worker_checkpoint,
            identity=identity,
            request_digest=str(request["requestDigest"]),
        )
        action_triggered_at = requested_at
        try:
            if provider is None or provider.binding.as_document() != binding:
                raise RuntimeEvidenceError(
                    "fault action provider identity drift or missing"
                )
            _assert_hook_attestation(
                session,
                output_root=runtime.output_root,
                fault_type=fault_type,
            )
            action = provider.trigger(target)
            triggered_at = _parse_time(
                action.triggered_at, label="fault action triggeredAt"
            )
            action_triggered_at = action.triggered_at
            if triggered_at < _parse_time(requested_at, label="fault requestedAt"):
                raise RuntimeEvidenceError("fault action timestamp predates request")
            if triggered_at > _now() + timedelta(
                seconds=FAULT_EVENT_CLOCK_SKEW_SECONDS
            ):
                raise RuntimeEvidenceError("fault action timestamp is in the future")
            provider_ref = None
            provider_digest = None
            if action.provider_evidence_path is not None:
                provider_ref = safe_ref(
                    action.provider_evidence_path, output_root=runtime.output_root
                )
                provider_digest = file_digest(action.provider_evidence_path)
            elif fault_type != "worker_termination":
                raise RuntimeEvidenceError(
                    "DATA.RUNTIME_EVIDENCE.PROVIDER_EVIDENCE_MISSING"
                )
        except Exception as exc:  # noqa: BLE001
            receipt = _failed_receipt(
                path=receipt_path,
                request=request,
                request_path=request_path,
                session=session,
                output_root=runtime.output_root,
                result_code=_provider_failure_code(exc),
                action_triggered_at=action_triggered_at,
            )
            return receipt, receipt_path
        try:
            queue_event = queue_provider.wait_for_fault_event(
                execution_id=execution_id,
                job_id=job_id,
                fault_type=fault_type,
                after=action.triggered_at,
                timeout_seconds=queue_event_timeout_seconds,
            )
            event_at = _parse_time(
                queue_event.event_at, label="fault queue eventAt"
            )
            if event_at < triggered_at:
                raise RuntimeEvidenceError("fault queue event predates action")
            if event_at > _now() + timedelta(
                seconds=FAULT_EVENT_CLOCK_SKEW_SECONDS
            ):
                raise RuntimeEvidenceError("fault queue event timestamp is in the future")
        except Exception as exc:  # noqa: BLE001
            receipt = _failed_receipt(
                path=receipt_path,
                request=request,
                request_path=request_path,
                session=session,
                output_root=runtime.output_root,
                result_code=(
                    "DATA.RUNTIME_EVIDENCE.QUEUE_EVENT_NOT_OBSERVED."
                    f"{type(exc).__name__}"
                ),
                action_triggered_at=action.triggered_at,
                provider_evidence_path=action.provider_evidence_path,
            )
            return receipt, receipt_path
        event = {
            "schema": "quwoquan_data.fault_injection_event",
            "caseId": case_id,
            "faultType": fault_type,
            "carrier": carrier,
            "executionId": execution_id,
            "jobId": job_id,
            "triggeredAt": queue_event.event_at,
        }
        _write_event_once(event_path, event)
        stable = {
            "schema": "quwoquan_data.runtime_fault_case_receipt",
            "caseId": case_id,
            "requestRef": safe_ref(request_path, output_root=runtime.output_root),
            "requestDigest": request["requestDigest"],
            "sessionRef": request["sessionRef"],
            "sessionDigest": session["receiptDigest"],
            **identity.as_document(),
            "faultType": fault_type,
            "carrier": carrier,
            "executionId": execution_id,
            "jobId": job_id,
            "actionStatus": "triggered",
            "actionResultCode": action.result_code,
            "actionTriggeredAt": action.triggered_at,
            "faultEventAt": queue_event.event_at,
            "eventRef": safe_ref(event_path, output_root=runtime.output_root),
            "eventSha256": file_digest(event_path),
            "queueEventEvidenceDigest": queue_event.evidence_digest,
            "providerEvidenceRef": provider_ref,
            "providerEvidenceSha256": provider_digest,
        }
        receipt = write_create_once(
            receipt_path,
            stable=stable,
            schema_name="runtime_fault_case_receipt",
            digest_field="receiptDigest",
            recorded_at_field="recordedAt",
        )
        return receipt, receipt_path


__all__ = [
    "CampaignWorkerTerminator",
    "FaultActionProvider",
    "FaultActionResult",
    "FaultActionTarget",
    "finalize_fault_cases",
    "inject_fault",
]

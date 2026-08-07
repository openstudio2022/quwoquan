"""Immutable identity boundary for campaign fault and resource evidence."""
from __future__ import annotations

import fcntl
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign.runtime import (
    assert_campaign_fence,
    lane_checkpoint_path,
    runtime_root,
    runtime_snapshot_path,
)
from content.execution.campaign.workspace import CampaignRuntimePaths

FAULT_TYPES = (
    "worker_termination",
    "lease_expiry",
    "redis_restart",
    "mongo_reconnect",
    "provider_timeout",
    "provider_rate_limit",
)
CARRIERS = ("homepage", "article", "image", "video")
_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{2,127}$")

class RuntimeEvidenceError(RuntimeError):
    """A runtime target or create-once evidence boundary is invalid."""


@dataclass(frozen=True, slots=True)
class RuntimeEvidenceIdentity:
    root_execution_id: str
    run_id: str
    generation: int
    fencing_token: str

    def as_document(self) -> dict[str, object]:
        return {
            "rootExecutionId": self.root_execution_id,
            "runId": self.run_id,
            "generation": self.generation,
            "fencingToken": self.fencing_token,
        }


@dataclass(frozen=True, slots=True)
class ProcessObservation:
    pid: int
    pgid: int
    command: str
    start_token: str
    rss_bytes: int
    open_fd_count: int

    @property
    def identity_digest(self) -> str:
        return canonical_digest(
            {
                "pid": self.pid,
                "pgid": self.pgid,
                "command": self.command,
                "startToken": self.start_token,
            }
        )


class ProcessInspector(Protocol):
    def observe(self, pid: int) -> ProcessObservation:
        """Return one live OS observation or raise when the process is absent."""

    def observe_group(self, pgid: int) -> tuple[ProcessObservation, ...]:
        """Return every live member of one exact process group."""


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    provider_id: str
    configuration_digest: str

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("runtime evidence providerId is required")
        _require_digest(self.configuration_digest, label="configurationDigest")

    def as_document(self) -> dict[str, str]:
        return {
            "providerId": self.provider_id,
            "configurationDigest": self.configuration_digest,
        }


@dataclass(frozen=True, slots=True)
class FaultProviderBinding(ProviderBinding):
    fault_type: str

    def __post_init__(self) -> None:
        ProviderBinding.__post_init__(self)
        if self.fault_type not in FAULT_TYPES:
            raise ValueError(f"unsupported runtime fault type: {self.fault_type}")

    def as_document(self) -> dict[str, str]:
        return {
            "faultType": self.fault_type,
            **ProviderBinding.as_document(self),
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now().isoformat()


def _parse_time(value: object, *, label: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RuntimeEvidenceError(f"{label} must be RFC3339 date-time") from exc
    if parsed.tzinfo is None:
        raise RuntimeEvidenceError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


def _require_digest(value: object, *, label: str) -> str:
    text = str(value or "")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", text) is None:
        raise RuntimeEvidenceError(f"{label} must be a sha256 digest")
    return text


def canonical_digest(value: Mapping[str, Any], *, excluded: str | None = None) -> str:
    payload = dict(value)
    if excluded is not None:
        payload.pop(excluded, None)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise RuntimeEvidenceError(f"runtime evidence file is missing or unsafe: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def safe_ref(path: Path, *, output_root: Path, require_file: bool = True) -> str:
    if path.is_symlink() or (require_file and not path.is_file()):
        raise RuntimeEvidenceError(f"runtime evidence path is missing or unsafe: {path}")
    if not require_file and not path.exists():
        raise RuntimeEvidenceError(f"runtime workspace path is missing: {path}")
    try:
        return path.resolve().relative_to(output_root.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeEvidenceError(
            f"runtime evidence path escapes QWQ_OUTPUT_ROOT: {path}"
        ) from exc


def resolve_ref(ref: str, *, output_root: Path, require_file: bool = True) -> Path:
    candidate = Path(str(ref or ""))
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise RuntimeEvidenceError(f"unsafe runtime evidence ref: {ref!r}")
    path = output_root / candidate
    safe_ref(path, output_root=output_root, require_file=require_file)
    return path


def _load_mapping(path: Path, *, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeEvidenceError(f"{label} is missing or unsafe: {path}")
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise RuntimeEvidenceError(f"{label} must be an object")
    return payload


def _validate_digest_document(
    path: Path,
    *,
    schema_name: str,
    digest_field: str,
) -> dict[str, Any]:
    payload = _load_mapping(path, label=schema_name)
    assert_valid(payload, "execution", schema_name, label=f"runtime evidence:{path}")
    expected = canonical_digest(payload, excluded=digest_field)
    if payload.get(digest_field) != expected:
        raise RuntimeEvidenceError(f"{schema_name} digest drift: {path}")
    return payload


def write_create_once(
    path: Path,
    *,
    stable: Mapping[str, Any],
    schema_name: str,
    digest_field: str,
    recorded_at_field: str | None = None,
) -> dict[str, Any]:
    """Atomically write one immutable document and reject identity collisions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / f".{path.name}.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if path.is_file():
            existing = _validate_digest_document(
                path, schema_name=schema_name, digest_field=digest_field
            )
            if any(existing.get(key) != value for key, value in stable.items()):
                raise RuntimeEvidenceError(f"create-once collision: {path}")
            return existing
        document = dict(stable)
        if recorded_at_field is not None:
            document[recorded_at_field] = _iso_now()
        document[digest_field] = canonical_digest(document, excluded=digest_field)
        assert_valid(
            document,
            "execution",
            schema_name,
            label=f"runtime evidence:{path}",
        )
        write_json(path, document)
        return document


def _assert_plan(path: Path, identity: RuntimeEvidenceIdentity) -> dict[str, Any]:
    plan = _load_mapping(path, label="campaign plan")
    assert_valid(plan, "execution", "content_campaign_plan", label="campaign plan")
    if plan.get("rootExecutionId") != identity.root_execution_id:
        raise RuntimeEvidenceError("campaign plan rootExecutionId drift")
    if plan.get("planDigest") != canonical_digest(plan, excluded="planDigest"):
        raise RuntimeEvidenceError("campaign planDigest drift")
    expected_revision = canonical_digest(
        {
            "schema": "quwoquan_data.campaign_content_source_revision",
            "sourceDigest": plan.get("sourceDigest"),
            "entityCatalogDigest": plan.get("entityCatalogDigest"),
        }
    )
    if plan.get("sourceRevision") != expected_revision:
        raise RuntimeEvidenceError("campaign sourceRevision drift")
    execution_ids = plan.get("executionIds")
    if not isinstance(execution_ids, Mapping) or set(execution_ids) != set(CARRIERS):
        raise RuntimeEvidenceError("campaign plan must bind exactly four lanes")
    return plan


def _assert_current_lease(
    runtime: CampaignRuntimePaths,
    identity: RuntimeEvidenceIdentity,
) -> dict[str, Any]:
    snapshot = assert_campaign_fence(
        runtime,
        identity.root_execution_id,
        run_id=identity.run_id,
        generation=identity.generation,
        fencing_token=identity.fencing_token,
    )
    if str(snapshot.get("status") or "") != "active":
        raise RuntimeEvidenceError("campaign runtime lease is not active")
    lease_seconds = int(snapshot.get("leaseSeconds") or 0)
    heartbeat = _parse_time(snapshot.get("heartbeatAt"), label="campaign heartbeat")
    age = max(0.0, (_now() - heartbeat).total_seconds())
    if lease_seconds < 1 or age > lease_seconds:
        raise RuntimeEvidenceError(
            f"campaign runtime lease is stale: age={age:.3f}s lease={lease_seconds}s"
        )
    return snapshot


def validate_provider_fault_test_hook_attestation(
    path: Path,
    *,
    identity: RuntimeEvidenceIdentity,
    provider_rows: Sequence[Mapping[str, str]],
) -> None:
    payload = _load_mapping(path, label="provider fault test-hook attestation")
    assert_valid(
        payload,
        "execution",
        "runtime_provider_fault_test_hook_attestation",
        label="provider fault test-hook attestation",
    )
    if payload.get("attestationDigest") != canonical_digest(
        payload, excluded="attestationDigest"
    ):
        raise RuntimeEvidenceError("provider fault test-hook attestation digest drift")
    if any(payload.get(key) != value for key, value in identity.as_document().items()):
        raise RuntimeEvidenceError("provider fault test-hook campaign identity drift")
    from content.execution.runtime_evidence.fault_adapters import (
        is_unavailable_fault_binding_document,
    )

    expected = [
        dict(row)
        for row in provider_rows
        if row.get("faultType") in {"provider_timeout", "provider_rate_limit"}
        and not is_unavailable_fault_binding_document(row)
    ]
    observed = payload.get("providerBindings")
    if not isinstance(observed, list) or sorted(
        observed, key=lambda row: str(row.get("faultType") or "")
    ) != sorted(expected, key=lambda row: str(row.get("faultType") or "")):
        raise RuntimeEvidenceError("provider fault test-hook binding drift")
    issued = _parse_time(payload.get("issuedAt"), label="test-hook issuedAt")
    expires = _parse_time(payload.get("expiresAt"), label="test-hook expiresAt")
    now = _now()
    if issued > now or expires <= now or expires <= issued:
        raise RuntimeEvidenceError("provider fault test-hook attestation is not current")


def assert_current_session(
    runtime: CampaignRuntimePaths,
    session: Mapping[str, Any],
    identity: RuntimeEvidenceIdentity,
    *,
    require_active_lease: bool = True,
) -> dict[str, Any]:
    expected = identity.as_document()
    if any(session.get(key) != value for key, value in expected.items()):
        raise RuntimeEvidenceError("runtime evidence session identity drift")
    if require_active_lease:
        return _assert_current_lease(runtime, identity)
    return assert_campaign_fence(
        runtime,
        identity.root_execution_id,
        run_id=identity.run_id,
        generation=identity.generation,
        fencing_token=identity.fencing_token,
    )


def session_root(
    runtime: CampaignRuntimePaths,
    identity: RuntimeEvidenceIdentity,
    session_id: str,
) -> Path:
    if _SAFE_ID.fullmatch(session_id) is None:
        raise RuntimeEvidenceError("runtime evidence sessionId is unsafe")
    return runtime_root(runtime, identity.root_execution_id) / "evidence" / session_id


def session_path(
    runtime: CampaignRuntimePaths,
    identity: RuntimeEvidenceIdentity,
    session_id: str,
) -> Path:
    return session_root(runtime, identity, session_id) / "session.json"


def load_runtime_evidence_session(
    runtime: CampaignRuntimePaths,
    identity: RuntimeEvidenceIdentity,
    session_id: str,
    *,
    require_active_lease: bool = True,
) -> dict[str, Any]:
    payload = _validate_digest_document(
        session_path(runtime, identity, session_id),
        schema_name="runtime_evidence_session",
        digest_field="receiptDigest",
    )
    assert_current_session(
        runtime,
        payload,
        identity,
        require_active_lease=require_active_lease,
    )
    plan_path = resolve_ref(
        str(payload["campaignPlanRef"]), output_root=runtime.output_root
    )
    if file_digest(plan_path) != payload["campaignPlanSha256"]:
        raise RuntimeEvidenceError("runtime evidence campaign plan digest drift")
    plan = _assert_plan(plan_path, identity)
    for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest"):
        if plan.get(field) != payload.get(field):
            raise RuntimeEvidenceError(
                f"runtime evidence campaign plan {field} drift"
            )
    return payload


def _assert_process_scope(
    observation: ProcessObservation,
    *,
    execution_id: str,
    role: str,
) -> None:
    command = observation.command.replace("\\", "/")
    if (
        observation.pid < 2
        or observation.pgid < 2
        or "quwoquan_data/scripts/cli.py" not in command
        or execution_id not in command
    ):
        raise RuntimeEvidenceError(
            f"registered {role} process is outside Data execution scope: {execution_id}"
        )
    if role == "worker" and observation.pid != observation.pgid:
        raise RuntimeEvidenceError(
            f"registered worker does not own an isolated process group: {execution_id}"
        )


def _process_row(
    *,
    role: str,
    carrier: str | None,
    execution_id: str,
    checkpoint: Path,
    workspace: Path,
    pid: int,
    pgid: int,
    inspector: ProcessInspector,
    output_root: Path,
) -> dict[str, Any]:
    observation = inspector.observe(pid)
    if observation.pid != pid or observation.pgid != pgid:
        raise RuntimeEvidenceError(f"registered process PID/PGID drift: {execution_id}")
    _assert_process_scope(observation, execution_id=execution_id, role=role)
    return {
        "role": role,
        "carrier": carrier,
        "executionId": execution_id,
        "pid": pid,
        "pgid": pgid,
        "processIdentityDigest": observation.identity_digest,
        "checkpointRef": safe_ref(checkpoint, output_root=output_root),
        "checkpointSha256": file_digest(checkpoint),
        "workspaceRef": safe_ref(
            workspace, output_root=output_root, require_file=False
        ),
    }


def create_runtime_evidence_session(
    *,
    runtime: CampaignRuntimePaths,
    identity: RuntimeEvidenceIdentity,
    session_id: str,
    campaign_plan_path: Path,
    inspector: ProcessInspector,
    queue_evidence_provider: ProviderBinding,
    fault_providers: Sequence[FaultProviderBinding],
    provider_fault_test_hook_attestation: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Freeze live controller/lane registrations without accepting caller PIDs."""
    snapshot = _assert_current_lease(runtime, identity)
    plan = _assert_plan(campaign_plan_path, identity)
    output_root = runtime.output_root
    snapshot_path = runtime_snapshot_path(runtime, identity.root_execution_id)
    execution_ids = dict(plan["executionIds"])
    controller = _process_row(
        role="controller",
        carrier=None,
        execution_id=identity.root_execution_id,
        checkpoint=snapshot_path,
        workspace=runtime_root(runtime, identity.root_execution_id),
        pid=int(snapshot.get("pid") or 0),
        pgid=int(snapshot.get("pgid") or 0),
        inspector=inspector,
        output_root=output_root,
    )
    workers: list[dict[str, Any]] = []
    for carrier in CARRIERS:
        checkpoint_path = lane_checkpoint_path(
            runtime, identity.root_execution_id, carrier
        )
        checkpoint = _load_mapping(
            checkpoint_path, label=f"{carrier} campaign lane checkpoint"
        )
        if (
            checkpoint.get("runId") != identity.run_id
            or checkpoint.get("generation") != identity.generation
            or checkpoint.get("fencingToken") != identity.fencing_token
            or checkpoint.get("carrier") != carrier
            or checkpoint.get("executionId") != execution_ids[carrier]
            or checkpoint.get("status") != "running"
        ):
            raise RuntimeEvidenceError(f"{carrier} lane is not current and running")
        workspace = Path(str(checkpoint.get("executionRoot") or ""))
        workers.append(
            _process_row(
                role="worker",
                carrier=carrier,
                execution_id=str(execution_ids[carrier]),
                checkpoint=checkpoint_path,
                workspace=workspace,
                pid=int(checkpoint.get("pid") or 0),
                pgid=int(checkpoint.get("pgid") or 0),
                inspector=inspector,
                output_root=output_root,
            )
        )
    provider_rows = [binding.as_document() for binding in fault_providers]
    provider_types = [row["faultType"] for row in provider_rows]
    if len(provider_types) != len(set(provider_types)):
        raise RuntimeEvidenceError("runtime fault provider bindings contain duplicates")
    if "worker_termination" not in provider_types:
        raise RuntimeEvidenceError("worker termination provider binding is required")
    hook_enabled = provider_fault_test_hook_attestation is not None
    from content.execution.runtime_evidence.fault_adapters import (
        is_unavailable_fault_binding_document,
    )

    provider_faults = {
        str(row["faultType"])
        for row in provider_rows
        if row["faultType"] in {"provider_timeout", "provider_rate_limit"}
        and not is_unavailable_fault_binding_document(row)
    }
    if provider_faults and not hook_enabled:
        raise RuntimeEvidenceError(
            "provider fault bindings require explicit test-hook attestation"
        )
    hook_ref: str | None = None
    hook_digest: str | None = None
    if provider_fault_test_hook_attestation is not None:
        validate_provider_fault_test_hook_attestation(
            provider_fault_test_hook_attestation,
            identity=identity,
            provider_rows=provider_rows,
        )
        hook_ref = safe_ref(
            provider_fault_test_hook_attestation, output_root=output_root
        )
        hook_digest = file_digest(provider_fault_test_hook_attestation)
    stable = {
        "schema": "quwoquan_data.runtime_evidence_session",
        "sessionId": session_id,
        **identity.as_document(),
        "campaignPlanRef": safe_ref(
            campaign_plan_path, output_root=output_root
        ),
        "campaignPlanSha256": file_digest(campaign_plan_path),
        "sourceRevision": plan["sourceRevision"],
        "sourceDigest": plan["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
        "runtimeSnapshotRef": safe_ref(snapshot_path, output_root=output_root),
        "runtimeSnapshotSha256": file_digest(snapshot_path),
        "leaseHeartbeatAt": snapshot["heartbeatAt"],
        "leaseSeconds": int(snapshot["leaseSeconds"]),
        "controller": controller,
        "workers": workers,
        "queueEvidenceProvider": queue_evidence_provider.as_document(),
        "faultProviders": provider_rows,
        "providerFaultTestHooksEnabled": hook_enabled,
        "providerFaultTestHookAttestationRef": hook_ref,
        "providerFaultTestHookAttestationSha256": hook_digest,
    }
    path = session_path(runtime, identity, session_id)
    document = write_create_once(
        path,
        stable=stable,
        schema_name="runtime_evidence_session",
        digest_field="receiptDigest",
        recorded_at_field="createdAt",
    )
    return document, path


__all__ = [
    "CARRIERS",
    "FAULT_TYPES",
    "FaultProviderBinding",
    "ProcessInspector",
    "ProcessObservation",
    "ProviderBinding",
    "RuntimeEvidenceError",
    "RuntimeEvidenceIdentity",
    "assert_current_session",
    "canonical_digest",
    "create_runtime_evidence_session",
    "file_digest",
    "load_runtime_evidence_session",
    "resolve_ref",
    "safe_ref",
    "session_path",
    "session_root",
    "validate_provider_fault_test_hook_attestation",
    "write_create_once",
]

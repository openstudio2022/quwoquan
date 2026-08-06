"""Canonical CLI facade for fenced campaign runtime evidence.

The facade deliberately exposes only adapters that exist in production code.
It never accepts an environment, process, provider, fault-type, command, or
argv selector from the caller.  Every action derives the current run identity
and all paths from the canonical campaign runtime snapshot.
"""
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.runtime_policy import active_runtime_policy

from content.execution.campaign_plan import plan_path
from content.execution.campaign_runtime import (
    assert_campaign_fence,
    read_runtime_snapshot,
)
from content.execution.campaign_workspace import CampaignRuntimePaths
from content.execution.identity import validate_execution_id
from content.execution.runtime_evidence_contract import (
    CARRIERS,
    RuntimeEvidenceError,
    RuntimeEvidenceIdentity,
    create_runtime_evidence_session,
    file_digest,
    load_runtime_evidence_session,
    safe_ref,
)
from content.execution.runtime_evidence_fault_adapters import (
    unavailable_fault_adapter,
)
from content.execution.runtime_evidence_faults import (
    CampaignWorkerTerminator,
    finalize_fault_cases,
    inject_fault,
)
from content.execution.runtime_evidence_observation import SystemProcessInspector
from content.execution.runtime_evidence_queue import (
    resolve_frozen_queue_evidence_provider,
)
from content.execution.runtime_evidence_sampling import (
    capture_resource_sample,
    finalize_resource_samples,
)

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _runtime_paths() -> CampaignRuntimePaths:
    return CampaignRuntimePaths.defaults()


def _identity_from_snapshot(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> RuntimeEvidenceIdentity:
    """Derive identity from canonical state; callers cannot select a generation."""
    root_id = validate_execution_id(root_execution_id)
    snapshot = read_runtime_snapshot(runtime, root_id)
    if not isinstance(snapshot, Mapping):
        raise RuntimeEvidenceError("campaign runtime snapshot is missing")
    run_id = str(snapshot.get("runId") or "").strip()
    fencing_token = str(snapshot.get("fencingToken") or "").strip()
    try:
        generation = int(snapshot.get("generation") or 0)
    except (TypeError, ValueError) as exc:
        raise RuntimeEvidenceError("campaign runtime generation is invalid") from exc
    if not run_id or generation < 1 or _DIGEST.fullmatch(fencing_token) is None:
        raise RuntimeEvidenceError("campaign runtime identity is incomplete")
    return RuntimeEvidenceIdentity(
        root_execution_id=root_id,
        run_id=run_id,
        generation=generation,
        fencing_token=fencing_token,
    )


def _summary(
    *,
    action: str,
    identity: RuntimeEvidenceIdentity,
    path: Path,
    runtime: CampaignRuntimePaths,
    receipt_digest: object | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "action": action,
        **identity.as_document(),
        "evidenceRef": safe_ref(path, output_root=runtime.output_root),
        "evidenceSha256": file_digest(path),
    }
    if receipt_digest is not None:
        result["receiptDigest"] = receipt_digest
    return result


def _worker_execution_id(
    session: Mapping[str, Any],
    *,
    carrier: str,
) -> str:
    matches = [
        str(row.get("executionId") or "")
        for row in session.get("workers") or []
        if isinstance(row, Mapping) and row.get("carrier") == carrier
    ]
    if len(matches) != 1 or not matches[0]:
        raise RuntimeEvidenceError(
            f"runtime evidence session has no unique {carrier} worker"
        )
    return matches[0]


def _execution_ids_from_plan(path: Path) -> dict[str, str]:
    payload = read_json(path)
    execution_ids = payload.get("executionIds") if isinstance(payload, Mapping) else None
    if not isinstance(execution_ids, Mapping) or set(execution_ids) != set(CARRIERS):
        raise RuntimeEvidenceError("campaign plan has no exact four-lane execution set")
    return {carrier: str(execution_ids[carrier]) for carrier in CARRIERS}


def _session_execution_ids(session: Mapping[str, Any]) -> dict[str, str]:
    rows = session.get("workers")
    if not isinstance(rows, list):
        raise RuntimeEvidenceError("runtime evidence session workers are invalid")
    execution_ids = {
        str(row.get("carrier") or ""): str(row.get("executionId") or "")
        for row in rows
        if isinstance(row, Mapping)
    }
    if set(execution_ids) != set(CARRIERS) or any(not value for value in execution_ids.values()):
        raise RuntimeEvidenceError("runtime evidence session has no exact four-lane set")
    return execution_ids


def _fault_providers() -> dict[str, Any]:
    providers: dict[str, Any] = {
        "worker_termination": CampaignWorkerTerminator(),
    }
    for fault_type in (
        "lease_expiry",
        "redis_restart",
        "mongo_reconnect",
        "provider_timeout",
        "provider_rate_limit",
    ):
        providers[fault_type] = unavailable_fault_adapter(fault_type)
    return providers


def _handle_create_session(args: argparse.Namespace) -> None:
    runtime = _runtime_paths()
    evidence_policy = active_runtime_policy().runtime_evidence
    identity = _identity_from_snapshot(runtime, args.campaign_root_execution_id)
    campaign_plan_path = plan_path(runtime, identity.root_execution_id)
    queue = resolve_frozen_queue_evidence_provider(
        _execution_ids_from_plan(campaign_plan_path)
    )
    providers = _fault_providers()
    document, path = create_runtime_evidence_session(
        runtime=runtime,
        identity=identity,
        session_id=str(args.session_id),
        campaign_plan_path=campaign_plan_path,
        inspector=SystemProcessInspector(
            timeout_seconds=evidence_policy.process_inspection_timeout_seconds
        ),
        queue_evidence_provider=queue.binding,
        fault_providers=tuple(
            providers[fault_type].binding
            for fault_type in (
                "worker_termination",
                "lease_expiry",
                "redis_restart",
                "mongo_reconnect",
                "provider_timeout",
                "provider_rate_limit",
            )
        ),
    )
    print(
        json.dumps(
            _summary(
                action="create-session",
                identity=identity,
                path=path,
                runtime=runtime,
                receipt_digest=document["receiptDigest"],
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


def _handle_sample(args: argparse.Namespace) -> None:
    runtime = _runtime_paths()
    evidence_policy = active_runtime_policy().runtime_evidence
    identity = _identity_from_snapshot(runtime, args.campaign_root_execution_id)
    session = load_runtime_evidence_session(runtime, identity, str(args.session_id))
    queue = resolve_frozen_queue_evidence_provider(_session_execution_ids(session))
    document, path = capture_resource_sample(
        runtime=runtime,
        identity=identity,
        session_id=str(args.session_id),
        sample_id=str(args.sample_id),
        inspector=SystemProcessInspector(
            timeout_seconds=evidence_policy.process_inspection_timeout_seconds
        ),
        queue_provider=queue,
    )
    print(
        json.dumps(
            _summary(
                action="sample",
                identity=identity,
                path=path,
                runtime=runtime,
                receipt_digest=document["receiptDigest"],
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


def _handle_fixed_fault(args: argparse.Namespace, *, fault_type: str) -> None:
    confirmation = (
        "confirm_active_worker_termination"
        if fault_type == "worker_termination"
        else "confirm_governed_fault_request"
    )
    if getattr(args, confirmation, False) is not True:
        raise RuntimeEvidenceError(
            f"{fault_type} requires explicit confirmation"
        )
    runtime = _runtime_paths()
    evidence_policy = active_runtime_policy().runtime_evidence
    identity = _identity_from_snapshot(runtime, args.campaign_root_execution_id)
    session_id = str(args.session_id)
    session = load_runtime_evidence_session(runtime, identity, session_id)
    carrier = str(args.carrier)
    execution_id = _worker_execution_id(session, carrier=carrier)
    queue = resolve_frozen_queue_evidence_provider(_session_execution_ids(session))
    providers = _fault_providers()
    document, path = inject_fault(
        runtime=runtime,
        identity=identity,
        session_id=session_id,
        case_id=str(args.case_id),
        fault_type=fault_type,
        carrier=carrier,
        execution_id=execution_id,
        job_id=str(args.job_id),
        inspector=SystemProcessInspector(
            timeout_seconds=evidence_policy.process_inspection_timeout_seconds
        ),
        queue_provider=queue,
        providers={fault_type: providers[fault_type]},
        queue_event_timeout_seconds=evidence_policy.queue_fault_event_timeout_seconds,
    )
    print(
        json.dumps(
            _summary(
                action=f"inject-{fault_type.replace('_', '-')}",
                identity=identity,
                path=path,
                runtime=runtime,
                receipt_digest=document["receiptDigest"],
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


def _handle_inject_worker_termination(args: argparse.Namespace) -> None:
    _handle_fixed_fault(args, fault_type="worker_termination")


def _handle_inject_lease_expiry(args: argparse.Namespace) -> None:
    _handle_fixed_fault(args, fault_type="lease_expiry")


def _handle_inject_redis_restart(args: argparse.Namespace) -> None:
    _handle_fixed_fault(args, fault_type="redis_restart")


def _handle_inject_mongo_reconnect(args: argparse.Namespace) -> None:
    _handle_fixed_fault(args, fault_type="mongo_reconnect")


def _handle_inject_provider_timeout(args: argparse.Namespace) -> None:
    _handle_fixed_fault(args, fault_type="provider_timeout")


def _handle_inject_provider_rate_limit(args: argparse.Namespace) -> None:
    _handle_fixed_fault(args, fault_type="provider_rate_limit")


def _handle_finalize(args: argparse.Namespace) -> None:
    runtime = _runtime_paths()
    identity = _identity_from_snapshot(runtime, args.campaign_root_execution_id)
    snapshot = assert_campaign_fence(
        runtime,
        identity.root_execution_id,
        run_id=identity.run_id,
        generation=identity.generation,
        fencing_token=identity.fencing_token,
    )
    if str(snapshot.get("status") or "") == "active":
        raise RuntimeEvidenceError(
            "runtime evidence cannot finalize while the campaign lease is active"
        )
    resources, resource_path = finalize_resource_samples(
        runtime=runtime,
        identity=identity,
        session_id=str(args.session_id),
    )
    faults, fault_path = finalize_fault_cases(
        runtime=runtime,
        identity=identity,
        session_id=str(args.session_id),
    )
    print(
        json.dumps(
            {
                "action": "finalize",
                **identity.as_document(),
                "resourceEvidenceRef": safe_ref(
                    resource_path, output_root=runtime.output_root
                ),
                "resourceEvidenceSha256": file_digest(resource_path),
                "resourceSampleCount": len(resources["samples"]),
                "faultEvidenceRef": safe_ref(
                    fault_path, output_root=runtime.output_root
                ),
                "faultEvidenceSha256": file_digest(fault_path),
                "faultCaseCount": len(faults["cases"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _add_session_identity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--campaign-root-execution-id", required=True)
    parser.add_argument("--session-id", required=True)


def _add_fault_target(parser: argparse.ArgumentParser) -> None:
    _add_session_identity(parser)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--carrier", required=True, choices=CARRIERS)
    parser.add_argument("--job-id", required=True)


def register_runtime_evidence_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "runtime-evidence",
        help="从当前 fenced campaign 采集 create-once runtime evidence",
    )
    actions = parser.add_subparsers(dest="runtime_evidence_action", required=True)

    create = actions.add_parser(
        "create-session",
        help="冻结当前 controller、四 lane、queue 与内置故障 adapter",
    )
    _add_session_identity(create)
    create.set_defaults(handler=_handle_create_session)

    sample = actions.add_parser(
        "sample",
        help="从固定 OS、queue 与 workspace observer 采样",
    )
    _add_session_identity(sample)
    sample.add_argument("--sample-id", required=True)
    sample.set_defaults(handler=_handle_sample)

    inject = actions.add_parser(
        "inject-worker-termination",
        help="仅终止 session 已冻结的一条 worker process group",
    )
    _add_fault_target(inject)
    inject.add_argument(
        "--confirm-active-worker-termination",
        action="store_true",
        required=True,
        help="确认对当前 fenced worker 执行受治理的 process-group 终止",
    )
    inject.set_defaults(handler=_handle_inject_worker_termination)

    fixed_fault_actions = (
        ("inject-lease-expiry", _handle_inject_lease_expiry),
        ("inject-redis-restart", _handle_inject_redis_restart),
        ("inject-mongo-reconnect", _handle_inject_mongo_reconnect),
        ("inject-provider-timeout", _handle_inject_provider_timeout),
        ("inject-provider-rate-limit", _handle_inject_provider_rate_limit),
    )
    for name, handler in fixed_fault_actions:
        fixed = actions.add_parser(
            name,
            help=f"创建固定 {name.removeprefix('inject-')} typed fault request",
        )
        _add_fault_target(fixed)
        fixed.add_argument(
            "--confirm-governed-fault-request",
            action="store_true",
            required=True,
            help="确认创建受治理 fault intent；无 owner callback 时 fail closed",
        )
        fixed.set_defaults(handler=handler)

    finalize = actions.add_parser(
        "finalize",
        help="在 campaign 终态后投影 resource/fault raw evidence",
    )
    _add_session_identity(finalize)
    finalize.set_defaults(handler=_handle_finalize)


__all__ = ["register_runtime_evidence_parser"]

"""Aggregate Cursor SDK runtime evidence for managed/local/fanout/supervisor runs."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from _common.io import read_json, write_json
from _common.ops_governance import failure_ledger_path, summarize_failure_ledger
from _common.paths import (
    OUTPUT_ARTIFACTS_ROOT,
    batch_shared_dir,
    batch_workflow_state_path,
    fanout_run_matrix_path,
    now_iso,
)

SDK_MONITORING_SCHEMA = "quwoquan_data.sdk_monitoring_report/1"
_ARTIFACTS_ROOT = OUTPUT_ARTIFACTS_ROOT


def _read_json_if_file(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _latest_matching_file(root: Path, patterns: list[str]) -> Path | None:
    if not root.is_dir():
        return None
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(path for path in root.rglob(pattern) if path.is_file())
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _discover_startup_probe_path() -> Path | None:
    return _latest_matching_file(
        _ARTIFACTS_ROOT,
        [
            "*cursor_probe*.json",
            "*local_cursor_probe*.json",
        ],
    )


def _discover_watchdog_log_path() -> Path | None:
    return _latest_matching_file(_ARTIFACTS_ROOT, ["*watchdog_kills*.log"])


def _startup_probe_summary(path: Path | None) -> dict[str, Any]:
    data = _read_json_if_file(path)
    if not data:
        return {"exists": False, "path": str(path) if path else ""}
    return {
        "exists": True,
        "path": str(path),
        "schemaVersion": str(data.get("schemaVersion") or ""),
        "ready": bool(data.get("ready")),
        "attempts": _safe_int(data.get("attempts")),
        "successCount": _safe_int(data.get("successCount")),
        "authFailures": _safe_int(data.get("authFailures")),
        "true5xxCount": _safe_int(data.get("true5xxCount")),
        "startupTimeoutCount": _safe_int(data.get("startupTimeoutCount")),
        "bridgeDisconnectCount": _safe_int(data.get("bridgeDisconnectCount")),
        "startupLatencyP95": _safe_float(data.get("startupLatencyP95")),
        "issues": list(data.get("issues") or []),
    }


def _watchdog_summary(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"exists": False, "path": str(path) if path else "", "eventCount": 0}
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {
        "exists": True,
        "path": str(path),
        "eventCount": len(lines),
        "lastEvent": lines[-1][:1000] if lines else "",
    }


def _run_matrix_summary(path: Path | None) -> dict[str, Any]:
    data = _read_json_if_file(path)
    if not data:
        return {"exists": False, "path": str(path) if path else ""}
    orchestrators = [item for item in (data.get("orchestrators") or []) if isinstance(item, Mapping)]
    workers = [item for item in (data.get("workers") or []) if isinstance(item, Mapping)]
    summary = data.get("summary") if isinstance(data.get("summary"), Mapping) else {}
    reached = sum(1 for item in orchestrators if bool(item.get("reached")))
    errors = [str(item.get("error") or "") for item in orchestrators if str(item.get("error") or "").strip()]
    return {
        "exists": True,
        "path": str(path),
        "schemaVersion": str(data.get("schemaVersion") or ""),
        "executionBranch": str(data.get("executionBranch") or (summary.get("executionBranch") or "")),
        "credentialIngress": dict(summary.get("credentialIngress") or {}),
        "orchestratorCount": len(orchestrators),
        "orchestratorReachedCount": reached,
        "orchestratorErrorCount": len(errors),
        "workerCount": len(workers),
        "summary": {
            "assignments": _safe_int(summary.get("assignments")),
            "leased": _safe_int(summary.get("leased")),
            "completed": _safe_int(summary.get("completed")),
            "failed": _safe_int(summary.get("failed")),
            "attemptFailures": _safe_int(summary.get("attemptFailures")),
            "startupFailures": _safe_int(summary.get("startupFailures")),
            "orchestrationFailed": _safe_int(summary.get("orchestrationFailed")),
            "connectionRefused": _safe_int(summary.get("connectionRefused")),
            "throughput": dict(summary.get("throughput") or {}),
        },
    }


def _object_queue_summary(task_id: str, batch_id: str) -> dict[str, Any]:
    queue_dir = batch_shared_dir(task_id, batch_id) / "object_queue"
    counts: dict[str, int] = {}
    startup_failure_jobs = 0
    startup_failure_count = 0
    reconciled_jobs = 0
    if queue_dir.is_dir():
        for path in sorted(queue_dir.glob("*.json")):
            data = _read_json_if_file(path) or {}
            state = str(data.get("state") or "unknown")
            counts[state] = counts.get(state, 0) + 1
            failures = _safe_int(data.get("startupFailureCount"))
            if failures > 0:
                startup_failure_jobs += 1
                startup_failure_count += failures
            timings = [item for item in (data.get("timings") or []) if isinstance(item, Mapping)]
            if any(str(item.get("event") or "") == "reconciled" for item in timings):
                reconciled_jobs += 1
    return {
        "path": str(queue_dir),
        "counts": counts,
        "deadJobs": _safe_int(counts.get("dead")),
        "failedJobs": _safe_int(counts.get("failed")),
        "startupFailureJobs": startup_failure_jobs,
        "startupFailureCount": startup_failure_count,
        "staleRecoveryCount": reconciled_jobs,
    }


def _managed_batch_audit_summary(task_id: str, batch_id: str) -> dict[str, Any]:
    audit_path = batch_shared_dir(task_id, batch_id) / "managed_batch_audit.json"
    audit = _read_json_if_file(audit_path)
    if audit is None:
        try:
            from task.target_selection import audit_managed_batch

            audit = audit_managed_batch(task_id, batch_id)
        except Exception:
            audit = None
    if not audit:
        return {"exists": False, "path": str(audit_path)}
    last_agent = audit.get("lastAgentRun") if isinstance(audit.get("lastAgentRun"), Mapping) else {}
    return {
        "exists": True,
        "path": str(audit_path),
        "failedLaneCount": _safe_int(audit.get("failedLaneCount")),
        "lanePassed": dict(audit.get("lanePassed") or {}),
        "inactiveEntityArtifactCount": _safe_int(audit.get("inactiveEntityArtifactCount")),
        "replacementCount": _safe_int(audit.get("replacementCount")),
        "abandonedCount": _safe_int(audit.get("abandonedCount")),
        "abandonedContentCount": _safe_int(audit.get("abandonedContentCount")),
        "workflowState": dict(audit.get("workflowState") or {}),
        "lastAgentRun": dict(last_agent),
    }


def _env_ready_summary(shared: Path) -> dict[str, Any]:
    path = shared / "env_ready_report.json"
    report = _read_json_if_file(path)
    if not report:
        return {"exists": False, "path": str(path)}
    preflight = report.get("preflight") if isinstance(report.get("preflight"), Mapping) else {}
    startup = report.get("cursorStartup") if isinstance(report.get("cursorStartup"), Mapping) else {}
    if not startup:
        startup = preflight.get("cursorStartup") if isinstance(preflight, Mapping) else {}
    return {
        "exists": True,
        "path": str(path),
        "ready": bool(report.get("ready")),
        "agentProvider": str(report.get("agentProvider") or ""),
        "model": str(report.get("model") or ""),
        "startupTimeoutSeconds": _safe_float(report.get("startupTimeoutSeconds")),
        "credentialIngress": dict(report.get("credentialIngress") or {}),
        "runtimeRoots": dict(report.get("runtimeRoots") or {}),
        "cursorStartup": dict(startup or {}),
        "issues": list((preflight.get("issues") or report.get("issues") or [])[:20]) if isinstance(preflight, Mapping) else [],
    }


def _startup_probe_from_env_ready(env_ready: Mapping[str, Any]) -> dict[str, Any]:
    startup = env_ready.get("cursorStartup") if isinstance(env_ready.get("cursorStartup"), Mapping) else {}
    if not startup:
        return {"exists": False, "path": str(env_ready.get("path") or "")}
    return {
        "exists": True,
        "path": str(env_ready.get("path") or ""),
        "derivedFromEnvReady": True,
        "schemaVersion": str(startup.get("schemaVersion") or ""),
        "checked": bool(startup.get("checked")),
        "ready": bool(startup.get("ready")),
        "status": str(startup.get("status") or ""),
        "attempts": _safe_int(startup.get("attempts")),
        "successCount": _safe_int(startup.get("successCount")),
        "authFailures": _safe_int(startup.get("authFailures")),
        "true5xxCount": _safe_int(startup.get("true5xxCount")),
        "startupTimeoutCount": _safe_int(startup.get("startupTimeoutCount")),
        "bridgeDisconnectCount": _safe_int(startup.get("bridgeDisconnectCount")),
        "startupLatencyP95": _safe_float(startup.get("startupLatencyP95")),
        "timeoutSeconds": _safe_float(
            startup.get("timeoutSeconds") or env_ready.get("startupTimeoutSeconds")
        ),
        "issues": list(startup.get("issues") or []),
    }


def _ship_report_summary(shared: Path) -> dict[str, Any]:
    path = shared / "ship_report.json"
    report = _read_json_if_file(path)
    if not report:
        return {"exists": False, "path": str(path)}
    import_reports = []
    for raw in report.get("importReports") or []:
        import_path = Path(str(raw))
        import_payload = _read_json_if_file(import_path)
        import_reports.append(
            {
                "path": str(import_path),
                "exists": import_payload is not None,
                "status": str((import_payload or {}).get("status") or ""),
                "releaseId": str((import_payload or {}).get("releaseId") or ""),
            }
        )
    return {
        "exists": True,
        "path": str(path),
        "closureType": str(report.get("closureType") or "ship"),
        "dataReleaseId": str(report.get("dataReleaseId") or ""),
        "sourceReleaseId": str(report.get("sourceReleaseId") or ""),
        "envs": [str(item) for item in (report.get("envs") or [])],
        "importRequested": bool(report.get("importRequested")),
        "dryRun": bool(report.get("dryRun")),
        "summary": [dict(item) for item in (report.get("summary") or []) if isinstance(item, Mapping)],
        "importReports": import_reports,
    }


def _failure_ledger_summary(task_id: str, batch_id: str) -> dict[str, Any]:
    path = failure_ledger_path(task_id, batch_id)
    if not path.is_file():
        return {"exists": False, "path": str(path), "totalFailures": 0, "byCategory": {}, "abandonedByReason": {}}
    summary = summarize_failure_ledger(task_id, batch_id)
    return {
        "exists": True,
        "path": str(path),
        "totalFailures": _safe_int(summary.get("totalFailures")),
        "byCategory": dict(summary.get("byCategory") or {}),
        "abandonedByReason": dict(summary.get("abandonedByReason") or {}),
    }


def build_sdk_monitoring_report(
    task_id: str,
    batch_id: str,
    *,
    plan_id: str | None = None,
    startup_probe_path: str | Path | None = None,
    watchdog_log_path: str | Path | None = None,
    run_matrix_path: str | Path | None = None,
    accept_estimated_token_ledger: bool = False,
) -> dict[str, Any]:
    shared = batch_shared_dir(task_id, batch_id)
    workflow_path = batch_workflow_state_path(task_id, batch_id)
    workflow = _read_json_if_file(workflow_path) or {}
    token_ledger_path = shared / "token_ledger.json"
    token_ledger = _read_json_if_file(token_ledger_path) or {}

    # Do not auto-discover global startup/watchdog artifacts for a batch report:
    # they are not batch-scoped and can silently import stale evidence from an
    # unrelated run. Callers must pass explicit paths when they want those
    # signals included.
    startup_path = Path(startup_probe_path) if startup_probe_path else None
    watchdog_path = Path(watchdog_log_path) if watchdog_log_path else None
    matrix_path = (
        Path(run_matrix_path)
        if run_matrix_path
        else (fanout_run_matrix_path(str(plan_id)) if str(plan_id or "").strip() else None)
    )

    external_startup = _startup_probe_summary(startup_path)
    watchdog = _watchdog_summary(watchdog_path)
    run_matrix = _run_matrix_summary(matrix_path)
    managed_audit = _managed_batch_audit_summary(task_id, batch_id)
    object_queue = _object_queue_summary(task_id, batch_id)
    env_ready = _env_ready_summary(shared)
    startup = _startup_probe_from_env_ready(env_ready)
    ship_report = _ship_report_summary(shared)
    failure_summary = _failure_ledger_summary(task_id, batch_id)

    throughput = dict(workflow.get("throughput") or {})
    quality = dict(workflow.get("quality") or {})
    last_agent = dict(workflow.get("lastAgentRun") or {})
    token_summary = dict(token_ledger.get("summary") or {})
    token_measurement_mode = str(token_ledger.get("measurementMode") or "")

    auth_vs_infra = {
        "startupProbeAuthFailures": _safe_int(startup.get("authFailures")),
        "startupProbeTrue5xxCount": _safe_int(startup.get("true5xxCount")),
        "startupProbeBridgeDisconnectCount": _safe_int(startup.get("bridgeDisconnectCount")),
        "workflowInfrastructureFailures": _safe_int(last_agent.get("infrastructureFailures")),
        "managedAuditInfrastructureFailures": _safe_int((managed_audit.get("lastAgentRun") or {}).get("infrastructureFailures")),
        "runMatrixStartupFailures": _safe_int((run_matrix.get("summary") or {}).get("startupFailures")),
        "runMatrixConnectionRefused": _safe_int((run_matrix.get("summary") or {}).get("connectionRefused")),
    }

    issues: list[str] = []
    accepted_deviations: list[str] = []
    if not workflow:
        issues.append("task_workflow_state.json missing")
    if not token_ledger:
        issues.append("token_ledger.json missing")
    elif token_measurement_mode == "estimated_from_artifacts":
        if accept_estimated_token_ledger:
            # 显式接受口径（acceptance GWT2 / 2026-07-06 用户裁定）：本地 cursor_sdk bridge
            # 不回传 usage，estimated 账本可准出；默认仍视为 issue，禁止静默放宽。
            accepted_deviations.append(
                "tokenLedger.measurementMode=estimated_from_artifacts "
                "(explicitly accepted via --accept-estimated-token-ledger)"
            )
        else:
            issues.append("tokenLedger.measurementMode=estimated_from_artifacts")
    if not managed_audit.get("exists"):
        issues.append("managed_batch_audit.json missing")
    if not env_ready.get("exists"):
        issues.append("env_ready_report.json missing")
    elif not env_ready.get("ready"):
        issues.append("env_ready_report.ready=false")
    if not startup.get("exists"):
        issues.append("startup probe report missing")
    elif not startup.get("checked"):
        issues.append("env_ready_report.cursorStartup.checked=false")
    if str(plan_id or "").strip() and not run_matrix.get("exists"):
        issues.append(f"run_matrix.json missing for planId={plan_id}")
    if ship_report.get("exists") and ship_report.get("importRequested") and not ship_report.get("importReports"):
        issues.append("ship_report.importRequested=true but importReports is empty")
    if _safe_int(startup.get("authFailures")) > 0:
        issues.append(f"startupProbe.authFailures={startup.get('authFailures')}")
    if _safe_int(startup.get("true5xxCount")) > 0:
        issues.append(f"startupProbe.true5xxCount={startup.get('true5xxCount')}")
    if _safe_int(startup.get("bridgeDisconnectCount")) > 0:
        issues.append(f"startupProbe.bridgeDisconnectCount={startup.get('bridgeDisconnectCount')}")
    if _safe_int(last_agent.get("infrastructureFailures")) > 0:
        issues.append(f"lastAgentRun.infrastructureFailures={last_agent.get('infrastructureFailures')}")
    if _safe_int((managed_audit.get("lastAgentRun") or {}).get("infrastructureFailures")) > 0:
        issues.append(
            "managedBatchAudit.lastAgentRun.infrastructureFailures="
            + str((managed_audit.get("lastAgentRun") or {}).get("infrastructureFailures"))
        )
    if _safe_int(managed_audit.get("failedLaneCount")) > 0:
        issues.append(f"managedBatchAudit.failedLaneCount={managed_audit.get('failedLaneCount')}")
    if _safe_int(object_queue.get("deadJobs")) > 0:
        issues.append(f"objectQueue.deadJobs={object_queue.get('deadJobs')}")
    if _safe_int(watchdog.get("eventCount")) > 0:
        issues.append(f"watchdog.eventCount={watchdog.get('eventCount')}")
    if _safe_int((run_matrix.get("summary") or {}).get("startupFailures")) > 0:
        issues.append(f"runMatrix.startupFailures={(run_matrix.get('summary') or {}).get('startupFailures')}")
    if _safe_int((run_matrix.get("summary") or {}).get("orchestrationFailed")) > 0:
        issues.append(
            f"runMatrix.orchestrationFailed={(run_matrix.get('summary') or {}).get('orchestrationFailed')}"
        )

    return {
        "schemaVersion": SDK_MONITORING_SCHEMA,
        "createdAt": now_iso(),
        "taskId": task_id,
        "batchId": batch_id,
        "planId": str(plan_id or ""),
        "passed": not issues,
        "issues": issues,
        "acceptedDeviations": accepted_deviations,
        "workflowState": {
            "path": str(workflow_path),
            "status": str(workflow.get("status") or ""),
            "waitingCheckpoint": str(workflow.get("waitingCheckpoint") or ""),
            "nextAction": str(workflow.get("nextAction") or ""),
            "completedCount": len(workflow.get("completed") or []),
        },
        "throughput": {
            "objectsPerHour": _safe_float(throughput.get("objectsPerHour")),
            "elapsedSeconds": _safe_float(throughput.get("elapsedSeconds")),
            "postCount": _safe_int(throughput.get("postCount")),
            "maxWorkers": _safe_int(throughput.get("maxWorkers")),
            "agentActive": bool(throughput.get("agentActive")),
        },
        "quality": {
            "firstPassRate": _safe_float(quality.get("firstPassRate")),
            "reviewedRefs": _safe_int(quality.get("reviewedRefs")),
            "repairedRefs": _safe_int(quality.get("repairedRefs")),
        },
        "tokenLedger": {
            "path": str(token_ledger_path),
            "measurementMode": token_measurement_mode,
            "entryCount": _safe_int(token_summary.get("entryCount")),
            "usedTokens": _safe_int(token_summary.get("usedTokens")),
            "averageUsedTokens": _safe_float(token_summary.get("averageUsedTokens")),
            "unitPassedCostUsd": _safe_float(token_summary.get("unitPassedCostUsd")),
        },
        "envReady": env_ready,
        "shipReport": ship_report,
        "failureLedger": failure_summary,
        "managedBatchAudit": managed_audit,
        "objectQueue": object_queue,
        "startupProbe": startup,
        "externalStartupProbe": external_startup,
        "watchdog": watchdog,
        "runMatrix": run_matrix,
        "authVsInfra": auth_vs_infra,
    }


def write_sdk_monitoring_report(path: str | Path, report: Mapping[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, dict(report))
    return target


__all__ = [
    "SDK_MONITORING_SCHEMA",
    "build_sdk_monitoring_report",
    "write_sdk_monitoring_report",
]

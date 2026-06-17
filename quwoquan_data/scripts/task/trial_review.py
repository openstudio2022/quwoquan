"""Managed trial review and convergence diagnostics.

This module turns a managed content trial into a repeatable readiness report.
It is deliberately evidence-first: missing runtime artifacts are reported as a
workflow/infra issue instead of being treated as content-quality feedback.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from _common.io import read_json, read_ndjson, write_json
from _common.paths import (
    batch_root,
    batch_shared_dir,
    committed_task_progress,
    release_manifest,
    task_baseline_freeze_packet_path,
    task_catalog,
    task_shared_dir,
)
from task import store


SCHEMA_VERSION = "quwoquan_data.trial_review/1"
LANES = ("homepage", "article", "image")


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = read_json(path)
    except Exception as exc:  # noqa: BLE001
        return {"_readError": f"{type(exc).__name__}: {exc}"}
    return data if isinstance(data, dict) else {"_value": data}


def _count_ndjson(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return len(read_ndjson(path))
    except Exception:  # noqa: BLE001
        return 0


def _coverage_target_names(spec: Mapping[str, Any]) -> list[str]:
    targets = (((spec.get("scope") or {}).get("coverageTargets") or []) if isinstance(spec, Mapping) else [])
    names: list[str] = []
    for target in targets:
        if not isinstance(target, Mapping):
            continue
        name = str(target.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def _quota_int(quotas: Mapping[str, Any], *keys: str, default: int = 0) -> int:
    for key in keys:
        if key in quotas:
            try:
                return max(0, int(quotas.get(key) or 0))
            except (TypeError, ValueError):
                return default
    return default


def _trial_scope(spec: Mapping[str, Any]) -> dict[str, Any]:
    names = _coverage_target_names(spec)
    content = spec.get("content") or {}
    quotas = content.get("quotas") or {}
    if not isinstance(quotas, Mapping):
        quotas = {}
    target_count = len(names)
    article_per_target = _quota_int(quotas, "entityArticlesPerTarget", default=0)
    image_per_target = _quota_int(quotas, "imageWorksPerTarget", default=0)
    homepage_per_target = _quota_int(quotas, "entityHomepagesPerTarget", default=1)
    article_jobs = target_count * article_per_target
    image_jobs = target_count * image_per_target
    queue_policy = spec.get("queuePolicy") if isinstance(spec.get("queuePolicy"), Mapping) else {}
    research = content.get("research") if isinstance(content.get("research"), Mapping) else {}
    return {
        "targetCount": target_count,
        "targets": names,
        "modalityContract": str(content.get("modalityContract") or ""),
        "carriers": list(content.get("carriers") or []),
        "quotas": {
            "entityArticlesPerTarget": article_per_target,
            "imageWorksPerTarget": image_per_target,
            "entityHomepagesPerTarget": homepage_per_target,
        },
        "estimatedObjects": {
            "homepages": target_count * homepage_per_target,
            "articleDrafts": article_jobs,
            "imageWorks": image_jobs,
            "totalPublishableObjects": target_count * homepage_per_target + article_jobs + image_jobs,
        },
        "agentCallPlan": {
            "creativeAuthorJobs": article_jobs + image_jobs,
            "expectedModelCriticalStage": "produce_author",
            "deterministicFirstStages": ["download_plan_prepare", "build_homepage", "content_plan"],
        },
        "executionPolicy": {
            "queueBackend": str(queue_policy.get("backend") or ""),
            "maxConcurrency": _quota_int(research, "maxConcurrency", default=0),
            "laneConcurrency": dict(research.get("laneConcurrency") or {}),
        },
    }


def _managed_runtime_config() -> dict[str, Any]:
    from task import run as run_mod

    return {
        "localCursorMaxWorkers": int(getattr(run_mod, "MANAGED_LOCAL_CURSOR_MAX_WORKERS", 1)),
        "agentTimeoutSeconds": int(getattr(run_mod, "MANAGED_AGENT_TIMEOUT_SECONDS", 240)),
        "futureGraceSeconds": int(getattr(run_mod, "MANAGED_AGENT_FUTURE_GRACE_SECONDS", 15)),
        "laneLimits": dict(getattr(run_mod, "MANAGED_LANE_LIMITS", {})),
        "runnerMode": "isolated_subprocess_per_agent_job",
        "knownCostShape": (
            "local managed starts one killable subprocess per prompt and launches a local Cursor bridge inside it"
        ),
    }


def _workflow_snapshot(task_id: str, batch_id: str) -> dict[str, Any]:
    shared = batch_shared_dir(task_id, batch_id)
    state = _load_json_if_exists(shared / "task_workflow_state.json")
    last_agent = state.get("lastAgentRun") or {}
    if not isinstance(last_agent, Mapping):
        last_agent = {}
    agent_history = state.get("agentRunHistory") if isinstance(state.get("agentRunHistory"), list) else []
    return {
        "batchRootExists": batch_root(task_id, batch_id).is_dir(),
        "workflowStateExists": (shared / "task_workflow_state.json").is_file(),
        "workflowState": {
            key: state.get(key)
            for key in (
                "status",
                "waitingCheckpoint",
                "owner",
                "nextAction",
                "retryCounts",
                "infrastructureRetryCounts",
                "failedObjects",
                "throughput",
                "quality",
            )
        },
        "lastAgentRun": {
            key: last_agent.get(key)
            for key in (
                "stage",
                "jobCount",
                "plannedJobCount",
                "startedCount",
                "finishedCount",
                "infrastructureFailures",
                "scheduler",
                "finishedAt",
            )
        },
        "agentRunHistory": [
            {
                key: row.get(key)
                for key in (
                    "stage",
                    "jobCount",
                    "plannedJobCount",
                    "startedCount",
                    "finishedCount",
                    "infrastructureFailures",
                    "scheduler",
                    "finishedAt",
                )
            }
            for row in agent_history
            if isinstance(row, Mapping)
        ],
    }


def _artifact_evidence(task_id: str, batch_id: str) -> dict[str, Any]:
    shared = batch_shared_dir(task_id, batch_id)
    baseline_report = _load_json_if_exists(task_shared_dir(task_id) / "baseline_report.json")
    auto_research = _load_json_if_exists(shared / "auto_research_plan.json")
    managed_env = _load_json_if_exists(shared / "managed_env_ready.json")
    env_ready = _load_json_if_exists(shared / "env_ready_report.json")
    token_ledger = _load_json_if_exists(shared / "token_ledger.json")
    managed_audit = _load_json_if_exists(shared / "managed_batch_audit.json")
    content_plan_diag = _load_json_if_exists(shared / "content_plan_source_diagnostics.json")
    release_id = ""
    for candidate in (shared / "release_report.json", shared / "publish_report.json"):
        report = _load_json_if_exists(candidate)
        if report:
            release_id = str(report.get("releaseId") or report.get("release_id") or "")
            break
    if not release_id:
        inferred_release_id = f"{task_id.replace('/', '__')}__{batch_id}"
        if release_manifest(inferred_release_id).is_file():
            release_id = inferred_release_id
    import_paths = [
        str(path)
        for path in (
            shared / "import_report.json",
            shared / "ship_report.json",
            shared / "staging_import_report.json",
            shared / "gamma_import_report.json",
        )
        if path.is_file()
    ]
    return {
        "taskSpecExists": store.spec_exists(task_id),
        "progressExists": committed_task_progress(task_id).is_file(),
        "baselinePacketExists": task_baseline_freeze_packet_path(task_id).is_file(),
        "baselineReportExists": bool(baseline_report),
        "baselineStatus": baseline_report.get("status") or baseline_report.get("result"),
        "catalogExists": task_catalog(task_id).is_file(),
        "catalogRows": _count_ndjson(task_catalog(task_id)),
        "autoResearchPlanExists": bool(auto_research),
        "autoResearchSummary": {
            "readyTargets": len(((auto_research.get("sourceAvailability") or {}).get("readyTargets") or []))
            if isinstance(auto_research.get("sourceAvailability"), Mapping)
            else 0,
            "ineligibleTargets": len(((auto_research.get("sourceAvailability") or {}).get("ineligibleTargets") or []))
            if isinstance(auto_research.get("sourceAvailability"), Mapping)
            else 0,
        },
        "managedEnvReadyReportExists": bool(managed_env),
        "managedEnvReady": managed_env.get("ready"),
        "managedEnvIssues": managed_env.get("issues") or [],
        "envReadyReportExists": bool(env_ready),
        "envReady": env_ready.get("ready"),
        "envReadyIssues": env_ready.get("issues") or [],
        "managedBatchAuditExists": bool(managed_audit),
        "managedBatchAudit": {
            "targetCount": managed_audit.get("targetCount"),
            "lanePassed": managed_audit.get("lanePassed"),
            "failedLaneCount": managed_audit.get("failedLaneCount"),
            "abandonedCount": managed_audit.get("abandonedCount"),
        },
        "contentPlanSourceDiagnosticsExists": bool(content_plan_diag),
        "contentPlanSourceDiagnostics": {
            target: {
                key: value
                for key, value in (row if isinstance(row, Mapping) else {}).items()
                if key in {
                    "rawArticleBaseSources",
                    "qualifiedArticleBaseSources",
                    "pickedArticleBaseSources",
                    "pickedImageSources",
                    "articleRejects",
                }
            }
            for target, row in ((content_plan_diag.get("targets") or {}).items())
        } if isinstance(content_plan_diag.get("targets"), Mapping) else {},
        "tokenLedgerExists": bool(token_ledger),
        "tokenLedgerSummary": token_ledger.get("summary") or {},
        "releaseEvidenceExists": bool(release_id),
        "releaseId": release_id,
        "importEvidencePaths": import_paths,
    }


def _failure_score(snapshot: Mapping[str, Any], evidence: Mapping[str, Any] | None = None) -> int:
    score = 0
    if not snapshot.get("batchRootExists"):
        score += 30
    if not snapshot.get("workflowStateExists"):
        score += 30
    state = snapshot.get("workflowState") or {}
    if isinstance(state, Mapping):
        if state.get("waitingCheckpoint"):
            score += 10
        failed_objects = state.get("failedObjects") or []
        score += min(20, len(failed_objects) * 2) if isinstance(failed_objects, list) else 4
        status = str(state.get("status") or "")
        if status in {"repairing", "manual_required", "failed"}:
            score += 10
    last_agent = snapshot.get("lastAgentRun") or {}
    if isinstance(last_agent, Mapping):
        score += 5 * int(last_agent.get("infrastructureFailures") or 0)
        job_count = int(last_agent.get("jobCount") or 0)
        finished = int(last_agent.get("finishedCount") or 0)
        if job_count and finished < job_count:
            score += min(20, job_count - finished)
    if evidence:
        audit = evidence.get("managedBatchAudit") or {}
        if isinstance(audit, Mapping):
            score += min(30, int(audit.get("failedLaneCount") or 0))
        if not evidence.get("baselinePacketExists"):
            score += 20
    return score


def _compare_scores(compare_runs: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task_id, batch_id in compare_runs:
        snapshot = _workflow_snapshot(task_id, batch_id)
        evidence = _artifact_evidence(task_id, batch_id)
        rows.append({
            "taskId": task_id,
            "batchId": batch_id,
            "score": _failure_score(snapshot, evidence),
            "status": (snapshot.get("workflowState") or {}).get("status"),
            "waitingCheckpoint": (snapshot.get("workflowState") or {}).get("waitingCheckpoint"),
            "failedLaneCount": (evidence.get("managedBatchAudit") or {}).get("failedLaneCount"),
            "infrastructureFailures": (snapshot.get("lastAgentRun") or {}).get("infrastructureFailures"),
        })
    return rows


def _convergence(
    current_score: int,
    workflow: Mapping[str, Any],
    comparisons: list[dict[str, Any]],
) -> dict[str, Any]:
    if not workflow.get("batchRootExists"):
        return {
            "status": "not_started",
            "trend": "not_evaluable",
            "score": current_score,
            "observations": ["no batch runtime exists; trial stopped before managed workflow evidence"],
            "comparisons": comparisons,
        }
    if not workflow.get("workflowStateExists"):
        return {
            "status": "no_workflow_state",
            "trend": "not_evaluable",
            "score": current_score,
            "observations": ["batch directory exists but task_workflow_state.json is missing"],
            "comparisons": comparisons,
        }
    last_agent = workflow.get("lastAgentRun") or {}
    observations: list[str] = []
    if not any(last_agent.get(key) for key in ("stage", "jobCount", "plannedJobCount")):
        observations.append("workflow has not recorded an agent run yet")
    if comparisons:
        scores = [int(item["score"]) for item in comparisons] + [current_score]
        if len(scores) >= 2 and scores[-1] < min(scores[:-1]):
            trend = "improving"
        elif len(scores) >= 2 and scores[-1] > scores[-2]:
            trend = "regressing"
        elif len(set(scores[-2:])) == 1:
            trend = "flat"
        else:
            trend = "mixed"
    else:
        trend = "insufficient_history"
        observations.append("no comparison runs were supplied; trend cannot be proven")
    return {
        "status": "evaluable" if comparisons else "single_run_only",
        "trend": trend,
        "score": current_score,
        "observations": observations,
        "comparisons": comparisons,
    }


def _blockers_and_warnings(
    *,
    scope: Mapping[str, Any],
    workflow: Mapping[str, Any],
    evidence: Mapping[str, Any],
    env: Mapping[str, str],
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not evidence.get("baselinePacketExists"):
        blockers.append("baseline freeze packet missing")
    if not workflow.get("batchRootExists"):
        blockers.append("managed batch runtime missing; no end-to-end trial evidence")
    if workflow.get("batchRootExists") and not workflow.get("workflowStateExists"):
        blockers.append("task_workflow_state.json missing")
    state = workflow.get("workflowState") or {}
    if isinstance(state, Mapping):
        waiting = str(state.get("waitingCheckpoint") or "").strip()
        status = str(state.get("status") or "").strip()
        failed = state.get("failedObjects") or []
        if waiting:
            blockers.append(f"workflow stuck at checkpoint {waiting}")
        if status in {"repairing", "manual_required", "failed"}:
            blockers.append(f"workflow status is {status}")
        if isinstance(failed, list) and failed:
            blockers.append(f"workflow has failedObjects={len(failed)}")
    last_agent = workflow.get("lastAgentRun") or {}
    if isinstance(last_agent, Mapping):
        infra = int(last_agent.get("infrastructureFailures") or 0)
        job_count = int(last_agent.get("jobCount") or 0)
        started = int(last_agent.get("startedCount") or 0)
        finished = int(last_agent.get("finishedCount") or 0)
        if infra:
            blockers.append(f"Cursor SDK infrastructure failures={infra}")
        if job_count and started <= 0:
            blockers.append("agent jobs planned but no worker started")
        if job_count and finished < job_count:
            blockers.append(f"agent jobs unfinished: {finished}/{job_count}")
    audit = evidence.get("managedBatchAudit") or {}
    if isinstance(audit, Mapping) and int(audit.get("failedLaneCount") or 0):
        blockers.append(f"managed batch failed lanes={audit.get('failedLaneCount')}")
    env_ready = evidence.get("envReady") if evidence.get("envReadyReportExists") else evidence.get("managedEnvReady")
    if env_ready is not True and not env.get("CURSOR_API_KEY"):
        blockers.append("CURSOR_API_KEY missing; real managed Cursor SDK trial cannot run")
    if env_ready is False:
        blockers.append("env ready evidence failed")
    if int(scope.get("targetCount") or 0) <= 5:
        warnings.append("trial target count is small; quality trend and throughput variance are not statistically stable")
    if workflow.get("workflowStateExists") and not evidence.get("tokenLedgerExists"):
        warnings.append("TokenLedger evidence missing; scale cost projection is blocked until author stage completes")
    if not evidence.get("managedBatchAuditExists"):
        warnings.append("managed_batch_audit.json missing; lane-level source convergence not persisted")
    return sorted(set(blockers)), sorted(set(warnings))


def _terminal_cause(
    *,
    workflow: Mapping[str, Any],
    evidence: Mapping[str, Any],
    blockers: Sequence[str],
    env: Mapping[str, str],
) -> dict[str, Any]:
    env_ready = evidence.get("envReady") if evidence.get("envReadyReportExists") else evidence.get("managedEnvReady")
    if env_ready is not True and not env.get("CURSOR_API_KEY"):
        return {
            "category": "environment_blocker",
            "stage": "env_ready",
            "reason": "CURSOR_API_KEY missing; managed Cursor SDK authoring cannot start",
            "retryClass": "operator_action_required",
        }
    last_agent = workflow.get("lastAgentRun") or {}
    if isinstance(last_agent, Mapping) and int(last_agent.get("infrastructureFailures") or 0):
        return {
            "category": "cursor_sdk_infra_failure",
            "stage": str(last_agent.get("stage") or "managed_agent"),
            "reason": f"infrastructureFailures={last_agent.get('infrastructureFailures')}",
            "retryClass": "infra_retry_then_manual",
        }
    audit = evidence.get("managedBatchAudit") or {}
    if isinstance(audit, Mapping) and int(audit.get("failedLaneCount") or 0):
        return {
            "category": "source_sufficiency_blocker",
            "stage": "content_plan",
            "reason": f"failedLaneCount={audit.get('failedLaneCount')}",
            "retryClass": "source_ready_or_target_replacement",
        }
    state = workflow.get("workflowState") or {}
    if isinstance(state, Mapping):
        failed = state.get("failedObjects") or []
        next_action = str(state.get("nextAction") or "")
        joined_failed = "\n".join(str(item) for item in failed) if isinstance(failed, list) else str(failed)
        if "source_unavailable" in joined_failed or "source-unavailable" in next_action:
            return {
                "category": "source_sufficiency_blocker",
                "stage": "content_plan",
                "reason": next_action or "content plan has source_unavailable failed objects",
                "retryClass": "source_ready_or_target_replacement",
            }
    if workflow.get("batchRootExists") and not workflow.get("workflowStateExists"):
        return {
            "category": "workflow_state_missing",
            "stage": "workflow_bootstrap",
            "reason": "batch directory exists but task_workflow_state.json is missing",
            "retryClass": "rerun_workflow_from_clean_batch",
        }
    if not workflow.get("batchRootExists"):
        return {
            "category": "not_started",
            "stage": "batch_create",
            "reason": "no batch runtime exists",
            "retryClass": "run_workflow",
        }
    if isinstance(state, Mapping) and state.get("waitingCheckpoint"):
        return {
            "category": "checkpoint_waiting",
            "stage": str(state.get("waitingCheckpoint") or ""),
            "reason": str(state.get("nextAction") or "workflow waits at checkpoint"),
            "retryClass": "checkpoint_specific_repair",
        }
    if blockers:
        return {
            "category": "gate_blocked",
            "stage": "trial_gate",
            "reason": str(blockers[0]),
            "retryClass": "fix_blocker_then_repeat",
        }
    return {
        "category": "no_blocking_terminal_cause",
        "stage": str((state or {}).get("status") or "unknown"),
        "reason": "no trial-review blocker found",
        "retryClass": "advance_scale_gate",
    }


def _efficiency_assessment(scope: Mapping[str, Any], workflow: Mapping[str, Any]) -> dict[str, Any]:
    config = _managed_runtime_config()
    state = workflow.get("workflowState") or {}
    last_agent = workflow.get("lastAgentRun") or {}
    history = workflow.get("agentRunHistory") if isinstance(workflow.get("agentRunHistory"), list) else []
    def _run_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
        scheduler = row.get("scheduler") if isinstance(row.get("scheduler"), Mapping) else {}
        return (
            str(row.get("stage") or ""),
            str((scheduler or {}).get("startedAt") or ""),
            str(row.get("finishedAt") or (scheduler or {}).get("finishedAt") or ""),
            str(row.get("plannedJobCount") or row.get("jobCount") or ""),
        )

    agent_runs: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in history:
        if not isinstance(row, Mapping):
            continue
        key = _run_key(row)
        if key in seen:
            continue
        seen.add(key)
        agent_runs.append(row)
    if isinstance(last_agent, Mapping) and last_agent:
        key = _run_key(last_agent)
        if key not in seen:
            agent_runs.append(last_agent)

    def _run_prompt_count(row: Mapping[str, Any]) -> int:
        scheduler = row.get("scheduler") if isinstance(row.get("scheduler"), Mapping) else {}
        return int((scheduler or {}).get("promptCount") or row.get("plannedJobCount") or row.get("jobCount") or 0)

    primary_run = max(agent_runs, key=_run_prompt_count, default={})
    scheduler = primary_run.get("scheduler") if isinstance(primary_run, Mapping) else {}
    if not isinstance(scheduler, Mapping):
        scheduler = {}
    author_jobs = int(((scope.get("agentCallPlan") or {}).get("creativeAuthorJobs") or 0))
    target_count = int(scope.get("targetCount") or 0)
    configured_local_max = int(config.get("localCursorMaxWorkers") or 1)
    prompt_count = int(scheduler.get("promptCount") or 0)
    effective_workers = int(scheduler.get("effectiveWorkerCount") or configured_local_max or 1)
    scheduler_local_max = int(scheduler.get("localCursorMaxWorkers") or configured_local_max or 1)
    observed_local_max = max(configured_local_max, scheduler_local_max, effective_workers)
    local_max = observed_local_max if prompt_count <= 1 else max(scheduler_local_max, effective_workers)
    requested_workers = int(scheduler.get("requestedMaxWorkers") or local_max)
    issues: list[str] = []
    if observed_local_max <= 1:
        issues.append("local managed worker cap is 1, so startup-heavy agent jobs cannot parallelize effectively")
    if prompt_count >= requested_workers and requested_workers > effective_workers:
        issues.append(
            f"requested max-workers={requested_workers} but effective local Cursor workers={effective_workers}"
        )
    if author_jobs and author_jobs <= 20:
        issues.append("small batches pay bridge/subprocess startup overhead per job before throughput benefits appear")
    if not workflow.get("workflowStateExists"):
        issues.append("current evidence stops before timing/token ledgers, so real content latency is not measurable")
    if target_count and author_jobs:
        estimated_min_waves = (author_jobs + max(local_max, 1) - 1) // max(local_max, 1)
    else:
        estimated_min_waves = 0
    recommendations = [
        "keep download/homepage/content planning deterministic and use Cursor only for creative authoring and hard repairs",
        "for small validation, run until content_plan first, audit source sufficiency, then author only a sampled ref set",
        "for scale, prefer external Cursor SDK workers with reliable queue and cloud runtime instead of per-job local bridge launches",
        "batch by independent refs at the queue layer, but keep one content object as the write-isolation unit",
    ]
    return {
        "managedRuntime": config,
        "estimatedAuthorJobs": author_jobs,
        "estimatedLocalWaves": estimated_min_waves,
        "agentRunHistoryCount": len(agent_runs),
        "primaryAuthorRun": {
            key: primary_run.get(key)
            for key in ("stage", "jobCount", "plannedJobCount", "startedCount", "finishedCount", "infrastructureFailures")
        } if isinstance(primary_run, Mapping) else {},
        "batchScheduler": dict(scheduler),
        "measuredThroughput": (
            state.get("throughput") if isinstance(state.get("throughput"), Mapping) else {}
        ),
        "issues": issues,
        "recommendations": recommendations,
    }


def _trial_strategy(
    task_id: str,
    batch_id: str,
    *,
    terminal_cause: Mapping[str, Any],
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    category = str(terminal_cause.get("category") or "")
    clean_batch = f"{batch_id}_next"
    if category == "environment_blocker":
        mode = "deterministic_until_content_plan"
        commands = [
            "python3 quwoquan_data/scripts/cli.py env ready",
            (
                "python3 quwoquan_data/scripts/cli.py task run "
                f"--task '{task_id}' --batch {clean_batch} --reset-state --until content_plan"
            ),
            (
                "python3 quwoquan_data/scripts/cli.py task audit-batch "
                f"--task '{task_id}' --batch {clean_batch} --json --write"
            ),
            (
                "python3 quwoquan_data/scripts/cli.py task trial-review "
                f"--task '{task_id}' --batch {clean_batch} --compare {batch_id} --write"
            ),
        ]
    elif category == "source_sufficiency_blocker":
        mode = "source_ready_repair_or_replace"
        commands = [
            (
                "python3 quwoquan_data/scripts/cli.py data source-discover "
                f"--task '{task_id}' --batch {batch_id} --lane all --force"
            ),
            (
                "python3 quwoquan_data/scripts/cli.py task audit-batch "
                f"--task '{task_id}' --batch {batch_id} --json --write --strict"
            ),
        ]
    elif category == "cursor_sdk_infra_failure":
        mode = "managed_author_retry_after_infra_recovery"
        commands = [
            "python3 quwoquan_data/scripts/cli.py env ready",
            (
                "python3 quwoquan_data/scripts/cli.py task retry-stage "
                f"--task '{task_id}' --batch {batch_id} --stage {terminal_cause.get('stage')}"
            ),
            (
                "python3 quwoquan_data/scripts/cli.py task run "
                f"--task '{task_id}' --batch {batch_id} --managed --runtime local --release-only --max-workers 2"
            ),
        ]
    else:
        mode = "repeat_small_trial_then_scale_ladder"
        commands = [
            (
                "python3 quwoquan_data/scripts/cli.py task run "
                f"--task '{task_id}' --batch {clean_batch} --managed --runtime local --release-only --max-workers 2"
            ),
            (
                "python3 quwoquan_data/scripts/cli.py verify scale-readiness "
                f"--task '{task_id}' --batch {clean_batch} --daily-target 100 --mode trial --allow-missing-import"
            ),
        ]
    return {
        "mode": mode,
        "recommendedBatchId": clean_batch,
        "stopAfter": "content_plan" if mode == "deterministic_until_content_plan" else "publish",
        "commands": commands,
        "successCriteria": [
            "lanePassed homepage/article/image equals targetCount",
            "workflowState exists and terminal cause is not environment/workflow bootstrap",
            "TokenLedger appears after author stage",
            "release/import/smoke evidence appears before scale",
        ],
        "estimatedAuthorJobs": int(((scope.get("agentCallPlan") or {}).get("creativeAuthorJobs") or 0)),
    }


def _scale_ladder(
    *,
    scope: Mapping[str, Any],
    evidence: Mapping[str, Any],
    workflow: Mapping[str, Any],
    blockers: Sequence[str],
) -> dict[str, Any]:
    queue_backend = str(((scope.get("executionPolicy") or {}).get("queueBackend") or ""))
    state = workflow.get("workflowState") or {}
    status = str(state.get("status") or "")
    has_token = bool(evidence.get("tokenLedgerExists"))
    has_release = bool(evidence.get("releaseEvidenceExists"))
    has_import = bool(evidence.get("importEvidencePaths"))
    throughput = state.get("throughput") if isinstance(state.get("throughput"), Mapping) else {}
    try:
        objects_per_hour = float((throughput or {}).get("objectsPerHour") or 0)
    except (TypeError, ValueError):
        objects_per_hour = 0.0
    target_count = int(scope.get("targetCount") or 0)
    quotas = scope.get("quotas") if isinstance(scope.get("quotas"), Mapping) else {}
    article_per_target = int((quotas or {}).get("entityArticlesPerTarget") or 0)
    image_per_target = int((quotas or {}).get("imageWorksPerTarget") or 0)
    homepage_per_target = int((quotas or {}).get("entityHomepagesPerTarget") or 0)
    objects_per_entity = homepage_per_target + article_per_target + image_per_target
    target_objects_per_entity = max(homepage_per_target, 1) + 4 + 2
    base_requirements = list(blockers)
    entity_levels: list[dict[str, Any]] = []
    for entities, label in (
        (10, "ten_entity_trial"),
        (100, "hundred_entity_trial"),
        (1_000, "thousand_entity_trial"),
    ):
        required = list(base_requirements)
        if status != "succeeded":
            required.append(f"workflow status must be succeeded; got {status or 'missing'}")
        if target_count < entities:
            required.append(f"current trial targetCount {target_count} < required {entities}")
        if article_per_target != 4 or image_per_target != 2:
            required.append(
                "entity batch ladder requires entityArticlesPerTarget=4 and imageWorksPerTarget=2"
            )
        if entities >= 100 and queue_backend != "reliabletask":
            required.append("reliabletask queue backend required for hundred-level fanout")
        if entities >= 100 and not has_token:
            required.append("TokenLedger required before hundred-level trial")
        if entities >= 100 and not has_release:
            required.append("isolated release evidence required before hundred-level trial")
        if entities >= 1_000:
            required.extend([
                "fanout plan/run_matrix evidence required for thousand-level trial",
                "external Cursor SDK workers or reliable queue workers required beyond local bridge capacity",
            ])
        entity_levels.append({
            "label": label,
            "entityCount": entities,
            "articlesPerEntity": 4,
            "imageWorksPerEntity": 2,
            "expectedPublishableObjects": entities * target_objects_per_entity,
            "go": not required,
            "requiredBeforeGo": sorted(set(required)),
        })

    levels: list[dict[str, Any]] = []
    for target, label in (
        (100, "hundred_trial"),
        (1_000, "thousand_trial"),
        (10_000, "daily_10k"),
        (100_000, "daily_100k_challenge"),
    ):
        required = list(base_requirements)
        if status != "succeeded":
            required.append(f"workflow status must be succeeded; got {status or 'missing'}")
        if target >= 1_000 and queue_backend != "reliabletask":
            required.append("reliabletask queue backend required for thousand-level fanout")
        if target >= 1_000 and not has_token:
            required.append("TokenLedger required for cost/timeout projection")
        if target >= 10_000 and not has_release:
            required.append("isolated release evidence required")
        if target >= 10_000 and not has_import:
            required.append("service importer and consumer smoke evidence required")
        required_per_hour = target / 24
        if not throughput:
            required.append("measured throughput evidence required")
        elif objects_per_hour < required_per_hour:
            required.append(
                f"measured throughput {objects_per_hour:.4f} objects/hour < required {required_per_hour:.4f}"
            )
        if target >= 100_000:
            required.extend([
                "external Cursor SDK cloud/self-hosted workers required; local bridge cannot be the throughput path",
                "provider/source capacity reservation and rights pool must be proven by vertical",
                "ops dashboards and error-budget automation required",
            ])
        levels.append({
            "label": label,
            "dailyTargetObjects": target,
            "requiredThroughputPerHour": round(required_per_hour, 4),
            "measuredThroughputPerHour": round(objects_per_hour, 4),
            "go": not required,
            "requiredBeforeGo": sorted(set(required)),
        })
    return {
        "currentObjectCount": int(((scope.get("estimatedObjects") or {}).get("totalPublishableObjects") or 0)),
        "currentEntityCount": target_count,
        "objectsPerEntity": objects_per_entity,
        "targetObjectsPerEntity": target_objects_per_entity,
        "queueBackend": queue_backend,
        "entityBatchLevels": entity_levels,
        "levels": levels,
    }


def _decision(blockers: Sequence[str], convergence: Mapping[str, Any]) -> dict[str, Any]:
    if blockers:
        return {
            "canScale": False,
            "nextGate": "trial_fix",
            "reason": "blocking trial evidence remains",
            "requiredBeforeNextRun": list(blockers),
        }
    if convergence.get("trend") not in {"improving", "flat", "insufficient_history"}:
        return {
            "canScale": False,
            "nextGate": "repeat_small_trial",
            "reason": f"convergence trend is {convergence.get('trend')}",
            "requiredBeforeNextRun": ["repeat small trial and compare scores"],
        }
    return {
        "canScale": True,
        "nextGate": "hundred_level_trial",
        "reason": "no blocking trial evidence found",
        "requiredBeforeNextRun": [],
    }


def parse_run_ref(value: str, *, default_task_id: str | None = None) -> tuple[str, str]:
    text = str(value or "").strip()
    if "::" in text:
        task_id, batch_id = text.split("::", 1)
        return task_id.strip(), batch_id.strip()
    if not default_task_id:
        raise ValueError("run ref without TASK::BATCH requires default_task_id")
    return default_task_id, text


def build_trial_review(
    task_id: str,
    batch_id: str,
    *,
    compare_runs: Sequence[tuple[str, str]] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    spec = store.load_spec(task_id)
    scope = _trial_scope(spec)
    workflow = _workflow_snapshot(task_id, batch_id)
    evidence = _artifact_evidence(task_id, batch_id)
    current_score = _failure_score(workflow, evidence)
    comparisons = _compare_scores(compare_runs or [])
    convergence = _convergence(current_score, workflow, comparisons)
    blockers, warnings = _blockers_and_warnings(
        scope=scope,
        workflow=workflow,
        evidence=evidence,
        env=env or os.environ,
    )
    efficiency = _efficiency_assessment(scope, workflow)
    terminal_cause = _terminal_cause(
        workflow=workflow,
        evidence=evidence,
        blockers=blockers,
        env=env or os.environ,
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "taskId": task_id,
        "batchId": batch_id,
        "scope": scope,
        "evidence": evidence,
        "workflow": workflow,
        "convergence": convergence,
        "qualityAndScaleGate": {
            "blockers": blockers,
            "warnings": warnings,
            "passed": not blockers,
        },
        "terminalCause": terminal_cause,
        "efficiency": efficiency,
        "nextTrialStrategy": _trial_strategy(
            task_id,
            batch_id,
            terminal_cause=terminal_cause,
            scope=scope,
        ),
        "scaleLadder": _scale_ladder(
            scope=scope,
            evidence=evidence,
            workflow=workflow,
            blockers=blockers,
        ),
        "decision": _decision(blockers, convergence),
    }


def write_trial_review(report: Mapping[str, Any]) -> Path:
    path = batch_shared_dir(str(report["taskId"]), str(report["batchId"])) / "trial_review.json"
    write_json(path, dict(report))
    return path

"""Managed trial review and convergence diagnostics.

This module turns a managed content trial into a repeatable readiness report.
It is deliberately evidence-first: missing runtime artifacts are reported as a
workflow/infra issue instead of being treated as content-quality feedback.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from _common.image_asset_strategy import (
    image_asset_strategy,
    image_asset_strategy_scale_issues,
)
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
from task.trial_review_scale import (
    decision as _decision,
    efficiency_assessment as _efficiency_assessment,
    scale_ladder as _scale_ladder,
    trial_strategy as _trial_strategy,
)


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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(max(0, numerator) / denominator, 4)


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
    workflow_policy = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), Mapping) else {}
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
            "allowPartialContent": bool(workflow_policy.get("allowPartialContent", True) is not False),
            "deliveryMode": str(workflow_policy.get("deliveryMode") or ""),
        },
    }


def _workflow_snapshot(task_id: str, batch_id: str) -> dict[str, Any]:
    shared = batch_shared_dir(task_id, batch_id)
    state = _load_json_if_exists(shared / "task_workflow_state.json")
    last_agent = state.get("lastAgentRun") or {}
    if not isinstance(last_agent, Mapping):
        last_agent = {}
    active_scheduler = state.get("activeAgentScheduler") or {}
    if not isinstance(active_scheduler, Mapping):
        active_scheduler = {}
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
        "activeAgentScheduler": {
            key: active_scheduler.get(key)
            for key in (
                "stage",
                "requestedMaxWorkers",
                "effectiveWorkerCount",
                "localCursorMaxWorkers",
                "runtime",
                "promptCount",
                "estimatedMinWaves",
                "laneLimits",
                "startedAt",
                "elapsedSeconds",
            )
        } if active_scheduler else {},
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


def _source_readiness_summary(
    auto_research: Mapping[str, Any],
    managed_audit: Mapping[str, Any],
) -> dict[str, Any]:
    availability = auto_research.get("sourceAvailability") if isinstance(auto_research, Mapping) else {}
    if not isinstance(availability, Mapping):
        availability = {}
    auto_ready = [str(item).strip() for item in availability.get("readyTargets") or [] if str(item).strip()]
    auto_ineligible = [
        item for item in availability.get("ineligibleTargets") or []
        if isinstance(item, Mapping)
    ]
    auto_unavailable = [
        item for item in auto_research.get("sourceUnavailable") or []
        if isinstance(item, Mapping)
    ] if isinstance(auto_research, Mapping) else []
    target_count = _safe_int(managed_audit.get("targetCount"))
    lane_passed_raw = managed_audit.get("lanePassed") if isinstance(managed_audit.get("lanePassed"), Mapping) else {}
    lane_passed = {lane: _safe_int((lane_passed_raw or {}).get(lane)) for lane in LANES}
    failed_lanes = [
        item for item in managed_audit.get("failedLanes") or []
        if isinstance(item, Mapping)
    ]
    failed_entities = sorted({
        str(item.get("entity") or "").strip()
        for item in failed_lanes
        if str(item.get("entity") or "").strip() and str(item.get("entity") or "").strip() != "__batch__"
    })
    failed_lane_count = _safe_int(managed_audit.get("failedLaneCount"))
    auto_signal = bool(auto_ready or auto_ineligible)
    if auto_signal:
        target_count = target_count or len(auto_ready) + len(auto_ineligible)
        lane_missing = {lane: 0 for lane in LANES}
        failed_entities = []
        for item in auto_ineligible:
            entity = str(item.get("entityId") or "").strip()
            if entity:
                failed_entities.append(entity)
            lanes = [str(lane) for lane in (item.get("lanes") or []) if str(lane).strip()]
            if not lanes:
                lanes = list(LANES)
            for lane in lanes:
                if lane in lane_missing:
                    lane_missing[lane] += 1
        lane_passed = {
            lane: max(0, target_count - int(lane_missing.get(lane) or 0))
            for lane in LANES
        }
        failed_lane_count = len(auto_ineligible)
        all_lane_ready = len(auto_ready)
    elif target_count and failed_entities:
        all_lane_ready = max(0, target_count - len(failed_entities))
    elif target_count and lane_passed:
        all_lane_ready = min(lane_passed.values())
    else:
        all_lane_ready = len(auto_ready)
    lane_coverage = {
        lane: {
            "passed": passed,
            "targetCount": target_count,
            "missing": max(0, target_count - passed) if target_count else 0,
            "ratio": _ratio(passed, target_count),
        }
        for lane, passed in lane_passed.items()
    }
    bottleneck_lane = ""
    if lane_coverage:
        bottleneck_lane = min(
            lane_coverage,
            key=lambda lane: (float(lane_coverage[lane]["ratio"]), int(lane_coverage[lane]["passed"])),
        )
    missing_parts = [
        f"{lane} {row['passed']}/{row['targetCount']}"
        for lane, row in lane_coverage.items()
        if int(row.get("missing") or 0) > 0
    ]
    if auto_signal and auto_ineligible:
        missing_parts.insert(0, f"source availability ready {len(auto_ready)}/{target_count}")
    status = "ready"
    next_action = "advance_to_author_or_release_gate"
    if failed_lane_count or missing_parts:
        status = "blocked"
        next_action = "source_ready_target_replacement_or_upstream_source_expansion"
    return {
        "status": status,
        "targetCount": target_count,
        "allLaneReadyTargetCount": all_lane_ready,
        "allLaneReadyRatio": _ratio(all_lane_ready, target_count),
        "laneCoverage": lane_coverage,
        "bottleneckLane": bottleneck_lane,
        "failedLaneCount": failed_lane_count,
        "failedEntityCount": len(failed_entities),
        "failedEntitySample": failed_entities[:20],
        "missingSummary": ", ".join(missing_parts),
        "nextAction": next_action,
        "autoResearch": {
            "readyTargets": len(auto_ready),
            "ineligibleTargets": len(auto_ineligible),
            "sourceUnavailable": len(auto_unavailable),
            "readyTargetSample": auto_ready[:20],
            "ineligibleTargetSample": [
                str(item.get("entityId") or "").strip()
                for item in auto_ineligible[:20]
                if str(item.get("entityId") or "").strip()
            ],
        },
    }


def _artifact_evidence(task_id: str, batch_id: str, spec: Mapping[str, Any] | None = None) -> dict[str, Any]:
    shared = batch_shared_dir(task_id, batch_id)
    spec = spec if isinstance(spec, Mapping) else store.load_spec(task_id)
    baseline_report = _load_json_if_exists(task_shared_dir(task_id) / "baseline_report.json")
    auto_research = _load_json_if_exists(shared / "auto_research_plan.json")
    managed_env = _load_json_if_exists(shared / "managed_env_ready.json")
    env_ready = _load_json_if_exists(shared / "env_ready_report.json")
    token_ledger = _load_json_if_exists(shared / "token_ledger.json")
    managed_audit = _load_json_if_exists(shared / "managed_batch_audit.json")
    content_plan_diag = _load_json_if_exists(shared / "content_plan_source_diagnostics.json")
    open_license_proof = _load_json_if_exists(shared / "open_license_scale_proof.json")
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
        "sourceReadiness": _source_readiness_summary(auto_research, managed_audit),
        "imageAssetStrategy": {
            "strategy": image_asset_strategy(spec),
            "scaleIssues": image_asset_strategy_scale_issues(spec),
            "batchOpenLicenseProofExists": bool(open_license_proof),
            "batchOpenLicenseProof": {
                "passed": bool(open_license_proof.get("passed")),
                "desiredPassed": bool(open_license_proof.get("desiredPassed")),
                "preScreenedEntityCount": int(
                    ((open_license_proof.get("proof") or {}).get("preScreenedEntityCount") or 0)
                ),
                "scoredEntityCount": int(
                    ((open_license_proof.get("proof") or {}).get("scoredEntityCount") or 0)
                ),
                "requiredEntityCount": int(open_license_proof.get("requiredEntityCount") or 0),
                "publishableImageAssets": int(
                    ((open_license_proof.get("proof") or {}).get("publishableImageAssets") or 0)
                ),
                "requiredPublishableImageAssets": int(
                    open_license_proof.get("requiredPublishableImageAssets") or 0
                ),
                "desiredPublishableImageAssets": int(
                    open_license_proof.get("desiredPublishableImageAssets") or 0
                ),
                "minimumPublishableImageAssets": int(
                    open_license_proof.get("minimumPublishableImageAssets") or 0
                ),
                "averageImageCountScore": float(open_license_proof.get("averageImageCountScore") or 0.0),
                "averageCompositeScore": float(open_license_proof.get("averageCompositeScore") or 0.0),
                "failedEntityCount": int(open_license_proof.get("failedEntityCount") or 0),
                "belowDesiredEntityCount": int(open_license_proof.get("belowDesiredEntityCount") or 0),
            } if open_license_proof else {},
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
    execution_policy = scope.get("executionPolicy") if isinstance(scope.get("executionPolicy"), Mapping) else {}
    allow_partial = bool(execution_policy.get("allowPartialContent", True) is not False)
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
    active_scheduler = workflow.get("activeAgentScheduler") or {}
    if isinstance(active_scheduler, Mapping) and active_scheduler:
        warnings.append(
            "activeAgentScheduler evidence exists; previous managed run did not finalize cleanly"
        )
        prompt_count = int(active_scheduler.get("promptCount") or 0)
        effective_workers = int(active_scheduler.get("effectiveWorkerCount") or 0)
        if prompt_count and effective_workers:
            warnings.append(
                f"managed checkpoint had {prompt_count} prompts with {effective_workers} effective worker(s)"
            )
    audit = evidence.get("managedBatchAudit") or {}
    if isinstance(audit, Mapping) and int(audit.get("failedLaneCount") or 0):
        message = (
            f"managed batch partial failed lanes={audit.get('failedLaneCount')}; "
            "successful objects may continue to publish"
        )
        if allow_partial:
            warnings.append(message)
        else:
            blockers.append(f"managed batch failed lanes={audit.get('failedLaneCount')}")
    readiness = evidence.get("sourceReadiness") or {}
    if isinstance(readiness, Mapping) and readiness.get("status") == "blocked":
        target_count = int(readiness.get("targetCount") or 0)
        ready_count = int(readiness.get("allLaneReadyTargetCount") or 0)
        missing = str(readiness.get("missingSummary") or "").strip()
        if allow_partial:
            if target_count:
                warnings.append(f"partial source-ready targets {ready_count}/{target_count}")
            if missing:
                warnings.append(f"partial source lane coverage below target: {missing}")
        else:
            if target_count:
                blockers.append(f"source-ready targets {ready_count}/{target_count}")
            if missing:
                blockers.append(f"source lane coverage below target: {missing}")
    image_strategy = evidence.get("imageAssetStrategy") or {}
    if isinstance(image_strategy, Mapping):
        batch_proof = image_strategy.get("batchOpenLicenseProof")
        if isinstance(batch_proof, Mapping) and batch_proof and not bool(batch_proof.get("passed")):
            message = (
                "batch open-license proof failed: "
                f"entities {batch_proof.get('preScreenedEntityCount')}/{batch_proof.get('requiredEntityCount')}, "
                f"assets {batch_proof.get('publishableImageAssets')}/{batch_proof.get('requiredPublishableImageAssets')}"
            )
            if allow_partial:
                warnings.append(message)
            else:
                blockers.append(message)
        image_scale_issues = [str(item) for item in (image_strategy.get("scaleIssues") or []) if str(item).strip()]
        if allow_partial:
            warnings.extend(image_scale_issues)
        else:
            blockers.extend(image_scale_issues)
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
    scope: Mapping[str, Any],
    workflow: Mapping[str, Any],
    evidence: Mapping[str, Any],
    blockers: Sequence[str],
    env: Mapping[str, str],
) -> dict[str, Any]:
    execution_policy = scope.get("executionPolicy") if isinstance(scope.get("executionPolicy"), Mapping) else {}
    allow_partial = bool(execution_policy.get("allowPartialContent", True) is not False)
    env_ready = evidence.get("envReady") if evidence.get("envReadyReportExists") else evidence.get("managedEnvReady")
    last_agent = workflow.get("lastAgentRun") or {}
    if isinstance(last_agent, Mapping) and int(last_agent.get("infrastructureFailures") or 0):
        return {
            "category": "cursor_sdk_infra_failure",
            "stage": str(last_agent.get("stage") or "managed_agent"),
            "reason": f"infrastructureFailures={last_agent.get('infrastructureFailures')}",
            "retryClass": "infra_retry_then_manual",
        }
    state = workflow.get("workflowState") or {}
    if isinstance(state, Mapping):
        failed = state.get("failedObjects") or []
        next_action = str(state.get("nextAction") or "")
        joined_failed = "\n".join(str(item) for item in failed) if isinstance(failed, list) else str(failed)
        if "interrupted" in joined_failed.casefold() or "interrupted" in next_action.casefold():
            return {
                "category": "workflow_interrupted",
                "stage": str(state.get("waitingCheckpoint") or "workflow"),
                "reason": next_action or "workflow interrupted before checkpoint completion",
                "retryClass": "rerun_from_clean_batch_or_same_checkpoint",
            }
    image_strategy = evidence.get("imageAssetStrategy") or {}
    if isinstance(image_strategy, Mapping):
        batch_proof = image_strategy.get("batchOpenLicenseProof")
        if isinstance(batch_proof, Mapping) and batch_proof and not bool(batch_proof.get("passed")) and not allow_partial:
            return {
                "category": "image_asset_strategy_blocker",
                "stage": "task_preflight",
                "reason": (
                    "batch open-license proof failed: "
                    f"entities {batch_proof.get('preScreenedEntityCount')}/{batch_proof.get('requiredEntityCount')}, "
                    f"assets {batch_proof.get('publishableImageAssets')}/{batch_proof.get('requiredPublishableImageAssets')}"
                ),
                "retryClass": "configure_asset_provider_or_prescreened_pool",
            }
        scale_issues = [str(item) for item in (image_strategy.get("scaleIssues") or []) if str(item).strip()]
        if scale_issues and not allow_partial:
            return {
                "category": "image_asset_strategy_blocker",
                "stage": "task_preflight",
                "reason": scale_issues[0],
                "retryClass": "configure_asset_provider_or_prescreened_pool",
            }
    readiness = evidence.get("sourceReadiness") or {}
    if isinstance(readiness, Mapping) and readiness.get("status") == "blocked" and not allow_partial:
        reason = str(readiness.get("missingSummary") or "").strip()
        if not reason:
            reason = f"source-ready targets {readiness.get('allLaneReadyTargetCount')}/{readiness.get('targetCount')}"
        return {
            "category": "source_sufficiency_blocker",
            "stage": "download_plan",
            "reason": reason,
            "retryClass": "source_ready_or_target_replacement",
        }
    audit = evidence.get("managedBatchAudit") or {}
    if isinstance(audit, Mapping) and int(audit.get("failedLaneCount") or 0) and not allow_partial:
        return {
            "category": "source_sufficiency_blocker",
            "stage": "download_plan",
            "reason": f"failedLaneCount={audit.get('failedLaneCount')}",
            "retryClass": "source_ready_or_target_replacement",
        }
    if env_ready is not True and not env.get("CURSOR_API_KEY"):
        return {
            "category": "environment_blocker",
            "stage": "env_ready",
            "reason": "CURSOR_API_KEY missing; managed Cursor SDK authoring cannot start",
            "retryClass": "operator_action_required",
        }
    if isinstance(state, Mapping):
        failed = state.get("failedObjects") or []
        next_action = str(state.get("nextAction") or "")
        joined_failed = "\n".join(str(item) for item in failed) if isinstance(failed, list) else str(failed)
        if "source_unavailable" in joined_failed or "source-unavailable" in next_action:
            if allow_partial:
                return {
                    "category": "partial_delivery_manual_required",
                    "stage": str(state.get("waitingCheckpoint") or "content_plan"),
                    "reason": next_action or "content plan has source_unavailable failed objects",
                    "retryClass": "resume_successful_objects_and_abandon_failed_lanes",
                }
            return {
                "category": "source_sufficiency_blocker",
                "stage": "download_plan",
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
        readiness = evidence.get("sourceReadiness") or {}
        if allow_partial and isinstance(readiness, Mapping) and readiness.get("status") == "blocked":
            return {
                "category": "partial_delivery_checkpoint_waiting",
                "stage": str(state.get("waitingCheckpoint") or ""),
                "reason": (
                    str(readiness.get("missingSummary") or "").strip()
                    or str(state.get("nextAction") or "workflow waits while partial lanes can continue")
                ),
                "retryClass": "resume_successful_objects_and_abandon_failed_lanes",
            }
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
    env_map = env if env is not None else os.environ
    scope = _trial_scope(spec)
    workflow = _workflow_snapshot(task_id, batch_id)
    evidence = _artifact_evidence(task_id, batch_id, spec)
    current_score = _failure_score(workflow, evidence)
    comparisons = _compare_scores(compare_runs or [])
    convergence = _convergence(current_score, workflow, comparisons)
    blockers, warnings = _blockers_and_warnings(
        scope=scope,
        workflow=workflow,
        evidence=evidence,
        env=env_map,
    )
    efficiency = _efficiency_assessment(scope, workflow)
    terminal_cause = _terminal_cause(
        scope=scope,
        workflow=workflow,
        evidence=evidence,
        blockers=blockers,
        env=env_map,
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

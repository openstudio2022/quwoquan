"""Scale and efficiency assessment helpers for managed trial reviews."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def managed_runtime_config() -> dict[str, Any]:
    from task import run as run_mod

    raw_local_cap = getattr(run_mod, "MANAGED_LOCAL_CURSOR_MAX_WORKERS", None)
    local_cursor_max_workers = None if raw_local_cap in (None, "") else int(raw_local_cap)
    return {
        "localCursorMaxWorkers": local_cursor_max_workers,
        "agentTimeoutSeconds": int(getattr(run_mod, "MANAGED_AGENT_TIMEOUT_SECONDS", 240)),
        "futureGraceSeconds": int(getattr(run_mod, "MANAGED_AGENT_FUTURE_GRACE_SECONDS", 15)),
        "laneLimits": dict(getattr(run_mod, "MANAGED_LANE_LIMITS", {})),
        "runnerMode": "isolated_subprocess_per_agent_job",
        "knownCostShape": (
            "local managed starts one killable subprocess per prompt and launches a local Cursor bridge inside it"
        ),
    }


def efficiency_assessment(scope: Mapping[str, Any], workflow: Mapping[str, Any]) -> dict[str, Any]:
    config = managed_runtime_config()
    state = workflow.get("workflowState") or {}
    last_agent = workflow.get("lastAgentRun") or {}
    active_scheduler = workflow.get("activeAgentScheduler") or {}
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
    if isinstance(active_scheduler, Mapping) and active_scheduler:
        active_record = {
            "stage": active_scheduler.get("stage"),
            "plannedJobCount": active_scheduler.get("promptCount"),
            "jobCount": 0,
            "startedCount": 0,
            "finishedCount": 0,
            "infrastructureFailures": 0,
            "scheduler": dict(active_scheduler),
        }
        key = _run_key(active_record)
        if key not in seen:
            agent_runs.append(active_record)

    def _run_prompt_count(row: Mapping[str, Any]) -> int:
        scheduler = row.get("scheduler") if isinstance(row.get("scheduler"), Mapping) else {}
        return int((scheduler or {}).get("promptCount") or row.get("plannedJobCount") or row.get("jobCount") or 0)

    primary_run = max(agent_runs, key=_run_prompt_count, default={})
    scheduler = primary_run.get("scheduler") if isinstance(primary_run, Mapping) else {}
    if not isinstance(scheduler, Mapping):
        scheduler = {}
    author_jobs = int(((scope.get("agentCallPlan") or {}).get("creativeAuthorJobs") or 0))
    target_count = int(scope.get("targetCount") or 0)

    def _positive_int(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return parsed if parsed > 0 else 0

    configured_local_max = _positive_int(config.get("localCursorMaxWorkers"))
    prompt_count = int(scheduler.get("promptCount") or 0)
    requested_workers = _positive_int(scheduler.get("requestedMaxWorkers"))
    effective_workers = _positive_int(scheduler.get("effectiveWorkerCount")) or requested_workers or configured_local_max or 1
    scheduler_local_max = _positive_int(scheduler.get("localCursorMaxWorkers")) or configured_local_max
    observed_local_max = max(configured_local_max, scheduler_local_max, effective_workers, requested_workers)
    local_max = observed_local_max or 1
    if prompt_count > 1:
        local_max = max(scheduler_local_max, effective_workers, requested_workers, 1)
    requested_workers = requested_workers or local_max
    issues: list[str] = []
    if configured_local_max == 1 or (scheduler_local_max == 1 and requested_workers <= 1 and effective_workers <= 1):
        issues.append("local managed worker cap is 1, so startup-heavy agent jobs cannot parallelize effectively")
    if prompt_count >= requested_workers and requested_workers > effective_workers:
        issues.append(
            f"requested max-workers={requested_workers} but effective local Cursor workers={effective_workers}"
        )
    if author_jobs and author_jobs <= 20:
        issues.append("small batches pay bridge/subprocess startup overhead per job before throughput benefits appear")
    if prompt_count >= 50 and str(primary_run.get("stage") or "") != "produce_author":
        issues.append(
            f"managed checkpoint {primary_run.get('stage') or 'unknown'} has {prompt_count} prompts; "
            "source discovery/repair must be batched or deterministic before hundred-level trials"
        )
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


def trial_strategy(
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
    elif category == "image_asset_strategy_blocker":
        mode = "asset_strategy_provider_or_prescreened_pool_required"
        commands = [
            f"python3 quwoquan_data/scripts/cli.py task lint '{task_id}'",
            (
                "python3 quwoquan_data/scripts/cli.py task run "
                f"--task '{task_id}' --batch {clean_batch} --managed --runtime local "
                "--release-only --max-workers 2"
            ),
            (
                "python3 quwoquan_data/scripts/cli.py task trial-review "
                f"--task '{task_id}' --batch {clean_batch} --compare {batch_id} --write"
            ),
        ]
    elif category == "source_sufficiency_blocker":
        mode = "source_ready_repair_or_replace"
        limit = int(scope.get("targetCount") or 100)
        replacement_task_name = f"{batch_id}_source_ready_retry"
        commands = [
            (
                "python3 quwoquan_data/scripts/cli.py task audit-batch "
                f"--task '{task_id}' --batch {batch_id} --json --write --strict"
            ),
            (
                "python3 quwoquan_data/scripts/cli.py task select-targets "
                f"--limit {limit} --mandatory '' --exclude-from-run '{task_id}::{batch_id}' "
                f"--name '{replacement_task_name}' --write"
            ),
        ]
    elif category in {"partial_delivery_checkpoint_waiting", "partial_delivery_manual_required"}:
        mode = "resume_partial_delivery_from_checkpoint"
        commands = [
            (
                "python3 quwoquan_data/scripts/cli.py task audit-batch "
                f"--task '{task_id}' --batch {batch_id} --json --write"
            ),
            (
                "python3 quwoquan_data/scripts/cli.py task run "
                f"--task '{task_id}' --batch {batch_id} --managed --runtime local "
                "--release-only --max-workers 2"
            ),
            (
                "python3 quwoquan_data/scripts/cli.py verify scale-readiness "
                f"--task '{task_id}' --batch {batch_id} --daily-target 100 --mode trial --allow-missing-import"
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
    elif category == "workflow_interrupted":
        mode = "rerun_interrupted_checkpoint_from_clean_batch"
        commands = [
            (
                "python3 quwoquan_data/scripts/cli.py task audit-batch "
                f"--task '{task_id}' --batch {batch_id} --json --write"
            ),
            (
                "python3 quwoquan_data/scripts/cli.py task run "
                f"--task '{task_id}' --batch {clean_batch} --reset-state --until {terminal_cause.get('stage') or 'download_plan'}"
            ),
            (
                "python3 quwoquan_data/scripts/cli.py task trial-review "
                f"--task '{task_id}' --batch {clean_batch} --compare {batch_id} --write"
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
    stop_after = "publish"
    if mode == "asset_strategy_provider_or_prescreened_pool_required":
        stop_after = "task_preflight"
    elif mode == "deterministic_until_content_plan":
        stop_after = "content_plan"
    elif mode == "rerun_interrupted_checkpoint_from_clean_batch":
        stop_after = str(terminal_cause.get("stage") or "download_plan")
    return {
        "mode": mode,
        "recommendedBatchId": clean_batch,
        "stopAfter": stop_after,
        "commands": commands,
        "successCriteria": [
            "imageAssetStrategy.scaleIssues is empty before managed run",
            "lanePassed homepage/article/image is recorded as fulfillment evidence, not a release quota blocker",
            "workflowState exists and terminal cause is not environment/workflow bootstrap",
            "TokenLedger appears after author stage",
            "release/import/smoke evidence appears before scale",
        ],
        "estimatedAuthorJobs": int(((scope.get("agentCallPlan") or {}).get("creativeAuthorJobs") or 0)),
    }


def scale_ladder(
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


def decision(blockers: Sequence[str], convergence: Mapping[str, Any]) -> dict[str, Any]:
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

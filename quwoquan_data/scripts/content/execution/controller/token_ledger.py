"""Token-ledger assembly for one content execution."""
from __future__ import annotations

from typing import Any, Mapping

from core.data_issue import (
    DataIssueCode,
    DataIssueError,
    DataIssueStage,
    data_issue,
)
from core.io import read_json
from core.paths import execution_root
from core.control_types import ContentType, ExecutionStage
from core.runtime_policy import active_runtime_policy
from content.execution.context import ExecutionContext
from content.execution.contracts import ExecutionStateTransition


_CONTENT_OBJECT_AGENT_STAGES = {
    ExecutionStage.BUILD_HOMEPAGE,
    ExecutionStage.POST_AUTHOR,
    ExecutionStage.POST_REVIEW,
}


def required_creator_profile_id(
    payload: Mapping[str, Any],
    *,
    ref: str,
) -> str:
    creator_profile_id = str(payload.get("creatorProfileId") or "").strip()
    if creator_profile_id:
        return creator_profile_id
    raise DataIssueError(
        (
            data_issue(
                DataIssueCode.CONTRACT_INVALID,
                stage=DataIssueStage.CONTENT_PLAN,
                message="creatorProfileId is required before usage is recorded",
                ref=ref,
            ),
        )
    )


def _dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    ordered: list[str] = []
    for entry in entries:
        job_id = str(entry.get("jobId") or "")
        if not job_id:
            continue
        if job_id not in latest:
            ordered.append(job_id)
        latest[job_id] = dict(entry)
    return [latest[job_id] for job_id in ordered]


def _queue_entries(execution_id: str) -> list[dict[str, Any]]:
    queue_dir = execution_root(execution_id) / "_shared" / "object_queue"
    entries: list[dict[str, Any]] = []
    if not queue_dir.is_dir():
        return entries
    for path in sorted(queue_dir.glob("*.json")):
        job = read_json(path)
        for entry in (job.get("tokenLedger") or []) if isinstance(job, Mapping) else []:
            if isinstance(entry, Mapping):
                entries.append(dict(entry))
    return _dedupe_entries(entries)


def _managed_entries(
    ctx: ExecutionContext,
    state: ExecutionStateTransition,
    *,
    default_budget: int,
) -> list[dict[str, Any]]:
    from content.post import object_index as content_object
    from content.post.article.draft_io import read_writing_pack
    from content.execution.production_contracts import build_token_ledger_entry

    from content.execution.agent.history import state_managed_agent_runs

    entries: list[dict[str, Any]] = []
    for run in state_managed_agent_runs(state):
        stage = run.stage
        for job_outcome in run.outcomes:
            outcome = job_outcome.outcome
            usage_mode = outcome.usage_measurement_mode
            used_tokens = outcome.used_tokens
            cost_usd = outcome.cost_usd if outcome.cost_known else None
            if not outcome.started and not usage_mode and used_tokens <= 0:
                continue
            ref = job_outcome.ref
            object_scope = bool(ref) and stage in _CONTENT_OBJECT_AGENT_STAGES
            if object_scope and stage == ExecutionStage.BUILD_HOMEPAGE:
                content_type = ContentType.HOMEPAGE.value
                entity_payload_path = execution_root(ctx.execution_id) / ref / "_entity.json"
                creator_payload = (
                    read_json(entity_payload_path)
                    if ref and entity_payload_path.is_file()
                    else {}
                )
            elif object_scope:
                coords = content_object.content_coords(ctx.execution_id, ref) if ref else {}
                creator_payload = read_writing_pack(ctx.execution_id, ref) if ref else {}
                content_type = str(coords.get("contentType") or stage.value).strip()
            else:
                creator_payload = {}
                content_type = ctx.spec.content.carriers[0].value
            if not content_type:
                raise DataIssueError(
                    (
                        data_issue(
                            DataIssueCode.CONTRACT_INVALID,
                            stage=DataIssueStage.CONTENT_PLAN,
                            message="contentType is required before usage is recorded",
                            ref=ref or outcome.run_id or "managed-agent-run",
                        ),
                    )
                )
            creator_profile_id = (
                required_creator_profile_id(
                    creator_payload,
                    ref=ref or outcome.run_id or "managed-agent-run",
                )
                if object_scope
                else ""
            )
            timing = dict(job_outcome.timing)
            job_id = outcome.run_id or (
                f"managed:{stage.value}:{ref or job_outcome.job_index}:"
                f"{timing.get('finishedAt') or run.finished_at}"
            )
            entries.append(
                build_token_ledger_entry(
                    execution_id=ctx.execution_id,
                    job_id=job_id,
                    run_id=outcome.run_id or job_id,
                    creator_profile_id=creator_profile_id,
                    content_type=content_type,
                    budget_tokens=default_budget,
                    used_tokens=used_tokens,
                    input_tokens=outcome.input_tokens,
                    output_tokens=outcome.output_tokens,
                    cache_read_tokens=outcome.cache_read_tokens,
                    cache_write_tokens=outcome.cache_write_tokens,
                    cost_usd=cost_usd,
                    cost_budget_usd=active_runtime_policy().default_object_cost_budget_usd,
                    cost_source=outcome.cost_source,
                    cost_issue=outcome.cost_issue,
                    pricing_revision=outcome.pricing_revision,
                    retry_cost_usd=outcome.retry_cost_usd,
                    scope="content_object" if object_scope else "execution_stage",
                    execution_stage=stage.value,
                    content_object_ref=ref if object_scope else "",
                    passed=outcome.succeeded,
                    provider=outcome.provider.value,
                    model=outcome.resolved_model_id or ctx.model,
                )
            )
    return _dedupe_entries(entries)


def build_token_ledger_payload(
    ctx: ExecutionContext,
    state: ExecutionStateTransition,
    *,
    estimated_entries: list[dict[str, Any]],
    default_budget: int,
) -> dict[str, Any]:
    from content.execution.controller.token_ledger_journal import (
        existing_usage_journal,
    )

    queue_entries = _queue_entries(ctx.execution_id)
    managed_entries = _managed_entries(ctx, state, default_budget=default_budget)
    authoritative_entries = _dedupe_entries([*queue_entries, *managed_entries])
    entries = authoritative_entries or estimated_entries
    if queue_entries and managed_entries:
        measurement_mode = "mixed_authoritative"
    elif queue_entries:
        measurement_mode = "object_queue_authoritative"
    elif managed_entries:
        measurement_mode = "cursor_sdk_result_usage"
    else:
        measurement_mode = "estimated_from_artifacts"
    total_tokens = sum(int(entry.get("usedTokens") or 0) for entry in entries)
    total_input = sum(int(entry.get("inputTokens") or 0) for entry in entries)
    total_output = sum(int(entry.get("outputTokens") or 0) for entry in entries)
    total_cache_read = sum(
        int(entry.get("cacheReadTokens") or 0) for entry in entries
    )
    total_cache_write = sum(
        int(entry.get("cacheWriteTokens") or 0) for entry in entries
    )
    known_costs = [
        float(entry["costUsd"])
        for entry in entries
        if isinstance(entry.get("costUsd"), (int, float))
    ]
    unknown_cost_count = len(entries) - len(known_costs)
    total_cost = sum(known_costs)
    passed_object_refs = {
        str(entry.get("contentObjectRef") or "")
        for entry in entries
        if entry.get("passed") is True
        and entry.get("scope") == "content_object"
        and str(entry.get("contentObjectRef") or "")
    }
    unit_passed_cost = (
        round(total_cost / len(passed_object_refs), 9)
        if passed_object_refs and not unknown_cost_count
        else None
    )
    return {
        "schema": "quwoquan.token_ledger",
        "executionId": ctx.execution_id,
        "measurementMode": measurement_mode,
        "entries": entries,
        "usageJournal": existing_usage_journal(ctx.execution_id),
        "summary": {
            "entryCount": len(entries),
            "usedTokens": total_tokens,
            "inputTokens": total_input,
            "outputTokens": total_output,
            "cacheReadTokens": total_cache_read,
            "cacheWriteTokens": total_cache_write,
            "averageUsedTokens": round(total_tokens / len(entries), 2) if entries else 0,
            "costUsd": round(total_cost, 9) if not unknown_cost_count else None,
            "unknownCostEntryCount": unknown_cost_count,
            "retryCostUsd": round(
                sum(float(entry.get("retryCostUsd") or 0.0) for entry in entries),
                9,
            ),
            "passedObjectCount": len(passed_object_refs),
            "unitPassedCostUsd": unit_passed_cost,
            "budgetExceededCount": sum(
                1 for entry in entries if entry.get("budgetExceeded") is True
            ),
        },
    }


__all__ = [
    "build_token_ledger_payload",
    "required_creator_profile_id",
]

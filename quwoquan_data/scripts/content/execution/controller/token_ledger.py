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
from content.execution.context import ExecutionContext
from content.execution.contracts import ExecutionStateTransition


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


def _agent_run_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    scheduler = row.get("scheduler") if isinstance(row.get("scheduler"), Mapping) else {}
    refs = ",".join(
        sorted(str(ref) for ref in (row.get("refs") or []) if str(ref).strip())
    )
    return (
        str(row.get("stage") or ""),
        str((scheduler or {}).get("startedAt") or ""),
        str(row.get("finishedAt") or (scheduler or {}).get("finishedAt") or ""),
        str(row.get("plannedJobCount") or row.get("jobCount") or ""),
        refs,
    )


def dedupe_agent_runs(rows: list[Any]) -> list[Mapping[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    unique: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = _agent_run_key(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


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

    rows: list[Any] = list(state.agent_run_history or [])
    if isinstance(state.last_agent_run, Mapping):
        rows.append(state.last_agent_run)
    entries: list[dict[str, Any]] = []
    for row in dedupe_agent_runs(rows):
        stage = str(row.get("stage") or "")
        outcomes = row.get("outcomes") or []
        if not isinstance(outcomes, list):
            continue
        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                continue
            usage_mode = str(outcome.get("usageMeasurementMode") or "").strip()
            used_tokens = int(outcome.get("usedTokens") or 0)
            cost_usd = float(outcome.get("costUsd") or 0.0)
            if not usage_mode and used_tokens <= 0 and cost_usd <= 0:
                continue
            ref = str(outcome.get("ref") or "")
            if stage == ExecutionStage.BUILD_HOMEPAGE:
                content_type = ContentType.HOMEPAGE.value
                entity_payload_path = execution_root(ctx.execution_id) / ref / "_entity.json"
                creator_payload = (
                    read_json(entity_payload_path)
                    if ref and entity_payload_path.is_file()
                    else {}
                )
            else:
                coords = content_object.content_coords(ctx.execution_id, ref) if ref else {}
                creator_payload = read_writing_pack(ctx.execution_id, ref) if ref else {}
                content_type = str(coords.get("contentType") or stage).strip()
            if not content_type:
                raise DataIssueError(
                    (
                        data_issue(
                            DataIssueCode.CONTRACT_INVALID,
                            stage=DataIssueStage.CONTENT_PLAN,
                            message="contentType is required before usage is recorded",
                            ref=ref or str(outcome.get("runId") or "managed-agent-run"),
                        ),
                    )
                )
            creator_profile_id = required_creator_profile_id(
                creator_payload,
                ref=ref or str(outcome.get("runId") or "managed-agent-run"),
            )
            timing = (
                outcome.get("timing")
                if isinstance(outcome.get("timing"), Mapping)
                else {}
            )
            job_id = str(
                outcome.get("runId")
                or f"managed:{stage}:{ref or outcome.get('jobIndex')}:{timing.get('finishedAt') or row.get('finishedAt') or ''}"
            )
            entries.append(
                build_token_ledger_entry(
                    execution_id=ctx.execution_id,
                    job_id=job_id,
                    run_id=str(outcome.get("runId") or job_id),
                    creator_profile_id=creator_profile_id,
                    content_type=content_type,
                    budget_tokens=max(default_budget, used_tokens),
                    used_tokens=used_tokens,
                    cost_usd=cost_usd,
                    provider=str(
                        row.get("agentProvider")
                        or outcome.get("provider")
                        or "cursor_sdk"
                    ),
                    model=str(row.get("model") or outcome.get("model") or ""),
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
    total_cost = sum(float(entry.get("costUsd") or 0.0) for entry in entries)
    return {
        "schema": "quwoquan.token_ledger",
        "executionId": ctx.execution_id,
        "measurementMode": measurement_mode,
        "entries": entries,
        "summary": {
            "entryCount": len(entries),
            "usedTokens": total_tokens,
            "averageUsedTokens": round(total_tokens / len(entries), 2) if entries else 0,
            "costUsd": round(total_cost, 6),
            "unitPassedCostUsd": 0.0,
        },
    }


__all__ = [
    "build_token_ledger_payload",
    "dedupe_agent_runs",
    "required_creator_profile_id",
]

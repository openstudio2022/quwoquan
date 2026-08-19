"""Operator-only recovery for immutable reviewed pool-delivery intents."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from typing import Any

from core.control_types import (
    ExecutionStage,
    ExecutionStateStatus,
    QueueJobStage,
    ReliableTaskDispatchStatus,
)
from core.schema import assert_valid

from content.execution import store
from content.execution.agent.reliabletask_dispatch import (
    dispatch_reliabletask_checkpoint,
)
from content.execution.closure.pool_delivery import (
    validate_pool_delivery_intent_for_job,
)
from content.execution.context import ExecutionContext, load_execution_state
from content.execution.coverage import coverage_entity_ids
from content.execution.identity import validate_execution_id
from content.execution.queue.core import _load_jobs
from content.execution.spec_contract import ExecutionSpec
from content.execution.workspace import load_frozen_execution_manifest

_DELIVERY_ONLY_INVALID = "DATA.POOL.DELIVERY_ONLY_INVALID"


def _result(**values: Any) -> dict[str, Any]:
    report = {
        "schema": "quwoquan_data.pool_delivery_drain_result",
        **values,
    }
    assert_valid(
        report,
        "execution",
        "pool_delivery_drain_result",
        label=f"pool delivery drain:{report.get('executionId', '')}",
    )
    return report


def _drain_reviewed_delivery_only(
    execution_id: str,
    *,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Promote only immutable qualified rows without resuming the workflow."""

    if not isinstance(manifest.get("sourceDigest"), Mapping) or not isinstance(
        manifest.get("executionBundle"), Mapping
    ):
        raise ValueError(  # noqa: TRY004 - stable operator error contract
            f"{_DELIVERY_ONLY_INVALID}: execution manifest is not complete v2"
        )
    state = load_execution_state(execution_id)
    if (
        state.status is not ExecutionStateStatus.MANUAL_REQUIRED
        or state.last_failed_stage != ExecutionStage.PUBLISH.value
    ):
        raise ValueError(
            f"{_DELIVERY_ONLY_INVALID}: execution state must be "
            "manual_required with lastFailedStage=publish"
        )
    from content.execution.closure.pool_delivery import (
        write_pool_delivery_intent,
    )
    from content.execution.closure.post_review import (
        indexed_post_targets,
        load_post_review_closure,
    )
    from content.execution.closure.publish_outcome import (
        PUBLISH_APPLY_FAILED,
        is_hard_publish_failure,
        publish_issue_code,
    )
    from content.release.canonical.post_promotion import promote_post_object

    closure = load_post_review_closure(
        execution_id,
        expected_object_targets=indexed_post_targets(execution_id),
        require_quota_milestone=False,
    )
    if not closure.qualified:
        raise ValueError(
            f"{_DELIVERY_ONLY_INVALID}: review closure has no qualified object"
        )
    intents: list[str] = []
    canonical_objects: list[dict[str, str]] = []
    issue_codes: list[str] = []
    for verdict in closure.qualified:
        try:
            intent, _path = write_pool_delivery_intent(
                execution_id,
                carrier=closure.carrier,
                object_ref=verdict.object_ref,
                content_object_dir=verdict.publish_ref,
            )
            intents.append(str(intent["intentId"]))
            canonical_objects.append(
                promote_post_object(
                    execution_id,
                    verdict.publish_ref,
                    pool_delivery_intent=intent,
                )
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            if is_hard_publish_failure(exc):
                raise
            issue_codes.append(publish_issue_code(exc) or PUBLISH_APPLY_FAILED)
    completed = len(canonical_objects)
    publish_discarded = len(closure.qualified) - completed
    return _result(
        executionId=execution_id,
        recoveryMode="reviewed_delivery_only",
        executionStatePreserved=True,
        status="completed" if completed else "blocked",
        attemptedCount=len(closure.qualified),
        completedCount=completed,
        qualifiedCount=len(closure.qualified),
        discardedCount=len(closure.discarded) + publish_discarded,
        intentIds=sorted(intents),
        canonicalObjects=canonical_objects,
        issueCodes=sorted(set(issue_codes)),
    )


def drain_pool_delivery(
    execution_id: str,
    *,
    campaign_root_execution_id: str | None = None,
) -> dict[str, Any]:
    """Drain existing publish jobs without planning or invoking semantic work."""

    normalized = validate_execution_id(execution_id)
    if campaign_root_execution_id is not None:
        from content.execution.controller.execute.campaign_reviewed_publish_recovery import (
            recover_campaign_reviewed_publish,
        )

        return recover_campaign_reviewed_publish(
            normalized,
            campaign_root_execution_id,
        )
    manifest = load_frozen_execution_manifest(normalized)
    jobs = tuple(
        job for job in _load_jobs(normalized) if job.stage is QueueJobStage.PUBLISH
    )
    if not jobs:
        return _drain_reviewed_delivery_only(normalized, manifest=manifest)
    raw_spec = store.load_spec(normalized)
    frozen_spec = ExecutionSpec.from_mapping(raw_spec)
    targets = tuple(coverage_entity_ids(raw_spec))
    if not targets:
        raise ValueError("pool delivery execution has no frozen coverage targets")
    intents = tuple(validate_pool_delivery_intent_for_job(job) for job in jobs)
    ctx = ExecutionContext(
        execution_id=normalized,
        entity_ids=targets,
        spec=frozen_spec,
        managed=False,
    )
    dispatch = dispatch_reliabletask_checkpoint(ctx, ExecutionStage.PUBLISH)
    if dispatch is None:
        from content.execution.queue.reliabletask.publish_reconciliation import (
            reconcile_frozen_publish_recovery,
        )

        report = reconcile_frozen_publish_recovery(normalized)
        if report is None:
            raise ValueError(
                "pool delivery execution has no current ReliableTask receipt"
            )
        completed = int(report.succeeded)
        # 通过的回执已经用 canonical 受理口径闭合，没有需要投影的失败归因；
        # 只有未通过的回执才把每个 job 的 typed failure code 带出来。
        issue_codes = (
            []
            if report.passed
            else sorted(
                {
                    str(outcome.failure_code or _DELIVERY_ONLY_INVALID)
                    for outcome in report.outcomes
                    if outcome.status != "succeeded"
                }
            )
        )
        return _result(
            executionId=normalized,
            recoveryMode="frozen_publish_jobs",
            executionStatePreserved=True,
            status=("completed" if completed else "blocked"),
            attemptedCount=sum(outcome.attempts for outcome in report.outcomes),
            completedCount=completed,
            qualifiedCount=len(intents),
            discardedCount=max(0, len(intents) - completed),
            intentIds=sorted(str(intent["intentId"]) for intent in intents),
            canonicalObjects=[],
            issueCodes=issue_codes,
        )
    dispatch_status = dispatch.status.value
    if (
        dispatch.status is not ReliableTaskDispatchStatus.WAITING
        and dispatch.completed_count > 0
    ):
        dispatch_status = ReliableTaskDispatchStatus.COMPLETED.value
    return _result(
        executionId=normalized,
        recoveryMode="frozen_publish_jobs",
        executionStatePreserved=True,
        status=dispatch_status,
        attemptedCount=dispatch.attempted_count,
        completedCount=dispatch.completed_count,
        qualifiedCount=len(intents),
        discardedCount=(
            0
            if dispatch.status is ReliableTaskDispatchStatus.WAITING
            else max(0, len(intents) - dispatch.completed_count)
        ),
        intentIds=sorted(str(intent["intentId"]) for intent in intents),
        canonicalObjects=[],
        issueCodes=sorted({issue.code.value for issue in dispatch.issues}),
    )


def handle_drain_pool_delivery(args: argparse.Namespace) -> None:
    report = drain_pool_delivery(
        str(args.execution_id),
        campaign_root_execution_id=(
            str(args.campaign_root_execution_id)
            if args.campaign_root_execution_id
            else None
        ),
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    status = ReliableTaskDispatchStatus(str(report["status"]))
    if status is ReliableTaskDispatchStatus.WAITING:
        raise SystemExit(10)
    if status is ReliableTaskDispatchStatus.BLOCKED:
        raise SystemExit(1)


def register_drain_pool_delivery_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "drain-pool-delivery",
        help="只重放冻结的 reviewed delivery intents；不运行 semantic author/reviewer",
    )
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--campaign-root-execution-id")
    parser.set_defaults(handler=handle_drain_pool_delivery)


__all__ = [
    "drain_pool_delivery",
    "handle_drain_pool_delivery",
    "register_drain_pool_delivery_parser",
]

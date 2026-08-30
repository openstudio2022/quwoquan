"""Operator-only recovery for immutable reviewed pool-delivery intents."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from core.control_types import (
    ExecutionStage,
    ExecutionStateStatus,
    QueueJobStage,
    RecoveryNextAction,
    ReliableTaskDispatchStatus,
)
from core.schema import assert_valid

from content.execution import store
from content.execution.agent.reliabletask_dispatch import (
    dispatch_reliabletask_checkpoint,
)
from content.execution.runtime_contract import canonical_sha256
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


from content.execution.closure.pool_delivery_result import (
    build_pool_delivery_drain_result as _result,
    build_pool_delivery_object_result as _object_result,
)


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
    # 评审已裁定丢弃的对象也进 objectResults：只留一个批次级 discardedCount 时，
    # 重入的运维方无法知道是哪几个对象被排除在本次交付之外。
    rows: list[dict[str, Any]] = [
        _object_result(
            execution_id=execution_id,
            object_ref=str(verdict.object_ref),
            intent_id=None,
            result="excluded",
            next_action=RecoveryNextAction.REPAIR_EVIDENCE,
        )
        for verdict in closure.discarded
    ]
    for verdict in closure.qualified:
        intent_id: str | None = None
        try:
            intent, _path = write_pool_delivery_intent(
                execution_id,
                carrier=closure.carrier,
                object_ref=verdict.object_ref,
                content_object_dir=verdict.publish_ref,
            )
            intent_id = str(intent["intentId"])
            canonical_object = promote_post_object(
                execution_id,
                verdict.publish_ref,
                pool_delivery_intent=intent,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            if is_hard_publish_failure(exc):
                raise
            rows.append(
                _object_result(
                    execution_id=execution_id,
                    object_ref=str(verdict.object_ref),
                    intent_id=intent_id,
                    result="blocked",
                    issue_codes=[publish_issue_code(exc) or PUBLISH_APPLY_FAILED],
                    next_action=RecoveryNextAction.REPAIR_EVIDENCE,
                )
            )
            continue
        rows.append(
            _object_result(
                execution_id=execution_id,
                object_ref=str(verdict.object_ref),
                intent_id=intent_id,
                result=str(canonical_object.get("admissionResult") or "appended"),
                canonical_object=canonical_object,
            )
        )
    return _result(
        execution_id=execution_id,
        recovery_mode="reviewed_delivery_only",
        object_results=rows,
    )


def _canonical_object_from_applied_evidence(job: Any) -> Mapping[str, Any] | None:
    """Read one succeeded publish job's canonical object back from its evidence.

    The fleet applies the object transaction in its own process, so the drain
    report can only speak about a succeeded job by re-reading the durable apply
    report. Returning absent (rather than a synthesized row) keeps a job whose
    evidence is unreadable in a blocked state instead of claiming a pool delta.
    """

    from core.io import read_json
    from core.paths import OUTPUT_ROOT

    reference = str(job.result_envelope_ref or "").strip()
    if not reference:
        return None
    path = OUTPUT_ROOT / reference
    if not path.is_file():
        return None
    try:
        applied = read_json(path)
    except (OSError, TypeError, ValueError):
        return None
    if not isinstance(applied, Mapping):
        return None
    canonical_ref = str(applied.get("canonicalObjectRef") or "").strip()
    transaction_id = str(applied.get("transactionId") or "").strip()
    if not canonical_ref.startswith(("entities/", "posts/")) or not transaction_id:
        return None
    return {
        "transactionId": transaction_id,
        "applyReportRef": reference,
        "canonicalObjectRef": canonical_ref,
        "canonicalObjectSha256": str(applied.get("canonicalObjectSha256") or ""),
        "objectClosureDigest": str(applied.get("objectClosureDigest") or ""),
        "admissionResult": str(applied.get("admissionResult") or "appended"),
    }


def _job_object_result(
    execution_id: str,
    job: Any,
    intent: Mapping[str, Any],
    *,
    failure_code: str | None = None,
) -> dict[str, Any]:
    """Project one publish job's durable state into a per-object drain row."""

    from core.control_types import QueueJobState

    intent_id = str(intent["intentId"])
    object_ref = str(job.ref)
    if job.state is QueueJobState.SUCCEEDED:
        canonical_object = _canonical_object_from_applied_evidence(job)
        if canonical_object is None:
            return _object_result(
                execution_id=execution_id,
                object_ref=object_ref,
                intent_id=intent_id,
                result="blocked",
                issue_codes=[failure_code or _DELIVERY_ONLY_INVALID],
                next_action=RecoveryNextAction.REPAIR_EVIDENCE,
            )
        return _object_result(
            execution_id=execution_id,
            object_ref=object_ref,
            intent_id=intent_id,
            result=str(canonical_object["admissionResult"]),
            canonical_object=canonical_object,
        )
    if job.state in {QueueJobState.BLOCKED, QueueJobState.DEAD}:
        issue = job.last_issue
        return _object_result(
            execution_id=execution_id,
            object_ref=object_ref,
            intent_id=intent_id,
            result="blocked",
            issue_codes=[
                failure_code
                or (issue.code.value if issue is not None else _DELIVERY_ONLY_INVALID)
            ],
            next_action=RecoveryNextAction.REPAIR_EVIDENCE,
        )
    return _object_result(
        execution_id=execution_id,
        object_ref=object_ref,
        intent_id=intent_id,
        result="pending",
        issue_codes=[failure_code] if failure_code else (),
        next_action=RecoveryNextAction.RESUME_DELIVERY,
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
        # 通过的回执已经用 canonical 受理口径闭合；未通过的回执把每个 job 的
        # typed failure code 带回它自己那一行，不再压成一个批次级集合。
        failure_by_ref = {
            str(getattr(outcome, "ref", "") or ""): str(
                getattr(outcome, "failure_code", "") or _DELIVERY_ONLY_INVALID
            )
            for outcome in report.outcomes
            if getattr(outcome, "status", "") != "succeeded"
        }
        return _result(
            execution_id=normalized,
            recovery_mode="frozen_publish_jobs",
            object_results=[
                _job_object_result(
                    normalized,
                    job,
                    intent,
                    failure_code=failure_by_ref.get(str(job.ref)),
                )
                for job, intent in zip(jobs, intents, strict=True)
            ],
        )
    dispatch_issue_codes = sorted({issue.code.value for issue in dispatch.issues})
    return _result(
        execution_id=normalized,
        recovery_mode="frozen_publish_jobs",
        object_results=[
            _job_object_result(normalized, job, intent)
            for job, intent in zip(jobs, intents, strict=True)
        ],
        issue_codes=dispatch_issue_codes,
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

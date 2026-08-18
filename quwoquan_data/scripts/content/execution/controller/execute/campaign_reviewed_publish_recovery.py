"""Fenced same-execution publish recovery for an immutable reviewed lane."""

from __future__ import annotations

import fcntl
import hashlib
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from core.control_types import ExecutionStateStatus
from core.io import read_json
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid

from content.execution.campaign.distributed_frozen import load_distributed_plan
from content.execution.campaign.distributed_workspace import load_distributed_capsule
from content.execution.campaign.lane import normalize_active_carriers
from content.execution.campaign.lane_claim import (
    campaign_lane_claim_session,
    read_lane_claim,
)
from content.execution.campaign.plan import report_path
from content.execution.campaign.receipt import (
    lane_receipt_path,
    load_lane_receipt,
    write_publish_receipt,
)
from content.execution.campaign.submission import campaign_root, load_submissions
from content.execution.campaign.workspace import (
    CampaignLaneWorkspace,
    CampaignRuntimePaths,
    lane_execution_root,
)
from content.execution.closure.pool_delivery import write_pool_delivery_intent
from content.execution.closure.post_review import (
    indexed_post_targets,
    load_post_review_closure,
)
from content.execution.closure.publish_outcome import (
    PUBLISH_APPLY_FAILED,
    is_hard_publish_failure,
    publish_discard,
    publish_issue_code,
)
from content.execution.context import load_execution_state
from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.workspace import (
    execution_root as canonical_execution_root,
)
from content.execution.workspace import (
    load_frozen_execution_manifest,
    write_publish_ref,
)
from content.release.canonical.post_promotion import promote_post_object

_INVALID = "DATA.CAMPAIGN.REVIEWED_PUBLISH_RECOVERY_INVALID"
_PUBLISH_CONFLICT = "DATA.CAMPAIGN.REVIEWED_PUBLISH_CONFLICT"
_HARD_RECOVERY_MARKERS = (
    "ATTESTATION",
    "CLOSURE",
    "DIGEST",
    "EVIDENCE",
    "MANIFEST",
    "REVIEW",
    "RIGHTS",
    "SYMLINK",
    "审核",
    "授权",
    "权利",
    "证据",
)


def _result(**values: Any) -> dict[str, Any]:
    payload = {
        "schema": "quwoquan_data.pool_delivery_drain_result",
        **values,
    }
    assert_valid(
        payload,
        "execution",
        "pool_delivery_drain_result",
        label=f"campaign reviewed publish:{payload.get('executionId', '')}",
    )
    return payload


def _require_regular(path: Path, *, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{_INVALID}: {label} must be one regular file: {path}")


def _is_hard_recovery_failure(error: BaseException) -> bool:
    message = str(error).strip().upper()
    return is_hard_publish_failure(error) or any(
        marker in message for marker in _HARD_RECOVERY_MARKERS
    )


@contextmanager
def _campaign_recovery_lock(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    carrier: str,
):
    lock_path = (
        campaign_root(root_execution_id, root=runtime.campaigns_root)
        / "receipts"
        / f".{carrier}-reviewed-publish-recovery.lock"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_regular_campaign_report(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> dict[str, Any]:
    path = report_path(runtime, root_execution_id)
    _require_regular(path, label="frozen campaign report")
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise TypeError(f"{_INVALID}: frozen campaign report must be an object")
    assert_valid(
        payload,
        "execution",
        "content_campaign_report",
        label=f"frozen campaign report:{root_execution_id}",
    )
    if payload.get("rootExecutionId") != root_execution_id:
        raise ValueError(f"{_INVALID}: frozen campaign report identity drift")
    return payload


def _validate_frozen_lane(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    execution_id: str,
) -> tuple[dict[str, Any], dict[str, Any], Any, int, str]:
    plan_file = (
        campaign_root(root_execution_id, root=runtime.campaigns_root)
        / "campaign_plan.json"
    )
    _require_regular(plan_file, label="frozen campaign plan")
    plan = load_distributed_plan(runtime, root_execution_id)
    report = _load_regular_campaign_report(runtime, root_execution_id)
    capsule = load_distributed_capsule(runtime, plan, report)
    active = normalize_active_carriers(plan["activeCarriers"])
    carrier = parse_execution_id(execution_id).content_type.value
    if carrier != "article":
        raise ValueError(f"{_INVALID}: recovery currently accepts Article lanes only")
    if (
        carrier not in active
        or (plan.get("executionIds") or {}).get(carrier) != execution_id
    ):
        raise ValueError(f"{_INVALID}: execution is not the frozen campaign lane")
    quota = int((plan.get("workloads") or {}).get(carrier) or 0)
    if quota <= 0:
        raise ValueError(f"{_INVALID}: frozen Article workload quota is invalid")
    submissions = load_submissions(
        root_execution_id,
        root=runtime.campaigns_root,
    )
    if set(submissions) != set(active):
        raise ValueError(f"{_INVALID}: frozen campaign submissions are incomplete")
    for lane in active:
        submission = submissions[lane]
        if (plan.get("executionIds") or {}).get(lane) != submission.get(
            "executionId"
        ) or (plan.get("submissionDigests") or {}).get(lane) != submission.get(
            "requestDigest"
        ):
            raise ValueError(f"{_INVALID}: {lane} frozen submission drift")
    return plan, report, capsule, quota, carrier


def _validate_execution_source(
    execution_id: str,
    *,
    plan: Mapping[str, Any],
) -> None:
    manifest = load_frozen_execution_manifest(execution_id)
    source = manifest.get("sourceDigest")
    bundle = manifest.get("executionBundle")
    if (
        not isinstance(source, Mapping)
        or not isinstance(bundle, Mapping)
        or source.get("digest") != plan.get("sourceDigest")
        or dict(bundle) != plan.get("executionBundle")
    ):
        raise ValueError(f"{_INVALID}: execution source/campaign capsule drift")
    state = load_execution_state(execution_id)
    stopped_for_publish = (
        state.status is ExecutionStateStatus.STOPPED_AT_UNTIL
        and state.stopped_at_stage == "post_review"
        and state.next_action == "publish"
    )
    manual_publish = (
        state.status is ExecutionStateStatus.MANUAL_REQUIRED
        and state.last_failed_stage == "publish"
    )
    if not (stopped_for_publish or manual_publish):
        raise ValueError(
            f"{_INVALID}: execution must stop after review with nextAction=publish"
        )


def _load_reviewed_closure(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    execution_id: str,
    *,
    carrier: str,
    quota: int,
) -> tuple[dict[str, Any], Any]:
    review = load_lane_receipt(
        root_execution_id,
        carrier,
        "review",
        root=runtime.campaigns_root,
    )
    qualified_count = int(review.get("qualifiedCount") or 0)
    if (
        review.get("executionId") != execution_id
        or review.get("status") not in {"qualified", "partial"}
        or int(review.get("approvedQuota") or 0) != quota
        or qualified_count <= 0
    ):
        raise ValueError(f"{_INVALID}: review receipt is not publishable")
    closure = load_post_review_closure(
        execution_id,
        expected_object_targets=indexed_post_targets(execution_id),
        require_quota_milestone=False,
    )
    discarded = tuple(closure.discarded)
    discarded_refs = {str(row.object_ref) for row in discarded}
    receipt_discards = {
        str(row.get("objectRef") or "") for row in (review.get("discards") or [])
    }
    if (
        closure.carrier != carrier
        or len(closure.qualified) != qualified_count
        or len(discarded) != int(review.get("discardedCount") or 0)
        or int(review.get("selectedCount") or 0)
        != len(closure.qualified) + len(discarded)
        or discarded_refs != receipt_discards
        or len({str(row.object_ref) for row in closure.qualified})
        != len(closure.qualified)
        or len({str(row.publish_ref) for row in closure.qualified})
        != len(closure.qualified)
    ):
        raise ValueError(f"{_INVALID}: review receipt/object closure drift")
    return review, closure


def _normalized_publish_ref(value: object) -> str:
    return str(value or "").strip().strip("/").removeprefix("posts/")


def _load_existing_publish_outcome(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    execution_id: str,
    *,
    plan: Mapping[str, Any],
    capsule_ref: str,
    carrier: str,
    quota: int,
    review: Mapping[str, Any],
    expected_publish_refs: set[str],
) -> dict[str, Any] | None:
    publish_path = lane_execution_root(runtime, execution_id) / "publish_ref.json"
    receipt_path = lane_receipt_path(
        root_execution_id,
        carrier,
        "publish",
        root=runtime.campaigns_root,
    )
    if publish_path.is_symlink() or receipt_path.is_symlink():
        raise ValueError(f"{_PUBLISH_CONFLICT}: publish evidence cannot be symlinked")
    has_publish = publish_path.is_file()
    has_receipt = receipt_path.is_file()
    if not has_publish and not has_receipt:
        return None
    if has_publish != has_receipt:
        raise ValueError(
            f"{_PUBLISH_CONFLICT}: publish_ref and receipt must already form a pair"
        )
    raw = publish_path.read_bytes()
    publish = read_json(publish_path)
    assert_valid(
        publish,
        "execution",
        "publish_ref",
        label=f"existing campaign publish_ref:{execution_id}",
    )
    receipt = load_lane_receipt(
        root_execution_id,
        carrier,
        "publish",
        root=runtime.campaigns_root,
    )
    refs = (publish.get("publishedRefs") or {}).get("posts") or []
    publish_discards = publish.get("publishDiscards") or []
    outcome_refs = {str(ref) for ref in refs} | {
        str(row.get("objectRef") or "") for row in publish_discards
    }
    distributed = plan.get("distributedRun") or {}
    portable_ref = publish_path.resolve().relative_to(runtime.output_root.resolve())
    claim = read_lane_claim(runtime, root_execution_id, carrier)
    expected_claim = {
        "rootExecutionId": root_execution_id,
        "planDigest": plan.get("planDigest"),
        "campaignRunId": distributed.get("campaignRunId"),
        "campaignGeneration": distributed.get("campaignGeneration"),
        "campaignFencingToken": distributed.get("campaignFencingToken"),
        "executionId": execution_id,
        "carrier": carrier,
        "capsuleRef": capsule_ref,
        "status": "completed",
        "phase": "completed",
    }
    if (
        publish.get("executionId") != execution_id
        or outcome_refs != expected_publish_refs
        or len(refs) + len(publish_discards) != int(review.get("qualifiedCount") or 0)
        or receipt.get("executionId") != execution_id
        or int(receipt.get("approvedQuota") or 0) != quota
        or int(receipt.get("finalizedCount") or 0) != len(refs)
        or receipt.get("publishDiscards") != publish_discards
        or receipt.get("executionPublishRef") != portable_ref.as_posix()
        or receipt.get("executionPublishSha256")
        != "sha256:" + hashlib.sha256(raw).hexdigest()
        or any(
            receipt.get(key) != distributed.get(source)
            for key, source in {
                "campaignRunId": "campaignRunId",
                "campaignGeneration": "campaignGeneration",
                "campaignFencingToken": "campaignFencingToken",
            }.items()
        )
        or not isinstance(claim, Mapping)
        or any(claim.get(key) != value for key, value in expected_claim.items())
    ):
        raise ValueError(f"{_PUBLISH_CONFLICT}: terminal publish evidence drift")
    issues = sorted(
        {str(issue) for row in publish_discards for issue in (row.get("issues") or [])}
    )
    return _result(
        executionId=execution_id,
        recoveryMode="campaign_reviewed_publish",
        executionStatePreserved=True,
        status="completed" if refs else "blocked",
        attemptedCount=int(review["qualifiedCount"]),
        completedCount=len(refs),
        qualifiedCount=int(review["qualifiedCount"]),
        discardedCount=int(review["discardedCount"]) + len(publish_discards),
        intentIds=[],
        canonicalObjects=[],
        issueCodes=issues,
    )


def _recover_campaign_reviewed_publish_locked(
    execution_id: str,
    root_execution_id: str,
    *,
    runtime_paths: CampaignRuntimePaths | None = None,
) -> dict[str, Any]:
    """Publish the immutable qualified closure under a new lane claim attempt."""

    normalized = validate_execution_id(execution_id)
    root_id = validate_execution_id(root_execution_id)
    runtime = runtime_paths or CampaignRuntimePaths.defaults()
    plan, _report, capsule, quota, carrier = _validate_frozen_lane(
        runtime,
        root_id,
        normalized,
    )
    _validate_execution_source(normalized, plan=plan)
    review, closure = _load_reviewed_closure(
        runtime,
        root_id,
        normalized,
        carrier=carrier,
        quota=quota,
    )
    expected_refs = {
        _normalized_publish_ref(verdict.publish_ref) for verdict in closure.qualified
    }
    existing = _load_existing_publish_outcome(
        runtime,
        root_id,
        normalized,
        plan=plan,
        capsule_ref=str(capsule.ref),
        carrier=carrier,
        quota=quota,
        review=review,
        expected_publish_refs=expected_refs,
    )
    if existing is not None:
        return existing
    workspace = CampaignLaneWorkspace(
        carrier=carrier,
        capsule=capsule,
        execution_root=lane_execution_root(runtime, normalized),
    )
    if (
        workspace.execution_root.resolve()
        != canonical_execution_root(normalized).resolve()
    ):
        raise ValueError(f"{_INVALID}: lane execution root is not canonical")
    intents: list[str] = []
    canonical: list[dict[str, str]] = []
    successful_refs: list[str] = []
    publish_discards: list[dict[str, Any]] = []
    with campaign_lane_claim_session(
        runtime,
        root_id,
        plan=plan,
        carrier=carrier,
        workspace=workspace,
        process_termination_timeout_seconds=(
            active_runtime_policy().process_termination_timeout_seconds
        ),
    ) as session:
        session.lane_checkpoint(
            carrier=carrier,
            execution_id=normalized,
            phase="run",
            status="running",
            capsule_ref=workspace.ref,
            execution_root=workspace.execution_root,
        )
        for verdict in closure.qualified:
            try:
                intent, _intent_path = write_pool_delivery_intent(
                    normalized,
                    carrier=carrier,
                    object_ref=verdict.object_ref,
                    content_object_dir=verdict.publish_ref,
                )
                intents.append(str(intent["intentId"]))
                promoted = promote_post_object(
                    normalized,
                    verdict.publish_ref,
                    pool_delivery_intent=intent,
                )
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                if _is_hard_recovery_failure(exc):
                    raise
                publish_discards.append(
                    publish_discard(
                        _normalized_publish_ref(verdict.publish_ref),
                        issue=publish_issue_code(exc) or PUBLISH_APPLY_FAILED,
                    )
                )
                continue
            canonical.append(promoted)
            promoted_ref = _normalized_publish_ref(promoted["canonicalObjectRef"])
            expected_ref = _normalized_publish_ref(verdict.publish_ref)
            if promoted_ref != expected_ref:
                raise ValueError(
                    "DATA.PUBLISH.TARGET_CONFLICT: promoted object identity drift"
                )
            successful_refs.append(promoted_ref)
        publish_path = workspace.execution_root / "publish_ref.json"
        receipt_path = lane_receipt_path(
            root_id,
            carrier,
            "publish",
            root=runtime.campaigns_root,
        )
        if (
            publish_path.exists()
            or publish_path.is_symlink()
            or receipt_path.exists()
            or receipt_path.is_symlink()
        ):
            raise ValueError(
                f"{_PUBLISH_CONFLICT}: publish evidence appeared during claim"
            )
        write_publish_ref(
            normalized,
            post_refs=successful_refs,
            publish_discards=publish_discards,
        )
        write_publish_receipt(
            root_execution_id=root_id,
            execution_id=normalized,
            runtime_paths=runtime,
        )
        session.finish(status="completed")
    issue_codes = sorted({issue for row in publish_discards for issue in row["issues"]})
    return _result(
        executionId=normalized,
        recoveryMode="campaign_reviewed_publish",
        executionStatePreserved=True,
        status="completed" if canonical else "blocked",
        attemptedCount=len(closure.qualified),
        completedCount=len(canonical),
        qualifiedCount=len(closure.qualified),
        discardedCount=len(closure.discarded) + len(publish_discards),
        intentIds=sorted(intents),
        canonicalObjects=canonical,
        issueCodes=issue_codes,
    )


def recover_campaign_reviewed_publish(
    execution_id: str,
    root_execution_id: str,
    *,
    runtime_paths: CampaignRuntimePaths | None = None,
) -> dict[str, Any]:
    """Serialize operator calls while the campaign lane claim remains the fence."""

    normalized = validate_execution_id(execution_id)
    root_id = validate_execution_id(root_execution_id)
    runtime = runtime_paths or CampaignRuntimePaths.defaults()
    carrier = parse_execution_id(normalized).content_type.value
    with _campaign_recovery_lock(runtime, root_id, carrier):
        return _recover_campaign_reviewed_publish_locked(
            normalized,
            root_id,
            runtime_paths=runtime,
        )


__all__ = ["recover_campaign_reviewed_publish"]

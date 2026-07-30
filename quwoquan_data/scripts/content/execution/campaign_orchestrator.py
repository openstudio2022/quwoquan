"""Fail-closed four-lane campaign orchestration behind ``task execute``.

Lane failures stay lane-local: qualified objects on other carriers still publish.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.runtime_policy import DEFAULT_RUNTIME_PROFILE_ID, load_runtime_policy
from content.execution.campaign_copy_ready import maybe_write_copy_ready_receipt
from content.execution.campaign_plan import (
    aggregate_status,
    apply_receipt_fields,
    controller_lock,
    empty_lane,
    freeze_plan,
    load_review_for_lane,
    report_path,
    utc_now,
    wait_for_submissions,
    write_report,
)
from content.execution.campaign_receipt import load_lane_receipt
from content.execution.campaign_process import (
    CAMPAIGN_CARRIERS,
    LaneRunner,
    run_phase,
)
from content.execution.campaign_workspace import (
    CampaignRuntimePaths,
    DetachedClone,
    assert_frozen_main_tree,
    assert_frozen_revision,
    cleanup_clone,
    prepare_detached_clone,
    require_clean_main_tree,
)
from content.execution.identity import validate_execution_id


_REVIEW_STAGE = "review-only"
_PUBLISH_STAGE = "run"


def run_campaign(
    root_execution_id: str,
    *,
    submission_timeout_seconds: int | None = None,
    lane_timeout_seconds: float | None = None,
    runtime_paths: CampaignRuntimePaths | None = None,
    lane_runner: LaneRunner | None = None,
) -> Path:
    root_id = validate_execution_id(root_execution_id)
    runtime = runtime_paths or CampaignRuntimePaths.defaults()
    policy = load_runtime_policy(DEFAULT_RUNTIME_PROFILE_ID)
    effective_submission_timeout = (
        submission_timeout_seconds or policy.campaign_submission_timeout_seconds
    )
    effective_lane_timeout = (
        lane_timeout_seconds or policy.campaign_lane_timeout_seconds
    )
    started_at = utc_now()
    lanes = {carrier: empty_lane() for carrier in CAMPAIGN_CARRIERS}
    clones: dict[str, DetachedClone] = {}
    plan: dict[str, Any] | None = None
    plan_digest: str | None = None
    final_status = "blocked"
    final_phase = "submission"
    failure: str | None = None
    caught: Exception | None = None

    with controller_lock(runtime, root_id):
        try:
            require_clean_main_tree(runtime.repo_root)
            submissions = wait_for_submissions(
                runtime,
                root_id,
                timeout_seconds=effective_submission_timeout,
                lanes=lanes,
                started_at=started_at,
            )
            for carrier in CAMPAIGN_CARRIERS:
                lanes[carrier]["executionId"] = str(
                    submissions[carrier]["executionId"]
                )
            final_phase = "freeze"
            plan, plan_digest = freeze_plan(runtime, root_id, submissions)
            write_report(
                runtime,
                root_id,
                status="running",
                phase="clone",
                plan_digest=plan_digest,
                git_branch=str(plan["gitBranch"]),
                git_commit_sha=str(plan["gitCommitSha"]),
                source_digest=str(plan["sourceDigest"]),
                entity_catalog_digest=str(plan["entityCatalogDigest"]),
                lanes=lanes,
                started_at=started_at,
                failure=None,
            )
            final_phase = "clone"
            for carrier in CAMPAIGN_CARRIERS:
                clone = prepare_detached_clone(
                    runtime,
                    root_execution_id=root_id,
                    carrier=carrier,
                    commit_sha=str(plan["gitCommitSha"]),
                    source_digest=str(plan["sourceDigest"]),
                )
                clones[carrier] = clone
                lanes[carrier].update(
                    {
                        "status": "clone_ready",
                        "phase": "clone",
                        "cloneRef": clone.ref,
                        "cloneCommitSha": clone.commit_sha,
                        "cloneSourceDigest": clone.source_digest,
                        "cloneDetached": clone.detached,
                        "cleanupStatus": "pending",
                    }
                )
            assert_frozen_main_tree(
                runtime.repo_root,
                git_branch=str(plan["gitBranch"]),
                commit_sha=str(plan["gitCommitSha"]),
                source_digest=str(plan["sourceDigest"]),
            )
            final_phase = "review"
            review = run_phase(
                clones,
                submissions,
                stage=_REVIEW_STAGE,
                runtime=runtime,
                root_execution_id=root_id,
                timeout_seconds=effective_lane_timeout,
                worker_count=policy.campaign_lane_workers,
                lane_runner=lane_runner,
            )
            publishable: list[str] = []
            for carrier, (code, error) in review.items():
                lanes[carrier].update(
                    {
                        "reviewReturnCode": code,
                        "phase": "review",
                        "error": error,
                    }
                )
                if code != 0:
                    lanes[carrier]["status"] = "blocked"
                    continue
                receipt = load_review_for_lane(
                    runtime,
                    root_id,
                    carrier,
                    expected_execution_id=str(submissions[carrier]["executionId"]),
                    expected_quota=int(submissions[carrier]["quota"]),
                )
                if receipt is None:
                    lanes[carrier]["status"] = "blocked"
                    lanes[carrier]["error"] = (
                        error or f"{carrier} review receipt missing after success"
                    )
                    continue
                apply_receipt_fields(lanes, carrier, receipt, phase="review")
                if int(receipt["qualifiedCount"]) > 0 and str(
                    receipt["status"]
                ) in {"qualified", "partial"}:
                    publishable.append(carrier)
                else:
                    lanes[carrier]["status"] = "blocked"
            write_report(
                runtime,
                root_id,
                status="running",
                phase="publish",
                plan_digest=plan_digest,
                git_branch=str(plan["gitBranch"]),
                git_commit_sha=str(plan["gitCommitSha"]),
                source_digest=str(plan["sourceDigest"]),
                entity_catalog_digest=str(plan["entityCatalogDigest"]),
                lanes=lanes,
                started_at=started_at,
                failure=None,
            )
            final_phase = "publish"
            if publishable:
                assert_frozen_main_tree(
                    runtime.repo_root,
                    git_branch=str(plan["gitBranch"]),
                    commit_sha=str(plan["gitCommitSha"]),
                    source_digest=str(plan["sourceDigest"]),
                )
                published = run_phase(
                    clones,
                    submissions,
                    stage=_PUBLISH_STAGE,
                    runtime=runtime,
                    root_execution_id=root_id,
                    timeout_seconds=effective_lane_timeout,
                    worker_count=policy.campaign_lane_workers,
                    lane_runner=lane_runner,
                    carriers=tuple(publishable),
                )
                for carrier, (code, error) in published.items():
                    lanes[carrier].update(
                        {
                            "publishReturnCode": code,
                            "phase": "publish",
                            "error": error if code != 0 else None,
                        }
                    )
                    if code != 0:
                        lanes[carrier]["status"] = "blocked"
                        continue
                    try:
                        receipt = load_lane_receipt(
                            root_id,
                            carrier,
                            "publish",
                            root=runtime.campaigns_root,
                        )
                    except (OSError, ValueError) as exc:
                        lanes[carrier]["status"] = "blocked"
                        lanes[carrier]["error"] = str(exc)
                        continue
                    if str(receipt.get("executionId") or "") != str(
                        submissions[carrier]["executionId"]
                    ):
                        lanes[carrier]["status"] = "blocked"
                        lanes[carrier]["error"] = (
                            f"{carrier} publish receipt executionId drift"
                        )
                        continue
                    apply_receipt_fields(lanes, carrier, receipt, phase="publish")
            assert_frozen_revision(
                runtime.repo_root,
                git_branch=str(plan["gitBranch"]),
                commit_sha=str(plan["gitCommitSha"]),
                source_digest=str(plan["sourceDigest"]),
            )
            final_status = aggregate_status(lanes)
            final_phase = "completed"
            if final_status == "blocked":
                failure = "campaign produced no publishable qualified objects"
                caught = RuntimeError(failure)
            else:
                lane_failures = [
                    f"{carrier}:{lanes[carrier].get('error') or lanes[carrier]['status']}"
                    for carrier in CAMPAIGN_CARRIERS
                    if str(lanes[carrier].get("status") or "") == "blocked"
                    or int(lanes[carrier].get("finalizedCount") or 0) <= 0
                ]
                if lane_failures and final_status == "succeeded_partial":
                    failure = "partial campaign; blocked lanes: " + ", ".join(
                        lane_failures
                    )
                maybe_write_copy_ready_receipt(
                    root_execution_id=root_id,
                    plan=plan,
                    submissions=submissions,
                    lanes=lanes,
                    campaigns_root=runtime.campaigns_root,
                    output_root=runtime.output_root,
                    assessed_at=utc_now(),
                )
        except Exception as exc:  # noqa: BLE001
            caught = exc
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            cleanup_errors: list[str] = []
            for carrier, clone in clones.items():
                try:
                    cleanup_clone(clone)
                    lanes[carrier]["cleanupStatus"] = "cleaned"
                except OSError as exc:
                    lanes[carrier]["cleanupStatus"] = "failed"
                    cleanup_errors.append(f"{carrier}: {exc}")
            if cleanup_errors:
                final_status = "blocked"
                final_phase = "cleanup"
                failure = "; ".join(
                    item for item in (failure, *cleanup_errors) if item
                )
                if caught is None:
                    caught = RuntimeError(failure)
            write_report(
                runtime,
                root_id,
                status=final_status,
                phase=final_phase,
                plan_digest=plan_digest,
                git_branch=(
                    str(plan["gitBranch"]) if plan is not None else None
                ),
                git_commit_sha=(
                    str(plan["gitCommitSha"]) if plan is not None else None
                ),
                source_digest=(
                    str(plan["sourceDigest"]) if plan is not None else None
                ),
                entity_catalog_digest=(
                    str(plan["entityCatalogDigest"]) if plan is not None else None
                ),
                lanes=lanes,
                started_at=started_at,
                failure=failure,
            )
    if caught is not None and final_status == "blocked":
        raise caught
    return report_path(runtime, root_id)


__all__ = [
    "CAMPAIGN_CARRIERS",
    "LaneRunner",
    "run_campaign",
]

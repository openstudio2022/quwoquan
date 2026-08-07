"""Freeze once, run one claimed carrier per session, then aggregate receipts."""
from __future__ import annotations

import fcntl
from pathlib import Path
from typing import Any

from core.io import read_json
from core.runtime_policy import DEFAULT_RUNTIME_PROFILE_ID, load_runtime_policy
from core.schema import assert_valid

from content.execution.campaign.copy_ready import maybe_write_copy_ready_receipt
from content.execution.campaign.external_input_runtime import (
    freeze_execution_external_input_envelope,
)
from content.execution.campaign.fleet_transport import (
    resolve_campaign_fleet_transport,
)
from content.execution.campaign.lane_claim import (
    campaign_lane_claim_session,
    read_lane_claim,
)
from content.execution.campaign.observer_binary import (
    resolve_campaign_observer_binary,
)
from content.execution.campaign.plan import (
    aggregate_status,
    apply_receipt_fields,
    empty_lane,
    freeze_plan,
    load_publish_for_lane,
    load_review_for_lane,
    report_path,
    sha256_payload,
    utc_now,
    wait_for_submissions,
    write_report,
)
from content.execution.campaign.process import (
    CAMPAIGN_CARRIERS,
    LaneRunner,
    run_phase,
)
from content.execution.campaign.receipt import load_lane_receipt
from content.execution.campaign.runtime import (
    campaign_run_session,
    read_runtime_snapshot,
)
from content.execution.campaign.submission import campaign_root, load_submissions
from content.execution.campaign.workspace import (
    CampaignLaneWorkspace,
    CampaignRuntimePaths,
    SourceCapsule,
    assert_frozen_main_tree,
    prepare_lane_workspace,
    prepare_source_capsule,
    release_lane_workspace,
)
from content.execution.identity import validate_execution_id


def _load_distributed_plan(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> dict[str, Any]:
    path = (
        campaign_root(root_execution_id, root=runtime.campaigns_root)
        / "campaign_plan.json"
    )
    plan = read_json(path)
    assert_valid(
        plan,
        "execution",
        "content_campaign_plan",
        label=f"distributed campaign plan:{root_execution_id}",
    )
    stable = {key: value for key, value in plan.items() if key != "planDigest"}
    if (
        plan.get("rootExecutionId") != root_execution_id
        or plan.get("executionMode") != "distributed"
        or plan.get("planDigest") != sha256_payload(stable)
    ):
        raise ValueError("distributed campaign plan identity or digest drift")
    return plan


def _reuse_existing_frozen_campaign(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> Path | None:
    campaign = campaign_root(root_execution_id, root=runtime.campaigns_root)
    if not (campaign / "campaign_plan.json").is_file():
        return None
    plan = _load_distributed_plan(runtime, root_execution_id)
    submissions = load_submissions(
        root_execution_id,
        root=runtime.campaigns_root,
    )
    if set(submissions) != set(CAMPAIGN_CARRIERS):
        raise ValueError("existing frozen campaign submissions are incomplete")
    for carrier in CAMPAIGN_CARRIERS:
        if (
            plan["executionIds"].get(carrier)
            != submissions[carrier].get("executionId")
            or plan["submissionDigests"].get(carrier)
            != submissions[carrier].get("requestDigest")
        ):
            raise ValueError(
                f"existing frozen campaign {carrier} submission drift"
            )
    distributed_run = plan.get("distributedRun")
    snapshot = read_runtime_snapshot(runtime, root_execution_id)
    if (
        not isinstance(distributed_run, dict)
        or not isinstance(snapshot, dict)
        or snapshot.get("runId") != distributed_run.get("campaignRunId")
        or snapshot.get("generation")
        != distributed_run.get("campaignGeneration")
        or snapshot.get("fencingToken")
        != distributed_run.get("campaignFencingToken")
        or snapshot.get("planDigest") != plan.get("planDigest")
        or snapshot.get("status") != "frozen"
        or not snapshot.get("finishedAt")
    ):
        raise ValueError("existing frozen campaign runtime fence drift")
    path = report_path(runtime, root_execution_id)
    if not path.is_file():
        raise ValueError("existing frozen campaign report is missing")
    report = read_json(path)
    assert_valid(
        report,
        "execution",
        "content_campaign_report",
        label=f"distributed campaign report:{root_execution_id}",
    )
    if (
        report.get("rootExecutionId") != root_execution_id
        or report.get("planDigest") != plan.get("planDigest")
    ):
        raise ValueError("existing frozen campaign report identity drift")
    return path


def _prepare_capsule(
    runtime: CampaignRuntimePaths,
    plan: dict[str, Any],
) -> SourceCapsule:
    return prepare_source_capsule(
        runtime,
        commit_sha=str(plan["gitCommitSha"]),
        source_revision=str(plan["sourceRevision"]),
        source_digest=str(plan["sourceDigest"]),
        entity_catalog_digest=str(plan["entityCatalogDigest"]),
        lane_external_inputs=dict(plan["laneExternalInputs"]),
        external_inputs_digest=str(plan["externalInputsDigest"]),
    )


def _prepare_workspace(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    plan: dict[str, Any],
    submissions: dict[str, dict[str, Any]],
    capsule: SourceCapsule,
    carrier: str,
) -> CampaignLaneWorkspace:
    workspace = prepare_lane_workspace(
        runtime,
        capsule=capsule,
        carrier=carrier,
        execution_id=str(submissions[carrier]["executionId"]),
    )
    freeze_execution_external_input_envelope(
        runtime=runtime,
        root_execution_id=root_execution_id,
        plan=plan,
        submission=submissions[carrier],
        workspace=workspace,
    )
    return workspace


def freeze_campaign(
    root_execution_id: str,
    *,
    submission_timeout_seconds: int | None = None,
    runtime_paths: CampaignRuntimePaths | None = None,
) -> Path:
    root_id = validate_execution_id(root_execution_id)
    runtime = runtime_paths or CampaignRuntimePaths.defaults()
    from content.execution.campaign.submission_reconciliation import (
        assert_campaign_not_reconciled,
    )

    assert_campaign_not_reconciled(root_id, output_root=runtime.output_root)
    existing_report = _reuse_existing_frozen_campaign(runtime, root_id)
    if existing_report is not None:
        return existing_report
    policy = load_runtime_policy(DEFAULT_RUNTIME_PROFILE_ID)
    timeout = (
        submission_timeout_seconds or policy.campaign_submission_timeout_seconds
    )
    started_at = utc_now()
    lanes = {carrier: empty_lane() for carrier in CAMPAIGN_CARRIERS}
    with campaign_run_session(
        runtime,
        root_id,
        lease_seconds=policy.controller_lease_stale_seconds,
        process_termination_timeout_seconds=(
            policy.process_termination_timeout_seconds
        ),
    ) as session:
        session.campaign_checkpoint(phase="submission")
        submissions = wait_for_submissions(
            runtime,
            root_id,
            timeout_seconds=timeout,
            lanes=lanes,
            started_at=started_at,
            run_session=session,
        )
        for carrier in CAMPAIGN_CARRIERS:
            lanes[carrier]["executionId"] = str(submissions[carrier]["executionId"])
        plan, plan_digest = freeze_plan(
            runtime,
            root_id,
            submissions,
            execution_mode="distributed",
            distributed_run={
                "campaignRunId": session.run_id,
                "campaignGeneration": session.generation,
                "campaignFencingToken": session.fencing_token,
            },
        )
        session.campaign_checkpoint(phase="capsule", plan_digest=plan_digest)
        capsule = _prepare_capsule(runtime, plan)
        for carrier in CAMPAIGN_CARRIERS:
            workspace = _prepare_workspace(
                runtime,
                root_id,
                plan,
                submissions,
                capsule,
                carrier,
            )
            lanes[carrier].update(
                {
                    "status": "capsule_ready",
                    "phase": "capsule",
                    "sourceCapsuleRef": workspace.ref,
                    "sourceCapsuleDigest": capsule.capsule_digest,
                    "sourceCapsuleCommitSha": capsule.commit_sha,
                    "sourceCapsuleSourceDigest": capsule.source_digest,
                    "sourceCapsuleReadOnly": capsule.read_only,
                    "executionRootRef": workspace.execution_root.relative_to(
                        runtime.output_root
                    ).as_posix(),
                    "cleanupStatus": "pending",
                }
            )
            release_lane_workspace(workspace)
        path = write_report(
            runtime,
            root_id,
            status="running",
            phase="capsule",
            plan_digest=plan_digest,
            git_branch=str(plan["gitBranch"]),
            git_commit_sha=str(plan["gitCommitSha"]),
            source_digest=str(plan["sourceDigest"]),
            entity_catalog_digest=str(plan["entityCatalogDigest"]),
            lanes=lanes,
            started_at=started_at,
            failure=None,
        )
        session.finish(status="frozen", phase="capsule", failure=None)
        return path


def run_campaign_lane(
    root_execution_id: str,
    carrier: str,
    *,
    lane_timeout_seconds: float | None = None,
    runtime_paths: CampaignRuntimePaths | None = None,
    lane_runner: LaneRunner | None = None,
) -> Path:
    root_id = validate_execution_id(root_execution_id)
    if carrier not in CAMPAIGN_CARRIERS:
        raise ValueError(f"campaign carrier is invalid: {carrier}")
    runtime = runtime_paths or CampaignRuntimePaths.defaults()
    policy = load_runtime_policy(DEFAULT_RUNTIME_PROFILE_ID)
    timeout = lane_timeout_seconds or policy.campaign_lane_timeout_seconds
    plan = _load_distributed_plan(runtime, root_id)
    submissions = load_submissions(root_id, root=runtime.campaigns_root)
    if set(submissions) != set(CAMPAIGN_CARRIERS):
        raise ValueError("distributed campaign submissions are incomplete")
    expected_execution_id = str((plan["executionIds"] or {}).get(carrier) or "")
    if expected_execution_id != str(submissions[carrier]["executionId"]):
        raise ValueError(f"{carrier} distributed execution identity drift")
    existing = load_publish_for_lane(
        runtime,
        root_id,
        carrier,
        expected_execution_id=expected_execution_id,
        expected_quota=int(submissions[carrier]["quota"]),
    )
    if existing is not None:
        return report_path(runtime, root_id)
    assert_frozen_main_tree(
        runtime.repo_root,
        git_branch=str(plan["gitBranch"]),
        commit_sha=str(plan["gitCommitSha"]),
        source_digest=str(plan["sourceDigest"]),
    )
    capsule = _prepare_capsule(runtime, plan)
    workspace = _prepare_workspace(
        runtime,
        root_id,
        plan,
        submissions,
        capsule,
        carrier,
    )
    observer = resolve_campaign_observer_binary(
        runtime,
        root_id,
        plan_digest=str(plan["planDigest"]),
    )
    fleet = resolve_campaign_fleet_transport(
        runtime,
        root_id,
        plan_digest=str(plan["planDigest"]),
    )
    try:
        with campaign_lane_claim_session(
            runtime,
            root_id,
            plan=plan,
            carrier=carrier,
            workspace=workspace,
            process_termination_timeout_seconds=(
                policy.process_termination_timeout_seconds
            ),
        ) as session:
            review = load_review_for_lane(
                runtime,
                root_id,
                carrier,
                expected_execution_id=expected_execution_id,
                expected_quota=int(submissions[carrier]["quota"]),
            )
            if review is None:
                reviewed = run_phase(
                    {carrier: workspace},
                    {carrier: submissions[carrier]},
                    stage="review-only",
                    runtime=runtime,
                    root_execution_id=root_id,
                    timeout_seconds=timeout,
                    worker_count=1,
                    lane_runner=lane_runner,
                    run_session=session,
                    observer_binary_binding=observer,
                    fleet_transport_binding=fleet,
                    carriers=(carrier,),
                )
                code, error = reviewed[carrier]
                if code != 0:
                    raise RuntimeError(error or f"{carrier} review failed")
                review = load_review_for_lane(
                    runtime,
                    root_id,
                    carrier,
                    expected_execution_id=expected_execution_id,
                    expected_quota=int(submissions[carrier]["quota"]),
                )
            if (
                review is None
                or int(review["qualifiedCount"]) <= 0
                or str(review["status"]) not in {"qualified", "partial"}
            ):
                raise RuntimeError(f"{carrier} review produced no qualified objects")
            assert_frozen_main_tree(
                runtime.repo_root,
                git_branch=str(plan["gitBranch"]),
                commit_sha=str(plan["gitCommitSha"]),
                source_digest=str(plan["sourceDigest"]),
            )
            published = run_phase(
                {carrier: workspace},
                {carrier: submissions[carrier]},
                stage="run",
                runtime=runtime,
                root_execution_id=root_id,
                timeout_seconds=timeout,
                worker_count=1,
                lane_runner=lane_runner,
                run_session=session,
                observer_binary_binding=observer,
                fleet_transport_binding=fleet,
                carriers=(carrier,),
            )
            code, error = published[carrier]
            if code != 0:
                raise RuntimeError(error or f"{carrier} publish failed")
            receipt = load_lane_receipt(
                root_id,
                carrier,
                "publish",
                root=runtime.campaigns_root,
            )
            distributed = plan["distributedRun"]
            if any(
                receipt.get(key) != distributed[source]
                for key, source in (
                    ("campaignRunId", "campaignRunId"),
                    ("campaignGeneration", "campaignGeneration"),
                    ("campaignFencingToken", "campaignFencingToken"),
                )
            ):
                raise ValueError(f"{carrier} publish receipt campaign fence drift")
            session.finish(status="completed")
    finally:
        release_lane_workspace(workspace)
    return report_path(runtime, root_id)


def finalize_campaign(
    root_execution_id: str,
    *,
    runtime_paths: CampaignRuntimePaths | None = None,
) -> Path:
    root_id = validate_execution_id(root_execution_id)
    runtime = runtime_paths or CampaignRuntimePaths.defaults()
    campaign = campaign_root(root_id, root=runtime.campaigns_root)
    lock_path = campaign / ".finalize.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        plan = _load_distributed_plan(runtime, root_id)
        submissions = load_submissions(root_id, root=runtime.campaigns_root)
        if set(submissions) != set(CAMPAIGN_CARRIERS):
            raise ValueError("distributed campaign submissions are incomplete")
        capsule = _prepare_capsule(runtime, plan)
        lanes = {carrier: empty_lane() for carrier in CAMPAIGN_CARRIERS}
        failure_rows: list[str] = []
        for carrier in CAMPAIGN_CARRIERS:
            execution_id = str(submissions[carrier]["executionId"])
            workspace = _prepare_workspace(
                runtime,
                root_id,
                plan,
                submissions,
                capsule,
                carrier,
            )
            lane = lanes[carrier]
            lane.update(
                {
                    "executionId": execution_id,
                    "sourceCapsuleRef": workspace.ref,
                    "sourceCapsuleDigest": capsule.capsule_digest,
                    "sourceCapsuleCommitSha": capsule.commit_sha,
                    "sourceCapsuleSourceDigest": capsule.source_digest,
                    "sourceCapsuleReadOnly": capsule.read_only,
                    "executionRootRef": workspace.execution_root.relative_to(
                        runtime.output_root
                    ).as_posix(),
                    "cleanupStatus": "cleaned",
                }
            )
            review = load_review_for_lane(
                runtime,
                root_id,
                carrier,
                expected_execution_id=execution_id,
                expected_quota=int(submissions[carrier]["quota"]),
            )
            if review is not None:
                lane["reviewReturnCode"] = 0
                apply_receipt_fields(lanes, carrier, review, phase="review")
            publish = load_publish_for_lane(
                runtime,
                root_id,
                carrier,
                expected_execution_id=execution_id,
                expected_quota=int(submissions[carrier]["quota"]),
            )
            if publish is not None:
                lane["publishReturnCode"] = 0
                apply_receipt_fields(lanes, carrier, publish, phase="publish")
            else:
                claim = read_lane_claim(runtime, root_id, carrier)
                lane.update(
                    {
                        "status": "blocked",
                        "publishReturnCode": (
                            int(claim["returnCode"])
                            if claim and claim.get("returnCode") is not None
                            else None
                        ),
                        "error": (
                            str(claim.get("error") or "publish receipt missing")
                            if claim
                            else "carrier session has not claimed this lane"
                        ),
                    }
                )
                failure_rows.append(f"{carrier}:{lane['error']}")
            release_lane_workspace(workspace)
        status = aggregate_status(lanes)
        failure = "; ".join(failure_rows) if failure_rows else None
        path = write_report(
            runtime,
            root_id,
            status=status,
            phase="completed",
            plan_digest=str(plan["planDigest"]),
            git_branch=str(plan["gitBranch"]),
            git_commit_sha=str(plan["gitCommitSha"]),
            source_digest=str(plan["sourceDigest"]),
            entity_catalog_digest=str(plan["entityCatalogDigest"]),
            lanes=lanes,
            started_at=str(plan["frozenAt"]),
            failure=failure,
        )
        if all(
            str(lanes[carrier]["status"]) in {"finalized", "partial"}
            for carrier in CAMPAIGN_CARRIERS
        ):
            maybe_write_copy_ready_receipt(
                root_execution_id=root_id,
                plan=plan,
                submissions=submissions,
                lanes=lanes,
                campaigns_root=runtime.campaigns_root,
                output_root=runtime.output_root,
                assessed_at=utc_now(),
            )
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return path


__all__ = [
    "finalize_campaign",
    "freeze_campaign",
    "run_campaign_lane",
]

"""Fail-closed four-lane campaign orchestration behind ``task execute``.

Lane failures stay lane-local: qualified objects on other carriers still publish.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.runtime_policy import DEFAULT_RUNTIME_PROFILE_ID, load_runtime_policy

from content.execution.campaign.copy_ready import maybe_write_copy_ready_receipt
from content.execution.campaign.external_input_runtime import (
    freeze_execution_external_input_envelope,
)
from content.execution.campaign.fleet_transport import (
    resolve_campaign_fleet_transport,
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
    utc_now,
    wait_for_submissions,
    write_report,
)
from content.execution.campaign.lane import (
    CAMPAIGN_CARRIERS,
    LaneRunner,
)
from content.execution.campaign.process import run_phase
from content.execution.campaign.receipt import load_lane_receipt
from content.execution.campaign.runtime import campaign_run_session
from content.execution.campaign.workspace import (
    CampaignLaneWorkspace,
    CampaignRuntimePaths,
    SourceCapsule,
    assert_frozen_main_tree,
    assert_frozen_revision,
    prepare_lane_workspace,
    prepare_source_capsule,
    release_lane_workspace,
)
from content.execution.identity import validate_execution_id
from content.execution.queue.reliabletask.transport import FrozenReliableTaskFleetBinding
from content.execution.runtime_evidence.reliabletask_process import (
    ReliableTaskObserverBinaryBinding,
)

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
    from content.execution.campaign.submission_reconciliation import (
        assert_campaign_not_reconciled,
    )

    assert_campaign_not_reconciled(
        root_id,
        output_root=runtime.output_root,
    )
    policy = load_runtime_policy(DEFAULT_RUNTIME_PROFILE_ID)
    effective_submission_timeout = (
        submission_timeout_seconds or policy.campaign_submission_timeout_seconds
    )
    effective_lane_timeout: float | None = None
    started_at = utc_now()
    lanes = {carrier: empty_lane() for carrier in CAMPAIGN_CARRIERS}
    workspaces: dict[str, CampaignLaneWorkspace] = {}
    capsule: SourceCapsule | None = None
    plan: dict[str, Any] | None = None
    plan_digest: str | None = None
    submissions: dict[str, dict[str, Any]] | None = None
    final_status = "blocked"
    final_phase = "submission"
    failure: str | None = None
    caught: BaseException | None = None
    review_carriers: list[str] = list(CAMPAIGN_CARRIERS)
    recovered_review_carriers: list[str] = []
    observer_binary_binding: ReliableTaskObserverBinaryBinding | None = None
    fleet_transport_binding: FrozenReliableTaskFleetBinding | None = None

    with campaign_run_session(
        runtime,
        root_id,
        lease_seconds=policy.controller_lease_stale_seconds,
        process_termination_timeout_seconds=(
            policy.process_termination_timeout_seconds
        ),
    ) as campaign_run:
        try:
            campaign_run.campaign_checkpoint(phase="submission")
            submissions = wait_for_submissions(
                runtime,
                root_id,
                timeout_seconds=effective_submission_timeout,
                lanes=lanes,
                started_at=started_at,
                run_session=campaign_run,
            )
            for carrier in CAMPAIGN_CARRIERS:
                lanes[carrier]["executionId"] = str(submissions[carrier]["executionId"])
            final_phase = "freeze"
            plan, plan_digest = freeze_plan(runtime, root_id, submissions)
            effective_lane_timeout = (
                lane_timeout_seconds
                or policy.campaign_lane_timeout_seconds_for_scale(str(plan["scale"]))
            )
            campaign_run.campaign_checkpoint(
                phase="freeze",
                plan_digest=plan_digest,
            )

            def persist_running_report(phase: str) -> None:
                campaign_run.campaign_checkpoint(
                    phase=phase,
                    plan_digest=plan_digest,
                )
                write_report(
                    runtime,
                    root_id,
                    status="running",
                    phase=phase,
                    plan_digest=plan_digest,
                    git_branch=str(plan["gitBranch"]),
                    git_commit_sha=str(plan["gitCommitSha"]),
                    source_digest=str(plan["sourceDigest"]),
                    entity_catalog_digest=str(plan["entityCatalogDigest"]),
                    lanes=lanes,
                    started_at=started_at,
                    failure=None,
                )

            persist_running_report("capsule")
            final_phase = "capsule"
            capsule = prepare_source_capsule(
                runtime,
                commit_sha=str(plan["gitCommitSha"]),
                source_revision=str(plan["sourceRevision"]),
                source_digest=str(plan["sourceDigest"]),
                entity_catalog_digest=str(plan["entityCatalogDigest"]),
                lane_external_inputs=dict(plan["laneExternalInputs"]),
                external_inputs_digest=str(plan["externalInputsDigest"]),
            )
            for carrier in CAMPAIGN_CARRIERS:
                workspace = prepare_lane_workspace(
                    runtime,
                    capsule=capsule,
                    carrier=carrier,
                    execution_id=str(submissions[carrier]["executionId"]),
                )
                workspaces[carrier] = workspace
                freeze_execution_external_input_envelope(
                    runtime=runtime,
                    root_execution_id=root_id,
                    plan=plan,
                    submission=submissions[carrier],
                    workspace=workspace,
                )
                lanes[carrier].update(
                    {
                        "status": "capsule_ready",
                        "phase": "capsule",
                        "sourceCapsuleRef": workspace.ref,
                        "sourceCapsuleDigest": workspace.capsule.capsule_digest,
                        "sourceCapsuleCommitSha": workspace.commit_sha,
                        "sourceCapsuleSourceDigest": workspace.source_digest,
                        "sourceCapsuleReadOnly": workspace.capsule.read_only,
                        "executionRootRef": workspace.execution_root.relative_to(
                            runtime.output_root
                        ).as_posix(),
                        "cleanupStatus": "pending",
                    }
                )
                campaign_run.lane_checkpoint(
                    carrier=carrier,
                    execution_id=str(submissions[carrier]["executionId"]),
                    phase="capsule",
                    status="ready",
                    capsule_ref=workspace.ref,
                    execution_root=workspace.execution_root,
                )
                persist_running_report("capsule")
            for carrier in CAMPAIGN_CARRIERS:
                expected_execution_id = str(submissions[carrier]["executionId"])
                expected_quota = int(submissions[carrier]["quota"])
                publish_receipt = load_publish_for_lane(
                    runtime,
                    root_id,
                    carrier,
                    expected_execution_id=expected_execution_id,
                    expected_quota=expected_quota,
                )
                if publish_receipt is not None:
                    lanes[carrier]["reviewReturnCode"] = 0
                    lanes[carrier]["publishReturnCode"] = 0
                    apply_receipt_fields(
                        lanes,
                        carrier,
                        publish_receipt,
                        phase="publish",
                    )
                    review_carriers.remove(carrier)
                    campaign_run.lane_checkpoint(
                        carrier=carrier,
                        execution_id=expected_execution_id,
                        phase="publish",
                        status="recovered",
                        capsule_ref=workspaces[carrier].ref,
                        execution_root=workspaces[carrier].execution_root,
                        return_code=0,
                    )
                    continue
                review_receipt = load_review_for_lane(
                    runtime,
                    root_id,
                    carrier,
                    expected_execution_id=expected_execution_id,
                    expected_quota=expected_quota,
                )
                if (
                    review_receipt is not None
                    and int(review_receipt["qualifiedCount"]) > 0
                    and str(review_receipt["status"]) in {"qualified", "partial"}
                ):
                    lanes[carrier]["reviewReturnCode"] = 0
                    apply_receipt_fields(
                        lanes,
                        carrier,
                        review_receipt,
                        phase="review",
                    )
                    review_carriers.remove(carrier)
                    recovered_review_carriers.append(carrier)
                    campaign_run.lane_checkpoint(
                        carrier=carrier,
                        execution_id=expected_execution_id,
                        phase="review",
                        status="recovered",
                        capsule_ref=workspaces[carrier].ref,
                        execution_root=workspaces[carrier].execution_root,
                        return_code=0,
                    )
            if review_carriers or recovered_review_carriers:
                observer_binary_binding = resolve_campaign_observer_binary(
                    runtime,
                    root_id,
                    plan_digest=str(plan_digest),
                )
                fleet_transport_binding = resolve_campaign_fleet_transport(
                    runtime,
                    root_id,
                    plan_digest=str(plan_digest),
                )
            assert_frozen_main_tree(
                runtime.repo_root,
                git_branch=str(plan["gitBranch"]),
                commit_sha=str(plan["gitCommitSha"]),
                source_digest=str(plan["sourceDigest"]),
            )
            final_phase = "review"
            persist_running_report("review")

            def publish_reviewed_lane(carrier: str) -> None:
                assert_frozen_main_tree(
                    runtime.repo_root,
                    git_branch=str(plan["gitBranch"]),
                    commit_sha=str(plan["gitCommitSha"]),
                    source_digest=str(plan["sourceDigest"]),
                )
                # Publish stays single-writer because all carriers share the
                # canonical PUBLISH_ROOT.  It starts as soon as this lane's
                # review closes instead of waiting for sibling reviews.
                published = run_phase(
                    workspaces,
                    submissions,
                    stage=_PUBLISH_STAGE,
                    runtime=runtime,
                    root_execution_id=root_id,
                    timeout_seconds=effective_lane_timeout,
                    worker_count=1,
                    lane_runner=lane_runner,
                    run_session=campaign_run,
                    observer_binary_binding=observer_binary_binding,
                    fleet_transport_binding=fleet_transport_binding,
                    carriers=(carrier,),
                )
                code, error = published[carrier]
                lanes[carrier].update(
                    {
                        "publishReturnCode": code,
                        "phase": "publish",
                        "error": error if code != 0 else None,
                    }
                )
                if code != 0:
                    lanes[carrier]["status"] = "blocked"
                    persist_running_report("publish")
                    return
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
                    persist_running_report("publish")
                    return
                if str(receipt.get("executionId") or "") != str(
                    submissions[carrier]["executionId"]
                ):
                    lanes[carrier]["status"] = "blocked"
                    lanes[carrier]["error"] = (
                        f"{carrier} publish receipt executionId drift"
                    )
                    persist_running_report("publish")
                    return
                apply_receipt_fields(lanes, carrier, receipt, phase="publish")
                persist_running_report("publish")

            def handle_review_result(
                carrier: str,
                result: tuple[int, str | None],
            ) -> None:
                code, error = result
                lanes[carrier].update(
                    {
                        "reviewReturnCode": code,
                        "phase": "review",
                        "error": error,
                    }
                )
                if code != 0:
                    lanes[carrier]["status"] = "blocked"
                    persist_running_report("review")
                    return
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
                    persist_running_report("review")
                    return
                apply_receipt_fields(lanes, carrier, receipt, phase="review")
                if int(receipt["qualifiedCount"]) > 0 and str(receipt["status"]) in {
                    "qualified",
                    "partial",
                }:
                    publish_reviewed_lane(carrier)
                else:
                    lanes[carrier]["status"] = "blocked"
                    persist_running_report("review")

            for carrier in recovered_review_carriers:
                publish_reviewed_lane(carrier)
            run_phase(
                workspaces,
                submissions,
                stage=_REVIEW_STAGE,
                runtime=runtime,
                root_execution_id=root_id,
                timeout_seconds=effective_lane_timeout,
                worker_count=policy.campaign_lane_workers,
                lane_runner=lane_runner,
                run_session=campaign_run,
                observer_binary_binding=observer_binary_binding,
                fleet_transport_binding=fleet_transport_binding,
                carriers=tuple(review_carriers),
                on_result=handle_review_result,
            )
            persist_running_report("publish")
            final_phase = "publish"
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
        except BaseException as exc:  # noqa: BLE001
            campaign_run.abort_active_lanes()
            caught = exc
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            cleanup_errors: list[str] = []
            for carrier, workspace in workspaces.items():
                try:
                    release_lane_workspace(workspace)
                    lanes[carrier]["cleanupStatus"] = "cleaned"
                except OSError as exc:
                    lanes[carrier]["cleanupStatus"] = "failed"
                    cleanup_errors.append(f"{carrier}: {exc}")
            if cleanup_errors:
                final_status = "blocked"
                final_phase = "cleanup"
                failure = "; ".join(item for item in (failure, *cleanup_errors) if item)
                if caught is None:
                    caught = RuntimeError(failure)
            # COPY_READY predicates require cleanupStatus=cleaned; write only
            # after every lane releases process ownership of the shared capsule.
            lanes_ready_for_copy = all(
                str(lanes[carrier].get("status") or "") in {"finalized", "partial"}
                and str(lanes[carrier].get("cleanupStatus") or "") == "cleaned"
                for carrier in CAMPAIGN_CARRIERS
            )
            if plan is not None and submissions is not None and lanes_ready_for_copy:
                maybe_write_copy_ready_receipt(
                    root_execution_id=root_id,
                    plan=plan,
                    submissions=submissions,
                    lanes=lanes,
                    campaigns_root=runtime.campaigns_root,
                    output_root=runtime.output_root,
                    assessed_at=utc_now(),
                )
            campaign_run.assert_fence()
            write_report(
                runtime,
                root_id,
                status=final_status,
                phase=final_phase,
                plan_digest=plan_digest,
                git_branch=(str(plan["gitBranch"]) if plan is not None else None),
                git_commit_sha=(
                    str(plan["gitCommitSha"]) if plan is not None else None
                ),
                source_digest=(str(plan["sourceDigest"]) if plan is not None else None),
                entity_catalog_digest=(
                    str(plan["entityCatalogDigest"]) if plan is not None else None
                ),
                lanes=lanes,
                started_at=started_at,
                failure=failure,
            )
            campaign_run.finish(
                status=final_status,
                phase=final_phase,
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

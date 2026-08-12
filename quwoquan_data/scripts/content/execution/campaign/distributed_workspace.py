"""Capsule/workspace preparation for the distributed campaign facade."""
from __future__ import annotations

from typing import Any

from content.execution.campaign.external_input_runtime import (
    freeze_execution_external_input_envelope,
)
from content.execution.campaign.capsule_reload import load_source_capsule
from content.execution.campaign.workspace import (
    CampaignLaneWorkspace,
    CampaignRuntimePaths,
    SourceCapsule,
    prepare_lane_workspace,
    prepare_source_capsule,
)


CAPSULE_INTEGRITY_FAILURE_CODE = "DATA.CONTRACT.INVALID"


def prepare_distributed_capsule(
    runtime: CampaignRuntimePaths, plan: dict[str, Any]
) -> SourceCapsule:
    pool_selections = plan.get("laneSourcePoolSelections")
    return prepare_source_capsule(
        runtime,
        git_branch=str(plan["gitBranch"]),
        commit_sha=str(plan["gitCommitSha"]),
        source_revision=str(plan["sourceRevision"]),
        source_digest=str(plan["sourceDigest"]),
        execution_bundle=dict(plan["executionBundle"]),
        entity_catalog_digest=str(plan["entityCatalogDigest"]),
        lane_external_inputs=dict(plan["laneExternalInputs"]),
        external_inputs_digest=str(plan["externalInputsDigest"]),
        scale_source_pool=(
            dict(plan["scaleSourcePool"])
            if isinstance(plan.get("scaleSourcePool"), dict)
            else None
        ),
        source_pool_evidence_root_ref=(
            str(plan["sourcePoolEvidenceRootRef"])
            if plan.get("sourcePoolEvidenceRootRef") is not None
            else None
        ),
        lane_source_pool_selections=(
            {
                str(carrier): dict(selection)
                for carrier, selection in pool_selections.items()
            }
            if isinstance(pool_selections, dict)
            else None
        ),
    )


def load_distributed_capsule(
    runtime: CampaignRuntimePaths,
    plan: dict[str, Any],
    report: dict[str, Any],
) -> SourceCapsule:
    lanes = report.get("lanes")
    if not isinstance(lanes, dict) or set(lanes) != {
        "homepage",
        "article",
        "image",
        "video",
    }:
        raise ValueError("frozen campaign report lanes are incomplete")
    refs = {str(lane.get("sourceCapsuleRef") or "") for lane in lanes.values()}
    digests = {
        str(lane.get("sourceCapsuleDigest") or "") for lane in lanes.values()
    }
    if len(refs) != 1 or "" in refs or len(digests) != 1 or "" in digests:
        raise ValueError("frozen campaign report capsule binding drift")
    for carrier, lane in lanes.items():
        if (
            lane.get("executionId") != plan["executionIds"][carrier]
            or lane.get("sourceCapsuleCommitSha") != plan["gitCommitSha"]
            or lane.get("sourceCapsuleSourceDigest") != plan["sourceDigest"]
            or lane.get("sourceCapsuleReadOnly") is not True
        ):
            raise ValueError(f"frozen campaign {carrier} capsule identity drift")
    pool_selections = plan.get("laneSourcePoolSelections")
    return load_source_capsule(
        runtime,
        capsule_ref=refs.pop(),
        capsule_digest=digests.pop(),
        git_branch=str(plan["gitBranch"]),
        commit_sha=str(plan["gitCommitSha"]),
        source_revision=str(plan["sourceRevision"]),
        source_digest=str(plan["sourceDigest"]),
        execution_bundle=dict(plan["executionBundle"]),
        entity_catalog_digest=str(plan["entityCatalogDigest"]),
        lane_external_inputs=dict(plan["laneExternalInputs"]),
        external_inputs_digest=str(plan["externalInputsDigest"]),
        scale_source_pool=(
            dict(plan["scaleSourcePool"])
            if isinstance(plan.get("scaleSourcePool"), dict)
            else None
        ),
        lane_source_pool_selections=(
            {
                str(carrier): dict(selection)
                for carrier, selection in pool_selections.items()
            }
            if isinstance(pool_selections, dict)
            else None
        ),
    )


def capsule_integrity_failure_lanes(
    report: dict[str, Any],
    submissions: dict[str, dict[str, Any]],
    *,
    detail: str,
) -> tuple[dict[str, dict[str, Any]], str]:
    """Project a terminal blocker without consuming a corrupted capsule."""

    failure = (
        f"{CAPSULE_INTEGRITY_FAILURE_CODE}: "
        f"campaign capsule integrity failure: {detail}"
    )
    frozen_lanes = report["lanes"]
    lanes: dict[str, dict[str, Any]] = {}
    for carrier in ("homepage", "article", "image", "video"):
        lane = dict(frozen_lanes[carrier])
        lane.update(
            {
                "executionId": str(submissions[carrier]["executionId"]),
                "status": "blocked",
                "phase": "capsule",
                "reviewReturnCode": None,
                "publishReturnCode": None,
                "sourceCapsuleReadOnly": False,
                "cleanupStatus": "failed",
                "approvedQuota": None,
                "qualifiedCount": None,
                "finalizedCount": None,
                "selectedCount": None,
                "discardedCount": None,
                "shortfallCount": None,
                "error": failure,
            }
        )
        lanes[carrier] = lane
    return lanes, failure


def prepare_distributed_workspace(
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


__all__ = [
    "capsule_integrity_failure_lanes",
    "load_distributed_capsule",
    "prepare_distributed_capsule",
    "prepare_distributed_workspace",
]

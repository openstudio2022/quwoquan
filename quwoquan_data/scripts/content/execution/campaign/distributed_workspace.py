"""Capsule/workspace preparation for the distributed campaign facade."""
from __future__ import annotations

from typing import Any

from content.execution.campaign.external_input_runtime import (
    freeze_execution_external_input_envelope,
)
from content.execution.campaign.workspace import (
    CampaignLaneWorkspace,
    CampaignRuntimePaths,
    SourceCapsule,
    prepare_lane_workspace,
    prepare_source_capsule,
)


def prepare_distributed_capsule(
    runtime: CampaignRuntimePaths, plan: dict[str, Any]
) -> SourceCapsule:
    pool_selections = plan.get("laneSourcePoolSelections")
    return prepare_source_capsule(
        runtime,
        commit_sha=str(plan["gitCommitSha"]),
        source_revision=str(plan["sourceRevision"]),
        source_digest=str(plan["sourceDigest"]),
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


__all__ = ["prepare_distributed_capsule", "prepare_distributed_workspace"]

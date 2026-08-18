"""Strict reload of a frozen campaign capsule for terminal aggregation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.io import read_json
from content.execution.campaign.lane import normalize_active_carriers

from content.execution.campaign.workspace import (
    CampaignRuntimePaths,
    SourceCapsule,
    load_source_capsule_manifest,
)


def load_source_capsule(
    runtime_paths: CampaignRuntimePaths,
    *,
    capsule_ref: str,
    capsule_digest: str,
    git_branch: str,
    commit_sha: str,
    source_revision: str,
    source_digest: str,
    execution_bundle: dict[str, Any],
    entity_catalog_digest: str,
    lane_external_inputs: dict[str, dict[str, Any]],
    external_inputs_digest: str,
    scale_source_pool: dict[str, Any] | None = None,
    lane_source_pool_selections: dict[str, dict[str, Any]] | None = None,
) -> SourceCapsule:
    """Load immutable bytes without consulting the later live source tree."""
    relative = Path(str(capsule_ref).strip())
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("campaign capsule ref is unsafe")
    capsule_path = (runtime_paths.output_root / relative).resolve()
    expected_parent = (
        runtime_paths.workspaces_root / "content-addressed-capsules"
    ).resolve()
    if capsule_path.parent != expected_parent:
        raise ValueError("campaign capsule ref is outside the canonical root")
    expected_key = str(capsule_digest).removeprefix("sha256:")
    if len(expected_key) != 64 or capsule_path.name != expected_key:
        raise ValueError("campaign capsule ref/digest drift")
    manifest = read_json(capsule_path / ".qwq_campaign_capsule.json")
    if not isinstance(manifest, dict):
        raise TypeError("campaign capsule manifest must be an object")
    stable = {
        key: value
        for key, value in manifest.items()
        if key not in {"capsuleDigest", "treeDigest"}
    }
    expected_identity = {
        "gitBranch": git_branch,
        "gitCommitSha": commit_sha,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "executionBundle": execution_bundle,
        "entityCatalogDigest": entity_catalog_digest,
        "externalInputsDigest": external_inputs_digest,
    }
    if any(stable.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("campaign capsule plan identity drift")
    active = normalize_active_carriers(lane_external_inputs)
    expected_lanes = {
        carrier: {
            "rootRef": f"external-inputs/{carrier}",
            "externalInputRefs": list(lane_external_inputs[carrier]["externalInputRefs"]),
            "externalInputsDigest": str(
                lane_external_inputs[carrier]["externalInputsDigest"]
            ),
        }
        for carrier in active
    }
    if stable.get("laneExternalInputs") != expected_lanes:
        raise ValueError("campaign capsule external input plan drift")
    capsule = load_source_capsule_manifest(
        runtime_paths,
        capsule_path,
        stable=stable,
        capsule_digest=capsule_digest,
    )
    if capsule.scale_source_pool != scale_source_pool:
        raise ValueError("campaign capsule scale source pool plan drift")
    if capsule.lane_source_pool_selections != lane_source_pool_selections:
        raise ValueError("campaign capsule lane source pool selection drift")
    return capsule


__all__ = ["load_source_capsule"]

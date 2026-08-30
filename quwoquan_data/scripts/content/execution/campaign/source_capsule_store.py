"""Content-addressed campaign source capsule store.

从 workspace.py 逐字迁出的 capsule 域：capsule 常量、CampaignRuntimePaths、
SourceCapsule 与 capsule 身份/装载/物化函数。workspace.py 保持 re-export，
既有引用面不变。
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core import paths
from core.content_library import library_root_for_output
from core.io import read_json, write_json
from core.schema import assert_valid
from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
)

from content.execution.campaign.external_inputs import (
    external_inputs_digest as refs_digest,
)
from content.execution.campaign.external_inputs import (
    lane_acquisition_root,
    materialize_external_input_bundle,
    payload_digest,
    verify_external_input_refs,
)
from content.execution.campaign.source_snapshot import (
    SNAPSHOT_FORMAT,
    campaign_snapshot_roots,
    materialize_source_snapshot,
)
from content.execution.campaign.capsule_seal import (
    capsule_tree_digest,
    capsule_tree_is_sealed,
    discard_capsule_tree,
    seal_capsule_tree,
)
from content.execution.campaign.source_pool_binding import (
    capsule_source_pool_fields,
    load_capsule_source_pool,
    materialize_bound_scale_source_pool,
    resolve_capsule_scale_source_pool_identity,
)

CAPSULE_SCHEMA = "quwoquan_data.content_campaign_source_capsule"
CAPSULE_FORMAT = SNAPSHOT_FORMAT


@dataclass(frozen=True, slots=True)
class CampaignRuntimePaths:
    repo_root: Path
    output_root: Path
    publish_root: Path
    campaigns_root: Path
    workspaces_root: Path

    @property
    def acquisition_root(self) -> Path:
        relative = paths.SOURCE_ACQUISITION_ROOT.relative_to(paths.OUTPUT_ROOT)
        return (self.output_root / relative).resolve()

    @property
    def library_root(self) -> Path:
        return library_root_for_output(self.output_root).resolve()

    @classmethod
    def defaults(cls) -> CampaignRuntimePaths:
        workspace = paths.DATA_LOCAL_ROOT / "workspace"
        campaigns = workspace / "content-campaign-submissions"
        return cls(
            repo_root=paths.REPO_ROOT.resolve(),
            output_root=paths.OUTPUT_ROOT.resolve(),
            publish_root=paths.PUBLISH_ROOT.resolve(),
            campaigns_root=campaigns.resolve(),
            workspaces_root=paths.CONTENT_CAMPAIGN_WORKSPACES_ROOT.resolve(),
        )


@dataclass(frozen=True, slots=True)
class SourceCapsule:
    path: Path
    ref: str
    capsule_digest: str
    git_branch: str
    commit_sha: str
    source_revision: str
    source_digest: str
    execution_bundle_digest: str
    entity_catalog_digest: str
    external_inputs_digest: str
    lane_external_inputs: dict[str, dict[str, Any]]
    roots: tuple[str, ...]
    read_only: bool
    scale_source_pool: dict[str, Any] | None = None
    lane_source_pool_selections: dict[str, dict[str, Any]] | None = None
    source_pool_snapshot_root_ref: str | None = None

    def external_input_root(self, carrier: str) -> Path:
        lane = self.lane_external_inputs.get(carrier)
        if not isinstance(lane, dict):
            raise TypeError(f"campaign capsule has no {carrier} external input lane")
        relative = Path(str(lane.get("rootRef") or ""))
        root = (self.path / relative).resolve()
        if self.path.resolve() not in root.parents:
            raise ValueError("campaign capsule external input root escapes capsule")
        return root

    def source_pool_snapshot_root(self) -> Path:
        if not self.source_pool_snapshot_root_ref:
            raise ValueError("campaign capsule has no scale source pool")
        root = (self.path / self.source_pool_snapshot_root_ref).resolve()
        if self.path.resolve() not in root.parents:
            raise ValueError("campaign capsule source pool escapes capsule")
        return root



def _portable_ref(path: Path, output_root: Path) -> str:
    try:
        return path.relative_to(output_root).as_posix()
    except ValueError:
        return path.as_posix()


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _capsule_identity(
    *,
    git_branch: str,
    commit_sha: str,
    source_revision: str,
    source_digest: str,
    execution_bundle: dict[str, Any],
    entity_catalog_digest: str,
    lane_external_inputs: dict[str, dict[str, Any]],
    external_inputs_digest: str,
    source_pool_fields: dict[str, Any],
    roots: tuple[str, ...],
) -> tuple[dict[str, Any], str]:
    stable = {
        "schema": CAPSULE_SCHEMA,
        "format": CAPSULE_FORMAT,
        "gitBranch": git_branch,
        "gitCommitSha": commit_sha,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "executionBundle": execution_bundle,
        "entityCatalogDigest": entity_catalog_digest,
        "roots": list(roots),
        "laneExternalInputs": lane_external_inputs,
        "externalInputsDigest": external_inputs_digest,
    }
    stable.update(source_pool_fields)
    return stable, _canonical_digest(stable)


def load_source_capsule_manifest(
    runtime_paths: CampaignRuntimePaths,
    path: Path,
    *,
    stable: dict[str, Any],
    capsule_digest: str,
) -> SourceCapsule:
    manifest_path = path / ".qwq_campaign_capsule.json"
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise TypeError("campaign capsule manifest must be an object")
    assert_valid(
        manifest,
        "execution",
        "content_source_capsule",
        label=f"campaign capsule:{path}",
    )
    expected_fields = {*stable, "capsuleDigest", "treeDigest"}
    if set(manifest) != expected_fields or any(
        manifest.get(key) != value for key, value in stable.items()
    ):
        raise ValueError("campaign capsule manifest drift")
    if manifest.get("capsuleDigest") != capsule_digest:
        raise ValueError("campaign capsule identity digest drift")
    if manifest.get("treeDigest") != capsule_tree_digest(path):
        raise ValueError("campaign capsule tree digest drift")
    observed_digest = SourceDefinitionSnapshot.build(repo_root=path).digest
    if observed_digest != stable["sourceDigest"]:
        raise ValueError(
            "campaign capsule sourceDigest mismatch: "
            f"{observed_digest} != {stable['sourceDigest']}"
        )
    observed_bundle = ExecutionBundleIdentity.build(repo_root=path).digest
    if observed_bundle != stable["executionBundle"]["digest"]:
        raise ValueError("campaign capsule executionBundle mismatch")
    for carrier, lane in stable["laneExternalInputs"].items():
        if lane["externalInputsDigest"] != refs_digest(lane["externalInputRefs"]):
            raise ValueError(
                "campaign capsule lane externalInputsDigest drift: " f"{carrier}"
            )
        verify_external_input_refs(
            carrier,
            lane["externalInputRefs"],
            acquisition_root=(path / str(lane["rootRef"])).resolve(),
            source_revision=str(stable["sourceRevision"]),
            source_digest=str(stable["sourceDigest"]),
            entity_catalog_digest=str(stable["entityCatalogDigest"]),
        )
    pool_binding, lane_pool_selections, snapshot_root_ref = load_capsule_source_pool(
        stable, capsule_path=path
    )
    if not capsule_tree_is_sealed(path):
        raise ValueError("campaign capsule must be read-only")
    return SourceCapsule(
        path=path,
        ref=_portable_ref(path, runtime_paths.output_root),
        capsule_digest=capsule_digest,
        git_branch=str(stable["gitBranch"]),
        commit_sha=str(stable["gitCommitSha"]),
        source_revision=str(stable["sourceRevision"]),
        source_digest=str(stable["sourceDigest"]),
        execution_bundle_digest=str(stable["executionBundle"]["digest"]),
        entity_catalog_digest=str(stable["entityCatalogDigest"]),
        external_inputs_digest=str(stable["externalInputsDigest"]),
        lane_external_inputs={
            str(carrier): dict(lane)
            for carrier, lane in stable["laneExternalInputs"].items()
        },
        scale_source_pool=pool_binding,
        lane_source_pool_selections=lane_pool_selections,
        source_pool_snapshot_root_ref=snapshot_root_ref,
        roots=tuple(str(item) for item in stable["roots"]),
        read_only=True,
    )


def prepare_source_capsule(
    runtime_paths: CampaignRuntimePaths,
    *,
    git_branch: str,
    commit_sha: str,
    source_revision: str,
    source_digest: str,
    execution_bundle: dict[str, Any],
    entity_catalog_digest: str,
    lane_external_inputs: dict[str, dict[str, Any]],
    external_inputs_digest: str,
    scale_source_pool: dict[str, Any] | None = None,
    source_pool_evidence_root_ref: str | None = None,
    lane_source_pool_selections: dict[str, dict[str, Any]] | None = None,
) -> SourceCapsule:
    """Export one immutable source tree shared by the active lane processes."""
    from content.execution.campaign.lane import normalize_active_carriers

    active = normalize_active_carriers(lane_external_inputs)
    expected_aggregate = payload_digest(
        {
            "schema": "quwoquan_data.campaign_external_input_lanes",
            "lanes": lane_external_inputs,
        }
    )
    if external_inputs_digest != expected_aggregate:
        raise ValueError(
            "GATE_BLOCK DATA.CAMPAIGN.EXTERNAL_INPUT_DIGEST_DRIFT: "
            "campaign aggregate externalInputsDigest drift"
        )
    capsule_lanes = {
        carrier: {
            "rootRef": f"external-inputs/{carrier}",
            "externalInputRefs": list(lane_external_inputs[carrier]["externalInputRefs"]),
            "externalInputsDigest": str(
                lane_external_inputs[carrier]["externalInputsDigest"]
            ),
        }
        for carrier in active
    }
    for carrier, lane in capsule_lanes.items():
        if lane["externalInputsDigest"] != refs_digest(lane["externalInputRefs"]):
            raise ValueError(
                "GATE_BLOCK DATA.CAMPAIGN.EXTERNAL_INPUT_DIGEST_DRIFT: "
                f"{carrier} externalInputsDigest drift"
            )
    roots = campaign_snapshot_roots(
        runtime_paths.repo_root,
        expected_digest=source_digest,
        expected_execution_bundle=str(execution_bundle["digest"]),
    )
    source_pool_snapshot_root_ref, source_pool_snapshot_digest = (
        resolve_capsule_scale_source_pool_identity(
            scale_source_pool,
            evidence_root_ref=source_pool_evidence_root_ref,
            output_root=runtime_paths.output_root,
            lane_selections=lane_source_pool_selections,
        )
    )
    source_pool_fields = capsule_source_pool_fields(
        scale_source_pool,
        lane_source_pool_selections,
        source_pool_snapshot_root_ref,
        source_pool_snapshot_digest,
    )
    stable, capsule_digest = _capsule_identity(
        git_branch=git_branch,
        commit_sha=commit_sha,
        source_revision=source_revision,
        source_digest=source_digest,
        execution_bundle=execution_bundle,
        entity_catalog_digest=entity_catalog_digest,
        lane_external_inputs=capsule_lanes,
        external_inputs_digest=external_inputs_digest,
        roots=roots,
        source_pool_fields=source_pool_fields,
    )
    key = capsule_digest.removeprefix("sha256:")
    capsules_root = runtime_paths.workspaces_root / "content-addressed-capsules"
    capsule_path = capsules_root / key
    capsules_root.mkdir(parents=True, exist_ok=True)
    lock_path = capsules_root / f".{key}.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if capsule_path.is_dir():
            try:
                return load_source_capsule_manifest(
                    runtime_paths,
                    capsule_path,
                    stable=stable,
                    capsule_digest=capsule_digest,
                )
            except (OSError, TypeError, ValueError):
                discard_capsule_tree(capsule_path)

        temp_root = Path(
            tempfile.mkdtemp(prefix=f".{key}.", dir=capsules_root)
        )
        try:
            materialize_source_snapshot(
                runtime_paths.repo_root,
                temp_root,
                roots=roots,
                expected_digest=source_digest,
                expected_execution_bundle=str(execution_bundle["digest"]),
                library_root=runtime_paths.library_root,
            )
            for carrier, lane in capsule_lanes.items():
                materialize_external_input_bundle(
                    temp_root / str(lane["rootRef"]),
                    lane["externalInputRefs"],
                    acquisition_root=lane_acquisition_root(
                        lane_external_inputs.get(carrier) or {},
                        default=runtime_paths.acquisition_root,
                    ),
                    carrier=carrier,
                    source_revision=source_revision,
                    source_digest=source_digest,
                    entity_catalog_digest=entity_catalog_digest,
                    library_root=runtime_paths.library_root,
                )
            if scale_source_pool is not None:
                materialize_bound_scale_source_pool(
                    scale_source_pool,
                    evidence_root_ref=str(source_pool_evidence_root_ref),
                    output_root=runtime_paths.output_root,
                    destination=temp_root / str(source_pool_snapshot_root_ref),
                    lane_selections=lane_source_pool_selections or {},
                    expected_snapshot_digest=source_pool_snapshot_digest,
                )
            write_json(
                temp_root / ".qwq_campaign_capsule.json",
                {
                    **stable,
                    "capsuleDigest": capsule_digest,
                    "treeDigest": capsule_tree_digest(temp_root),
                },
            )
            seal_capsule_tree(temp_root)
            os.replace(temp_root, capsule_path)
        finally:
            if temp_root.exists():
                discard_capsule_tree(temp_root)
        return load_source_capsule_manifest(
            runtime_paths,
            capsule_path,
            stable=stable,
            capsule_digest=capsule_digest,
        )

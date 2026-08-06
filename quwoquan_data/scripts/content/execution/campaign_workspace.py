"""Content-addressed read-only campaign capsule and isolated lane roots."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid
from core.source_digest import current_source_digest

from content.execution.campaign_external_inputs import (
    external_inputs_digest as refs_digest,
)
from content.execution.campaign_external_inputs import (
    materialize_external_input_bundle,
    payload_digest,
    verify_external_input_refs,
)
from content.execution.campaign_source_snapshot import (
    SNAPSHOT_FORMAT,
    campaign_snapshot_roots,
    materialize_source_snapshot,
)
from content.execution.identity import validate_execution_id

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

    @classmethod
    def defaults(cls) -> CampaignRuntimePaths:
        workspace = paths.DATA_LOCAL_ROOT / "workspace"
        campaigns = workspace / "content-campaign-submissions"
        return cls(
            repo_root=paths.REPO_ROOT.resolve(),
            output_root=paths.OUTPUT_ROOT.resolve(),
            publish_root=paths.PUBLISH_ROOT.resolve(),
            campaigns_root=campaigns.resolve(),
            workspaces_root=(
                paths.DATA_LOCAL_ROOT
                / "cache"
                / "content-campaign-workspaces"
            ).resolve(),
        )


@dataclass(frozen=True, slots=True)
class SourceCapsule:
    path: Path
    ref: str
    capsule_digest: str
    commit_sha: str
    source_revision: str
    source_digest: str
    entity_catalog_digest: str
    external_inputs_digest: str
    lane_external_inputs: dict[str, dict[str, Any]]
    roots: tuple[str, ...]
    read_only: bool

    def external_input_root(self, carrier: str) -> Path:
        lane = self.lane_external_inputs.get(carrier)
        if not isinstance(lane, dict):
            raise TypeError(f"campaign capsule has no {carrier} external input lane")
        relative = Path(str(lane.get("rootRef") or ""))
        root = (self.path / relative).resolve()
        if self.path.resolve() not in root.parents:
            raise ValueError("campaign capsule external input root escapes capsule")
        return root


@dataclass(frozen=True, slots=True)
class CampaignLaneWorkspace:
    carrier: str
    capsule: SourceCapsule
    execution_root: Path

    @property
    def path(self) -> Path:
        return self.capsule.path

    @property
    def ref(self) -> str:
        return self.capsule.ref

    @property
    def commit_sha(self) -> str:
        return self.capsule.commit_sha

    @property
    def source_digest(self) -> str:
        return self.capsule.source_digest

def _git(
    repo_root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=check,
        capture_output=True,
        text=True,
    )


def current_commit(repo_root: Path) -> str:
    return _git(repo_root, "rev-parse", "HEAD").stdout.strip()


def current_branch(repo_root: Path) -> str:
    return _git(repo_root, "branch", "--show-current").stdout.strip()


def require_clean_main_tree(repo_root: Path) -> None:
    """Retained only as an explicit diagnostic, never as campaign admission.

    A shared monorepo is expected to be dirty outside the sourceDigest input
    closure.  Campaign freeze therefore calls :func:`assert_frozen_revision`
    instead of this whole-tree diagnostic.
    """
    dirty = _git(
        repo_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ).stdout.strip()
    if dirty:
        first = dirty.splitlines()[0]
        raise ValueError(
            "campaign main worktree is not globally clean; "
            f"first drift={first}"
        )


def assert_frozen_main_tree(
    repo_root: Path,
    *,
    git_branch: str,
    commit_sha: str,
    source_digest: str,
) -> None:
    """Verify only governed revision inputs, not unrelated monorepo changes."""
    assert_frozen_revision(
        repo_root,
        git_branch=git_branch,
        commit_sha=commit_sha,
        source_digest=source_digest,
    )


def assert_frozen_revision(
    repo_root: Path,
    *,
    git_branch: str,
    commit_sha: str,
    source_digest: str,
) -> None:
    observed_branch = current_branch(repo_root)
    if observed_branch != git_branch:
        raise ValueError(
            "campaign branch drift: "
            f"frozen={git_branch} current={observed_branch}"
        )
    observed_commit = current_commit(repo_root)
    if observed_commit != commit_sha:
        raise ValueError(
            "campaign commit drift: "
            f"frozen={commit_sha} current={observed_commit}"
        )
    observed_digest = current_source_digest(repo_root=repo_root).digest
    if observed_digest != source_digest:
        raise ValueError(
            "campaign sourceDigest drift: "
            f"frozen={source_digest} current={observed_digest}"
        )


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


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _capsule_tree_digest(root: Path) -> str:
    """Verify every exported executor byte, not only sourceDigest inputs."""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == ".qwq_campaign_capsule.json":
            continue
        if path.is_symlink():
            row = f"L\0{relative}\0{os.readlink(path)}\n"
        elif path.is_file():
            executable = path.stat().st_mode & 0o111
            row = f"F\0{relative}\0{executable:o}\0{_file_digest(path)}\n"
        else:
            continue
        digest.update(row.encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def _capsule_identity(
    *,
    commit_sha: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    lane_external_inputs: dict[str, dict[str, Any]],
    external_inputs_digest: str,
    roots: tuple[str, ...],
) -> tuple[dict[str, Any], str]:
    stable = {
        "schema": CAPSULE_SCHEMA,
        "format": CAPSULE_FORMAT,
        "gitCommitSha": commit_sha,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "roots": list(roots),
        "laneExternalInputs": lane_external_inputs,
        "externalInputsDigest": external_inputs_digest,
    }
    return stable, _canonical_digest(stable)


def _make_tree_writable(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        try:
            path.chmod(path.stat().st_mode | 0o700)
        except OSError:
            pass
    try:
        root.chmod(root.stat().st_mode | 0o700)
    except OSError:
        pass


def _remove_tree(root: Path) -> None:
    if not root.exists():
        return
    _make_tree_writable(root)
    shutil.rmtree(root)


def _make_tree_read_only(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod(mode & ~0o222)
    root.chmod(root.stat().st_mode & ~0o222)


def _tree_is_read_only(root: Path) -> bool:
    if root.stat().st_mode & 0o222:
        return False
    for path in root.rglob("*"):
        if not path.is_symlink() and path.stat().st_mode & 0o222:
            return False
    return True


def _load_capsule(
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
    if manifest.get("treeDigest") != _capsule_tree_digest(path):
        raise ValueError("campaign capsule tree digest drift")
    observed_digest = current_source_digest(repo_root=path).digest
    if observed_digest != stable["sourceDigest"]:
        raise ValueError(
            "campaign capsule sourceDigest mismatch: "
            f"{observed_digest} != {stable['sourceDigest']}"
        )
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
    if not _tree_is_read_only(path):
        raise ValueError("campaign capsule must be read-only")
    return SourceCapsule(
        path=path,
        ref=_portable_ref(path, runtime_paths.output_root),
        capsule_digest=capsule_digest,
        commit_sha=str(stable["gitCommitSha"]),
        source_revision=str(stable["sourceRevision"]),
        source_digest=str(stable["sourceDigest"]),
        entity_catalog_digest=str(stable["entityCatalogDigest"]),
        external_inputs_digest=str(stable["externalInputsDigest"]),
        lane_external_inputs={
            str(carrier): dict(lane)
            for carrier, lane in stable["laneExternalInputs"].items()
        },
        roots=tuple(str(item) for item in stable["roots"]),
        read_only=True,
    )


def prepare_source_capsule(
    runtime_paths: CampaignRuntimePaths,
    *,
    commit_sha: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    lane_external_inputs: dict[str, dict[str, Any]],
    external_inputs_digest: str,
) -> SourceCapsule:
    """Export one immutable source tree shared by all four lane processes."""
    if set(lane_external_inputs) != {"homepage", "article", "image", "video"}:
        raise ValueError("campaign capsule requires all four external input lanes")
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
        for carrier in ("homepage", "article", "image", "video")
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
    )
    stable, capsule_digest = _capsule_identity(
        commit_sha=commit_sha,
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
        lane_external_inputs=capsule_lanes,
        external_inputs_digest=external_inputs_digest,
        roots=roots,
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
                return _load_capsule(
                    runtime_paths,
                    capsule_path,
                    stable=stable,
                    capsule_digest=capsule_digest,
                )
            except (OSError, TypeError, ValueError):
                _remove_tree(capsule_path)

        temp_root = Path(
            tempfile.mkdtemp(prefix=f".{key}.", dir=capsules_root)
        )
        try:
            materialize_source_snapshot(
                runtime_paths.repo_root,
                temp_root,
                roots=roots,
                expected_digest=source_digest,
            )
            for carrier, lane in capsule_lanes.items():
                materialize_external_input_bundle(
                    temp_root / str(lane["rootRef"]),
                    lane["externalInputRefs"],
                    acquisition_root=runtime_paths.acquisition_root,
                    carrier=carrier,
                    source_revision=source_revision,
                    source_digest=source_digest,
                    entity_catalog_digest=entity_catalog_digest,
                )
            write_json(
                temp_root / ".qwq_campaign_capsule.json",
                {
                    **stable,
                    "capsuleDigest": capsule_digest,
                    "treeDigest": _capsule_tree_digest(temp_root),
                },
            )
            _make_tree_read_only(temp_root)
            os.replace(temp_root, capsule_path)
        finally:
            if temp_root.exists():
                _remove_tree(temp_root)
        return _load_capsule(
            runtime_paths,
            capsule_path,
            stable=stable,
            capsule_digest=capsule_digest,
        )


def lane_execution_root(
    runtime_paths: CampaignRuntimePaths,
    execution_id: str,
) -> Path:
    root = (
        runtime_paths.output_root
        / "data"
        / "tasks"
        / validate_execution_id(execution_id)
    ).resolve()
    expected_parent = (runtime_paths.output_root / "data" / "tasks").resolve()
    if root.parent != expected_parent:
        raise ValueError("campaign lane execution root escapes output root")
    return root


def prepare_lane_workspace(
    runtime_paths: CampaignRuntimePaths,
    *,
    capsule: SourceCapsule,
    carrier: str,
    execution_id: str,
) -> CampaignLaneWorkspace:
    execution_root = lane_execution_root(runtime_paths, execution_id)
    execution_root.mkdir(parents=True, exist_ok=True)
    if not capsule.path.is_dir() or capsule.path.stat().st_mode & 0o222:
        raise ValueError("campaign capsule became writable")
    return CampaignLaneWorkspace(
        carrier=carrier,
        capsule=capsule,
        execution_root=execution_root,
    )


def release_lane_workspace(workspace: CampaignLaneWorkspace) -> None:
    """Release process ownership without deleting durable execution evidence."""
    if not workspace.execution_root.is_dir():
        raise OSError(
            f"campaign execution root disappeared: {workspace.execution_root}"
        )
    if (
        not workspace.capsule.path.is_dir()
        or workspace.capsule.path.stat().st_mode & 0o222
    ):
        raise OSError(f"campaign capsule is missing or writable: {workspace.path}")


__all__ = [
    "CampaignLaneWorkspace",
    "CampaignRuntimePaths",
    "SourceCapsule",
    "assert_frozen_main_tree",
    "assert_frozen_revision",
    "current_branch",
    "current_commit",
    "lane_execution_root",
    "prepare_lane_workspace",
    "prepare_source_capsule",
    "release_lane_workspace",
    "require_clean_main_tree",
]

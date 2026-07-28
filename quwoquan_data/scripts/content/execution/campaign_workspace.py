"""Frozen main-tree and disposable detached-clone operations for campaigns."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core import paths
from core.source_digest import current_source_digest
from content.execution.identity import validate_execution_id


@dataclass(frozen=True, slots=True)
class CampaignRuntimePaths:
    repo_root: Path
    output_root: Path
    publish_root: Path
    campaigns_root: Path
    workspaces_root: Path

    @classmethod
    def defaults(cls) -> "CampaignRuntimePaths":
        campaigns = paths.DATA_LOCAL_ROOT / "content-campaign-submissions"
        return cls(
            repo_root=paths.REPO_ROOT.resolve(),
            output_root=paths.OUTPUT_ROOT.resolve(),
            publish_root=paths.PUBLISH_ROOT.resolve(),
            campaigns_root=campaigns.resolve(),
            workspaces_root=(
                paths.DATA_LOCAL_ROOT / "content-campaign-workspaces"
            ).resolve(),
        )


@dataclass(frozen=True, slots=True)
class DetachedClone:
    carrier: str
    path: Path
    ref: str
    commit_sha: str
    source_digest: str
    detached: bool


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


def require_clean_main_tree(repo_root: Path) -> None:
    dirty = _git(
        repo_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ).stdout.strip()
    if dirty:
        first = dirty.splitlines()[0]
        raise ValueError(
            "campaign main worktree must be clean before freeze; "
            f"first drift={first}"
        )


def assert_frozen_main_tree(
    repo_root: Path,
    *,
    commit_sha: str,
    source_digest: str,
) -> None:
    require_clean_main_tree(repo_root)
    assert_frozen_revision(
        repo_root,
        commit_sha=commit_sha,
        source_digest=source_digest,
    )


def assert_frozen_revision(
    repo_root: Path,
    *,
    commit_sha: str,
    source_digest: str,
) -> None:
    """Check frozen code inputs even after publish creates intended Git output."""
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


def workspace_path(
    runtime_paths: CampaignRuntimePaths,
    root_execution_id: str,
    carrier: str,
) -> Path:
    return (
        runtime_paths.workspaces_root
        / validate_execution_id(root_execution_id)
        / carrier
    )


def _portable_ref(path: Path, output_root: Path) -> str:
    try:
        return path.relative_to(output_root).as_posix()
    except ValueError:
        return path.as_posix()


def prepare_detached_clone(
    runtime_paths: CampaignRuntimePaths,
    *,
    root_execution_id: str,
    carrier: str,
    commit_sha: str,
    source_digest: str,
) -> DetachedClone:
    workspace = workspace_path(runtime_paths, root_execution_id, carrier)
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "git",
            "clone",
            "--no-hardlinks",
            "--no-checkout",
            str(runtime_paths.repo_root),
            str(workspace),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(workspace, "checkout", "--detach", commit_sha)
    observed_commit = current_commit(workspace)
    if observed_commit != commit_sha:
        raise ValueError(
            f"{carrier} clone commit drift: {observed_commit} != {commit_sha}"
        )
    symbolic = _git(workspace, "symbolic-ref", "-q", "HEAD", check=False)
    detached = symbolic.returncode != 0
    if not detached:
        raise ValueError(f"{carrier} campaign clone must use detached HEAD")
    require_clean_main_tree(workspace)
    observed_digest = current_source_digest(repo_root=workspace).digest
    if observed_digest != source_digest:
        raise ValueError(
            f"{carrier} clone sourceDigest mismatch: "
            f"{observed_digest} != {source_digest}"
        )
    return DetachedClone(
        carrier=carrier,
        path=workspace,
        ref=_portable_ref(workspace, runtime_paths.output_root),
        commit_sha=observed_commit,
        source_digest=observed_digest,
        detached=detached,
    )


def cleanup_clone(clone: DetachedClone) -> None:
    if clone.path.exists():
        shutil.rmtree(clone.path)
    if clone.path.exists():
        raise OSError(f"campaign clone cleanup failed: {clone.path}")


__all__ = [
    "CampaignRuntimePaths",
    "DetachedClone",
    "assert_frozen_main_tree",
    "assert_frozen_revision",
    "cleanup_clone",
    "current_commit",
    "prepare_detached_clone",
    "require_clean_main_tree",
]

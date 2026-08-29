"""Content-addressed read-only campaign capsule and isolated lane roots."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core import paths
from core.source_digest import current_source_definition_snapshot

from content.execution.campaign.source_capsule_store import (
    CAPSULE_FORMAT,
    CAPSULE_SCHEMA,
    CampaignRuntimePaths,
    SourceCapsule,
    _canonical_digest,
    _capsule_identity,
    _portable_ref,
    load_source_capsule_manifest,
    prepare_source_capsule,
)
from content.execution.identity import validate_execution_id


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
    execution_bundle_digest: str,
) -> None:
    """Verify only governed revision inputs, not unrelated monorepo changes."""
    assert_frozen_revision(
        repo_root,
        git_branch=git_branch,
        commit_sha=commit_sha,
        source_digest=source_digest,
        execution_bundle_digest=execution_bundle_digest,
    )


def assert_frozen_revision(
    repo_root: Path,
    *,
    git_branch: str,
    commit_sha: str,
    source_digest: str,
    execution_bundle_digest: str,
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
    observed_digest = current_source_definition_snapshot(repo_root=repo_root).digest
    if observed_digest != source_digest:
        raise ValueError(
            "campaign sourceDigest drift: "
            f"frozen={source_digest} current={observed_digest}"
        )
    from core.source_digest import current_execution_bundle_identity

    observed_bundle = current_execution_bundle_identity(repo_root=repo_root).digest
    if observed_bundle != execution_bundle_digest:
        raise ValueError(
            "campaign execution bundle drift: "
            f"frozen={execution_bundle_digest} current={observed_bundle}"
        )


def audit_frozen_revision(
    repo_root: Path,
    *,
    phase: str,
    git_branch: str,
    commit_sha: str,
    source_digest: str,
    execution_bundle_digest: str,
) -> dict[str, Any]:
    """DEC-030：阶段边界的冻结身份复核。

    只有 gitBranch 保留为执行前置（期望值恒定，验证环境正确性）；
    commit/sourceDigest/executionBundle 三项降为审计记录——漂移不阻断阶段推进，
    观测值与漂移标志由调用方写入 campaign report 的 revisionAudits。
    冻结时点的全量断言仍走 assert_frozen_revision。
    """
    observed_branch = current_branch(repo_root)
    if observed_branch != git_branch:
        raise ValueError(
            "campaign branch drift: "
            f"frozen={git_branch} current={observed_branch}"
        )
    observed_commit = current_commit(repo_root)
    observed_digest = current_source_definition_snapshot(repo_root=repo_root).digest
    from core.source_digest import current_execution_bundle_identity

    observed_bundle = current_execution_bundle_identity(repo_root=repo_root).digest
    from content.execution.campaign.plan_identity import utc_now

    return {
        "phase": phase,
        "observedAt": utc_now(),
        "gitBranch": observed_branch,
        "frozenCommitSha": commit_sha,
        "observedCommitSha": observed_commit,
        "frozenSourceDigest": source_digest,
        "observedSourceDigest": observed_digest,
        "frozenExecutionBundleDigest": execution_bundle_digest,
        "observedExecutionBundleDigest": observed_bundle,
        "drifted": (
            observed_commit != commit_sha
            or observed_digest != source_digest
            or observed_bundle != execution_bundle_digest
        ),
    }


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
    "audit_frozen_revision",
    "current_branch",
    "current_commit",
    "lane_execution_root",
    "load_source_capsule_manifest",
    "prepare_lane_workspace",
    "prepare_source_capsule",
    "release_lane_workspace",
    "require_clean_main_tree",
]

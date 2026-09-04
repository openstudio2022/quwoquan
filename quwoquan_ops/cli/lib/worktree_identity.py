"""Resolve the current Git worktree identity without assuming a clone layout."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorktreeIdentityError(RuntimeError):
    """The requested path cannot be resolved to an unambiguous worktree."""


@dataclass(frozen=True)
class WorktreeIdentity:
    repo_toplevel: str
    worktree_root: str | None
    branch: str
    lane: str
    head_sha: str
    dirty_count: int
    is_integration: bool

    def as_dict(self) -> dict[str, object]:
        """Return the canonical camelCase receipt projection."""
        return {
            "repoToplevel": self.repo_toplevel,
            "worktreeRoot": self.worktree_root,
            "branch": self.branch,
            "lane": self.lane,
            "headSha": self.head_sha,
            "dirtyCount": self.dirty_count,
            "isIntegration": self.is_integration,
        }


def _git(path: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise WorktreeIdentityError(f"cannot execute git for {path}: {error}") from error
    output = result.stdout.strip()
    if result.returncode != 0:
        detail = result.stderr.strip() or output or f"exit={result.returncode}"
        raise WorktreeIdentityError(f"git {' '.join(args)} failed for {path}: {detail}")
    return output



def resolve_worktree_identity(path: Path | str | None = None) -> WorktreeIdentity:
    """Resolve a path inside a linked or ordinary Git worktree.

    A bare common-dir is represented with ``worktree_root=None`` and zero dirty
    entries; linked worktrees resolve to their own toplevel, not the bare hub.
    """
    origin = Path.cwd() if path is None else Path(path).expanduser()
    origin = origin.resolve()
    if origin.is_file():
        origin = origin.parent
    if not origin.is_dir():
        raise WorktreeIdentityError(f"worktree identity path is not a directory: {origin}")

    is_bare = _git(origin, "rev-parse", "--is-bare-repository") == "true"
    repository = (
        Path(_git(origin, "rev-parse", "--absolute-git-dir")).resolve()
        if is_bare
        else Path(_git(origin, "rev-parse", "--show-toplevel")).resolve()
    )
    try:
        branch = _git(repository, "symbolic-ref", "--quiet", "--short", "HEAD")
    except WorktreeIdentityError:
        branch = ""
    head_sha = _git(repository, "rev-parse", "HEAD")
    if is_bare:
        worktree_root = None
        dirty_count = 0
    else:
        worktree_root = str(repository)
        status = _git(
            repository, "status", "--porcelain=v1", "--untracked-files=all"
        )
        dirty_count = len([line for line in status.splitlines() if line.strip()])
    lane = branch or f"detached@{head_sha[:12]}"
    is_integration = not is_bare and (
        branch == "dev1.0" or repository.name == "integration"
    )

    return WorktreeIdentity(
        repo_toplevel=str(repository),
        worktree_root=worktree_root,
        branch=branch,
        lane=lane,
        head_sha=head_sha,
        dirty_count=dirty_count,
        is_integration=is_integration,
    )

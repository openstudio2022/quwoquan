# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001
"""integration 预检只拦 HEAD...candidate 重叠脏文件。"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.cli.integration_run_acceptance import preflight_identity
from quwoquan_ops.cli.integration_run_bundle import IntegrationRunError
from quwoquan_ops.cli.lib.dirty_worktree import overlapping_dirty_paths, parse_porcelain_z


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise IntegrationRunError("INTEGRATION_RUN.GIT", completed.stderr or completed.stdout)
    return completed.stdout.rstrip("\n\r")


def make_repo(tmp_path: Path) -> tuple[Path, str, str]:
    target = tmp_path / "integration"
    remote = tmp_path / "hub.git"
    target.mkdir()
    git(target, "init", "-b", "dev1.0")
    git(target, "config", "user.name", "Test")
    git(target, "config", "user.email", "test@example.com")
    (target / "owned.txt").write_text("before\n")
    (target / "other.txt").write_text("other\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "parent")
    parent = git(target, "rev-parse", "HEAD")
    git(tmp_path, "init", "--bare", "-b", "dev1.0", str(remote))
    git(target, "remote", "add", "origin", str(remote))
    git(target, "push", "-q", "origin", "dev1.0")
    (target / "owned.txt").write_text("after\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "candidate")
    commit = git(target, "rev-parse", "HEAD")
    git(target, "reset", "--hard", parent)
    return target, parent, commit


def bind_git(repo: Path):
    def runner(*args: str) -> str:
        return git(repo, *args)

    def is_ancestor(parent: str, commit: str) -> bool:
        return subprocess.run(
            ["git", "merge-base", "--is-ancestor", parent, commit], cwd=repo, check=False,
        ).returncode == 0

    return runner, is_ancestor


def args_for(commit: str) -> argparse.Namespace:
    return argparse.Namespace(
        candidate=commit, remote="origin", baseline=None, mode="integrate", validate_bundle_only=True,
    )


def test_overlapping_dirty_paths_include_parent_child() -> None:
    assert overlapping_dirty_paths(["gamma/wip.txt"], ["owned.txt"]) == ()
    assert overlapping_dirty_paths(["owned.txt"], ["owned.txt"]) == ("owned.txt",)
    assert overlapping_dirty_paths(["dir/file.txt"], ["dir"]) == ("dir/file.txt",)
    assert parse_porcelain_z(" M owned.txt\0?? gamma.txt\0") == ("owned.txt", "gamma.txt")


def test_preflight_allows_non_overlapping_dirty_and_untracked(tmp_path: Path) -> None:
    target, _parent, commit = make_repo(tmp_path)
    (target / "other.txt").write_text("dirty other\n")
    (target / "gamma.wip").write_text("untracked\n")
    runner, is_ancestor = bind_git(target)
    identity = preflight_identity(args_for(commit), git=runner, is_ancestor=is_ancestor)
    assert identity["commit"] == commit
    assert identity["parent"] == git(target, "rev-parse", "HEAD")


def test_preflight_blocks_overlapping_dirty_path(tmp_path: Path) -> None:
    target, _parent, commit = make_repo(tmp_path)
    (target / "owned.txt").write_text("dirty overlap\n")
    runner, is_ancestor = bind_git(target)
    with pytest.raises(IntegrationRunError, match="DIRTY_WORKTREE"):
        preflight_identity(args_for(commit), git=runner, is_ancestor=is_ancestor)


def test_preflight_blocks_overlapping_untracked_path(tmp_path: Path) -> None:
    target, parent, commit = make_repo(tmp_path)
    git(target, "reset", "--hard", commit)
    (target / "added.txt").write_text("in candidate\n")
    git(target, "add", ".")
    git(target, "commit", "-m", "add path")
    added = git(target, "rev-parse", "HEAD")
    git(target, "reset", "--hard", parent)
    (target / "added.txt").write_text("untracked overlap\n")
    runner, is_ancestor = bind_git(target)
    with pytest.raises(IntegrationRunError, match="DIRTY_WORKTREE"):
        preflight_identity(args_for(added), git=runner, is_ancestor=is_ancestor)

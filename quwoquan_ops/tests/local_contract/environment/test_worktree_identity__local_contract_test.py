from __future__ import annotations

import subprocess
from pathlib import Path

from quwoquan_ops.cli.lib.worktree_identity import resolve_worktree_identity


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(path: Path) -> str:
    _git(path, "config", "user.email", "local-contract@example.invalid")
    _git(path, "config", "user.name", "Local Contract")
    (path / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _git(path, "add", "tracked.txt")
    _git(path, "commit", "-m", "baseline")
    return _git(path, "rev-parse", "HEAD")


def test_resolves_linked_lane_worktree_from_nested_path(tmp_path: Path) -> None:
    hub = tmp_path / "hub.git"
    source = tmp_path / "source"
    linked = tmp_path / "ops"
    _git(tmp_path, "init", "--bare", str(hub))
    _git(tmp_path, "clone", str(hub), str(source))
    head = _commit(source)
    _git(source, "push", "origin", "HEAD:dev1.0")
    _git(source, "branch", "lane/ops")
    _git(source, "worktree", "add", str(linked), "lane/ops")
    nested = linked / "nested"
    nested.mkdir()
    (linked / "untracked one.txt").write_text("dirty\n", encoding="utf-8")

    identity = resolve_worktree_identity(nested)

    assert identity.repo_toplevel == str(linked.resolve())
    assert identity.worktree_root == str(linked.resolve())
    assert identity.branch == "lane/ops"
    assert identity.lane == "lane/ops"
    assert identity.head_sha == head
    assert identity.dirty_count == 1
    assert identity.is_integration is False
    assert identity.as_dict()["worktreeRoot"] == str(linked.resolve())


def test_bare_hub_has_repo_identity_without_a_worktree(tmp_path: Path) -> None:
    hub = tmp_path / "hub.git"
    source = tmp_path / "source"
    _git(tmp_path, "init", "--bare", str(hub))
    _git(tmp_path, "clone", str(hub), str(source))
    head = _commit(source)
    _git(source, "push", "origin", "HEAD:main")
    _git(hub, "symbolic-ref", "HEAD", "refs/heads/main")

    identity = resolve_worktree_identity(hub)

    assert identity.repo_toplevel == str(hub.resolve())
    assert identity.worktree_root is None
    assert identity.branch == "main"
    assert identity.lane == "main"
    assert identity.head_sha == head
    assert identity.dirty_count == 0
    assert identity.is_integration is False


def test_dev1_branch_is_integration_even_outside_named_directory(tmp_path: Path) -> None:
    repository = tmp_path / "runtime-host"
    _git(tmp_path, "init", "-b", "dev1.0", str(repository))
    head = _commit(repository)

    identity = resolve_worktree_identity(repository)

    assert identity.branch == "dev1.0"
    assert identity.lane == "dev1.0"
    assert identity.head_sha == head
    assert identity.dirty_count == 0
    assert identity.is_integration is True


def test_detached_checkout_retains_host_lock_identity(tmp_path: Path) -> None:
    repository = tmp_path / "detached-runner"
    _git(tmp_path, "init", "-b", "lane/small-fix", str(repository))
    head = _commit(repository)
    _git(repository, "checkout", "--detach", head)

    identity = resolve_worktree_identity(repository)

    assert identity.branch == ""
    assert identity.lane == f"detached@{head[:12]}"
    assert identity.head_sha == head
    assert identity.worktree_root == str(repository.resolve())
    assert identity.is_integration is False

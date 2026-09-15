# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002
"""执行真实 Make recipe，证明本地回同步不再承担远端发布。"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=contract", "-c", "user.email=contract@example.invalid",
         "-c", "commit.gpgsign=false", *args], cwd=path, check=True,
        text=True, capture_output=True,
    ).stdout.strip()


def commit(path: Path, name: str) -> str:
    (path / name).write_text(name + "\n", encoding="utf-8")
    git(path, "add", name)
    git(path, "commit", "-qm", name)
    return git(path, "rev-parse", "HEAD")


@pytest.fixture
def repositories(tmp_path: Path) -> tuple[Path, Path, str, str]:
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, "init", "--bare", "-q", "-b", "dev1.0")
    local = tmp_path / "integration"
    local.mkdir()
    git(local, "init", "-q", "-b", "dev1.0")
    before = commit(local, "base.txt")
    git(local, "remote", "add", "origin", str(origin))
    git(local, "push", "-q", "origin", "dev1.0", "dev1.0:main")
    # 本地仅有旧 dev，main 的新对象通过 fetch 读取。
    producer = tmp_path / "producer"
    producer.mkdir()
    git(producer, "init", "-q", "-b", "main")
    git(producer, "remote", "add", "origin", str(origin))
    git(producer, "fetch", "-q", "origin", "main")
    git(producer, "reset", "--hard", "FETCH_HEAD")
    after = commit(producer, "promoted.txt")
    git(producer, "push", "-q", "origin", "main")
    return local, origin, before, after


def run_recipe(local: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        env.pop(key, None)
    return subprocess.run(
        ["make", "-f", str(ROOT / "Makefile"), "promotion-backsync"],
        cwd=local, env=env, text=True, capture_output=True, check=False,
    )


def test_unfinished_system_backsync_preserves_local_and_remote(repositories) -> None:
    local, origin, before, after = repositories
    result = run_recipe(local)
    assert result.returncode != 0
    assert "受管 system-backsync" in result.stderr
    assert git(local, "rev-parse", "HEAD") == before
    assert git(origin, "rev-parse", "dev1.0") == before
    assert git(origin, "rev-parse", "main") == after


def test_finished_system_backsync_only_fast_forwards_local_and_is_idempotent(repositories) -> None:
    local, origin, before, after = repositories
    git(origin, "update-ref", "refs/heads/dev1.0", after, before)
    before_refs = git(origin, "show-ref")
    for _ in range(2):
        result = run_recipe(local)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "local-only" in result.stdout
        assert git(local, "rev-parse", "HEAD") == after
        assert git(origin, "show-ref") == before_refs


def test_local_divergence_is_not_reset_or_merged(repositories) -> None:
    local, origin, before, after = repositories
    git(origin, "update-ref", "refs/heads/dev1.0", after, before)
    own_head = commit(local, "own.txt")
    result = run_recipe(local)
    assert result.returncode != 0
    assert "已分叉" in result.stderr
    assert git(local, "rev-parse", "HEAD") == own_head
    assert git(origin, "rev-parse", "dev1.0") == after


def test_untracked_work_is_preserved_before_any_fetch(repositories) -> None:
    local, origin, before, after = repositories
    git(origin, "update-ref", "refs/heads/dev1.0", after, before)
    (local / "untracked.txt").write_text("WIP", encoding="utf-8")
    result = run_recipe(local)
    assert result.returncode != 0
    assert "工作树必须干净" in result.stderr
    assert git(local, "rev-parse", "HEAD") == before
    assert (local / "untracked.txt").read_text(encoding="utf-8") == "WIP"

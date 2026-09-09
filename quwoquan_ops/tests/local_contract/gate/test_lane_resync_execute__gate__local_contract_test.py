# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-005.t1
"""lane 回同步执行面的三态零写合同。

回同步只对「无进行中 merge、干净或脏文件与 ff 不重叠、且是 dev1.0 祖先」的 lane 移动 ref；
分叉、重叠脏树与进行中 merge 的 lane 必须 HEAD/index/工作树字节零变化并给出 typed 结果。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
extra = ROOT / "quwoquan_ops/cli/lib"
if str(extra) not in sys.path:
    sys.path.insert(0, str(extra))

import local_worktree_inventory as inventory  # noqa: E402
from quwoquan_ops.cli import lane_worktree_commands  # noqa: E402

DEV = "dev1.0"


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _commit(worktree: Path, name: str, content: str, message: str) -> str:
    (worktree / name).write_text(content, encoding="utf-8")
    _git(worktree, "add", name)
    _git(worktree, "commit", "-qm", message)
    return _git(worktree, "rev-parse", "HEAD")


@pytest.fixture
def hub(tmp_path: Path) -> dict[str, Path]:
    """bare hub + integration worktree(dev1.0) + 一条 lane worktree，lane 落后 dev1.0 一个提交。"""
    project = tmp_path / "project"
    project.mkdir()
    bare = project / "hub.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", DEV, str(bare)], check=True, capture_output=True)
    integration = project / "integration"
    _git(bare, "worktree", "add", "-q", "--orphan", "-b", DEV, str(integration))
    _commit(integration, "base.txt", "base\n", "base")
    lane = project / "engineering"
    _git(bare, "worktree", "add", "-q", "-b", "lane/engineering", str(lane), DEV)
    _commit(integration, "shared.txt", "v2\n", "dev1.0 advances")
    return {"bare": bare, "integration": integration, "lane": lane}


def _resync(lane: Path, *, push: bool = False) -> lane_worktree_commands.LaneResyncResult:
    return lane_worktree_commands.resync_lane(
        branch="lane/engineering", path=lane, target_branch=DEV, push=push
    )


def test_clean_ancestor_lane_is_fast_forwarded(hub) -> None:
    target = _git(hub["integration"], "rev-parse", "HEAD")
    before = _git(hub["lane"], "rev-parse", "HEAD")
    assert before != target

    result = _resync(hub["lane"])

    assert result.outcome == "ff_done"
    assert result.before == before and result.after == target and result.pushed is False
    assert _git(hub["lane"], "rev-parse", "HEAD") == target
    assert (hub["lane"] / "shared.txt").read_text(encoding="utf-8") == "v2\n"


def test_dirty_but_non_overlapping_lane_is_fast_forwarded_and_keeps_dirty_bytes(hub) -> None:
    (hub["lane"] / "wip.txt").write_text("wip\n", encoding="utf-8")
    (hub["lane"] / "base.txt").write_text("edited locally\n", encoding="utf-8")

    result = _resync(hub["lane"])

    assert result.outcome == "ff_done"
    assert _git(hub["lane"], "rev-parse", "HEAD") == result.target
    assert (hub["lane"] / "wip.txt").read_text(encoding="utf-8") == "wip\n"
    assert (hub["lane"] / "base.txt").read_text(encoding="utf-8") == "edited locally\n"


def test_dirty_overlap_is_zero_write_and_typed(hub) -> None:
    (hub["lane"] / "shared.txt").write_text("local conflicting edit\n", encoding="utf-8")
    before = _git(hub["lane"], "rev-parse", "HEAD")

    result = _resync(hub["lane"])

    assert result.outcome == "skipped_dirty_overlap"
    assert result.overlap == ("shared.txt",)
    assert _git(hub["lane"], "rev-parse", "HEAD") == before
    assert (hub["lane"] / "shared.txt").read_text(encoding="utf-8") == "local conflicting edit\n"
    assert _git(hub["lane"], "status", "--porcelain") == "?? shared.txt" or "shared.txt" in _git(hub["lane"], "status", "--porcelain")


def test_diverged_lane_is_zero_write_and_typed(hub) -> None:
    before = _commit(hub["lane"], "lane-only.txt", "lane\n", "lane-only commit")

    result = _resync(hub["lane"])

    assert result.outcome == "skipped_diverged"
    assert result.before == before and result.after == ""
    assert _git(hub["lane"], "rev-parse", "HEAD") == before


def test_in_progress_merge_is_zero_write_and_typed(hub) -> None:
    git_dir = Path(_git(hub["lane"], "rev-parse", "--git-dir"))
    if not git_dir.is_absolute():
        git_dir = hub["lane"] / git_dir
    (git_dir / "MERGE_HEAD").write_text(_git(hub["integration"], "rev-parse", "HEAD") + "\n", encoding="utf-8")
    before = _git(hub["lane"], "rev-parse", "HEAD")

    result = _resync(hub["lane"])

    assert result.outcome == "skipped_in_progress"
    assert _git(hub["lane"], "rev-parse", "HEAD") == before


def test_already_current_lane_reports_ff_done_without_movement(hub) -> None:
    _git(hub["lane"], "merge", "--ff-only", DEV)
    head = _git(hub["lane"], "rev-parse", "HEAD")

    result = _resync(hub["lane"])

    assert result.outcome == "ff_done" and result.before == result.after == head
    assert result.detail == "already at target"


def test_missing_or_wrong_branch_worktree_is_skipped(hub, tmp_path: Path) -> None:
    missing = lane_worktree_commands.resync_lane(
        branch="lane/ops", path=tmp_path / "absent", target_branch=DEV, push=False
    )
    assert missing.outcome == "skipped_missing"
    wrong = lane_worktree_commands.resync_lane(
        branch="lane/ops", path=hub["lane"], target_branch=DEV, push=False
    )
    assert wrong.outcome == "skipped_missing" and "lane/engineering" in wrong.detail


def test_push_updates_same_named_remote_lane_only(hub, tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", DEV, str(origin)], check=True, capture_output=True)
    _git(hub["lane"], "remote", "add", "origin", str(origin))
    _git(hub["lane"], "push", "-q", "origin", "refs/heads/lane/engineering:refs/heads/lane/engineering")

    result = _resync(hub["lane"], push=True)

    assert result.outcome == "ff_done" and result.pushed is True
    remote_heads = _git(origin, "for-each-ref", "--format=%(refname)").splitlines()
    assert remote_heads == ["refs/heads/lane/engineering"], "回同步只推同名 lane，不写 dev1.0/main"
    assert _git(origin, "rev-parse", "refs/heads/lane/engineering") == result.after


def test_execute_resync_covers_every_fixed_lane_and_outcomes_are_closed(hub, monkeypatch: pytest.MonkeyPatch) -> None:
    policy = inventory.load_policy()
    test_policy = inventory.WorktreePolicy(**{**vars(policy), "project_root": str(hub["bare"].parent)})

    results = lane_worktree_commands.execute_resync(
        policy=test_policy, project_root=hub["bare"].parent, push=False
    )

    assert [item.branch for item in results] == [branch for branch, _ in policy.lane_worktree_directories]
    assert all(item.outcome in lane_worktree_commands.RESYNC_OUTCOMES for item in results)
    by_branch = {item.branch: item for item in results}
    assert by_branch["lane/engineering"].outcome == "ff_done"
    assert all(item.outcome == "skipped_missing" for name, item in by_branch.items() if name != "lane/engineering")


def test_render_mode_never_moves_refs(hub) -> None:
    before = _git(hub["lane"], "rev-parse", "HEAD")
    commands = lane_worktree_commands.render("resync")
    assert len(commands) == 6 and all("merge --ff-only dev1.0" in command for command in commands)
    assert _git(hub["lane"], "rev-parse", "HEAD") == before

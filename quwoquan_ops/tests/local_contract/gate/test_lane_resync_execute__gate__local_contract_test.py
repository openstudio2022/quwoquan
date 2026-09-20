# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-005.t1
"""回同步绑定一轮冻结的已发布 origin/dev1.0；跳过路径保持 HEAD/index/WIP 零写。"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
extra = ROOT / "quwoquan_ops/cli/lib"
if str(extra) not in sys.path:
    sys.path.insert(0, str(extra))

import local_worktree_inventory as inventory  # noqa: E402
from quwoquan_ops.cli import lane_worktree_commands  # noqa: E402

DEV = "dev1.0"
PUBLISHED = f"refs/remotes/origin/{DEV}"


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "-c", "commit.gpgsign=false", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    )
    return completed.stdout.strip()


def _commit(worktree: Path, name: str, content: str, message: str) -> str:
    (worktree / name).write_text(content, encoding="utf-8")
    _git(worktree, "add", name)
    _git(worktree, "commit", "-qm", message)
    return _git(worktree, "rev-parse", "HEAD")


@pytest.fixture
def hub(tmp_path: Path) -> dict[str, Path]:
    """临时 bare hub + integration + lane，published dev 比 lane 领先一提交。"""
    project = tmp_path / "project"
    project.mkdir()
    bare = project / "hub.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", DEV, str(bare)], check=True, capture_output=True)
    integration = project / "integration"
    _git(bare, "worktree", "add", "-q", "--orphan", "-b", DEV, str(integration))
    _commit(integration, "base.txt", "base\n", "base")
    lane = project / "engineering"
    _git(bare, "worktree", "add", "-q", "-b", "lane/engineering", str(lane), DEV)
    published = _commit(integration, "shared.txt", "v2\n", "published dev advances")
    _git(bare, "update-ref", PUBLISHED, published)
    return {"bare": bare, "integration": integration, "lane": lane}


def _policy(hub):
    return replace(inventory.load_policy(), project_root=str(hub["bare"].parent), bare_hub_directory="hub.git")


def _resync(lane: Path) -> lane_worktree_commands.LaneResyncResult:
    return lane_worktree_commands.resync_lane(
        branch="lane/engineering", path=lane, target_sha=_git(lane, "rev-parse", PUBLISHED),
    )


def _snapshot(lane: Path) -> tuple[str, bytes, dict[str, bytes]]:
    index = Path(_git(lane, "rev-parse", "--git-path", "index"))
    if not index.is_absolute():
        index = lane / index
    return (_git(lane, "rev-parse", "HEAD"), index.read_bytes(),
            {path.relative_to(lane).as_posix(): path.read_bytes() for path in lane.rglob("*") if path.is_file()})


def test_clean_ancestor_lane_is_fast_forwarded(hub) -> None:
    target = _git(hub["bare"], "rev-parse", PUBLISHED)
    before = _git(hub["lane"], "rev-parse", "HEAD")
    result = _resync(hub["lane"])
    assert before != target
    assert result.outcome == "ff_done"
    assert result.before == before and result.after == target
    assert _git(hub["lane"], "rev-parse", "HEAD") == target
    assert (hub["lane"] / "shared.txt").read_text(encoding="utf-8") == "v2\n"
    assert "pushed" not in result.as_dict()


def test_dirty_but_non_overlapping_lane_is_fast_forwarded_and_keeps_dirty_bytes(hub) -> None:
    (hub["lane"] / "wip.txt").write_text("wip\n", encoding="utf-8")
    (hub["lane"] / "base.txt").write_text("edited locally\n", encoding="utf-8")
    result = _resync(hub["lane"])
    assert result.outcome == "ff_done"
    assert _git(hub["lane"], "rev-parse", "HEAD") == result.target
    assert (hub["lane"] / "wip.txt").read_text(encoding="utf-8") == "wip\n"
    assert (hub["lane"] / "base.txt").read_text(encoding="utf-8") == "edited locally\n"


@pytest.mark.parametrize("state,expected", [
    ("overlap", "skipped_dirty_overlap"), ("diverged", "skipped_diverged"),
    ("MERGE_HEAD", "skipped_in_progress"), ("CHERRY_PICK_HEAD", "skipped_in_progress"),
    ("REVERT_HEAD", "skipped_in_progress"), ("rebase-merge", "skipped_in_progress"),
    ("rebase-apply", "skipped_in_progress"),
])
def test_skipped_lane_keeps_head_index_and_all_worktree_bytes(hub, state, expected) -> None:
    lane = hub["lane"]
    if state == "overlap":
        (lane / "shared.txt").write_text("local conflicting edit\n", encoding="utf-8")
    elif state == "diverged":
        _commit(lane, "lane-only.txt", "lane\n", "unpublished lane")
    else:
        marker = Path(_git(lane, "rev-parse", "--git-path", state))
        if state.startswith("rebase-"):
            marker.mkdir()
        else:
            marker.write_text(_git(hub["bare"], "rev-parse", PUBLISHED) + "\n", encoding="utf-8")
    (lane / "staged.txt").write_text("staged WIP\n", encoding="utf-8")
    _git(lane, "add", "staged.txt")
    before = _snapshot(lane)
    result = _resync(lane)
    assert result.outcome == expected
    assert _snapshot(lane) == before
    if state == "overlap":
        assert result.overlap == ("shared.txt",)


def _align(hub, lane: Path, *, merge_authorized: bool = False) -> dict[str, object]:
    return lane_worktree_commands.align_published(
        worktree=lane, merge_authorized=merge_authorized, policy=_policy(hub),
        project_root=hub["bare"].parent, fetch=False,
    )


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-005.t1
def test_align_published_covers_behind_ahead_and_diverged(hub) -> None:
    lane, target = hub["lane"], _git(hub["bare"], "rev-parse", PUBLISHED)
    behind = _align(hub, lane)
    assert (behind["outcome"], behind["after"]) == ("ff_done", target)
    # 已含已发布 SHA 是常态，不是错误，也不再移动 ref。
    ahead_head = _commit(lane, "lane-only.txt", "lane\n", "new lane commit")
    ahead = _align(hub, lane)
    assert (ahead["outcome"], ahead["after"]) == ("ahead", ahead_head)
    assert _git(lane, "rev-parse", "HEAD") == ahead_head


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-005.t1
@pytest.mark.parametrize("authorized", [False, True])
def test_align_published_diverged_requires_authorization_and_stays_zero_write_on_conflict(hub, authorized) -> None:
    lane = hub["lane"]
    _commit(lane, "shared.txt", "lane conflicting\n", "lane touches the same path")
    before = _snapshot(lane)
    result = _align(hub, lane, merge_authorized=authorized)
    assert result["outcome"] == ("merge_conflict" if authorized else "skipped_diverged")
    assert _snapshot(lane) == before


# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-005.t1
def test_align_published_merges_authorized_divergence_without_touching_other_lanes(hub) -> None:
    lane = hub["lane"]
    lane_head = _commit(lane, "lane-only.txt", "lane\n", "unpublished lane work")
    integration_before = _snapshot(hub["integration"])
    result = _align(hub, lane, merge_authorized=True)
    assert result["outcome"] == "merged"
    assert _git(lane, "rev-parse", "HEAD") not in {lane_head, result["target"]}
    assert _git(lane, "merge-base", "--is-ancestor", str(result["target"]), "HEAD") == ""
    assert _snapshot(hub["integration"]) == integration_before


@pytest.mark.parametrize("name", ["空 格.txt", " leading.txt", "new\nline.txt", "shared.txt/nested.txt"])
def test_untracked_overlap_handles_exact_names_and_parent_paths(hub, name) -> None:
    if "/" not in name:
        target = _commit(hub["integration"], name, "published\n", "published unusual path")
        _git(hub["bare"], "update-ref", PUBLISHED, target)
    local = hub["lane"] / name
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("local WIP\n", encoding="utf-8")
    before = _snapshot(hub["lane"])
    result = _resync(hub["lane"])
    assert result.outcome == "skipped_dirty_overlap"
    assert name in result.overlap
    assert _snapshot(hub["lane"]) == before


def test_staged_rename_source_overlap_is_zero_write(hub) -> None:
    target = _commit(hub["integration"], "base.txt", "published edit\n", "base edit")
    _git(hub["bare"], "update-ref", PUBLISHED, target)
    _git(hub["lane"], "mv", "base.txt", "renamed.txt")
    before = _snapshot(hub["lane"])
    result = _resync(hub["lane"])
    assert result.outcome == "skipped_dirty_overlap" and "base.txt" in result.overlap
    assert _snapshot(hub["lane"]) == before


def test_already_current_lane_reports_ff_done_without_movement(hub) -> None:
    _git(hub["lane"], "merge", "--ff-only", PUBLISHED)
    before = _snapshot(hub["lane"])
    result = _resync(hub["lane"])
    assert result.outcome == "ff_done" and result.before == result.after == before[0]
    assert result.detail == "already at target"
    assert _snapshot(hub["lane"]) == before


def test_missing_or_wrong_branch_worktree_is_zero_write(hub, tmp_path: Path) -> None:
    target = _git(hub["bare"], "rev-parse", PUBLISHED)
    before = _snapshot(hub["lane"])
    missing = lane_worktree_commands.resync_lane(branch="lane/ops", path=tmp_path / "absent", target_sha=target)
    wrong = lane_worktree_commands.resync_lane(branch="lane/ops", path=hub["lane"], target_sha=target)
    assert missing.outcome == wrong.outcome == "skipped_missing"
    assert "lane/engineering" in wrong.detail
    assert not (tmp_path / "absent").exists()
    assert _snapshot(hub["lane"]) == before


def test_local_unpublished_dev_is_not_propagated(hub) -> None:
    published = _git(hub["bare"], "rev-parse", PUBLISHED)
    unpublished = _commit(hub["integration"], "secret-wip.txt", "unpublished\n", "local dev only")
    results = lane_worktree_commands.execute_resync(policy=_policy(hub), project_root=hub["bare"].parent)
    assert {item.target for item in results} == {published}
    assert _git(hub["lane"], "rev-parse", "HEAD") == published != unpublished
    assert not (hub["lane"] / "secret-wip.txt").exists()


def test_remote_ahead_of_local_dev_is_used(hub) -> None:
    local = _git(hub["integration"], "rev-parse", "HEAD")
    published = _git(hub["bare"], "commit-tree", f"{local}^{{tree}}", "-p", local, "-m", "remote ahead")
    _git(hub["bare"], "update-ref", PUBLISHED, published)
    results = lane_worktree_commands.execute_resync(policy=_policy(hub), project_root=hub["bare"].parent)
    assert {item.target for item in results} == {published}
    assert _git(hub["lane"], "rev-parse", "HEAD") == published
    assert _git(hub["integration"], "rev-parse", "HEAD") == local


@pytest.mark.parametrize("mode", ["render", "execute"])
def test_published_target_is_frozen_once_for_all_six_lanes(hub, mode) -> None:
    policy = _policy(hub)
    root = hub["bare"].parent
    published = _git(hub["bare"], "rev-parse", PUBLISHED)
    advanced = _commit(hub["integration"], "later.txt", "later\n", "later published commit")
    for branch, directory in policy.lane_worktree_directories:
        if branch != "lane/engineering":
            _git(hub["bare"], "worktree", "add", "-q", "-b", branch, str(root / directory), "lane/engineering")
    snapshots = {directory: _snapshot(root / directory) for _, directory in policy.lane_worktree_directories}
    resolutions = []

    def moving_remote(cwd, *args):
        result = lane_worktree_commands._git(cwd, *args)
        if f"{PUBLISHED}^{{commit}}" in args:
            resolutions.append(result[1])
            _git(hub["bare"], "update-ref", PUBLISHED, advanced)
        return result

    if mode == "render":
        commands = lane_worktree_commands.render("resync", policy=policy, project_root=root, git=moving_remote)
        assert len(commands) == 6 and all(command.endswith(f"merge --ff-only {published}") for command in commands)
        assert {directory: _snapshot(root / directory) for _, directory in policy.lane_worktree_directories} == snapshots
    else:
        results = lane_worktree_commands.execute_resync(policy=policy, project_root=root, git=moving_remote)
        assert len(results) == 6
        assert {item.target for item in results} == {published}
        assert all(item.outcome == "ff_done" and item.after == published for item in results)
    assert resolutions == [published]


def test_missing_remote_ref_never_falls_back_to_local_dev(hub) -> None:
    _git(hub["bare"], "update-ref", "-d", PUBLISHED)
    before = _snapshot(hub["lane"])
    results = lane_worktree_commands.execute_resync(policy=_policy(hub), project_root=hub["bare"].parent)
    assert len(results) == 6 and all(item.outcome == "skipped_missing" and not item.target for item in results)
    with pytest.raises(RuntimeError, match="published origin/dev1.0"):
        lane_worktree_commands.render("resync", policy=_policy(hub), project_root=hub["bare"].parent)
    assert _snapshot(hub["lane"]) == before


@pytest.mark.parametrize("retired", ["--push", "--no-push"])
def test_retired_cli_arguments_fail_before_any_git_operation(hub, monkeypatch, retired) -> None:
    before = _snapshot(hub["lane"])
    monkeypatch.setattr(lane_worktree_commands, "execute_resync", lambda **_: pytest.fail("must reject before execute"))
    monkeypatch.setattr(lane_worktree_commands, "render", lambda *_: pytest.fail("must reject before render"))
    with pytest.raises(SystemExit) as error:
        lane_worktree_commands.main(["resync", "--execute", retired])
    assert error.value.code == 2
    assert _snapshot(hub["lane"]) == before


def test_execute_resync_covers_closed_outcomes_without_push(hub) -> None:
    policy = _policy(hub)
    results = lane_worktree_commands.execute_resync(policy=policy, project_root=hub["bare"].parent)
    assert [item.branch for item in results] == [branch for branch, _ in policy.lane_worktree_directories]
    assert all(item.outcome in lane_worktree_commands.RESYNC_OUTCOMES for item in results)
    assert "push_failed" not in lane_worktree_commands.RESYNC_OUTCOMES
    assert next(item for item in results if item.branch == "lane/engineering").outcome == "ff_done"
    assert all(item.outcome == "skipped_missing" for item in results if item.branch != "lane/engineering")


def test_resync_execute_exits_zero_unless_ff_failed(monkeypatch, capsys) -> None:
    skipped = [lane_worktree_commands.LaneResyncResult(
        branch="lane/engineering", path="/tmp/engineering", outcome="skipped_dirty_overlap", target="a" * 40,
    )]
    failed = [lane_worktree_commands.LaneResyncResult(
        branch="lane/engineering", path="/tmp/engineering", outcome="ff_failed", target="a" * 40,
    )]
    monkeypatch.setattr(lane_worktree_commands, "execute_resync", lambda: skipped)
    assert lane_worktree_commands.main(["resync", "--execute"]) == 0
    monkeypatch.setattr(lane_worktree_commands, "execute_resync", lambda: failed)
    assert lane_worktree_commands.main(["resync", "--execute"]) == 1
    capsys.readouterr()


def test_skill_metadata_body_and_execution_share_published_baseline() -> None:
    skills = ROOT / ".agents/skills"
    for name in ("sync-lane-from-dev", "integrate-lane-to-dev"):
        text = (skills / name / "SKILL.md").read_text(encoding="utf-8")
        metadata, body = text.split("---", 2)[1:]
        assert "origin/dev1.0" in metadata and "frozen after fetch" in metadata
        assert "refs/remotes/origin/dev1.0^{commit}" in body
        assert "published_sha" in body and "POST" not in metadata
        assert "source-only" not in text and "push_failed" not in text
        assert "git merge --ff-only dev1.0" not in text
        assert "git diff --name-only HEAD dev1.0" not in text
    integrate = (skills / "integrate-lane-to-dev/SKILL.md").read_text(encoding="utf-8")
    # 一次任务闭环：PRE 身份在前，一条 make accept PUBLISH=1 发布，不再有换工作区与二次入口停点。
    assert integrate.index("make feature-context TARGET=<exact-path>") < integrate.index("make accept PUBLISH=1")
    assert "仅 readback 为 `after` 后" in integrate
    assert "expectedParent...candidate" in integrate
    # 同步不是发布的隐式前置；保留显式 bundle 消费的等价受管入口。
    assert "make accept PUBLISH=1 SYNC=1" not in integrate
    assert "INTEGRATE_ARGS=--validate-bundle-only" in integrate
    assert "git merge --ff-only <exact-candidate-sha>" in integrate
    assert "消费他树 bundle" in integrate
    assert "Gamma → `IntegrationQualificationFact` → `dev1.0 → main`" in integrate
    assert "可选报告" in integrate and "skipped_*" in integrate
    assert "source-admitted" in integrate
    sync = (skills / "sync-lane-from-dev/SKILL.md").read_text(encoding="utf-8")
    assert "分叉默认停止" in sync and "明确授权" in sync

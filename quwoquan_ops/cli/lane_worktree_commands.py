#!/usr/bin/env python3
"""六 lane bootstrap/resync：默认只渲染命令；`resync --execute` 按 branch policy 的
`persistent_lane_admission.resync_scope` 执行 ff-only 回同步并输出每条 lane 的 typed 结果。

行为语义归属：
`specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md`
REQ-002 与 GWT-005。回同步只对「无进行中 merge/rebase、工作树干净或脏文件与本次 ff
不重叠、且是新 dev1.0 祖先」的 lane 移动 ref；其余 lane 零写并只报告，由该 lane 会话以
`sync-lane-from-dev` Skill 自行解决。任何分支都不 reset/stash/clean/merge 他人字节。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli/lib"))

import local_worktree_inventory as inventory  # noqa: E402

# push 可能明显超过 inventory._git 的 20 秒探测预算，这里用同样的仓库本地环境变量剥离但放宽超时。
_GIT_TIMEOUT_SECONDS = 180

RESYNC_OUTCOMES = (
    "ff_done",
    "skipped_missing",
    "skipped_in_progress",
    "skipped_dirty_overlap",
    "skipped_diverged",
    "ff_failed",
    "push_failed",
)
_IN_PROGRESS_MARKERS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply")
_OVERLAP_PREVIEW = 20

GitRunner = Callable[..., tuple[int, str]]


def _git(cwd: Path, *args: str) -> tuple[int, str]:
    command_env = os.environ.copy()
    for name in inventory._GIT_REPOSITORY_LOCAL_ENV_VARS:
        command_env.pop(name, None)
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=command_env,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    output = completed.stdout.strip()
    if completed.returncode != 0 and completed.stderr.strip():
        output = completed.stderr.strip()
    return completed.returncode, output


@dataclass(frozen=True)
class LaneResyncResult:
    branch: str
    path: str
    outcome: str
    target: str
    before: str = ""
    after: str = ""
    pushed: bool = False
    overlap: tuple[str, ...] = field(default_factory=tuple)
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["overlap"] = list(self.overlap)
        return payload


def render(action: str) -> list[str]:
    policy = inventory.load_policy()
    project_root = inventory.resolve_project_root(ROOT, policy)
    hub = project_root / policy.bare_hub_directory
    commands: list[str] = []
    for branch, directory in policy.lane_worktree_directories:
        path = project_root / directory
        if action == "bootstrap":
            commands.append(
                f'QWQ_WORKTREE_AUTHZ="<reason>" git -C {hub} worktree add {path} {branch}'
            )
        else:
            commands.append(f"git -C {path} merge --ff-only {policy.integration_branch}")
    return commands


def _status_paths(git: GitRunner, path: Path) -> list[str]:
    code, out = git(path, "status", "--porcelain", "--untracked-files=all")
    if code != 0:
        raise RuntimeError(out or "git status failed")
    paths: list[str] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        rel = line[3:].strip()
        if " -> " in rel:
            paths.extend(part.strip().strip('"') for part in rel.split(" -> ", 1))
        else:
            paths.append(rel.strip('"'))
    return paths


def _ff_paths(git: GitRunner, path: Path, target: str) -> list[str]:
    code, out = git(path, "diff", "--name-only", "HEAD", target)
    if code != 0:
        raise RuntimeError(out or "git diff --name-only failed")
    return [line.strip() for line in out.splitlines() if line.strip()]


def _in_progress(git: GitRunner, path: Path) -> bool:
    code, git_dir = git(path, "rev-parse", "--git-dir")
    if code != 0 or not git_dir:
        return False
    base = Path(git_dir)
    if not base.is_absolute():
        base = path / base
    return any((base / marker).exists() for marker in _IN_PROGRESS_MARKERS)


def resync_lane(
    *,
    branch: str,
    path: Path,
    target_branch: str,
    push: bool,
    git: GitRunner = _git,
) -> LaneResyncResult:
    """对单条 lane 执行三态判定；只有 ff-only 可证明安全时才移动 ref。"""

    def skipped(outcome: str, detail: str, **extra: object) -> LaneResyncResult:
        return LaneResyncResult(branch=branch, path=str(path), outcome=outcome, target=target_sha, detail=detail, **extra)

    target_sha = ""
    if not path.is_dir():
        return skipped("skipped_missing", "worktree directory does not exist")
    code, head_branch = git(path, "symbolic-ref", "--quiet", "--short", "HEAD")
    if code != 0 or head_branch != branch:
        return skipped("skipped_missing", f"worktree HEAD is {head_branch or '<detached>'}, expected {branch}")
    code, target_sha = git(path, "rev-parse", "--verify", "--quiet", f"refs/heads/{target_branch}")
    if code != 0 or not target_sha:
        return skipped("skipped_missing", f"local {target_branch} is not resolvable from {path}")
    code, before = git(path, "rev-parse", "HEAD")
    if code != 0 or not before:
        return skipped("skipped_missing", before or "HEAD unresolvable")
    if _in_progress(git, path):
        return skipped("skipped_in_progress", "merge/rebase/cherry-pick in progress", before=before)
    if git(path, "merge-base", "--is-ancestor", "HEAD", target_sha)[0] != 0:
        return skipped("skipped_diverged", f"{branch} has commits not reachable from {target_branch}", before=before)
    if before == target_sha:
        return LaneResyncResult(branch=branch, path=str(path), outcome="ff_done", target=target_sha, before=before, after=before, detail="already at target")
    try:
        dirty = set(_status_paths(git, path))
        touched = set(_ff_paths(git, path, target_sha))
    except RuntimeError as error:
        return skipped("skipped_missing", str(error), before=before)
    overlap = tuple(sorted(dirty & touched))
    if overlap:
        return skipped(
            "skipped_dirty_overlap",
            f"{len(overlap)} dirty path(s) would be overwritten by fast-forward",
            before=before,
            overlap=overlap[:_OVERLAP_PREVIEW],
        )
    code, out = git(path, "merge", "--ff-only", target_sha)
    after = git(path, "rev-parse", "HEAD")[1]
    if code != 0 or after != target_sha:
        return LaneResyncResult(branch=branch, path=str(path), outcome="ff_failed", target=target_sha, before=before, after=after, detail=out or "fast-forward did not reach target")
    if not push:
        return LaneResyncResult(branch=branch, path=str(path), outcome="ff_done", target=target_sha, before=before, after=after)
    code, out = git(path, "push", "origin", f"refs/heads/{branch}:refs/heads/{branch}")
    if code != 0:
        return LaneResyncResult(branch=branch, path=str(path), outcome="push_failed", target=target_sha, before=before, after=after, detail=out or "git push failed")
    return LaneResyncResult(branch=branch, path=str(path), outcome="ff_done", target=target_sha, before=before, after=after, pushed=True)


def execute_resync(
    *,
    policy: inventory.WorktreePolicy | None = None,
    project_root: Path | None = None,
    push: bool = True,
    git: GitRunner = _git,
) -> list[LaneResyncResult]:
    active = policy or inventory.load_policy()
    root = project_root or inventory.resolve_project_root(ROOT, active)
    return [
        resync_lane(
            branch=branch,
            path=root / directory,
            target_branch=active.integration_branch,
            push=push,
            git=git,
        )
        for branch, directory in active.lane_worktree_directories
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bootstrap", "resync"))
    parser.add_argument("--execute", action="store_true", help="resync 时真正执行 ff-only 回同步并输出 JSON 结果")
    parser.add_argument("--no-push", action="store_true", help="执行模式下只 ff，不推送同名远端 lane")
    args = parser.parse_args(argv)
    if args.action == "resync" and args.execute:
        results = execute_resync(push=not args.no_push)
        print(json.dumps([item.as_dict() for item in results], ensure_ascii=False, indent=2))
        return 0 if all(item.outcome == "ff_done" for item in results) else 1
    for command in render(args.action):
        print(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

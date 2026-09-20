#!/usr/bin/env python3
"""六 lane bootstrap/resync/align-published：默认只渲染命令；`resync --execute` 按 branch policy 的
`persistent_lane_admission.resync_scope` 执行 ff-only 回同步并输出每条 lane 的 typed 结果；
`align-published` 只把当前工作树对齐到已发布 exact SHA，供 `make accept SYNC=1` 在验收前调用。

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
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli/lib"))

import local_worktree_inventory as inventory  # noqa: E402

# FF 操作使用独立超时，并剥离调用者仓库本地环境变量。
_GIT_TIMEOUT_SECONDS = 180

RESYNC_OUTCOMES = (
    "ff_done",
    "skipped_missing",
    "skipped_in_progress",
    "skipped_dirty_overlap",
    "skipped_diverged",
    "ff_failed",
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
    output = completed.stdout if "-z" in args else completed.stdout.strip()
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
    overlap: tuple[str, ...] = field(default_factory=tuple)
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["overlap"] = list(self.overlap)
        return payload


def _published_target(git: GitRunner, root: Path, policy: inventory.WorktreePolicy) -> str:
    """调用者 fetch 后一轮只解析一次远端 tracking ref；不回退本地 dev。"""
    ref = f"refs/remotes/origin/{policy.integration_branch}^{{commit}}"
    code, sha = git(root / policy.bare_hub_directory, "rev-parse", "--verify", "--quiet", ref)
    if code != 0 or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) is None:
        raise RuntimeError(f"published origin/{policy.integration_branch} is not resolvable; fetch origin first")
    return sha


def render(
    action: str, *, policy: inventory.WorktreePolicy | None = None,
    project_root: Path | None = None, git: GitRunner = _git,
) -> list[str]:
    active = policy or inventory.load_policy()
    root = project_root or inventory.resolve_project_root(ROOT, active)
    hub = shlex.quote(str(root / active.bare_hub_directory))
    target_sha = _published_target(git, root, active) if action == "resync" else ""
    commands: list[str] = []
    for branch, directory in active.lane_worktree_directories:
        path = shlex.quote(str(root / directory))
        if action == "bootstrap":
            commands.append(
                f'QWQ_WORKTREE_AUTHZ="<reason>" git -C {hub} worktree add {path} {shlex.quote(branch)}'
            )
        else:
            commands.append(f"git -C {path} merge --ff-only {target_sha}")
    return commands


def _status_paths(git: GitRunner, path: Path) -> list[str]:
    code, out = git(path, "--no-optional-locks", "status", "--porcelain", "-z", "--untracked-files=all")
    if code != 0:
        raise RuntimeError(out or "git status failed")
    paths: list[str] = []
    entries = iter(out.split("\0"))
    for entry in entries:
        if not entry:
            continue
        paths.append(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            paths.append(next(entries))
    return paths


def _ff_paths(git: GitRunner, path: Path, target: str) -> list[str]:
    code, out = git(path, "diff", "--name-only", "--no-renames", "-z", "HEAD", target)
    if code != 0:
        raise RuntimeError(out or "git diff --name-only failed")
    return [name for name in out.split("\0") if name]


def _dirty_overlap(dirty: set[str], touched: set[str]) -> tuple[str, ...]:
    """同时保护 rename 两端及文件/目录替换，保留原始路径字节。"""
    return tuple(sorted(name for name in dirty if any(
        name == changed or name.startswith(changed + "/") or changed.startswith(name + "/")
        for changed in touched
    )))


def _in_progress(git: GitRunner, path: Path) -> bool:
    code, git_dir = git(path, "rev-parse", "--git-dir")
    if code != 0 or not git_dir:
        return True
    base = Path(git_dir)
    if not base.is_absolute():
        base = path / base
    return any((base / marker).exists() for marker in _IN_PROGRESS_MARKERS)


def resync_lane(
    *,
    branch: str,
    path: Path,
    target_sha: str,
    git: GitRunner = _git,
) -> LaneResyncResult:
    """对单条 lane 执行三态判定；只有 ff-only 可证明安全时才移动 ref。"""

    def skipped(outcome: str, detail: str, **extra: object) -> LaneResyncResult:
        return LaneResyncResult(branch=branch, path=str(path), outcome=outcome, target=target_sha, detail=detail, **extra)

    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", target_sha) is None:
        return skipped("skipped_missing", "published target must be an exact commit SHA")
    if not path.is_dir():
        return skipped("skipped_missing", "worktree directory does not exist")
    code, head_branch = git(path, "symbolic-ref", "--quiet", "--short", "HEAD")
    if code != 0 or head_branch != branch:
        return skipped("skipped_missing", f"worktree HEAD is {head_branch or '<detached>'}, expected {branch}")
    code, before = git(path, "rev-parse", "HEAD")
    if code != 0 or not before:
        return skipped("skipped_missing", before or "HEAD unresolvable")
    if _in_progress(git, path):
        return skipped("skipped_in_progress", "merge/rebase/cherry-pick in progress", before=before)
    if git(path, "merge-base", "--is-ancestor", "HEAD", target_sha)[0] != 0:
        return skipped("skipped_diverged", f"{branch} has commits not reachable from published {target_sha}", before=before)
    if before == target_sha:
        return LaneResyncResult(branch=branch, path=str(path), outcome="ff_done", target=target_sha, before=before, after=before, detail="already at target")
    try:
        dirty = set(_status_paths(git, path))
        touched = set(_ff_paths(git, path, target_sha))
    except RuntimeError as error:
        return skipped("skipped_missing", str(error), before=before)
    overlap = _dirty_overlap(dirty, touched)
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
    return LaneResyncResult(branch=branch, path=str(path), outcome="ff_done", target=target_sha, before=before, after=after)


def _align_identity(git: GitRunner, path: Path, target: str) -> tuple[str, str, dict[str, object] | None]:
    """返回 (branch, before, 早退结果)；HEAD 不可解析或有进行中操作即零写早退。"""
    code, branch = git(path, "symbolic-ref", "--quiet", "--short", "HEAD")
    if code != 0 or not branch:
        return "", "", {"outcome": "skipped_missing", "detail": "worktree HEAD is detached", "target": target}
    code, before = git(path, "rev-parse", "HEAD")
    if code != 0 or not before:
        return branch, "", {"outcome": "skipped_missing", "detail": before or "HEAD unresolvable",
                            "target": target, "branch": branch}
    if _in_progress(git, path):
        return branch, before, {"outcome": "skipped_in_progress", "detail": "merge/rebase/cherry-pick in progress",
                                "target": target, "branch": branch, "before": before}
    return branch, before, None


def align_published(
    *,
    worktree: Path | None = None,
    merge_authorized: bool = False,
    policy: inventory.WorktreePolicy | None = None,
    project_root: Path | None = None,
    git: GitRunner = _git,
    fetch: bool = True,
) -> dict[str, object]:
    """把**当前**工作树对齐到已发布 origin/dev1.0 exact SHA，供发布前一条命令使用。

    `ahead` 是常态（本 lane 有新提交），不是错误。落后走 ff-only；分叉只在调用方显式授权
    合并时才在本工作树 merge 同一 SHA，且先用 `merge-tree` 零写预判冲突。任何情形都不
    reset/stash/clean，也不触碰其他工作树。
    """
    active = policy or inventory.load_policy()
    root = project_root or inventory.resolve_project_root(ROOT, active)
    path = (worktree or ROOT).resolve()

    if fetch:
        code, out = git(root / active.bare_hub_directory, "fetch", "--no-tags", "origin",
                        f"refs/heads/{active.integration_branch}:refs/remotes/origin/{active.integration_branch}")
        if code != 0:
            return {"outcome": "skipped_missing", "worktree": str(path), "detail": out or "fetch origin failed"}
    try:
        target = _published_target(git, root, active)
    except RuntimeError as error:
        return {"outcome": "skipped_missing", "worktree": str(path), "detail": str(error)}

    branch, before, early = _align_identity(git, path, target)
    if early is not None:
        return {"worktree": str(path), **early}
    common = {"worktree": str(path), "target": target, "branch": branch, "before": before, "detail": ""}
    if before == target:
        return {**common, "outcome": "aligned", "detail": "already at the published SHA", "after": before}
    if git(path, "merge-base", "--is-ancestor", target, before)[0] == 0:
        return {**common, "outcome": "ahead", "detail": "worktree already contains the published SHA", "after": before}

    try:
        overlap = _dirty_overlap(set(_status_paths(git, path)), set(_ff_paths(git, path, target)))
    except RuntimeError as error:
        return {**common, "outcome": "skipped_missing", "detail": str(error)}
    if overlap:
        return {**common, "outcome": "skipped_dirty_overlap", "overlap": list(overlap[:_OVERLAP_PREVIEW]),
                "detail": f"{len(overlap)} dirty path(s) overlap the published delta"}

    behind_only = git(path, "merge-base", "--is-ancestor", before, target)[0] == 0
    if not behind_only:
        if not merge_authorized:
            return {**common, "outcome": "skipped_diverged",
                    "detail": f"{branch} diverged from published {target}; explicit merge authorization required"}
        # merge-tree 只算树、不动工作树：冲突时零写阻断，不留半成品 merge 状态。
        if git(path, "merge-tree", "--write-tree", before, target)[0] != 0:
            return {**common, "outcome": "merge_conflict",
                    "detail": f"merging published {target} conflicts; resolve in this worktree via sync-lane-from-dev"}
    code, out = git(path, "merge", "--no-edit", *(["--ff-only"] if behind_only else []), target)
    after = git(path, "rev-parse", "HEAD")[1]
    if code != 0 or (behind_only and after != target):
        return {**common, "outcome": "ff_failed", "after": after,
                "detail": out or "merge did not reach the published SHA"}
    return {**common, "outcome": "ff_done" if behind_only else "merged", "after": after}


def execute_resync(
    *,
    policy: inventory.WorktreePolicy | None = None,
    project_root: Path | None = None,
    git: GitRunner = _git,
) -> list[LaneResyncResult]:
    active = policy or inventory.load_policy()
    root = project_root or inventory.resolve_project_root(ROOT, active)
    try:
        target_sha = _published_target(git, root, active)
    except RuntimeError as error:
        return [LaneResyncResult(branch=branch, path=str(root / directory), outcome="skipped_missing",
                                 target="", detail=str(error))
                for branch, directory in active.lane_worktree_directories]
    return [
        resync_lane(
            branch=branch,
            path=root / directory,
            target_sha=target_sha,
            git=git,
        )
        for branch, directory in active.lane_worktree_directories
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bootstrap", "resync", "align-published"))
    parser.add_argument("--execute", action="store_true", help="resync 时真正执行 ff-only 回同步并输出 JSON 结果")
    parser.add_argument("--merge-authorized", action="store_true",
                        help="align-published：调用方已显式授权在本工作树合并同一已发布 SHA；冲突仍零写阻断")
    args = parser.parse_args(argv)
    if args.action == "align-published":
        outcome = align_published(merge_authorized=args.merge_authorized)
        print(json.dumps(outcome, ensure_ascii=False, indent=2))
        return 0 if outcome["outcome"] in {"aligned", "ahead", "ff_done", "merged"} else 1
    if args.action == "resync" and args.execute:
        results = execute_resync()
        print(json.dumps([item.as_dict() for item in results], ensure_ascii=False, indent=2))
        return 0 if all(item.outcome != "ff_failed" for item in results) else 1
    try:
        commands = render(args.action)
    except RuntimeError as error:
        print(f"skipped_missing: {error}", file=sys.stderr)
        return 1
    for command in commands:
        print(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

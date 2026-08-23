#!/usr/bin/env python3
"""本地工作副本清单与未合入滞留判定，全部实时派生。

角色：lib。被 `quwoquan_ops/hooks/worktree_merge_reminder.py` 与
`quwoquan_ops/gate/verify_local_worktree_lifecycle.py` 调用。

行为语义归属：
`specs/feature-tree/runtime/system-architecture-and-engineering-guide/local-worktree-lifecycle-governance/spec.md`
的 REQ-002 与 REQ-004。

清单只实时派生：linked worktree 来自 `git worktree list --porcelain`，同源 clone 来自策略
声明的发现根扫描。不存在受版本控制的 registry、allowlist 或滞留基线。
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT / "quwoquan_ops/policies/worktree_policy.yaml"
BRANCH_POLICY_PATH = ROOT / "quwoquan_ops/policies/branch_policy.yaml"

_FAILURE_CODE_KEYS = ("not_authorized", "unmerged_overdue", "hooks_not_installed")
_SKIP_DIR_NAMES = frozenset(
    {"node_modules", ".qwq_output", "build", "Pods", ".dart_tool", "vendor", "target"}
)


class PolicyError(ValueError):
    """策略文件缺失或形状非法。fail-closed，不接受默认值兜底。"""


@dataclass(frozen=True)
class WorktreePolicy:
    authorization_env_var: str
    unmerged_reminder_after_days: int
    reminder_min_interval_hours: int
    discovery_roots: tuple[str, ...]
    discovery_max_depth: int
    hooks_path: str
    install_command: str
    failure_codes: tuple[tuple[str, str], ...]
    allowed_local_branches: frozenset[str]

    def failure_code(self, name: str) -> str:
        for key, code in self.failure_codes:
            if key == name:
                return code
        raise KeyError(name)


@dataclass(frozen=True)
class WorkCopy:
    """一个本地工作副本的当前事实。

    `oldest_unmerged_epoch` 为 None 表示「没有任何未合入事实」，属于在场为空，
    不是探测失败；探测失败由 `probe_error` 单独承载。
    """

    path: str
    kind: str
    branch: str
    ahead: int
    dirty: int
    stashes: int
    oldest_unmerged_epoch: int | None
    probe_error: str

    @property
    def unmerged_facts(self) -> int:
        return self.ahead + self.dirty + self.stashes

    @property
    def has_unmerged(self) -> bool:
        return self.unmerged_facts > 0

    def stale_days(self, *, now: int) -> float:
        if self.oldest_unmerged_epoch is None:
            return 0.0
        return max(0.0, (now - self.oldest_unmerged_epoch) / 86400.0)

    def is_overdue(self, policy: WorktreePolicy, *, now: int) -> bool:
        if not self.has_unmerged:
            return False
        return self.stale_days(now=now) >= policy.unmerged_reminder_after_days


def _require_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PolicyError(f"worktree policy requires positive int {key}")
    return value


def _require_str(payload: dict[str, object], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise PolicyError(f"worktree policy requires non-empty {key}")
    return value


def load_policy(*, policy_path: Path | None = None, branch_policy_path: Path | None = None) -> WorktreePolicy:
    path = policy_path or POLICY_PATH
    branch_path = branch_policy_path or BRANCH_POLICY_PATH
    if not path.is_file():
        raise PolicyError(f"missing worktree policy: {path}")
    if not branch_path.is_file():
        raise PolicyError(f"missing branch policy: {branch_path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PolicyError("worktree policy must be a mapping")

    roots = payload.get("discovery_roots")
    if not isinstance(roots, list) or not roots:
        raise PolicyError("worktree policy discovery_roots must be a non-empty list")

    codes = payload.get("failure_codes")
    if not isinstance(codes, dict):
        raise PolicyError("worktree policy failure_codes must be a mapping")
    missing = [key for key in _FAILURE_CODE_KEYS if not str(codes.get(key) or "").strip()]
    if missing:
        raise PolicyError(f"worktree policy failure_codes missing: {', '.join(missing)}")

    # 分支白名单只有 branch_policy.yaml 一个真相源，本策略读取而不复制。
    branch_payload = yaml.safe_load(branch_path.read_text(encoding="utf-8"))
    if not isinstance(branch_payload, dict):
        raise PolicyError("branch policy must be a mapping")
    allowed = branch_payload.get("allowed_local_branches")
    if not isinstance(allowed, list) or not allowed:
        raise PolicyError("branch policy allowed_local_branches must be a non-empty list")

    return WorktreePolicy(
        authorization_env_var=_require_str(payload, "authorization_env_var"),
        unmerged_reminder_after_days=_require_int(payload, "unmerged_reminder_after_days"),
        reminder_min_interval_hours=_require_int(payload, "reminder_min_interval_hours"),
        discovery_roots=tuple(str(item).strip() for item in roots if str(item).strip()),
        discovery_max_depth=_require_int(payload, "discovery_max_depth"),
        hooks_path=_require_str(payload, "hooks_path"),
        install_command=_require_str(payload, "install_command"),
        failure_codes=tuple((key, str(codes[key]).strip()) for key in _FAILURE_CODE_KEYS),
        allowed_local_branches=frozenset(str(item).strip() for item in allowed),
    )


def _git(cwd: Path, *args: str) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return completed.returncode, completed.stdout.strip()


def _git_lines(cwd: Path, *args: str) -> list[str]:
    code, out = _git(cwd, *args)
    if code != 0 or not out:
        return []
    return [line for line in out.splitlines() if line.strip()]


def parse_worktree_list(porcelain: str) -> list[tuple[str, str]]:
    """把 `git worktree list --porcelain` 解析为 (path, branch) 序列，detached 的 branch 为空串。"""
    entries: list[tuple[str, str]] = []
    path = ""
    branch = ""
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            if path:
                entries.append((path, branch))
            path = line[len("worktree ") :].strip()
            branch = ""
        elif line.startswith("branch "):
            branch = line[len("branch ") :].strip().removeprefix("refs/heads/")
    if path:
        entries.append((path, branch))
    return entries


def _integration_ref(cwd: Path, policy: WorktreePolicy) -> str:
    """未合入基准：优先远端集成分支，其次同名本地分支。两者都不存在时返回空串。"""
    for candidate in ("origin/dev1.0", "dev1.0"):
        if candidate.split("/")[-1] not in policy.allowed_local_branches:
            continue
        code, _ = _git(cwd, "rev-parse", "--verify", "--quiet", candidate)
        if code == 0:
            return candidate
    return ""


def _unmerged_commits(path: Path, repo_root: Path, policy: WorktreePolicy) -> list[int]:
    """返回该副本未合入提交的 committer epoch 列表。

    基准必须是主仓库的集成分支，不能是副本自身的远程引用——副本的 `origin/dev1.0`
    往往是它被创建那天的陈旧快照。实测 `/private/tmp` 下一个 clone 因此被算出 41 个
    「未合入」提交，而它的 HEAD 其实早已可达真正的 `origin/dev1.0`。按陈旧基准报警
    等于每天对着已完成的工作喊狼来了，几次之后整条提醒就没人看了。
    """
    head = _git(path, "rev-parse", "HEAD")[1]
    if not head:
        return []

    base_ref = _integration_ref(repo_root, policy)
    base_sha = _git(repo_root, "rev-parse", "--verify", "--quiet", base_ref)[1] if base_ref else ""

    if base_sha and _git(repo_root, "cat-file", "-e", f"{head}^{{commit}}")[0] == 0:
        if _git(repo_root, "merge-base", "--is-ancestor", head, base_sha)[0] == 0:
            return []
        return [int(v) for v in _git_lines(repo_root, "log", "--format=%ct", f"{base_sha}..{head}") if v.isdigit()]

    # 主仓库不认识该 HEAD，说明副本确实含有主仓库没有的提交。改用副本内可解析的最近
    # 基准计数：优先主仓库集成分支的 sha（副本若已 fetch 到则最准），否则退回副本自身引用。
    local_base = ""
    if base_sha and _git(path, "cat-file", "-e", f"{base_sha}^{{commit}}")[0] == 0:
        local_base = base_sha
    else:
        local_base = _integration_ref(path, policy)
    if not local_base:
        return []
    return [int(v) for v in _git_lines(path, "log", "--format=%ct", f"{local_base}..HEAD") if v.isdigit()]


def _oldest_dirty_mtime(cwd: Path, status_lines: list[str]) -> int | None:
    oldest: int | None = None
    for line in status_lines:
        rel = line[3:].strip()
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1]
        target = cwd / rel.strip('"')
        try:
            mtime = int(target.stat().st_mtime)
        except OSError:
            continue
        if oldest is None or mtime < oldest:
            oldest = mtime
    return oldest


def probe_work_copy(
    path: Path, *, kind: str, branch: str, policy: WorktreePolicy, repo_root: Path | None = None
) -> WorkCopy:
    """采集单个工作副本的未合入事实。git 不可读时以 probe_error 显式承载，不用零值冒充。"""
    root = repo_root or ROOT
    code, _ = _git(path, "rev-parse", "--is-inside-work-tree")
    if code != 0:
        return WorkCopy(
            path=str(path),
            kind=kind,
            branch=branch,
            ahead=0,
            dirty=0,
            stashes=0,
            oldest_unmerged_epoch=None,
            probe_error="git worktree not readable",
        )

    status_lines = _git_lines(path, "status", "--porcelain")
    # stash 存放在 common dir，全部 linked worktree 与主 worktree 共享同一份 stash list。
    # 把它算进 linked worktree 会让刚创建的副本立刻继承主仓库 stash 的年龄——实测一个
    # 新建 worktree 因此被判为已滞留 2.5 天。stash 归主仓库，而主仓库不在提醒范围内。
    stash_epochs: list[int] = []
    if kind == "clone":
        stash_epochs = [int(v) for v in _git_lines(path, "stash", "list", "--format=%ct") if v.isdigit()]
    ahead_epochs = _unmerged_commits(path, root, policy)
    ahead = len(ahead_epochs)

    candidates = [*ahead_epochs, *stash_epochs]
    dirty_epoch = _oldest_dirty_mtime(path, status_lines)
    if dirty_epoch is not None:
        candidates.append(dirty_epoch)

    return WorkCopy(
        path=str(path),
        kind=kind,
        branch=branch,
        ahead=ahead,
        dirty=len(status_lines),
        stashes=len(stash_epochs),
        oldest_unmerged_epoch=min(candidates) if candidates else None,
        probe_error="",
    )


def _resolve_roots(root: Path, policy: WorktreePolicy) -> list[Path]:
    resolved: list[Path] = []
    for raw in policy.discovery_roots:
        text = raw.replace("{repo_parent}", str(root.parent))
        candidate = Path(text).expanduser()
        if candidate.is_dir():
            resolved.append(candidate)
    return resolved


def _scan_for_clones(root: Path, policy: WorktreePolicy, known: set[str]) -> list[Path]:
    """在发现根下寻找同源 clone。clone 目标不继承本仓库 hooks，只能由源侧发现。"""
    found: list[Path] = []
    root_commit = _git_lines(root, "rev-list", "--max-parents=0", "HEAD")
    origin_url = _git(root, "remote", "get-url", "origin")[1]

    for base in _resolve_roots(root, policy):
        for candidate in _walk(base, policy.discovery_max_depth):
            resolved = str(candidate.resolve())
            if resolved in known:
                continue
            known.add(resolved)
            if not _is_same_origin(candidate, origin_url, root_commit, root):
                continue
            found.append(candidate)
    return found


def _walk(base: Path, max_depth: int) -> list[Path]:
    results: list[Path] = []
    frontier = [(base, 0)]
    while frontier:
        current, depth = frontier.pop()
        if depth > max_depth:
            continue
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False) or entry.name in _SKIP_DIR_NAMES:
                continue
            child = Path(entry.path)
            if (child / ".git").exists():
                results.append(child)
                continue
            if depth < max_depth:
                frontier.append((child, depth + 1))
    return results


def _is_same_origin(candidate: Path, origin_url: str, root_commit: list[str], root: Path) -> bool:
    code, url = _git(candidate, "remote", "get-url", "origin")
    if code == 0 and url:
        if origin_url and url == origin_url:
            return True
        if Path(url).expanduser().resolve(strict=False) == root.resolve():
            return True
    if not root_commit:
        return False
    return _git_lines(candidate, "rev-list", "--max-parents=0", "HEAD") == root_commit


def discover_work_copies(*, root: Path | None = None, policy: WorktreePolicy | None = None) -> list[WorkCopy]:
    """派生除主 worktree 之外的全部工作副本。

    主 worktree 被刻意排除：根 AGENTS.md 明文「脏工作树是常态」，对它报滞留会产生
    每日假红，最终导致整条提醒被忽略。用户要治理的是「未合入主 worktree 的副本」，
    主副本自身的推送纪律由 branch policy 与 pre-push 承担。
    """
    repo_root = root or ROOT
    active = policy or load_policy()
    copies: list[WorkCopy] = []
    known: set[str] = set()

    code, porcelain = _git(repo_root, "worktree", "list", "--porcelain")
    main_path = repo_root.resolve()
    if code == 0:
        for index, (path, branch) in enumerate(parse_worktree_list(porcelain)):
            resolved = Path(path).resolve()
            known.add(str(resolved))
            if index == 0 or resolved == main_path:
                continue
            copies.append(
                probe_work_copy(
                    resolved, kind="linked_worktree", branch=branch, policy=active, repo_root=repo_root
                )
            )

    known.add(str(main_path))
    for clone in _scan_for_clones(repo_root, active, known):
        branch = _git(clone, "rev-parse", "--abbrev-ref", "HEAD")[1]
        copies.append(
            probe_work_copy(
                clone,
                kind="clone",
                branch="" if branch == "HEAD" else branch,
                policy=active,
                repo_root=repo_root,
            )
        )
    return copies


def hooks_installed(*, root: Path | None = None, policy: WorktreePolicy | None = None) -> bool:
    """`core.hooksPath` 是否指向仓内受版本控制的 hook 目录。"""
    repo_root = root or ROOT
    active = policy or load_policy()
    code, configured = _git(repo_root, "config", "--get", "core.hooksPath")
    if code != 0 or not configured:
        return False
    expected = (repo_root / active.hooks_path).resolve()
    actual = Path(configured)
    if not actual.is_absolute():
        actual = repo_root / actual
    return actual.resolve() == expected and expected.is_dir()


def summarize(copies: list[WorkCopy], policy: WorktreePolicy, *, now: int | None = None) -> dict[str, object]:
    moment = now if now is not None else int(time.time())
    pending = [copy for copy in copies if copy.has_unmerged]
    overdue = [copy for copy in pending if copy.is_overdue(policy, now=moment)]
    return {
        "checkedAt": moment,
        "totalWorkCopies": len(copies),
        "withUnmergedWork": len(pending),
        "overdue": len(overdue),
        "items": [
            {
                "path": copy.path,
                "kind": copy.kind,
                "branch": copy.branch,
                "ahead": copy.ahead,
                "dirty": copy.dirty,
                "stashes": copy.stashes,
                "staleDays": round(copy.stale_days(now=moment), 1),
                "overdue": copy.is_overdue(policy, now=moment),
                "probeError": copy.probe_error,
            }
            for copy in pending
        ],
    }

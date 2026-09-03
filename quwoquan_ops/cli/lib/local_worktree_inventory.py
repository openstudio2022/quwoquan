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

import importlib.util
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT / "quwoquan_ops/policies/worktree_policy.yaml"
BRANCH_POLICY_PATH = ROOT / "quwoquan_ops/policies/branch_policy.yaml"

_FAILURE_CODE_KEYS = ("not_authorized", "unmerged_overdue", "hooks_not_installed")
_WORKTREE_POLICY_FIELDS = frozenset(
    {
        "authorization_env_var",
        "unmerged_reminder_after_days",
        "reminder_min_interval_hours",
        "discovery_roots",
        "discovery_max_depth",
        "hooks_path",
        "install_command",
        "failure_codes",
    }
)
_SKIP_DIR_NAMES = frozenset(
    {"node_modules", ".qwq_output", "build", "Pods", ".dart_tool", "vendor", "target"}
)
# Git hooks export repository-local variables for the invoking worktree.  Every
# command in this module may inspect a different worktree or clone, so those
# variables must not override its cwd.  This is the static, reviewed set
# reported by `git rev-parse --local-env-vars`; global auth/SSH/PATH variables
# deliberately remain inherited.
_GIT_REPOSITORY_LOCAL_ENV_VARS = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_DIR",
        "GIT_GRAFT_FILE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    }
)


class PolicyError(ValueError):
    """策略文件缺失或形状非法。fail-closed，不接受默认值兜底。"""


class InventoryError(RuntimeError):
    """实时 worktree authority 不可读或身份含糊，必须 typed fail-closed。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


INVENTORY_UNAVAILABLE = "OPS.WORKTREE.INVENTORY_UNAVAILABLE"
IDENTITY_INVALID = "OPS.WORKTREE.IDENTITY_INVALID"


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
    head: str = ""
    clean: bool = False

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
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"worktree policy requires non-empty string {key}")
    return value.strip()


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """拒绝任意层级重复 YAML key。"""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _load_branch_policy_parser():
    path = ROOT / "quwoquan_ops/gate/verify_git_branch_policy.py"
    spec = importlib.util.spec_from_file_location("_canonical_git_branch_policy", path)
    if spec is None or spec.loader is None:
        raise PolicyError("canonical branch policy parser is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_policy(
    *, policy_path: Path | None = None, branch_policy_path: Path | None = None
) -> WorktreePolicy:
    path = policy_path or POLICY_PATH
    branch_path = branch_policy_path or BRANCH_POLICY_PATH
    if not path.is_file():
        raise PolicyError(f"missing worktree policy: {path}")
    if not branch_path.is_file():
        raise PolicyError(f"missing branch policy: {branch_path}")

    try:
        payload = yaml.load(
            path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader
        )
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise PolicyError(f"worktree policy invalid: {error}") from error
    if not isinstance(payload, dict):
        raise PolicyError("worktree policy must be a mapping")
    actual_fields = set(payload)
    if actual_fields != _WORKTREE_POLICY_FIELDS:
        raise PolicyError(
            "worktree policy root fields drifted; "
            f"missing={sorted(_WORKTREE_POLICY_FIELDS - actual_fields)}, "
            f"unexpected={sorted(actual_fields - _WORKTREE_POLICY_FIELDS, key=repr)}"
        )

    roots = payload.get("discovery_roots")
    if (
        not isinstance(roots, list)
        or not roots
        or any(not isinstance(item, str) or not item.strip() for item in roots)
    ):
        raise PolicyError(
            "worktree policy discovery_roots must be a non-empty string list"
        )
    normalized_roots = tuple(item.strip() for item in roots)
    if len(normalized_roots) != len(set(normalized_roots)):
        raise PolicyError("worktree policy discovery_roots must be duplicate-free")

    codes = payload.get("failure_codes")
    if not isinstance(codes, dict):
        raise PolicyError("worktree policy failure_codes must be a mapping")
    if set(codes) != set(_FAILURE_CODE_KEYS):
        raise PolicyError(
            "worktree policy failure_codes drifted; "
            f"missing={sorted(set(_FAILURE_CODE_KEYS) - set(codes))}, "
            f"unexpected={sorted(set(codes) - set(_FAILURE_CODE_KEYS), key=repr)}"
        )
    if any(
        not isinstance(codes[key], str) or not codes[key].strip()
        for key in _FAILURE_CODE_KEYS
    ):
        raise PolicyError("worktree policy failure_codes must be non-empty strings")

    # 分支白名单只有 branch_policy.yaml 一个真相源；复用其唯一完整 parser，
    # 不复制 schema。
    try:
        branch_policy = _load_branch_policy_parser().load_policy_bytes(
            branch_path.read_bytes()
        )
    except Exception as error:
        raise PolicyError(f"branch policy invalid: {error}") from error
    allowed = branch_policy.allowed_local

    return WorktreePolicy(
        authorization_env_var=_require_str(payload, "authorization_env_var"),
        unmerged_reminder_after_days=_require_int(payload, "unmerged_reminder_after_days"),
        reminder_min_interval_hours=_require_int(payload, "reminder_min_interval_hours"),
        discovery_roots=normalized_roots,
        discovery_max_depth=_require_int(payload, "discovery_max_depth"),
        hooks_path=_require_str(payload, "hooks_path"),
        install_command=_require_str(payload, "install_command"),
        failure_codes=tuple(
            (key, codes[key].strip()) for key in _FAILURE_CODE_KEYS
        ),
        allowed_local_branches=frozenset(allowed),
    )


def _git(cwd: Path, *args: str) -> tuple[int, str]:
    command_env = os.environ.copy()
    for name in _GIT_REPOSITORY_LOCAL_ENV_VARS:
        command_env.pop(name, None)
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=command_env,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    output = completed.stdout.strip()
    if completed.returncode != 0 and completed.stderr.strip():
        output = completed.stderr.strip()
    return completed.returncode, output


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


def _failed_work_copy(path: Path, *, kind: str, branch: str, detail: str) -> WorkCopy:
    return WorkCopy(
        path=str(path),
        kind=kind,
        branch=branch,
        ahead=0,
        dirty=0,
        stashes=0,
        oldest_unmerged_epoch=None,
        probe_error=detail,
    )


def probe_work_copy(
    path: Path, *, kind: str, branch: str, policy: WorktreePolicy, repo_root: Path | None = None
) -> WorkCopy:
    """采集单个工作副本；身份所需的 root/HEAD/status 任一失败都显式承载。"""
    root = repo_root or ROOT
    code, inside = _git(path, "rev-parse", "--is-inside-work-tree")
    if code != 0 or inside != "true":
        return _failed_work_copy(
            path, kind=kind, branch=branch, detail=f"git worktree not readable: {inside}"
        )

    code, head = _git(path, "rev-parse", "--verify", "HEAD")
    if code != 0 or not head:
        return _failed_work_copy(
            path, kind=kind, branch=branch, detail=f"HEAD probe failed: {head}"
        )
    code, status = _git(path, "status", "--porcelain")
    if code != 0:
        return _failed_work_copy(
            path, kind=kind, branch=branch, detail=f"status probe failed: {status}"
        )
    status_lines = [line for line in status.splitlines() if line.strip()]

    # stash 存放在 common dir，全部 linked worktree 与主 worktree 共享同一份 stash list。
    # 把它算进 linked worktree 会让刚创建的副本继承主仓库 stash 的年龄。
    stash_epochs: list[int] = []
    if kind == "clone":
        stash_epochs = [
            int(value)
            for value in _git_lines(path, "stash", "list", "--format=%ct")
            if value.isdigit()
        ]
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
        head=head,
        clean=not status_lines,
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


def _fixed_lane_branches(policy: WorktreePolicy) -> frozenset[str]:
    lanes = frozenset(
        branch for branch in policy.allowed_local_branches if branch.startswith("lane/")
    )
    if len(lanes) != 6:
        raise PolicyError(
            "branch policy must expose exactly six fixed lane branches for worktree identity"
        )
    return lanes


def discover_work_copies(*, root: Path | None = None, policy: WorktreePolicy | None = None) -> list[WorkCopy]:
    """实时派生 linked worktree 与同源 clone；authority 失败绝不退化为空清单。"""
    repo_root = (root or ROOT).resolve()
    active = policy or load_policy()
    copies: list[WorkCopy] = []
    known: set[str] = set()

    code, porcelain = _git(repo_root, "worktree", "list", "--porcelain")
    if code != 0:
        raise InventoryError(
            INVENTORY_UNAVAILABLE,
            f"git worktree list --porcelain failed: {porcelain or 'no diagnostic'}",
        )
    entries = parse_worktree_list(porcelain)
    if not entries:
        raise InventoryError(INVENTORY_UNAVAILABLE, "git worktree list returned no entries")

    canonical_occurrences = 0
    for raw_path, branch in entries:
        try:
            resolved = Path(raw_path).resolve(strict=True)
        except OSError as error:
            raise InventoryError(
                IDENTITY_INVALID, f"worktree path cannot be resolved: {raw_path}: {error}"
            ) from error
        normalized = str(resolved)
        if normalized in known:
            raise InventoryError(IDENTITY_INVALID, f"duplicate worktree path: {normalized}")
        known.add(normalized)
        if resolved == repo_root:
            canonical_occurrences += 1
            continue
        copies.append(
            probe_work_copy(
                resolved,
                kind="linked_worktree",
                branch=branch,
                policy=active,
                repo_root=repo_root,
            )
        )
    if canonical_occurrences != 1:
        raise InventoryError(
            IDENTITY_INVALID,
            f"canonical worktree root must appear exactly once, found={canonical_occurrences}",
        )

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


def validate_worktree_identity(
    copies: list[WorkCopy],
    policy: WorktreePolicy,
    *,
    require_all_lanes: bool = False,
    repo_root: Path | None = None,
) -> list[str]:
    """验证实时 linked worktree 身份；默认不要求六条 lane 已全部创建。"""
    lanes = _fixed_lane_branches(policy)
    issues: list[str] = []
    seen_paths: set[str] = set()
    branch_paths: dict[str, str] = {}
    linked = [copy for copy in copies if copy.kind == "linked_worktree"]

    for copy in linked:
        normalized = str(Path(copy.path).resolve(strict=False))
        if normalized in seen_paths:
            issues.append(f"{IDENTITY_INVALID}: duplicate worktree path: {normalized}")
        seen_paths.add(normalized)
        if copy.probe_error:
            issues.append(
                f"{IDENTITY_INVALID}: linked worktree probe failed: {copy.path}: {copy.probe_error}"
            )
        if not copy.branch:
            issues.append(f"{IDENTITY_INVALID}: detached linked worktree: {copy.path}")
            continue
        if copy.branch not in lanes:
            issues.append(
                f"{IDENTITY_INVALID}: linked worktree branch is not a fixed lane: "
                f"{copy.path}: {copy.branch}"
            )
            continue
        previous = branch_paths.get(copy.branch)
        if previous is not None:
            issues.append(
                f"{IDENTITY_INVALID}: duplicate lane binding: {copy.branch}: "
                f"{previous}, {copy.path}"
            )
        else:
            branch_paths[copy.branch] = copy.path

    if not require_all_lanes:
        return issues

    missing = sorted(lanes - set(branch_paths))
    unexpected = sorted(set(branch_paths) - lanes)
    if missing or unexpected or len(linked) != len(lanes):
        issues.append(
            f"{IDENTITY_INVALID}: require-all-lanes mismatch; "
            f"missing={missing}, unexpected={unexpected}, linked={len(linked)}"
        )

    root = (repo_root or ROOT).resolve()
    ref = _integration_ref(root, policy)
    if not ref:
        issues.append(
            f"{INVENTORY_UNAVAILABLE}: canonical integration ref unavailable "
            "(expected origin/dev1.0, fallback dev1.0)"
        )
        return issues
    code, integration_head = _git(root, "rev-parse", "--verify", ref)
    if code != 0 or not integration_head:
        issues.append(
            f"{INVENTORY_UNAVAILABLE}: canonical integration ref probe failed: {ref}: {integration_head}"
        )
        return issues

    for copy in linked:
        if copy.probe_error or copy.branch not in lanes:
            continue
        if not copy.clean or copy.dirty:
            issues.append(f"{IDENTITY_INVALID}: lane worktree is not clean: {copy.path}")
        if copy.head != integration_head:
            issues.append(
                f"{IDENTITY_INVALID}: lane HEAD differs from {ref}: "
                f"{copy.path}: actual={copy.head or '<missing>'} expected={integration_head}"
            )
    return issues

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

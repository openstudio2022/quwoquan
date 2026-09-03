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

import fnmatch
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
LANE_OWNERSHIP_PATH = ROOT / "quwoquan_ops/policies/lane_ownership.yaml"

_FAILURE_CODE_KEYS = ("not_authorized", "unmerged_overdue", "hooks_not_installed")
_WORKTREE_POLICY_FIELDS = frozenset(
    {
        "schema_version",
        "project_root",
        "bare_hub_directory",
        "integration_worktree_directory",
        "lane_worktree_directory_rule",
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
    schema_version: int
    project_root: str
    bare_hub_directory: str
    integration_directory: str
    integration_branch: str
    lane_worktree_directories: tuple[tuple[str, str], ...]
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
class WorktreeListEntry:
    path: str
    branch: str
    bare: bool


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
    behind: int = 0
    ownership_drift: tuple[str, ...] = ()

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


def load_lane_ownership(
    *, path: Path | None = None, allowed_lanes: frozenset[str] | None = None
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Load the ordered ownership matcher without duplicating branch or layout truth."""
    source = path or LANE_OWNERSHIP_PATH
    try:
        payload = yaml.load(source.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise PolicyError(f"lane ownership policy invalid: {error}") from error
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "matching", "rules"}:
        raise PolicyError("lane ownership policy must contain exact schema_version/matching/rules")
    if payload["schema_version"] != 1 or payload["matching"] != "first_match":
        raise PolicyError("lane ownership policy requires schema_version=1 and matching=first_match")
    raw_rules = payload["rules"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise PolicyError("lane ownership policy rules must be a non-empty list")
    rules: list[tuple[str, tuple[str, ...]]] = []
    seen_patterns: set[str] = set()
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict) or set(raw_rule) != {"owner", "patterns"}:
            raise PolicyError(f"lane ownership rule {index} must contain exact owner/patterns")
        owner = raw_rule["owner"]
        patterns = raw_rule["patterns"]
        if not isinstance(owner, str) or not owner.startswith("lane/"):
            raise PolicyError(f"lane ownership rule {index} owner must be a lane branch")
        if allowed_lanes is not None and owner not in allowed_lanes:
            raise PolicyError(f"lane ownership owner is not a fixed lane: {owner}")
        if (
            not isinstance(patterns, list)
            or not patterns
            or any(not isinstance(pattern, str) or not pattern.strip() for pattern in patterns)
        ):
            raise PolicyError(f"lane ownership rule {index} patterns must be non-empty strings")
        normalized = tuple(pattern.strip() for pattern in patterns)
        duplicate = seen_patterns & set(normalized)
        if duplicate:
            raise PolicyError(f"lane ownership patterns must be globally duplicate-free: {sorted(duplicate)}")
        seen_patterns.update(normalized)
        rules.append((owner, normalized))
    return tuple(rules)


def ownership_owner(
    relative_path: str, rules: tuple[tuple[str, tuple[str, ...]], ...]
) -> str | None:
    normalized = relative_path.replace("\\", "/").lstrip("./")
    for owner, patterns in rules:
        if any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns):
            return owner
    return None


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

    schema_version = payload.get("schema_version")
    if schema_version != 2:
        raise PolicyError("worktree policy schema_version must be 2")
    project_root = _require_str(payload, "project_root")
    if project_root != "{repo_parent}":
        raise PolicyError("worktree policy project_root must be the {repo_parent} token")
    bare_hub = _require_str(payload, "bare_hub_directory")
    if Path(bare_hub).name != bare_hub or bare_hub in {".", ".."}:
        raise PolicyError("worktree policy bare_hub_directory must be one directory name")

    integration_directory = _require_str(payload, "integration_worktree_directory")
    if Path(integration_directory).name != integration_directory or integration_directory in {".", ".."}:
        raise PolicyError("worktree policy integration directory must be one directory name")
    lane_directory_rule = _require_str(payload, "lane_worktree_directory_rule")
    if lane_directory_rule != "branch_suffix":
        raise PolicyError("worktree policy lane directory rule must be branch_suffix")

    # 分支白名单只有 branch_policy.yaml 一个真相源；复用其唯一完整 parser，
    # 不复制 schema。
    try:
        branch_policy = _load_branch_policy_parser().load_policy_bytes(
            branch_path.read_bytes()
        )
    except Exception as error:
        raise PolicyError(f"branch policy invalid: {error}") from error
    allowed = branch_policy.allowed_local
    lanes = frozenset(branch for branch in allowed if branch.startswith("lane/"))
    if len(lanes) != 6:
        raise PolicyError("branch policy must expose exactly six fixed lanes")
    integration_branch = branch_policy.integration_branch
    normalized_lane_directories = tuple(
        (branch, branch.removeprefix("lane/")) for branch in sorted(lanes)
    )
    reserved_directories = {bare_hub, integration_directory}
    if reserved_directories & {directory for _, directory in normalized_lane_directories}:
        raise PolicyError("worktree policy bare/integration/lane directories must be distinct")


    return WorktreePolicy(
        schema_version=schema_version,
        project_root=project_root,
        bare_hub_directory=bare_hub,
        integration_directory=integration_directory,
        integration_branch=integration_branch,
        lane_worktree_directories=tuple(normalized_lane_directories),
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
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
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


def parse_worktree_list(porcelain: str) -> list[WorktreeListEntry]:
    """Parse porcelain records, preserving bare hubs as non-worktree entries."""
    entries: list[WorktreeListEntry] = []
    current: dict[str, object] | None = None
    for line in [*porcelain.splitlines(), ""]:
        if line.startswith("worktree "):
            if current is not None:
                entries.append(WorktreeListEntry(**current))
            current = {
                "path": line[len("worktree ") :].strip(),
                "branch": "",
                "bare": False,
            }
        elif not line:
            if current is not None:
                entries.append(WorktreeListEntry(**current))
                current = None
        elif current is None:
            raise InventoryError(IDENTITY_INVALID, f"worktree porcelain field without record: {line}")
        elif line == "bare":
            current["bare"] = True
        elif line.startswith("branch "):
            current["branch"] = line[len("branch ") :].strip().removeprefix("refs/heads/")
    return entries


def _integration_ref(cwd: Path, policy: WorktreePolicy) -> str:
    """未合入基准：优先远端集成分支，其次同名本地分支。两者都不存在时返回空串。"""
    for candidate in (f"origin/{policy.integration_branch}", policy.integration_branch):
        if candidate.removeprefix("origin/") not in policy.allowed_local_branches:
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
    code, status = _git(path, "-c", "core.quotepath=off", "status", "--porcelain=v1")
    if code != 0:
        return _failed_work_copy(
            path, kind=kind, branch=branch, detail=f"status probe failed: {status}"
        )
    status_lines = [line for line in status.splitlines() if line.strip()]
    status_paths: list[str] = []
    for line in status_lines:
        relative = line[3:].strip()
        if " -> " in relative:
            relative = relative.split(" -> ", 1)[1]
        status_paths.append(relative.strip('"'))
    lanes = frozenset(
        candidate for candidate in policy.allowed_local_branches if candidate.startswith("lane/")
    )
    ownership_rules = load_lane_ownership(allowed_lanes=lanes)
    ownership_drift = tuple(
        relative
        for relative in status_paths
        if (owner := ownership_owner(relative, ownership_rules)) is not None and owner != branch
    )

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
    behind = 0
    base_ref = _integration_ref(root, policy)
    if base_ref:
        base_sha = _git(root, "rev-parse", "--verify", base_ref)[1]
        if base_sha and _git(path, "cat-file", "-e", f"{base_sha}^{{commit}}")[0] == 0:
            counts = _git(path, "rev-list", "--left-right", "--count", f"HEAD...{base_sha}")[1].split()
            if len(counts) == 2 and all(value.isdigit() for value in counts):
                ahead, behind = (int(value) for value in counts)

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
        behind=behind,
        ownership_drift=ownership_drift,
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

    resolved_project_root = resolve_project_root(root, policy)
    skipped = {(resolved_project_root / policy.bare_hub_directory).resolve()}
    for base in _resolve_roots(root, policy):
        for candidate in _walk(base, policy.discovery_max_depth, skipped=skipped):
            resolved = str(candidate.resolve())
            if resolved in known:
                continue
            known.add(resolved)
            if not _is_same_origin(candidate, origin_url, root_commit, root):
                continue
            found.append(candidate)
    return found


def _walk(base: Path, max_depth: int, *, skipped: set[Path] | None = None) -> list[Path]:
    results: list[Path] = []
    skipped_paths = skipped or set()
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
            if child.resolve() in skipped_paths:
                continue
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


def resolve_project_root(repo_root: Path, policy: WorktreePolicy) -> Path:
    return Path(policy.project_root.replace("{repo_parent}", str(repo_root.parent))).expanduser().resolve()


def discover_work_copies(*, root: Path | None = None, policy: WorktreePolicy | None = None) -> list[WorkCopy]:
    """实时派生 bare hub、linked worktree 与同源 clone；bare hub 不作为脏工作副本 probe。"""
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

    resolved_project_root = resolve_project_root(repo_root, active)
    expected_bare = (resolved_project_root / active.bare_hub_directory).resolve()
    bare_occurrences = 0
    worktree_occurrences = 0
    for entry in entries:
        try:
            resolved = Path(entry.path).resolve(strict=True)
        except OSError as error:
            raise InventoryError(
                IDENTITY_INVALID, f"worktree path cannot be resolved: {entry.path}: {error}"
            ) from error
        normalized = str(resolved)
        if normalized in known:
            raise InventoryError(IDENTITY_INVALID, f"duplicate worktree path: {normalized}")
        known.add(normalized)
        if entry.bare:
            if resolved != expected_bare:
                raise InventoryError(
                    IDENTITY_INVALID,
                    f"bare hub path mismatch: actual={resolved} expected={expected_bare}",
                )
            bare_occurrences += 1
            continue
        worktree_occurrences += int(resolved == repo_root)
        copies.append(
            probe_work_copy(
                resolved,
                kind="linked_worktree",
                branch=entry.branch,
                policy=active,
                repo_root=repo_root,
            )
        )
    if bare_occurrences != 1:
        raise InventoryError(
            IDENTITY_INVALID, f"canonical bare hub must appear exactly once, found={bare_occurrences}"
        )
    if worktree_occurrences != 1:
        raise InventoryError(
            IDENTITY_INVALID,
            f"invoking worktree root must appear exactly once, found={worktree_occurrences}",
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
    """Validate exact branch-to-directory bindings; integration is checked separately."""
    lanes = _fixed_lane_branches(policy)
    root = (repo_root or ROOT).resolve()
    resolved_project_root = resolve_project_root(root, policy)
    expected_lane_paths = {
        branch: str((resolved_project_root / directory).resolve())
        for branch, directory in policy.lane_worktree_directories
    }
    expected_integration_path = str((resolved_project_root / policy.integration_directory).resolve())
    issues: list[str] = []
    seen_paths: set[str] = set()
    lane_copies: dict[str, WorkCopy] = {}
    integrations: list[WorkCopy] = []
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
        if copy.branch == policy.integration_branch:
            integrations.append(copy)
            if normalized != expected_integration_path:
                issues.append(
                    f"{IDENTITY_INVALID}: integration path mismatch: actual={normalized} "
                    f"expected={expected_integration_path}"
                )
            continue
        if not copy.branch:
            issues.append(f"{IDENTITY_INVALID}: detached linked worktree: {copy.path}")
            continue
        if copy.branch not in lanes:
            issues.append(
                f"{IDENTITY_INVALID}: linked worktree branch is not integration or a fixed lane: "
                f"{copy.path}: {copy.branch}"
            )
            continue
        expected_path = expected_lane_paths[copy.branch]
        if normalized != expected_path:
            issues.append(
                f"{IDENTITY_INVALID}: lane path mismatch for {copy.branch}: "
                f"actual={normalized} expected={expected_path}"
            )
        previous = lane_copies.get(copy.branch)
        if previous is not None:
            issues.append(
                f"{IDENTITY_INVALID}: duplicate lane binding: {copy.branch}: "
                f"{previous.path}, {copy.path}"
            )
        else:
            lane_copies[copy.branch] = copy

    if len(integrations) != 1:
        issues.append(
            f"{IDENTITY_INVALID}: integration worktree must appear exactly once at "
            f"{expected_integration_path}; found={len(integrations)}"
        )
    elif integrations[0].probe_error:
        pass
    elif not integrations[0].clean or integrations[0].dirty:
        issues.append(
            f"{IDENTITY_INVALID}: integration worktree is not clean: {integrations[0].path}"
        )

    if not require_all_lanes:
        return issues

    missing = sorted(lanes - set(lane_copies))
    if missing or len(lane_copies) != len(lanes):
        issues.append(
            f"{IDENTITY_INVALID}: require-all-lanes mismatch; "
            f"missing={missing}, unexpected=[], lanes={len(lane_copies)}"
        )

    ref = _integration_ref(root, policy)
    if not ref:
        issues.append(
            f"{INVENTORY_UNAVAILABLE}: canonical integration ref unavailable "
            f"(expected origin/{policy.integration_branch}, fallback {policy.integration_branch})"
        )
        return issues
    code, integration_head = _git(root, "rev-parse", "--verify", ref)
    if code != 0 or not integration_head:
        issues.append(
            f"{INVENTORY_UNAVAILABLE}: canonical integration ref probe failed: {ref}: {integration_head}"
        )
        return issues

    if integrations and not integrations[0].probe_error and integrations[0].head != integration_head:
        issues.append(
            f"{IDENTITY_INVALID}: integration HEAD differs from {ref}: "
            f"actual={integrations[0].head or '<missing>'} expected={integration_head}"
        )
    for copy in lane_copies.values():
        if copy.probe_error:
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
        "identities": [
            {
                "path": copy.path,
                "kind": copy.kind,
                "branch": copy.branch,
                "ahead": copy.ahead,
                "behind": copy.behind,
                "dirty": copy.dirty,
                "ownershipDrift": list(copy.ownership_drift),
                "probeError": copy.probe_error,
            }
            for copy in copies
        ],
        "items": [
            {
                "path": copy.path,
                "kind": copy.kind,
                "branch": copy.branch,
                "ahead": copy.ahead,
                "behind": copy.behind,
                "dirty": copy.dirty,
                "ownershipDrift": list(copy.ownership_drift),
                "stashes": copy.stashes,
                "staleDays": round(copy.stale_days(now=moment), 1),
                "overdue": copy.is_overdue(policy, now=moment),
                "probeError": copy.probe_error,
            }
            for copy in pending
        ],
    }

"""执行分支治理（branch-policy 单一真相源）。

P4 主干归一：移除「homepage-only 内容类型 → 临时 feature 分支」绑定。
分支不再是内容类型配置；商业执行只认 `quwoquan_ops/policies/branch_policy.yaml`
声明的正式 mainline 分支（allowed_local_branches）。执行实例照旧把当前
branch/commit 冻结进 spec/证据（可重放审计），但校验对象是 branch policy，
不是任何按内容类型推导出来的分支。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

_BRANCH_POLICY_RELPATH = Path("quwoquan_ops") / "policies" / "branch_policy.yaml"


def _repo_root() -> Path:
    from core.paths import REPO_ROOT

    return Path(REPO_ROOT)


def _quota_int(spec: Mapping[str, Any] | None, key: str) -> int:
    content = (spec or {}).get("content") if isinstance(spec, Mapping) else {}
    quotas = content.get("quotas") if isinstance(content, Mapping) else {}
    quotas = quotas if isinstance(quotas, Mapping) else {}
    try:
        return int(quotas.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def is_homepage_only_spec(spec: Mapping[str, Any] | None = None) -> bool:
    """内容形态判定（homepage-only 任务跳过 article/image stage 用）。

    仅描述任务配额形态，与 Git 分支无关（分支绑定已于商用收口 P4 拆除）。
    """
    return (
        _quota_int(spec, "entityHomepagesPerTarget") > 0
        and _quota_int(spec, "entityArticlesPerTarget") <= 0
        and _quota_int(spec, "imageWorksPerTarget") <= 0
        and _quota_int(spec, "routeArticles") <= 0
    )


def current_git_branch(*, cwd: str | Path | None = None) -> str:
    root = str(Path(cwd).resolve()) if cwd else None
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return ""
    if result.returncode != 0:
        return ""
    return str(result.stdout or "").strip()


def current_git_commit(*, cwd: str | Path | None = None) -> str:
    root = str(Path(cwd).resolve()) if cwd else None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return ""
    if result.returncode != 0:
        return ""
    return str(result.stdout or "").strip()


def branch_policy_allowed_branches(*, repo_root: str | Path | None = None) -> list[str]:
    """读取 branch policy 的 allowed_local_branches（缺文件即 fail-closed 空表）。"""
    import yaml

    root = Path(repo_root) if repo_root else _repo_root()
    policy_path = root / _BRANCH_POLICY_RELPATH
    if not policy_path.is_file():
        return []
    doc = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    rows = doc.get("allowed_local_branches") if isinstance(doc, dict) else []
    return [str(row).strip() for row in rows or [] if str(row).strip()]


def resolve_execution_branch(
    spec: Mapping[str, Any] | None = None,
    *,
    cwd: str | Path | None = None,
) -> str:
    """执行分支 = 当前 git 分支（证据用途）。

    历史遗留 spec 中的 executionPolicy.executionBranch 只作记录，不参与解析，
    防止旧 feature 分支冻结值把新批锁死在已废止分支上。
    """
    return current_git_branch(cwd=cwd or _repo_root())


def stamp_execution_branch(
    spec: dict[str, Any],
    *,
    cwd: str | Path | None = None,
) -> str:
    """把当前正式分支与 commit 冻结进 spec（生成期证据；可重放审计）。"""
    workflow = spec.setdefault("executionPolicy", {})
    if not isinstance(workflow, dict):
        raise ValueError("executionPolicy must be a mapping")
    branch = current_git_branch(cwd=cwd or _repo_root())
    if branch:
        workflow["executionBranch"] = branch
    commit = current_git_commit(cwd=cwd or _repo_root())
    if commit:
        workflow["gitCommitSha"] = commit
    return branch


def execution_branch_payload(
    spec: Mapping[str, Any] | None = None,
    *,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    workflow = (spec or {}).get("executionPolicy") if isinstance(spec, Mapping) else {}
    workflow = workflow if isinstance(workflow, Mapping) else {}
    return {
        "stampedExecutionBranch": str(workflow.get("executionBranch") or "").strip(),
        "stampedGitCommitSha": str(workflow.get("gitCommitSha") or "").strip(),
        "currentGitBranch": current_git_branch(cwd=cwd or _repo_root()),
        "currentGitCommitSha": current_git_commit(cwd=cwd or _repo_root()),
        "allowedBranches": branch_policy_allowed_branches(),
    }


def execution_branch_issues(
    spec: Mapping[str, Any] | None = None,
    *,
    cwd: str | Path | None = None,
) -> list[str]:
    """商业执行分支门：当前分支必须在 branch policy allowlist 内。"""
    del spec  # 分支不再由任务内容类型推导；历史 spec 冻结值仅是证据。
    allowed = branch_policy_allowed_branches()
    actual = current_git_branch(cwd=cwd or _repo_root())
    issues: list[str] = []
    if not allowed:
        issues.append(
            f"branch policy 缺失或为空（{_BRANCH_POLICY_RELPATH}）；商业执行 fail-closed"
        )
        return issues
    if not actual:
        issues.append("current git branch is unavailable; cannot verify branch policy")
        return issues
    if actual not in allowed:
        issues.append(
            f"当前 git 分支 {actual!r} 不在正式分支 allowlist {allowed}；"
            "商业执行只允许 mainline（临时 feature 分支绑定已废止）"
        )
    return issues


__all__ = [
    "branch_policy_allowed_branches",
    "current_git_branch",
    "current_git_commit",
    "execution_branch_issues",
    "execution_branch_payload",
    "is_homepage_only_spec",
    "resolve_execution_branch",
    "stamp_execution_branch",
]

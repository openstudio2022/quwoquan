"""商业分支门必须锚定代码树根，不受 lane 子进程 cwd 影响。

Campaign capsule lane 子进程的 cwd 是 execution root（.qwq_output/data/tasks/<id>），
那里没有 quwoquan_ops/policies/branch_policy.yaml。分支门若以 Path.cwd() 为锚，
managed preflight 会错误 fail-closed（历史缺陷：三条 M100 lane 全部 rc=2 静默退出）。
"""
from __future__ import annotations

import os
from pathlib import Path

from core.execution_branch import (
    branch_policy_allowed_branches,
    execution_branch_issues,
)


def test_repository_policy_exposes_integration_and_release_branches() -> None:
    assert branch_policy_allowed_branches() == ["dev1.0", "main"]


def test_branch_gate_resolves_policy_from_tree_root_not_process_cwd(
    tmp_path: Path,
) -> None:
    empty_execution_root = tmp_path / "execution-root"
    empty_execution_root.mkdir()
    previous_cwd = Path.cwd()
    os.chdir(empty_execution_root)
    try:
        issues = execution_branch_issues({})
    finally:
        os.chdir(previous_cwd)

    assert not any("branch policy 缺失或为空" in issue for issue in issues), issues


def test_branch_gate_fails_closed_when_anchored_root_lacks_policy(
    tmp_path: Path,
) -> None:
    bare_root = tmp_path / "bare-root"
    bare_root.mkdir()

    assert branch_policy_allowed_branches(repo_root=bare_root) == []
    issues = execution_branch_issues({}, cwd=bare_root)
    assert any("branch policy 缺失或为空" in issue for issue in issues)

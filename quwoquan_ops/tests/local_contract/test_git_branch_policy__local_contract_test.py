from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_git_branch_policy import branch_policy_issues


def test_branch_policy_accepts_dev1_only_locally_and_main_remotely() -> None:
    issues = branch_policy_issues(
        allowed_local={"dev1.0"},
        allowed_remote={"dev1.0", "main"},
        local_branches=["dev1.0"],
        remote_branches=["dev1.0", "main"],
        current_branch="dev1.0",
    )

    assert issues == []


def test_branch_policy_rejects_extra_local_branch() -> None:
    issues = branch_policy_issues(
        allowed_local={"dev1.0"},
        allowed_remote={"dev1.0", "main"},
        local_branches=["dev1.0", "feature/demo"],
        remote_branches=["dev1.0", "main"],
        current_branch="feature/demo",
    )

    assert any("feature/demo" in issue for issue in issues)


def test_branch_policy_rejects_local_main_branch() -> None:
    issues = branch_policy_issues(
        allowed_local={"dev1.0"},
        allowed_remote={"dev1.0", "main"},
        local_branches=["dev1.0", "main"],
        remote_branches=["dev1.0", "main"],
        current_branch="main",
    )

    assert any("current branch 'main'" in issue for issue in issues)
    assert any("unexpected local branches: main" in issue for issue in issues)


def test_branch_policy_rejects_extra_remote_branch() -> None:
    issues = branch_policy_issues(
        allowed_local={"dev1.0"},
        allowed_remote={"dev1.0", "main"},
        local_branches=["dev1.0"],
        remote_branches=["cursor/demo", "dev1.0", "main"],
        current_branch="dev1.0",
    )

    assert any("cursor/demo" in issue for issue in issues)

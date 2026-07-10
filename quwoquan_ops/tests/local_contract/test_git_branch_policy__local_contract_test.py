from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_git_branch_policy import branch_policy_issues


def test_branch_policy_accepts_dev_and_main_only() -> None:
    issues = branch_policy_issues(
        allowed_local={"dev1.0", "main"},
        allowed_remote={"dev1.0", "main"},
        local_branches=["dev1.0", "main"],
        remote_branches=["dev1.0", "main"],
        current_branch="dev1.0",
    )

    assert issues == []


def test_branch_policy_rejects_extra_local_branch() -> None:
    issues = branch_policy_issues(
        allowed_local={"dev1.0", "main"},
        allowed_remote={"dev1.0", "main"},
        local_branches=["dev1.0", "feature/demo", "main"],
        remote_branches=["dev1.0", "main"],
        current_branch="feature/demo",
    )

    assert any("feature/demo" in issue for issue in issues)


def test_branch_policy_rejects_extra_remote_branch() -> None:
    issues = branch_policy_issues(
        allowed_local={"dev1.0", "main"},
        allowed_remote={"dev1.0", "main"},
        local_branches=["dev1.0", "main"],
        remote_branches=["cursor/demo", "dev1.0", "main"],
        current_branch="dev1.0",
    )

    assert any("cursor/demo" in issue for issue in issues)

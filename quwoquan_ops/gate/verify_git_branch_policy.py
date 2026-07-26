#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "quwoquan_ops/policies/branch_policy.yaml"


def _run_git(*args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def load_policy() -> tuple[set[str], set[str]]:
    payload = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")) or {}
    allowed_local = {str(name).strip() for name in payload.get("allowed_local_branches", []) if str(name).strip()}
    allowed_remote = {str(name).strip() for name in payload.get("allowed_remote_branches", []) if str(name).strip()}
    return allowed_local, allowed_remote


def branch_policy_issues(
    *,
    allowed_local: set[str],
    allowed_remote: set[str],
    local_branches: list[str],
    remote_branches: list[str],
    current_branch: str | None,
    ci_head_branch: str | None = None,
) -> list[str]:
    issues: list[str] = []
    if not current_branch:
        if ci_head_branch in allowed_local:
            # GitHub pull_request checks out the synthetic merge commit detached.
            # The source branch is still required to be the sole allowed local
            # development branch; arbitrary detached local work stays forbidden.
            pass
        else:
            issues.append("detached HEAD is forbidden; work on dev1.0 and merge to main explicitly")
    elif current_branch not in allowed_local:
        issues.append(f"current branch '{current_branch}' is not allowed; only {sorted(allowed_local)} may receive commits")

    extra_local = sorted(branch for branch in local_branches if branch not in allowed_local)
    extra_remote = sorted(branch for branch in remote_branches if branch not in allowed_remote)
    if extra_local:
        issues.append(f"unexpected local branches: {', '.join(extra_local)}")
    if extra_remote:
        issues.append(f"unexpected remote branches: {', '.join(extra_remote)}")
    return issues


def current_repo_issues() -> list[str]:
    allowed_local, allowed_remote = load_policy()
    local_branches = _run_git("for-each-ref", "--format=%(refname:short)", "refs/heads")
    remote_branches = [
        ref[len("origin/") :]
        for ref in _run_git("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin")
        if ref not in {"origin", "origin/HEAD"}
    ]
    current_branch = None
    try:
        current_branch = _run_git("symbolic-ref", "--quiet", "--short", "HEAD")[0]
    except (subprocess.CalledProcessError, IndexError):
        current_branch = None
    ci_head_branch = None
    if os.environ.get("GITHUB_ACTIONS") == "true":
        ci_head_branch = os.environ.get("GITHUB_HEAD_REF", "").strip() or None
    return branch_policy_issues(
        allowed_local=allowed_local,
        allowed_remote=allowed_remote,
        local_branches=local_branches,
        remote_branches=remote_branches,
        current_branch=current_branch,
        ci_head_branch=ci_head_branch,
    )


def main() -> int:
    issues = current_repo_issues()
    if issues:
        print("[verify_git_branch_policy] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_git_branch_policy] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

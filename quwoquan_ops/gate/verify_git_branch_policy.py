#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
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


def load_policy() -> tuple[set[str], set[str], set[str]]:
    payload = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")) or {}
    allowed_local = {str(name).strip() for name in payload.get("allowed_local_branches", []) if str(name).strip()}
    allowed_remote = {str(name).strip() for name in payload.get("allowed_remote_branches", []) if str(name).strip()}
    pull_request_prefixes = {
        str(prefix).strip()
        for prefix in payload.get("pull_request_branch_prefixes", [])
        if str(prefix).strip()
    }
    return allowed_local, allowed_remote, pull_request_prefixes


def _matches_pull_request_prefix(branch: str | None, prefixes: set[str]) -> bool:
    return bool(branch) and any(branch.startswith(prefix) for prefix in prefixes)


def pull_request_branch_from_environment(environment: dict[str, str]) -> str | None:
    """Return the reviewed source branch for GitHub's detached PR merge checkout."""
    if environment.get("GITHUB_ACTIONS") != "true":
        return None
    if environment.get("GITHUB_EVENT_NAME") != "pull_request":
        return None
    head_ref = environment.get("GITHUB_HEAD_REF", "").strip()
    return head_ref or None


def branch_policy_issues(
    *,
    allowed_local: set[str],
    allowed_remote: set[str],
    pull_request_prefixes: set[str],
    local_branches: list[str],
    remote_branches: list[str],
    current_branch: str | None,
    ci_head_branch: str | None = None,
) -> list[str]:
    issues: list[str] = []
    active_pull_request_branch = (
        current_branch
        if _matches_pull_request_prefix(current_branch, pull_request_prefixes)
        else None
    )
    if not current_branch:
        if ci_head_branch in allowed_local or _matches_pull_request_prefix(
            ci_head_branch, pull_request_prefixes
        ):
            # GitHub pull_request checks out the synthetic merge commit detached.
            # The source branch is still required to be the sole allowed local
            # development branch; arbitrary detached local work stays forbidden.
            pass
        else:
            issues.append(
                "detached HEAD is forbidden; work on main or an active pull-request branch"
            )
    elif current_branch not in allowed_local and active_pull_request_branch is None:
        issues.append(
            f"current branch '{current_branch}' is not allowed; main is the only long-lived branch"
        )

    permitted_local = allowed_local | ({active_pull_request_branch} if active_pull_request_branch else set())
    reviewed_pull_request_branch = (
        ci_head_branch
        if _matches_pull_request_prefix(ci_head_branch, pull_request_prefixes)
        else active_pull_request_branch
    )
    permitted_remote = allowed_remote | (
        {reviewed_pull_request_branch} if reviewed_pull_request_branch else set()
    )
    extra_local = sorted(branch for branch in local_branches if branch not in permitted_local)
    extra_remote = sorted(branch for branch in remote_branches if branch not in permitted_remote)
    if extra_local:
        issues.append(f"unexpected local branches: {', '.join(extra_local)}")
    if extra_remote:
        issues.append(f"unexpected remote branches: {', '.join(extra_remote)}")
    return issues


def current_repo_issues() -> list[str]:
    allowed_local, allowed_remote, pull_request_prefixes = load_policy()
    local_branches = _run_git("for-each-ref", "--format=%(refname:short)", "refs/heads")
    remote_branches = [
        ref[len("origin/") :]
        for ref in _run_git("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin")
        if ref not in {"origin", "origin/HEAD"}
    ]
    current_branch = None
    ci_head_branch = pull_request_branch_from_environment(dict(os.environ))
    try:
        current_branch = _run_git("symbolic-ref", "--quiet", "--short", "HEAD")[0]
    except (subprocess.CalledProcessError, IndexError):
        current_branch = ci_head_branch
    return branch_policy_issues(
        allowed_local=allowed_local,
        allowed_remote=allowed_remote,
        pull_request_prefixes=pull_request_prefixes,
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

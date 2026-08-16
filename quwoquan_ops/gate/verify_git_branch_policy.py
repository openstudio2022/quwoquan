#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "quwoquan_ops/policies/branch_policy.yaml"
ZERO_SHA = "0" * 40


@dataclass(frozen=True)
class PullRequestEdge:
    base: str
    head: str | None = None
    head_prefix: str | None = None

    def matches(self, *, head: str, base: str) -> bool:
        if base != self.base:
            return False
        if self.head is not None:
            return head == self.head
        return bool(self.head_prefix) and head.startswith(self.head_prefix)


@dataclass(frozen=True)
class SystemBacksync:
    head: str
    base: str
    mode: str


@dataclass(frozen=True)
class BranchPolicy:
    allowed_local: frozenset[str]
    allowed_remote: frozenset[str]
    pull_request_prefixes: frozenset[str]
    integration_branch: str
    release_branch: str
    production_source_branch: str
    allowed_pull_request_edges: tuple[PullRequestEdge, ...]
    system_backsync: SystemBacksync | None


def _run_git(*args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"branch policy requires non-empty {key}")
    return value


def _string_set(payload: Mapping[str, object], key: str) -> frozenset[str]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise TypeError(f"branch policy {key} must be a list")
    rows = [str(value).strip() for value in raw if str(value).strip()]
    if not rows or len(rows) != len(set(rows)):
        raise ValueError(f"branch policy {key} must be non-empty and duplicate-free")
    return frozenset(rows)


def _pull_request_edges(payload: Mapping[str, object]) -> tuple[PullRequestEdge, ...]:
    raw = payload.get("allowed_pull_request_edges")
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            "branch policy allowed_pull_request_edges must be a non-empty list"
        )
    edges: list[PullRequestEdge] = []
    for index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise TypeError(
                f"branch policy allowed_pull_request_edges[{index}] must be a mapping"
            )
        base = _required_string(value, "base")
        head = str(value.get("head") or "").strip() or None
        head_prefix = str(value.get("head_prefix") or "").strip() or None
        if (head is None) == (head_prefix is None):
            raise ValueError(
                f"branch policy allowed_pull_request_edges[{index}] requires exactly one of head/head_prefix"
            )
        edges.append(PullRequestEdge(base=base, head=head, head_prefix=head_prefix))
    if len(edges) != len(set(edges)):
        raise ValueError(
            "branch policy allowed_pull_request_edges must be duplicate-free"
        )
    return tuple(edges)


def _system_backsync(payload: Mapping[str, object]) -> SystemBacksync | None:
    raw = payload.get("system_backsync")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise TypeError("branch policy system_backsync must be a mapping")
    return SystemBacksync(
        head=_required_string(raw, "head"),
        base=_required_string(raw, "base"),
        mode=_required_string(raw, "mode"),
    )


def load_policy(path: Path = POLICY_PATH) -> BranchPolicy:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise TypeError("branch policy root must be a mapping")
    policy = BranchPolicy(
        allowed_local=_string_set(payload, "allowed_local_branches"),
        allowed_remote=_string_set(payload, "allowed_remote_branches"),
        pull_request_prefixes=_string_set(payload, "pull_request_branch_prefixes"),
        integration_branch=_required_string(payload, "integration_branch"),
        release_branch=_required_string(payload, "release_branch"),
        production_source_branch=_required_string(payload, "production_source_branch"),
        allowed_pull_request_edges=_pull_request_edges(payload),
        system_backsync=_system_backsync(payload),
    )
    for branch_name in (
        policy.integration_branch,
        policy.release_branch,
        policy.production_source_branch,
    ):
        if (
            branch_name not in policy.allowed_local
            or branch_name not in policy.allowed_remote
        ):
            raise ValueError(
                f"branch policy role branch {branch_name!r} must be allowed both locally and remotely"
            )
    if policy.production_source_branch != policy.release_branch:
        raise ValueError(
            "branch policy production_source_branch must equal release_branch"
        )
    for edge in policy.allowed_pull_request_edges:
        if edge.base not in policy.allowed_remote:
            raise ValueError(
                f"branch policy PR base {edge.base!r} is not an allowed remote branch"
            )
        if edge.head is not None and edge.head not in policy.allowed_local:
            raise ValueError(
                f"branch policy PR head {edge.head!r} is not an allowed local branch"
            )
        if (
            edge.head_prefix is not None
            and edge.head_prefix not in policy.pull_request_prefixes
        ):
            raise ValueError(
                f"branch policy PR head_prefix {edge.head_prefix!r} is not a declared pull-request prefix"
            )
    if policy.integration_branch == policy.release_branch:
        if policy.system_backsync is not None:
            raise ValueError(
                "branch policy with one integration/release branch cannot declare backsync"
            )
    else:
        expected_backsync = SystemBacksync(
            head=policy.release_branch,
            base=policy.integration_branch,
            mode="fast_forward_only",
        )
        if policy.system_backsync != expected_backsync:
            raise ValueError(
                "branch policy system_backsync must be release -> integration and fast_forward_only"
            )
    return policy


def _matches_pull_request_prefix(branch: str | None, prefixes: frozenset[str]) -> bool:
    return bool(branch) and any(branch.startswith(prefix) for prefix in prefixes)


def pull_request_context_from_environment(
    environment: Mapping[str, str],
) -> tuple[str | None, str | None]:
    """Return the reviewed source/base pair for GitHub's detached PR checkout."""
    if environment.get("GITHUB_ACTIONS") != "true":
        return None, None
    if environment.get("GITHUB_EVENT_NAME") != "pull_request":
        return None, None
    head_ref = environment.get("GITHUB_HEAD_REF", "").strip() or None
    base_ref = environment.get("GITHUB_BASE_REF", "").strip() or None
    return head_ref, base_ref


def branch_policy_issues(
    *,
    policy: BranchPolicy,
    local_branches: list[str],
    remote_branches: list[str],
    current_branch: str | None,
    ci_head_branch: str | None = None,
    ci_base_branch: str | None = None,
) -> list[str]:
    issues: list[str] = []
    active_pull_request_branch = (
        current_branch
        if _matches_pull_request_prefix(current_branch, policy.pull_request_prefixes)
        else None
    )
    has_pr_context = ci_head_branch is not None or ci_base_branch is not None
    if has_pr_context:
        if not ci_head_branch or not ci_base_branch:
            issues.append("pull-request branch policy requires both head and base refs")
        elif not any(
            edge.matches(head=ci_head_branch, base=ci_base_branch)
            for edge in policy.allowed_pull_request_edges
        ):
            issues.append(
                f"pull-request edge '{ci_head_branch} -> {ci_base_branch}' is not allowed"
            )

    if not current_branch:
        if ci_head_branch in policy.allowed_local or _matches_pull_request_prefix(
            ci_head_branch, policy.pull_request_prefixes
        ):
            pass
        else:
            issues.append(
                "detached HEAD is forbidden; use a declared long-lived or reviewed pull-request branch"
            )
    elif (
        current_branch not in policy.allowed_local
        and active_pull_request_branch is None
    ):
        issues.append(
            f"current branch '{current_branch}' is not allowed; declared long-lived branches are "
            f"{sorted(policy.allowed_local)}"
        )

    permitted_local = set(policy.allowed_local)
    if active_pull_request_branch:
        permitted_local.add(active_pull_request_branch)
    if ci_head_branch and (
        ci_head_branch in policy.allowed_local
        or _matches_pull_request_prefix(ci_head_branch, policy.pull_request_prefixes)
    ):
        permitted_local.add(ci_head_branch)
    permitted_remote = set(policy.allowed_remote)
    if ci_head_branch and _matches_pull_request_prefix(
        ci_head_branch, policy.pull_request_prefixes
    ):
        permitted_remote.add(ci_head_branch)
    elif active_pull_request_branch:
        permitted_remote.add(active_pull_request_branch)

    extra_local = sorted(
        branch for branch in local_branches if branch not in permitted_local
    )
    extra_remote = sorted(
        branch for branch in remote_branches if branch not in permitted_remote
    )
    if extra_local:
        issues.append(f"unexpected local branches: {', '.join(extra_local)}")
    if extra_remote:
        issues.append(f"unexpected remote branches: {', '.join(extra_remote)}")
    return issues


def current_repo_issues() -> list[str]:
    policy = load_policy()
    local_branches = _run_git("for-each-ref", "--format=%(refname:short)", "refs/heads")
    remote_branches = [
        ref[len("origin/") :]
        for ref in _run_git(
            "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"
        )
        if ref not in {"origin", "origin/HEAD"}
    ]
    ci_head_branch, ci_base_branch = pull_request_context_from_environment(os.environ)
    try:
        current_branch = _run_git("symbolic-ref", "--quiet", "--short", "HEAD")[0]
    except (subprocess.CalledProcessError, IndexError):
        current_branch = None
    return branch_policy_issues(
        policy=policy,
        local_branches=local_branches,
        remote_branches=remote_branches,
        current_branch=current_branch,
        ci_head_branch=ci_head_branch,
        ci_base_branch=ci_base_branch,
    )


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=ROOT,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def pre_push_issues(
    *,
    policy: BranchPolicy,
    current_branch: str | None,
    update_lines: Iterable[str],
    environment: Mapping[str, str],
    is_ancestor: Callable[[str, str], bool] = _git_is_ancestor,
) -> list[str]:
    issues: list[str] = []
    if not current_branch:
        return ["detached HEAD is forbidden; push from a declared branch"]
    if current_branch not in policy.allowed_local and not _matches_pull_request_prefix(
        current_branch, policy.pull_request_prefixes
    ):
        issues.append(
            f"current branch '{current_branch}' is not allowed; declared long-lived branches are "
            f"{sorted(policy.allowed_local)}"
        )

    system_backsync_requested = (
        environment.get("GITHUB_ACTIONS") == "true"
        and environment.get("QWQ_SYSTEM_BRANCH_BACKSYNC") == "true"
    )
    parsed_updates: list[tuple[str, str, str, str]] = []
    for raw_line in update_lines:
        fields = raw_line.strip().split()
        if not fields:
            continue
        if len(fields) != 4:
            issues.append(
                "pre-push update must contain local_ref local_sha remote_ref remote_sha"
            )
            continue
        parsed_updates.append((fields[0], fields[1], fields[2], fields[3]))

    for local_ref, local_sha, remote_ref, remote_sha in parsed_updates:
        if not remote_ref.startswith("refs/heads/") or local_sha == ZERO_SHA:
            continue
        remote_branch = remote_ref.removeprefix("refs/heads/")
        if _matches_pull_request_prefix(remote_branch, policy.pull_request_prefixes):
            if (
                remote_branch != current_branch
                or local_ref != f"refs/heads/{current_branch}"
            ):
                issues.append(
                    f"temporary branch push must update its matching remote ref: {current_branch!r}"
                )
            continue
        if remote_branch not in policy.allowed_remote:
            issues.append(
                f"push to undeclared remote branch '{remote_branch}' is blocked"
            )
            continue
        backsync = policy.system_backsync
        if (
            system_backsync_requested
            and backsync is not None
            and remote_branch == backsync.base
            and current_branch == backsync.head
            and local_ref == f"refs/heads/{backsync.head}"
            and remote_sha != ZERO_SHA
            and is_ancestor(remote_sha, local_sha)
        ):
            continue
        if remote_branch == policy.integration_branch:
            issues.append(
                f"direct update of '{remote_branch}' is blocked; use codex/* -> "
                f"{policy.integration_branch} PR or the system fast-forward backsync"
            )
        elif remote_branch == policy.release_branch:
            issues.append(
                f"direct update of '{remote_branch}' is blocked; use "
                f"{policy.integration_branch} -> {policy.release_branch} promotion PR"
            )
        else:
            issues.append(
                f"direct update of long-lived branch '{remote_branch}' is blocked"
            )
    return issues


def _current_branch() -> str | None:
    try:
        return _run_git("symbolic-ref", "--quiet", "--short", "HEAD")[0]
    except (subprocess.CalledProcessError, IndexError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the canonical Git branch policy"
    )
    parser.add_argument(
        "--pre-push",
        action="store_true",
        help="validate pre-push update lines from stdin",
    )
    args = parser.parse_args(argv)
    try:
        if args.pre_push:
            issues = pre_push_issues(
                policy=load_policy(),
                current_branch=_current_branch(),
                update_lines=sys.stdin,
                environment=os.environ,
            )
        else:
            issues = current_repo_issues()
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        issues = [f"branch policy is invalid: {exc}"]
    if issues:
        print("[verify_git_branch_policy] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_git_branch_policy] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

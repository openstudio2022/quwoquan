#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "quwoquan_ops/policies/branch_policy.yaml"
ZERO_SHA = "0" * 40
FAILURE_CODE_KEYS = frozenset(
    {
        "policy_invalid",
        "ref_not_allowed",
        "direct_push_not_allowed",
        "backsync_not_fast_forward",
        "backsync_cas_conflict",
        "authority_unavailable",
        "source_not_main_reachable",
    }
)
FAILURE_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True)
class PullRequestEdge:
    base: str
    head: str

    def matches(self, *, head: str, base: str) -> bool:
        if base != self.base:
            return False
        if self.head.endswith("*"):
            return head.startswith(self.head[:-1])
        return head == self.head

    @property
    def prefix(self) -> str | None:
        return self.head[:-1] if self.head.endswith("*") else None


@dataclass(frozen=True)
class SystemBacksync:
    head: str
    base: str
    mode: str


@dataclass(frozen=True)
class RequiredPromotionCheck:
    name: str
    workflow: str


@dataclass(frozen=True)
class BranchPolicy:
    allowed_local: frozenset[str]
    allowed_remote: frozenset[str]
    pull_request_prefixes: frozenset[str]
    integration_branch: str
    release_branch: str
    production_source_branch: str
    production_workflow: str
    required_promotion_checks: tuple[RequiredPromotionCheck, ...]
    allowed_pull_request_edges: tuple[PullRequestEdge, ...]
    system_backsync: SystemBacksync | None
    failure_codes: tuple[tuple[str, str], ...]

    def failure_code(self, name: str) -> str:
        for key, code in self.failure_codes:
            if key == name:
                return code
        raise KeyError(name)


@dataclass(frozen=True)
class BranchTransition:
    event: str
    actor_kind: str
    repository: str
    head: str | None = None
    base: str | None = None
    before_oid: str | None = None
    after_oid: str | None = None
    refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class BranchDecision:
    status: str
    reason_code: str | None = None
    string_context: tuple[tuple[str, str], ...] = ()

    @property
    def allowed(self) -> bool:
        return self.status == "allowed"


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


def _required_promotion_checks(
    payload: Mapping[str, object],
) -> tuple[RequiredPromotionCheck, ...]:
    key = "required_promotion_checks"
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise TypeError(f"branch policy {key} must be a list")
    rows: list[RequiredPromotionCheck] = []
    for index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise TypeError(f"branch policy {key}[{index}] must be a mapping")
        rows.append(
            RequiredPromotionCheck(
                name=_required_string(value, "name"),
                workflow=_required_string(value, "workflow"),
            )
        )
    if not rows or len(rows) != len(set(rows)):
        raise ValueError(f"branch policy {key} must be non-empty and duplicate-free")
    if len({row.name for row in rows}) != len(rows):
        raise ValueError(f"branch policy {key} names must be duplicate-free")
    if len({row.workflow for row in rows}) != len(rows):
        raise ValueError(f"branch policy {key} workflows must be duplicate-free")
    for row in rows:
        if not row.workflow.startswith(".github/workflows/") or not row.workflow.endswith(
            (".yml", ".yaml")
        ):
            raise ValueError(
                f"branch policy {key} workflow must be a repository workflow path"
            )
    return tuple(rows)


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
        head = _required_string(value, "head")
        if "*" in head and (not head.endswith("*") or head.count("*") != 1):
            raise ValueError(
                f"branch policy allowed_pull_request_edges[{index}].head only supports a single trailing wildcard"
            )
        edges.append(PullRequestEdge(base=base, head=head))
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


def _failure_codes(payload: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    raw = payload.get("failure_codes")
    if not isinstance(raw, Mapping):
        raise TypeError("branch policy failure_codes must be a mapping")
    keys = frozenset(str(key) for key in raw)
    if keys != FAILURE_CODE_KEYS:
        missing = sorted(FAILURE_CODE_KEYS - keys)
        unexpected = sorted(keys - FAILURE_CODE_KEYS)
        raise ValueError(
            "branch policy failure_codes must contain the exact canonical keys; "
            f"missing={missing}, unexpected={unexpected}"
        )
    rows: list[tuple[str, str]] = []
    for key in sorted(FAILURE_CODE_KEYS):
        code = str(raw.get(key) or "").strip()
        if not FAILURE_CODE_PATTERN.fullmatch(code):
            raise ValueError(
                f"branch policy failure_codes.{key} must use MODULE.KIND.REASON"
            )
        rows.append((key, code))
    if len({code for _, code in rows}) != len(rows):
        raise ValueError("branch policy failure_codes must be duplicate-free")
    return tuple(rows)


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
        production_workflow=_required_string(payload, "production_workflow"),
        required_promotion_checks=_required_promotion_checks(payload),
        allowed_pull_request_edges=_pull_request_edges(payload),
        system_backsync=_system_backsync(payload),
        failure_codes=_failure_codes(payload),
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
    if not policy.production_workflow.startswith(
        ".github/workflows/"
    ) or not policy.production_workflow.endswith((".yml", ".yaml")):
        raise ValueError(
            "branch policy production_workflow must be a repository workflow path"
        )
    for edge in policy.allowed_pull_request_edges:
        if edge.base not in policy.allowed_remote:
            raise ValueError(
                f"branch policy PR base {edge.base!r} is not an allowed remote branch"
            )
        if edge.prefix is None and edge.head not in policy.allowed_local:
            raise ValueError(
                f"branch policy PR head {edge.head!r} is not an allowed local branch"
            )
        if edge.prefix is not None and edge.prefix not in policy.pull_request_prefixes:
            raise ValueError(
                f"branch policy PR head pattern {edge.head!r} is not a declared pull-request prefix"
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
            mode="fast-forward-only",
        )
        if policy.system_backsync != expected_backsync:
            raise ValueError(
                "branch policy system_backsync must be release -> integration and fast-forward-only"
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


def _decision_context(**values: str | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, value) for key, value in values.items() if value))


def evaluate_transition(
    *,
    policy: BranchPolicy,
    transition: BranchTransition,
    is_ancestor: Callable[[str, str], bool] | None = None,
) -> BranchDecision:
    """Evaluate one immutable branch transition without performing side effects."""

    context = _decision_context(
        event=transition.event,
        actorKind=transition.actor_kind,
        repository=transition.repository,
        head=transition.head,
        base=transition.base,
        beforeOid=transition.before_oid,
        afterOid=transition.after_oid,
    )
    if transition.event == "pull_request":
        if transition.head and transition.base and any(
            edge.matches(head=transition.head, base=transition.base)
            for edge in policy.allowed_pull_request_edges
        ):
            return BranchDecision(status="allowed", string_context=context)
        return BranchDecision(
            status="blocked",
            reason_code=policy.failure_code("ref_not_allowed"),
            string_context=context,
        )
    if transition.event == "direct_push":
        return BranchDecision(
            status="blocked",
            reason_code=policy.failure_code("direct_push_not_allowed"),
            string_context=context,
        )
    if transition.event == "system_backsync":
        backsync = policy.system_backsync
        if (
            transition.actor_kind != "system"
            or backsync is None
            or transition.head != backsync.head
            or transition.base != backsync.base
            or not transition.before_oid
            or not transition.after_oid
        ):
            return BranchDecision(
                status="blocked",
                reason_code=policy.failure_code("ref_not_allowed"),
                string_context=context,
            )
        if transition.before_oid == transition.after_oid:
            return BranchDecision(status="allowed", string_context=context)
        if is_ancestor is None:
            return BranchDecision(
                status="blocked",
                reason_code=policy.failure_code("authority_unavailable"),
                string_context=context,
            )
        try:
            ancestor = is_ancestor(transition.before_oid, transition.after_oid)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return BranchDecision(
                status="blocked",
                reason_code=policy.failure_code("authority_unavailable"),
                string_context=context,
            )
        if ancestor:
            return BranchDecision(status="allowed", string_context=context)
        return BranchDecision(
            status="blocked",
            reason_code=policy.failure_code("backsync_not_fast_forward"),
            string_context=context,
        )
    return BranchDecision(
        status="blocked",
        reason_code=policy.failure_code("policy_invalid"),
        string_context=context,
    )


def _issue(policy: BranchPolicy, failure_key: str, message: str) -> str:
    return f"{policy.failure_code(failure_key)}: {message}"


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
            issues.append(
                _issue(
                    policy,
                    "ref_not_allowed",
                    "pull-request branch policy requires both head and base refs",
                )
            )
        else:
            decision = evaluate_transition(
                policy=policy,
                transition=BranchTransition(
                    event="pull_request",
                    actor_kind="github",
                    repository="github",
                    head=ci_head_branch,
                    base=ci_base_branch,
                ),
            )
            if not decision.allowed:
                issues.append(
                    f"{decision.reason_code}: pull-request edge "
                    f"'{ci_head_branch} -> {ci_base_branch}' is not allowed"
                )

    if not current_branch:
        if ci_head_branch in policy.allowed_local or _matches_pull_request_prefix(
            ci_head_branch, policy.pull_request_prefixes
        ):
            pass
        else:
            issues.append(
                _issue(
                    policy,
                    "ref_not_allowed",
                    "detached HEAD is forbidden; use a declared long-lived or reviewed pull-request branch",
                )
            )
    elif (
        current_branch not in policy.allowed_local
        and active_pull_request_branch is None
    ):
        issues.append(
            _issue(
                policy,
                "ref_not_allowed",
                f"current branch '{current_branch}' is not allowed; declared long-lived branches are "
                f"{sorted(policy.allowed_local)}",
            )
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
        issues.append(
            _issue(
                policy,
                "ref_not_allowed",
                f"unexpected local branches: {', '.join(extra_local)}",
            )
        )
    if extra_remote:
        issues.append(
            _issue(
                policy,
                "ref_not_allowed",
                f"unexpected remote branches: {', '.join(extra_remote)}",
            )
        )
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


def pre_push_issues(
    *,
    policy: BranchPolicy,
    current_branch: str | None,
    update_lines: Iterable[str],
    environment: Mapping[str, str],
) -> list[str]:
    issues: list[str] = []
    if not current_branch:
        return [
            _issue(
                policy,
                "ref_not_allowed",
                "detached HEAD is forbidden; push from a declared branch",
            )
        ]
    if current_branch not in policy.allowed_local and not _matches_pull_request_prefix(
        current_branch, policy.pull_request_prefixes
    ):
        issues.append(
            _issue(
                policy,
                "ref_not_allowed",
                f"current branch '{current_branch}' is not allowed; declared long-lived branches are "
                f"{sorted(policy.allowed_local)}",
            )
        )

    parsed_updates: list[tuple[str, str, str, str]] = []
    for raw_line in update_lines:
        fields = raw_line.strip().split()
        if not fields:
            continue
        if len(fields) != 4:
            issues.append(
                _issue(
                    policy,
                    "policy_invalid",
                    "pre-push update must contain local_ref local_sha remote_ref remote_sha",
                )
            )
            continue
        parsed_updates.append((fields[0], fields[1], fields[2], fields[3]))

    for local_ref, local_sha, remote_ref, remote_sha in parsed_updates:
        if not remote_ref.startswith("refs/heads/"):
            continue
        remote_branch = remote_ref.removeprefix("refs/heads/")
        if local_sha == ZERO_SHA:
            if _matches_pull_request_prefix(
                remote_branch, policy.pull_request_prefixes
            ):
                continue
            issues.append(
                _issue(
                    policy,
                    "ref_not_allowed",
                    f"deletion of protected or undeclared branch '{remote_branch}' is blocked",
                )
            )
            continue
        if _matches_pull_request_prefix(remote_branch, policy.pull_request_prefixes):
            if (
                remote_branch != current_branch
                or local_ref != f"refs/heads/{current_branch}"
            ):
                issues.append(
                    _issue(
                        policy,
                        "ref_not_allowed",
                        f"temporary branch push must update its matching remote ref: {current_branch!r}",
                    )
                )
            continue
        if remote_branch not in policy.allowed_remote:
            issues.append(
                _issue(
                    policy,
                    "ref_not_allowed",
                    f"push to undeclared remote branch '{remote_branch}' is blocked",
                )
            )
            continue
        if remote_branch == policy.integration_branch:
            issues.append(
                _issue(
                    policy,
                    "direct_push_not_allowed",
                    f"direct update of '{remote_branch}' is blocked; use codex/* -> "
                    f"{policy.integration_branch} PR or the system fast-forward backsync",
                )
            )
        elif remote_branch == policy.release_branch:
            issues.append(
                _issue(
                    policy,
                    "direct_push_not_allowed",
                    f"direct update of '{remote_branch}' is blocked; use "
                    f"{policy.integration_branch} -> {policy.release_branch} promotion PR",
                )
            )
        else:
            issues.append(
                _issue(
                    policy,
                    "direct_push_not_allowed",
                    f"direct update of long-lived branch '{remote_branch}' is blocked",
                )
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
        issues = [f"OPS.BRANCH.POLICY_INVALID: branch policy is invalid: {exc}"]
    if issues:
        print("[verify_git_branch_policy] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_git_branch_policy] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

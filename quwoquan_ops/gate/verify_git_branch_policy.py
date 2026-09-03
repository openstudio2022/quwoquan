#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
POLICY_PATH = ROOT / "quwoquan_ops/policies/branch_policy.yaml"
POLICY_INVALID_RECOVERY = "repair_canonical_branch_policy"
AUTHORITY_UNAVAILABLE_RECOVERY = "restore_git_authority_then_retry"
ACTIVATION_EVIDENCE_SCHEMA_VERSION = 1
SYSTEM_BACKSYNC_WORKFLOW_REF_SUFFIX = (
    "/.github/workflows/system-backsync.yml@refs/heads/main"
)

from quwoquan_ops.gate.git_branch_policy.policy import (
    ACTIVATION_STATES,
    ACTIVATION_TRANSITION_COMMAND,
    BRANCH_POLICY_FIELDS,
    FAILURE_CODE_KEYS,
    FAILURE_CODE_PATTERN,
    FIXED_PERSISTENT_LANE_BRANCHES,
    RECOVERY_BY_FAILURE_KEY,
    ZERO_SHA,
    BranchDecision,
    BranchPolicy,
    BranchTransition,
    IntegrationBranchActivation,
    PersistentLaneAdmission,
    PullRequestEdge,
    RequiredPromotionCheck,
    SystemBacksync,
    _matches_pull_request_prefix,
    evaluate_transition,
    load_policy as _load_policy,
    load_policy_bytes,
    pull_request_context_from_environment,
    repository_branch_context_from_environment,
)

def _run_git(*args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def load_policy(path: Path = POLICY_PATH) -> BranchPolicy:
    """Read canonical policy bytes once, preserving the public path default."""
    return _load_policy(path)


def _issue(policy: BranchPolicy, failure_key: str, message: str) -> str:
    return (
        f"{policy.failure_code(failure_key)}: terminal=blocked; {message}; "
        f"recovery={RECOVERY_BY_FAILURE_KEY[failure_key]}"
    )


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
        current_branch if current_branch in policy.allowed_local else None
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
                    _issue(
                        policy,
                        "ref_not_allowed",
                        f"pull-request edge '{ci_head_branch} -> {ci_base_branch}' is not allowed",
                    )
                )

    if not current_branch:
        if ci_head_branch in policy.allowed_local:
            pass
        else:
            issues.append(
                _issue(
                    policy,
                    "ref_not_allowed",
                    "detached HEAD is forbidden; use one of the declared repository branches",
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
    if ci_head_branch in policy.allowed_local:
        permitted_local.add(ci_head_branch)
    permitted_remote = set(policy.allowed_remote)
    if ci_head_branch in policy.allowed_remote:
        permitted_remote.add(ci_head_branch)
    elif active_pull_request_branch in policy.allowed_remote:
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


def current_repo_issues(policy: BranchPolicy | None = None) -> list[str]:
    policy = policy or load_policy()
    ci_head_branch, ci_base_branch = pull_request_context_from_environment(os.environ)
    if (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("GITHUB_EVENT_NAME") == "pull_request"
    ):
        # Hosted PR checkout state is an implementation detail. The event's remote
        # head/base pair is the only branch fact this gate needs to authorize.
        return branch_policy_issues(
            policy=policy,
            local_branches=[],
            remote_branches=[],
            current_branch=None,
            ci_head_branch=ci_head_branch,
            ci_base_branch=ci_base_branch,
        )
    local_branches = _run_git("for-each-ref", "--format=%(refname:short)", "refs/heads")
    remote_branches = [
        ref[len("origin/") :]
        for ref in _run_git(
            "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"
        )
        if ref not in {"origin", "origin/HEAD"}
    ]
    hosted_branch = repository_branch_context_from_environment(os.environ)
    current_branch = _current_branch()
    if hosted_branch is not None:
        current_branch = hosted_branch
    issues = branch_policy_issues(
        policy=policy,
        local_branches=local_branches,
        remote_branches=remote_branches,
        current_branch=current_branch,
        ci_head_branch=ci_head_branch,
        ci_base_branch=ci_base_branch,
    )
    # A generic GitHub push event does not carry the update provenance needed to
    # distinguish a direct push from a server-side PR merge. Direct-push decisions
    # are therefore constructed only by explicit update sources such as pre-push.
    return issues


def _failure_key_for_code(policy: BranchPolicy, code: str | None) -> str:
    for key, candidate in policy.failure_codes:
        if candidate == code:
            return key
    return "policy_invalid"


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    raise OSError(_safe_error_detail(RuntimeError(completed.stderr)))


def _is_managed_system_backsync_environment(
    environment: Mapping[str, str],
) -> bool:
    workflow_ref = environment.get("GITHUB_WORKFLOW_REF", "")
    return (
        environment.get("GITHUB_ACTIONS") == "true"
        and environment.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and environment.get("GITHUB_REF_TYPE") == "branch"
        and environment.get("GITHUB_REF_NAME") == "main"
        and environment.get("GITHUB_ACTOR") == "github-actions[bot]"
        and workflow_ref.endswith(SYSTEM_BACKSYNC_WORKFLOW_REF_SUFFIX)
    )


def activation_readback(policy: BranchPolicy) -> dict[str, object]:
    activation = policy.integration_branch_activation
    return {
        "schema_version": ACTIVATION_EVIDENCE_SCHEMA_VERSION,
        "kind": activation.evidence_kind,
        "integration_branch": policy.integration_branch,
        "state": activation.state,
        "transition_command": activation.transition_command,
        "tracked_policy_mutated": False,
    }


def _activation_evidence_path(path_text: str) -> Path:
    path = Path(path_text)
    candidate = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    output_root = (ROOT / ".qwq_output").resolve()
    if candidate == output_root or output_root not in candidate.parents:
        raise ValueError("activation evidence path must be below .qwq_output")
    return candidate


def write_activation_transition_evidence(
    *, policy: BranchPolicy, evidence_path: str
) -> dict[str, object]:
    activation = policy.integration_branch_activation
    if activation.state != "bootstrap":
        raise ValueError(
            "integration branch activation transition requires current state 'bootstrap'"
        )
    path = _activation_evidence_path(evidence_path)
    payload = {
        "schema_version": ACTIVATION_EVIDENCE_SCHEMA_VERSION,
        "kind": activation.evidence_kind,
        "integration_branch": policy.integration_branch,
        "from_state": "bootstrap",
        "proposed_state": "active",
        "policy_sha256": "sha256:" + hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest(),
        "tracked_policy_mutated": False,
        "proposal": {
            "path": str(POLICY_PATH.relative_to(ROOT)),
            "field": "integration_branch_activation.state",
            "current": "bootstrap",
            "replacement": "active",
        },
        "instructions": [
            f"review evidence at {path.relative_to(ROOT)}",
            "change integration_branch_activation.state from bootstrap to active",
            "commit the tracked policy change through the normal human-controlled workflow",
            "run --activation-readback after the active policy is checked out",
        ],
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError("activation evidence already exists; create-once transition refused") from error
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
    return payload


def _emit_json(payload: Mapping[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


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
    if current_branch not in policy.allowed_local:
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
            # 所有声明的长期分支受保护；未声明 ref 同样禁止借删除操作进入协议。
            issues.append(
                _issue(
                    policy,
                    "ref_not_allowed",
                    f"deletion of protected or undeclared branch '{remote_branch}' is blocked",
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
        if _matches_pull_request_prefix(remote_branch, policy.pull_request_prefixes):
            if (
                remote_branch != current_branch
                or local_ref != f"refs/heads/{current_branch}"
            ):
                issues.append(
                    _issue(
                        policy,
                        "ref_not_allowed",
                        f"persistent lane push must update its matching remote ref: {current_branch!r}",
                    )
                )
            continue
        if remote_branch == policy.integration_branch:
            activation = policy.integration_branch_activation
            matching_integration_source = (
                current_branch == policy.integration_branch
                and local_ref == f"refs/heads/{policy.integration_branch}"
            )
            matching_backsync_source = (
                current_branch == policy.release_branch
                and local_ref == f"refs/heads/{policy.release_branch}"
            )
            if activation.state == "bootstrap":
                if not matching_integration_source or remote_sha != ZERO_SHA:
                    issues.append(
                        _issue(
                            policy,
                            "direct_push_not_allowed",
                            f"bootstrap update of '{remote_branch}' is create-only from the "
                            f"matching local {policy.integration_branch} branch",
                        )
                    )
            elif matching_backsync_source and _is_managed_system_backsync_environment(
                environment
            ):
                decision = evaluate_transition(
                    policy=policy,
                    transition=BranchTransition(
                        event="system_backsync",
                        actor_kind="system",
                        repository=environment.get("GITHUB_REPOSITORY", "github"),
                        head=policy.release_branch,
                        base=policy.integration_branch,
                        before_oid=remote_sha,
                        after_oid=local_sha,
                    ),
                    is_ancestor=lambda ancestor, descendant: _git_is_ancestor(
                        ancestor, descendant
                    ),
                )
                if not decision.allowed:
                    failure_key = _failure_key_for_code(policy, decision.reason_code)
                    issues.append(
                        _issue(
                            policy,
                            failure_key,
                            f"managed system backsync to '{remote_branch}' was rejected",
                        )
                    )
            else:
                issues.append(
                    _issue(
                        policy,
                        "direct_push_not_allowed",
                        f"direct update of active integration branch '{remote_branch}' is blocked; "
                        "use a lane pull request or managed system fast-forward backsync",
                    )
                )
            continue
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


def local_commit_issues(
    policy: BranchPolicy, current_branch: str | None,
) -> list[str]:
    """Validate the commit branch, then enforce read-only integration surfaces."""
    if not current_branch:
        return [
            _issue(
                policy,
                "ref_not_allowed",
                "detached HEAD is forbidden; commit from a declared local branch",
            )
        ]
    if current_branch not in policy.allowed_local:
        return [
            _issue(
                policy,
                "ref_not_allowed",
                f"current branch '{current_branch}' is not allowed; declared long-lived branches are "
                f"{sorted(policy.allowed_local)}",
            )
        ]
    if current_branch in {policy.integration_branch, policy.release_branch}:
        return [
            _issue(
                policy,
                "integration_read_only",
                f"local commits on read-only branch '{current_branch}' are blocked",
            )
        ]
    return []


def _current_branch() -> str | None:
    try:
        rows = _run_git("symbolic-ref", "--quiet", "--short", "HEAD")
    except subprocess.CalledProcessError as error:
        if error.returncode == 1:
            return None
        raise
    if not rows:
        raise OSError("git symbolic-ref returned no branch")
    return rows[0]


def _safe_error_detail(error: BaseException) -> str:
    return " ".join(str(error).replace("\x00", "\\x00").split()) or type(error).__name__


def _emit_terminal_failure(*, code: str, detail: str, recovery: str) -> int:
    print("[verify_git_branch_policy] FAIL")
    print(f"  - {code}: terminal=blocked; {detail}; recovery={recovery}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the canonical Git branch policy"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--pre-push",
        action="store_true",
        help="validate pre-push update lines from stdin",
    )
    mode.add_argument(
        "--local-commit",
        action="store_true",
        help="reject local commits from read-only dev1.0/main worktrees",
    )
    mode.add_argument(
        "--activation-readback",
        action="store_true",
        help="print the canonical integration branch activation state",
    )
    mode.add_argument(
        "--activation-transition",
        action="store_true",
        help="create transition evidence and print the tracked-policy proposal",
    )
    parser.add_argument(
        "--evidence-path",
        help="create-once evidence path below .qwq_output for --activation-transition",
    )
    args = parser.parse_args(argv)
    if bool(args.evidence_path) != bool(args.activation_transition):
        parser.error("--evidence-path is required exactly with --activation-transition")
    try:
        policy = load_policy()
    except (OSError, UnicodeError, TypeError, ValueError, yaml.YAMLError) as error:
        return _emit_terminal_failure(
            code="OPS.BRANCH.POLICY_INVALID",
            detail=f"branch policy is invalid: {_safe_error_detail(error)}",
            recovery=POLICY_INVALID_RECOVERY,
        )
    try:
        if args.activation_readback:
            _emit_json(activation_readback(policy))
            return 0
        if args.activation_transition:
            _emit_json(
                write_activation_transition_evidence(
                    policy=policy, evidence_path=args.evidence_path
                )
            )
            return 0
        if args.pre_push:
            issues = pre_push_issues(
                policy=policy,
                current_branch=_current_branch(),
                update_lines=sys.stdin,
                environment=os.environ,
            )
        elif args.local_commit:
            issues = local_commit_issues(
                policy=policy,
                current_branch=_current_branch(),
            )
        else:
            issues = current_repo_issues(policy)
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        return _emit_terminal_failure(
            code=policy.failure_code("authority_unavailable"),
            detail=f"Git authority is unavailable: {_safe_error_detail(error)}",
            recovery=AUTHORITY_UNAVAILABLE_RECOVERY,
        )
    if issues:
        print("[verify_git_branch_policy] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[verify_git_branch_policy] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

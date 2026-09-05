#!/usr/bin/env python3
"""Fail-closed GitHub ruleset, Environment and Actions authority readback."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.lib.github_actions_api import GithubActionsApiError, request_json  # noqa: E402
from quwoquan_ops.gate.verify_git_branch_policy import BranchPolicy, load_policy  # noqa: E402

AUTHORITY_CODE = "OPS.BRANCH.AUTHORITY_UNAVAILABLE"
GITHUB_ACTIONS_APP_ID = 15368
EXPECTED_RUNNER_NAMES = ("quwoquan-local-mac", "quwoquan-local-mac-b")
RELEASE_RUNNER_LABELS = {"self-hosted", "macOS", "ARM64", "quwoquan-release-authority"}
SENSITIVE_ENVIRONMENTS: Mapping[str, tuple[str, ...]] = {
    "production": ("main",),
    "release-signing": ("main",),
    "device-matrix": ("dev1.0", "main", "refs/pull/*/merge"),
}


class HostedReleaseAuthorityError(RuntimeError):
    """One stable fail-closed hosted authority terminal."""


def _block(detail: object) -> HostedReleaseAuthorityError:
    safe = " ".join(str(detail).replace("\x00", "\\x00").split())
    return HostedReleaseAuthorityError(
        f"{AUTHORITY_CODE}: terminal=blocked; {safe}; "
        "recovery=restore_git_authority_then_retry"
    )


def _api_get(repository: str, path: str, token: str) -> Any:
    try:
        payload, _stats = request_json(
            f"https://api.github.com/repos/{repository}{path}", token
        )
        return payload
    except GithubActionsApiError as error:
        raise _block(
            f"GitHub authority query failed for {path or '/'}: {error.reason}"
        ) from error


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _block(f"{label} response is not an object")
    return value


def _object_list(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise _block(f"{label} response is not an object list")
    return list(value)


def _rule(ruleset: Mapping[str, Any], rule_type: str) -> dict[str, Any]:
    rules = ruleset.get("rules")
    matches = [
        item
        for item in (rules if isinstance(rules, list) else [])
        if isinstance(item, dict) and item.get("type") == rule_type
    ]
    if len(matches) != 1:
        raise _block(
            f"ruleset {ruleset.get('name')!r} must contain one {rule_type!r} rule"
        )
    return matches[0]


def _verify_ruleset(
    *, ruleset: Mapping[str, Any], branch: str,
    required_checks: tuple[str, ...], minimum_approvals: int,
) -> dict[str, Any]:
    if ruleset.get("enforcement") != "active" or ruleset.get("bypass_actors") != []:
        raise _block(f"{branch} ruleset must be active with no bypass actors")
    conditions = ruleset.get("conditions") or {}
    ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if ref_name != {"exclude": [], "include": [f"refs/heads/{branch}"]}:
        raise _block(f"{branch} ruleset ref condition drifted")
    _rule(ruleset, "deletion")
    _rule(ruleset, "non_fast_forward")
    pull_request = _rule(ruleset, "pull_request").get("parameters") or {}
    if (
        not isinstance(pull_request, dict)
        or int(pull_request.get("required_approving_review_count", -1)) < minimum_approvals
        or pull_request.get("dismiss_stale_reviews_on_push") is not True
        or pull_request.get("required_review_thread_resolution") is not True
        or pull_request.get("require_extra_approval_for_unattributed_changes") is not True
        or pull_request.get("allowed_merge_methods") != ["merge"]
        or (branch == "main" and pull_request.get("require_last_push_approval") is not True)
    ):
        raise _block(f"{branch} pull-request protection is incomplete")
    required = _rule(ruleset, "required_status_checks").get("parameters") or {}
    checks = required.get("required_status_checks") if isinstance(required, dict) else None
    if (
        required.get("strict_required_status_checks_policy") is not True
        or required.get("do_not_enforce_on_create") is not False
        or not isinstance(checks, list)
    ):
        raise _block(f"{branch} required-check protection is incomplete")
    observed = {
        str(item.get("context")): item.get("integration_id")
        for item in checks if isinstance(item, dict)
    }
    expected = {name: GITHUB_ACTIONS_APP_ID for name in required_checks}
    if observed != expected:
        raise _block(f"{branch} required checks are not exact GitHub Actions producers")
    return {
        "id": int(ruleset["id"]), "name": str(ruleset["name"]), "branch": branch,
        "requiredChecks": [
            {"name": name, "integrationId": GITHUB_ACTIONS_APP_ID}
            for name in required_checks
        ],
        "minimumApprovals": minimum_approvals,
        "updatedAt": str(ruleset.get("updated_at") or ""),
    }


def _verify_environment(
    *, environment: Mapping[str, Any], branch_policies: object,
    name: str, expected_branches: tuple[str, ...],
) -> dict[str, Any]:
    if environment.get("name") != name or environment.get("can_admins_bypass") is not False:
        raise _block(f"{name} Environment must exist and forbid admin bypass")
    if environment.get("deployment_branch_policy") != {
        "protected_branches": False, "custom_branch_policies": True,
    }:
        raise _block(f"{name} Environment branch policy is not custom/fail-closed")
    policy_payload = _object(branch_policies, f"{name} deployment branch policies")
    policies = _object_list(
        policy_payload.get("branch_policies"), f"{name} branch policies"
    )
    observed_policies = sorted(
        (str(item.get("type") or ""), str(item.get("name") or ""))
        for item in policies
    )
    expected_policies = sorted(("branch", branch) for branch in expected_branches)
    if observed_policies != expected_policies:
        raise _block(f"{name} Environment allowed ref policies drifted")
    observed_branches = [policy_name for policy_type, policy_name in observed_policies if policy_type == "branch"]
    protections = _object_list(environment.get("protection_rules"), f"{name} protections")
    reviewer_rules = [item for item in protections if item.get("type") == "required_reviewers"]
    if name == "production":
        if len(reviewer_rules) != 1:
            raise _block("production must have one required-reviewers protection rule")
        reviewers = reviewer_rules[0].get("reviewers")
        if (
            reviewer_rules[0].get("prevent_self_review") is not True
            or not isinstance(reviewers, list) or not reviewers
        ):
            raise _block("production must require a non-self reviewer")
    elif reviewer_rules:
        raise _block(f"{name} must not add a second human approval before production")
    return {
        "name": name, "adminBypass": False, "branches": observed_branches,
        "requiredReviewerCount": (
            len(reviewer_rules[0].get("reviewers") or []) if reviewer_rules else 0
        ),
        "preventSelfReview": (
            reviewer_rules[0].get("prevent_self_review") is True if reviewer_rules else False
        ),
        "updatedAt": str(environment.get("updated_at") or ""),
    }


def verify_hosted_release_authority(
    *, repository: str, token: str, policy: BranchPolicy | None = None,
) -> dict[str, Any]:
    if not repository or "/" not in repository or not token:
        raise _block("repository and authenticated GitHub token are required")
    branch_policy = policy or load_policy()
    repository_state = _object(_api_get(repository, "", token), "repository")
    if (
        repository_state.get("full_name") != repository
        or repository_state.get("default_branch") != branch_policy.release_branch
    ):
        raise _block("hosted repository identity/default branch drifted")
    workflow_permissions = _object(
        _api_get(repository, "/actions/permissions/workflow", token),
        "Actions workflow permissions",
    )
    actions_permissions = _object(
        _api_get(repository, "/actions/permissions", token), "Actions permissions"
    )
    if workflow_permissions != {
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
    }:
        raise _block("default Actions token is not read-only")
    if (
        actions_permissions.get("enabled") is not True
        or actions_permissions.get("sha_pinning_required") is not True
    ):
        raise _block("Actions SHA pinning is not enforced")
    security = repository_state.get("security_and_analysis")
    if not isinstance(security, dict):
        raise _block("repository security status is unavailable")
    required_security = ("secret_scanning", "secret_scanning_push_protection")
    if any(
        not isinstance(security.get(name), dict)
        or security[name].get("status") != "enabled"
        for name in required_security
    ):
        raise _block("required secret security controls are not enabled")
    alerts = _api_get(repository, "/dependabot/alerts?per_page=1", token)
    if not isinstance(alerts, list):
        raise _block("Dependabot vulnerability alerts are not readable")
    if (
        not isinstance(security.get("dependabot_security_updates"), dict)
        or security["dependabot_security_updates"].get("status") != "disabled"
    ):
        raise _block(
            "automated security fixes must be disabled because bot branches violate the declared ref set"
        )

    runner_payload = _object(
        _api_get(repository, "/actions/runners?per_page=100", token),
        "self-hosted runners",
    )
    runners = _object_list(runner_payload.get("runners"), "self-hosted runners")
    runner_names = sorted(str(runner.get("name") or "") for runner in runners)
    if runner_names != sorted(EXPECTED_RUNNER_NAMES):
        raise _block("registered release runner identities drifted")
    for runner in runners:
        labels = runner.get("labels")
        if not isinstance(labels, list):
            raise _block("release runner labels are unavailable")
        observed_labels = {
            str(label.get("name") or "")
            for label in labels
            if isinstance(label, dict)
        }
        if observed_labels != RELEASE_RUNNER_LABELS:
            raise _block(f"release runner {runner.get('name')!r} labels drifted")
    if not any(runner.get("status") == "online" for runner in runners):
        raise _block("no release-authority runner is online")
    runner_authority = {
        "names": runner_names,
        "labels": sorted(RELEASE_RUNNER_LABELS),
        "minimumOnlineSatisfied": True,
    }

    summaries = _object_list(_api_get(repository, "/rulesets", token), "rulesets")
    details = []
    for summary in summaries:
        ruleset_id = summary.get("id")
        if isinstance(ruleset_id, int):
            details.append(_object(
                _api_get(repository, f"/rulesets/{ruleset_id}", token),
                f"ruleset {ruleset_id}",
            ))
    by_branch: dict[str, dict[str, Any]] = {}
    for branch in (branch_policy.integration_branch, branch_policy.release_branch):
        expected_ref = f"refs/heads/{branch}"
        matches = []
        for detail in details:
            conditions = detail.get("conditions") or {}
            ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
            if isinstance(ref_name, dict) and expected_ref in (ref_name.get("include") or []):
                matches.append(detail)
        if len(matches) != 1:
            raise _block(f"{branch} must have exactly one applicable branch ruleset")
        by_branch[branch] = matches[0]
    expected_checks = tuple(item.name for item in branch_policy.required_promotion_checks)
    rulesets = [
        _verify_ruleset(
            ruleset=by_branch[branch_policy.integration_branch],
            branch=branch_policy.integration_branch,
            required_checks=(expected_checks[0],), minimum_approvals=0,
        ),
        _verify_ruleset(
            ruleset=by_branch[branch_policy.release_branch],
            branch=branch_policy.release_branch,
            required_checks=expected_checks, minimum_approvals=1,
        ),
    ]
    environments = []
    for name, expected_branches in SENSITIVE_ENVIRONMENTS.items():
        encoded = urllib.parse.quote(name, safe="")
        environments.append(_verify_environment(
            environment=_object(
                _api_get(repository, f"/environments/{encoded}", token),
                f"{name} Environment",
            ),
            branch_policies=_api_get(
                repository, f"/environments/{encoded}/deployment-branch-policies", token
            ),
            name=name, expected_branches=expected_branches,
        ))
    receipt: dict[str, Any] = {
        "schema": "hosted-release-authority-receipt",
        "repository": repository,
        "defaultBranch": branch_policy.release_branch,
        "hostedProtectionVerified": True,
        "formalProd": True,
        "actions": {
            "defaultWorkflowPermissions": "read",
            "canApprovePullRequestReviews": False,
            "shaPinningRequired": True,
        },
        "security": {
            **{name: "enabled" for name in required_security},
            "dependabot_vulnerability_alerts": "enabled",
            "dependabot_security_updates": "disabled_ref_policy_incompatible",
        },
        "runnerAuthority": runner_authority,
        "rulesets": rulesets, "environments": environments,
        "observedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    digest_payload = {
        key: value for key, value in receipt.items()
        if key not in {"observedAt", "evidenceDigest"}
    }
    receipt["evidenceDigest"] = "sha256:" + hashlib.sha256(json.dumps(
        digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--expected-digest", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = verify_hosted_release_authority(
            repository=args.repository,
            token=os.environ.get(args.token_env, "").strip(),
        )
        if args.expected_digest and receipt["evidenceDigest"] != args.expected_digest:
            raise _block("hosted authority changed between preflight and mutation")
    except (HostedReleaseAuthorityError, OSError, TypeError, ValueError) as error:
        detail = str(error)
        if AUTHORITY_CODE not in detail:
            detail = str(_block(detail))
        print(f"GATE_BLOCK: {detail}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.write("applicability=required\n")
            stream.write("decision=pass\n")
            stream.write(f"authority_digest={receipt['evidenceDigest']}\n")
    print(
        f"hosted release authority verified repository={args.repository} "
        f"digest={receipt['evidenceDigest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

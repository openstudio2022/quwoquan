# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-003.t2
from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

from quwoquan_ops.ci.verify_hosted_release_authority import (
    GITHUB_ACTIONS_APP_ID,
    HostedReleaseAuthorityError,
    verify_hosted_release_authority,
)
from quwoquan_ops.gate.verify_git_branch_policy import load_policy

REPOSITORY = "example/quwoquan"


def _ruleset(rule_id: int, branch: str, checks: list[str], approvals: int) -> dict:
    return {
        "id": rule_id,
        "name": f"protect {branch}",
        "enforcement": "active",
        "bypass_actors": [],
        "updated_at": "2026-09-05T00:00:00Z",
        "conditions": {"ref_name": {"exclude": [], "include": [f"refs/heads/{branch}"]}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {
                "required_approving_review_count": approvals,
                "dismiss_stale_reviews_on_push": True,
                "required_review_thread_resolution": True,
                "require_extra_approval_for_unattributed_changes": True,
                "require_last_push_approval": branch == "main",
                "allowed_merge_methods": ["merge"],
            }},
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": True,
                "do_not_enforce_on_create": False,
                "required_status_checks": [
                    {"context": check, "integration_id": GITHUB_ACTIONS_APP_ID}
                    for check in checks
                ],
            }},
        ],
    }


def _environment(name: str, reviewers: bool) -> dict:
    protection_rules = [{"type": "branch_policy"}]
    if reviewers:
        protection_rules.insert(0, {
            "type": "required_reviewers",
            "prevent_self_review": True,
            "reviewers": [{"type": "User", "reviewer": {"login": "release-owner"}}],
        })
    return {
        "name": name,
        "can_admins_bypass": False,
        "deployment_branch_policy": {
            "protected_branches": False,
            "custom_branch_policies": True,
        },
        "protection_rules": protection_rules,
        "updated_at": "2026-09-05T00:00:00Z",
    }


def _responses() -> dict[str, object]:
    checks = [item.name for item in load_policy().required_promotion_checks]
    return {
        "": {
            "full_name": REPOSITORY,
            "default_branch": "main",
            "security_and_analysis": {
                "dependabot_security_updates": {"status": "disabled"},
                "secret_scanning": {"status": "enabled"},
                "secret_scanning_push_protection": {"status": "enabled"},
            },
        },
        "/actions/permissions/workflow": {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": False,
        },
        "/actions/permissions": {"enabled": True, "sha_pinning_required": True},
        "/dependabot/alerts?per_page=1": [],
        "/actions/runners?per_page=100": {
            "total_count": 2,
            "runners": [
                {
                    "name": "quwoquan-local-mac",
                    "status": "online",
                    "labels": [{"name": name} for name in (
                        "self-hosted", "macOS", "ARM64", "quwoquan-release-authority",
                    )],
                },
                {
                    "name": "quwoquan-local-mac-b",
                    "status": "offline",
                    "labels": [{"name": name} for name in (
                        "self-hosted", "macOS", "ARM64", "quwoquan-release-authority",
                    )],
                },
            ],
        },
        "/rulesets": [{"id": 1}, {"id": 2}],
        "/rulesets/1": _ruleset(1, "dev1.0", checks[:1], 0),
        "/rulesets/2": _ruleset(2, "main", checks, 1),
        "/environments/production": _environment("production", True),
        "/environments/release-signing": _environment("release-signing", False),
        "/environments/device-matrix": _environment("device-matrix", False),
        "/environments/production/deployment-branch-policies": {
            "branch_policies": [{"name": "main", "type": "branch"}],
        },
        "/environments/release-signing/deployment-branch-policies": {
            "branch_policies": [{"name": "main", "type": "branch"}],
        },
        "/environments/device-matrix/deployment-branch-policies": {
            "branch_policies": [
                {"name": "main", "type": "branch"},
                {"name": "dev1.0", "type": "branch"},
                {"name": "refs/pull/*/merge", "type": "branch"},
            ],
        },
    }


def _verify(responses: dict[str, object]) -> dict:
    with patch(
        "quwoquan_ops.ci.verify_hosted_release_authority._api_get",
        side_effect=lambda _repository, path, _token: copy.deepcopy(responses[path]),
    ):
        return verify_hosted_release_authority(repository=REPOSITORY, token="token")


def test_hosted_authority_accepts_exact_fail_closed_control_plane() -> None:
    receipt = _verify(_responses())
    assert receipt["hostedProtectionVerified"] is True
    assert receipt["formalProd"] is True
    assert receipt["actions"]["defaultWorkflowPermissions"] == "read"
    assert receipt["runnerAuthority"]["minimumOnlineSatisfied"] is True
    assert receipt["runnerAuthority"]["names"] == [
        "quwoquan-local-mac", "quwoquan-local-mac-b",
    ]
    assert [item["branch"] for item in receipt["rulesets"]] == ["dev1.0", "main"]
    assert [item["name"] for item in receipt["environments"]] == [
        "production", "release-signing", "device-matrix",
    ]
    assert receipt["evidenceDigest"].startswith("sha256:")


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("write-token", lambda value: value["/actions/permissions/workflow"].update(default_workflow_permissions="write")),
        ("unbound-check", lambda value: value["/rulesets/2"]["rules"][3]["parameters"]["required_status_checks"][0].pop("integration_id")),
        ("ruleset-bypass", lambda value: value["/rulesets/2"].update(bypass_actors=[{"actor_id": 1}])),
        ("admin-bypass", lambda value: value["/environments/production"].update(can_admins_bypass=True)),
        ("missing-prod-review", lambda value: value["/environments/production"].update(protection_rules=[{"type": "branch_policy"}])),
        ("extra-signing-review", lambda value: value["/environments/release-signing"].update(protection_rules=_environment("production", True)["protection_rules"])),
        ("wrong-device-branch", lambda value: value["/environments/device-matrix/deployment-branch-policies"].update(branch_policies=[{"name": "main", "type": "branch"}])),
        ("extra-tag-policy", lambda value: value["/environments/device-matrix/deployment-branch-policies"]["branch_policies"].append({"name": "v*", "type": "tag"})),
        ("unknown-policy-type", lambda value: value["/environments/device-matrix/deployment-branch-policies"]["branch_policies"].append({"name": "main", "type": "unknown"})),
        ("security-disabled", lambda value: value[""]["security_and_analysis"]["secret_scanning"].update(status="disabled")),
        ("unreadable-alerts", lambda value: value.update({"/dependabot/alerts?per_page=1": {}})),
        ("bot-branches-enabled", lambda value: value[""]["security_and_analysis"]["dependabot_security_updates"].update(status="enabled")),
        ("missing-runner", lambda value: value["/actions/runners?per_page=100"]["runners"].pop()),
        ("runner-label-drift", lambda value: value["/actions/runners?per_page=100"]["runners"][0]["labels"].pop()),
        ("all-runners-offline", lambda value: [runner.update(status="offline") for runner in value["/actions/runners?per_page=100"]["runners"]]),
    ],
)
def test_hosted_authority_negative_controls_fail_closed(label: str, mutate) -> None:
    responses = _responses()
    mutate(responses)
    with pytest.raises(HostedReleaseAuthorityError, match="OPS.BRANCH.AUTHORITY_UNAVAILABLE"):
        _verify(responses)


def test_hosted_authority_requires_authenticated_token() -> None:
    with pytest.raises(HostedReleaseAuthorityError, match="terminal=blocked"):
        verify_hosted_release_authority(repository=REPOSITORY, token="")

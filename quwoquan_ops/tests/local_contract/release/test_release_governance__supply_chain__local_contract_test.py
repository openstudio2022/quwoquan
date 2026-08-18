# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-003.t2
from __future__ import annotations

import urllib.error
import unittest
from unittest.mock import patch

from quwoquan_ops.ci.verify_release_governance import (
    _api_get,
    verify_release_governance as _verify_release_governance,
)


REPOSITORY = "example/quwoquan"
WORKFLOW_REF = (
    "example/quwoquan/.github/workflows/deploy-prod-auto.yml@refs/heads/main"
)
SHA = "a" * 40
PROMOTION_HEAD_SHA = "b" * 40
CURRENT_RUN_ID = 9001
CURRENT_RUN_ATTEMPT = 2


def verify_release_governance(**kwargs):
    return _verify_release_governance(
        workflow_run_id=str(CURRENT_RUN_ID),
        workflow_run_attempt=str(CURRENT_RUN_ATTEMPT),
        **kwargs,
    )


def _promotion_pull(sha: str = SHA, *, head: str = "dev1.0") -> dict:
    return {
        "number": 42,
        "merged_at": "2026-07-20T12:00:00Z",
        "merge_commit_sha": sha,
        "base": {"ref": "main"},
        "head": {
            "ref": head,
            "sha": PROMOTION_HEAD_SHA,
            "repo": {"full_name": REPOSITORY},
        },
        "user": {"login": "author"},
        "merged_by": {"login": "maintainer"},
    }


def _successful_checks(sha: str = PROMOTION_HEAD_SHA) -> dict:
    return {
        "check_runs": [
            {
                "id": 2000 + index,
                "name": name,
                "head_sha": sha,
                "status": "completed",
                "conclusion": "success",
                "details_url": (
                    f"https://github.com/{REPOSITORY}/actions/runs/"
                    f"{1000 + index}/job/{3000 + index}"
                ),
                "app": {"slug": "github-actions"},
                "check_suite": {"id": 4000 + index, "head_sha": sha},
            }
            for index, name in enumerate(
                (
                    "03. Delivery Gate",
                    "04. Pre-Release Gate",
                    "05. App Env Device Matrix",
                )
            )
        ]
    }


def _successful_workflow_runs(sha: str = PROMOTION_HEAD_SHA) -> list[dict]:
    return [
        {
            "id": 1000 + index,
            "run_attempt": 1,
            "event": "pull_request",
            "head_sha": sha,
            "status": "completed",
            "conclusion": "success",
            "path": path,
            "pull_requests": [{"number": 42}],
            "repository": {"full_name": REPOSITORY},
            "actor": {"login": "github-actions"},
        }
        for index, path in enumerate(
            (
                ".github/workflows/delivery-gate.yml",
                ".github/workflows/pre-release-gate.yml",
                ".github/workflows/app-env-device-matrix-self-hosted.yml",
            )
        )
    ]


def _hosted_responses(
    *,
    sha: str = SHA,
    reviews: list[dict] | None = None,
    checks: dict | None = None,
    comparison: dict | None = None,
    workflow_runs: list[dict] | None = None,
) -> list[object]:
    return [
        [_promotion_pull(sha)],
        {
            "id": CURRENT_RUN_ID,
            "run_attempt": CURRENT_RUN_ATTEMPT,
            "head_sha": sha,
            "head_branch": "main",
            "path": ".github/workflows/deploy-prod-auto.yml",
            "event": "push",
            "status": "in_progress",
            "repository": {"full_name": REPOSITORY},
            "actor": {"login": "release-bot"},
            "triggering_actor": {"login": "maintainer"},
            "workflow_id": 7001,
        },
        {
            "full_name": REPOSITORY,
            "default_branch": "main",
            "delete_branch_on_merge": True,
        },
        {"sha": sha, "parents": [{"sha": PROMOTION_HEAD_SHA}]},
        {"object": {"sha": sha, "type": "commit"}},
        comparison
        or {"status": "identical", "merge_base_commit": {"sha": sha}},
        reviews
        or [
            {
                "submitted_at": "2026-07-20T11:00:00Z",
                "state": "APPROVED",
                "commit_id": PROMOTION_HEAD_SHA,
                "user": {"login": "reviewer"},
            }
        ],
        checks or _successful_checks(),
        *(workflow_runs or _successful_workflow_runs()),
    ]


class ReleaseGovernanceContractTest(unittest.TestCase):
    def test_hosted_api_failure_preserves_authority_unavailable_identity(self) -> None:
        with patch(
            "quwoquan_ops.ci.verify_release_governance.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "OPS.BRANCH.AUTHORITY_UNAVAILABLE"
            ):
                _api_get(REPOSITORY, "", "token")

    def test_early_source_admission_does_not_invent_an_artifact_digest(self) -> None:
        with patch(
            "quwoquan_ops.ci.verify_release_governance._api_get",
            side_effect=_hosted_responses(),
        ):
            receipt = verify_release_governance(
                repository=REPOSITORY,
                git_sha=SHA,
                token="token",
                workflow_ref=WORKFLOW_REF,
            )

        self.assertEqual(receipt["schema"], "prod-source-governance-receipt")
        self.assertNotIn("artifactDigest", receipt)

    def test_reviewed_merge_requires_distinct_approval(self) -> None:
        with patch(
            "quwoquan_ops.ci.verify_release_governance._api_get",
            side_effect=_hosted_responses(),
        ):
            receipt = verify_release_governance(
                repository=REPOSITORY,
                git_sha=SHA,
                artifact_digest="sha256:" + ("a" * 64),
                token="token",
                workflow_ref=WORKFLOW_REF,
            )
        self.assertEqual(receipt["pullRequest"], 42)
        self.assertEqual(receipt["approvers"], ["reviewer"])
        self.assertEqual(receipt["artifactDigest"], "sha256:" + ("a" * 64))
        self.assertEqual(receipt["mainOid"], SHA)
        self.assertEqual(receipt["promotionHeadOid"], PROMOTION_HEAD_SHA)
        self.assertEqual(receipt["workflowRef"], WORKFLOW_REF)
        self.assertEqual(len(receipt["requiredChecks"]), 3)
        self.assertGreaterEqual(len(receipt["distinctPrincipals"]), 2)

    def test_direct_push_and_author_self_approval_fail_closed(self) -> None:
        with patch(
            "quwoquan_ops.ci.verify_release_governance._api_get",
            return_value=[],
        ):
            with self.assertRaisesRegex(RuntimeError, "unique merge result"):
                verify_release_governance(
                    repository=REPOSITORY,
                    git_sha=SHA,
                    artifact_digest="sha256:" + ("a" * 64),
                    token="token",
                    workflow_ref=WORKFLOW_REF,
                )

        self_review = [
            {
                "submitted_at": "2026-07-20T11:00:00Z",
                "state": "APPROVED",
                "commit_id": PROMOTION_HEAD_SHA,
                "user": {"login": "author"},
            }
        ]
        with patch(
            "quwoquan_ops.ci.verify_release_governance._api_get",
            side_effect=_hosted_responses(reviews=self_review),
        ):
            with self.assertRaisesRegex(RuntimeError, "non-author approval"):
                verify_release_governance(
                    repository=REPOSITORY,
                    git_sha=SHA,
                    artifact_digest="sha256:" + ("b" * 64),
                    token="token",
                    workflow_ref=WORKFLOW_REF,
                )

    def test_codex_to_main_merge_never_has_release_eligibility(self) -> None:
        responses = [
            [
                {
                    "number": 44,
                    "merged_at": "2026-07-20T12:00:00Z",
                    "merge_commit_sha": SHA,
                    "base": {"ref": "main"},
                    "head": {
                        "ref": "codex/direct-main",
                        "repo": {"full_name": REPOSITORY},
                    },
                    "user": {"login": "author"},
                    "merged_by": {"login": "maintainer"},
                }
            ]
        ]
        with patch(
            "quwoquan_ops.ci.verify_release_governance._api_get",
            side_effect=responses,
        ):
            with self.assertRaisesRegex(RuntimeError, "dev1.0 -> main"):
                verify_release_governance(
                    repository=REPOSITORY,
                    git_sha=SHA,
                    artifact_digest="sha256:" + ("c" * 64),
                    token="token",
                    workflow_ref=WORKFLOW_REF,
                )

    def test_exact_sha_and_canonical_workflow_ref_are_mandatory(self) -> None:
        for git_sha, workflow_ref in (
            ("short", WORKFLOW_REF),
            (SHA, "example/quwoquan/.github/workflows/deploy-prod-auto.yml@refs/heads/dev1.0"),
        ):
            with self.subTest(git_sha=git_sha, workflow_ref=workflow_ref):
                with self.assertRaises(RuntimeError):
                    verify_release_governance(
                        repository=REPOSITORY,
                        git_sha=git_sha,
                        artifact_digest="sha256:" + ("d" * 64),
                        token="token",
                        workflow_ref=workflow_ref,
                    )

    def test_main_reachability_and_required_checks_fail_closed(self) -> None:
        unreachable = {
            "status": "diverged",
            "merge_base_commit": {"sha": "b" * 40},
        }
        with patch(
            "quwoquan_ops.ci.verify_release_governance._api_get",
            side_effect=_hosted_responses(comparison=unreachable),
        ):
            with self.assertRaisesRegex(RuntimeError, "reachable from trusted main"):
                verify_release_governance(
                    repository=REPOSITORY,
                    git_sha=SHA,
                    artifact_digest="sha256:" + ("e" * 64),
                    token="token",
                    workflow_ref=WORKFLOW_REF,
                )

        failed_checks = _successful_checks()
        failed_checks["check_runs"][0]["conclusion"] = "failure"
        with patch(
            "quwoquan_ops.ci.verify_release_governance._api_get",
            side_effect=_hosted_responses(checks=failed_checks),
        ):
            with self.assertRaisesRegex(RuntimeError, "not successful for exact SHA"):
                verify_release_governance(
                    repository=REPOSITORY,
                    git_sha=SHA,
                    artifact_digest="sha256:" + ("f" * 64),
                    token="token",
                    workflow_ref=WORKFLOW_REF,
                )

    def test_stale_approval_and_same_named_noncanonical_workflow_fail_closed(self) -> None:
        stale_review = [
            {
                "submitted_at": "2026-07-20T11:00:00Z",
                "state": "APPROVED",
                "commit_id": "c" * 40,
                "user": {"login": "reviewer"},
            }
        ]
        with patch(
            "quwoquan_ops.ci.verify_release_governance._api_get",
            side_effect=_hosted_responses(reviews=stale_review),
        ):
            with self.assertRaisesRegex(RuntimeError, "non-author approval"):
                verify_release_governance(
                    repository=REPOSITORY,
                    git_sha=SHA,
                    artifact_digest="sha256:" + ("1" * 64),
                    token="token",
                    workflow_ref=WORKFLOW_REF,
                )

        drifted_runs = _successful_workflow_runs()
        drifted_runs[0]["path"] = ".github/workflows/lookalike.yml"
        with patch(
            "quwoquan_ops.ci.verify_release_governance._api_get",
            side_effect=_hosted_responses(workflow_runs=drifted_runs),
        ):
            with self.assertRaisesRegex(RuntimeError, "canonical workflow run"):
                verify_release_governance(
                    repository=REPOSITORY,
                    git_sha=SHA,
                    artifact_digest="sha256:" + ("2" * 64),
                    token="token",
                    workflow_ref=WORKFLOW_REF,
                )

if __name__ == "__main__":
    unittest.main()

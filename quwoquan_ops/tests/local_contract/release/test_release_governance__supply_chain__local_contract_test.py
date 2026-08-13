from __future__ import annotations

import unittest
from unittest.mock import patch

from quwoquan_ops.ci.verify_release_governance import verify_release_governance


class ReleaseGovernanceContractTest(unittest.TestCase):
    def test_reviewed_merge_requires_distinct_approval(self) -> None:
        responses = [
            [
                {
                    "number": 42,
                    "merged_at": "2026-07-20T12:00:00Z",
                    "merge_commit_sha": "abc123",
                    "base": {"ref": "main"},
                    "user": {"login": "author"},
                    "merged_by": {"login": "maintainer"},
                }
            ],
            [
                {
                    "submitted_at": "2026-07-20T11:00:00Z",
                    "state": "APPROVED",
                    "user": {"login": "reviewer"},
                }
            ],
        ]
        with patch(
            "quwoquan_ops.ci.verify_release_governance._api_get",
            side_effect=responses,
        ):
            receipt = verify_release_governance(
                repository="example/quwoquan",
                git_sha="abc123",
                artifact_digest="sha256:" + ("a" * 64),
                token="token",
            )
        self.assertEqual(receipt["pullRequest"], 42)
        self.assertEqual(receipt["approvers"], ["reviewer"])
        self.assertEqual(receipt["artifactDigest"], "sha256:" + ("a" * 64))
        self.assertGreaterEqual(len(receipt["distinctPrincipals"]), 2)

    def test_direct_push_and_author_self_approval_fail_closed(self) -> None:
        with patch(
            "quwoquan_ops.ci.verify_release_governance._api_get",
            return_value=[],
        ):
            with self.assertRaisesRegex(RuntimeError, "unique merge result"):
                verify_release_governance(
                    repository="example/quwoquan",
                    git_sha="direct",
                    artifact_digest="sha256:" + ("a" * 64),
                    token="token",
                )

        responses = [
            [
                {
                    "number": 43,
                    "merged_at": "2026-07-20T12:00:00Z",
                    "merge_commit_sha": "self",
                    "base": {"ref": "main"},
                    "user": {"login": "author"},
                    "merged_by": {"login": "author"},
                }
            ],
            [
                {
                    "submitted_at": "2026-07-20T11:00:00Z",
                    "state": "APPROVED",
                    "user": {"login": "author"},
                }
            ],
        ]
        with patch(
            "quwoquan_ops.ci.verify_release_governance._api_get",
            side_effect=responses,
        ):
            with self.assertRaisesRegex(RuntimeError, "non-author approval"):
                verify_release_governance(
                    repository="example/quwoquan",
                    git_sha="self",
                    artifact_digest="sha256:" + ("b" * 64),
                    token="token",
                )


if __name__ == "__main__":
    unittest.main()

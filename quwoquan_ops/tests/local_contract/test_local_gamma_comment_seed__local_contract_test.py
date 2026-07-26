from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_app.scripts.gamma import run_local_gamma_t3 as local_gamma_t3
from quwoquan_ops.cli import stackctl


class LocalGammaCommentSeedContractTest(unittest.TestCase):
    def test_fixture_post_has_a_valid_revision_for_report_moderation(self) -> None:
        document = local_gamma_t3.fixture_post_to_doc(
            {
                "postId": "fixture_photo_001",
                "contentType": "image",
                "title": "可审核的 Gamma 种子内容",
                "createdAt": "2026-06-05T11:00:00Z",
            }
        )

        self.assertEqual(document["version"], 1)
        self.assertRegex(
            document["contentDigest"],
            r"^sha256:[0-9a-f]{64}$",
        )

    def test_fixture_post_preserves_canonical_tag_refs_for_search_backfill(self) -> None:
        document = local_gamma_t3.fixture_post_to_doc(
            {
                "postId": "fixture_photo_search_tags",
                "contentType": "image",
                "title": "带标签的 Gamma 搜索内容",
                "tagRefs": ["fixture", "photography", "fixture"],
                "tags": ["must-not-override-canonical-tag-refs"],
            }
        )

        self.assertEqual(
            document["tagRefs"],
            ["fixture", "photography", "fixture"],
        )

    def test_content_seed_does_not_write_comment_aggregate_documents(
        self,
    ) -> None:
        fixture_payload = {
            "seedSets": {
                "content_core": {
                    "posts": [
                        {
                            "postId": "fixture_photo_001",
                            "contentType": "image",
                            "createdAt": "2026-06-05T11:00:00Z",
                            "tagRefs": ["fixture", "photography"],
                        }
                    ],
                    "comments": [
                        {
                            "commentId": "fixture_comment_parent_001",
                            "postId": "fixture_photo_001",
                            "authorId": "fixture_user_current",
                            "content": "主评论示例",
                            "createdAt": "2026-06-05T12:00:00Z",
                            "authorIpLocation": "浙江",
                            "hotScore": 128,
                        }
                    ],
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = Path(tmp_dir) / "fixture.json"
            fixture_path.write_text(
                json.dumps(fixture_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            artifact_root = Path(tmp_dir) / "artifacts"
            with (
                mock.patch.object(
                    local_gamma_t3,
                    "gamma_content_fixture_spec",
                    return_value=(fixture_path, ["content_core"]),
                ),
                mock.patch.object(local_gamma_t3, "GAMMA_RUN_ROOT", artifact_root),
                mock.patch.object(
                    local_gamma_t3,
                    "compose_command",
                    return_value=["mongosh"],
                ),
                mock.patch.object(
                    local_gamma_t3.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        ["mongosh"],
                        0,
                        "seed ok",
                    ),
                ),
            ):
                result = local_gamma_t3.seed_content()

            seed_script = (artifact_root / "seed-content.js").read_text(
                encoding="utf-8"
            )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["insertedCount"], 1)
        self.assertIn(
            "dbh.posts.deleteMany({_id: {$in: ids}})",
            seed_script,
        )
        self.assertIn(
            'tagRefs: Array.isArray(doc.tagRefs) ? doc.tagRefs : [],',
            seed_script,
        )
        self.assertNotIn("dbh.comments", seed_script)

    def test_comment_thread_setup_uses_public_commands_without_expected_version(
        self,
    ) -> None:
        calls: list[tuple[str, dict[str, object]]] = []
        responses = iter(
            [
                (200, {"id": "comment-parent", "version": 1}),
                (200, {"id": "comment-reply", "version": 1}),
                (200, {"reaction": "like"}),
                (200, {"version": 2}),
            ]
        )

        def request(url: str, **kwargs: object) -> tuple[int, bytes]:
            calls.append((url, kwargs))
            status, body = next(responses)
            return status, json.dumps(body).encode("utf-8")

        with (
            mock.patch.object(local_gamma_t3, "http_request", side_effect=request),
            mock.patch.object(
                local_gamma_t3,
                "gamma_probe_idempotency_key",
                side_effect=lambda purpose: f"key-{purpose}",
            ),
        ):
            result = local_gamma_t3.setup_comment_thread("https://gamma.example")

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["parentCommentId"], "comment-parent")
        self.assertEqual(result["replyCommentId"], "comment-reply")
        self.assertEqual(len(calls), 4)
        self.assertEqual(
            [call[0] for call in calls],
            [
                "https://gamma.example/content/posts/fixture_photo_001/comments",
                "https://gamma.example/content/posts/fixture_photo_001/comments",
                "https://gamma.example/content/comments/comment-parent/reaction",
                "https://gamma.example/content/comments/comment-parent/media:bind",
            ],
        )
        self.assertEqual(calls[0][1]["body"], {"content": "主评论示例"})
        self.assertEqual(
            calls[1][1]["body"],
            {"content": "回复示例", "replyToCommentId": "comment-parent"},
        )
        self.assertEqual(calls[2][1]["body"], {"reaction": "like"})
        self.assertEqual(calls[3][1]["body"], {"attachmentMediaIds": []})
        self.assertNotIn("version", calls[3][1]["body"])

    def test_content_scoped_probe_does_not_require_product_ops_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "t3-report.json"
            session = local_gamma_t3.LocalGammaAcceptanceSession(
                owner_id="fixture_owner",
                persona_id="fixture_persona",
                access_token="test-token",
            )
            with (
                mock.patch.object(
                    local_gamma_t3,
                    "wait_url",
                    return_value={"status": "passed"},
                ) as wait_url,
                mock.patch.object(
                    local_gamma_t3,
                    "open_local_acceptance_session",
                    return_value=session,
                ),
                mock.patch.object(
                    local_gamma_t3,
                    "setup_runtime_fixtures",
                    return_value={
                        "status": "passed",
                        "parentCommentId": "parent",
                        "replyCommentId": "reply",
                    },
                ),
                mock.patch.object(local_gamma_t3, "endpoint_checks", return_value=[]),
                mock.patch.object(
                    local_gamma_t3,
                    "strict_endpoint_checks",
                    return_value=[],
                ),
                mock.patch.object(local_gamma_t3, "_ACTIVE_SESSION", None),
                mock.patch.object(
                    local_gamma_t3.sys,
                    "argv",
                    [
                        "run_local_gamma_t3.py",
                        "--enabled-domain",
                        "content",
                        "--skip-seed",
                        "--skip-flutter-contracts",
                        "--report",
                        str(report_path),
                    ],
                ),
            ):
                self.assertEqual(local_gamma_t3.main(), 0)

            wait_url.assert_called_once_with(
                "https://gamma-api.quwoquan-env.test:19000/healthz",
                45,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["enabledDomains"], ["content"])
            self.assertEqual(
                report["productOpsHealth"],
                {"status": "skipped", "reason": "domain_scoped_verification"},
            )

    def test_content_scoped_probe_runs_only_content_flutter_contract(self) -> None:
        calls: list[list[str]] = []

        def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "content contract passed")

        with mock.patch.object(local_gamma_t3.subprocess, "run", side_effect=run):
            checks = local_gamma_t3.run_flutter_contracts(
                "https://gamma.example",
                "https://gamma-product-ops.example",
                {"content"},
                include_product_ops=False,
            )

        self.assertEqual([check["name"] for check in checks], ["content_api_contract"])
        self.assertEqual(len(calls), 1)
        self.assertIn(
            "test/api_integration/cloud/content/api_contract_runner.dart",
            calls[0],
        )

    def test_gamma_integration_profile_uses_content_scoped_t3_probe(self) -> None:
        with mock.patch.object(stackctl, "_local_target_runtime_ready", return_value=True):
            commands = stackctl._selected_profile_commands(
                "gamma",
                "gamma-local",
                stackctl.VerificationProfile.INTEGRATION,
            )

        probe = next(command for command in commands if command["name"] == "gamma-local-t3")
        self.assertEqual(
            probe["argv"],
            [
                "python3",
                "quwoquan_app/scripts/gamma/run_local_gamma_t3.py",
                "--enabled-domain",
                "content",
            ],
        )


if __name__ == "__main__":
    unittest.main()

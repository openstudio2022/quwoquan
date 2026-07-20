from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_app.scripts.gamma import run_local_gamma_t3 as local_gamma_t3


class LocalGammaCommentSeedContractTest(unittest.TestCase):
    def test_comment_fixture_maps_to_canonical_mongo_document(self) -> None:
        document = local_gamma_t3.fixture_comment_to_doc(
            {
                "commentId": "fixture_comment_parent_001",
                "postId": "fixture_photo_001",
                "authorId": "fixture_user_current",
                "authorDisplayNameSnapshot": "契约用户",
                "authorAvatarUrlSnapshot": "media/avatar/fixture.png",
                "content": "主评论示例",
                "createdAt": "2026-06-05T12:00:00Z",
                "authorIpLocation": "浙江",
                "hotScore": 128,
                "isPinned": True,
                "pinnedAt": "2026-06-05T12:30:00Z",
            }
        )

        self.assertEqual(document["_id"], "fixture_comment_parent_001")
        self.assertEqual(document["status"], "active")
        self.assertEqual(document["authorIpLocation"], "浙江")
        self.assertEqual(document["hotScore"], 128)
        self.assertEqual(document["parentCommentId"], "")
        self.assertEqual(document["attachmentMediaIds"], [])
        self.assertEqual(document["mentions"], [])

    def test_content_seed_replaces_fixture_post_threads_and_verifies_comments(
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
        self.assertEqual(result["insertedCommentCount"], 1)
        self.assertIn(
            "dbh.comments.deleteMany({postId: {$in: postIds}})",
            seed_script,
        )
        self.assertIn(
            "commentStoredCount !== comments.length",
            seed_script,
        )
        self.assertIn('"authorIpLocation": "浙江"', seed_script)
        self.assertIn('"hotScore": 128', seed_script)


if __name__ == "__main__":
    unittest.main()

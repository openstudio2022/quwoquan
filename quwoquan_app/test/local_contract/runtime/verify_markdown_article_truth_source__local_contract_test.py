#!/usr/bin/env python3
"""Markdown 文章真相源门禁的 local_contract。"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = (
    REPO_ROOT
    / "quwoquan_app"
    / "scripts"
    / "content_service"
    / "content"
    / "post"
    / "verify_markdown_article_no_article_document.py"
)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_markdown_article_truth_source", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifyMarkdownArticleTruthSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def test_service_article_requires_embedded_markdown(self) -> None:
        payload = {
            "postId": "post-1",
            "contentType": "article",
            "articleRenderProfile": {},
        }
        failures = self.verifier.validate_article(
            payload,
            location="fixture.posts[0]",
            source_path=Path("fixture.json"),
            is_document_root=False,
        )
        self.assertEqual(
            failures,
            ["fixture.posts[0]: article missing articleMarkdown"],
        )

    def test_canonical_data_article_uses_sibling_markdown_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            (root / "article.md").write_text("# 正文\n", encoding="utf-8")
            payload = {
                "schema": "quwoquan_data.post_object",
                "contentType": "article",
                "finalContentRef": "article.md",
                "articleRenderProfile": {},
            }
            failures = self.verifier.validate_article(
                payload,
                location=str(manifest_path),
                source_path=manifest_path,
                is_document_root=True,
            )
        self.assertEqual(failures, [])

    def test_data_article_rejects_missing_markdown_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            payload = {
                "schema": "quwoquan_data.post_manifest",
                "contentType": "article",
                "articleRenderProfile": {},
            }
            failures = self.verifier.validate_article(
                payload,
                location=str(manifest_path),
                source_path=manifest_path,
                is_document_root=True,
            )
        self.assertTrue(
            any("missing non-empty article.md" in failure for failure in failures)
        )

    def test_object_job_is_not_misclassified_as_service_post(self) -> None:
        payload = {
            "schema": "quwoquan.object_job",
            "contentType": "article",
            "authorId": None,
        }
        failures = self.verifier.validate_article(
            payload,
            location="object_queue/job.json",
            source_path=Path("job.json"),
            is_document_root=True,
        )
        self.assertEqual(failures, [])

    def test_article_document_is_always_rejected(self) -> None:
        payload = {
            "schema": "quwoquan.object_job",
            "contentType": "article",
            "articleDocument": {"body": "retired"},
        }
        failures = self.verifier.validate_article(
            payload,
            location="object_queue/job.json",
            source_path=Path("job.json"),
            is_document_root=True,
        )
        self.assertEqual(
            failures,
            ["object_queue/job.json: article contains articleDocument"],
        )


if __name__ == "__main__":
    unittest.main()

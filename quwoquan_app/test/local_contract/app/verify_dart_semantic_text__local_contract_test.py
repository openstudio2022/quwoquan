#!/usr/bin/env python3
"""用户可见文案语义门禁的 local_contract。"""

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
    / "runtime"
    / "verify_dart_semantic.py"
)


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_dart_semantic", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifyDartSemanticTextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def scan(self, relative_path: str, source: str):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / relative_path
            path.parent.mkdir(parents=True)
            path.write_text(source, encoding="utf-8")
            return self.verifier.scan_user_visible_text_literals(
                str(path),
                str(root / "quwoquan_app" / "lib"),
                str(root),
            )

    def test_detects_chinese_in_user_visible_argument(self) -> None:
        violations = self.scan(
            "quwoquan_app/lib/ui/content/example.dart",
            "Widget build() => Card(title: '未迁移文案');\n",
        )
        self.assertEqual(len(violations), 1)

    def test_detects_multiline_text_literal(self) -> None:
        violations = self.scan(
            "quwoquan_app/lib/ui/chat/example.dart",
            "Widget build() => Text(\n  '未迁移文案',\n);\n",
        )
        self.assertEqual(len(violations), 1)

    def test_detects_intersection_cloud_fallback_copy(self) -> None:
        violations = self.scan(
            "quwoquan_app/lib/cloud/services/content/intersection_statement.dart",
            "const fallback = Card(description: '你们都去过这里');\n",
        )
        self.assertEqual(len(violations), 1)

    def test_ignores_constants_comments_and_generated_metadata(self) -> None:
        constants = self.scan(
            "quwoquan_app/lib/ui/content/example.dart",
            "const copy = '常量定义';\n// title: '注释文案'\n",
        )
        generated = self.scan(
            "quwoquan_app/lib/ui/content/generated/example.g.dart",
            "const row = Row(description: '元数据生成说明');\n",
        )
        self.assertEqual(constants, [])
        self.assertEqual(generated, [])

    def test_migrated_scope_is_zero_tolerance(self) -> None:
        self.assertTrue(
            self.verifier.is_migrated_text_scope(
                "quwoquan_app/lib/ui/content/example.dart"
            )
        )
        self.assertFalse(
            self.verifier.is_migrated_text_scope(
                "quwoquan_app/lib/ui/rtc/example.dart"
            )
        )
        self.assertTrue(
            self.verifier.is_migrated_text_scope(
                "quwoquan_app/lib/cloud/services/content/intersection_statement.dart"
            )
        )

    def test_generated_metadata_is_outside_visual_token_scan(self) -> None:
        lib_root = "/repo/quwoquan_app/lib"
        self.assertTrue(
            self.verifier.should_skip(
                f"{lib_root}/application/content/media/generated/policy.g.dart",
                lib_root,
            )
        )
        self.assertFalse(
            self.verifier.should_skip(
                f"{lib_root}/ui/content/page.dart",
                lib_root,
            )
        )


if __name__ == "__main__":
    unittest.main()

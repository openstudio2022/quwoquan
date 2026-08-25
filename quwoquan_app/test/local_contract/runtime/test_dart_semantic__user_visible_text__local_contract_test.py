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
    / "runtime" / "observability" / "verify_dart_semantic.py"
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
            "quwoquan_app/lib/service/content_service/content/post/presentation/example.dart",
            "Widget build() => Card(title: '未迁移文案');\n",
        )
        self.assertEqual(len(violations), 1)

    def test_detects_multiline_text_literal(self) -> None:
        violations = self.scan(
            "quwoquan_app/lib/service/chat_service/chat/message/presentation/example.dart",
            "Widget build() => Text(\n  '未迁移文案',\n);\n",
        )
        self.assertEqual(len(violations), 1)

    def test_detects_intersection_cloud_fallback_copy(self) -> None:
        violations = self.scan(
            "quwoquan_app/lib/service/recommendation_service/recommendation/"
            "recommendation_feature_profile_view/presentation/intersection_statement_row.dart",
            "const fallback = Card(description: '你们都去过这里');\n",
        )
        self.assertEqual(len(violations), 1)

    def test_ignores_constants_comments_and_generated_metadata(self) -> None:
        constants = self.scan(
            "quwoquan_app/lib/service/content_service/content/post/presentation/example.dart",
            "const copy = '常量定义';\n// title: '注释文案'\n",
        )
        generated = self.scan(
            "quwoquan_app/lib/service/content_service/content/post/presentation/generated/example.g.dart",
            "const row = Row(description: '元数据生成说明');\n",
        )
        self.assertEqual(constants, [])
        self.assertEqual(generated, [])

    def test_every_scope_is_zero_tolerance(self) -> None:
        # 曾经按域豁免的作用域现在与已迁移域同判，门禁不再有例外面。
        for relative_path in (
            "quwoquan_app/lib/service/content_service/content/post/presentation/example.dart",
            "quwoquan_app/lib/service/rtc_service/rtc/call_session/presentation/example.dart",
        ):
            with self.subTest(relative_path=relative_path):
                violations = self.scan(
                    relative_path,
                    "Widget build() => Card(title: '未迁移文案');\n",
                )
                self.assertEqual(len(violations), 1)

    def test_generated_metadata_is_outside_visual_token_scan(self) -> None:
        lib_root = "/repo/quwoquan_app/lib"
        self.assertTrue(
            self.verifier.should_skip(
                f"{lib_root}/content/media/media_asset/application/generated/content_image_variant_policy.g.dart",
                lib_root,
            )
        )
        self.assertFalse(
            self.verifier.should_skip(
                f"{lib_root}/content/content/post/presentation/page.dart",
                lib_root,
            )
        )

    def test_only_canonical_design_system_root_is_excluded(self) -> None:
        lib_root = "/repo/quwoquan_app/lib"
        self.assertTrue(
            self.verifier.should_skip(
                f"{lib_root}/design_system/colors/app_colors.dart",
                lib_root,
            )
        )
        self.assertFalse(
            self.verifier.should_skip(
                f"{lib_root}/content/content/post/presentation/design_system/card.dart",
                lib_root,
            )
        )

    def test_scans_design_system_copy_but_not_its_visual_tokens(self) -> None:
        lib_root = "/repo/quwoquan_app/lib"
        path = f"{lib_root}/design_system/navigation/example.dart"
        self.assertTrue(self.verifier.should_skip(path, lib_root))
        violations = self.scan(
            "quwoquan_app/lib/design_system/navigation/example.dart",
            "const item = Item(label: '推荐');\n",
        )
        self.assertEqual(len(violations), 1)

    def test_scans_runtime_composition_shell_copy(self) -> None:
        violations = self.scan(
            "quwoquan_app/lib/runtime/shell/example.dart",
            "Widget build() => App(title: '应用标题');\n",
        )
        self.assertEqual(len(violations), 1)

    def test_retired_ui_root_is_not_a_positive_scan_input(self) -> None:
        violations = self.scan(
            "quwoquan_app/lib/ui/content/example.dart",
            "Widget build() => Card(title: '旧目录文案');\n",
        )
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()

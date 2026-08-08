#!/usr/bin/env python3
"""Canonical unified-error ratchet local contract."""

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
    / "runtime" / "error" / "verify_unified_error_semantics_ratchet.py"
)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_unified_error_semantics_ratchet",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifyUnifiedErrorSemanticsRatchetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def scan(self, files: dict[str, str]):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative, source in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
            return self.verifier.collect_violations(
                str(root / "quwoquan_app" / "lib"),
                str(root),
            )

    def test_canonical_page_shape_includes_parts_and_runtime_shells(self) -> None:
        self.assertTrue(
            self.verifier.is_page_like(
                "quwoquan_app/lib/service/content_service/content/post/presentation/page_part.dart"
            )
        )
        self.assertTrue(
            self.verifier.is_page_like(
                "quwoquan_app/lib/runtime/shell/composition.dart"
            )
        )
        self.assertFalse(
            self.verifier.is_page_like("quwoquan_app/lib/ui/content/old.dart")
        )

    def test_warning_triangle_is_not_a_generic_error_icon(self) -> None:
        violations = self.scan(
            {
                "quwoquan_app/lib/service/circle_service/circle_management/gathering/presentation/page.dart": (
                    "final icon = CupertinoIcons.exclamationmark_triangle;\n"
                ),
            }
        )
        self.assertEqual(violations, [])

    def test_bare_exclamation_icon_is_blocked(self) -> None:
        violations = self.scan(
            {
                "quwoquan_app/lib/service/circle_service/circle_management/gathering/presentation/page.dart": (
                    "final icon = CupertinoIcons.exclamationmark;\n"
                ),
            }
        )
        self.assertEqual(len(violations), 1)
        self.assertIn("通用错误态禁止新增", violations[0][3])

    def test_runtime_shell_direct_display_message_is_blocked(self) -> None:
        violations = self.scan(
            {
                "quwoquan_app/lib/runtime/shell/page.dart": (
                    "final copy = runtimeErrorDisplayMessage(error);\n"
                ),
            }
        )
        self.assertEqual(len(violations), 1)


if __name__ == "__main__":
    unittest.main()

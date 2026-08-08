#!/usr/bin/env python3
"""Canonical recoverable-error surface scanner local contract."""

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
    / "runtime" / "error" / "verify_app_recoverable_error_surface.py"
)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_app_recoverable_error_surface",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifyAppRecoverableErrorSurfaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def scan(self, files: dict[str, str]) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative, source in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
            return self.verifier.collect_ui_failures(
                repo_root=root,
                app_lib=root / "quwoquan_app" / "lib",
            )

    def test_scans_canonical_presentation_and_runtime_shells(self) -> None:
        failures = self.scan(
            {
                "quwoquan_app/lib/service/content_service/content/post/presentation/page.dart": (
                    "Widget build() => CupertinoActivityIndicator();\n"
                ),
                "quwoquan_app/lib/runtime/shell/root.dart": (
                    "Widget build() => CircularProgressIndicator();\n"
                ),
                "quwoquan_app/lib/runtime/shell/app.dart": (
                    "Widget build() => CupertinoActivityIndicator();\n"
                ),
            }
        )
        self.assertEqual(len(failures), 3)

    def test_ignores_retired_ui_root_and_generated_output(self) -> None:
        failures = self.scan(
            {
                "quwoquan_app/lib/ui/content/old.dart": (
                    "Widget build() => CupertinoActivityIndicator();\n"
                ),
                "quwoquan_app/lib/service/content_service/content/post/presentation/generated/view.g.dart": (
                    "Widget build() => CupertinoActivityIndicator();\n"
                ),
            }
        )
        self.assertEqual(failures, [])

    def test_allows_only_the_exact_shared_progress_primitives(self) -> None:
        failures = self.scan(
            {
                "quwoquan_app/lib/design_system/feedback/app_request_feedback.dart": (
                    "Widget build() => CupertinoActivityIndicator();\n"
                ),
                "quwoquan_app/lib/design_system/feedback/error_states/app_error_action_row.dart": (
                    "Widget build() => CupertinoActivityIndicator();\n"
                ),
                "quwoquan_app/lib/design_system/layout/ios_selection_page_components.dart": (
                    "Widget build() => CupertinoActivityIndicator();\n"
                ),
                "quwoquan_app/lib/design_system/feedback/other_feedback.dart": (
                    "Widget build() => CupertinoActivityIndicator();\n"
                ),
            }
        )
        self.assertEqual(len(failures), 1)
        self.assertIn("other_feedback.dart:1", failures[0])

    def test_blocks_direct_recoverable_copy_in_canonical_presentation(self) -> None:
        failures = self.scan(
            {
                "quwoquan_app/lib/service/content_service/media/upload/presentation/page.dart": (
                    "final semantic = UiErrorSemantic(\n"
                    "  category: UiErrorCategory.pageLoad,\n"
                    ");\n"
                ),
            }
        )
        self.assertEqual(len(failures), 1)
        self.assertIn("AppUserRecoveryContract", failures[0])


if __name__ == "__main__":
    unittest.main()

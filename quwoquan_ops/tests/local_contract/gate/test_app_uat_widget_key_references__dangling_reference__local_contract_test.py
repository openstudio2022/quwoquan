#!/usr/bin/env python3
"""UAT 引用的 Widget key ↔ App 实现同源门禁的 local_contract。"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "quwoquan_ops" / "gate" / "verify_app_uat_widget_key_references.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_app_uat_widget_key_references", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AppUatWidgetKeyReferencesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def lib_universe(self, source: str) -> tuple[set[str], list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            lib_root = Path(directory) / "lib"
            lib_root.mkdir()
            (lib_root / "page.dart").write_text(source, encoding="utf-8")
            original = self.verifier.LIB_ROOT
            self.verifier.LIB_ROOT = lib_root
            try:
                return self.verifier._lib_key_universe()
            finally:
                self.verifier.LIB_ROOT = original

    def uat_references(self, source: str) -> dict[str, list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            uat_root = Path(directory) / "user_acceptance"
            uat_root.mkdir()
            (uat_root / "journey_test.dart").write_text(source, encoding="utf-8")
            original_roots = self.verifier.UAT_ROOTS
            original_repo = self.verifier.REPO_ROOT
            self.verifier.UAT_ROOTS = (uat_root,)
            self.verifier.REPO_ROOT = Path(directory)
            try:
                return self.verifier._uat_key_references()
            finally:
                self.verifier.UAT_ROOTS = original_roots
                self.verifier.REPO_ROOT = original_repo

    def test_exact_literal_is_produced(self) -> None:
        self.assertTrue(
            self.verifier._is_produced("home-search-chrome", {"home-search-chrome"}, [])
        )

    def test_key_absent_from_lib_is_dangling(self) -> None:
        self.assertFalse(
            self.verifier._is_produced("home-search-chrome", {"other-key"}, [])
        )

    def test_dynamic_key_resolves_through_its_template_prefix(self) -> None:
        self.assertTrue(
            self.verifier._is_produced("home-feed-card-0", set(), ["home-feed-card-"])
        )

    def test_interpolated_template_yields_its_static_prefix(self) -> None:
        _, prefixes = self.lib_universe(
            "Widget build() => Card(key: ValueKey('home-feed-card-$index'));\n"
        )
        self.assertIn("home-feed-card-", prefixes)

    def test_short_prefix_does_not_wave_everything_through(self) -> None:
        # 前缀短于 4 个字符没有区分度，收进来会让门禁失效。
        _, prefixes = self.lib_universe(
            "Widget build() => Card(key: ValueKey('ab$index'));\n"
        )
        self.assertEqual(prefixes, [])

    def test_recognizes_every_uat_key_spelling(self) -> None:
        references = self.uat_references(
            "await tester.tap(find.byKey(const ValueKey<String>('typed-key')));\n"
            "await tester.tap(find.byKey(const ValueKey('value-key')));\n"
            "await tester.tap(find.byKey(const Key('plain-key')));\n"
        )
        self.assertEqual(
            sorted(references), ["plain-key", "typed-key", "value-key"]
        )

    def test_gate_currently_passes_on_the_real_tree(self) -> None:
        self.assertEqual(self.verifier.main(), 0)


if __name__ == "__main__":
    unittest.main()

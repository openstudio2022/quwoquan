#!/usr/bin/env python3
"""R03 只扫描 canonical source roots，不得吸收可重建缓存。"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GATE = (
    ROOT
    / "quwoquan_app"
    / "scripts"
    / "runtime"
    / "architecture"
    / "verify_file_line_budget.py"
)
SPEC = importlib.util.spec_from_file_location("verify_file_line_budget", GATE)
assert SPEC is not None and SPEC.loader is not None
budget = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(budget)


class FileLineBudgetSourceRootsContract(unittest.TestCase):
    def test_service_repository_root_is_not_a_scan_root(self) -> None:
        self.assertNotIn(("quwoquan_service", "*.go"), budget.SOURCE_ROOT_SPECS)
        self.assertIn(
            ("quwoquan_service/services", "*.go"), budget.SOURCE_ROOT_SPECS
        )
        self.assertIn(
            ("quwoquan_service/internal", "*.go"), budget.SOURCE_ROOT_SPECS
        )

    def test_qwq_output_and_cache_segments_are_always_excluded(self) -> None:
        for relative in (
            "quwoquan_service/.qwq_output/go-mod/example/cache.go",
            "quwoquan_service/services/example/.qwq_output/cache.go",
            "quwoquan_service/services/example/.cache/go-build/cache.go",
        ):
            with self.subTest(relative=relative):
                self.assertTrue(budget.is_excluded(relative, "cache.go"))

    def test_scan_reads_canonical_source_but_not_repo_cache_or_copied_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = (
                root
                / "quwoquan_service"
                / "services"
                / "example-service"
                / "internal"
                / "example.go"
            )
            cached = (
                root
                / "quwoquan_service"
                / ".qwq_output"
                / "go-mod"
                / "example"
                / "cache.go"
            )
            nested_cache = (
                root
                / "quwoquan_service"
                / "services"
                / "example-service"
                / ".cache"
                / "go-build"
                / "cache.go"
            )
            copied_tree = (
                root
                / "quwoquan_service"
                / "quwoquan_app"
                / "copied.go"
            )
            for path in (canonical, cached, nested_cache, copied_tree):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("package example\n" * 1001, encoding="utf-8")

            self.assertEqual(
                budget.scan(root),
                {
                    "quwoquan_service/services/example-service/internal/example.go": 1001
                },
            )


if __name__ == "__main__":
    unittest.main()

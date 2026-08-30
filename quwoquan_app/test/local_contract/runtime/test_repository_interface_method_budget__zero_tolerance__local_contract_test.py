#!/usr/bin/env python3
"""R02 Repository 接口方法数预算门禁的 local_contract。"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = (
    REPO_ROOT
    / "quwoquan_app"
    / "scripts"
    / "runtime" / "architecture" / "verify_repository_interface_method_budget.py"
)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_repository_interface_method_budget", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepositoryInterfaceMethodBudgetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def body_of(self, source: str) -> str:
        brace = source.find("{")
        return self.verifier.extract_body(source, brace)

    def test_threshold_is_ten(self) -> None:
        self.assertEqual(self.verifier.METHOD_THRESHOLD, 10)

    def test_counts_top_level_member_declarations(self) -> None:
        body = self.body_of(
            "abstract class ExampleRepository {\n"
            "  Future<void> save(Post post);\n"
            "  Future<Post?> findById(String id);\n"
            "}\n"
        )
        self.assertEqual(self.verifier.count_members(body), 2)

    def test_umbrella_interface_counts_zero(self) -> None:
        # 伞组合接口只 implements 窄接口、body 为空，不该被计成超预算。
        body = self.body_of(
            "abstract class ContentRepository implements ContentReadRepository, "
            "ContentWriteRepository {}\n"
        )
        self.assertEqual(self.verifier.count_members(body), 0)

    def test_nested_parameter_semicolons_do_not_inflate_count(self) -> None:
        body = self.body_of(
            "abstract class ExampleRepository {\n"
            "  Future<void> save({required Post post, void Function()? onDone});\n"
            "}\n"
        )
        self.assertEqual(self.verifier.count_members(body), 1)

    def test_comments_are_not_counted_as_members(self) -> None:
        stripped = self.verifier.strip_comments(
            "abstract class ExampleRepository {\n"
            "  // Future<void> commented();\n"
            "  /* Future<void> blocked(); */\n"
            "  Future<void> real();\n"
            "}\n"
        )
        self.assertEqual(self.verifier.count_members(self.body_of(stripped)), 1)

    def test_gate_has_no_exemption_surface(self) -> None:
        # 该门禁已转零容忍：不得再出现 allowlist / baseline 之类的豁免入口。
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        for forbidden in ("allowlist", "ALLOWLIST", "baseline", "BASELINE"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

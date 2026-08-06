"""`verify_ui_mock_isolation` 的替身判定必须按结构事实，不按类名词汇。

此前判据是 `class (Mock|Stub|Noop|Fake|Memory|InMemory)*Repository`，两个方向都错：
assistant 长期记忆的 `MemoryProfileRepository` 会被误伤，替身改名成 `LocalPostRepository`
则直接逃逸。现判据是 import 边（Dart 必须先 import 才能引用）与声明位置。
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "quwoquan_app" / "scripts" / "env" / "verify_ui_mock_isolation.py"


def _load_gate():
    script_dir = str(SCRIPT.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("verify_ui_mock_isolation", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载门禁：{SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RETIRED_CLASS_NAME_RULE = re.compile(
    r"\bclass\s+(?:Mock|Stub|Noop|Fake|Memory|InMemory)"
    r"[A-Za-z0-9_]*(?:Repository|Query|Writer|Reader|Facet|Store|Service|Client|Adapter)\b"
)


class UiMockIsolationStructuralCriteriaTest(unittest.TestCase):
    def test_business_memory_concept_is_not_flagged(self) -> None:
        """assistant 长期记忆是业务概念；名字含 Memory 不构成替身。"""
        gate = _load_gate()
        source = (
            "import 'package:quwoquan_app/service/assistant_service/assistant/"
            "assistant_learning_fact/domain/memory_profile.dart';\n\n"
            "final class MemoryProfileRepository implements MemoryProfilePort {\n"
            "  MemoryProfileRepository(this._client);\n"
            "  final CloudClient _client;\n"
            "}\n"
        )
        self.assertEqual(gate.test_library_imports(source), [])
        self.assertIsNotNone(
            RETIRED_CLASS_NAME_RULE.search(source),
            "被删掉的类名判据确实会误伤这个业务概念，负例才有意义",
        )

    def test_cleanly_named_double_is_caught_by_import_edge(self) -> None:
        """替身改成干净名字仍必须命中——这是类名判据漏掉的那一半。"""
        gate = _load_gate()
        source = (
            "import 'package:mocktail/mocktail.dart';\n"
            "import 'package:quwoquan_app/service/content_service/content/post/"
            "application/post_query.dart';\n\n"
            "final class LocalPostRepository extends Mock implements PostQuery {}\n"
        )
        self.assertEqual(
            gate.test_library_imports(source),
            ["package:mocktail/mocktail.dart"],
        )
        self.assertIsNone(
            RETIRED_CLASS_NAME_RULE.search(source),
            "该正例刻意不含替身类名词汇；若能被词汇命中则测不出结构判据的价值",
        )

    def test_flutter_test_and_patrol_imports_are_caught(self) -> None:
        gate = _load_gate()
        for target in (
            "package:flutter_test/flutter_test.dart",
            "package:patrol/patrol.dart",
            "package:mockito/mockito.dart",
            "package:http/testing.dart",
        ):
            with self.subTest(target=target):
                self.assertEqual(
                    gate.test_library_imports(f"import '{target}';\n"),
                    [target],
                )

    def test_production_imports_are_not_flagged(self) -> None:
        gate = _load_gate()
        source = (
            "import 'package:flutter/widgets.dart';\n"
            "import 'package:flutter_riverpod/flutter_riverpod.dart';\n"
            "import 'package:http/http.dart';\n"
            "import 'package:quwoquan_app/runtime/di/app_providers.dart';\n"
        )
        self.assertEqual(gate.test_library_imports(source), [])

    def test_retired_class_name_rule_is_not_resurrected(self) -> None:
        gate = _load_gate()
        self.assertFalse(hasattr(gate, "BUSINESS_TEST_DOUBLE_CLASS_RE"))

    def test_production_test_library_import_baseline_is_empty(self) -> None:
        """Patrol support 已迁出 production lib，豁免基线必须保持归零。"""
        gate = _load_gate()
        self.assertEqual(gate.TEST_LIBRARY_IMPORT_BASELINE, frozenset())


if __name__ == "__main__":
    unittest.main()

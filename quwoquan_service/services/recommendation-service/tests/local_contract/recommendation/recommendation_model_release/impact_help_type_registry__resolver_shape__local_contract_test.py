#!/usr/bin/env python3
"""spec_ref: specs/feature-tree/runtime/spec.md#dom-001"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[7]
SCRIPT = (
    REPO_ROOT
    / "quwoquan_service"
    / "scripts"
    / "recommendation-service"
    / "recommendation"
    / "recommendation_model_release"
    / "verify_impact_help_type_registry.py"
)
STANDARD_ICON_KEYS = {
    "connect",
    "communityJoin",
    "decisionCompass",
    "knowledgeRead",
    "spreadShare",
    "audienceReach",
    "cascadePath",
}
EXPECTED = {
    "iconKeyByHelpType": {
        key: key for key in STANDARD_ICON_KEYS if key != "cascadePath"
    },
    "defaultIconKey": "cascadePath",
}


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_impact_help_type_registry",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def resolver_source(
    icon_keys: set[str],
    *,
    map_comment: str = "",
    extra_body: str = "",
) -> str:
    entries = "\n".join(
        f"    '{key}': CupertinoIcons.link," for key in sorted(icon_keys)
    )
    return f"""
import 'impact_help_type_metadata.g.dart';

class IntersectionIconResolver {{
  static const Map<String, IconData> _iconByKey = <String, IconData>{{
{entries}
    {map_comment}
  }};

  static IconData? _iconForKey(String key) => _iconByKey[key];
  static String tone(String key) => impactToneByIconKey[key] ?? 'stone';
  {extra_body}
}}
"""


class ImpactHelpTypeRegistryResolverShapeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def validate(self, source: str) -> list[str]:
        problems: list[str] = []
        self.verifier.validate_resolver_source(source, EXPECTED, problems)
        return problems

    def test_complete_const_icon_map_passes(self) -> None:
        self.assertEqual(self.validate(resolver_source(STANDARD_ICON_KEYS)), [])

    def test_missing_standard_icon_map_key_fails(self) -> None:
        problems = self.validate(
            resolver_source(STANDARD_ICON_KEYS - {"decisionCompass"})
        )
        self.assertTrue(
            any("decisionCompass" in problem and "missing" in problem for problem in problems),
            problems,
        )

    def test_legacy_icon_map_key_fails(self) -> None:
        problems = self.validate(resolver_source(STANDARD_ICON_KEYS | {"compass"}))
        self.assertTrue(
            any("compass" in problem and "legacy" in problem for problem in problems),
            problems,
        )

    def test_commented_key_does_not_impersonate_a_map_entry(self) -> None:
        problems = self.validate(
            resolver_source(
                STANDARD_ICON_KEYS - {"knowledgeRead"},
                map_comment="// 'knowledgeRead': CupertinoIcons.book_fill,",
            )
        )
        self.assertTrue(
            any("knowledgeRead" in problem and "missing" in problem for problem in problems),
            problems,
        )

    def test_legacy_switch_case_fails(self) -> None:
        problems = self.validate(
            resolver_source(
                STANDARD_ICON_KEYS,
                extra_body="""
IconData legacy(String key) {
  switch (key) {
    case 'read':
      return CupertinoIcons.book;
    default:
      return CupertinoIcons.link;
  }
}
""",
            )
        )
        self.assertTrue(
            any("read" in problem and "legacy" in problem for problem in problems),
            problems,
        )


if __name__ == "__main__":
    unittest.main()

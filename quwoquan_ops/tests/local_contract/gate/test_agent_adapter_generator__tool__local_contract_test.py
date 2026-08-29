#!/usr/bin/env python3
"""Cursor/Codex Reviewer adapter 中性生成合约。"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import ModuleType

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TOOL = _REPO_ROOT / "quwoquan_ops/tools/generate_agent_adapters.py"


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_agent_adapters", _TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_tool = _load_tool()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_contract(root: Path) -> None:
    _write(
        root / _tool.CONTRACT_REL,
        yaml.safe_dump(
            {
                "schema_version": 1,
                "tracked_projections": {
                    "authoring_source": _tool.SOURCE_REL.as_posix(),
                    "generator": _tool.GENERATOR_REL,
                    "outputs": [
                        _tool.CURSOR_TARGET_REL.as_posix(),
                        _tool.CODEX_TARGET_REL.as_posix(),
                    ],
                    "manual_edit": "forbidden",
                },
            },
            sort_keys=False,
        ),
    )


_SOURCE = """---
name: reviewer
description: Shared read-only reviewer.
access: read-only
---

只消费命名 evidence，不自行运行 gate。
"""


class AgentAdapterGeneratorTest(unittest.TestCase):
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/
    #   agent-skill-review-context-organization/spec.md#gwt-005

    def test_one_neutral_source_generates_cursor_and_codex_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract(root)
            _write(root / _tool.SOURCE_REL, _SOURCE)

            self.assertEqual(_tool.sync(root, check=False), [])
            self.assertEqual(_tool.sync(root, check=True), [])

            cursor_text = (root / _tool.CURSOR_TARGET_REL).read_text(encoding="utf-8")
            _, frontmatter, cursor_body = cursor_text.split("---", 2)
            cursor_fields = yaml.safe_load(frontmatter)
            self.assertEqual(cursor_fields["name"], "reviewer")
            self.assertTrue(cursor_fields["readonly"])
            self.assertIn("不自行运行 gate", cursor_body)

            codex_fields = tomllib.loads(
                (root / _tool.CODEX_TARGET_REL).read_text(encoding="utf-8")
            )
            self.assertEqual(codex_fields["sandbox_mode"], "read-only")
            self.assertIn("不自行运行 gate", codex_fields["developer_instructions"])

    def test_check_rejects_stale_missing_and_orphan_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract(root)
            _write(root / _tool.SOURCE_REL, _SOURCE)
            _write(root / _tool.CURSOR_TARGET_REL, "stale\n")
            _write(root / ".cursor/agents/orphan.md", "orphan\n")
            _write(root / ".codex/agents/orphan.toml", "orphan = true\n")

            issues = _tool.sync(root, check=True)
            self.assertTrue(any("与中性源不一致" in issue for issue in issues), issues)
            self.assertTrue(any("缺失" in issue for issue in issues), issues)
            self.assertEqual(
                sum("孤儿 adapter" in issue for issue in issues),
                2,
                issues,
            )

            self.assertEqual(_tool.sync(root, check=False), [])
            self.assertFalse((root / ".cursor/agents/orphan.md").exists())
            self.assertFalse((root / ".codex/agents/orphan.toml").exists())
            self.assertEqual(_tool.sync(root, check=True), [])

    def test_source_rejects_harness_specific_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract(root)
            _write(root / _tool.SOURCE_REL, _SOURCE.replace("access:", "tools: Bash\naccess:"))
            with self.assertRaisesRegex(ValueError, "非中性字段 tools"):
                _tool.expected_outputs(root)

    def test_projection_contract_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_contract(root)
            contract = root / _tool.CONTRACT_REL
            contract.write_text(
                contract.read_text(encoding="utf-8").replace(
                    ".cursor/agents/reviewer.md",
                    ".cursor/agents/other.md",
                ),
                encoding="utf-8",
            )
            _write(root / _tool.SOURCE_REL, _SOURCE)
            with self.assertRaisesRegex(ValueError, "tracked_projections"):
                _tool.expected_outputs(root)


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)

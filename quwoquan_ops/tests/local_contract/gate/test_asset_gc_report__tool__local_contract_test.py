#!/usr/bin/env python3
"""资产垃圾回收报告与 distill 沉淀资产合约。

三类垃圾（僵尸 reference、harness 分叉、AGENTS.md 与特性树重复正文）必须各有
能让报告非空的负例；distill 工作流的候选结构与回写约束必须锁在真相源文件上。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TOOL = _REPO_ROOT / "quwoquan_ops/tools/report_asset_gc.py"


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_asset_gc", _TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_tool = _load_tool()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class AssetGcReportTest(unittest.TestCase):
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-003.t1

    def test_zombie_reference_is_reported(self) -> None:
        with self._tmp() as root:
            _write(
                root / ".agents/skills/demo/SKILL.md",
                "---\nname: demo\n---\n\n见 [用法](references/used.md)。\n",
            )
            _write(root / ".agents/skills/demo/references/used.md", "被引用。\n")
            _write(root / ".agents/skills/demo/references/orphan.md", "没人引用。\n")
            zombies = _tool.collect_zombie_references(root)
            self.assertEqual(zombies, [".agents/skills/demo/references/orphan.md"])

    def test_directory_link_and_role_md_are_not_zombies(self) -> None:
        """目录级链接覆盖目录下全部文件；ROLE.md 结构性加载豁免。"""
        with self._tmp() as root:
            _write(
                root / ".agents/skills/demo/SKILL.md",
                "---\nname: demo\n---\n\n按载体读 [references/carriers/](references/carriers/)。\n",
            )
            _write(root / ".agents/skills/demo/references/carriers/a.md", "载体 A。\n")
            _write(
                root / ".agents/skills/demo/references/roles/x/ROLE.md", "角色。\n"
            )
            self.assertEqual(_tool.collect_zombie_references(root), [])

    def test_any_harness_workflow_stub_is_reported(self) -> None:
        with self._tmp() as root:
            _write(
                root / ".cursor/skills/forwarding/SKILL.md",
                "---\nname: forwarding\n---\n\n见 .agents/skills/forwarding/SKILL.md\n",
            )
            issues = _tool.collect_harness_forks(root)
            self.assertEqual(len(issues), 1, issues)
            self.assertIn("宿主专属 Workflow stub", issues[0])

    def test_duplicate_body_between_agents_and_tree_is_reported(self) -> None:
        paragraph = "这是一段足够长的治理正文，" * 10
        with self._tmp() as root:
            _write(root / "AGENTS.md", f"# 指南\n\n{paragraph}\n")
            _write(
                root / "specs/feature-tree/runtime/spec.md",
                f"# L1\n\n{paragraph}\n",
            )
            duplicates = _tool.collect_duplicate_bodies(root)
            self.assertEqual(len(duplicates), 1, duplicates)
            self.assertIn("AGENTS.md 与 specs/feature-tree/runtime/spec.md", duplicates[0])

    def test_clean_tree_reports_zero_candidates(self) -> None:
        with self._tmp() as root:
            _write(root / "AGENTS.md", "# 指南\n\n短。\n")
            report = _tool.build_report(root)
            self.assertEqual(report.count("- 无候选"), 3, report)

    def test_distill_skill_locks_candidate_structure_and_writeback(self) -> None:
        """SIT-003 沉淀子句锁定候选结构、人确认与正常下游。"""
        text = (_REPO_ROOT / ".agents/skills/distill/SKILL.md").read_text(
            encoding="utf-8"
        )
        for token in ("触发场景", "根因层", "唯一 owner 层", "gate/check/evidence 绑定"):
            self.assertIn(token, text, f"distill SKILL 缺候选字段「{token}」")
        self.assertIn("人确认", text.replace(" ", ""))
        self.assertIn("不直接改规则/规格/gate", text)
        handoff = text.split("## 条件性交接", 1)[1]
        self.assertIn("prd", handoff)
        self.assertIn("dev", handoff)

    @staticmethod
    def _tmp():
        import tempfile
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            with tempfile.TemporaryDirectory() as tmp:
                yield Path(tmp)

        return _ctx()


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)

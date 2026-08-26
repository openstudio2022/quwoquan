"""review_dispatch 派发装配合约。

派发装配一旦回退为主会话手工解析 YAML，就会重新出现跳过派发与无关 gate
误加载。本合约用真实 registry.yaml 锁住装配语义：profile 派生、when 求值、
gate 保序去重、非法输入拒绝，以及 triggers 第二套派发机制不得复活。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CLI = _REPO_ROOT / "quwoquan_ops/cli/review_dispatch.py"
_REGISTRY = _REPO_ROOT / ".agents/skills/review/references/registry.yaml"


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_review_dispatch", _CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_cli = _load_cli()
_registry = yaml.safe_load(_REGISTRY.read_text(encoding="utf-8"))


class ReviewDispatchAssemblyTest(unittest.TestCase):
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-004

    def test_pure_python_gate_change_loads_no_dart_roles(self) -> None:
        plan = _cli.build_plan(
            _registry,
            "dev",
            "POST",
            None,
            ["quwoquan_ops/gate/verify_handoff_manifest.py"],
        )
        self.assertIn("python-script", plan["profiles"])
        self.assertIn("gate", plan["profiles"])
        self.assertNotIn("dart-app", plan["profiles"])
        checklists = [
            checklist
            for item in plan["dispatches"]
            for checklist in item["checklists"]
        ]
        self.assertTrue(any("python-script" in c for c in checklists))
        self.assertFalse(any("dart-app" in c for c in checklists))
        self.assertFalse(any("flutter-page" in c for c in checklists))

    def test_dart_app_change_loads_dart_bundle_not_go(self) -> None:
        plan = _cli.build_plan(
            _registry,
            "dev",
            "POST",
            None,
            ["quwoquan_app/lib/service/content_service/foo.dart"],
        )
        self.assertIn("dart-app", plan["profiles"])
        checklists = [
            checklist
            for item in plan["dispatches"]
            for checklist in item["checklists"]
        ]
        self.assertTrue(any("dev/dart-app" in c for c in checklists))
        self.assertFalse(any("go-service" in c for c in checklists))

    def test_deliverable_alone_activates_profile(self) -> None:
        plan = _cli.build_plan(_registry, "prd", "POST", "page", [])
        self.assertIn("flutter-page", plan["profiles"])
        self.assertIn("ux", [item["role"] for item in plan["dispatches"]])

    def test_gates_are_deduplicated_preserving_order(self) -> None:
        plan = _cli.build_plan(
            _registry,
            "dev",
            "POST",
            None,
            ["quwoquan_ops/gate/verify_handoff_manifest.py"],
        )
        self.assertEqual(len(plan["gates"]), len(set(plan["gates"])))
        self.assertIn("make verify-retired-terms-zero", plan["gates"])

    def test_parameterized_gates_are_split_out_of_runnable(self) -> None:
        """参数化门（含 `<...>` 占位符）不得混入可直跑 gates。

        无参直跑必失败（R3 POST 评审实证）。占位符是唯一判据——需要实参的
        gate 行必须在 checklist 里自带占位符（如
        `make verify-data-release-consistency RELEASE_FILE=<release json 路径>`），
        不维护平行的「已知参数化目标」闭集。
        """
        gates, parameterized = _cli.collect_gates(
            [
                str(path.relative_to(_REPO_ROOT / ".agents/skills/review/references"))
                for path in (
                    _REPO_ROOT / ".agents/skills/review/references/roles"
                ).rglob("*.md")
                if "/checklists/" in path.as_posix()
            ]
        )
        for command in gates:
            self.assertIsNone(
                _cli._PLACEHOLDER_RE.search(command),
                f"可直跑 gates 混入占位符命令：{command}",
            )
            self.assertFalse(
                command.startswith("`") or command.endswith("`"),
                f"gate 命令未剥反引号：{command}",
            )
        # 需实参的 gate 必须不出现在可直跑侧（占位符判据生效的实例锁）。
        self.assertFalse(
            any(command.startswith("make verify-data-release-consistency") for command in gates),
            gates,
        )
        self.assertTrue(
            any(
                command.startswith("make verify-data-release-consistency")
                and "RELEASE_FILE=<" in command
                for command in parameterized
            ),
            parameterized,
        )
        self.assertTrue(
            any("feature-context TARGET=<" in command for command in parameterized)
        )
        self.assertTrue(
            any("--release <releaseId>" in command for command in parameterized)
        )

    def test_plan_json_has_parameterized_gates_field(self) -> None:
        plan = _cli.build_plan(
            _registry,
            "dev",
            "POST",
            None,
            ["quwoquan_ops/gate/verify_handoff_manifest.py"],
        )
        self.assertIn("parameterized_gates", plan)
        overlap = set(plan["gates"]) & set(plan["parameterized_gates"])
        self.assertEqual(overlap, set(), f"两字段不得重叠：{overlap}")

    def test_unknown_workflow_exits_2(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            _cli.build_plan(_registry, "commit", "POST", None, [])
        self.assertEqual(ctx.exception.code, 2)

    def test_undeclared_segment_exits_2(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            _cli.build_plan(_registry, "explore", "PRE", None, [])
        self.assertEqual(ctx.exception.code, 2)

    def test_registry_has_no_second_dispatch_track(self) -> None:
        """triggers 曾是有文无表的第二套派发机制；领域角色只走 profiles+when。"""
        self.assertNotIn("triggers", _registry)


if __name__ == "__main__":
    unittest.main()

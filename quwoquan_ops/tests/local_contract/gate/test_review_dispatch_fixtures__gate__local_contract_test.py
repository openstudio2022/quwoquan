"""review registry 的典型技术栈派发 fixture。

registry 只是数据；派发语义（profile 派生 → when 条件装配 → gate 去重）由
`.agents/skills/review/SKILL.md` 描述、由模型执行。本合约用一个按同一语义实现的
最小 resolver 跑真实 registry，锁定目标场景：**无关角色与无关 gate 零加载**。
registry 改动一旦让 Go 契约场景装配出 Flutter gate、或让 Dart 页面场景丢掉 ux 角色，
这里先于线上评审转红。
"""

from __future__ import annotations

import sys
import unittest
from fnmatch import fnmatch
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
_REFERENCES = _REPO_ROOT / ".agents/skills/review/references"
_REGISTRY = yaml.safe_load((_REFERENCES / "registry.yaml").read_text(encoding="utf-8"))


def derive_profiles(changed_paths: list[str], deliverable: str) -> set[str]:
    """registry 语义第 1 步：changed_paths 命中 paths 或 deliverable 命中即激活。"""
    active: set[str] = set()
    for name, config in (_REGISTRY.get("profiles") or {}).items():
        config = config or {}
        if deliverable in (config.get("deliverables") or []):
            active.add(name)
            continue
        for pattern in config.get("paths") or []:
            if any(fnmatch(path, pattern) for path in changed_paths):
                active.add(name)
                break
    return active


def assemble_bundle(workflow: str, profiles: set[str]) -> list[dict]:
    """registry 语义第 2 步：省略 when 恒装配；when 列表任一 profile 命中即装配。"""
    bindings = (_REGISTRY["workflows"][workflow] or {}).get("bindings") or []
    selected: list[dict] = []
    for binding in bindings:
        when = binding.get("when")
        if when is None or set(when) & profiles:
            selected.append(binding)
    return selected


def bundle_gates(bundle: list[dict]) -> list[str]:
    """registry 语义第 3 步的输入：选中 bundle 的全部 gate 命令（未去重）。"""
    gates: list[str] = []
    for binding in bundle:
        text = (_REFERENCES / binding["checklist"]).read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("gate:"):
                gates.append(stripped.removeprefix("gate:").strip())
    return gates


class ReviewDispatchFixtureTest(unittest.TestCase):
    def _roles(self, bundle: list[dict]) -> set[str]:
        return {binding["role"] for binding in bundle}

    def _checklists(self, bundle: list[dict]) -> set[str]:
        return {binding["checklist"] for binding in bundle}

    def test_go_contract_change_loads_no_flutter_or_ux_gate(self) -> None:
        profiles = derive_profiles(
            ["quwoquan_service/services/content-service/contracts/content/post/fields.yaml"],
            "contract",
        )
        self.assertIn("go-service", profiles)
        self.assertNotIn("dart-app", profiles)

        bundle = assemble_bundle("dev", profiles)
        roles = self._roles(bundle)
        self.assertLessEqual({"developer", "architect", "test"}, roles)
        for irrelevant in ("ux", "user", "pageflip", "recommendation", "growth", "observability"):
            self.assertNotIn(irrelevant, roles)
        for gate in bundle_gates(bundle):
            self.assertNotIn("verify-app-page", gate, f"Go 契约场景不得加载 Flutter 页面 gate: {gate}")
            self.assertNotIn("verify-app-theme", gate)

    def test_dart_page_change_loads_developer_architect_ux_test(self) -> None:
        profiles = derive_profiles(
            ["quwoquan_app/lib/service/content_service/content/post/presentation/content_detail_page.dart"],
            "implementation",
        )
        self.assertLessEqual({"dart-app", "flutter-page"}, profiles)

        bundle = assemble_bundle("dev", profiles)
        roles = self._roles(bundle)
        self.assertLessEqual({"developer", "architect", "ux", "test", "user"}, roles)
        for irrelevant in ("ops", "pageflip", "recommendation", "data-quality", "infra-capacity"):
            self.assertNotIn(irrelevant, roles)
        checklists = self._checklists(bundle)
        self.assertIn("roles/developer/checklists/dev/dart-app.md", checklists)
        self.assertNotIn("roles/developer/checklists/dev/go-service.md", checklists)

    def test_python_gate_change_loads_python_and_gate_profiles_only(self) -> None:
        profiles = derive_profiles(["quwoquan_ops/gate/verify_new_thing.py"], "gate")
        self.assertLessEqual({"python-script", "gate"}, profiles)
        self.assertNotIn("dart-app", profiles)

        bundle = assemble_bundle("dev", profiles)
        checklists = self._checklists(bundle)
        self.assertIn("roles/developer/checklists/dev/python-script.md", checklists)
        self.assertIn("roles/ops/checklists/dev/gate.md", checklists)
        self.assertNotIn("roles/developer/checklists/dev/dart-app.md", checklists)
        self.assertNotIn("roles/ux/checklists/dev/flutter-page.md", checklists)

    def test_environment_release_loads_only_release_and_capacity_roles(self) -> None:
        profiles = derive_profiles(
            ["quwoquan_ops/environments/prod/rollout/stages.yaml"], "release-evidence"
        )
        self.assertIn("environment-release", profiles)

        bundle = assemble_bundle("environment-ops", profiles)
        self.assertEqual({"ops", "infra-capacity"}, self._roles(bundle))
        self.assertIn(
            "roles/ops/checklists/environment-ops/environment-release.md",
            self._checklists(bundle),
        )

    def test_pageflip_path_appends_domain_role(self) -> None:
        profiles = derive_profiles(
            ["quwoquan_app/lib/design_system/pageflip/backward_render_frame_builder.dart"],
            "implementation",
        )
        self.assertIn("pageflip", profiles)
        roles = self._roles(assemble_bundle("dev", profiles))
        self.assertIn("pageflip", roles)

    def test_prd_without_page_skips_ux(self) -> None:
        profiles = derive_profiles(
            ["quwoquan_service/services/user-service/contracts/user/profile/fields.yaml"],
            "spec-node",
        )
        roles = self._roles(assemble_bundle("prd", profiles))
        self.assertEqual({"product", "user", "test"}, roles)

    def test_same_input_always_produces_same_bundle(self) -> None:
        """自然语言与显式命令共用同一 resolver 输入，装配必须确定。"""
        paths = ["quwoquan_app/lib/service/chat_service/chat/conversation/presentation/page.dart"]
        first = assemble_bundle("dev", derive_profiles(paths, "implementation"))
        second = assemble_bundle("dev", derive_profiles(paths, "implementation"))
        self.assertEqual(first, second)

    def test_selected_bundle_gates_deduplicate(self) -> None:
        """去重后每条 gate 只执行一次；重复次数是 evidence 共享的输入，不是重复执行的理由。"""
        profiles = derive_profiles(
            ["quwoquan_app/lib/service/content_service/content/post/presentation/content_detail_page.dart"],
            "implementation",
        )
        gates = bundle_gates(assemble_bundle("dev", profiles))
        deduplicated = set(gates)
        self.assertLess(len(deduplicated), len(gates) + 1)
        self.assertTrue(all(gates.count(gate) >= 1 for gate in deduplicated))


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)

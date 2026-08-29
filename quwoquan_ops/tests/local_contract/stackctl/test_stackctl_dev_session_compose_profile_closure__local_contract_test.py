"""test_live compose 闭包与激活 profile 必须同构。

profile 门控的服务只有在 profile 被激活时才会有容器。闭包选入了某个 compose
文件却不激活它声明的 profile，会让服务永远只存在于声明里：能力静默缺失，而
运行态 roster 校验把「按设计未启动」误判成漂移，绑定内容因此永久 GATE_BLOCK。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
"""
from __future__ import annotations

import inspect
import unittest
from unittest import mock

import yaml

import quwoquan_ops.cli.stackctl as stackctl
from quwoquan_ops.cli.commands import down_domain
from quwoquan_ops.cli.commands.dev_session_compose import (
    _dev_session_source_compose_files,
)
from quwoquan_ops.cli.lib import runtime_topology_package


class StackctlDevSessionComposeProfileClosureTest(unittest.TestCase):
    def _closure(self) -> tuple[list, list[str]]:
        """Resolve the real worktree closure with no Provider workload."""
        with mock.patch(
            "quwoquan_ops.cli.stackctl.validate_provider_runtime_composition",
            return_value={"workloads": []},
        ):
            return _dev_session_source_compose_files(
                environment="beta",
                target="beta-local",
                provider_composition={},
            )

    def test_every_profile_gated_service_in_closure_is_activated(self) -> None:
        files, profiles = self._closure()
        activated = set(profiles)
        gated: dict[str, set[str]] = {}
        for path in files:
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            services = document.get("services") or {}
            for name, definition in services.items():
                declared = (definition or {}).get("profiles") or []
                if declared:
                    gated.setdefault(str(name), set()).update(
                        str(item) for item in declared
                    )
        self.assertTrue(gated, "closure must contain profile-gated services")
        unreachable = {
            name: sorted(required)
            for name, required in gated.items()
            if not (required & activated)
        }
        self.assertEqual(
            unreachable,
            {},
            "profile-gated services in the closure are never startable",
        )

    def test_control_plane_layer_is_part_of_the_full_workload(self) -> None:
        files, profiles = self._closure()
        control_plane_files = [
            path for path in files if "control-plane" in path.parts
        ]
        self.assertTrue(
            control_plane_files,
            "test_live closure must select the control-plane layer",
        )
        self.assertIn("control-plane", profiles)

    def test_full_workload_profiles_come_from_one_declaration(self) -> None:
        """mutable test_live 与 immutable down 投影必须读同一处 profile 声明。

        两侧各抄一份闭集时，任一侧漏掉 profile 都不会被任何断言发现：被门控的
        服务只存在于声明里而永不启动，运行态 roster 随之判定漂移。
        """
        _files, profiles = self._closure()
        self.assertEqual(
            set(profiles),
            set(runtime_topology_package.FULL_WORKLOAD_COMPOSE_PROFILES),
            "test_live profiles must be the declared full-workload closed set",
        )
        self.assertIs(
            stackctl.FULL_WORKLOAD_COMPOSE_PROFILES,
            runtime_topology_package.FULL_WORKLOAD_COMPOSE_PROFILES,
            "stackctl must re-export the declaration, not copy it",
        )

    def test_down_projection_activates_the_declared_full_workload_profiles(
        self,
    ) -> None:
        """immutable down 的 profile 必须来自声明位，且覆盖 test_live 的全集。"""
        source = inspect.getsource(down_domain)
        for profile in runtime_topology_package.FULL_WORKLOAD_COMPOSE_PROFILES:
            self.assertNotIn(
                f'"{profile}"',
                source,
                f"down projection must not inline the {profile} profile literal",
            )
        self.assertIn("FULL_WORKLOAD_COMPOSE_PROFILES", source)


if __name__ == "__main__":
    unittest.main()

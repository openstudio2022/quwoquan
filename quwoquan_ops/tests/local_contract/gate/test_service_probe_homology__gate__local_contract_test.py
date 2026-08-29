"""服务端就绪路由 ↔ deploy 探针声明同源门禁的 companion 测试。

门禁的判据:注册了 `/readyz` 的服务其 readinessProbe 必须指向 `/readyz`,
未注册的服务不得声明 `/readyz`。这里同时锁住路由识别正则的语义与
真实仓库上双向校验的最终结论。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.gate import verify_service_probe_homology as gate


class ReadinessRouteRegexContractTest(unittest.TestCase):
    def test_regex_matches_plain_and_method_prefixed_registrations(self) -> None:
        for source in (
            'mux.HandleFunc("/readyz", handler)',
            'mux.Handle("/readyz", handler)',
            'mux.HandleFunc("GET /readyz", handler)',
        ):
            with self.subTest(source=source):
                self.assertIsNotNone(gate._READYZ_ROUTE.search(source))

    def test_regex_rejects_lookalike_routes_and_literals(self) -> None:
        for source in (
            'mux.HandleFunc("/readyz/deep", handler)',
            'mux.HandleFunc("/healthz", handler)',
            'path := "/readyz"',
        ):
            with self.subTest(source=source):
                self.assertIsNone(gate._READYZ_ROUTE.search(source))

    def test_regex_scopes_to_route_registration_only(self) -> None:
        # 注释或字符串拼接里出现 readyz 不构成路由注册。
        self.assertIsNone(
            gate._READYZ_ROUTE.search('// serve "/readyz" some day')
        )


class ServiceProbeHomologyRepoTest(unittest.TestCase):
    def test_repo_probe_matrix_is_bidirectionally_homologous(self) -> None:
        """真实仓库上两侧真相源必须闭合;任何一侧漂移都让门禁退出非零。"""
        self.assertEqual(gate.main(), 0)

    def test_route_scan_excludes_test_tree_sources(self) -> None:
        registered = gate.services_registering_readiness_route()
        self.assertIsInstance(registered, set)
        # 双向规则成立时,注册集必是探针矩阵声明 /readyz 服务集的同集。
        matrix = gate.service_probe_matrix()
        declared = {
            service
            for service, probes in matrix.items()
            if probes.readiness == gate.READINESS_PATH
        }
        self.assertEqual(registered, declared)


if __name__ == "__main__":
    unittest.main()

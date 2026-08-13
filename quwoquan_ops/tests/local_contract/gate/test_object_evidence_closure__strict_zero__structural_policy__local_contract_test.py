"""verify_object_evidence_closure 的 STRUCTURAL 严格零值政策合约。

由 test_object_evidence_closure__strict_zero__contract_graph__local_contract_test.py
（Python 1000 行硬顶治理）按场景拆出：历史 baseline 必须缺席、任一结构缺口
阻断并指向 objectId、canonical 证据键映射完备、未分层维度先于静态放行阻断。
测试逐字搬移；共享 harness 见 tests/support。
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.tests.support.object_evidence_closure_test_support import (
    BASELINE,
    ObjectEvidenceClosureStrictZeroSupport,
    PACKAGE_DIR,
    SCRIPT,
    closure,
    synthetic_graph,
)


class ObjectEvidenceClosureStrictZeroTest(ObjectEvidenceClosureStrictZeroSupport):
    # --- strict-zero policy -----------------------------------------------

    def test_committed_baseline_is_retired(self) -> None:
        self.assertFalse(BASELINE.exists())

    def test_gate_has_no_baseline_policy_surface(self) -> None:
        # 入口 + 实现包全部模块都不得再出现 baseline 政策面。
        source = "\n".join(
            [SCRIPT.read_text(encoding="utf-8")]
            + [
                module_path.read_text(encoding="utf-8")
                for module_path in sorted(PACKAGE_DIR.rglob("*.py"))
            ]
        )
        self.assertNotIn("object_evidence_closure_baseline.json", source)
        self.assertNotIn('add_argument("--baseline"', source)
        self.assertNotIn('add_argument("--update-baseline"', source)

    def test_baseline_cli_surfaces_are_retired(self) -> None:
        graph = self.write_graph(
            {"objects": [], "objectReadiness": [], "readinessEvidence": [], "operations": []}
        )
        for arguments in (
            ("--baseline", str(self.workspace / "baseline.json")),
            ("--update-baseline",),
        ):
            with self.subTest(arguments=arguments):
                result = self.run_gate("--graph", str(graph), *arguments)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("unrecognized arguments", result.stderr)

    def test_structural_gap_blocks_and_names_the_object(self) -> None:
        graph = self.write_graph(synthetic_graph())

        result = self.run_gate("--graph", str(graph))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("GATE_BLOCK STRUCTURAL 严格零值要求未满足", result.stdout)
        self.assertIn("app.client / content.demo", result.stdout)
        self.assertIn("修复路径", result.stdout)

    def test_canonical_app_runner_missing_keys_are_structural(self) -> None:
        cases = (
            ("implementation.app.api_integration", "test.api_integration"),
            ("implementation.app.user_acceptance", "test.user_acceptance_entry"),
        )
        for missing, dimension in cases:
            with self.subTest(missing=missing):
                graph = self.write_graph(synthetic_graph(missing=missing))
                result = self.run_gate("--graph", str(graph))

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(f"{dimension} / content.demo", result.stdout)
                self.assertEqual(
                    closure.EVIDENCE_CLASS_BY_DIMENSION[dimension],
                    closure.STRUCTURAL,
                )

    def test_all_canonical_app_evidence_keys_are_mapped(self) -> None:
        expected = {
            "implementation.app.application": "app.client",
            "implementation.app.adapters": "app.client",
            "implementation.app.local_contract": "test.local_contract",
            "implementation.app.api_integration": "test.api_integration",
            "implementation.app.presentation": "app.page",
            "implementation.app.user_acceptance": "test.user_acceptance_entry",
        }
        for missing_key, dimension in expected.items():
            with self.subTest(missing_key=missing_key):
                self.assertEqual(
                    closure.LAYER_BY_MISSING_KEY[missing_key],
                    dimension,
                )
                self.assertEqual(
                    closure.EVIDENCE_CLASS_BY_DIMENSION[dimension],
                    closure.STRUCTURAL,
                )

    def test_all_canonical_service_and_ops_evidence_keys_are_mapped(self) -> None:
        expected = {
            "implementation.service.domain": "cloud.domain_behavior",
            "implementation.service.store": "cloud.store",
            "implementation.service.reader": "cloud.reader",
            "implementation.service.transport": "cloud.transport",
            "implementation.service.local_contract": "test.local_contract",
            "implementation.service.api_integration": "test.api_integration",
            "implementation.ops.environment_acceptance": (
                "ops.environment_acceptance_entry"
            ),
            "implementation.ops.rollback_runner": "ops.rollback_runner_entry",
            "implementation.ops.replay_runner": "ops.replay_runner_entry",
        }
        for missing_key, dimension in expected.items():
            with self.subTest(missing_key=missing_key):
                self.assertEqual(
                    closure.LAYER_BY_MISSING_KEY[missing_key],
                    dimension,
                )
                self.assertEqual(
                    closure.EVIDENCE_CLASS_BY_DIMENSION[dimension],
                    closure.STRUCTURAL,
                )

    def test_canonical_service_and_ops_missing_keys_block_the_gate(self) -> None:
        cases = (
            ("implementation.service.domain", "cloud.domain_behavior"),
            ("implementation.service.store", "cloud.store"),
            ("implementation.service.reader", "cloud.reader"),
            ("implementation.service.transport", "cloud.transport"),
            ("implementation.service.local_contract", "test.local_contract"),
            ("implementation.service.api_integration", "test.api_integration"),
            (
                "implementation.ops.environment_acceptance",
                "ops.environment_acceptance_entry",
            ),
            ("implementation.ops.rollback_runner", "ops.rollback_runner_entry"),
            ("implementation.ops.replay_runner", "ops.replay_runner_entry"),
        )
        for missing_key, dimension in cases:
            with self.subTest(missing_key=missing_key):
                graph = self.write_graph(synthetic_graph(missing=missing_key))
                result = self.run_gate("--graph", str(graph))

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(f"{dimension} / content.demo", result.stdout)

    def test_flat_evidence_keys_are_rejected_not_dual_read(self) -> None:
        legacy = {
            "implementation.domain_behavior",
            "implementation.store",
            "implementation.reader",
            "implementation.transport",
            "implementation.local_contract",
            "implementation.api_integration",
            "implementation.app_client",
            "implementation.page",
            "commercial.user_acceptance",
            "commercial.environment.alpha",
            "commercial.environment.beta",
            "commercial.environment.gamma",
            "commercial.environment.prod",
        }
        self.assertTrue(legacy.isdisjoint(closure.LAYER_BY_MISSING_KEY))

    def test_external_reference_store_or_transport_gap_is_structural(self) -> None:
        graph = self.write_graph(
            synthetic_graph(
                kind="external_reference",
                missing="implementation.service.store_or_transport",
            )
        )

        result = self.run_gate("--graph", str(graph))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "cloud.external_implementation / content.demo",
            result.stdout,
        )
        self.assertEqual(
            closure.EVIDENCE_CLASS_BY_DIMENSION["cloud.external_implementation"],
            closure.STRUCTURAL,
        )

    def test_external_reference_with_store_or_transport_has_no_gap(self) -> None:
        document = synthetic_graph(kind="external_reference", missing="")
        document["objectReadiness"][0]["missing"] = []
        graph = self.write_graph(document)

        result = self.run_gate("--graph", str(graph))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("cloud.external_implementation", result.stdout)

    def test_zero_structural_gaps_pass(self) -> None:
        graph = self.write_graph(
            {"objects": [], "objectReadiness": [], "readinessEvidence": [], "operations": []}
        )

        result = self.run_gate("--graph", str(graph))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("structural_policy=strict_zero", result.stdout)
        self.assertIn("无缺口", result.stdout)

    def test_unclassified_dimension_blocks_before_static_pass(self) -> None:
        graph = self.write_graph(synthetic_graph())
        report = self.workspace / "report" / "object_evidence_closure.json"
        unknown = closure.Gap(
            "content.demo",
            "projection",
            "implemented",
            "future.unclassified_evidence",
            "synthetic future dimension",
        )
        arguments = SimpleNamespace(
            report_dir=report.parent,
            require_commercial_readiness=False,
        )

        with (
            mock.patch.object(closure, "parse_args", return_value=arguments),
            mock.patch.object(closure, "select_graph_path", return_value=graph),
            mock.patch.object(
                closure,
                "load_graph_with_digest",
                return_value=(synthetic_graph(), hashlib.sha256(graph.read_bytes()).hexdigest()),
            ),
            mock.patch.object(closure, "collect_gaps", return_value=[unknown]),
            mock.patch.object(
                closure,
                "load_blind_spot_registry_with_digest",
                return_value=({}, None),
            ),
            mock.patch.object(closure, "write_reports", return_value=report),
            mock.patch("builtins.print") as print_line,
        ):
            return_code = closure.main()

        self.assertEqual(return_code, 1)
        output = "\n".join(" ".join(map(str, call.args)) for call in print_line.call_args_list)
        self.assertIn("GATE_BLOCK 出现未分层的缺口维度", output)
        self.assertIn("future.unclassified_evidence", output)


if __name__ == "__main__":
    unittest.main()

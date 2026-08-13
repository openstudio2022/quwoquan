"""verify_object_evidence_closure 的动态商业 readiness 合约。

由 test_object_evidence_closure__strict_zero__contract_graph__local_contract_test.py
（Python 1000 行硬顶治理）按场景拆出：RESULT 只可见不伪造静态 PASS、
--require-commercial-readiness 缺可信动态回执时 fail-closed、evaluator 退出码/
协议/超时/输入漂移语义。测试逐字搬移；共享 harness 见 tests/support。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.tests.support.object_evidence_closure_test_support import (
    ObjectEvidenceClosureStrictZeroSupport,
    PACKAGE_DIR,
    closure,
    synthetic_graph,
)


class ObjectEvidenceClosureStrictZeroTest(ObjectEvidenceClosureStrictZeroSupport):
    def test_commercial_result_bundle_gap_is_visible_as_result_evidence(self) -> None:
        graph = synthetic_graph(missing="commercial.result_bundle")

        gaps = closure.collect_gaps(graph)
        partitions = closure.partition_by_evidence_class(gaps)

        self.assertEqual([gap.dimension for gap in gaps], ["commercial.result_bundle"])
        self.assertEqual(partitions[closure.STRUCTURAL], [])
        self.assertEqual(
            [gap.dimension for gap in partitions[closure.RESULT]],
            ["commercial.result_bundle"],
        )
        self.assertEqual(closure.unclassified_dimensions(gaps), [])

    def test_result_only_graph_passes_static_gate_but_remains_visible(self) -> None:
        graph = self.write_graph(synthetic_graph(missing="commercial.result_bundle"))

        result = self.run_gate("--graph", str(graph))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("commercial.result_bundle: 1 条", result.stdout)
        self.assertIn("无缺口", result.stdout)
        report = json.loads(
            (self.workspace / "report" / "object_evidence_closure.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["gapsByDimension"], {"commercial.result_bundle": 1})
        self.assertEqual(report["structuralPolicy"], {
            "mode": "strict_zero",
            "allowedGapCount": 0,
        })

    def test_environment_dimensions_are_not_a_static_graph_dual_track(self) -> None:
        for environment in ("alpha", "beta", "gamma", "prod"):
            with self.subTest(environment=environment):
                dimension = f"environment.{environment}"
                self.assertNotIn(dimension, closure.EVIDENCE_CLASS_BY_DIMENSION)
                self.assertNotIn(
                    f"commercial.environment.{environment}",
                    closure.LAYER_BY_MISSING_KEY,
                )

    def test_static_report_marks_dynamic_readiness_not_evaluated(self) -> None:
        graph = self.write_graph(synthetic_graph(missing="commercial.result_bundle"))

        result = self.run_gate("--graph", str(graph))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(
            (self.workspace / "report" / "object_evidence_closure.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["dynamicReadiness"]["status"], "not_evaluated")
        self.assertFalse(report["dynamicReadiness"]["commercialReady"])
        self.assertIsNone(report["dynamicReadiness"]["resultBundle"])
        self.assertNotIn("ratchetBaseline", report)
        self.assertEqual(
            report[closure.REPORT_BLIND_SPOT_REGISTRY_FIELD],
            {
                "path": closure.display_path(closure.BLIND_SPOT_REGISTRY.resolve()),
                "status": "absent",
            },
        )

    def test_required_commercial_mode_blocks_without_trusted_dynamic_evidence(self) -> None:
        graph = self.write_graph(
            {
                "objects": [],
                "objectReadiness": [],
                "readinessEvidence": [],
                "operations": [],
            }
        )

        result = self.run_gate(
            "--graph",
            str(graph),
            "--require-commercial-readiness",
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("GATE_BLOCK 动态商业 readiness 输入不完整", result.stdout)
        self.assertIn("resultBundle", result.stdout)
        report = json.loads(
            (self.workspace / "report" / "object_evidence_closure.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["dynamicReadiness"]["status"], "invalid_input")
        self.assertEqual(report["dynamicReadiness"]["evaluatorExitCode"], 2)

    def test_required_commercial_mode_rejects_structural_debt_first(self) -> None:
        graph = self.write_graph(synthetic_graph())

        result = self.run_gate(
            "--graph",
            str(graph),
            "--require-commercial-readiness",
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("GATE_BLOCK STRUCTURAL 严格零值要求未满足", result.stdout)
        self.assertIn("app.client", result.stdout)
        self.assertNotIn("动态商业 readiness 未执行", result.stdout)

    def test_dynamic_inputs_without_commercial_mode_are_usage_error(self) -> None:
        graph = self.write_graph(
            {"objects": [], "objectReadiness": [], "readinessEvidence": [], "operations": []}
        )
        _, cli = self.commercial_inputs()

        result = self.run_gate("--graph", str(graph), *cli)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(
            "dynamic readiness inputs require --require-commercial-readiness",
            result.stderr,
        )

    def test_partial_commercial_inputs_are_usage_error_after_structural_pass(self) -> None:
        graph = self.write_graph(
            {"objects": [], "objectReadiness": [], "readinessEvidence": [], "operations": []}
        )
        arguments, _ = self.commercial_inputs()

        result = self.run_gate(
            "--graph",
            str(graph),
            "--require-commercial-readiness",
            "--readiness-bundle",
            str(arguments.readiness_bundle),
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("signedCurrentSnapshot", result.stdout)

    def test_dynamic_evaluator_preserves_canonical_exit_codes_and_binds_inputs(self) -> None:
        graph = self.write_graph(
            {"objects": [], "objectReadiness": [], "readinessEvidence": [], "operations": []}
        )
        graph_digest = hashlib.sha256(graph.read_bytes()).hexdigest()
        arguments, _ = self.commercial_inputs()
        expected = {
            0: {"commercialReady": True, "objects": []},
            1: {"commercialReady": False, "objects": [{"objectId": "demo"}]},
            2: {"commercialReady": False, "error": "signed receipt missing"},
        }
        for exit_code, payload in expected.items():
            with self.subTest(exit_code=exit_code):
                completed = subprocess.CompletedProcess(
                    args=["evaluate_readiness"],
                    returncode=exit_code,
                    stdout=json.dumps(payload) + "\n",
                    stderr="",
                )
                with (
                    mock.patch.object(
                        closure,
                        "build_readiness_evaluator",
                        return_value=(self.workspace / "evaluate_readiness", "a" * 64),
                    ),
                    mock.patch.object(closure.subprocess, "run", return_value=completed),
                ):
                    outcome = closure.evaluate_dynamic_readiness(
                        arguments, graph, graph_digest
                    )

                self.assertEqual(outcome.exit_code, exit_code)
                self.assertEqual(outcome.report["evaluatorExitCode"], exit_code)
                self.assertEqual(outcome.report["closure"], payload)
                self.assertEqual(
                    outcome.report["inputs"]["resultBundle"]["sha256"],
                    hashlib.sha256(arguments.readiness_bundle.read_bytes()).hexdigest(),
                )
                self.assertEqual(
                    outcome.report["inputs"]["receiptRoot"]["kind"], "directory"
                )

    def test_dynamic_evaluator_is_a_bounded_direct_go_binary_call(self) -> None:
        # evaluator 构建在 readiness_inputs.py，运行超时约束在 gate.py。
        source = "\n".join(
            (PACKAGE_DIR / module_name).read_text(encoding="utf-8")
            for module_name in ("readiness_inputs.py", "gate.py")
        )
        self.assertIn('"go",\n                "build",', source)
        self.assertNotIn('"go", "run", "./tools/evaluate_readiness"', source)
        self.assertIn("READINESS_EVALUATOR_BUILD_TIMEOUT_SECONDS", source)
        self.assertIn("READINESS_EVALUATOR_RUN_TIMEOUT_SECONDS", source)
        self.assertEqual(closure.READINESS_EVALUATOR_PACKAGE, "./tools/evaluate_readiness")

    def test_dynamic_evaluator_protocol_failures_are_exit_two(self) -> None:
        graph = self.write_graph(
            {"objects": [], "objectReadiness": [], "readinessEvidence": [], "operations": []}
        )
        graph_digest = hashlib.sha256(graph.read_bytes()).hexdigest()
        arguments, _ = self.commercial_inputs()
        cases = (
            (0, "not-json"),
            (0, '{"commercialReady":true}\n{"commercialReady":true}\n'),
            (7, '{"commercialReady":false}\n'),
            (0, '{"commercialReady":false}\n'),
            (2, '{"commercialReady":false}\n'),
        )
        for return_code, stdout in cases:
            with self.subTest(return_code=return_code, stdout=stdout):
                completed = subprocess.CompletedProcess(
                    args=["evaluate_readiness"],
                    returncode=return_code,
                    stdout=stdout,
                    stderr="",
                )
                with (
                    mock.patch.object(
                        closure,
                        "build_readiness_evaluator",
                        return_value=(self.workspace / "evaluate_readiness", "a" * 64),
                    ),
                    mock.patch.object(closure.subprocess, "run", return_value=completed),
                ):
                    outcome = closure.evaluate_dynamic_readiness(
                        arguments, graph, graph_digest
                    )
                self.assertEqual(outcome.exit_code, 2)
                self.assertEqual(outcome.report["status"], "invalid_input")

    def test_dynamic_evaluator_timeout_and_input_drift_are_exit_two(self) -> None:
        graph = self.write_graph(
            {"objects": [], "objectReadiness": [], "readinessEvidence": [], "operations": []}
        )
        graph_digest = hashlib.sha256(graph.read_bytes()).hexdigest()
        arguments, _ = self.commercial_inputs()
        with (
            mock.patch.object(
                closure,
                "build_readiness_evaluator",
                return_value=(self.workspace / "evaluate_readiness", "a" * 64),
            ),
            mock.patch.object(
                closure.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("evaluate_readiness", 120),
            ),
        ):
            timed_out = closure.evaluate_dynamic_readiness(arguments, graph, graph_digest)
        self.assertEqual(timed_out.exit_code, 2)

        completed = subprocess.CompletedProcess(
            args=["evaluate_readiness"],
            returncode=0,
            stdout='{"commercialReady":true}\n',
            stderr="",
        )
        with (
            mock.patch.object(
                closure,
                "build_readiness_evaluator",
                return_value=(self.workspace / "evaluate_readiness", "a" * 64),
            ),
            mock.patch.object(closure.subprocess, "run", return_value=completed),
            mock.patch.object(
                closure,
                "verify_readiness_input_bindings",
                side_effect=ValueError("input drift"),
            ),
        ):
            drifted = closure.evaluate_dynamic_readiness(arguments, graph, graph_digest)
        self.assertEqual(drifted.exit_code, 2)
        self.assertIn("input drift", drifted.report["reason"])

    def test_required_commercial_mode_rejects_registered_blindspot(self) -> None:
        graph = self.write_graph(
            synthetic_graph(missing="blindspot.python_store_invisible")
        )
        report = self.workspace / "report" / "object_evidence_closure.json"
        key = ("content.demo", "blindspot.python_store_invisible")
        arguments = SimpleNamespace(
            report_dir=report.parent,
            require_commercial_readiness=True,
        )

        with (
            mock.patch.object(closure, "parse_args", return_value=arguments),
            mock.patch.object(closure, "select_graph_path", return_value=graph),
            mock.patch.object(
                closure,
                "load_blind_spot_registry_with_digest",
                return_value=(
                    {
                        key: {
                            "classification": closure.BLIND_SPOT_IMPLEMENTED,
                            "attested_scope": "synthetic",
                        }
                    },
                    "1" * 64,
                ),
            ),
            mock.patch.object(closure, "write_reports", return_value=report),
            mock.patch("builtins.print") as print_line,
        ):
            return_code = closure.main()

        self.assertEqual(return_code, 1)
        output = "\n".join(
            " ".join(map(str, call.args)) for call in print_line.call_args_list
        )
        self.assertIn("scanner blindspot 零缺口", output)
        self.assertNotIn("动态商业 readiness 未执行", output)


if __name__ == "__main__":
    unittest.main()

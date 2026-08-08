"""verify_object_evidence_closure 的 STRUCTURAL 严格零值合约。

覆盖：历史 baseline 必须缺席；任一结构缺口都阻断并指向 objectId；
RESULT 只可见而不伪造静态 PASS；商业模式没有可信动态回执时继续 fail-closed；
门禁与本测试都必须留在 `gate_repo.sh` 里。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "quwoquan_ops/gate/verify_object_evidence_closure.py"
BASELINE = ROOT / "quwoquan_ops/policies/gates/object_evidence_closure_baseline.json"
GATE_REPO = ROOT / "quwoquan_ops/gate/gate_repo.sh"
MAKEFILE = ROOT / "Makefile"
COMMITTED_GRAPH = ROOT / "quwoquan_service/generated/contract_graph.json"

SPEC = importlib.util.spec_from_file_location("verify_object_evidence_closure", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
closure = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = closure
SPEC.loader.exec_module(closure)


def canonical_evidence_packet(object_id: str = "content.demo") -> dict:
    return {
        "objectId": object_id,
        "operationIds": [],
        "service": {
            "domain": [],
            "store": [],
            "outbox": [],
            "reader": [],
            "transport": [],
            "localContract": [],
            "apiIntegration": [],
        },
        "app": {
            "domain": [],
            "application": [],
            "adapters": [],
            "presentation": [],
            "localContract": [],
            "apiIntegration": [],
            "userAcceptance": [],
            "pageParticipant": False,
            "pageOwned": False,
        },
        "ops": {
            "environmentAcceptance": [],
            "rollbackRunner": [],
            "replayRunner": [],
        },
        "sourcePath": "content/demo/object.yaml",
    }


def synthetic_graph(
    kind: str = "projection",
    missing: str = "implementation.app.application",
) -> dict:
    """最小合成图：只保留 readiness 展开所需的三段，避免把真实契约拖进判定。"""
    return {
        "objects": [
            {"id": "content.demo", "kind": kind, "sourcePath": "content/demo/object.yaml"}
        ],
        "objectReadiness": [
            {
                "objectId": "content.demo",
                "stage": "implemented",
                "contractReady": True,
                "missing": [missing],
            }
        ],
        "readinessEvidence": [canonical_evidence_packet()],
        "operations": [],
    }


class ObjectEvidenceClosureStrictZeroTest(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self._directory.name)
        self.addCleanup(self._directory.cleanup)

    def write_graph(self, document: dict) -> Path:
        path = self.workspace / "graph.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def write_artifact(self, name: str, payload: bytes) -> tuple[Path, str]:
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path, hashlib.sha256(payload).hexdigest()

    def write_blind_spot_registry(self, entries: list[dict]) -> Path:
        path = self.workspace / "blind_spots.yaml"
        path.write_text(
            json.dumps({"unresolved_sites": entries}, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def write_page_contract(self, document: dict) -> Path:
        path = self.workspace / "page_object_contract.yaml"
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        return path

    def commercial_inputs(self) -> tuple[SimpleNamespace, list[str]]:
        files = {}
        for name in (
            "readiness_bundle",
            "signed_current_snapshot",
            "snapshot_keyring",
            "runner_keyring",
        ):
            path = self.workspace / f"{name}.json"
            path.write_text(json.dumps({"input": name}), encoding="utf-8")
            files[name] = path
        receipt_root = self.workspace / "receipts"
        evidence_root = self.workspace / "evidence"
        receipt_root.mkdir()
        evidence_root.mkdir()
        (receipt_root / "receipt.json").write_text("{}", encoding="utf-8")
        (evidence_root / "artifact.json").write_text("{}", encoding="utf-8")
        arguments = SimpleNamespace(
            **files,
            receipt_root=receipt_root,
            evidence_root=evidence_root,
        )
        cli = [
            "--readiness-bundle",
            str(files["readiness_bundle"]),
            "--signed-current-snapshot",
            str(files["signed_current_snapshot"]),
            "--snapshot-keyring",
            str(files["snapshot_keyring"]),
            "--runner-keyring",
            str(files["runner_keyring"]),
            "--receipt-root",
            str(receipt_root),
            "--evidence-root",
            str(evidence_root),
        ]
        return arguments, cli

    def run_gate(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "QWQ_OUTPUT_ROOT": str(ROOT / ".qwq_output"),
        }
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--report-dir",
                str(self.workspace / "report"),
                *arguments,
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    # --- strict-zero policy -----------------------------------------------

    def test_committed_baseline_is_retired(self) -> None:
        self.assertFalse(BASELINE.exists())

    def test_gate_has_no_baseline_policy_surface(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
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

    def test_legacy_flat_evidence_keys_are_not_dual_read(self) -> None:
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
        source = SCRIPT.read_text(encoding="utf-8")
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

    def test_unregistered_blind_spot_is_blocked(self) -> None:
        graph = self.write_graph(
            synthetic_graph(missing="blindspot.python_store_invisible")
        )

        result = self.run_gate("--graph", str(graph))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("GATE_BLOCK 维度盲点集合与登记册不一致", result.stdout)
        self.assertIn("content.demo", result.stdout)

    def test_derive_and_graph_are_mutually_exclusive(self) -> None:
        result = self.run_gate("--derive", "--graph", str(COMMITTED_GRAPH))

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("互斥", result.stderr)

    def test_default_graph_selection_derives_the_current_workspace(self) -> None:
        derived = self.workspace / "fresh-contract-graph.json"
        arguments = SimpleNamespace(graph=None, report_dir=self.workspace / "report")

        with mock.patch.object(
            closure,
            "derive_contract_graph",
            return_value=derived,
        ) as derive:
            selected = closure.select_graph_path(arguments)

        self.assertEqual(selected, derived)
        derive.assert_called_once_with(arguments.report_dir)

    def test_explicit_graph_selection_does_not_rederive(self) -> None:
        selected_graph = self.workspace / "bound-contract-graph.json"
        arguments = SimpleNamespace(graph=selected_graph, report_dir=self.workspace / "report")

        with mock.patch.object(closure, "derive_contract_graph") as derive:
            selected = closure.select_graph_path(arguments)

        self.assertEqual(selected, selected_graph)
        derive.assert_not_called()

    def test_canonical_producer_separated_packet_shape_is_accepted(self) -> None:
        graph = self.write_graph(synthetic_graph())

        loaded, digest = closure.load_graph_with_digest(graph)

        self.assertEqual(loaded["readinessEvidence"], [canonical_evidence_packet()])
        self.assertEqual(digest, hashlib.sha256(graph.read_bytes()).hexdigest())

    def test_legacy_flattened_evidence_packet_is_blocked(self) -> None:
        document = synthetic_graph()
        packet = document["readinessEvidence"][0]
        packet["outbox"] = [
            {"storage": "legacy", "path": "legacy.go", "sha256": "0" * 64}
        ]
        graph = self.write_graph(document)

        result = self.run_gate("--graph", str(graph))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("producer-separated", result.stderr)
        self.assertIn("旧扁平证据字段 ['outbox']", result.stderr)

    def test_producer_maps_are_required_and_exact(self) -> None:
        for producer in ("service", "app", "ops"):
            with self.subTest(producer=producer):
                document = synthetic_graph()
                document["readinessEvidence"][0][producer] = []
                with self.assertRaises(SystemExit) as failure:
                    closure.validate_contract_graph_shape(document)
                self.assertIn(f".{producer} 必须是 map", str(failure.exception))

        document = synthetic_graph()
        del document["readinessEvidence"][0]["service"]["outbox"]
        with self.assertRaises(SystemExit) as failure:
            closure.validate_contract_graph_shape(document)
        self.assertIn("missing=['outbox']", str(failure.exception))

    def test_artifact_and_storage_evidence_shapes_are_exact(self) -> None:
        artifact_document = synthetic_graph()
        artifact_document["readinessEvidence"][0]["service"]["store"] = [
            {"path": "store.go", "sha256": "0" * 64, "storage": "legacy"}
        ]
        with self.assertRaises(SystemExit) as artifact_failure:
            closure.validate_contract_graph_shape(artifact_document)
        self.assertIn("必须且只能包含 path/sha256", str(artifact_failure.exception))

        storage_document = synthetic_graph()
        storage_document["readinessEvidence"][0]["service"]["outbox"] = [
            {"storage": "legacy", "path": "outbox.go", "sha256": "0" * 64}
        ]
        with self.assertRaises(SystemExit) as storage_failure:
            closure.validate_contract_graph_shape(storage_document)
        self.assertIn(
            "旧扁平 storage/path/sha256 不可复用", str(storage_failure.exception)
        )

    def test_concurrent_derivations_use_distinct_view_and_graph_work_roots(self) -> None:
        commands: list[list[str]] = []

        def record_command(arguments: list[str], **_: object) -> SimpleNamespace:
            commands.append([str(value) for value in arguments])
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(closure.subprocess, "run", side_effect=record_command):
            with ThreadPoolExecutor(max_workers=2) as executor:
                graphs = list(
                    executor.map(
                        closure.derive_contract_graph,
                        (self.workspace / "report", self.workspace / "report"),
                    )
                )

        build_commands = [
            command for command in commands if "build_service_contract_view.py" in " ".join(command)
        ]
        generate_commands = [
            command for command in commands if "./tools/qwq_contract" in command
        ]
        views = {command[command.index("--output") + 1] for command in build_commands}
        generated_outputs = {
            command[command.index("--output") + 1] for command in generate_commands
        }
        self.assertEqual(len(build_commands), 2)
        self.assertEqual(len(generate_commands), 2)
        self.assertEqual(len(views), 2)
        self.assertEqual(len(generated_outputs), 2)
        self.assertEqual({str(path) for path in graphs}, generated_outputs)
        metadata_dirs = {
            command[command.index("--metadata-dir") + 1]
            for command in generate_commands
        }
        self.assertEqual(metadata_dirs, views)
        for command in generate_commands:
            metadata_dir = Path(command[command.index("--metadata-dir") + 1])
            graph_output = Path(command[command.index("--output") + 1])
            self.assertEqual(metadata_dir.parent, graph_output.parent)
        for graph in graphs:
            self.assertIn(".qwq_output/env/repo/local/object-evidence-closure/cache/derive-", str(graph))
            self.assertEqual(graph.name, "contract_graph.json")

    # --- artifact 与 report identity ------------------------------------

    def test_artifact_sha_mutation_is_a_structural_gap(self) -> None:
        artifact, original_digest = self.write_artifact("store.go", b"before")
        artifact.write_bytes(b"after")

        with mock.patch.object(closure, "ROOT", self.workspace):
            gaps = closure.artifact_gaps(
                "content.demo",
                "aggregate_root",
                "implemented",
                {
                    "service": {
                        "store": [
                            {
                                "path": artifact.relative_to(self.workspace).as_posix(),
                                "sha256": original_digest,
                            }
                        ]
                    }
                },
            )

        self.assertEqual([gap.dimension for gap in gaps], ["derivation.artifact_digest"])
        self.assertIn("expected=", gaps[0].detail)
        self.assertIn("actual=", gaps[0].detail)

    def test_publication_delivery_artifact_is_in_digest_closure(self) -> None:
        artifact, digest = self.write_artifact("relay.go", b"relay-v1")
        packet = {
            "publicationDelivery": [
                {
                    "storage": "content_demo_outbox",
                    "artifact": {
                        "path": artifact.relative_to(self.workspace).as_posix(),
                        "sha256": digest,
                    },
                }
            ]
        }

        with mock.patch.object(closure, "ROOT", self.workspace):
            self.assertEqual(
                closure.artifact_gaps(
                    "content.demo", "aggregate_root", "implemented", packet
                ),
                [],
            )
            artifact.write_bytes(b"relay-v2")
            gaps = closure.artifact_gaps(
                "content.demo", "aggregate_root", "implemented", packet
            )
        self.assertEqual([gap.dimension for gap in gaps], ["derivation.artifact_digest"])
        self.assertIn("publicationDelivery", gaps[0].detail)

    def test_service_outbox_artifact_is_in_digest_closure(self) -> None:
        artifact, digest = self.write_artifact("outbox.go", b"outbox-v1")
        packet = canonical_evidence_packet()
        packet["service"]["outbox"] = [
            {
                "storage": "content_demo_outbox",
                "artifact": {
                    "path": artifact.relative_to(self.workspace).as_posix(),
                    "sha256": digest,
                },
            }
        ]

        with mock.patch.object(closure, "ROOT", self.workspace):
            self.assertEqual(
                closure.artifact_gaps(
                    "content.demo", "aggregate_root", "implemented", packet
                ),
                [],
            )
            artifact.write_bytes(b"outbox-v2")
            gaps = closure.artifact_gaps(
                "content.demo", "aggregate_root", "implemented", packet
            )

        self.assertEqual([gap.dimension for gap in gaps], ["derivation.artifact_digest"])
        self.assertIn("service.outbox", gaps[0].detail)

    def test_outbox_gap_diagnostic_reads_producer_separated_service_evidence(self) -> None:
        detail = closure.publication_gap_detail(
            "implementation.outbox",
            {
                "publicationStores": ["already_bound", "missing_outbox"],
                "service": {
                    "outbox": [
                        {
                            "storage": "already_bound",
                            "artifact": {"path": "unused.go", "sha256": "0" * 64},
                        }
                    ]
                },
            },
        )

        self.assertIn("missing_outbox", detail)
        self.assertNotIn("already_bound", detail)

    def test_artifact_paths_reject_absolute_traversal_and_symlink_escape(self) -> None:
        artifact, digest = self.write_artifact("inside.go", b"inside")
        with tempfile.TemporaryDirectory() as outside_dir:
            outside = Path(outside_dir) / "outside.go"
            outside.write_bytes(b"outside")
            symlink = self.workspace / "escaped.go"
            symlink.symlink_to(outside)
            cases = (
                str(artifact),
                "../outside.go",
                symlink.relative_to(self.workspace).as_posix(),
            )
            with mock.patch.object(closure, "ROOT", self.workspace):
                for path_text in cases:
                    with self.subTest(path=path_text):
                        gaps = closure.artifact_integrity_gaps(
                            "content.demo",
                            "aggregate_root",
                            "implemented",
                            "service.store",
                            {"path": path_text, "sha256": digest},
                        )
                        self.assertEqual(
                            [gap.dimension for gap in gaps],
                            ["derivation.artifact_missing"],
                        )

    def test_report_without_graph_binding_is_blocked(self) -> None:
        graph = self.write_graph(synthetic_graph())
        report = self.workspace / "report.json"
        report.write_text("{}", encoding="utf-8")

        with self.assertRaises(SystemExit) as failure:
            closure.validate_report_graph_binding(report, graph)

        self.assertIn("GATE_BLOCK", str(failure.exception))
        self.assertIn("contractGraph.path/sha256", str(failure.exception))

    def test_report_graph_digest_mismatch_is_blocked(self) -> None:
        graph = self.write_graph(synthetic_graph())
        report = self.workspace / "report.json"
        report.write_text(
            json.dumps(
                {
                    closure.REPORT_GRAPH_FIELD: {
                        "path": closure.display_path(graph),
                        "sha256": "0" * 64,
                    }
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaises(SystemExit) as failure:
            closure.validate_report_graph_binding(report, graph)

        self.assertIn("摘要不一致", str(failure.exception))

    def test_report_policy_binding_mismatch_is_blocked(self) -> None:
        graph = self.write_graph(synthetic_graph())
        registry = self.workspace / "absent-blind-spots.yaml"
        report = self.workspace / "report.json"
        report.write_text(
            json.dumps(
                {
                    closure.REPORT_BLIND_SPOT_REGISTRY_FIELD: {
                        "path": closure.display_path(registry.resolve()),
                        "sha256": "0" * 64,
                    },
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaises(SystemExit) as failure:
            closure.validate_report_policy_bindings(
                report,
                registry.resolve(),
                None,
            )

        self.assertIn("blindSpotRegistry", str(failure.exception))

    # --- scanner blindspot ------------------------------------------------

    def test_attested_scope_alone_cannot_release_a_blind_spot(self) -> None:
        registry = self.write_blind_spot_registry(
            [
                {
                    "object_id": "content.demo",
                    "dimension": "blindspot.publication_delivery_tracking",
                    "attested_scope": "demo scope",
                }
            ]
        )

        with self.assertRaises(SystemExit) as failure:
            closure.load_blind_spot_registry(registry)

        self.assertIn("classification", str(failure.exception))
        self.assertIn("attested_scope 不能证明实现存在", str(failure.exception))

    def test_implemented_blind_spot_requires_sha_bound_write_and_delivery(self) -> None:
        write, write_digest = self.write_artifact(
            "quwoquan_service/services/demo-service/internal/demo/store.go",
            b"write",
        )
        delivery, delivery_digest = self.write_artifact(
            "quwoquan_service/services/demo-service/internal/demo/relay.go",
            b"delivery",
        )
        key = ("content.demo", "blindspot.publication_delivery_tracking")
        registry_path = self.write_blind_spot_registry(
            [
                {
                    "object_id": key[0],
                    "dimension": key[1],
                    "attested_scope": "demo scope",
                    "classification": closure.BLIND_SPOT_IMPLEMENTED,
                    "implementation_evidence": {
                        "publication_write": [
                            {
                                "path": write.relative_to(self.workspace).as_posix(),
                                "sha256": write_digest,
                            }
                        ],
                        "publication_delivery": [
                            {
                                "path": delivery.relative_to(self.workspace).as_posix(),
                                "sha256": delivery_digest,
                            }
                        ],
                    },
                }
            ]
        )
        with mock.patch.object(closure, "ROOT", self.workspace):
            registry = closure.load_blind_spot_registry(registry_path)
        gap = closure.Gap(
            key[0], "aggregate_root", "implemented", key[1], "scanner blindspot"
        )

        self.assertEqual(closure.blind_spot_gaps([gap], registry), [])

    def test_implemented_blind_spot_rejects_test_source_as_evidence(self) -> None:
        test_source, digest = self.write_artifact(
            "quwoquan_service/services/demo-service/internal/demo/store_test.go",
            b"test only",
        )
        registry_path = self.write_blind_spot_registry(
            [
                {
                    "object_id": "content.demo",
                    "dimension": "blindspot.publication_write_tracking",
                    "attested_scope": "demo scope",
                    "classification": closure.BLIND_SPOT_IMPLEMENTED,
                    "implementation_evidence": {
                        "publication_write": [
                            {
                                "path": test_source.relative_to(
                                    self.workspace
                                ).as_posix(),
                                "sha256": digest,
                            }
                        ],
                        "publication_delivery": [
                            {
                                "path": test_source.relative_to(
                                    self.workspace
                                ).as_posix(),
                                "sha256": digest,
                            }
                        ],
                    },
                }
            ]
        )

        with (
            mock.patch.object(closure, "ROOT", self.workspace),
            self.assertRaises(SystemExit) as failure,
        ):
            closure.load_blind_spot_registry(registry_path)

        self.assertIn("生产 Go/Python 源码", str(failure.exception))

    def test_implementation_missing_blind_spot_stays_blocking(self) -> None:
        key = ("content.demo", "blindspot.publication_delivery_tracking")
        gap = closure.Gap(
            key[0], "aggregate_root", "implemented", key[1], "scanner blindspot"
        )
        problems = closure.blind_spot_gaps(
            [gap],
            {
                key: {
                    "attested_scope": "demo scope",
                    "classification": closure.BLIND_SPOT_MISSING,
                }
            },
        )

        self.assertEqual(len(problems), 1)
        self.assertIn("implementation_missing", problems[0])
        self.assertIn("必须补生产实现", problems[0])

    # --- App page / runtime consumption truth ---------------------------

    def test_page_command_is_bound_to_its_declared_participant(self) -> None:
        page_contract = self.write_page_contract(
            {
                "pages": [
                    {
                        "page_id": "content.demo",
                        "object_ids": ["content.demo"],
                        "query_slices": [],
                        "command_operations": ["content.demo.WriteDemo"],
                    }
                ],
                "runtime_execution": [],
            }
        )
        graph = {
            "objects": [{"id": "content.demo"}],
            "operations": [
                {
                    "id": "content.demo.WriteDemo",
                    "objectId": "content.demo",
                    "kind": "command",
                    "clientContract": True,
                }
            ],
        }

        with mock.patch.object(closure, "PAGE_OBJECT_CONTRACT", page_contract):
            claimed, query, command, runtime = closure.page_claims_and_consumers(graph)

        self.assertEqual(claimed, {"content.demo"})
        self.assertEqual(query, {})
        self.assertEqual(command, {"content.demo": {"content.demo"}})
        self.assertEqual(runtime, {})

    def test_page_command_rejects_query_or_foreign_object(self) -> None:
        graph = {
            "objects": [{"id": "content.demo"}, {"id": "content.foreign"}],
            "operations": [
                {
                    "id": "content.demo.ReadDemo",
                    "objectId": "content.demo",
                    "kind": "query",
                    "clientContract": True,
                },
                {
                    "id": "content.foreign.WriteForeign",
                    "objectId": "content.foreign",
                    "kind": "command",
                    "clientContract": True,
                },
            ],
        }
        for operation_id in ("content.demo.ReadDemo", "content.foreign.WriteForeign"):
            with self.subTest(operation_id=operation_id):
                page_contract = self.write_page_contract(
                    {
                        "pages": [
                            {
                                "page_id": "content.demo",
                                "object_ids": ["content.demo"],
                                "query_slices": [],
                                "command_operations": [operation_id],
                            }
                        ],
                        "runtime_execution": [],
                    }
                )
                with mock.patch.object(closure, "PAGE_OBJECT_CONTRACT", page_contract):
                    with self.assertRaises(SystemExit):
                        closure.page_claims_and_consumers(graph)

    def test_runtime_execution_rejects_adapter_only_or_missing_symbol(self) -> None:
        graph = {
            "objects": [{"id": "realtime.connection"}],
            "operations": [
                {
                    "id": "realtime.connection.IssueConnectionTicket",
                    "objectId": "realtime.connection",
                    "kind": "session",
                    "clientContract": True,
                    "localId": "IssueConnectionTicket",
                    "requestEntity": "IssueConnectionTicketRequest",
                    "facadeMethod": "issueTicket",
                }
            ],
        }
        evidence = [
            {
                "path": "lib/service/realtime_gateway/realtime/connection/adapters/realtime_connection_operation_remote.dart",
                "symbols": ["IssueConnectionTicketRequest"],
            },
            {
                "path": "lib/service/realtime_gateway/realtime/connection/adapters/realtime_config.dart",
                "symbols": ["realtimeConnectionWebSocketUpgrade"],
            },
        ]
        for mutated in (
            evidence,
            [evidence[0], {**evidence[1], "symbols": ["MissingProductionSymbol"]}],
        ):
            with self.subTest(evidence=mutated):
                page_contract = self.write_page_contract(
                    {
                        "pages": [],
                        "runtime_execution": [
                            {
                                "object_id": "realtime.connection",
                                "operation_ids": [
                                    "realtime.connection.IssueConnectionTicket"
                                ],
                                "production_evidence": mutated,
                            }
                        ],
                    }
                )
                with mock.patch.object(closure, "PAGE_OBJECT_CONTRACT", page_contract):
                    with self.assertRaises(SystemExit):
                        closure.page_claims_and_consumers(graph)

    def test_current_contract_keeps_exact_page_and_runtime_consumers(self) -> None:
        graph = json.loads(COMMITTED_GRAPH.read_text(encoding="utf-8"))
        claimed, query, command, runtime = closure.page_claims_and_consumers(graph)

        expected_query_pages = {
            "assistant.assistant_entry_view": {"content.home"},
            "assistant.assistant_task_view": {"assistant.skill_center"},
            "assistant.assistant_turn_view": {"assistant.personal_session"},
            "chat.message_receipt_fact": {"chat.detail"},
            "circle.circle_file": {"circle.detail"},
            "circle.circle_group": {"circle.detail", "circle.stats"},
            "circle.circle_group_membership": {"circle.detail"},
            "circle.circle_membership": {
                "circle.membership_approval",
                "circle.stats",
            },
            "entity.homepage_review": {"entity.detail"},
            "user.following_subject": {"content.home"},
        }
        expected_command_pages = {
            "assistant.assistant_learning_fact": {"assistant.personal_session"},
            "assistant.page_context": {"assistant.personal_session", "content.home"},
            "chat.conversation_user_state": {"chat.detail"},
            "circle.circle_behavior_fact": {"circle.detail"},
            "circle.circle_group_membership": {"circle.detail"},
            "circle.circle_post_placement": {
                "content.home",
                "content.media_viewer",
                "content.work_browser_entry",
            },
            "content.content_behavior_fact": {
                "assistant.personal_session",
                "circle.detail",
                "content.home",
                "content.media_viewer",
                "content.work_browser_entry",
                "entity.detail",
                "intersection.object_list",
                "user.my_footprint",
                "user.my_intersections",
                "user.my_profile",
                "user.other_profile",
            },
            "content.media_upload_session": {"chat.detail"},
            "rtc.call_session": {"chat.detail", "chat.settings"},
            "search.search_feedback_fact": {"search.network_results"},
            "tag.tag_feedback_fact": {"user.career_interest"},
            "user.followed_subject_visit_state": {"content.home"},
            "user.subject_follow": {"entity.detail"},
        }
        for object_id, pages in expected_query_pages.items():
            self.assertEqual(query.get(object_id), pages, object_id)
        for object_id, pages in expected_command_pages.items():
            self.assertTrue(pages.issubset(command.get(object_id) or set()), object_id)

        self.assertEqual(
            set(runtime),
            {
                "notification.notification_delivery_job",
                "ops.event_record",
                "ops.visit_record",
                "user.device_registration",
            },
        )
        for object_id in (
            "chat.message_receipt_fact",
            "circle.circle_group_membership",
        ):
            self.assertIn(object_id, claimed)
            self.assertIn(object_id, query)
            self.assertNotIn(object_id, runtime)

    def test_unconsumed_client_contract_is_a_structural_gap(self) -> None:
        page_contract = self.write_page_contract(
            {"pages": [], "runtime_execution": []}
        )
        graph = synthetic_graph(missing="")
        graph["objectReadiness"][0]["missing"] = []
        graph["operations"] = [
            {
                "id": "content.demo.ReadDemo",
                "objectId": "content.demo",
                "kind": "query",
                "clientContract": True,
            }
        ]
        with mock.patch.object(closure, "PAGE_OBJECT_CONTRACT", page_contract):
            gaps = closure.collect_gaps(graph)

        self.assertIn("app.unconsumed_contract", {gap.dimension for gap in gaps})
        self.assertEqual(
            closure.EVIDENCE_CLASS_BY_DIMENSION["app.unconsumed_contract"],
            closure.STRUCTURAL,
        )

    def test_gate_repo_runs_the_gate_and_this_contract(self) -> None:
        text = GATE_REPO.read_text(encoding="utf-8")
        self.assertIn("quwoquan_ops/gate/verify_object_evidence_closure.py", text)
        self.assertIn(Path(__file__).name, text)

    def test_make_commercial_target_requires_and_forwards_all_six_inputs(self) -> None:
        text = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("verify-object-evidence-commercial-closure:", text)
        expected = {
            "OBJECT_EVIDENCE_READINESS_BUNDLE": "--readiness-bundle",
            "OBJECT_EVIDENCE_SIGNED_CURRENT_SNAPSHOT": "--signed-current-snapshot",
            "OBJECT_EVIDENCE_SNAPSHOT_KEYRING": "--snapshot-keyring",
            "OBJECT_EVIDENCE_RUNNER_KEYRING": "--runner-keyring",
            "OBJECT_EVIDENCE_RECEIPT_ROOT": "--receipt-root",
            "OBJECT_EVIDENCE_EVIDENCE_ROOT": "--evidence-root",
        }
        for variable, option in expected.items():
            with self.subTest(variable=variable):
                self.assertIn(f'test -n "$(%s)"' % variable, text)
                self.assertIn(f'{option} "$(%s)"' % variable, text)
        self.assertNotIn("--update-baseline", text)


if __name__ == "__main__":
    unittest.main()

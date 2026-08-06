"""verify_object_evidence_closure 的棘轮基线判定口径合约。

覆盖：受版本控制的基线必须带完整 policy governance；任一「维度 × kind」计数格新增即
阻断且失败信息指向 objectId；格内下降或持平放行；`--update-baseline` 只能登记下降；
门禁与本测试都必须留在 `gate_repo.sh` 里（防止被悄悄摘掉）。
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


def synthetic_graph(kind: str = "projection", missing: str = "implementation.app_client") -> dict:
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


def baseline_document(cells: dict[str, dict[str, int]]) -> dict:
    return {
        "_governance": {
            "owner": "cloud-contract-governance",
            "reason": "test",
            "expires_when": "test",
        },
        "schema": closure.BASELINE_SCHEMA,
        "cells": cells,
    }


class ObjectEvidenceClosureRatchetTest(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self._directory.name)
        self.addCleanup(self._directory.cleanup)

    def write_graph(self, document: dict) -> Path:
        path = self.workspace / "graph.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def write_baseline(self, cells: dict[str, dict[str, int]], **overrides: object) -> Path:
        document = baseline_document(cells)
        document.update(overrides)
        path = self.workspace / "baseline.json"
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
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

    # --- 基线治理 ---------------------------------------------------------

    def test_committed_baseline_carries_full_policy_governance(self) -> None:
        document = json.loads(BASELINE.read_text(encoding="utf-8"))
        for key in ("owner", "reason", "expires_when"):
            self.assertTrue(
                str(document.get("_governance", {}).get(key) or "").strip(),
                f"基线 _governance 缺少 {key}",
            )
        self.assertEqual(document.get("schema"), closure.BASELINE_SCHEMA)
        self.assertTrue(closure.load_baseline(BASELINE))
        self.assertNotIn("手工", str(document.get("notes") or ""))

    def test_committed_baseline_contains_only_structural_dimensions(self) -> None:
        cells = json.loads(BASELINE.read_text(encoding="utf-8"))["cells"]

        self.assertTrue(cells)
        for dimension in cells:
            self.assertIn(dimension, closure.EVIDENCE_CLASS_BY_DIMENSION)
            self.assertEqual(
                closure.EVIDENCE_CLASS_BY_DIMENSION[dimension],
                closure.STRUCTURAL,
                dimension,
            )

    def test_baseline_rejects_result_blindspot_and_unknown_dimensions(self) -> None:
        cases = (
            ("environment.alpha", "result"),
            ("environment.beta", "result"),
            ("environment.gamma", "result"),
            ("environment.prod", "result"),
            ("blindspot.python_store_invisible", "blindspot"),
            ("future.unclassified", "未分层"),
        )
        for dimension, expected in cases:
            with self.subTest(dimension=dimension):
                path = self.write_baseline({dimension: {"projection": 1}})
                with self.assertRaises(SystemExit) as failure:
                    closure.load_baseline(path)
                self.assertIn(expected, str(failure.exception))

    def test_baseline_without_governance_is_blocked(self) -> None:
        path = self.write_baseline({}, _governance={"owner": "x", "reason": "y"})

        with self.assertRaises(SystemExit) as failure:
            closure.load_baseline(path)

        self.assertIn("expires_when", str(failure.exception))

    def test_missing_baseline_file_is_blocked(self) -> None:
        with self.assertRaises(SystemExit) as failure:
            closure.load_baseline(self.workspace / "absent.json")

        self.assertIn("GATE_BLOCK", str(failure.exception))

    def test_baseline_registers_counts_not_object_ids(self) -> None:
        """基线粒度即 allowlist 边界：出现 objectId 就等于给具体缺口发豁免。"""
        text = BASELINE.read_text(encoding="utf-8")
        cells = json.loads(text)["cells"]
        for dimension, kinds in cells.items():
            for kind, count in kinds.items():
                self.assertIsInstance(count, int, f"{dimension}.{kind} 必须是计数")
        for object_entry in json.loads(COMMITTED_GRAPH.read_text(encoding="utf-8"))["objects"]:
            self.assertNotIn(object_entry["id"], text)

    # --- 棘轮比对 ---------------------------------------------------------

    def test_new_cell_is_a_regression(self) -> None:
        regressions, improvements = closure.compare_with_baseline(
            {"app.client": {"projection": 1}}, {}
        )

        self.assertEqual([(item.dimension, item.kind, item.delta) for item in regressions],
                         [("app.client", "projection", 1)])
        self.assertEqual(improvements, [])

    def test_flat_and_decreased_cells_are_not_regressions(self) -> None:
        regressions, improvements = closure.compare_with_baseline(
            {"app.client": {"projection": 1, "aggregate_root": 3}},
            {"app.client": {"projection": 1, "aggregate_root": 5}},
        )

        self.assertEqual(regressions, [])
        self.assertEqual([(item.dimension, item.kind, item.delta) for item in improvements],
                         [("app.client", "aggregate_root", -2)])

    def test_gap_increase_blocks_and_names_the_object(self) -> None:
        graph = self.write_graph(synthetic_graph())
        baseline = self.write_baseline({})

        result = self.run_gate("--graph", str(graph), "--baseline", str(baseline))

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("GATE_BLOCK", result.stdout)
        self.assertIn("app.client / projection: 基线 0 → 实测 1（+1）", result.stdout)
        self.assertIn("content.demo", result.stdout)
        self.assertIn("修复路径", result.stdout)

    def test_gap_decrease_passes(self) -> None:
        graph = self.write_graph(synthetic_graph())
        baseline = self.write_baseline({"app.client": {"projection": 3}})

        result = self.run_gate("--graph", str(graph), "--baseline", str(baseline))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("未超出棘轮基线", result.stdout)
        self.assertIn("--update-baseline", result.stdout)

    def test_zero_gaps_passes_and_asks_to_retire_the_baseline(self) -> None:
        graph = self.write_graph(
            {"objects": [], "objectReadiness": [], "readinessEvidence": [], "operations": []}
        )
        baseline = self.write_baseline({"app.client": {"projection": 3}})

        result = self.run_gate("--graph", str(graph), "--baseline", str(baseline))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("无缺口", result.stdout)
        self.assertIn("删除基线文件", result.stdout)

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

    def test_all_environment_dimensions_are_result_evidence(self) -> None:
        for environment in ("alpha", "beta", "gamma", "prod"):
            with self.subTest(environment=environment):
                dimension = f"environment.{environment}"
                self.assertEqual(
                    closure.EVIDENCE_CLASS_BY_DIMENSION[dimension], closure.RESULT
                )

    def test_update_baseline_does_not_write_result_dimensions(self) -> None:
        graph = self.write_graph(
            synthetic_graph(missing="commercial.environment.alpha")
        )
        baseline = self.write_baseline({})

        result = self.run_gate(
            "--graph", str(graph), "--baseline", str(baseline), "--update-baseline"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(baseline.read_text(encoding="utf-8"))["cells"], {})

    def test_static_report_marks_dynamic_readiness_not_evaluated(self) -> None:
        graph = self.write_graph(synthetic_graph())
        baseline = self.write_baseline({"app.client": {"projection": 1}})

        result = self.run_gate("--graph", str(graph), "--baseline", str(baseline))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(
            (self.workspace / "report" / "object_evidence_closure.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(report["dynamicReadiness"]["status"], "not_evaluated")
        self.assertFalse(report["dynamicReadiness"]["commercialReady"])
        self.assertIsNone(report["dynamicReadiness"]["resultBundle"])
        self.assertEqual(
            report[closure.REPORT_BASELINE_FIELD],
            {
                "path": closure.display_path(baseline.resolve()),
                "sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
            },
        )
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
        baseline = self.write_baseline({})

        result = self.run_gate(
            "--graph",
            str(graph),
            "--baseline",
            str(baseline),
            "--require-commercial-readiness",
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("GATE_BLOCK 动态商业 readiness 未执行", result.stdout)
        self.assertIn("可信 ReceiptResolver", result.stdout)

    def test_required_commercial_mode_rejects_baselined_structural_debt(self) -> None:
        graph = self.write_graph(synthetic_graph())
        baseline = self.write_baseline({"app.client": {"projection": 1}})

        result = self.run_gate(
            "--graph",
            str(graph),
            "--baseline",
            str(baseline),
            "--require-commercial-readiness",
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "GATE_BLOCK 动态商业 readiness 要求结构性证据零缺口",
            result.stdout,
        )
        self.assertIn("app.client", result.stdout)
        self.assertNotIn("动态商业 readiness 未执行", result.stdout)

    def test_required_commercial_mode_rejects_registered_blindspot(self) -> None:
        graph = self.write_graph(
            synthetic_graph(missing="blindspot.python_store_invisible")
        )
        baseline = self.write_baseline({})
        report = self.workspace / "report" / "object_evidence_closure.json"
        key = ("content.demo", "blindspot.python_store_invisible")
        arguments = SimpleNamespace(
            baseline=baseline,
            report_dir=report.parent,
            update_baseline=False,
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

    def test_update_baseline_refuses_to_absorb_an_increase(self) -> None:
        graph = self.write_graph(synthetic_graph())
        baseline = self.write_baseline({})

        result = self.run_gate(
            "--graph", str(graph), "--baseline", str(baseline), "--update-baseline"
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("REFUSED --update-baseline", result.stdout)
        self.assertEqual(json.loads(baseline.read_text(encoding="utf-8"))["cells"], {})

    def test_update_baseline_refuses_an_unclassified_dimension(self) -> None:
        graph = self.write_graph(synthetic_graph())
        baseline = self.write_baseline({})
        report = self.workspace / "report" / "object_evidence_closure.json"
        unknown = closure.Gap(
            "content.demo",
            "projection",
            "implemented",
            "future.unclassified_evidence",
            "synthetic future dimension",
        )
        arguments = SimpleNamespace(
            baseline=baseline,
            report_dir=report.parent,
            update_baseline=True,
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
            mock.patch.object(closure, "load_baseline", return_value={}),
            mock.patch.object(closure, "load_blind_spot_registry", return_value={}),
            mock.patch.object(closure, "write_reports", return_value=report),
            mock.patch.object(closure, "write_baseline") as write_baseline,
            mock.patch("builtins.print") as print_line,
        ):
            return_code = closure.main()

        self.assertEqual(return_code, 1)
        output = "\n".join(" ".join(map(str, call.args)) for call in print_line.call_args_list)
        self.assertIn("GATE_BLOCK 出现未分层的缺口维度", output)
        self.assertIn("future.unclassified_evidence", output)
        write_baseline.assert_not_called()
        self.assertEqual(json.loads(baseline.read_text(encoding="utf-8"))["cells"], {})

    def test_update_baseline_refuses_an_unregistered_blind_spot(self) -> None:
        graph = self.write_graph(
            synthetic_graph(missing="blindspot.python_store_invisible")
        )
        baseline = self.write_baseline({})

        result = self.run_gate(
            "--graph", str(graph), "--baseline", str(baseline), "--update-baseline"
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("GATE_BLOCK 维度盲点集合与登记册不一致", result.stdout)
        self.assertIn("content.demo", result.stdout)
        self.assertEqual(json.loads(baseline.read_text(encoding="utf-8"))["cells"], {})

    def test_update_baseline_tightens_and_keeps_governance(self) -> None:
        graph = self.write_graph(synthetic_graph())
        baseline = self.write_baseline({"app.client": {"projection": 3}})

        result = self.run_gate(
            "--graph", str(graph), "--baseline", str(baseline), "--update-baseline"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        document = json.loads(baseline.read_text(encoding="utf-8"))
        self.assertEqual(document["cells"], {"app.client": {"projection": 1}})
        self.assertEqual(document["_governance"]["owner"], "cloud-contract-governance")

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
        baseline = self.write_baseline({"app.client": {"projection": 1}})

        result = self.run_gate("--graph", str(graph), "--baseline", str(baseline))

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
        baseline = self.write_baseline({})
        registry = self.workspace / "absent-blind-spots.yaml"
        baseline_digest = hashlib.sha256(baseline.read_bytes()).hexdigest()
        report = self.workspace / "report.json"
        report.write_text(
            json.dumps(
                {
                    closure.REPORT_BASELINE_FIELD: {
                        "path": closure.display_path(baseline.resolve()),
                        "sha256": "0" * 64,
                    },
                    closure.REPORT_BLIND_SPOT_REGISTRY_FIELD: {
                        "path": closure.display_path(registry.resolve()),
                        "status": "absent",
                    },
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaises(SystemExit) as failure:
            closure.validate_report_policy_bindings(
                report,
                baseline.resolve(),
                baseline_digest,
                registry.resolve(),
                None,
            )

        self.assertIn("ratchetBaseline", str(failure.exception))

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
            "circle.circle_group": {"circle.detail"},
            "circle.circle_group_membership": {"circle.detail"},
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
                "ops.app_release",
                "ops.event_record",
                "ops.recovery_failure",
                "ops.visit_record",
                "realtime.connection",
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


if __name__ == "__main__":
    unittest.main()

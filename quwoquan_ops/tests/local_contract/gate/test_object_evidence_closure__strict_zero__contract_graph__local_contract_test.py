"""verify_object_evidence_closure 的 STRUCTURAL 严格零值合约。

覆盖：历史 baseline 必须缺席；任一结构缺口都阻断并指向 objectId；
RESULT 只可见而不伪造静态 PASS；商业模式没有可信动态回执时继续 fail-closed；
门禁与本测试都必须留在 `gate_repo.sh` 里。
"""

# Python 1000 行硬顶治理：原单文件按场景拆分为本文件与同目录
# test_object_evidence_closure__strict_zero__*__local_contract_test.py 兄弟文件；
# 共享 harness 下沉 quwoquan_ops/tests/support/object_evidence_closure_test_support.py。
# 本文件保留「contract graph 派生/选择、图形状校验与 report 绑定」场景。

from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.tests.support.object_evidence_closure_test_support import (
    COMMITTED_GRAPH,
    ObjectEvidenceClosureStrictZeroSupport,
    canonical_evidence_packet,
    closure,
    synthetic_graph,
)


class ObjectEvidenceClosureStrictZeroTest(ObjectEvidenceClosureStrictZeroSupport):
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


if __name__ == "__main__":
    unittest.main()

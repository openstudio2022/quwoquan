"""readiness execution plan 的进程隔离与 fail-closed 合约。"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "quwoquan_ops/gate/verify_readiness_execution_plan.py"
MAKEFILE = ROOT / "Makefile"
SPEC = importlib.util.spec_from_file_location("verify_readiness_execution_plan", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
planner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = planner
SPEC.loader.exec_module(planner)


class FakeRunner:
    def __init__(self, output: bytes, *, exit_code: int = 0) -> None:
        self.output = output
        self.exit_code = exit_code
        self.calls: list[list[str]] = []
        self.after_run = None

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(command)
        if command[:2] == ["go", "build"]:
            binary = Path(command[command.index("-o") + 1])
            binary.write_bytes(b"planner-binary")
            binary.chmod(0o700)
            return subprocess.CompletedProcess(command, 0, b"", b"")
        if self.after_run is not None:
            self.after_run(len(self.calls) - 1)
        return subprocess.CompletedProcess(command, self.exit_code, self.output, b"")


class ReadinessExecutionPlanGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.addCleanup(self._temporary.cleanup)
        self.graph = self.root / "contract_graph.json"
        self.graph.write_text(json.dumps({"sources": []}), encoding="utf-8")
        self.report_dir = self.root / "reports"
        self.build_root = self.root / "build"

    def valid_plan(self) -> dict:
        return {
            "schema": planner.PLAN_SCHEMA,
            "contractGraphSourceHash": "a" * 64,
            "caseCount": 1,
            "executionSlotCount": 1,
            "runnerSourceCount": 1,
            "slots": [
                {
                    "objectId": "assistant.assistant_run",
                    "specRef": "specs/assistant/spec.md#gwt-001",
                    "caseId": "assistant-run-local",
                    "producer": "service",
                    "layer": "local_contract",
                    "target": {"kind": "object", "id": "assistant.assistant_run"},
                    "runnerSourcePath": "quwoquan_service/services/assistant-service/tests/local_contract/assistant/assistant_run/run_test.go",
                    "sourcePath": "assistant/assistant_run/operations.yaml",
                    "execution": {
                        "environment": "alpha",
                        "platform": "server",
                        "deviceClass": "host",
                        "provider": "local",
                        "digestBinding": "candidate",
                    },
                }
            ],
        }

    def runner_for(self, document: dict | None = None, *, exit_code: int = 0) -> FakeRunner:
        payload = json.dumps(document or self.valid_plan(), sort_keys=True).encode() + b"\n"
        return FakeRunner(payload, exit_code=exit_code)

    def extract(self, runner: FakeRunner) -> Path:
        return planner.extract_plan(
            self.graph,
            self.report_dir,
            build_root=self.build_root,
            runner=runner,
        )

    def test_builds_once_runs_binary_twice_and_binds_digests(self) -> None:
        runner = self.runner_for()
        report_path = self.extract(runner)
        self.assertEqual(runner.calls[0][:2], ["go", "build"])
        self.assertEqual(len(runner.calls), 3)
        self.assertEqual(runner.calls[1], runner.calls[2])
        self.assertNotEqual(runner.calls[1][0], "go")

        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["schema"], planner.REPORT_SCHEMA)
        self.assertEqual(
            report["contractGraph"]["sha256"],
            hashlib.sha256(self.graph.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            report["planSha256"],
            hashlib.sha256(runner.output).hexdigest(),
        )
        self.assertEqual(report["plan"]["executionSlotCount"], 1)
        self.assertNotIn("status", runner.output.decode())
        self.assertNotIn("receipt", runner.output.decode())
        self.assertNotIn("signature", runner.output.decode())

    def test_invalid_exit_and_planner_rejection_block(self) -> None:
        with self.assertRaisesRegex(planner.GateBlock, "非法 exit=1"):
            self.extract(self.runner_for(exit_code=1))
        failure = FakeRunner(b'{"error":"invalid graph"}\n', exit_code=2)
        with self.assertRaisesRegex(planner.GateBlock, "拒绝 ContractGraph"):
            self.extract(failure)

    def test_non_json_multiple_json_and_duplicate_key_block(self) -> None:
        for payload in (
            b"not-json",
            b'{"schema":"x"}\n{"second":true}\n',
            b'{"schema":"x","schema":"y"}\n',
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(planner.GateBlock):
                    self.extract(FakeRunner(payload))

    def test_protocol_count_or_shape_drift_blocks(self) -> None:
        wrong_count = self.valid_plan()
        wrong_count["executionSlotCount"] = 2
        with self.assertRaisesRegex(planner.GateBlock, "slots 长度"):
            self.extract(self.runner_for(wrong_count))
        wrong_shape = self.valid_plan()
        wrong_shape["slots"][0]["status"] = "passed"
        with self.assertRaisesRegex(planner.GateBlock, "keys 不匹配"):
            self.extract(self.runner_for(wrong_shape))

    def test_graph_drift_during_planner_run_blocks_without_report(self) -> None:
        runner = self.runner_for()

        def mutate(call_index: int) -> None:
            if call_index == 2:
                self.graph.write_text(json.dumps({"sources": [], "changed": True}), encoding="utf-8")

        runner.after_run = mutate
        with self.assertRaisesRegex(planner.GateBlock, "发生漂移"):
            self.extract(runner)
        self.assertEqual(list(self.report_dir.glob("readiness_execution_plan.*.json")), [])

    def test_timeout_blocks(self) -> None:
        def timeout_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
            raise subprocess.TimeoutExpired(command, 1)

        with self.assertRaisesRegex(planner.GateBlock, "命令超时"):
            planner.extract_plan(
                self.graph,
                self.report_dir,
                build_root=self.build_root,
                runner=timeout_runner,
            )

    def test_cli_and_make_require_an_explicit_graph(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as context:
            planner.parse_arguments([])
        self.assertEqual(context.exception.code, 2)
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("verify-readiness-execution-plan:", makefile)
        self.assertIn("READINESS_EXECUTION_PLAN_GRAPH", makefile)
        self.assertNotIn("--update-baseline", SCRIPT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

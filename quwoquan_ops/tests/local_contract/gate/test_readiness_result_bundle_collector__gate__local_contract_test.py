"""signed readiness bundle collector 的薄进程包装合同。"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "quwoquan_ops/gate/collect_readiness_result_bundle.py"
MAKEFILE = ROOT / "Makefile"
SPEC = importlib.util.spec_from_file_location("collect_readiness_result_bundle", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
collector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)


class FakeRunner:
    def __init__(self, output: bytes, exit_code: int) -> None:
        self.output = output
        self.exit_code = exit_code
        self.calls: list[list[str]] = []
        self.after_collect = None

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(command)
        if command[:2] == ["go", "build"]:
            binary = Path(command[command.index("-o") + 1])
            binary.write_bytes(b"collector-binary")
            binary.chmod(0o700)
            return subprocess.CompletedProcess(command, 0, b"", b"")
        if self.after_collect is not None:
            self.after_collect()
        return subprocess.CompletedProcess(command, self.exit_code, self.output, b"")


class ReadinessResultBundleCollectorGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)
        self.graph = self.root / "contract_graph.json"
        self.keyring = self.root / "runner_keyring.json"
        self.receipts = self.root / "receipts"
        self.evidence = self.root / "evidence"
        self.metadata = self.root / "metadata"
        self.graph.write_text('{"sources":[]}', encoding="utf-8")
        self.keyring.write_text('{"runners":[]}', encoding="utf-8")
        self.receipts.mkdir()
        self.evidence.mkdir()
        self.metadata.mkdir()
        self.build_root = self.root / "build"

    def arguments(self) -> list[str]:
        return [
            "--graph",
            str(self.graph),
            "--runner-keyring",
            str(self.keyring),
            "--receipt-root",
            str(self.receipts),
            "--evidence-root",
            str(self.evidence),
            "--metadata-dir",
            str(self.metadata),
        ]

    @staticmethod
    def bundle(statuses: list[str]) -> bytes:
        return (
            json.dumps(
                {
                    "generatedAt": "2026-08-08T10:00:00Z",
                    "results": [{"status": status} for status in statuses],
                },
                sort_keys=True,
            )
            + "\n"
        ).encode()

    def invoke(self, runner: FakeRunner) -> tuple[int, bytes]:
        output = io.BytesIO()
        code = collector.main(
            self.arguments(),
            stdout=output,
            runner=runner,
            build_root=self.build_root,
        )
        return code, output.getvalue()

    def test_builds_once_and_preserves_zero_one_two_protocol(self) -> None:
        for exit_code, payload in (
            (0, self.bundle(["passed"])),
            (1, self.bundle(["failed"])),
            (1, b'{"complete":false,"missingSlots":2}\n'),
            (2, b'{"error":"untrusted receipt"}\n'),
        ):
            with self.subTest(exit_code=exit_code, payload=payload):
                runner = FakeRunner(payload, exit_code)
                code, output = self.invoke(runner)
                self.assertEqual(code, exit_code)
                self.assertEqual(output, payload)
                self.assertEqual(runner.calls[0][:2], ["go", "build"])
                self.assertEqual(len(runner.calls), 2)
                self.assertNotEqual(runner.calls[1][0], "go")

    def test_invalid_exit_json_stderr_or_protocol_returns_two(self) -> None:
        cases = (
            FakeRunner(b'{"generatedAt":"x","results":[]}\n', 7),
            FakeRunner(b"not-json", 0),
            FakeRunner(b'{"error":"x"}\n{}\n', 2),
            FakeRunner(b'{"error":"x","error":"y"}\n', 2),
            FakeRunner(b'{"complete":true,"missingSlots":1}\n', 1),
            FakeRunner(self.bundle(["failed"]), 0),
        )
        for runner in cases:
            with self.subTest(output=runner.output, exit_code=runner.exit_code):
                code, output = self.invoke(runner)
                self.assertEqual(code, 2)
                self.assertIsInstance(json.loads(output), dict)
                self.assertIn("error", json.loads(output))
        stderr = FakeRunner(self.bundle(["passed"]), 0)

        def writes_stderr(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
            result = stderr(command)
            if command[:2] != ["go", "build"]:
                result.stderr = b"unexpected"
            return result

        output = io.BytesIO()
        code = collector.main(
            self.arguments(), stdout=output, runner=writes_stderr, build_root=self.build_root
        )
        self.assertEqual(code, 2)

    def test_graph_or_keyring_drift_returns_two(self) -> None:
        for path in (self.graph, self.keyring):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                runner = FakeRunner(self.bundle(["passed"]), 0)
                runner.after_collect = lambda selected=path: selected.write_bytes(
                    selected.read_bytes() + b" "
                )
                code, output = self.invoke(runner)
                self.assertEqual(code, 2)
                self.assertIn("漂移", json.loads(output)["error"])
                path.write_bytes(original)

    def test_symlinked_graph_is_rejected_before_build(self) -> None:
        real = self.root / "real_graph.json"
        real.write_bytes(self.graph.read_bytes())
        self.graph.unlink()
        self.graph.symlink_to(real)
        runner = FakeRunner(self.bundle(["passed"]), 0)
        code, output = self.invoke(runner)
        self.assertEqual(code, 2)
        self.assertEqual(runner.calls, [])
        self.assertIn("symlink", json.loads(output)["error"])

    def test_make_target_requires_inputs_and_calls_only_thin_wrapper(self) -> None:
        text = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn("collect-readiness-result-bundle:", text)
        for variable in (
            "READINESS_RESULT_BUNDLE_GRAPH",
            "READINESS_RESULT_BUNDLE_RUNNER_KEYRING",
            "READINESS_RESULT_BUNDLE_RECEIPT_ROOT",
            "READINESS_RESULT_BUNDLE_EVIDENCE_ROOT",
        ):
            self.assertIn(f'test -n "$({variable})"', text)
        self.assertIn("quwoquan_ops/gate/collect_readiness_result_bundle.py", text)
        self.assertNotIn("PrivateKey", SCRIPT.read_text(encoding="utf-8"))
        self.assertNotIn("--update-baseline", SCRIPT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

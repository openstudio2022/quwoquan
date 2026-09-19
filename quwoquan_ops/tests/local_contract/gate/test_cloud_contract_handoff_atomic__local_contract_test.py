from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops/cli/cloud_contract_handoff_atomic.py"
SPEC = importlib.util.spec_from_file_location(
    "cloud_contract_handoff_atomic_test_subject",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
atomic = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = atomic
SPEC.loader.exec_module(atomic)


class CloudContractHandoffAtomicTest(unittest.TestCase):
    def test_preview_only_never_accepts_even_without_breaking(self) -> None:
        # spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
        for changes in ([], [{"kind": "changed"}]):
            with tempfile.TemporaryDirectory() as directory:
                lock = Path(directory) / "lock.json"
                lock.write_text("{}", encoding="utf-8")
                with (
                    mock.patch.object(sys, "argv", ["atomic", "--preview-only", "--max-attempts", "1"]),
                    mock.patch.object(atomic, "CANONICAL_LOCK", lock),
                    mock.patch.object(atomic, "tree_is_quiet", return_value=True),
                    mock.patch.object(atomic, "rebuild_graph", return_value=True),
                    mock.patch.object(atomic, "preview_breaking", return_value=(True, changes)),
                    mock.patch.object(atomic, "accept_lock") as accept,
                    mock.patch.object(atomic, "codegen_app") as generate,
                ):
                    self.assertEqual(atomic.main(), atomic.EXIT_OK)
                    accept.assert_not_called()
                    generate.assert_not_called()
                    self.assertEqual(lock.read_text(), "{}")

    def test_breaking_preview_exit_is_a_successful_review_handoff(self) -> None:
        breaking = [
            {
                "kind": "removed",
                "canonicalOperationId": "circle.gathering_plan.CreateGatheringPlan",
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            preview = Path(temp_dir) / "preview.json"
            stale = {"breakingChanges": []}
            preview.write_text(json.dumps(stale), encoding="utf-8")

            def run_preview(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
                # preview_breaking must remove stale evidence before invoking the CLI.
                self.assertFalse(preview.exists())
                preview.write_text(
                    json.dumps({"breakingChanges": breaking}),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(
                    args=["handoff", "accept", "--preview-report"],
                    returncode=1,
                    stdout="PREVIEW: report written\nFAIL: breaking changes found\n",
                    stderr="",
                )

            with (
                mock.patch.object(atomic, "PREVIEW_REPORT", preview),
                mock.patch.object(atomic, "_run", side_effect=run_preview),
            ):
                ok, actual = atomic.preview_breaking(Path("snapshot"), "a" * 64)

        self.assertTrue(ok)
        self.assertEqual(actual, breaking)

    def test_non_breaking_nonzero_preview_remains_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            preview = Path(temp_dir) / "preview.json"

            def run_preview(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
                preview.write_text(
                    json.dumps({"breakingChanges": []}),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(
                    args=["handoff", "accept", "--preview-report"],
                    returncode=1,
                    stdout="FAIL: unrelated preview failure\n",
                    stderr="",
                )

            with (
                mock.patch.object(atomic, "PREVIEW_REPORT", preview),
                mock.patch.object(atomic, "_run", side_effect=run_preview),
            ):
                ok, actual = atomic.preview_breaking(Path("snapshot"), "a" * 64)

        self.assertFalse(ok)
        self.assertEqual(actual, [])


if __name__ == "__main__":
    unittest.main()

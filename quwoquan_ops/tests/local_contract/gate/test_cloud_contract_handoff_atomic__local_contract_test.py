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

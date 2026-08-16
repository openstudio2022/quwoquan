"""Mutable startup receipts never impersonate immutable runtime evidence.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-001
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import test_live_startup_attempt_receipt as receipt
from quwoquan_ops.cli.lib.startup_attempt_receipt import validate_startup_attempt


def _plan() -> dict[str, object]:
    return {
        "schema": "stackctl.mutable_test_live_runtime",
        "environment": "alpha",
        "target": "alpha-local",
        "composeProject": "quwoquan_alpha_test_live",
        "composeDigest": "sha256:" + "1" * 64,
        "configurationDigest": "sha256:" + "2" * 64,
        "providerRuntimeDigest": "sha256:" + "3" * 64,
        "portProfile": "alpha-local",
        "portBlock": {"start": 17000, "end": 17999},
        "publishedPorts": {"api-edge": 17000, "sms-provider-substitute": 17080},
        "tlsProfile": "local-managed",
        "resolverHandoffDigest": "sha256:" + "4" * 64,
        "publicWebPackage": {
            "environment": "alpha",
            "packageVersion": "web-release-alpha",
            "manifestDigest": "sha256:" + "7" * 64,
            "contentDigest": "sha256:" + "8" * 64,
            "publicOrigin": "https://alpha.quwoquan.com:17000",
        },
        "workspaceIdentity": {
            "sourceRevision": "a" * 40,
            "workspaceStatusDigest": "sha256:" + "5" * 64,
            "mutableStateDigest": "sha256:" + "6" * 64,
        },
    }


class TestLiveStartupAttemptReceiptContractTest(unittest.TestCase):
    def _patch_roots(self, root: Path):
        return (
            mock.patch.object(receipt, "target_process_dir", return_value=root / "process"),
            mock.patch.object(receipt, "env_runs_root", return_value=root / "runs"),
        )

    def test_prepared_partial_running_is_target_scoped_and_nonpromotable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_root = root / "runs" / "dev-session-alpha"
            process_patch, runs_patch = self._patch_roots(root)
            with process_patch, runs_patch:
                prepared = receipt.transition_test_live_startup_attempt(
                    environment="alpha",
                    target="alpha-local",
                    attempt_id="alpha-test-live-attempt-1",
                    status="prepared",
                    runtime_plan=_plan(),
                    run_root=run_root,
                )
                partial = receipt.transition_test_live_startup_attempt(
                    environment="alpha",
                    target="alpha-local",
                    attempt_id=prepared["attemptId"],
                    status="partial",
                    runtime_plan=_plan(),
                    run_root=run_root,
                )
                running = receipt.transition_test_live_startup_attempt(
                    environment="alpha",
                    target="alpha-local",
                    attempt_id=prepared["attemptId"],
                    status="running",
                    runtime_plan=_plan(),
                    run_root=run_root,
                )
                loaded = receipt.load_test_live_startup_attempt("alpha-local")

        self.assertEqual(prepared["status"], "prepared")
        self.assertEqual(partial["status"], "partial")
        self.assertEqual(running, loaded)
        self.assertEqual(running["status"], "running")
        self.assertEqual(running["configurationDigest"], "sha256:" + "2" * 64)
        self.assertEqual(running["sourceRevision"], "a" * 40)
        self.assertEqual(
            running["publicWebPackage"]["packageVersion"],
            "web-release-alpha",
        )
        self.assertTrue(running["nonPromotable"])
        self.assertNotIn("candidateDigest", running)
        self.assertNotIn("imageComposition", running)
        with self.assertRaisesRegex(ValueError, "fields mismatch"):
            validate_startup_attempt(running)

    def test_up_failure_remains_partial_with_the_original_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_root = root / "runs" / "dev-session-alpha"
            process_patch, runs_patch = self._patch_roots(root)
            with process_patch, runs_patch:
                receipt.transition_test_live_startup_attempt(
                    environment="alpha",
                    target="alpha-local",
                    attempt_id="alpha-test-live-attempt-2",
                    status="prepared",
                    runtime_plan=_plan(),
                    run_root=run_root,
                )
                receipt.transition_test_live_startup_attempt(
                    environment="alpha",
                    target="alpha-local",
                    attempt_id="alpha-test-live-attempt-2",
                    status="partial",
                    runtime_plan=_plan(),
                    run_root=run_root,
                )
                failed = receipt.transition_test_live_startup_attempt(
                    environment="alpha",
                    target="alpha-local",
                    attempt_id="alpha-test-live-attempt-2",
                    status="partial",
                    runtime_plan=_plan(),
                    run_root=run_root,
                    failure="compose up exited 1",
                )

        self.assertEqual(failed["status"], "partial")
        self.assertEqual(failed["failure"], "compose up exited 1")

    def test_identity_drift_and_formal_fields_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_root = root / "runs" / "dev-session-alpha"
            process_patch, runs_patch = self._patch_roots(root)
            with process_patch, runs_patch:
                prepared = receipt.transition_test_live_startup_attempt(
                    environment="alpha",
                    target="alpha-local",
                    attempt_id="alpha-test-live-attempt-3",
                    status="prepared",
                    runtime_plan=_plan(),
                    run_root=run_root,
                )
                drifted = _plan()
                drifted["configurationDigest"] = "sha256:" + "9" * 64
                with self.assertRaisesRegex(ValueError, "configurationDigest"):
                    receipt.transition_test_live_startup_attempt(
                        environment="alpha",
                        target="alpha-local",
                        attempt_id=prepared["attemptId"],
                        status="partial",
                        runtime_plan=drifted,
                        run_root=run_root,
                    )
                drifted_web = _plan()
                drifted_web["publicWebPackage"] = {
                    **drifted_web["publicWebPackage"],
                    "contentDigest": "sha256:" + "9" * 64,
                }
                with self.assertRaisesRegex(ValueError, "publicWebPackage"):
                    receipt.transition_test_live_startup_attempt(
                        environment="alpha",
                        target="alpha-local",
                        attempt_id=prepared["attemptId"],
                        status="partial",
                        runtime_plan=drifted_web,
                        run_root=run_root,
                    )
                invalid = dict(prepared)
                invalid["candidateDigest"] = "sha256:" + "7" * 64
                with self.assertRaisesRegex(ValueError, "fields mismatch"):
                    receipt.validate_test_live_startup_attempt(invalid)

    def test_cross_target_ports_and_unsafe_receipt_paths_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_root = root / "runs" / "dev-session-alpha"
            process_patch, runs_patch = self._patch_roots(root)
            with process_patch, runs_patch:
                invalid = _plan()
                invalid["publishedPorts"] = {"api-edge": 18000}
                with self.assertRaisesRegex(ValueError, "escapes target block"):
                    receipt.transition_test_live_startup_attempt(
                        environment="alpha",
                        target="alpha-local",
                        attempt_id="alpha-test-live-attempt-4",
                        status="prepared",
                        runtime_plan=invalid,
                        run_root=run_root,
                    )
                receipt_path = receipt.test_live_startup_attempt_path("alpha-local")
                receipt_path.parent.mkdir(parents=True)
                foreign = root / "foreign.json"
                foreign.write_text("{}\n", encoding="utf-8")
                receipt_path.symlink_to(foreign)
                with self.assertRaises(receipt.UnsafeTestLiveStartupReceiptPath):
                    receipt.load_test_live_startup_attempt("alpha-local")


if __name__ == "__main__":
    unittest.main()

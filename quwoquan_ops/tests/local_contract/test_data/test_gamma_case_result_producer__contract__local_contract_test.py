"""Contract tests for exact candidate-bound Gamma release-consumer/device-UAT CaseResult producers."""

# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-003

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_app.scripts.gamma import gamma_case_result
from quwoquan_app.scripts.gamma import run_local_gamma_release_consumer_api
from quwoquan_app.scripts.gamma import verify_local_gamma_mirror


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _identity() -> dict[str, str]:
    return {
        "environment": "gamma",
        "target": "gamma-local",
        "baselineId": _digest("1"),
        "attemptId": "attempt-gamma-1",
        "packageDigest": _digest("2"),
        "configurationDigest": _digest("3"),
        "providerRuntimeDigest": _digest("4"),
        "observabilityLogSinkDigest": _digest("5"),
        "imageDigest": _digest("6"),
    }


def _release_identity() -> dict[str, object]:
    return {
        "releaseId": "release-gamma-a",
        "sourceOwner": "quwoquan_data",
        "manifestDigest": _digest("7"),
        "mediaManifestDigest": _digest("8"),
        "importRunId": "import-gamma-a",
        "verifyRunId": "verify-gamma-a",
        "readinessReceiptRef": (
            "env/gamma/runs/release-gamma-a/verify-gamma-a/"
            "release-readiness.json"
        ),
    }


def _patrol_report(
    *,
    executed: int = 2,
    skipped: int = 0,
    failed: int = 0,
    status: str = "passed",
    devices: bool = True,
) -> dict[str, object]:
    execution = {
        "framework": "patrol",
        "executed": executed,
        "skipped": skipped,
        "failed": failed,
    }
    return {
        "suiteId": "environment_page_smoke",
        "status": status,
        "endedAt": "2026-08-06T00:00:10+00:00",
        "environmentAlias": "local-gamma",
        "runtimeEnv": "gamma",
        "apiContractEnv": "gamma",
        "composition": "production_remote",
        "evidenceClass": "user_acceptance_remote",
        "devices": ([{"id": "emulator-5554"}] if devices else []),
        "runs": [
            {
                "exitCode": 0 if status == "passed" else 1,
                "testExecution": execution,
            }
        ],
        "caseResults": [
            {
                "caseId": "patrol:feed:emulator-5554",
                "status": status,
                "deviceId": "emulator-5554",
                "testExecution": execution,
            }
        ],
    }


class GammaCaseResultProducerContractTest(unittest.TestCase):
    def test_passed_case_result_uses_exact_verifier_schema(self) -> None:
        payload = gamma_case_result.build_passed_case_result(
            phase="release_consumer",
            identity=_identity(),
            executed=1,
            skipped=0,
            failed=0,
            executed_at="2026-08-06T00:00:00Z",
        )

        self.assertEqual(set(payload), verify_local_gamma_mirror.CASE_RESULT_FIELDS)
        self.assertEqual(payload["caseId"], "local-gamma.release-consumer.remote-api")
        self.assertEqual(payload["specRefs"], verify_local_gamma_mirror.CASE_SPEC_REFS)
        self.assertEqual(
            verify_local_gamma_mirror.validate_gamma_case_result(
                payload,
                phase="release_consumer",
                identity=_identity(),
            ),
            payload,
        )

    def test_passed_case_result_rejects_skip_and_naive_timestamp(self) -> None:
        for skipped, executed_at in (
            (1, "2026-08-06T00:00:00Z"),
            (0, "2026-08-06T00:00:00"),
        ):
            with self.subTest(skipped=skipped, executed_at=executed_at):
                with self.assertRaises(gamma_case_result.GammaCaseResultError):
                    gamma_case_result.build_passed_case_result(
                        phase="device_uat",
                        identity=_identity(),
                        executed=1,
                        skipped=skipped,
                        failed=0,
                        executed_at=executed_at,
                    )

    def test_execution_identity_requires_one_stable_active_running_candidate(
        self,
    ) -> None:
        startup = {
            "status": "running",
            "workload": "full",
            "configurationDigest": _digest("3"),
        }
        active = {"baselineId": _digest("1"), "candidateDir": "/candidate"}
        candidate = {"baselineId": _digest("1")}
        with (
            mock.patch.object(
                gamma_case_result,
                "load_startup_attempt",
                side_effect=[startup, startup],
            ) as startup_loader,
            mock.patch.object(
                gamma_case_result,
                "active_deployment_candidate",
                side_effect=[active, active],
            ) as active_loader,
            mock.patch.object(
                gamma_case_result,
                "load_candidate_manifest",
                return_value=candidate,
            ) as candidate_loader,
            mock.patch.object(
                gamma_case_result.gamma_verifier,
                "_candidate_identity",
                return_value=_identity(),
            ) as identity_loader,
        ):
            actual = gamma_case_result.load_gamma_execution_identity()

        self.assertEqual(actual, _identity())
        self.assertEqual(startup_loader.call_count, 2)
        self.assertEqual(active_loader.call_count, 2)
        candidate_loader.assert_called_once_with(
            "gamma",
            "gamma-local",
            _digest("1"),
            require_full=True,
        )
        identity_loader.assert_called_once_with(
            startup=startup,
            active=active,
            candidate=candidate,
            configuration_digest=_digest("3"),
        )

    def test_execution_identity_rejects_mid_read_receipt_drift(self) -> None:
        startup = {
            "status": "running",
            "workload": "full",
            "configurationDigest": _digest("3"),
        }
        stopped = dict(startup, status="stopped")
        active = {"baselineId": _digest("1"), "candidateDir": "/candidate"}
        with (
            mock.patch.object(
                gamma_case_result,
                "load_startup_attempt",
                side_effect=[startup, stopped],
            ),
            mock.patch.object(
                gamma_case_result,
                "active_deployment_candidate",
                side_effect=[active, active],
            ),
            mock.patch.object(
                gamma_case_result,
                "load_candidate_manifest",
                return_value={"baselineId": _digest("1")},
            ),
            mock.patch.object(
                gamma_case_result.gamma_verifier,
                "_candidate_identity",
                return_value=_identity(),
            ),
        ):
            with self.assertRaisesRegex(
                gamma_case_result.GammaCaseResultError,
                "changed during identity validation",
            ):
                gamma_case_result.load_gamma_execution_identity()

    def test_evidence_path_rejects_escape_and_existing_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            evidence_root = root / "env" / "gamma" / "runs"
            physical = evidence_root / "physical"
            physical.mkdir(parents=True)
            link = evidence_root / "linked"
            link.symlink_to(physical, target_is_directory=True)

            with mock.patch.object(
                gamma_case_result,
                "output_root",
                return_value=root,
            ):
                with self.assertRaisesRegex(
                    gamma_case_result.GammaCaseResultError,
                    "cannot traverse a symlink",
                ):
                    gamma_case_result.resolve_gamma_evidence_path(
                        str(link / "device_uat.json"),
                        label="Gamma device-UAT CaseResult",
                    )
                with self.assertRaisesRegex(
                    gamma_case_result.GammaCaseResultError,
                    "must stay below",
                ):
                    gamma_case_result.resolve_gamma_evidence_path(
                        str(root / "outside.json"),
                        label="Gamma device-UAT CaseResult",
                    )

    def test_release_consumer_writes_only_exact_passed_case_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_path = Path(temporary_dir) / "release_consumer.json"
            with (
                mock.patch.object(
                    run_local_gamma_release_consumer_api,
                    "resolve_release_consumer_report_path",
                    return_value=report_path,
                ),
                mock.patch.object(
                    run_local_gamma_release_consumer_api,
                    "load_gamma_execution_identity",
                    return_value=_identity(),
                ),
                mock.patch.object(
                    run_local_gamma_release_consumer_api,
                    "require_unchanged_identity",
                    return_value=_identity(),
                ),
                mock.patch.object(
                    run_local_gamma_release_consumer_api,
                    "resolve_readiness_path",
                    return_value=Path("/receipt/release-readiness.json"),
                ),
                mock.patch.object(
                    run_local_gamma_release_consumer_api,
                    "load_release_content_identity",
                    return_value=_release_identity(),
                ),
                mock.patch.object(
                    run_local_gamma_release_consumer_api,
                    "run_release_consumer",
                    return_value={
                        "status": "passed",
                        "mutationPolicy": "read_only",
                        "exitCode": 0,
                    },
                ),
                mock.patch.object(
                    run_local_gamma_release_consumer_api.sys,
                    "argv",
                    ["run_local_gamma_release_consumer_api.py", "--report", str(report_path)],
                ),
            ):
                exit_code = run_local_gamma_release_consumer_api.main()
            payload = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(set(payload), verify_local_gamma_mirror.CASE_RESULT_FIELDS)
        self.assertEqual(payload["executed"], 1)
        self.assertEqual(payload["skipped"], 0)
        self.assertEqual(payload["failed"], 0)
        self.assertNotIn("release", payload)
        self.assertNotIn("consumer", payload)

    def test_release_consumer_missing_or_drifted_runtime_never_leaves_passed_report(self) -> None:
        for failure_point in ("preflight", "postflight"):
            with self.subTest(failure_point=failure_point):
                with tempfile.TemporaryDirectory() as temporary_dir:
                    report_path = Path(temporary_dir) / "release_consumer.json"
                    report_path.write_text('{"status":"passed"}', encoding="utf-8")
                    preflight = (
                        gamma_case_result.GammaCaseResultError("receipt missing")
                        if failure_point == "preflight"
                        else _identity()
                    )
                    with (
                        mock.patch.object(
                            run_local_gamma_release_consumer_api,
                            "resolve_release_consumer_report_path",
                            return_value=report_path,
                        ),
                        mock.patch.object(
                            run_local_gamma_release_consumer_api,
                            "load_gamma_execution_identity",
                            side_effect=(
                                preflight
                                if isinstance(preflight, Exception)
                                else None
                            ),
                            return_value=(
                                None
                                if isinstance(preflight, Exception)
                                else preflight
                            ),
                        ),
                        mock.patch.object(
                            run_local_gamma_release_consumer_api,
                            "resolve_readiness_path",
                            return_value=Path("/receipt/release-readiness.json"),
                        ),
                        mock.patch.object(
                            run_local_gamma_release_consumer_api,
                            "load_release_content_identity",
                            return_value=_release_identity(),
                        ),
                        mock.patch.object(
                            run_local_gamma_release_consumer_api,
                            "run_release_consumer",
                            return_value={
                                "status": "passed",
                                "mutationPolicy": "read_only",
                                "exitCode": 0,
                            },
                        ) as consumer,
                        mock.patch.object(
                            run_local_gamma_release_consumer_api,
                            "require_unchanged_identity",
                            side_effect=gamma_case_result.GammaCaseResultError(
                                "candidate changed"
                            ),
                        ),
                        mock.patch.object(
                            run_local_gamma_release_consumer_api.sys,
                            "argv",
                            ["run_local_gamma_release_consumer_api.py", "--report", str(report_path)],
                        ),
                    ):
                        exit_code = run_local_gamma_release_consumer_api.main()
                    payload = json.loads(report_path.read_text(encoding="utf-8"))

                self.assertEqual(exit_code, 2)
                self.assertEqual(payload["status"], "gate_block")
                if failure_point == "preflight":
                    consumer.assert_not_called()

    def test_device_uat_finalize_uses_real_patrol_counts_and_exact_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            report_path = root / "device_uat.json"
            identity_path = root / "device_uat.identity.json"
            patrol_path = root / "device_uat.patrol.json"
            gamma_case_result.write_identity_snapshot(
                path=identity_path,
                phase="device_uat",
                identity=_identity(),
            )
            patrol_path.write_text(
                json.dumps(_patrol_report()),
                encoding="utf-8",
            )
            with mock.patch.object(
                gamma_case_result,
                "require_unchanged_identity",
                return_value=_identity(),
            ):
                payload = gamma_case_result.finalize_device_uat(
                    report_path=report_path,
                    identity_snapshot_path=identity_path,
                    patrol_report_path=patrol_path,
                    dry_run=False,
                )

        self.assertEqual(set(payload), verify_local_gamma_mirror.CASE_RESULT_FIELDS)
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["executed"], 2)
        self.assertEqual(payload["skipped"], 0)
        self.assertEqual(payload["failed"], 0)

    def test_device_uat_prepare_invalidates_stale_pass_before_identity_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            report_path = root / "device_uat.json"
            identity_path = root / "device_uat.identity.json"
            patrol_path = root / "device_uat.patrol.json"
            stale = json.dumps({"status": "passed"})
            for path in (report_path, identity_path, patrol_path):
                path.write_text(stale, encoding="utf-8")

            with (
                mock.patch.object(
                    gamma_case_result,
                    "resolve_gamma_evidence_path",
                    return_value=patrol_path,
                ),
                mock.patch.object(
                    gamma_case_result,
                    "load_gamma_execution_identity",
                    side_effect=gamma_case_result.GammaCaseResultError(
                        "running receipt missing"
                    ),
                ),
            ):
                with self.assertRaises(gamma_case_result.GammaCaseResultError):
                    gamma_case_result.prepare_device_uat(
                        report_path=report_path,
                        identity_snapshot_path=identity_path,
                        patrol_report_path=patrol_path,
                    )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            snapshot = json.loads(identity_path.read_text(encoding="utf-8"))
            patrol = json.loads(patrol_path.read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "gate_block")
        self.assertEqual(snapshot["status"], "gate_block")
        self.assertEqual(patrol["status"], "gate_block")

    def test_device_uat_skip_dry_run_missing_device_and_drift_are_gate_block(self) -> None:
        cases = (
            ("skipped", _patrol_report(skipped=1), False, None, 0),
            ("dry-run", _patrol_report(), True, None, 0),
            ("missing-device", _patrol_report(devices=False), False, None, 0),
            ("runner-failed", _patrol_report(), False, None, 1),
            (
                "identity-drift",
                _patrol_report(),
                False,
                gamma_case_result.GammaCaseResultError("candidate changed"),
                0,
            ),
        )
        for name, patrol, dry_run, identity_error, runner_exit_code in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary_dir:
                root = Path(temporary_dir)
                report_path = root / "device_uat.json"
                identity_path = root / "device_uat.identity.json"
                patrol_path = root / "device_uat.patrol.json"
                gamma_case_result.write_identity_snapshot(
                    path=identity_path,
                    phase="device_uat",
                    identity=_identity(),
                )
                patrol_path.write_text(json.dumps(patrol), encoding="utf-8")
                with mock.patch.object(
                    gamma_case_result,
                    "require_unchanged_identity",
                    side_effect=identity_error,
                    return_value=_identity(),
                ):
                    payload = gamma_case_result.finalize_device_uat(
                        report_path=report_path,
                        identity_snapshot_path=identity_path,
                        patrol_report_path=patrol_path,
                        dry_run=dry_run,
                        runner_exit_code=runner_exit_code,
                    )

            self.assertEqual(payload["status"], "gate_block")
            self.assertNotEqual(
                set(payload),
                verify_local_gamma_mirror.CASE_RESULT_FIELDS,
            )

    def test_device_uat_shell_keeps_patrol_detail_as_sidecar_and_finalizes_case_result(
        self,
    ) -> None:
        source = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_app/scripts/gamma/run_local_gamma_device_uat.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("prepare-device-uat", source)
        self.assertIn("finalize-device-uat", source)
        self.assertIn('--report "$PATROL_REPORT"', source)
        self.assertNotIn('--report "$REPORT"\n  --target', source)
        self.assertIn('finalize_args+=(--dry-run)', source)
        self.assertIn('--runner-exit-code "$patrol_status"', source)


if __name__ == "__main__":
    unittest.main()

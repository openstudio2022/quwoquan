# spec_ref: specs/feature-tree/spec.md#uat-003
# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))
sys.path.insert(0, str(APP_DIR / "scripts/runtime/platform"))
sys.path.insert(0, str(APP_DIR / "test/support/runtime/launcher"))

from verify_startup_first_frame import (
    ScreenshotAnalysis,
    analyze_screenshot,
    android_fresh_startup_log_evidence,
    build_arg_parser,
    classify_startup_terminal,
    detect_native_static_petal_mismatch,
    detect_prolonged_system_blue,
    detect_repeated_splash,
    extract_startup_watchdog_evidence,
    native_launch_visual_provenance,
    android_gate_main_order_observed,
    parse_android_launcher_resolution,
    parse_android_task_snapshot,
    parse_startup_sequence_log,
)
from build_launcher_handoff import (
    dart_defines_digest,
    effective_launch_manifest_digest,
)
from launcher_package_fixture import fixture_runtime_config_digest
from verify_flutter_run_defines import validate_flutter_run_defines
from verify_startup_ttid_baseline import main as verify_startup_ttid_main
from verify_startup_ttid_baseline import validate_commercial_uat
from run_dual_platform_usability_matrix import (
    _load_execution_input,
    _validate_execution_preconditions,
)
import verify_startup_environment_matrix as startup_matrix
from verify_startup_environment_matrix import (
    _case_counts,
    _report_status,
    _validate_observability_evidence,
    _validate_readback_evidence,
    _validate_runtime_evidence,
)
from verify_startup_web import (
    build_arg_parser as build_web_arg_parser,
    overlay_removed_event,
    parse_startup_report,
    shell_event,
    startup_event,
    terminal_event,
)


class StartupProbeParserContractTest(unittest.TestCase):
    def test_release_bound_matrix_passes_only_with_all_real_case_results(
        self,
    ) -> None:
        digest = "sha256:" + "d" * 64
        baseline_id = "baseline-001"
        release_id = "release-001"
        runtime_cases = (
            ("alpha", "alpha-local"),
            ("beta", "beta-local"),
            ("gamma", "gamma-local"),
            ("prod", "prod-hosted"),
        )
        defines = {key: "value" for key in startup_matrix.REQUIRED_DEFINES}

        def environment_defines(environment: str) -> dict[str, str]:
            return {**defines, "APP_RUNTIME_ENV": environment}

        def handoff(environment: str, target: str | None = None) -> dict[str, str]:
            resolved_target = target or startup_matrix.RUNTIME_TARGETS[environment]
            return {
                "target": resolved_target,
                "entrypoint": "lib/main_prod.dart",
                "dartDefinesDigest": digest,
                "runtimeConfigDigest": digest,
                "effectiveLaunchManifestDigest": digest,
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            report_path = Path(directory) / "report.json"
            for environment, target in runtime_cases:
                target_root = root / target
                target_root.mkdir(parents=True, exist_ok=True)
                attempt_ids: list[str] = []
                device_ids: list[str] = []
                for platform, device_kind, evidence_stem in (
                    startup_matrix.DEVICE_PROFILES[target]
                ):
                    device_id = f"{evidence_stem}-device"
                    device_ids.append(device_id)
                    samples = []
                    for index in range(2):
                        attempt_id = f"{target}-{evidence_stem}-{index}"
                        attempt_ids.append(attempt_id)
                        sample = {
                            "runtimeEnv": environment,
                            "runtimeTarget": target,
                            "platform": platform,
                            "deviceId": device_id,
                            "deviceKind": device_kind,
                            "passed": True,
                            "attemptId": attempt_id,
                            "rendererFirstFrameMs": 900,
                            "safeTerminalMs": 1200,
                            "reportedSafeTerminalMs": 1190,
                            "nativeReceivedSafeTerminalMs": 1210,
                            "watchdogOutcome": "safe_terminal",
                            "canonicalTerminal": "routerShell",
                            "launchMode": "release_package",
                            "runtimeConfigurationState": "complete",
                            "missingDefineKeys": "",
                            "failureCode": "",
                            "startupSequenceMotionCurrent": True,
                            "effectiveLaunchManifestDigest": digest,
                            "telemetryAcknowledged": True,
                            "sourceReport": f"{target}-{evidence_stem}.json",
                        }
                        if platform == "android":
                            sample.update(
                                {
                                    "launcherIntentUsed": True,
                                    "launcherStarted": True,
                                    "launcherResolution": {
                                        "matchesExpectedGate": True,
                                    },
                                    "gateMainOrderObserved": True,
                                    "taskSnapshot": {
                                        "singleMainTask": True,
                                        "mainActivityInstances": 1,
                                    },
                                    "launchVisual": {
                                        "contractVerified": True,
                                        "sourceDigest": "d" * 64,
                                        "profile": "default",
                                    },
                                }
                            )
                        else:
                            sample.update(
                                {
                                    "sceneLaunchUsed": True,
                                    "sceneStarted": True,
                                    "sceneLauncher": (
                                        "xcrun_devicectl"
                                        if device_kind == "physical"
                                        else "xcrun_simctl"
                                    ),
                                }
                            )
                        samples.append(sample)
                    (target_root / f"{evidence_stem}.json").write_text(
                        json.dumps(
                            {
                                "schema": startup_matrix.RUNTIME_EVIDENCE_SCHEMA,
                                "baselineId": baseline_id,
                                "releaseId": release_id,
                                "releaseDigest": digest,
                                "runtimeEnv": environment,
                                "runtimeTarget": target,
                                "platform": platform,
                                "runs": len(samples),
                                "passed": True,
                                "specRefs": list(startup_matrix.SPEC_REFS),
                                "samples": samples,
                            }
                        ),
                        encoding="utf-8",
                    )
                    (target_root / f"{evidence_stem}.readback.json").write_text(
                        json.dumps(
                            {
                                "schema": startup_matrix.READBACK_EVIDENCE_SCHEMA,
                                "status": "passed",
                                "baselineId": baseline_id,
                                "releaseId": release_id,
                                "releaseDigest": digest,
                                "environment": environment,
                                "target": target,
                                "platform": platform,
                                "deviceId": device_id,
                                "deviceKind": (
                                    "physical"
                                    if device_kind in {
                                        "physical",
                                        "true_device",
                                    }
                                    else "simulator"
                                ),
                                "effectiveLaunchManifestDigest": digest,
                                "executed": 1,
                                "required": 1,
                                "skipped": 0,
                                "failed": 0,
                                "specRefs": list(startup_matrix.SPEC_REFS),
                                "caseResults": [
                                    {
                                        "caseId": "readback",
                                        "status": "passed",
                                        "testExecution": {
                                            "executed": 1,
                                            "skipped": 0,
                                            "failed": 0,
                                        },
                                    }
                                ],
                            }
                        ),
                        encoding="utf-8",
                    )
                (target_root / "observability.json").write_text(
                    json.dumps(
                        {
                            "schema": (
                                startup_matrix.OBSERVABILITY_EVIDENCE_SCHEMA
                            ),
                            "status": "passed",
                            "environment": environment,
                            "target": target,
                            "baselineId": baseline_id,
                            "releaseId": release_id,
                            "releaseDigest": digest,
                            "effectiveLaunchManifestDigest": digest,
                            "attemptIds": attempt_ids,
                            "deviceIds": device_ids,
                            "telemetryBackend": "product-ops-event-record",
                            "backendReceiptRef": f"{target}/telemetry.json",
                            "required": len(attempt_ids),
                            "executed": len(attempt_ids),
                            "skipped": 0,
                            "failed": 0,
                            "specRefs": list(startup_matrix.SPEC_REFS),
                        }
                    ),
                    encoding="utf-8",
                )

            argv = [
                "verify_startup_environment_matrix.py",
                "--evidence-root",
                str(root),
                "--require-runtime-evidence",
                "--require-readback",
                "--require-observability",
                "--require-physical-release",
                "--minimum-runtime-runs",
                "2",
                "--baseline-id",
                baseline_id,
                "--release-id",
                release_id,
                "--release-digest",
                digest,
                "--report",
                str(report_path),
            ]
            with (
                mock.patch.object(
                    startup_matrix.cli,
                    "_runtime_defines",
                    side_effect=environment_defines,
                ),
                mock.patch.object(
                    startup_matrix.cli,
                    "_ios_defines",
                    side_effect=environment_defines,
                ),
                mock.patch.object(startup_matrix.cli, "_launcher_handoff", side_effect=handoff),
                mock.patch.object(sys, "argv", argv),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(startup_matrix.main(), 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["required"], 30)
            self.assertEqual(report["executed"], 30)
            self.assertEqual(report["skipped"], 0)
            self.assertEqual(report["failed"], 0)

    def test_startup_matrix_status_distinguishes_component_and_release_evidence(
        self,
    ) -> None:
        component = {
            "caseId": "component:alpha",
            "required": True,
            "status": "component_ready",
        }
        self.assertEqual(
            _report_status([component], release_gate=False),
            "component_ready",
        )
        blocked = {
            "caseId": "startup:alpha-local/android",
            "required": True,
            "status": "gate_block",
        }
        self.assertEqual(
            _report_status([component, blocked], release_gate=True),
            "gate_block",
        )
        self.assertEqual(
            _case_counts([component, blocked]),
            {"required": 2, "executed": 1, "skipped": 0, "failed": 0},
        )

    def test_partial_release_evidence_request_is_gate_blocked(self) -> None:
        digest = "sha256:" + "e" * 64
        defines = {key: "value" for key in startup_matrix.REQUIRED_DEFINES}

        def environment_defines(environment: str) -> dict[str, str]:
            return {**defines, "APP_RUNTIME_ENV": environment}

        def handoff(environment: str, target: str | None = None) -> dict[str, str]:
            return {
                "target": target or startup_matrix.RUNTIME_TARGETS[environment],
                "entrypoint": "lib/main_prod.dart",
                "dartDefinesDigest": digest,
                "runtimeConfigDigest": digest,
                "effectiveLaunchManifestDigest": digest,
            }

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            argv = [
                "verify_startup_environment_matrix.py",
                "--evidence-root",
                str(Path(directory) / "evidence"),
                "--require-runtime-evidence",
                "--require-physical-release",
                "--baseline-id",
                "baseline-001",
                "--release-id",
                "release-001",
                "--release-digest",
                digest,
                "--report",
                str(report_path),
            ]
            with (
                mock.patch.object(
                    startup_matrix.cli,
                    "_runtime_defines",
                    side_effect=environment_defines,
                ),
                mock.patch.object(
                    startup_matrix.cli,
                    "_ios_defines",
                    side_effect=environment_defines,
                ),
                mock.patch.object(
                    startup_matrix.cli,
                    "_launcher_handoff",
                    side_effect=handoff,
                ),
                mock.patch.object(sys, "argv", argv),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(startup_matrix.main(), 2)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "gate_block")
            blocked_ids = {
                case["caseId"]
                for case in report["cases"]
                if case["status"] == "gate_block"
            }
            self.assertIn("matrix-policy:app-core-readback", blocked_ids)
            self.assertIn("matrix-policy:observability-readback", blocked_ids)

    def test_execution_input_requires_unique_real_candidate_cases(self) -> None:
        digest = "sha256:" + "b" * 64
        payload = {
            "schema": "qwq.startup-matrix-execution-input",
            "baselineId": "baseline-001",
            "releaseId": "release-001",
            "releaseDigest": digest,
            "cases": [
                {
                    "environment": "prod",
                    "target": "prod-hosted",
                    "platform": "ios",
                    "deviceId": "iphone-real-001",
                    "deviceKind": "physical",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "execution.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            cases = _load_execution_input(
                path,
                baseline_id="baseline-001",
                release_id="release-001",
                release_digest=digest,
            )
            self.assertEqual(cases[0]["deviceId"], "iphone-real-001")

            payload["cases"][0]["deviceKind"] = "simulator"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "physical device"):
                _load_execution_input(
                    path,
                    baseline_id="baseline-001",
                    release_id="release-001",
                    release_digest=digest,
                )

    def test_execution_preconditions_gate_block_missing_release_inputs(self) -> None:
        case = {
            "environment": "beta",
            "target": "beta-local",
            "platform": "android",
            "deviceId": "android-emulator-001",
            "deviceKind": "emulator",
            "install": False,
        }
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GATE_BLOCK"):
                _validate_execution_preconditions(case)

    def test_readback_evidence_requires_real_non_skipped_case_result(self) -> None:
        digest = "sha256:" + "c" * 64
        payload = {
            "schema": startup_matrix.READBACK_EVIDENCE_SCHEMA,
            "status": "passed",
            "baselineId": "baseline-001",
            "releaseId": "release-001",
            "releaseDigest": digest,
            "environment": "gamma",
            "target": "gamma-local",
            "platform": "android",
            "deviceId": "android-real-001",
            "effectiveLaunchManifestDigest": digest,
            "required": 1,
            "executed": 1,
            "skipped": 0,
            "failed": 0,
            "specRefs": list(startup_matrix.SPEC_REFS),
            "caseResults": [
                {
                    "caseId": "readback",
                    "status": "passed",
                    "testExecution": {
                        "executed": 1,
                        "skipped": 0,
                        "failed": 0,
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "android.readback.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_readback_evidence(
                path,
                expected_environment="gamma",
                expected_target="gamma-local",
                expected_platform="android",
                expected_effective_manifest_digest=digest,
                expected_baseline_id="baseline-001",
                expected_release_id="release-001",
                expected_release_digest=digest,
            )
            self.assertEqual(issues, [])

            payload["executed"] = 0
            payload["skipped"] = 1
            path.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_readback_evidence(
                path,
                expected_environment="gamma",
                expected_target="gamma-local",
                expected_platform="android",
                expected_effective_manifest_digest=digest,
                expected_baseline_id="baseline-001",
                expected_release_id="release-001",
                expected_release_digest=digest,
            )
            self.assertTrue(any("executed" in issue for issue in issues))
            self.assertTrue(any("skipped" in issue for issue in issues))

    def test_observability_readback_binds_attempt_device_and_candidate(self) -> None:
        digest = "sha256:" + "f" * 64
        payload = {
            "schema": startup_matrix.OBSERVABILITY_EVIDENCE_SCHEMA,
            "status": "passed",
            "environment": "beta",
            "target": "beta-local",
            "baselineId": "baseline-001",
            "releaseId": "release-001",
            "releaseDigest": digest,
            "effectiveLaunchManifestDigest": digest,
            "attemptIds": ["attempt-beta-01", "attempt-beta-02"],
            "deviceIds": ["emulator-5554", "android-real-001"],
            "telemetryBackend": "product-ops-event-record",
            "backendReceiptRef": "beta/telemetry-readback.json",
            "required": 2,
            "executed": 2,
            "skipped": 0,
            "failed": 0,
            "specRefs": list(startup_matrix.SPEC_REFS),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observability.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_observability_evidence(
                path,
                expected_environment="beta",
                expected_target="beta-local",
                expected_effective_manifest_digest=digest,
                expected_baseline_id="baseline-001",
                expected_release_id="release-001",
                expected_release_digest=digest,
                expected_attempt_ids=["attempt-beta-01", "attempt-beta-02"],
                expected_device_ids=["emulator-5554", "android-real-001"],
            )
            self.assertEqual(issues, [])

            payload["attemptIds"][1] = "unknown"
            payload["backendReceiptRef"] = ""
            path.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_observability_evidence(
                path,
                expected_environment="beta",
                expected_target="beta-local",
                expected_effective_manifest_digest=digest,
                expected_baseline_id="baseline-001",
                expected_release_id="release-001",
                expected_release_digest=digest,
                expected_attempt_ids=["attempt-beta-01", "attempt-beta-02"],
                expected_device_ids=["emulator-5554", "android-real-001"],
            )
            self.assertTrue(any("attemptIds" in issue for issue in issues))
            self.assertTrue(any("backendReceiptRef" in issue for issue in issues))

    def test_required_startup_uat_has_no_dynamic_skip_and_make_is_candidate_bound(
        self,
    ) -> None:
        web_uat = (
            APP_DIR
            / "test/user_acceptance/journeys/app_startup/"
            "startup_web_3s_6s_report__user_acceptance_test.dart"
        ).read_text(encoding="utf-8")
        self.assertNotIn("skip:", web_uat)

        makefile = (APP_DIR.parent / "Makefile").read_text(encoding="utf-8")
        for target in (
            "verify-app-startup-environment-uat:",
            "verify-app-startup-observability-release:",
        ):
            start = makefile.index(target)
            next_target = makefile.find("\nverify-", start + len(target))
            block = makefile[start : next_target if next_target >= 0 else None]
            for token in (
                "GATE_BLOCK: STARTUP_EVIDENCE_ROOT is required",
                "GATE_BLOCK: STARTUP_BASELINE_ID is required",
                "GATE_BLOCK: STARTUP_RELEASE_ID is required",
                "GATE_BLOCK: STARTUP_RELEASE_DIGEST is required",
                "--require-runtime-evidence",
                "--require-readback",
                "--require-observability",
                "--require-physical-release",
                '--baseline-id "$(STARTUP_BASELINE_ID)"',
                '--release-id "$(STARTUP_RELEASE_ID)"',
                '--release-digest "$(STARTUP_RELEASE_DIGEST)"',
            ):
                self.assertIn(token, block, msg=f"{target} missing {token}")

    def test_runtime_matrix_requires_each_of_twenty_real_samples(self) -> None:
        digest = "sha256:" + "a" * 64
        sample = {
            "runtimeEnv": "prod",
            "runtimeTarget": "prod-hosted",
            "platform": "ios",
            "passed": True,
            "attemptId": "attempt_real_01",
            "rendererFirstFrameMs": 900,
            "safeTerminalMs": 1200,
            "reportedSafeTerminalMs": 1190,
            "nativeReceivedSafeTerminalMs": 1210,
            "watchdogOutcome": "safe_terminal",
            "canonicalTerminal": "routerShell",
            "launchMode": "release_package",
            "runtimeConfigurationState": "complete",
            "missingDefineKeys": "",
            "failureCode": "",
            "startupSequenceMotionCurrent": True,
            "effectiveLaunchManifestDigest": digest,
            "telemetryAcknowledged": True,
            "sceneLaunchUsed": True,
            "sceneStarted": True,
            "sceneLauncher": "xcrun_devicectl",
        }
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "ios.json"
            report.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "samples": [
                            {
                                **sample,
                                "attemptId": f"attempt_real_{index:02d}",
                            }
                            for index in range(20)
                        ],
                    }
                ),
                encoding="utf-8",
            )
            issues, _ = _validate_runtime_evidence(
                report,
                expected_environment="prod",
                expected_target="prod-hosted",
                expected_platform="ios",
                expected_effective_manifest_digest=digest,
                minimum_runs=20,
            )
            self.assertEqual(issues, [])

            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["samples"][7]["attemptId"] = "unknown"
            report.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_runtime_evidence(
                report,
                expected_environment="prod",
                expected_target="prod-hosted",
                expected_platform="ios",
                expected_effective_manifest_digest=digest,
                minimum_runs=20,
            )
            self.assertTrue(any("attemptId missing" in issue for issue in issues))

            payload["samples"][7]["attemptId"] = "attempt_real_07"
            payload["samples"][7]["sceneStarted"] = False
            report.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_runtime_evidence(
                report,
                expected_environment="prod",
                expected_target="prod-hosted",
                expected_platform="ios",
                expected_effective_manifest_digest=digest,
                minimum_runs=20,
            )
            self.assertTrue(any("iOS scene did not start" in issue for issue in issues))

    def test_effective_launch_manifest_digest_is_order_independent(self) -> None:
        left = {"schema": "app-effective-launch-manifest", "target": "prod-hosted"}
        right = {"target": "prod-hosted", "schema": "app-effective-launch-manifest"}
        self.assertEqual(
            effective_launch_manifest_digest(left),
            effective_launch_manifest_digest(right),
        )

    def test_launcher_handoff_validates_target_runner_and_digests(self) -> None:
        defines = {
            "APP_RUNTIME_ENV": "prod",
            "CLOUD_GATEWAY_BASE_URL": "https://api.quwoquan.com",
            "APP_LEGAL_BASE_URL": "https://quwoquan.com/legal",
            "PUBLIC_WEB_BASE_URL": "https://quwoquan.com",
            "MEDIA_AVATAR_CDN_BASE_URL": "https://cdn.quwoquan.com",
            "MEDIA_IMAGE_CDN_BASE_URL": "https://cdn.quwoquan.com",
            "MEDIA_VIDEO_CDN_BASE_URL": "https://cdn.quwoquan.com",
            "MEDIA_UPLOAD_BASE_URL": "https://upload.quwoquan.com",
            "RTC_MEDIA_CONNECTION_URL": "wss://rtc.quwoquan.com",
        }
        self.assertEqual(
            validate_flutter_run_defines(
                defines,
                expected_env="prod",
                target="prod-sim",
                entrypoint="lib/main_prod.dart",
                defines_digest=dart_defines_digest(defines),
                runtime_config_digest=fixture_runtime_config_digest(
                    "prod",
                    "prod-sim",
                ),
            ),
            [],
        )
        self.assertIn(
            "target alpha-local requires APP_RUNTIME_ENV=alpha",
            validate_flutter_run_defines(defines, target="alpha-local"),
        )
        alpha_defines = {**defines, "APP_RUNTIME_ENV": "alpha"}
        self.assertEqual(
            validate_flutter_run_defines(
                alpha_defines,
                expected_env="alpha",
                target="alpha-local",
                entrypoint="lib/main_prod.dart",
                defines_digest=dart_defines_digest(alpha_defines),
                runtime_config_digest=fixture_runtime_config_digest(
                    "alpha",
                    "alpha-local",
                ),
            ),
            [],
        )

    def test_launcher_handoff_validates_local_transport_receipts(self) -> None:
        defines = {
            "APP_RUNTIME_ENV": "beta",
            "CLOUD_GATEWAY_BASE_URL": "https://api.example.test",
            "APP_LEGAL_BASE_URL": "https://legal.example.test",
            "PUBLIC_WEB_BASE_URL": "https://web.example.test",
            "MEDIA_AVATAR_CDN_BASE_URL": "https://cdn.example.test",
            "MEDIA_IMAGE_CDN_BASE_URL": "https://cdn.example.test",
            "MEDIA_VIDEO_CDN_BASE_URL": "https://cdn.example.test",
            "MEDIA_UPLOAD_BASE_URL": "https://upload.example.test",
            "RTC_MEDIA_CONNECTION_URL": "wss://rtc.example.test",
        }
        digest = "sha256:" + "a" * 64
        self.assertEqual(
            validate_flutter_run_defines(
                defines,
                expected_env="beta",
                target="beta-local",
                entrypoint="lib/main_prod.dart",
                transport_required=True,
                reverse_expected_ports="7443,7444",
                reverse_actual_ports="7444,7443",
                reverse_receipt_digest=digest,
                consumer_lease_id=digest,
            ),
            [],
        )
        self.assertIn(
            "Android reverse expected/actual ports do not match",
            validate_flutter_run_defines(
                defines,
                target="beta-local",
                entrypoint="lib/main_prod.dart",
                transport_required=True,
                reverse_expected_ports="7443",
                reverse_actual_ports="7444",
                reverse_receipt_digest=digest,
                consumer_lease_id=digest,
            ),
        )

    def test_ttid_ratchet_default_mode_is_structural_and_self_compare_is_blocked(
        self,
    ) -> None:
        ratchet = APP_DIR.parent / "quwoquan_ops/policies/gates/startup_ttid_ratchet_baseline.json"
        with mock.patch.object(sys, "argv", ["verify_startup_ttid_baseline.py"]):
            self.assertEqual(verify_startup_ttid_main(), 0)
        with mock.patch.object(
            sys,
            "argv",
            [
                "verify_startup_ttid_baseline.py",
                "--baseline",
                str(ratchet),
                "--ratchet",
                str(ratchet),
            ],
        ):
            self.assertEqual(verify_startup_ttid_main(), 1)

    def test_parses_terminal_and_shell_events(self) -> None:
        raw = """
QWQStartup: startup_welcome_sequence phase=finished motionSpec=petal_bloom replayCount=1 exitReason=ready_replay welcomeExitMs=2410
I/QWQStartup: startup_probe phase=finished welcomeExitMs=2410 exitReason=ready_replay
QWQStartup: startup_welcome_sequence phase=main_shell_first_paint shellFirstPaintMs=2530
QWQStartup: startup_welcome_sequence phase=welcome_overlay_removed overlayRemovedMs=2650
"""
        parsed = parse_startup_sequence_log(raw)
        self.assertEqual(parsed["welcomeExitMs"], 2410)
        self.assertEqual(parsed["exitReason"], "ready_replay")
        self.assertEqual(parsed["replayCount"], 1)
        self.assertEqual(parsed["shellFirstPaintMs"], 2530)
        self.assertEqual(parsed["overlayRemovedMs"], 2650)
        self.assertEqual(parsed["motionSpec"], "petal_bloom")
        self.assertEqual(classify_startup_terminal(raw, parsed), "routerShell")

    def test_classifies_safe_and_native_recovery_terminal_surfaces(self) -> None:
        safe_raw = """
QWQStartup: startup_welcome_sequence phase=safe_recovery_shown result=failed
"""
        safe_sequence = parse_startup_sequence_log(safe_raw)
        self.assertEqual(
            classify_startup_terminal(safe_raw, safe_sequence),
            "safeRecovery",
        )

        native_raw = "QWQStartup: ios_native_first_frame_timeout elapsedMs=6000"
        self.assertEqual(
            classify_startup_terminal(
                native_raw,
                parse_startup_sequence_log(native_raw),
            ),
            "nativeRecovery",
        )
        safe_terminal_slow_raw = (
            "QWQStartup android_startup_safe_terminal_slow elapsedMs=6000"
        )
        self.assertEqual(
            classify_startup_terminal(
                safe_terminal_slow_raw,
                parse_startup_sequence_log(safe_terminal_slow_raw),
            ),
            "unresolved",
        )
        flutter_visible_slow_raw = """
QWQStartup android_startup_safe_terminal_slow elapsedMs=6001
QWQStartup android_startup_safe_terminal elapsedMs=6004
QWQStartup: startup_probe phase=finished welcomeExitMs=2410 exitReason=ready_primary
QWQStartup: startup_probe phase=main_shell_first_paint shellFirstPaintMs=2530
QWQStartup: startup_probe phase=welcome_overlay_removed overlayRemovedMs=2650
"""
        self.assertEqual(
            classify_startup_terminal(
                flutter_visible_slow_raw,
                parse_startup_sequence_log(flutter_visible_slow_raw),
            ),
            "routerShell",
        )

    def test_rejects_unresolved_static_native_terminal(self) -> None:
        raw = "QWQStartup: ios_did_finish_launching"
        self.assertEqual(
            classify_startup_terminal(raw, parse_startup_sequence_log(raw)),
            "unresolved",
        )

    def test_parses_native_json_event_bridge(self) -> None:
        raw = """
I/QWQStartup: startup_event {"eventName":"startup_welcome_sequence","phase":"finished","motionSpec":"petal_bloom","welcomeExitMs":1710,"exitReason":"ready_primary","replayCount":0}
I/QWQStartup: startup_event {"eventName":"startup_welcome_sequence","phase":"main_shell_first_paint","shellFirstPaintMs":1770}
I/QWQStartup: startup_event {"eventName":"startup_welcome_sequence","phase":"welcome_overlay_removed","overlayRemovedMs":1890}
"""
        parsed = parse_startup_sequence_log(raw)
        self.assertEqual(parsed["welcomeExitMs"], 1710)
        self.assertEqual(parsed["exitReason"], "ready_primary")
        self.assertEqual(parsed["shellFirstPaintMs"], 1770)
        self.assertEqual(parsed["overlayRemovedMs"], 1890)
        self.assertEqual(parsed["motionSpec"], "petal_bloom")

    def test_extracts_renderer_watchdog_and_canonical_terminal_evidence(self) -> None:
        raw = """
I/QWQStartup: android_flutter_first_frame elapsedMs=1210 source=renderer
I/QWQStartup: android_startup_safe_terminal elapsedMs=1450
I/QWQStartup: startup_event {"attemptId":"attempt_123"}
"""
        evidence = extract_startup_watchdog_evidence(raw)
        self.assertEqual(evidence["rendererFirstFrameMs"], 1210)
        self.assertEqual(evidence["safeTerminalMs"], 1450)
        self.assertEqual(evidence["watchdogOutcome"], "not_triggered")
        self.assertEqual(evidence["attemptId"], "attempt_123")

    def test_extracts_native_attempt_id_from_structured_log_suffix(self) -> None:
        digest = "sha256:" + "a" * 64
        raw = f"""
I/QWQStartup: ios_dart_startup_attempt attemptId=attempt_ios_1 launchMode=canonical_launcher hotRestart=false configurationState=complete effectiveLaunchManifestDigest={digest}
I/QWQStartup: ios_flutter_first_frame elapsedMs=980 source=renderer attemptId=attempt_ios_1
I/QWQStartup: ios_startup_safe_terminal reportedElapsedMs=1220 receivedMs=1240 attemptId=attempt_ios_1
I/QWQStartup: startup_telemetry_ack attemptId=attempt_ios_1 acceptedCount=4 duplicateCount=0
"""
        evidence = extract_startup_watchdog_evidence(raw)
        self.assertEqual(evidence["attemptId"], "attempt_ios_1")
        self.assertEqual(evidence["rendererFirstFrameMs"], 980)
        self.assertEqual(evidence["safeTerminalMs"], 1220)
        self.assertEqual(evidence["reportedSafeTerminalMs"], 1220)
        self.assertEqual(evidence["nativeReceivedSafeTerminalMs"], 1240)
        self.assertEqual(evidence["launchMode"], "canonical_launcher")
        self.assertFalse(evidence["hotRestart"])
        self.assertEqual(evidence["runtimeConfigurationState"], "complete")
        self.assertEqual(evidence["effectiveLaunchManifestDigest"], digest)
        self.assertEqual(evidence["failureCode"], "")
        self.assertTrue(evidence["telemetryAcknowledged"])

        failure_evidence = extract_startup_watchdog_evidence(
            "QWQStartup ios_startup_bootstrap_failure "
            "attemptId=attempt_ios_1 launchMode=canonical_launcher "
            "failureCode=OPS.SYSTEM.startup_configuration_invalid"
        )
        self.assertEqual(
            failure_evidence["failureCode"],
            "OPS.SYSTEM.startup_configuration_invalid",
        )

    def test_parses_native_terminal_probe_without_animation_detail(self) -> None:
        raw = """
I/QWQStartup: startup_probe phase=finished welcomeExitMs=1710 exitReason=ready_primary
I/QWQStartup: startup_probe phase=main_shell_first_paint shellFirstPaintMs=1770
I/QWQStartup: startup_probe phase=welcome_overlay_removed overlayRemovedMs=1890
"""
        parsed = parse_startup_sequence_log(raw)
        self.assertEqual(parsed["welcomeExitMs"], 1710)
        self.assertEqual(parsed["exitReason"], "ready_primary")
        self.assertIsNone(parsed["motionSpec"])
        self.assertEqual(parsed["shellFirstPaintMs"], 1770)
        self.assertEqual(parsed["overlayRemovedMs"], 1890)
        self.assertEqual(classify_startup_terminal(raw, parsed), "routerShell")

    def test_default_probe_samples_three_and_six_second_boundaries(self) -> None:
        args = build_arg_parser().parse_args([])
        self.assertIn(3000, args.android_offsets_ms)
        self.assertIn(6000, args.android_offsets_ms)
        self.assertIn(3000, args.ios_offsets_ms)
        self.assertIn(6000, args.ios_offsets_ms)
        self.assertEqual(args.shell_first_paint_target_ms, 3000)
        self.assertEqual(args.welcome_exit_hard_ms, 6000)
        self.assertEqual(args.android_blue_transition_budget_ms, 2000)
        self.assertFalse(args.require_no_native_recovery)

    def test_android_probe_uses_launcher_resolution_and_single_main_task(self) -> None:
        resolution = parse_android_launcher_resolution(
            "com.quwoquan.quwoquan_app/.StartupGateActivity\n",
            package="com.quwoquan.quwoquan_app",
            expected_activity="com.quwoquan.quwoquan_app/.StartupGateActivity",
        )
        self.assertTrue(resolution["matchesExpectedGate"])

        task = parse_android_task_snapshot(
            """
          Hist #0: ActivityRecord{abc123 u0 com.quwoquan.quwoquan_app/.MainActivity t42}
            """,
            package="com.quwoquan.quwoquan_app",
            main_activity="com.quwoquan.quwoquan_app/.MainActivity",
        )
        self.assertEqual(task["mainActivityInstances"], 1)
        self.assertTrue(task["singleMainTask"])
        self.assertTrue(
            android_gate_main_order_observed(
                """
QWQStartup android_gate_static_frame_drawn
QWQStartup android_gate_window_focus_confirmed
QWQStartup android_gate_window_focus_released
QWQStartup android_gate_main_handoff
QWQStartup android_activity_on_create elapsedMs=300
                """
            )
        )
        self.assertFalse(
            android_gate_main_order_observed(
                """
QWQStartup android_activity_on_create elapsedMs=300
QWQStartup android_gate_main_handoff
                """
            )
        )

    def test_android_fresh_log_requires_one_focus_handoff_attempt(self) -> None:
        draw_then_focus = """
QWQStartup android_gate_static_frame_drawn
QWQStartup android_gate_window_focus_confirmed
QWQStartup android_gate_window_focus_released
QWQStartup android_gate_main_handoff
QWQStartup android_activity_on_create elapsedMs=300
"""
        focus_then_draw = """
QWQStartup android_gate_window_focus_confirmed
QWQStartup android_gate_static_frame_draw_timeout
QWQStartup android_gate_window_focus_released
QWQStartup android_gate_main_handoff
QWQStartup android_activity_on_create elapsedMs=300
"""
        for current in (draw_then_focus, focus_then_draw):
            with self.subTest(current=current):
                evidence = android_fresh_startup_log_evidence(
                    baseline="",
                    current=current,
                    package="com.quwoquan.quwoquan_app",
                )
                self.assertTrue(evidence["startupAttemptLogUnique"])
                self.assertTrue(evidence["gateMainOrderObserved"])
                self.assertTrue(evidence["passed"])

        invalid_logs = {
            "missing_focus": """
QWQStartup android_gate_static_frame_drawn
QWQStartup android_gate_main_handoff
QWQStartup android_activity_on_create elapsedMs=300
""",
            "missing_focus_release": """
QWQStartup android_gate_static_frame_drawn
QWQStartup android_gate_window_focus_confirmed
QWQStartup android_gate_main_handoff
QWQStartup android_activity_on_create elapsedMs=300
""",
            "focus_after_handoff": """
QWQStartup android_gate_static_frame_drawn
QWQStartup android_gate_main_handoff
QWQStartup android_gate_window_focus_confirmed
QWQStartup android_gate_window_focus_released
QWQStartup android_activity_on_create elapsedMs=300
""",
            "focus_release_after_handoff": """
QWQStartup android_gate_static_frame_drawn
QWQStartup android_gate_window_focus_confirmed
QWQStartup android_gate_main_handoff
QWQStartup android_gate_window_focus_released
QWQStartup android_activity_on_create elapsedMs=300
""",
            "duplicate_focus": """
QWQStartup android_gate_static_frame_drawn
QWQStartup android_gate_window_focus_confirmed
QWQStartup android_gate_window_focus_confirmed
QWQStartup android_gate_window_focus_released
QWQStartup android_gate_main_handoff
QWQStartup android_activity_on_create elapsedMs=300
""",
            "duplicate_main": """
QWQStartup android_gate_static_frame_drawn
QWQStartup android_gate_window_focus_confirmed
QWQStartup android_gate_window_focus_released
QWQStartup android_gate_main_handoff
QWQStartup android_activity_on_create elapsedMs=300
QWQStartup android_activity_on_create elapsedMs=400
""",
        }
        for name, current in invalid_logs.items():
            with self.subTest(name=name):
                evidence = android_fresh_startup_log_evidence(
                    baseline="",
                    current=current,
                    package="com.quwoquan.quwoquan_app",
                )
                self.assertFalse(evidence["gateMainOrderObserved"])
                self.assertFalse(evidence["passed"])

    def test_android_fresh_log_rejects_only_current_package_anr(self) -> None:
        package = "com.quwoquan.quwoquan_app"
        old_anr = (
            "08-09 20:00:00.000 E ActivityManager: "
            f"ANR in {package}\n"
        )
        clean_attempt = """
QWQStartup android_gate_static_frame_drawn
QWQStartup android_gate_window_focus_confirmed
QWQStartup android_gate_window_focus_released
QWQStartup android_gate_main_handoff
QWQStartup android_activity_on_create elapsedMs=300
08-09 21:00:00.000 I am_anr : [0,12,com.example.other,reason]
08-09 21:00:00.001 E ActivityManager: ANR in com.quwoquan.quwoquan_app.preview
08-09 21:00:00.002 W InputDispatcher: Input dispatching timed out com.example.other
"""
        clean = android_fresh_startup_log_evidence(
            baseline=old_anr,
            current=old_anr + clean_attempt,
            package=package,
        )
        self.assertTrue(clean["baselineApplied"])
        self.assertFalse(clean["androidAnrDetected"])
        self.assertTrue(clean["passed"])

        current_anr_lines = {
            "am_anr": f"I am_anr : [0,16516,{package},reason]",
            "anr_in_package": f"E ActivityManager: ANR in {package}",
            "input_dispatch_timeout": (
                "W InputDispatcher: Input dispatching timed out "
                f"({package}/.StartupGateActivity)"
            ),
        }
        for expected_signal, line in current_anr_lines.items():
            with self.subTest(signal=expected_signal):
                evidence = android_fresh_startup_log_evidence(
                    baseline=old_anr,
                    current=old_anr + clean_attempt + line + "\n",
                    package=package,
                )
                self.assertTrue(evidence["baselineApplied"])
                self.assertTrue(evidence["androidAnrDetected"])
                self.assertIn(expected_signal, evidence["androidAnrSignals"])
                self.assertFalse(evidence["passed"])

    def test_android_fresh_log_fails_closed_when_baseline_is_not_prefix(self) -> None:
        evidence = android_fresh_startup_log_evidence(
            baseline="old log line\n",
            current="""
QWQStartup android_gate_static_frame_drawn
QWQStartup android_gate_window_focus_confirmed
QWQStartup android_gate_window_focus_released
QWQStartup android_gate_main_handoff
QWQStartup android_activity_on_create elapsedMs=300
""",
            package="com.quwoquan.quwoquan_app",
        )
        self.assertFalse(evidence["baselineApplied"])
        self.assertTrue(evidence["gateMainOrderObserved"])
        self.assertFalse(evidence["passed"])

    def test_android_launch_visual_provenance_is_profile_specific(self) -> None:
        provenance = native_launch_visual_provenance("sw393dp")
        self.assertTrue(provenance["contractVerified"])
        self.assertEqual(provenance["profile"], "sw393dp")
        self.assertEqual(len(provenance["sourceDigest"]), 64)
        self.assertFalse(provenance["missingFiles"])

    def test_android_system_splash_icon_is_not_counted_as_branded_welcome(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png") as screenshot:
            image = Image.new("RGB", (100, 100), (7, 93, 231))
            ImageDraw.Draw(image).rectangle((28, 28, 70, 70), fill=(255, 255, 255))
            image.save(screenshot.name)
            analysis = analyze_screenshot(Path(screenshot.name), offset_ms=400)

        self.assertGreaterEqual(analysis.foreground_ratio, 0.25)
        self.assertTrue(analysis.system_splash_icon)
        self.assertFalse(analysis.branded_or_content_visible)
        self.assertTrue(analysis.blue_background)

    def test_probe_fails_prolonged_system_blue_repeated_splash_and_petal_mismatch(
        self,
    ) -> None:
        blue = ScreenshotAnalysis(
            path="blue.png",
            offset_ms=1200,
            foreground_ratio=0.0,
            stddev_avg=1.0,
            median_rgb=(7, 93, 231),
            plain_background=False,
            blue_background=True,
            branded_or_content_visible=False,
        )
        branded = ScreenshotAnalysis(
            path="branded.png",
            offset_ms=1600,
            foreground_ratio=0.4,
            stddev_avg=40.0,
            median_rgb=(120, 140, 200),
            plain_background=False,
            blue_background=False,
            branded_or_content_visible=True,
        )
        blue_again = ScreenshotAnalysis(
            path="blue-again.png",
            offset_ms=2200,
            foreground_ratio=0.0,
            stddev_avg=1.0,
            median_rgb=(7, 93, 231),
            plain_background=False,
            blue_background=True,
            branded_or_content_visible=False,
        )
        self.assertTrue(
            detect_prolonged_system_blue([blue], transition_budget_ms=1000)
        )
        self.assertFalse(
            detect_prolonged_system_blue(
                [
                    ScreenshotAnalysis(
                        path="early-blue.png",
                        offset_ms=400,
                        foreground_ratio=0.0,
                        stddev_avg=1.0,
                        median_rgb=(7, 93, 231),
                        plain_background=False,
                        blue_background=True,
                        branded_or_content_visible=False,
                    ),
                    branded,
                ],
                transition_budget_ms=1000,
            )
        )
        self.assertTrue(
            detect_repeated_splash(
                [branded, blue_again],
                "QWQStartup android_gate_static_frame_drawn",
            )
        )
        self.assertTrue(
            detect_repeated_splash(
                [branded],
                "android_gate_static_frame_drawn\nandroid_gate_static_frame_drawn",
            )
        )
        self.assertTrue(
            detect_native_static_petal_mismatch(
                [blue],
                compare_after_ms=1000,
            )
        )
        self.assertFalse(
            detect_native_static_petal_mismatch(
                [branded],
                compare_after_ms=1000,
            )
        )
        self.assertFalse(
            detect_native_static_petal_mismatch(
                [blue],
                compare_after_ms=1000,
                safe_terminal_reached=True,
            )
        )

    def test_commercial_gate_rejects_simulator_or_fewer_than_twenty_runs(self) -> None:
        sample = {
            "welcomeExitMs": 2800,
            "exitReason": "ready_primary",
        }
        baseline = {
            "deviceKind": "true_device",
            "samples": [dict(sample) for _ in range(20)],
            "p95": {"firstVisibleMs": 900, "shellFirstPaintMs": 2600},
        }
        self.assertEqual(validate_commercial_uat(baseline), [])

        baseline["samples"] = baseline["samples"][:19]
        self.assertIn("at least 20 samples", validate_commercial_uat(baseline)[0])
        baseline["samples"] = [dict(sample) for _ in range(20)]
        baseline["deviceKind"] = "simulator"
        self.assertTrue(
            any("true_device" in error for error in validate_commercial_uat(baseline))
        )

    def test_web_probe_parses_embedded_report_and_defaults_to_twenty_runs(self) -> None:
        import base64
        import json

        events = [
            {
                "eventName": "startup_welcome_sequence",
                "phase": "finished",
                "motionSpec": "petal_bloom",
                "welcomeExitMs": 2100,
                "exitReason": "ready_primary",
            },
            {
                "eventName": "startup_welcome_sequence",
                "phase": "main_shell_first_paint",
                "shellFirstPaintMs": 2220,
            },
            {
                "eventName": "startup_welcome_sequence",
                "phase": "welcome_overlay_removed",
                "overlayRemovedMs": 2340,
            },
        ]
        encoded = base64.b64encode(json.dumps(events).encode()).decode()
        parsed = parse_startup_report(
            f'<html data-qwq-startup-report="{encoded}"></html>'
        )
        self.assertEqual(terminal_event(parsed)["welcomeExitMs"], 2100)
        self.assertEqual(shell_event(parsed)["shellFirstPaintMs"], 2220)
        self.assertEqual(overlay_removed_event(parsed)["overlayRemovedMs"], 2340)
        parsed.append(
            {
                "eventName": "startup_safe_terminal",
                "attemptId": "web_attempt_1",
                "elapsedMs": 2400,
            }
        )
        self.assertEqual(
            startup_event(parsed, "startup_safe_terminal")["attemptId"],
            "web_attempt_1",
        )
        self.assertEqual(
            build_web_arg_parser().parse_args(["--url", "http://localhost"]).runs,
            20,
        )


if __name__ == "__main__":
    unittest.main()

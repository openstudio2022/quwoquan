import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))
sys.path.insert(0, str(APP_DIR / "scripts/runtime"))

from verify_startup_first_frame import (
    ScreenshotAnalysis,
    analyze_screenshot,
    build_arg_parser,
    classify_startup_terminal,
    detect_native_static_petal_mismatch,
    detect_prolonged_system_blue,
    detect_repeated_splash,
    extract_startup_watchdog_evidence,
    inspect_android_local_ca,
    native_launch_visual_provenance,
    android_gate_main_order_observed,
    parse_android_launcher_resolution,
    parse_android_task_snapshot,
    parse_startup_sequence_log,
)
from build_launcher_handoff import (
    dart_defines_digest,
    effective_launch_manifest_digest,
    runtime_config_digest,
)
from verify_flutter_run_defines import validate_flutter_run_defines
from verify_startup_ttid_baseline import main as verify_startup_ttid_main
from verify_startup_ttid_baseline import validate_commercial_uat
from verify_startup_environment_matrix import _validate_runtime_evidence
from verify_startup_web import (
    build_arg_parser as build_web_arg_parser,
    overlay_removed_event,
    parse_startup_report,
    shell_event,
    startup_event,
    terminal_event,
)


class StartupProbeParserContractTest(unittest.TestCase):
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

    def test_effective_launch_manifest_digest_is_order_independent(self) -> None:
        left = {"schema": "app-effective-launch-manifest-v1", "target": "prod-hosted"}
        right = {"target": "prod-hosted", "schema": "app-effective-launch-manifest-v1"}
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
                runtime_config_digest=runtime_config_digest("prod"),
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
                runtime_config_digest=runtime_config_digest("alpha"),
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

    def test_reports_missing_and_placeholder_android_debug_ca(self) -> None:
        missing = inspect_android_local_ca("/definitely/not/a/certificate.pem")
        self.assertEqual(missing["state"], "missing")

        with tempfile.NamedTemporaryFile() as ca:
            ca.write(b"quwoquan-local-debug-placeholder")
            ca.flush()
            placeholder = inspect_android_local_ca(ca.name)
        self.assertEqual(placeholder["state"], "placeholder")

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

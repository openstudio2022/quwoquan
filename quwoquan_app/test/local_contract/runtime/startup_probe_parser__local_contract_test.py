# spec_ref: specs/feature-tree/spec.md#uat-003
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
#
# 由 1000 行硬顶拆分：本文件保留启动日志/事件解析、terminal 分类、probe 默认
# 采样与 Web 启动报告解析场景组；环境矩阵汇总组见
# startup_probe_parser__environment_matrix__local_contract_test.py；矩阵证据
# 校验组见 startup_probe_parser__matrix_evidence__local_contract_test.py；
# launcher handoff 与 TTID 门组见
# startup_probe_parser__launcher_handoff__local_contract_test.py；Android 探针
# 与截图分析组见 startup_probe_parser__android_probe__local_contract_test.py。

import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))
sys.path.insert(0, str(APP_DIR / "scripts/runtime/platform"))
sys.path.insert(0, str(APP_DIR / "test/support/runtime/launcher"))

from verify_startup_first_frame import (
    build_arg_parser,
    classify_startup_terminal,
    extract_startup_watchdog_evidence,
    parse_startup_sequence_log,
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
QWQStartup android_startup_safe_terminal surface=router_shell elapsedMs=6004
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
I/QWQStartup: android_startup_safe_terminal surface=router_shell elapsedMs=1450
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
I/QWQStartup: ios_dart_startup_attempt attemptId=attempt_ios_1 launchProvenance=canonical_launcher runtimeConfigSupplyMode=external_runtime_package hotRestart=false configurationState=complete effectiveLaunchManifestDigest={digest}
I/QWQStartup: ios_flutter_first_frame elapsedMs=980 source=renderer attemptId=attempt_ios_1
I/QWQStartup: ios_startup_safe_terminal surface=router_shell reportedElapsedMs=1220 receivedMs=1240 attemptId=attempt_ios_1
I/QWQStartup: startup_telemetry_ack attemptId=attempt_ios_1 acceptedCount=4 duplicateCount=0
"""
        evidence = extract_startup_watchdog_evidence(raw)
        self.assertEqual(evidence["attemptId"], "attempt_ios_1")
        self.assertEqual(evidence["rendererFirstFrameMs"], 980)
        self.assertEqual(evidence["safeTerminalMs"], 1220)
        self.assertEqual(evidence["reportedSafeTerminalMs"], 1220)
        self.assertEqual(evidence["nativeReceivedSafeTerminalMs"], 1240)
        self.assertEqual(evidence["launchProvenance"], "canonical_launcher")
        self.assertEqual(
            evidence["runtimeConfigSupplyMode"], "external_runtime_package"
        )
        self.assertFalse(evidence["hotRestart"])
        self.assertEqual(evidence["runtimeConfigurationState"], "complete")
        self.assertEqual(evidence["effectiveLaunchManifestDigest"], digest)
        self.assertEqual(evidence["failureCode"], "")
        self.assertTrue(evidence["telemetryAcknowledged"])

        failure_evidence = extract_startup_watchdog_evidence(
            "QWQStartup ios_startup_bootstrap_failure "
            "attemptId=attempt_ios_1 launchProvenance=canonical_launcher "
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

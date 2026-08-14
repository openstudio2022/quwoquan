# spec_ref: specs/feature-tree/spec.md#uat-003
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
#
# 由 1000 行硬顶从 startup_probe_parser__local_contract_test.py 拆出：
# 本文件承接 Android 探针与截图分析场景组（launcher resolution 与单 main
# task、fresh log focus/handoff 顺序、当前包 ANR 判定、baseline 前缀
# fail-closed、launch visual provenance、系统 splash 图标识别、蓝屏/重复
# splash/petal 失配检测）；测试逐字搬移。

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))
sys.path.insert(0, str(APP_DIR / "scripts/runtime/platform"))
sys.path.insert(0, str(APP_DIR / "test/support/runtime/launcher"))

from verify_startup_first_frame import (
    ScreenshotAnalysis,
    analyze_screenshot,
    android_fresh_startup_log_evidence,
    detect_native_static_petal_mismatch,
    detect_prolonged_system_blue,
    detect_repeated_splash,
    native_launch_visual_provenance,
    android_gate_main_order_observed,
    parse_android_launcher_resolution,
    parse_android_task_snapshot,
)


class StartupProbeParserContractTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))

from verify_startup_first_frame import build_arg_parser, parse_startup_sequence_log
from verify_startup_ttid_baseline import validate_commercial_uat
from verify_startup_web import (
    build_arg_parser as build_web_arg_parser,
    overlay_removed_event,
    parse_startup_report,
    shell_event,
    terminal_event,
)


class StartupProbeParserContractTest(unittest.TestCase):
    def test_parses_terminal_and_shell_events(self) -> None:
        raw = """
QWQStartup: startup_welcome_sequence phase=finished motionSpecVersion=petal_bloom_v2 replayCount=1 exitReason=ready_replay welcomeExitMs=2410
QWQStartup: startup_welcome_sequence phase=main_shell_first_paint shellFirstPaintMs=2530
QWQStartup: startup_welcome_sequence phase=welcome_overlay_removed overlayRemovedMs=2650
"""
        parsed = parse_startup_sequence_log(raw)
        self.assertEqual(parsed["welcomeExitMs"], 2410)
        self.assertEqual(parsed["exitReason"], "ready_replay")
        self.assertEqual(parsed["replayCount"], 1)
        self.assertEqual(parsed["shellFirstPaintMs"], 2530)
        self.assertEqual(parsed["overlayRemovedMs"], 2650)
        self.assertEqual(parsed["motionSpecVersion"], "petal_bloom_v2")

    def test_parses_native_json_event_bridge(self) -> None:
        raw = """
I/QWQStartup: startup_event {"eventName":"startup_welcome_sequence","phase":"finished","motionSpecVersion":"petal_bloom_v2","welcomeExitMs":1710,"exitReason":"ready_primary","replayCount":0}
I/QWQStartup: startup_event {"eventName":"startup_welcome_sequence","phase":"main_shell_first_paint","shellFirstPaintMs":1770}
I/QWQStartup: startup_event {"eventName":"startup_welcome_sequence","phase":"welcome_overlay_removed","overlayRemovedMs":1890}
"""
        parsed = parse_startup_sequence_log(raw)
        self.assertEqual(parsed["welcomeExitMs"], 1710)
        self.assertEqual(parsed["exitReason"], "ready_primary")
        self.assertEqual(parsed["shellFirstPaintMs"], 1770)
        self.assertEqual(parsed["overlayRemovedMs"], 1890)
        self.assertEqual(parsed["motionSpecVersion"], "petal_bloom_v2")

    def test_default_probe_samples_three_and_six_second_boundaries(self) -> None:
        args = build_arg_parser().parse_args([])
        self.assertIn(3000, args.android_offsets_ms)
        self.assertIn(6000, args.android_offsets_ms)
        self.assertIn(3000, args.ios_offsets_ms)
        self.assertIn(6000, args.ios_offsets_ms)
        self.assertEqual(args.shell_first_paint_target_ms, 3000)
        self.assertEqual(args.welcome_exit_hard_ms, 6000)

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
                "motionSpecVersion": "petal_bloom_v2",
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
        self.assertEqual(
            build_web_arg_parser().parse_args(["--url", "http://localhost"]).runs,
            20,
        )


if __name__ == "__main__":
    unittest.main()

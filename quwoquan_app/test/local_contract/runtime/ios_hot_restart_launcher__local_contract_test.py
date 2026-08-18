import json
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))

from verify_flutter_run_defines import validate_flutter_run_defines
from verify_ios_hot_restart import (
    _count_native_launches_since,
    _terminate_stale_device_runtime,
    cold_startup_terminal_observed,
    flutter_resident_ready_for_hot_restart,
)


PREFLIGHT = APP_DIR / "scripts/device/verify_flutter_run_defines.py"
LAUNCHER = APP_DIR / "run.sh"
HOT_RESTART = APP_DIR / "scripts/device/verify_ios_hot_restart.py"


def complete_defines(environment: str = "alpha") -> dict[str, str]:
    return {
        "APP_RUNTIME_ENV": environment,
        "CLOUD_GATEWAY_BASE_URL": "https://api.example.test",
        "APP_LEGAL_BASE_URL": "https://legal.example.test",
        "PUBLIC_WEB_BASE_URL": "https://web.example.test",
        "MEDIA_AVATAR_CDN_BASE_URL": "https://avatar.example.test",
        "MEDIA_IMAGE_CDN_BASE_URL": "https://image.example.test",
        "MEDIA_VIDEO_CDN_BASE_URL": "https://video.example.test",
        "MEDIA_UPLOAD_BASE_URL": "https://upload.example.test",
        "RTC_MEDIA_CONNECTION_URL": "wss://rtc.example.test",
    }


class IosHotRestartLauncherContractTest(unittest.TestCase):
    def test_complete_define_package_passes_before_flutter(self) -> None:
        self.assertEqual(
            validate_flutter_run_defines(
                complete_defines("beta"),
                expected_env="beta",
                platform="ios",
            ),
            [],
        )

    def test_missing_define_package_fails_actionably(self) -> None:
        issues = validate_flutter_run_defines(
            {"APP_RUNTIME_ENV": "alpha"},
            expected_env="alpha",
            platform="ios",
        )
        self.assertIn("missing CLOUD_GATEWAY_BASE_URL", issues)
        self.assertIn("missing MEDIA_UPLOAD_BASE_URL", issues)
        self.assertIn("missing RTC_MEDIA_CONNECTION_URL", issues)

        result = subprocess.run(
            [sys.executable, str(PREFLIGHT), "--env", "alpha", "--platform", "ios"],
            cwd=APP_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("before flutter build/run", result.stderr)
        self.assertIn("run.sh", result.stderr)

    def test_canonical_launcher_preflights_and_marks_compile_time_launch_mode(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("verify_flutter_run_defines.py", source)
        self.assertIn("--launch-mode canonical_launcher", source)
        self.assertIn("--dart-define", source)
        self.assertIn('export QWQ_APP_LAUNCH_MODE="$LAUNCH_MODE"', source)
        self.assertNotIn('stackctl.py" up', source)
        self.assertIn(
            'app-debug-preflight --purpose "$PREFLIGHT_PURPOSE"',
            source,
        )
        self.assertIn(
            '--target "$QWQ_LAUNCH_TARGET" --runtime-mode test_live',
            source,
        )

    def test_hot_restart_smoke_covers_both_surfaces_and_three_restarts(self) -> None:
        source = HOT_RESTART.read_text(encoding="utf-8")
        self.assertIn('APP_DIR / "run.sh"', source)
        self.assertIn(
            '["flutter", "run", "--flavor", args.env, "-d", args.device_id]',
            source,
        )
        self.assertIn('"direct_flutter_run"', source)
        self.assertIn('environment["QWQ_ENVIRONMENT"] = args.env', source)
        self.assertIn('os.write(master_fd, b"R")', source)
        self.assertIn('default=3', source)
        self.assertIn('range(args.hot_restart_count)', source)
        self.assertIn('_terminate_stale_device_runtime(', source)
        self.assertNotIn('["ps", "-axo", "pid=,command="]', source)
        self.assertNotIn('is_workspace_frontend_server', source)
        self.assertIn("extract_dart_startup_attempts", source)
        self.assertIn("nativeDidFinishLaunchingCount", source)

    def test_stale_cleanup_is_scoped_to_the_target_simulator_bundle(self) -> None:
        with patch(
            "verify_ios_hot_restart.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, "", ""),
        ) as run:
            result = _terminate_stale_device_runtime(
                "SIMULATOR-UDID",
                "com.example.quwoquanApp",
            )

        run.assert_called_once_with(
            [
                "xcrun",
                "simctl",
                "terminate",
                "SIMULATOR-UDID",
                "com.example.quwoquanApp",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result["cleanupScope"], "simulator_bundle_only")
        self.assertTrue(result["terminatedNativeApp"])
        self.assertEqual(result["terminatedFlutterResidentPids"], [])
        self.assertEqual(result["terminatedFrontendServerPids"], [])

    def test_hot_restart_waits_for_flutter_resident_command_reader(self) -> None:
        self.assertFalse(
            flutter_resident_ready_for_hot_restart(
                b"QWQ_APP_STARTUP_SEQUENCE phase=router_shell_mounted\n"
            )
        )
        self.assertFalse(
            flutter_resident_ready_for_hot_restart(
                b"Flutter run key commands.\n"
            )
        )
        self.assertTrue(
            flutter_resident_ready_for_hot_restart(
                b"Flutter run key commands.\nR Hot restart.\n"
            )
        )

    def test_preflight_json_is_typed_and_contains_no_endpoint_values(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(PREFLIGHT),
                "--env",
                "alpha",
                "--platform",
                "ios",
                "--defines-json",
                json.dumps(complete_defines()),
            ],
            cwd=APP_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "passed")
        self.assertNotIn("api.example.test", result.stdout)

    def test_flutter_style_dart_define_arguments_are_preflighted(self) -> None:
        defines = complete_defines("gamma")
        command = [
            sys.executable,
            str(PREFLIGHT),
            "--env",
            "gamma",
            "--platform",
            "ios",
        ]
        command.extend(
            f"--dart-define={key}={value}"
            for key, value in defines.items()
        )
        result = subprocess.run(
            command,
            cwd=APP_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout)["environment"], "gamma")

    def test_hot_restart_probe_ignores_baseline_attempts(self) -> None:
        raw = """
2026-07-19 14:00:00.000 Df Runner[1] QWQStartup ios_did_finish_launching
QWQStartup ios_dart_startup_attempt attemptId=old_attempt launchMode=canonical_launcher hotRestart=false configurationState=complete
QWQStartup ios_startup_safe_terminal reportedElapsedMs=1200 receivedMs=1300 attemptId=old_attempt
QWQStartup ios_dart_startup_attempt attemptId=new_attempt launchMode=canonical_launcher hotRestart=false configurationState=complete
QWQStartup ios_startup_safe_terminal reportedElapsedMs=1400 receivedMs=1500 attemptId=new_attempt
"""
        self.assertTrue(cold_startup_terminal_observed(raw))
        self.assertTrue(
            cold_startup_terminal_observed(
                raw,
                excluded_attempt_ids={"old_attempt"},
            )
        )
        self.assertEqual(
            _count_native_launches_since(
                raw,
                datetime(2026, 7, 19, 13, 59, 59),
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()

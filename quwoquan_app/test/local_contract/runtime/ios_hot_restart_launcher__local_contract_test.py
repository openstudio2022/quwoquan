# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003

import json
import signal
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))

from hot_restart_resident_observation import (
    cold_startup_terminal_observed,
    flutter_resident_ready_for_hot_restart,
)
from verify_flutter_run_defines import validate_flutter_run_defines
from verify_ios_hot_restart import (
    _attempt_evidence_issues,
    _count_native_launches_since,
    _runtime_identity_issues,
    _stop_original_process_group,
    _terminate_stale_device_runtime,
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
    def test_only_cold_native_receipt_can_use_an_explicit_uat_allowance(
        self,
    ) -> None:
        attempt = {
            "launchProvenance": "canonical_launcher",
            "runtimeConfigSupplyMode": "external_runtime_package",
            "bootstrapFailure": False,
            "terminalSurface": "router_shell",
            "canonicalTerminal": "routerShell",
            "configurationState": "complete",
            "missingDefineKeys": "",
            "terminalEventCount": 1,
            "reportedSafeTerminalMs": 3949,
            "nativeReceivedSafeTerminalMs": 6210,
        }

        default_issues = _attempt_evidence_issues(
            "cold",
            attempt,
            expected_launch_provenance="canonical_launcher",
            is_cold=True,
        )
        self.assertEqual(
            default_issues,
            [
                "cold: nativeReceivedSafeTerminalMs is missing or exceeds "
                "6000ms"
            ],
        )
        self.assertEqual(
            _attempt_evidence_issues(
                "cold",
                attempt,
                expected_launch_provenance="canonical_launcher",
                is_cold=True,
                max_cold_native_safe_terminal_ms=12000,
            ),
            [],
        )

        embedded_package = {
            **attempt,
            "runtimeConfigSupplyMode": "embedded_runtime_package",
        }
        self.assertIn(
            "cold: runtimeConfigSupplyMode is 'embedded_runtime_package', "
            "expected 'external_runtime_package'",
            _attempt_evidence_issues(
                "cold",
                embedded_package,
                expected_launch_provenance="canonical_launcher",
                is_cold=True,
                max_cold_native_safe_terminal_ms=12000,
            ),
        )

        recovery_surface = {**attempt, "terminalSurface": "safe_recovery"}
        self.assertIn(
            "cold: startup safe-terminal surface is 'safe_recovery', "
            "expected 'router_shell'",
            _attempt_evidence_issues(
                "cold",
                recovery_surface,
                expected_launch_provenance="canonical_launcher",
                is_cold=True,
                max_cold_native_safe_terminal_ms=12000,
            ),
        )

        cold_reported_slow = {**attempt, "reportedSafeTerminalMs": 6210}
        self.assertIn(
            "cold: reportedSafeTerminalMs is missing or exceeds 6000ms",
            _attempt_evidence_issues(
                "cold",
                cold_reported_slow,
                expected_launch_provenance="canonical_launcher",
                is_cold=True,
                max_cold_native_safe_terminal_ms=12000,
            ),
        )

        hot_slow = {
            **attempt,
            "reportedSafeTerminalMs": 6210,
            "nativeReceivedSafeTerminalMs": 6210,
        }
        hot_issues = _attempt_evidence_issues(
            "hot_restart_1",
            hot_slow,
            expected_launch_provenance="canonical_launcher",
            is_cold=False,
            max_cold_native_safe_terminal_ms=12000,
        )
        self.assertIn(
            "hot_restart_1: reportedSafeTerminalMs is missing or exceeds "
            "6000ms",
            hot_issues,
        )
        self.assertIn(
            "hot_restart_1: nativeReceivedSafeTerminalMs is missing or exceeds "
            "6000ms",
            hot_issues,
        )

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

    def test_canonical_launcher_exports_single_track_launch_identity(self) -> None:
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('--launch-provenance "$LAUNCH_PROVENANCE"', source)
        self.assertIn(
            "canonical_launcher|workspace_ide_debug",
            source,
        )
        # workspace facade 已退役：launcher 不再承认 workspace_flutter_run。
        self.assertNotIn("workspace_flutter_run", source)
        # runtime config 走签名 package 的安装后激活，不进编译期 define；构建输入的
        # 所有权也整体归 canonical executor，因此 launcher 既不写 dart define，
        # 也不自持第二处 define 校验。
        self.assertNotIn("--dart-define", source)
        self.assertNotIn("verify_flutter_run_defines.py", source)
        self.assertIn(
            'export QWQ_APP_LAUNCH_PROVENANCE="$LAUNCH_PROVENANCE"',
            source,
        )
        self.assertIn(
            'export QWQ_RUNTIME_CONFIG_SUPPLY_MODE="$RUNTIME_CONFIG_SUPPLY_MODE"',
            source,
        )
        self.assertNotIn('stackctl.py" up', source)
        self.assertIn(
            'app-debug-preflight --purpose "$PREFLIGHT_PURPOSE"',
            source,
        )
        self.assertIn(
            '--target "$QWQ_LAUNCH_TARGET" --runtime-mode test_live',
            source,
        )
        # workspace surface（IDE Flutter Debug）没有命令行 --mode 通道；
        # mode 与环境同构，经 QWQ_RUN_MODE 环境变量选择，默认
        # content-live，非法值走同一 GATE_BLOCK 校验。
        self.assertIn('RUN_MODE="${QWQ_RUN_MODE:-content-live}"', source)

    def test_hot_restart_smoke_covers_canonical_surface_and_three_restarts(self) -> None:
        source = HOT_RESTART.read_text(encoding="utf-8")
        self.assertIn('APP_DIR / "run.sh"', source)
        # workspace facade 已退役：smoke 只驱动 canonical launcher，
        # mode 经 --mode 参数透传。
        self.assertNotIn("flutter_facade", source)
        self.assertNotIn("workspace_flutter_run", source)
        self.assertNotIn('["flutter", "run", "-d", args.device_id]', source)
        self.assertNotIn('"--flavor"', source)
        self.assertIn('"--launch-provenance"', source)
        self.assertIn('environment["QWQ_APP_RUNTIME_ENV"] = args.env', source)
        # resident 会话是 flutter attach --machine（daemon 协议）：hot restart
        # 走 app.restart JSON-RPC；交互式 R 键仅作为非 daemon 会话的后备。
        self.assertIn('"method": "app.restart"', source)
        self.assertIn("daemon_resident_app_id", source)
        self.assertIn('os.write(master_fd, b"R")', source)
        # runtime identity 的真相源是安装后激活写入的 active receipt。
        self.assertIn("runtime-config-active-receipt.json", source)
        self.assertIn('default=3', source)
        self.assertIn('range(1, restart_count + 1)', source)
        self.assertIn("_publish_canonical_launch_terminal(", source)
        self.assertIn("QWQ_APP_STARTUP_TERMINAL_RECEIPT", source)
        self.assertIn('_terminate_stale_device_runtime(', source)
        self.assertNotIn('["ps", "-axo", "pid=,command="]', source)
        self.assertNotIn('is_workspace_frontend_server', source)
        self.assertIn("extract_dart_startup_attempts", source)
        self.assertIn("nativeDidFinishLaunchingCount", source)
        self.assertIn("runtimeIdentitySnapshots", source)
        self.assertIn("flutterProcessGroupStoppedBySigint", source)
        self.assertNotIn("process.terminate()", source)
        self.assertNotIn("process.kill()", source)

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

    def test_flutter_session_shutdown_targets_only_original_process_group(self) -> None:
        process = Mock()
        process.poll.return_value = None
        process.wait.return_value = 0
        with patch("verify_ios_hot_restart.os.killpg") as killpg:
            stopped = _stop_original_process_group(
                process,
                4242,
                attempts=1,
                wait_seconds=0.01,
            )

        self.assertTrue(stopped)
        killpg.assert_called_once_with(4242, signal.SIGINT)
        process.wait.assert_called_once_with(timeout=0.01)
        self.assertNotIn("call.terminate()", [str(call) for call in process.mock_calls])
        self.assertNotIn("call.kill()", [str(call) for call in process.mock_calls])

    def test_cold_and_three_hot_restarts_keep_one_runtime_identity(self) -> None:
        identity = {
            "environment": "beta",
            "target": "beta-local",
            "runtimeConfigDigest": f"sha256:{'1' * 64}",
            "effectiveLaunchManifestDigest": f"sha256:{'2' * 64}",
        }
        self.assertEqual(
            _runtime_identity_issues(
                [dict(identity) for _ in range(4)],
                expected_environment="beta",
            ),
            [],
        )

        drifted = [dict(identity) for _ in range(4)]
        drifted[3]["runtimeConfigDigest"] = f"sha256:{'3' * 64}"
        self.assertIn(
            "hot_restart_3: runtimeConfigDigest drifted from the cold runtime identity",
            _runtime_identity_issues(
                drifted,
                expected_environment="beta",
            ),
        )

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
        # daemon 协议（flutter attach --machine）以 app.started 为就绪信号。
        self.assertTrue(
            flutter_resident_ready_for_hot_restart(
                b'[{"event":"app.started","params":{"appId":"x"}}]\n'
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
QWQStartup ios_dart_startup_attempt attemptId=old_attempt launchProvenance=canonical_launcher runtimeConfigSupplyMode=external_runtime_package hotRestart=false configurationState=complete
QWQStartup ios_startup_safe_terminal surface=router_shell reportedElapsedMs=1200 receivedMs=1300 attemptId=old_attempt
QWQStartup ios_dart_startup_attempt attemptId=new_attempt launchProvenance=canonical_launcher runtimeConfigSupplyMode=external_runtime_package hotRestart=false configurationState=complete
QWQStartup ios_startup_safe_terminal surface=router_shell reportedElapsedMs=1400 receivedMs=1500 attemptId=new_attempt
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

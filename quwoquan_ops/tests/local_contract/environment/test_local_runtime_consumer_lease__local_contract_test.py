# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli.lib.local_runtime_consumer_lease import (
    acquire_consumer_lease,
    active_consumer_leases,
    list_consumer_leases,
)


ROOT = Path(__file__).resolve().parents[4]
STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"
APP_RUN = ROOT / "quwoquan_app/run.sh"
ANDROID_APP_BUILD = ROOT / "quwoquan_app/android/app/build.gradle.kts"


class LocalRuntimeConsumerLeaseTest(unittest.TestCase):
    def _run_launcher_with_preflight_policy(
        self,
        *,
        gate_block: bool,
    ) -> tuple[subprocess.CompletedProcess[str], str, str]:
        with tempfile.TemporaryDirectory() as temporary_dir:
            temp_root = Path(temporary_dir)
            flutter_log = temp_root / "flutter.log"
            stackctl_log = temp_root / "stackctl.log"
            fake_flutter = temp_root / "flutter"
            fake_flutter.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f"printf '%s\\n' \"$*\" >> {shlex.quote(str(flutter_log))}\n"
                "if [[ \"$*\" == \"pub get --offline\" ]]; then exit 0; fi\n"
                "if [[ \"$*\" == \"devices --machine\" ]]; then\n"
                "  echo '[{\"id\":\"policy-ios\",\"name\":\"Policy iPhone\","
                "\"targetPlatform\":\"ios\",\"emulator\":true,"
                "\"ephemeral\":false,\"isSupported\":true}]'\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"run\" ]]; then exit 0; fi\n"
                "exit 97\n",
                encoding="utf-8",
            )
            fake_flutter.chmod(0o755)

            fake_python = temp_root / "python3"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "if [[ \"${1:-}\" == */quwoquan_ops/cli/stackctl.py ]]; then\n"
                f"  printf '%s\\n' \"$*\" >> {shlex.quote(str(stackctl_log))}\n"
                "  if [[ \" $* \" == *\" app-debug-preflight \"* ]]; then\n"
                "    if [[ \"${TEST_PREFLIGHT_GATE_BLOCK:-0}\" == \"1\" ]]; then\n"
                "      echo '{\"exitCode\":2,\"status\":\"gate_block\","
                "\"details\":[\"alpha api endpoint escapes the selected namespace\"],"
                "\"warnings\":[]}'\n"
                "      exit 2\n"
                "    fi\n"
                "    echo '{\"exitCode\":0,\"status\":\"warning\","
                "\"purpose\":\"runtime\",\"nonPromotable\":true,"
                "\"details\":[],\"warnings\":[\"target startup status is not running: stopped\"],"
                "\"runtimeChecks\":[],\"contentBindingState\":\"unbound\","
                "\"contentAvailability\":{\"state\":\"unbound\","
                "\"emptyReason\":\"no_active_release\"}}'\n"
                "    exit 0\n"
                "  fi\n"
                "  if [[ \" $* \" == *\" device-trust \"* ]]"
                " || [[ \" $* \" == *\" consumer-lease acquire \"* ]]; then\n"
                "    exit 2\n"
                "  fi\n"
                "  if [[ \" $* \" == *\" consumer-lease release \"* ]]; then exit 0; fi\n"
                "fi\n"
                f"exec {shlex.quote(sys.executable)} \"$@\"\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = (
                f"{temporary_dir}{os.pathsep}{environment['PATH']}"
            )
            environment["QWQ_OUTPUT_ROOT"] = str(temp_root / "output")
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONPYCACHEPREFIX"] = str(temp_root / "pycache")
            environment["TEST_PREFLIGHT_GATE_BLOCK"] = "1" if gate_block else "0"
            result = subprocess.run(
                [
                    "bash",
                    str(APP_RUN),
                    "--env",
                    "alpha",
                    "--mode",
                    "ui-only",
                    "-d",
                    "policy-ios",
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            return (
                result,
                flutter_log.read_text(encoding="utf-8") if flutter_log.exists() else "",
                stackctl_log.read_text(encoding="utf-8") if stackctl_log.exists() else "",
            )

    def test_launcher_warning_policy_reaches_flutter_run_without_runtime_lease(
        self,
    ) -> None:
        result, flutter_log, stackctl_log = self._run_launcher_with_preflight_policy(
            gate_block=False
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "WARN: target startup status is not running: stopped",
            result.stderr,
        )
        self.assertIn(
            "WARN: runtime consumer lease is unavailable",
            result.stderr,
        )
        self.assertIn("run --no-pub", flutter_log)
        self.assertIn(
            "app-debug-preflight --purpose runtime "
            "--target alpha-local --runtime-mode test_live",
            stackctl_log,
        )

    def test_launcher_hard_safety_blocker_stops_before_flutter_run(self) -> None:
        result, flutter_log, stackctl_log = self._run_launcher_with_preflight_policy(
            gate_block=True
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "alpha api endpoint escapes the selected namespace", result.stderr
        )
        self.assertNotIn("run --no-pub", flutter_log)
        self.assertIn(
            "app-debug-preflight --purpose runtime "
            "--target alpha-local --runtime-mode test_live",
            stackctl_log,
        )

    def test_android_launcher_owns_and_releases_lease(self) -> None:
        script = APP_RUN.read_text(encoding="utf-8")
        self.assertIn("trap release_consumer_lease EXIT", script)
        self.assertIn("consumer-lease acquire", script)
        self.assertIn("consumer-lease release", script)
        self.assertIn('if [[ -z "$DEVICE_ID" ]]', script)
        self.assertIn("pass -d/--device-id", script)
        self.assertIn('--package-name "$QWQ_DEBUG_APP_ID"', script)
        self.assertIn("from quwoquan_ops.cli.lib.app_identity import application_id_for", script)
        self.assertIn('"$RUNTIME_STACKCTL_PYTHON" -c', script)
        self.assertIn("--ports \"$QWQ_ANDROID_LOCAL_PORTS\"", script)
        self.assertIn('export QWQ_ENVIRONMENT="${REQUESTED_ENVIRONMENT:-alpha}"', script)
        self.assertIn('export QWQ_APP_RUNTIME_ENV="$QWQ_ENVIRONMENT"', script)
        self.assertIn(
            'QWQ_LAUNCH_TARGET="${REQUESTED_TARGET:-${QWQ_APP_RUNTIME_ENV}-local}"',
            script,
        )
        self.assertIn(
            'app-debug-preflight --purpose "$PREFLIGHT_PURPOSE"',
            script,
        )
        self.assertIn(
            '--target "$QWQ_LAUNCH_TARGET" --runtime-mode test_live',
            script,
        )
        self.assertIn("--platform ios-simulator", script)
        self.assertIn('--bundle-id "$QWQ_DEBUG_APP_ID"', script)
        self.assertIn("QWQ_CONSUMER_LEASE_ID", script)
        self.assertIn("QWQ_ANDROID_REVERSE_RECEIPT_DIGEST", script)
        self.assertIn("QWQ_ANDROID_REVERSE_OWNED_PORTS", script)
        self.assertIn("QWQ_ANDROID_VM_FORWARD_PREEXISTING", script)
        self.assertIn("forward --remove tcp:8888", script)
        self.assertIn('"compileStatus": "passed" if exit_code == 0', script)
        self.assertIn('"launchStatus": "completed" if exit_code == 0', script)
        self.assertIn('"contentAvailability": preflight.get', script)
        self.assertIn('"providerAvailability": provider_availability', script)
        self.assertIn('DEVICE_TRUST_PLATFORM="android-emulator"', script)
        self.assertIn(r'r"tcp:(\d+)\s+tcp:\d+"', script)
        self.assertNotIn("exec flutter run", script)
        self.assertLess(
            script.index("consumer-lease acquire"),
            script.index("flutter run \\\n"),
        )

    def test_launcher_rejects_unknown_or_nonmobile_device_before_runtime_preflight(
        self,
    ) -> None:
        script = APP_RUN.read_text(encoding="utf-8")
        device_guard = "a connected iOS/Android device is required before runtime preflight"
        self.assertIn("Flutter device {device_id!r} is not currently connected", script)
        self.assertIn("unsupported platform {platform!r}", script)
        self.assertIn(device_guard, script)
        # 设备守卫必须先于任何设备绑定动作（trust/lease/flutter run）。
        # 环境级 content preflight 不依赖设备，允许先行。
        self.assertLess(
            script.index(device_guard),
            script.index("consumer-lease acquire"),
        )
        self.assertLess(
            script.index(device_guard),
            script.index("flutter run \\\n"),
        )

    def test_launcher_blocks_unknown_device_before_runtime_preflight_or_flutter_run(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            fake_flutter = Path(temporary_dir) / "flutter"
            fake_flutter.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"$*\" == \"pub get --offline\" ]]; then exit 0; fi\n"
                "if [[ \"$*\" == \"devices --machine\" ]]; then echo '[]'; exit 0; fi\n"
                "echo \"unexpected fake flutter invocation: $*\" >&2\n"
                "exit 97\n",
                encoding="utf-8",
            )
            fake_flutter.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{temporary_dir}{os.pathsep}{environment['PATH']}"
            result = subprocess.run(
                ["bash", str(APP_RUN), "--env", "alpha", "-d", "offline-device"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        # 未知设备的启动必须在 flutter run 之前被阻断。环境级 content
        # preflight 先于设备解析执行：环境未运行时先撞 preflight
        # GATE_BLOCK，环境在跑时到达设备守卫；两者都不得进入 flutter run。
        blocked_by_device_guard = (
            "a connected iOS/Android device is required" in result.stderr
        )
        blocked_by_preflight = '"status": "gate_block"' in result.stderr
        self.assertTrue(
            blocked_by_device_guard or blocked_by_preflight,
            result.stderr,
        )
        self.assertNotIn("validating full Debug runtime", result.stdout)
        self.assertNotIn("flutter run", result.stdout)

    def test_android_gradle_requires_canonical_transport_receipts(self) -> None:
        script = ANDROID_APP_BUILD.read_text(encoding="utf-8")
        launcher_gate = script[script.index("val verifyAndroidLocalLauncherContract") :]
        self.assertIn('"QWQ_CONSUMER_LEASE_ACQUIRED"', launcher_gate)
        self.assertIn('"QWQ_CONSUMER_LEASE_ID"', launcher_gate)
        self.assertIn('"QWQ_RUN_DEVICE_ID"', launcher_gate)
        self.assertIn('"QWQ_ANDROID_REVERSE_EXPECTED_PORTS"', launcher_gate)
        self.assertIn('"QWQ_ANDROID_REVERSE_ACTUAL_PORTS"', launcher_gate)
        self.assertIn('"QWQ_ANDROID_REVERSE_RECEIPT_DIGEST"', launcher_gate)
        self.assertNotIn('"QWQ_LOCAL_TLS_BUNDLE_DIGEST"', launcher_gate)
        self.assertIn('"reverse", "--list"', launcher_gate)
        self.assertIn('"consumer-lease",', launcher_gate)
        self.assertIn('"direct-flutter-run"', launcher_gate)
        self.assertIn("handoffLocalPorts(directDebugHandoff)", launcher_gate)
        self.assertIn('if (appLaunchPolicy == "prod_release")', launcher_gate)
        self.assertIn('if (leaseAcquired != "1")', launcher_gate)
        self.assertIn("test_live transport lease is unavailable", launcher_gate)
        self.assertNotIn("contentReadinessReceiptDigest", launcher_gate)

    def test_build_grace_blocks_without_adb_probe(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="alpha-local",
                device="device-1",
                consumer="flutter-run",
                package_name="com.quwoquan.quwoquan_app",
                ports=(17000, 17010, 17100),
                build_grace_seconds=1200,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )
            self.assertRegex(str(lease["leaseId"]), r"^sha256:[0-9a-f]{64}$")
            active = active_consumer_leases(
                "alpha-local",
                now=started_at + timedelta(seconds=30),
                runner=lambda _: self.fail("adb must not run during build grace"),
            )
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["state"], "build_grace")

    def test_ios_simulator_lease_records_release_bound_handoff_without_ports(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="beta-local",
                device="SIMULATOR-UDID",
                consumer="direct-flutter-run",
                package_name="com.example.quwoquanApp",
                ports=(),
                platform="ios-simulator",
                handoff_digest="sha256:" + "1" * 64,
                release_id="release-001",
                manifest_digest="sha256:" + "2" * 64,
                readiness_receipt_digest="sha256:" + "3" * 64,
                build_grace_seconds=1,
            )
            self.assertEqual(lease["platform"], "ios-simulator")
            self.assertEqual(lease["bundleId"], "com.example.quwoquanApp")
            self.assertEqual(lease["ports"], [])
            self.assertEqual(lease["releaseId"], "release-001")

    def test_ios_simulator_running_app_keeps_lease_after_grace(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="alpha-local",
                device="SIMULATOR-UDID",
                consumer="flutter-run",
                package_name="com.example.quwoquanApp",
                ports=(),
                platform="ios-simulator",
                build_grace_seconds=1,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )

            def running(argv: list[str]) -> subprocess.CompletedProcess[str]:
                if argv[-1] == "--json":
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        json.dumps(
                            {
                                "devices": {
                                    "runtime": [
                                        {
                                            "udid": "SIMULATOR-UDID",
                                            "state": "Booted",
                                        }
                                    ]
                                }
                            }
                        ),
                        "",
                    )
                if argv[-2:] == ["id", "-u"]:
                    return subprocess.CompletedProcess(argv, 0, "501\n", "")
                if "get_app_container" in argv:
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        "/tmp/Runner.app\n",
                        "",
                    )
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    (
                        "UIKitApplication:com.example.quwoquanApp[active]\n"
                        "path = /tmp/Runner.app/Runner"
                    ),
                    "",
                )

            active = active_consumer_leases(
                "alpha-local",
                now=started_at + timedelta(seconds=5),
                runner=running,
                xcrun_path="xcrun",
            )
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["state"], "active")

    def test_ios_simulator_verified_app_does_not_expire_after_twelve_hours(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="alpha-local",
                device="SIMULATOR-UDID",
                consumer="flutter-run",
                package_name="com.example.quwoquanApp",
                ports=(),
                platform="ios-simulator",
                build_grace_seconds=1,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )

            def running(argv: list[str]) -> subprocess.CompletedProcess[str]:
                if argv[-1] == "--json":
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        json.dumps(
                            {
                                "devices": {
                                    "runtime": [
                                        {
                                            "udid": "SIMULATOR-UDID",
                                            "state": "Booted",
                                        }
                                    ]
                                }
                            }
                        ),
                        "",
                    )
                if argv[-2:] == ["id", "-u"]:
                    return subprocess.CompletedProcess(argv, 0, "501\n", "")
                if "get_app_container" in argv:
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        "/tmp/Runner.app\n",
                        "",
                    )
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    (
                        "UIKitApplication:com.example.quwoquanApp[suspended]\n"
                        "path = /tmp/Runner.app/Runner"
                    ),
                    "",
                )

            active = active_consumer_leases(
                "alpha-local",
                now=started_at + timedelta(hours=24),
                runner=running,
                xcrun_path="xcrun",
            )
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["state"], "active")

    def test_ios_simulator_stopped_app_prunes_lease_after_grace(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="gamma-local",
                device="SIMULATOR-UDID",
                consumer="flutter-run",
                package_name="com.example.quwoquanApp",
                ports=(),
                platform="ios-simulator",
                build_grace_seconds=1,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )

            def stopped(argv: list[str]) -> subprocess.CompletedProcess[str]:
                if argv[-1] == "--json":
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        json.dumps(
                            {
                                "devices": {
                                    "runtime": [
                                        {
                                            "udid": "SIMULATOR-UDID",
                                            "state": "Booted",
                                        }
                                    ]
                                }
                            }
                        ),
                        "",
                    )
                if argv[-2:] == ["id", "-u"]:
                    return subprocess.CompletedProcess(argv, 0, "501\n", "")
                if "get_app_container" in argv:
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        "/tmp/Runner.app\n",
                        "",
                    )
                return subprocess.CompletedProcess(argv, 0, "other services", "")

            active = active_consumer_leases(
                "gamma-local",
                now=started_at + timedelta(seconds=5),
                runner=stopped,
                xcrun_path="xcrun",
            )
            self.assertEqual(active, [])
            self.assertEqual(
                len(list_consumer_leases("gamma-local")),
                1,
                "status/liveness inspection must be strictly read-only",
            )

    def test_disconnected_device_prunes_expired_build_lease(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                target="alpha-local",
                device="device-1",
                consumer="flutter-run",
                package_name="com.quwoquan.quwoquan_app",
                ports=(17000,),
                build_grace_seconds=1,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )

            def disconnected(_: list[str]) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess([], 1, "", "device missing")

            active = active_consumer_leases(
                "alpha-local",
                now=started_at + timedelta(seconds=5),
                runner=disconnected,
                adb_path="adb",
            )
            self.assertEqual(active, [])
            self.assertEqual(
                len(list_consumer_leases("alpha-local")),
                1,
                "stale cleanup requires an explicit release or GC operation",
            )

    def test_stackctl_down_is_gate_blocked_by_flutter_consumer(self) -> None:
        with tempfile.TemporaryDirectory() as output_root:
            environment = {
                **os.environ,
                "QWQ_OUTPUT_ROOT": output_root,
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            acquire = subprocess.run(
                [
                    sys.executable,
                    str(STACKCTL),
                    "--output-format",
                    "json",
                    "consumer-lease",
                    "acquire",
                    "--target",
                    "alpha-local",
                    "--device",
                    "device-1",
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(acquire.returncode, 0, acquire.stderr)
            down = subprocess.run(
                [
                    sys.executable,
                    str(STACKCTL),
                    "--output-format",
                    "json",
                    "down",
                    "--target",
                    "alpha-local",
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(down.returncode, 2, down.stderr)
            payload = json.loads(down.stdout)
            self.assertEqual(payload["exitCode"], 2)
            self.assertIn("consumer lease", " ".join(payload["details"]))

    def test_stackctl_accepts_ios_simulator_lease_without_transport_ports(self) -> None:
        with tempfile.TemporaryDirectory() as output_root:
            environment = {
                **os.environ,
                "QWQ_OUTPUT_ROOT": output_root,
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            acquire = subprocess.run(
                [
                    sys.executable,
                    str(STACKCTL),
                    "--output-format",
                    "json",
                    "consumer-lease",
                    "acquire",
                    "--target",
                    "beta-local",
                    "--platform",
                    "ios-simulator",
                    "--device",
                    "SIMULATOR-UDID",
                    "--bundle-id",
                    "com.example.quwoquanApp",
                    "--ports",
                    "",
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(acquire.returncode, 0, acquire.stderr)
            payload = json.loads(acquire.stdout)
            self.assertEqual(payload["lease"]["platform"], "ios-simulator")
            self.assertEqual(payload["lease"]["ports"], [])
            self.assertEqual(
                payload["lease"]["bundleId"],
                "com.example.quwoquanApp",
            )


if __name__ == "__main__":
    unittest.main()

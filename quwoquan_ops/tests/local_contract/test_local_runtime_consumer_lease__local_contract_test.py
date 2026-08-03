# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
from __future__ import annotations

import json
import os
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


ROOT = Path(__file__).resolve().parents[3]
STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"
APP_RUN = ROOT / "quwoquan_app/run.sh"
ANDROID_APP_BUILD = ROOT / "quwoquan_app/android/app/build.gradle.kts"


class LocalRuntimeConsumerLeaseTest(unittest.TestCase):
    def test_android_launcher_owns_and_releases_lease(self) -> None:
        script = APP_RUN.read_text(encoding="utf-8")
        self.assertIn("trap release_consumer_lease EXIT", script)
        self.assertIn("consumer-lease acquire", script)
        self.assertIn("consumer-lease release", script)
        self.assertIn('if [[ -z "$DEVICE_ID" ]]', script)
        self.assertIn("pass -d/--device-id", script)
        self.assertIn("--package-name com.quwoquan.quwoquan_app", script)
        self.assertIn("--ports \"$QWQ_ANDROID_LOCAL_PORTS\"", script)
        self.assertIn('export QWQ_ENVIRONMENT="${REQUESTED_ENVIRONMENT:-alpha}"', script)
        self.assertIn('export QWQ_APP_RUNTIME_ENV="$QWQ_ENVIRONMENT"', script)
        self.assertIn('QWQ_LAUNCH_TARGET="${QWQ_APP_RUNTIME_ENV}-local"', script)
        self.assertIn("app-debug-preflight", script)
        self.assertIn("--platform ios-simulator", script)
        self.assertIn("--bundle-id com.example.quwoquanApp", script)
        self.assertIn("QWQ_CONSUMER_LEASE_ID", script)
        self.assertIn("QWQ_ANDROID_REVERSE_RECEIPT_DIGEST", script)
        self.assertIn("QWQ_ANDROID_REVERSE_OWNED_PORTS", script)
        self.assertIn('DEVICE_TRUST_PLATFORM="android-emulator"', script)
        self.assertIn(r'r"tcp:(\d+)\s+tcp:\d+"', script)
        self.assertNotIn("exec flutter run", script)
        self.assertLess(
            script.index("consumer-lease acquire"),
            script.index("flutter run \\\n"),
        )

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
        self.assertIn('"--readiness-receipt-digest"', launcher_gate)

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

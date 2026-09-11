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


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.local_runtime_consumer_lease import (
    acquire_consumer_lease,
    active_consumer_leases,
    list_consumer_leases,
)


STACKCTL = ROOT / "quwoquan_ops/cli/stackctl.py"


class LocalRuntimeConsumerLeaseIosLivenessTest(unittest.TestCase):
    def test_ios_simulator_lease_records_release_bound_handoff_without_ports(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                instance_generation="runtime-1",
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

    def test_ios_physical_lease_records_bundle_without_transport_ports(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                instance_generation="runtime-1",
                target="gamma-local",
                device="REGISTERED-IPHONE-UDID",
                consumer="canonical-launcher",
                package_name="com.example.quwoquanApp.nonprod.debug",
                ports=(),
                platform="ios-physical",
                handoff_digest="sha256:" + "4" * 64,
                build_grace_seconds=1,
            )
            self.assertEqual(lease["platform"], "ios-physical")
            self.assertEqual(
                lease["bundleId"], "com.example.quwoquanApp.nonprod.debug"
            )
            self.assertEqual(lease["ports"], [])
            self.assertEqual(lease["handoffDigest"], "sha256:" + "4" * 64)

    def test_ios_physical_running_app_keeps_lease_after_grace(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            bundle_id = "com.example.quwoquanApp.nonprod.debug"
            app_url = "/private/var/containers/Bundle/Application/ID/Runner.app"
            lease = acquire_consumer_lease(
                instance_generation="runtime-1",
                target="alpha-local",
                device="REGISTERED-IPHONE-UDID",
                consumer="canonical-launcher",
                package_name=bundle_id,
                ports=(),
                platform="ios-physical",
                build_grace_seconds=1,
            )
            started_at = datetime.fromisoformat(
                str(lease["startedAt"]).replace("Z", "+00:00")
            )
            commands: list[list[str]] = []

            def running(argv: list[str]) -> subprocess.CompletedProcess[str]:
                command = list(argv)
                commands.append(command)
                output_path = Path(command[command.index("--json-output") + 1])
                if "apps" in command:
                    result = {
                        "apps": [
                            {
                                "bundleIdentifier": bundle_id,
                                "name": "Runner",
                                "url": app_url,
                            }
                        ]
                    }
                else:
                    result = {
                        "runningProcesses": [
                            {
                                "executable": f"{app_url}/Runner",
                                "processIdentifier": 4201,
                            }
                        ]
                    }
                output_path.write_text(
                    json.dumps({"result": result}), encoding="utf-8"
                )
                return subprocess.CompletedProcess(command, 0, "", "")

            active = active_consumer_leases(
                "alpha-local",
                now=started_at + timedelta(seconds=5),
                runner=running,
                xcrun_path="xcrun",
            )
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["state"], "active")
            self.assertEqual(
                [command[2:5] for command in commands],
                [
                    ["device", "info", "apps"],
                    ["device", "info", "processes"],
                ],
            )

    def test_ios_simulator_running_app_keeps_lease_after_grace(self) -> None:
        with tempfile.TemporaryDirectory() as output_root, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": output_root},
        ):
            lease = acquire_consumer_lease(
                instance_generation="runtime-1",
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
                instance_generation="runtime-1",
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
                instance_generation="runtime-1",
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
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0]["state"], "active_unverified")
            self.assertEqual(
                len(list_consumer_leases("gamma-local")),
                1,
                "status/liveness inspection must be strictly read-only",
            )

    def test_lease_acquire_succeeds_while_uat_holds_shared_use_lock(self) -> None:
        """真实子进程的共享锁可并存，不通过修改真实 CLI authority 做测试。"""
        from quwoquan_ops.cli.lib.local_runtime_reservation import acquire_local_runtime_use_lock
        guard = acquire_local_runtime_use_lock(target="gamma-local", purpose="uat-outer")
        try:
            result = subprocess.run([
                sys.executable, "-B", "-c",
                "from quwoquan_ops.cli.lib.local_runtime_reservation import acquire_local_runtime_use_lock; "
                "from quwoquan_ops.cli.lib.local_runtime_consumer_lease import acquire_consumer_lease; "
                "import json; "
                "guard=acquire_local_runtime_use_lock(target='gamma-local',purpose='inner'); "
                "print(json.dumps(acquire_consumer_lease(target='gamma-local',device='SIM-UDID',consumer='inner',"
                "package_name='app',ports=(),platform='ios-simulator',instance_generation='runtime-1'))); guard.close()",
            ], cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["leaseId"].startswith("sha256:"))
        finally:
            guard.close()

    def test_stackctl_accepts_ios_leases_without_transport_ports(self) -> None:
        from quwoquan_ops.cli import stackctl
        for platform, device in (("ios-simulator", "SIMULATOR-UDID"), ("ios-physical", "REGISTERED-IPHONE-UDID")):
            args = stackctl.build_parser().parse_args([
                "consumer-lease", "acquire", "--target", "beta-local", "--platform", platform,
                "--device", device, "--bundle-id", "com.example.quwoquanApp", "--ports", "",
                "--instance-generation", "runtime-1",
            ])
            with patch.object(stackctl, "load_startup_attempt", return_value={"status": "running", "attemptId": "runtime-1"}), patch.object(stackctl, "load_test_live_startup_attempt", return_value=None):
                payload = stackctl.command_consumer_lease(args)
            self.assertEqual(payload["exitCode"], 0)
            self.assertEqual(payload["lease"]["platform"], platform)
            self.assertEqual(payload["lease"]["ports"], [])
            self.assertEqual(payload["lease"]["bundleId"], "com.example.quwoquanApp")


if __name__ == "__main__":
    unittest.main()

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

    def test_lease_acquire_succeeds_while_uat_holds_shared_use_lock(self) -> None:
        """app-content-uat 全程持共享 use lock；run.sh 内的 lease 获取
        必须与之兼容（历史上 lease 持排他锁会与外层共享锁自死锁）。"""
        with tempfile.TemporaryDirectory() as output_root:
            environment = {
                **os.environ,
                "QWQ_OUTPUT_ROOT": output_root,
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            lock_probe = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import os, subprocess, sys\n"
                        "os.environ['QWQ_OUTPUT_ROOT'] = sys.argv[1]\n"
                        "sys.path.insert(0, sys.argv[2])\n"
                        "from quwoquan_ops.cli.lib.local_runtime_reservation import (\n"
                        "    acquire_local_runtime_use_lock,\n"
                        ")\n"
                        "handle = acquire_local_runtime_use_lock(\n"
                        "    target='gamma-local', purpose='uat-outer'\n"
                        ")\n"
                        "result = subprocess.run(\n"
                        "    [sys.executable, sys.argv[3], '--output-format',\n"
                        "     'json', 'consumer-lease', 'acquire', '--target',\n"
                        "     'gamma-local', '--platform', 'ios-simulator',\n"
                        "     '--device', 'SIM-UDID', '--consumer', 'inner-run',\n"
                        "     '--bundle-id', 'com.example.quwoquanApp',\n"
                        "     '--ports', ''],\n"
                        "    check=False, capture_output=True, text=True,\n"
                        ")\n"
                        "handle.close()\n"
                        "sys.stderr.write(result.stderr)\n"
                        "sys.stdout.write(result.stdout)\n"
                        "sys.exit(result.returncode)\n"
                    ),
                    output_root,
                    str(ROOT),
                    str(STACKCTL),
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(lock_probe.returncode, 0, lock_probe.stderr)
            payload = json.loads(lock_probe.stdout)
            self.assertEqual(payload["exitCode"], 0)
            self.assertTrue(payload["lease"]["leaseId"].startswith("sha256:"))

    def test_stackctl_accepts_ios_leases_without_transport_ports(self) -> None:
        for platform, device in (
            ("ios-simulator", "SIMULATOR-UDID"),
            ("ios-physical", "REGISTERED-IPHONE-UDID"),
        ):
            with self.subTest(
                platform=platform
            ), tempfile.TemporaryDirectory() as output_root:
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
                        platform,
                        "--device",
                        device,
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
                self.assertEqual(payload["lease"]["platform"], platform)
                self.assertEqual(payload["lease"]["ports"], [])
                self.assertEqual(
                    payload["lease"]["bundleId"],
                    "com.example.quwoquanApp",
                )


if __name__ == "__main__":
    unittest.main()

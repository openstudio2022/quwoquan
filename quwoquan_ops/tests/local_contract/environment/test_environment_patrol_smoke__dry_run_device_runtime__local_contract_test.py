"""dry-run 设备必须与真实发现同源解析 iOS 模拟器 runtime。

dry-run 的价值是验证真实执行会下发的确切命令。合成设备声称是 iOS 模拟器却不带
runtime 身份时，命令拼装拿不到 `--ios=<version>`，整条 dry-run 路径对 iOS 恒定
崩溃；编造一个版本又会让 dry-run 校验的命令与真实命令不同。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke.environment_patrol_smoke import devices as smoke_devices


def _simctl_runner(*, udid: str, version: str):
    runtime_id = "com.apple.CoreSimulator.SimRuntime.iOS-" + version.replace(".", "-")
    payload = json.dumps(
        {
            "runtimes": [
                {"identifier": runtime_id, "version": version, "isAvailable": True}
            ],
            "devices": {
                runtime_id: [
                    {"udid": udid, "name": "iPhone 17 Pro", "isAvailable": True}
                ]
            },
        }
    )

    def runner(command, **kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, payload, "")

    return runner


class EnvironmentPatrolSmokeDryRunDeviceRuntimeTest(unittest.TestCase):
    def _synthetic_ios_device(self, device_id: str) -> dict:
        return {
            "id": device_id,
            "name": "Dry Run Device",
            "targetPlatform": "ios",
            "sdk": "dry-run",
            "emulator": True,
            "screenClass": "phone",
        }

    def test_enriched_dry_run_device_yields_the_real_patrol_runtime(self) -> None:
        device_id = "DA74CDF7-1E16-4F85-BA5B-7D4320FD27DB"
        enriched = smoke_devices._enrich_ios_simulator_runtime_versions(
            [self._synthetic_ios_device(device_id)],
            xcrun_path="/usr/bin/xcrun",
            command_runner=_simctl_runner(udid=device_id, version="26.3"),
        )
        self.assertEqual([item["runtimeVersion"] for item in enriched], ["26.3"])
        self.assertEqual(
            smoke_devices.patrol_ios_runtime_argument(enriched[0]),
            "--ios=26.3",
        )

    def test_unenriched_ios_simulator_has_no_usable_runtime(self) -> None:
        """The synthetic sdk string must never stand in for a runtime identity."""
        with self.assertRaises(ValueError):
            smoke_devices.patrol_ios_runtime_argument(
                self._synthetic_ios_device("DA74CDF7-1E16-4F85-BA5B-7D4320FD27DB")
            )

    def test_enrichment_fails_closed_for_an_absent_simulator(self) -> None:
        with self.assertRaises(RuntimeError) as raised:
            smoke_devices._enrich_ios_simulator_runtime_versions(
                [self._synthetic_ios_device("dry-run-device")],
                xcrun_path="/usr/bin/xcrun",
                command_runner=_simctl_runner(udid="other-udid", version="26.3"),
            )
        self.assertIn("iOS Simulator runtime is unavailable", str(raised.exception))

    def test_dry_run_devices_routes_ios_through_the_same_enrichment(self) -> None:
        with mock.patch.object(
            smoke_devices,
            "_enrich_ios_simulator_runtime_versions",
            side_effect=lambda items: [{**item, "runtimeVersion": "26.3"} for item in items],
        ) as enrichment:
            devices = smoke_devices.dry_run_devices(
                argparse.Namespace(device_id=["device-a"], platform="ios")
            )
        self.assertEqual(enrichment.call_count, 1)
        self.assertEqual([item["runtimeVersion"] for item in devices], ["26.3"])

    def test_android_dry_run_device_needs_no_simulator_runtime(self) -> None:
        devices = smoke_devices.dry_run_devices(
            argparse.Namespace(device_id=["emulator-5556"], platform="android")
        )
        self.assertEqual(
            [item["targetPlatform"] for item in devices],
            ["android-arm64"],
        )
        self.assertIsNone(smoke_devices.patrol_ios_runtime_argument(devices[0]))


if __name__ == "__main__":
    unittest.main()

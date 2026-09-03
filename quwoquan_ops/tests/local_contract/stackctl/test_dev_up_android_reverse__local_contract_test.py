"""Android local transport owns only one target's canonical reverse block."""

from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from quwoquan_ops.cli.lib import dev_up


class DevUpAndroidReverseContractTest(unittest.TestCase):
    def test_switching_target_removes_only_unleased_canonical_mappings(self) -> None:
        topology = {
            "targets": {
                "alpha-local": {"backend": "local", "portProfile": "alpha-local"},
                "beta-local": {"backend": "local", "portProfile": "beta-local"},
                "gamma-local": {"backend": "local", "portProfile": "gamma-local"},
                "prod-sim": {"backend": "local", "portProfile": "prod-sim"},
            }
        }
        manifest = {
            "profiles": {
                name: {"blockStart": start, "blockEnd": start + 999}
                for name, start in (
                    ("alpha-local", 17000),
                    ("beta-local", 18000),
                    ("gamma-local", 19000),
                    ("prod-sim", 16000),
                )
            },
            "roles": {
                "api-edge": {"slotOffset": 0},
                "user-service": {"slotOffset": 210},
            },
        }
        calls: list[list[str]] = []

        def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            if argv[-1] == "--list":
                list_count = sum(call[-1] == "--list" for call in calls)
                output = (
                    "host tcp:17000 tcp:17000\n"
                    "host tcp:17210 tcp:17210\n"
                    "host tcp:54321 tcp:54321\n"
                    if list_count == 1
                    else "host tcp:19000 tcp:19000\nhost tcp:19210 tcp:19210\n"
                )
                return subprocess.CompletedProcess(argv, 0, output, "")
            return subprocess.CompletedProcess(argv, 0, "", "")

        with (
            mock.patch.object(dev_up.shutil, "which", return_value="/usr/bin/adb"),
            mock.patch.object(dev_up, "get_target", side_effect=lambda value, name: value["targets"][name]),
            mock.patch.object(dev_up, "load_port_manifest", return_value=manifest),
            mock.patch.object(dev_up, "active_consumer_leases", return_value=[]),
            mock.patch.object(dev_up.subprocess, "run", side_effect=run),
        ):
            ports = dev_up.enable_android_adb_reverse(
                "emulator-5554",
                "gamma-local",
                topology=topology,
            )

        self.assertEqual(ports, [19000, 19210])
        self.assertIn(
            ["/usr/bin/adb", "-s", "emulator-5554", "reverse", "--remove", "tcp:17000"],
            calls,
        )
        self.assertIn(
            ["/usr/bin/adb", "-s", "emulator-5554", "reverse", "--remove", "tcp:17210"],
            calls,
        )
        self.assertFalse(any(call[-1] == "tcp:54321" for call in calls))

    def test_repeat_same_target_reverse_is_idempotent_without_removals(self) -> None:
        """同设备同 target 的第二次会话不清理既有映射，只做等值重建。"""
        topology = {
            "targets": {
                "alpha-local": {"backend": "local", "portProfile": "alpha-local"},
                "beta-local": {"backend": "local", "portProfile": "beta-local"},
                "gamma-local": {"backend": "local", "portProfile": "gamma-local"},
                "prod-sim": {"backend": "local", "portProfile": "prod-sim"},
            }
        }
        manifest = {
            "profiles": {
                name: {"blockStart": start, "blockEnd": start + 999}
                for name, start in (
                    ("alpha-local", 17000),
                    ("beta-local", 18000),
                    ("gamma-local", 19000),
                    ("prod-sim", 16000),
                )
            },
            "roles": {
                "api-edge": {"slotOffset": 0},
                "user-service": {"slotOffset": 210},
            },
        }
        calls: list[list[str]] = []

        def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            if argv[-1] == "--list":
                # 上一会话已建立的同 target 映射仍然在位。
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    "host tcp:17000 tcp:17000\nhost tcp:17210 tcp:17210\n",
                    "",
                )
            return subprocess.CompletedProcess(argv, 0, "", "")

        with (
            mock.patch.object(dev_up.shutil, "which", return_value="/usr/bin/adb"),
            mock.patch.object(dev_up, "get_target", side_effect=lambda value, name: value["targets"][name]),
            mock.patch.object(dev_up, "load_port_manifest", return_value=manifest),
            mock.patch.object(dev_up, "active_consumer_leases", return_value=[]),
            mock.patch.object(dev_up.subprocess, "run", side_effect=run),
        ):
            ports = dev_up.enable_android_adb_reverse(
                "emulator-5554",
                "alpha-local",
                topology=topology,
            )

        self.assertEqual(ports, [17000, 17210])
        self.assertFalse(
            any("--remove" in call for call in calls),
            calls,
        )

    def test_active_other_target_lease_blocks_before_transport_mutation(self) -> None:
        topology = {
            "targets": {
                "alpha-local": {"backend": "local", "portProfile": "alpha-local"},
                "beta-local": {"backend": "local", "portProfile": "beta-local"},
                "gamma-local": {"backend": "local", "portProfile": "gamma-local"},
                "prod-sim": {"backend": "local", "portProfile": "prod-sim"},
            }
        }

        def leases(target: str, **_: object) -> list[dict[str, str]]:
            return [{"device": "emulator-5554"}] if target == "alpha-local" else []

        with (
            mock.patch.object(dev_up.shutil, "which", return_value="/usr/bin/adb"),
            mock.patch.object(dev_up, "local_target_ports", return_value=[19000]),
            mock.patch.object(dev_up, "active_consumer_leases", side_effect=leases),
            mock.patch.object(dev_up.subprocess, "run") as run,
        ):
            with self.assertRaisesRegex(RuntimeError, "active consumer lease for alpha-local"):
                dev_up.enable_android_adb_reverse(
                    "emulator-5554",
                    "gamma-local",
                    topology=topology,
                )

        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-003
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""Canonical Flutter mobile inventory and device selection authority."""

from __future__ import annotations

import io
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import dev_up


MOBILE_A = {
    "id": "SIM-AAAA",
    "name": "iPhone 15",
    "targetPlatform": "ios",
    "isSupported": True,
}
MOBILE_B = {
    "id": "EMU-BBBB",
    "name": "Pixel 8",
    "targetPlatform": "android-arm64",
    "isSupported": True,
}
DESKTOP = {
    "id": "macos",
    "name": "macOS",
    "targetPlatform": "darwin",
    "isSupported": True,
}


class _TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class DevUpDeviceSelectionContractTest(unittest.TestCase):
    def test_discovery_uses_exact_flutter_and_filters_desktop(self) -> None:
        app_dir = Path("/tmp/qwq-device-authority-app")
        executable = "/opt/flutter/bin/flutter"
        payload = "notice before inventory\n" + json.dumps(
            [MOBILE_A, DESKTOP]
        ) + "\nnotice after inventory\n"
        completed = subprocess.CompletedProcess(
            [executable, "devices", "--machine"], 0, payload, ""
        )
        with mock.patch.object(
            dev_up.subprocess, "run", return_value=completed
        ) as run:
            devices = dev_up.discover_flutter_devices(
                app_dir,
                include_mobile=True,
                include_web=False,
                include_desktop=False,
                flutter_executable=executable,
            )
        self.assertEqual([device["id"] for device in devices], ["SIM-AAAA"])
        run.assert_called_once_with(
            [executable, "devices", "--machine"],
            cwd=str(app_dir),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_discovery_rejects_ambiguous_or_failed_flutter_output(self) -> None:
        ambiguous = subprocess.CompletedProcess(
            ["flutter", "devices", "--machine"],
            0,
            "[]\n[]\n",
            "",
        )
        failed = subprocess.CompletedProcess(
            ["flutter", "devices", "--machine"],
            23,
            "",
            "sdk discovery failed",
        )
        with mock.patch.object(
            dev_up.subprocess, "run", return_value=ambiguous
        ):
            with self.assertRaisesRegex(RuntimeError, "ambiguous JSON arrays"):
                dev_up.discover_flutter_devices(include_web=False)
        with mock.patch.object(dev_up.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "sdk discovery failed"):
                dev_up.discover_flutter_devices(include_web=False)

    def test_single_and_explicit_device_selection_preserve_exact_id(self) -> None:
        self.assertEqual(dev_up.pick_device([MOBILE_A]), "SIM-AAAA")
        self.assertEqual(
            dev_up.select_device(
                [MOBILE_A, MOBILE_B], device_id="  EMU-BBBB  "
            ),
            "EMU-BBBB",
        )
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN"):
            dev_up.select_device([MOBILE_A], device_id="UNKNOWN")

    def test_no_device_and_multi_device_non_tty_are_typed_blocks(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "no Flutter device"):
            dev_up.pick_device([])
        stream_pairs = (
            (io.StringIO(), _TtyBuffer()),
            (_TtyBuffer(), io.StringIO()),
        )
        for stdin, stderr in stream_pairs:
            with self.subTest(
                stdin_tty=stdin.isatty(), stderr_tty=stderr.isatty()
            ), mock.patch.object(
                dev_up.sys, "stdin", stdin
            ), mock.patch.object(
                dev_up.sys, "stderr", stderr
            ):
                with self.assertRaisesRegex(RuntimeError, "--device-id <id>"):
                    dev_up.pick_device([MOBILE_A, MOBILE_B])

    def test_tty_numeric_selection_retries_and_eof_blocks(self) -> None:
        stdin = _TtyBuffer("invalid\n2\n")
        stderr = _TtyBuffer()
        with (
            mock.patch.object(dev_up.sys, "stdin", stdin),
            mock.patch.object(dev_up.sys, "stderr", stderr),
        ):
            selected = dev_up.pick_device([MOBILE_A, MOBILE_B])
        self.assertEqual(selected, "EMU-BBBB")
        self.assertIn("[1]", stderr.getvalue())
        self.assertIn("invalid selection", stderr.getvalue())

        with (
            mock.patch.object(dev_up.sys, "stdin", _TtyBuffer("")),
            mock.patch.object(dev_up.sys, "stderr", _TtyBuffer()),
        ):
            with self.assertRaisesRegex(RuntimeError, "no selection received"):
                dev_up.pick_device([MOBILE_A, MOBILE_B])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "avatar" / "check_device_matrix_gate.py"


def run_gate(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


class CheckDeviceMatrixGateTest(unittest.TestCase):
    def test_allows_missing_android_when_flag_enabled(self) -> None:
        result = run_gate(
            "--discover-result",
            "success",
            "--android-result",
            "skipped",
            "--ios-result",
            "success",
            "--has-android",
            "false",
            "--has-ios",
            "true",
            "--allow-missing-platforms",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("跳过 Android gate", result.stdout)
        self.assertIn("device matrix gate passed", result.stdout)

    def test_requires_missing_android_by_default(self) -> None:
        result = run_gate(
            "--discover-result",
            "success",
            "--android-result",
            "skipped",
            "--ios-result",
            "success",
            "--has-android",
            "false",
            "--has-ios",
            "true",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "android device environment is required, but no Android device was discovered",
            result.stderr,
        )

    def test_discovered_platform_failure_still_blocks(self) -> None:
        result = run_gate(
            "--discover-result",
            "success",
            "--android-result",
            "skipped",
            "--ios-result",
            "failure",
            "--has-android",
            "false",
            "--has-ios",
            "true",
            "--allow-missing-platforms",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ios expected success, got failure", result.stderr)

    def test_requires_at_least_one_mobile_device(self) -> None:
        result = run_gate(
            "--discover-result",
            "success",
            "--android-result",
            "skipped",
            "--ios-result",
            "skipped",
            "--has-android",
            "false",
            "--has-ios",
            "false",
            "--allow-missing-platforms",
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("至少需要一个可见移动设备", result.stderr)


if __name__ == "__main__":
    unittest.main()

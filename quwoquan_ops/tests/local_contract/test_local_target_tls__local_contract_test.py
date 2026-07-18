from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import local_target_tls


class LocalTargetTlsContractTest(unittest.TestCase):
    def test_aliases_resolve_to_one_local_target_set(self) -> None:
        self.assertEqual(
            local_target_tls.normalize_local_tls_target("local-gamma"),
            "gamma-local",
        )
        self.assertEqual(
            local_target_tls.normalize_local_tls_target("prod"),
            "prod-sim",
        )
        with self.assertRaisesRegex(local_target_tls.LocalTargetTlsError, "GATE_BLOCK"):
            local_target_tls.normalize_local_tls_target("prod-hosted")

    def test_root_ca_uses_flat_target_certificate_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            cert_dir = Path(temporary_dir) / "certificates"
            cert_dir.mkdir()
            cert_path = cert_dir / "root.crt"
            cert_path.write_text("certificate", encoding="utf-8")
            with mock.patch.object(
                local_target_tls,
                "certificate_export_dir",
                return_value=cert_dir,
            ):
                self.assertEqual(
                    local_target_tls.resolve_local_target_root_ca("alpha-local"),
                    cert_path,
                )

    def test_ios_install_uses_explicit_udid_not_booted_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            cert_dir = Path(temporary_dir) / "certificates"
            cert_dir.mkdir()
            cert_path = cert_dir / "root.crt"
            cert_path.write_text("certificate", encoding="utf-8")
            recorded: list[list[str]] = []

            def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
                recorded.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with mock.patch.object(
                local_target_tls,
                "certificate_export_dir",
                return_value=cert_dir,
            ):
                result = local_target_tls.install_ios_simulator_root_ca(
                    "alpha-local",
                    "SIMULATOR-UDID",
                    xcrun_path="/usr/bin/xcrun",
                    command_runner=runner,
                )

        self.assertEqual(result["status"], "installed")
        self.assertEqual(
            recorded,
            [[
                "/usr/bin/xcrun",
                "simctl",
                "keychain",
                "SIMULATOR-UDID",
                "add-root-cert",
                str(cert_path),
            ]],
        )
        self.assertNotIn("booted", recorded[0])

    def test_ios_install_fails_closed_on_simctl_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            cert_dir = Path(temporary_dir) / "certificates"
            cert_dir.mkdir()
            (cert_dir / "root.crt").write_text("certificate", encoding="utf-8")
            with (
                mock.patch.object(
                    local_target_tls,
                    "certificate_export_dir",
                    return_value=cert_dir,
                ),
                self.assertRaisesRegex(
                    local_target_tls.LocalTargetTlsError,
                    "failed to install local root CA",
                ),
            ):
                local_target_tls.install_ios_simulator_root_ca(
                    "beta-local",
                    "SIMULATOR-UDID",
                    xcrun_path="/usr/bin/xcrun",
                    command_runner=lambda argv, **_: subprocess.CompletedProcess(
                        argv,
                        1,
                        stdout="",
                        stderr="simctl rejected certificate",
                    ),
                )


    def test_ios_simulator_detection_uses_simctl_inventory(self) -> None:
        output = """{
          "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-18-0": [
              {"udid": "SIM-UDID", "name": "iPhone"}
            ]
          }
        }"""
        runner = lambda argv, **_: subprocess.CompletedProcess(
            argv,
            0,
            stdout=output,
            stderr="",
        )

        self.assertTrue(
            local_target_tls.is_ios_simulator_device(
                "SIM-UDID",
                xcrun_path="/usr/bin/xcrun",
                command_runner=runner,
            )
        )
        self.assertFalse(
            local_target_tls.is_ios_simulator_device(
                "physical-device",
                xcrun_path="/usr/bin/xcrun",
                command_runner=runner,
            )
        )

    def test_alpha_ios_prepare_fails_without_explicit_simulator_udid(self) -> None:
        script = (
            ROOT
            / "quwoquan_app"
            / "scripts"
            / "ios"
            / "prepare_alpha_local_https.sh"
        )
        env = os.environ.copy()
        env.update(
            {
                "EFFECTIVE_PLATFORM_NAME": "-iphonesimulator",
                "PLATFORM_NAME": "iphonesimulator",
                "QWQ_IOS_SIMULATOR_UDID": "",
                "TARGET_DEVICE_IDENTIFIER": "",
            },
        )

        result = subprocess.run(
            ["bash", str(script)],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("GATE_BLOCK: Simulator CA trust needs", result.stderr)
        self.assertIn("Repair:", result.stderr)

    def test_local_target_tls_cli_runs_from_an_arbitrary_working_directory(self) -> None:
        script = ROOT / "quwoquan_ops" / "cli" / "lib" / "local_target_tls.py"

        with tempfile.TemporaryDirectory() as temporary_dir:
            result = subprocess.run(
                [sys.executable, str(script), "--help"],
                text=True,
                capture_output=True,
                check=False,
                cwd=temporary_dir,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("resolve-root-ca", result.stdout)


if __name__ == "__main__":
    unittest.main()

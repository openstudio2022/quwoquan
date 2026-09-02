# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004

from __future__ import annotations

import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))

from verify_ios_hot_restart import _build_parser as build_hot_restart_parser


OWNED_SOURCES = (
    APP_DIR / "scripts/device/startup_first_frame/android_capture.py",
    APP_DIR / "scripts/device/startup_first_frame/cli.py",
    APP_DIR / "scripts/device/startup_first_frame/ios_capture.py",
    APP_DIR / "scripts/device/startup_first_frame/startup_log.py",
    APP_DIR / "scripts/device/verify_startup_web.py",
    APP_DIR / "scripts/device/build_startup_environment_matrix.py",
    APP_DIR / "scripts/device/run_dual_platform_usability_matrix.py",
    APP_DIR / "scripts/device/verify_ios_hot_restart.py",
    (
        APP_DIR
        / "scripts/runtime/platform/startup_environment_matrix/behavior_fingerprint.py"
    ),
    (
        APP_DIR
        / "scripts/runtime/platform/startup_environment_matrix/evidence_validation.py"
    ),
    (
        APP_DIR
        / "scripts/runtime/platform/startup_environment_matrix/package_probe.py"
    ),
)


class StartupLaunchIdentityProtocolContractTest(unittest.TestCase):
    def test_owned_python_sources_have_no_legacy_identity_protocol(self) -> None:
        legacy_tokens = (
            "launch" + "Mode",
            "direct_flutter" + "_" + "run",
            "--launch" + "-mode",
            "QWQ_APP_LAUNCH" + "_" + "MODE",
        )
        for path in OWNED_SOURCES:
            source = path.read_text(encoding="utf-8")
            for token in legacy_tokens:
                with self.subTest(path=path.name, token=token):
                    self.assertNotIn(token, source)

    def test_handoff_callers_use_canonical_launch_provenance(self) -> None:
        callers = (
            APP_DIR / "scripts/device/build_startup_environment_matrix.py",
            APP_DIR / "scripts/device/run_dual_platform_usability_matrix.py",
            (
                APP_DIR
                / "scripts/runtime/platform/startup_environment_matrix/package_probe.py"
            ),
        )
        for path in callers:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn('"--launch-provenance"', source)
                self.assertIn('"canonical_launcher"', source)

    def test_evidence_keeps_provenance_and_supply_mode_orthogonal(self) -> None:
        producers = (
            APP_DIR / "scripts/device/startup_first_frame/cli.py",
            APP_DIR / "scripts/device/verify_startup_web.py",
            APP_DIR / "scripts/device/verify_ios_hot_restart.py",
            (
                APP_DIR
                / "scripts/runtime/platform/startup_environment_matrix/"
                "evidence_validation.py"
            ),
        )
        for path in producers:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("launchProvenance", source)
                self.assertIn("runtimeConfigSupplyMode", source)

    def test_hot_restart_cli_accepts_only_canonical_provenance_surface(self) -> None:
        args = build_hot_restart_parser().parse_args(
            [
                "--env",
                "alpha",
                "--device-id",
                "simulator-id",
                "--launch-provenance",
                "canonical_launcher",
            ]
        )
        self.assertEqual(args.launch_provenance, "canonical_launcher")
        # workspace facade 已退役：workspace_flutter_run 不再是可选 provenance。
        with self.assertRaises(SystemExit):
            build_hot_restart_parser().parse_args(
                [
                    "--env",
                    "alpha",
                    "--device-id",
                    "simulator-id",
                    "--launch-provenance",
                    "workspace_flutter_run",
                ]
            )

    def test_native_safe_terminal_marker_preserves_canonical_surface(self) -> None:
        android = (
            APP_DIR
            / "android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java"
        ).read_text(encoding="utf-8")
        android_surface = (
            APP_DIR
            / "android/app/src/main/java/com/quwoquan/quwoquan_app/"
            "StartupSafeTerminalSurface.java"
        ).read_text(encoding="utf-8")
        ios = (APP_DIR / "ios/Runner/AppDelegate.swift").read_text(
            encoding="utf-8"
        )

        self.assertIn("StartupSafeTerminalSurface.fromEvent", android)
        self.assertIn('"android_startup_safe_terminal surface="', android)
        self.assertIn(
            '"android_startup_safe_terminal_rejected surface="', android
        )
        self.assertIn("StartupSafeTerminalSurface.parse(event: event)", ios)
        self.assertIn("ios_startup_safe_terminal surface=%@", ios)
        self.assertIn("ios_startup_safe_terminal_rejected surface=%@", ios)
        for recovery_surface in ("safe_recovery", "flutter_recovery"):
            with self.subTest(surface=recovery_surface):
                self.assertIn(recovery_surface, android_surface)
                self.assertIn(recovery_surface, ios)


if __name__ == "__main__":
    unittest.main()

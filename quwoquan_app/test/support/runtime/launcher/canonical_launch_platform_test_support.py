from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock


APP_DIR = Path(__file__).resolve().parents[4]
ROOT = APP_DIR.parent
for import_root in (ROOT, APP_DIR / "scripts/device"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import run_app_instance as executor
import supervise_app_launch as supervisor
from quwoquan_ops.cli.lib.app_launch_attempt import read_app_launch_attempt


SUPERVISOR = APP_DIR / "scripts/device/supervise_app_launch.py"


class CanonicalLaunchPlatformContractMixin:
    def test_iphone_runtime_read_distinguishes_absence_from_structured_failure(self) -> None:
        driver = executor.IOSPhysicalPlatformDriver(
            device_id="IPHONE-1",
            application_id="com.leadwise.quwoquan.nonprod.debug",
            entrypoint="lib/main_prod.dart",
        )
        for listing in (
            {"result": {"files": []}},
            {"result": {"items": []}},
        ):
            with self.subTest(absent_listing=listing), mock.patch.object(
                driver, "_devicectl", return_value=listing
            ):
                self.assertIsNone(
                    driver.read_runtime_file(executor.ACTIVE_RECEIPT_FILE_NAME)
                )

        for listing in (
            {},
            {"result": None},
            {"result": {}},
            {"result": {"files": "not-a-list"}},
            {"result": {"files": ["not-an-object"]}},
        ):
            with self.subTest(invalid_listing=listing), mock.patch.object(
                driver, "_devicectl", return_value=listing
            ):
                with self.assertRaisesRegex(
                    executor.CanonicalExecutorError,
                    "iPhone runtime receipt listing",
                ):
                    driver.read_runtime_file(executor.ACTIVE_RECEIPT_FILE_NAME)

    def test_supervisor_never_infers_install_phases_from_device_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "attempt.json"
            child = (
                "print('QWQ_APP_LAUNCH_PHASE status=compiled', flush=True)\n"
                "raise SystemExit(2)"
            )
            with mock.patch.object(supervisor.signal, "signal"), mock.patch.object(
                sys,
                "argv",
                [
                    "supervise_app_launch.py",
                    "--receipt",
                    str(receipt),
                    "--environment",
                    "alpha",
                    "--target",
                    "alpha-local",
                    "--platform",
                    "android",
                    "--build-mode",
                    "debug",
                    "--run-mode",
                    "ui-only",
                    "--device",
                    "device-1",
                    "--application-id",
                    "com.leadwise.quwoquan.nonprod.debug",
                    "--",
                    sys.executable,
                    "-c",
                    child,
                ],
            ):
                self.assertEqual(supervisor.main(), 2)
            payload = read_app_launch_attempt(receipt)

        self.assertEqual(payload["firstBlocker"], "APP.LAUNCH.install_failed")
        self.assertEqual(
            [item["status"] for item in payload["transitions"]],
            ["prepared", "compiling", "compiled", "failed"],
        )

    def test_supervisor_maps_configuring_failure_without_inventing_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "attempt.json"
            child = (
                "for phase in ('compiled','installing','installed','configuring'): "
                "print(f'QWQ_APP_LAUNCH_PHASE status={phase}', flush=True)\n"
                "raise SystemExit(2)"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SUPERVISOR),
                    "--receipt",
                    str(receipt),
                    "--environment",
                    "alpha",
                    "--target",
                    "alpha-local",
                    "--platform",
                    "android",
                    "--build-mode",
                    "debug",
                    "--run-mode",
                    "ui-only",
                    "--device",
                    "device-1",
                    "--",
                    sys.executable,
                    "-c",
                    child,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            payload = read_app_launch_attempt(receipt)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(
            payload["firstBlocker"],
            "APP.LAUNCH.runtime_config_activation_failed",
        )
        self.assertEqual(
            [item["status"] for item in payload["transitions"]],
            [
                "prepared",
                "compiling",
                "compiled",
                "installing",
                "installed",
                "configuring",
                "failed",
            ],
        )

    def test_platform_drivers_execute_canonical_install_and_launch_commands(self) -> None:
        application_id = "com.leadwise.quwoquan.nonprod.debug"
        digest = "sha256:" + "a" * 64
        android = executor.AndroidPlatformDriver(
            device_id="android-1",
            application_id=application_id,
            entrypoint="lib/main_prod.dart",
        )
        with mock.patch.object(executor, "_run_checked") as run_checked:
            android.install()
            android.launch_activation(digest)
            android.launch_application()
        component = (
            f"{application_id}/com.quwoquan.quwoquan_app.StartupGateActivity"
        )
        self.assertEqual(
            run_checked.call_args_list,
            [
                mock.call(
                    [
                        "adb",
                        "-s",
                        "android-1",
                        "install",
                        "-r",
                        "-t",
                        str(android.artifact_path()),
                    ]
                ),
                mock.call(
                    [
                        "adb",
                        "-s",
                        "android-1",
                        "shell",
                        "am",
                        "start",
                        "-S",
                        "-W",
                        "-n",
                        component,
                        "--es",
                        executor.ANDROID_REQUEST_DIGEST_EXTRA,
                        digest,
                    ]
                ),
                mock.call(
                    [
                        "adb",
                        "-s",
                        "android-1",
                        "shell",
                        "am",
                        "start",
                        "-S",
                        "-W",
                        "-n",
                        component,
                    ]
                ),
            ],
        )

        simulator = executor.IOSSimulatorPlatformDriver(
            device_id="SIM-1",
            application_id=application_id,
            entrypoint="lib/main_prod.dart",
        )
        with mock.patch.object(executor, "_run_checked") as run_checked:
            simulator.install()
            simulator.launch_activation(digest)
            simulator.launch_application()
        self.assertEqual(
            run_checked.call_args_list,
            [
                mock.call(
                    [
                        "xcrun",
                        "simctl",
                        "install",
                        "SIM-1",
                        str(simulator.artifact_path()),
                    ]
                ),
                mock.call(
                    [
                        "xcrun",
                        "simctl",
                        "launch",
                        "--terminate-running-process",
                        "SIM-1",
                        application_id,
                        executor.IOS_REQUEST_DIGEST_ARGUMENT,
                        digest,
                    ]
                ),
                mock.call(
                    [
                        "xcrun",
                        "simctl",
                        "launch",
                        "--terminate-running-process",
                        "SIM-1",
                        application_id,
                    ]
                ),
            ],
        )

        iphone = executor.IOSPhysicalPlatformDriver(
            device_id="IPHONE-1",
            application_id=application_id,
            entrypoint="lib/main_prod.dart",
        )
        with mock.patch.object(iphone, "_devicectl", return_value={}) as devicectl:
            iphone.install()
            iphone.launch_activation(digest)
            iphone.launch_application()
        self.assertEqual(
            devicectl.call_args_list,
            [
                mock.call(
                    [
                        "device",
                        "install",
                        "app",
                        "--device",
                        "IPHONE-1",
                        str(iphone.artifact_path()),
                    ]
                ),
                mock.call(
                    [
                        "device",
                        "process",
                        "launch",
                        "--device",
                        "IPHONE-1",
                        "--terminate-existing",
                        application_id,
                        executor.IOS_REQUEST_DIGEST_ARGUMENT,
                        digest,
                    ]
                ),
                mock.call(
                    [
                        "device",
                        "process",
                        "launch",
                        "--device",
                        "IPHONE-1",
                        "--terminate-existing",
                        application_id,
                    ]
                ),
            ],
        )
        for driver in (android, simulator, iphone):
            command = driver.build_command()
            self.assertEqual(command[:2], ["flutter", "build"])
            self.assertNotIn("run", command)
            self.assertFalse(any("dart-define" in item for item in command))

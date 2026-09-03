# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

APP_DIR = Path(__file__).resolve().parents[3]
ROOT = APP_DIR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(APP_DIR / "scripts/device"))

import run_app_instance as executor


class _ImmediateThread:
    def __init__(self, *, target: object, daemon: bool) -> None:
        del daemon
        self.target = target

    def start(self) -> None:
        self.target()


class _AttachProcess:
    def __init__(self, *lines: str, wait_timeouts: int = 0) -> None:
        self.pid = 4100 + wait_timeouts
        self.stdout = list(lines)
        self.wait_timeouts = wait_timeouts
        self.wait_calls: list[float | None] = []

    @staticmethod
    def poll() -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        if self.wait_timeouts > 0:
            self.wait_timeouts -= 1
            raise subprocess.TimeoutExpired("flutter attach", timeout)
        return 0 if timeout is None and len(self.wait_calls) == 1 else -signal.SIGKILL


class CanonicalLaunchExecutorProcessContractTest(unittest.TestCase):
    def test_attach_argument_sanitizer_rejects_executor_owned_inputs(self) -> None:
        for arguments in (
            ("--flavor", "prod"),
            ("--flavor=prod",),
            ("--dart-define", "ENV=prod"),
            ("--dart-define=ENV=prod",),
            ("-DENV=prod",),
            ("--debug-uri", "http://127.0.0.1:9999/token/"),
            ("--debug-uri=http://127.0.0.1:9999/token/",),
            ("--vm-service-port", "4567"),
            ("--vm-service-port=4567",),
            ("--device-timeout", "5"),
            ("--device-timeout=5",),
            ("--device-connection", "wireless"),
            ("--device-user", "10"),
            ("--release",),
            ("--machine",),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(executor.CanonicalExecutorError):
                    executor._sanitize_attach_arguments(arguments)

        for arguments in (
            ("-d", "device-1"),
            ("--device-id", "device-1"),
            ("--device-id=device-1",),
            ("-d",),
            ("--device-id",),
        ):
            with self.subTest(device_arguments=arguments):
                with self.assertRaises(executor.CanonicalExecutorError):
                    executor._sanitize_attach_arguments(arguments)

        self.assertEqual(executor._sanitize_attach_arguments(("--verbose",)), ["--verbose"])

    def test_main_rejects_executor_owned_attach_inputs_before_platform_actions(
        self,
    ) -> None:
        driver = mock.Mock()
        with mock.patch.object(
            executor,
            "_load_handoff",
            return_value={},
        ), mock.patch.object(
            executor,
            "build_platform_driver",
            return_value=driver,
        ), mock.patch.object(
            sys,
            "argv",
            [
                "run_app_instance.py",
                "--device-kind",
                "android_emulator",
                "--device",
                "device-1",
                "--application-id",
                "com.leadwise.quwoquan.nonprod.debug",
                "--entrypoint",
                "lib/main_prod.dart",
                "--",
                "--dart-define=APP_RUNTIME_ENV=prod",
            ],
        ):
            self.assertEqual(executor.main(), 2)

        driver.build.assert_not_called()
        driver.install.assert_not_called()
        driver.write_activation_request.assert_not_called()
        driver.launch_activation.assert_not_called()
        driver.launch_application.assert_not_called()
        driver.attach.assert_not_called()

    def test_main_rejects_invalid_timeouts_before_loading_inputs_or_platform_actions(
        self,
    ) -> None:
        for flag, value in (
            ("--activation-timeout-seconds", "0"),
            ("--activation-timeout-seconds", "-1"),
            ("--activation-timeout-seconds", "nan"),
            ("--activation-timeout-seconds", "inf"),
            ("--attach-timeout-seconds", "0"),
            ("--attach-timeout-seconds", "-1"),
            ("--attach-timeout-seconds", "nan"),
            ("--attach-timeout-seconds", "inf"),
        ):
            with self.subTest(flag=flag, value=value), mock.patch.object(
                executor,
                "_load_handoff",
            ) as load_handoff, mock.patch.object(
                executor,
                "build_platform_driver",
            ) as build_driver, mock.patch.object(
                sys,
                "argv",
                [
                    "run_app_instance.py",
                    "--device-kind",
                    "android_emulator",
                    "--device",
                    "device-1",
                    "--application-id",
                    "com.leadwise.quwoquan.nonprod.debug",
                    "--entrypoint",
                    "lib/main_prod.dart",
                    flag,
                    value,
                ],
            ):
                with self.assertRaises(SystemExit) as raised:
                    executor.main()
                self.assertEqual(raised.exception.code, 2)
                load_handoff.assert_not_called()
                build_driver.assert_not_called()

    def test_launcher_rejects_device_conflicts_and_invalid_timeouts_before_tools(
        self,
    ) -> None:
        launcher = APP_DIR / "run.sh"
        cases = (
            (["-d"], {}, "requires a device id"),
            (
                ["-d", "device-a", "--device-id=device-b"],
                {},
                "conflicting device selectors",
            ),
            (
                ["-d", "device-a"],
                {"QWQ_APP_ACTIVATION_TIMEOUT_SECONDS": "nan"},
                "positive finite numbers",
            ),
            (
                ["-d", "device-a"],
                {"QWQ_APP_LAUNCH_TIMEOUT_SECONDS": "0"},
                "positive finite numbers",
            ),
            (
                ["-d", "device-a", "--dart-define=APP_RUNTIME_ENV=prod"],
                {},
                "APP.LAUNCH.managed_argument_unsupported",
            ),
            (
                ["-d", "device-a", "--debug-uri=http://127.0.0.1:9999/token/"],
                {},
                "APP.LAUNCH.managed_argument_unsupported",
            ),
            (
                ["-d", "device-a", "--vm-service-port=4567"],
                {},
                "APP.LAUNCH.managed_argument_unsupported",
            ),
            (
                ["-d", "device-a", "--device-timeout", "5"],
                {},
                "APP.LAUNCH.managed_argument_unsupported",
            ),
        )
        for arguments, overrides, expected_error in cases:
            with self.subTest(arguments=arguments, overrides=overrides), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                tool_log = root / "tools.log"
                for tool in ("flutter", "adb", "xcrun"):
                    executable = root / tool
                    executable.write_text(
                        "#!/usr/bin/env bash\n"
                        f"printf '%s\\n' {tool!r} >> {str(tool_log)!r}\n"
                        "exit 97\n",
                        encoding="utf-8",
                    )
                    executable.chmod(0o755)
                environment = {
                    **os.environ,
                    "PATH": f"{root}{os.pathsep}{os.environ.get('PATH', '')}",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    **overrides,
                }
                result = subprocess.run(
                    ["bash", str(launcher), *arguments],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    2,
                    result.stdout + result.stderr,
                )
                self.assertIn(expected_error, result.stderr)
                self.assertFalse(tool_log.exists())

    def test_attach_timeout_terminates_and_reaps_the_process_group(self) -> None:
        process = _AttachProcess(wait_timeouts=1)
        driver = executor.AndroidPlatformDriver(
            device_id="device-1",
            application_id="com.leadwise.quwoquan.nonprod.debug",
            entrypoint="lib/main_prod.dart",
        )
        with mock.patch.object(
            executor.subprocess, "Popen", return_value=process
        ), mock.patch.object(
            executor.time, "monotonic", side_effect=(0.0, 2.0)
        ), mock.patch.object(executor.os, "killpg") as killpg:
            with self.assertRaisesRegex(
                executor.CanonicalExecutorError,
                "did not establish a VM service session",
            ):
                driver.attach((), timeout_seconds=1.0, on_attached=lambda: None)

        self.assertEqual(
            killpg.call_args_list,
            [mock.call(process.pid, signal.SIGTERM), mock.call(process.pid, signal.SIGKILL)],
        )
        self.assertEqual(process.wait_calls, [5.0, None])

    def test_attach_interrupt_escalates_and_reaps_before_returning(self) -> None:
        process = _AttachProcess(wait_timeouts=2)
        driver = executor.AndroidPlatformDriver(
            device_id="device-1",
            application_id="com.leadwise.quwoquan.nonprod.debug",
            entrypoint="lib/main_prod.dart",
        )
        with mock.patch.object(
            executor.subprocess, "Popen", return_value=process
        ), mock.patch.object(
            executor.queue.Queue, "get", side_effect=KeyboardInterrupt
        ), mock.patch.object(executor.os, "killpg") as killpg:
            self.assertEqual(
                driver.attach((), timeout_seconds=10.0, on_attached=lambda: None),
                130,
            )

        self.assertEqual(
            killpg.call_args_list,
            [
                mock.call(process.pid, signal.SIGINT),
                mock.call(process.pid, signal.SIGTERM),
                mock.call(process.pid, signal.SIGKILL),
            ],
        )
        self.assertEqual(process.wait_calls, [5.0, 5.0, None])

    def test_attach_term_and_hup_forward_escalate_and_reap_before_returning(self) -> None:
        cases = (
            (
                signal.SIGTERM,
                1,
                [signal.SIGTERM, signal.SIGKILL],
                [5.0, None],
            ),
            (
                signal.SIGHUP,
                2,
                [signal.SIGHUP, signal.SIGTERM, signal.SIGKILL],
                [5.0, 5.0, None],
            ),
        )
        for received_signal, wait_timeouts, expected_signals, expected_waits in cases:
            with self.subTest(received_signal=received_signal):
                process = _AttachProcess(wait_timeouts=wait_timeouts)
                driver = executor.AndroidPlatformDriver(
                    device_id="device-1",
                    application_id="com.leadwise.quwoquan.nonprod.debug",
                    entrypoint="lib/main_prod.dart",
                )
                handlers: dict[int, object] = {}

                def install_handler(signum: int, handler: object) -> object:
                    if callable(handler):
                        handlers[signum] = handler
                    return signal.SIG_DFL

                def receive_signal(*_: object, **__: object) -> None:
                    handler = handlers[received_signal]
                    assert callable(handler)
                    handler(received_signal, None)

                with mock.patch.object(
                    executor.subprocess, "Popen", return_value=process
                ), mock.patch.object(
                    executor.signal, "signal", side_effect=install_handler
                ), mock.patch.object(
                    executor.queue.Queue, "get", side_effect=receive_signal
                ), mock.patch.object(executor.os, "killpg") as killpg:
                    self.assertEqual(
                        driver.attach(
                            (), timeout_seconds=10.0, on_attached=lambda: None
                        ),
                        128 + received_signal,
                    )

                self.assertEqual(
                    killpg.call_args_list,
                    [mock.call(process.pid, item) for item in expected_signals],
                )
                self.assertEqual(process.wait_calls, expected_waits)
                self.assertIn(signal.SIGTERM, handlers)
                self.assertIn(signal.SIGHUP, handlers)

    def test_attach_callback_failure_terminates_and_reaps_process_group(self) -> None:
        process = _AttachProcess(
            '[{"event":"app.started","params":{"appId":"daemon-app-1"}}]\n',
            wait_timeouts=1,
        )
        driver = executor.AndroidPlatformDriver(
            device_id="device-1",
            application_id="com.leadwise.quwoquan.nonprod.debug",
            entrypoint="lib/main_prod.dart",
        )
        with mock.patch.object(
            executor.subprocess, "Popen", return_value=process
        ), mock.patch.object(
            executor.threading, "Thread", _ImmediateThread
        ), mock.patch.object(executor.os, "killpg") as killpg:
            with self.assertRaisesRegex(RuntimeError, "phase receipt write failed"):
                driver.attach(
                    (),
                    timeout_seconds=10.0,
                    on_attached=mock.Mock(
                        side_effect=RuntimeError("phase receipt write failed")
                    ),
                )

        self.assertEqual(
            killpg.call_args_list,
            [mock.call(process.pid, signal.SIGTERM), mock.call(process.pid, signal.SIGKILL)],
        )
        self.assertEqual(process.wait_calls, [5.0, None])


if __name__ == "__main__":
    unittest.main()

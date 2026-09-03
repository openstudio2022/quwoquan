# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""iOS Simulator VM-service discovery, attach evidence, and token safety."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

APP_DIR = Path(__file__).resolve().parents[3]
ROOT = APP_DIR.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(APP_DIR / "scripts/device"))

import canonical_app_instance.ios_vm_service as vm_service
import run_app_instance as executor


class _ImmediateThread:
    def __init__(self, *, target: object, daemon: bool) -> None:
        del daemon
        self.target = target

    def start(self) -> None:
        self.target()


class _DormantThread(_ImmediateThread):
    def start(self) -> None:
        return None


class _Process:
    def __init__(self, *lines: str, wait_timeouts: int = 0) -> None:
        self.pid = 59042
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
            raise subprocess.TimeoutExpired("dns-sd", timeout)
        return 0


def _launch_identity(
    *,
    device_id: str = "simulator-1",
    process_id: int = 82001,
) -> vm_service.IOSSimulatorLaunch:
    return vm_service.IOSSimulatorLaunch(
        device_id=device_id,
        application_id="com.example.app",
        process_id=process_id,
        log_start="2026-08-29 08:00:00+0800",
    )


class IOSSimulatorVMServiceContractTest(unittest.TestCase):
    def test_mdns_lookup_uses_loopback_record_and_clean_environment(self) -> None:
        process = _Process(
            "Lookup com.example.app._dartVmService._tcp.local.\n",
            "com.example.app._dartVmService._tcp.local. "
            "can be reached at Mac.local.:59042 (interface 15) Flags: 1\n",
            " authCode=YRbGVkjtl4o=\n",
        )
        with mock.patch.dict(
            os.environ,
            {"QWQ_ANDROID_RELEASE_STORE_PASSWORD": "secret"},
            clear=False,
        ), mock.patch.object(
            vm_service.subprocess,
            "Popen",
            return_value=process,
        ) as popen, mock.patch.object(
            vm_service.threading,
            "Thread",
            _ImmediateThread,
        ), mock.patch.object(
            vm_service,
            "_terminate_lookup_process",
        ) as terminate, mock.patch.object(
            vm_service.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                ["lsof"], 0, stdout="p82001\n", stderr=""
            ),
        ) as ownership:
                debug_url = vm_service.resolve_ios_simulator_debug_url(
                    _launch_identity(),
                    timeout_seconds=60.0,
                )

        self.assertEqual(debug_url, "http://127.0.0.1:59042/YRbGVkjtl4o%3D/")
        self.assertEqual(
            popen.call_args.args[0],
            [
                "dns-sd",
                "-L",
                "com.example.app",
                "_dartVmService._tcp",
                "local.",
            ],
        )
        self.assertNotIn(
            "QWQ_ANDROID_RELEASE_STORE_PASSWORD",
            popen.call_args.kwargs["env"],
        )
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        terminate.assert_called_once_with(process)
        self.assertEqual(
            ownership.call_args.args[0],
            [
                "/usr/sbin/lsof",
                "-nP",
                "-iTCP:59042",
                "-sTCP:LISTEN",
                "-Fp",
            ],
        )
        self.assertNotIn(
            "QWQ_ANDROID_RELEASE_STORE_PASSWORD",
            ownership.call_args.kwargs["env"],
        )

    def test_mdns_lookup_rejects_invalid_port_without_exposing_token(self) -> None:
        token = "SensitiveToken="
        process = _Process(
            "com.example.app._dartVmService._tcp.local. "
            "can be reached at Mac.local.:70000 (interface 15)\n",
            f" authCode={token}\n",
        )
        with mock.patch.object(
            vm_service.subprocess,
            "Popen",
            return_value=process,
        ), mock.patch.object(
            vm_service.threading,
            "Thread",
            _ImmediateThread,
        ), mock.patch.object(
            vm_service,
            "_terminate_lookup_process",
        ), self.assertRaisesRegex(
            executor.CanonicalExecutorError,
            "invalid port",
        ) as raised:
            vm_service.resolve_ios_simulator_debug_url(
                _launch_identity(),
                timeout_seconds=1.0,
            )

        self.assertNotIn(token, str(raised.exception))

    def test_mdns_lookup_rejects_two_complete_records_without_tokens(self) -> None:
        first_token = "FirstSimulatorToken="
        second_token = "SecondSimulatorToken="
        process = _Process(
            "com.example.app._dartVmService._tcp.local. "
            "can be reached at Mac.local.:59042 (interface 1)\n",
            f" authCode={first_token}\n",
            "com.example.app._dartVmService._tcp.local. "
            "can be reached at Mac.local.:59043 (interface 1)\n",
            f" authCode={second_token}\n",
        )
        with mock.patch.object(
            vm_service.subprocess,
            "Popen",
            return_value=process,
        ), mock.patch.object(
            vm_service.threading,
            "Thread",
            _ImmediateThread,
        ), mock.patch.object(
            vm_service,
            "_terminate_lookup_process",
        ), mock.patch.object(
            vm_service.subprocess,
            "run",
        ) as ownership, self.assertRaisesRegex(
            executor.CanonicalExecutorError,
            "ambiguous iOS Simulator VM service records",
        ) as raised:
            vm_service.resolve_ios_simulator_debug_url(
                _launch_identity(device_id="simulator-2"),
                timeout_seconds=1.0,
            )

        ownership.assert_not_called()
        self.assertNotIn(first_token, str(raised.exception))
        self.assertNotIn(second_token, str(raised.exception))

    def test_mdns_lookup_rejects_duplicate_complete_record(self) -> None:
        token = "RepeatedSimulatorToken="
        process = _Process(
            "com.example.app._dartVmService._tcp.local. "
            "can be reached at Mac.local.:59042 (interface 1)\n",
            f" authCode={token}\n",
            "com.example.app._dartVmService._tcp.local. "
            "can be reached at Mac.local.:59042 (interface 1)\n",
            f" authCode={token}\n",
        )
        with mock.patch.object(
            vm_service.subprocess,
            "Popen",
            return_value=process,
        ), mock.patch.object(
            vm_service.threading,
            "Thread",
            _ImmediateThread,
        ), mock.patch.object(
            vm_service,
            "_terminate_lookup_process",
        ), mock.patch.object(
            vm_service.subprocess,
            "run",
        ) as ownership, self.assertRaisesRegex(
            executor.CanonicalExecutorError,
            "ambiguous iOS Simulator VM service records",
        ) as raised:
            vm_service.resolve_ios_simulator_debug_url(
                _launch_identity(),
                timeout_seconds=1.0,
            )

        ownership.assert_not_called()
        self.assertNotIn(token, str(raised.exception))

    def test_mdns_lookup_is_capped_at_fifteen_seconds(self) -> None:
        process = _Process()
        with mock.patch.object(
            vm_service.subprocess,
            "Popen",
            return_value=process,
        ), mock.patch.object(
            vm_service.threading,
            "Thread",
            _DormantThread,
        ), mock.patch.object(
            vm_service.time,
            "monotonic",
            side_effect=(100.0, 116.0),
        ), mock.patch.object(
            vm_service,
            "_terminate_lookup_process",
        ), self.assertRaisesRegex(
            executor.CanonicalExecutorError,
            "within 15s",
        ):
            vm_service.resolve_ios_simulator_debug_url(
                _launch_identity(),
                timeout_seconds=600.0,
            )

    def test_mdns_lookup_rejects_other_simulator_process_for_same_bundle(self) -> None:
        token = "OtherSimulatorToken="
        process = _Process(
            "com.example.app._dartVmService._tcp.local. "
            "can be reached at Mac.local.:59042 (interface 1)\n",
            f" authCode={token}\n",
        )
        with mock.patch.object(
            vm_service.subprocess,
            "Popen",
            return_value=process,
        ), mock.patch.object(
            vm_service.threading,
            "Thread",
            _ImmediateThread,
        ), mock.patch.object(
            vm_service,
            "_terminate_lookup_process",
        ), mock.patch.object(
            vm_service.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                ["lsof"], 0, stdout="p81000\n", stderr=""
            ),
        ), self.assertRaisesRegex(
            executor.CanonicalExecutorError,
            "not bound to the selected device process",
        ) as raised:
            vm_service.resolve_ios_simulator_debug_url(
                _launch_identity(device_id="simulator-2"),
                timeout_seconds=1.0,
            )

        self.assertNotIn(token, str(raised.exception))

    def test_vm_service_redaction_covers_uri_and_inline_auth_code(self) -> None:
        token = "SensitiveToken="
        line = f"authCode={token} ws://127.0.0.1:57527/{token}/ws"

        redacted = vm_service.redact_vm_service_tokens(line)

        self.assertNotIn(token, redacted)
        self.assertIn("<redacted-vm-service-auth-code>", redacted)
        self.assertIn("<redacted-vm-service-uri>", redacted)

    def test_driver_binds_vm_lookup_to_selected_simulator_launch_pid(self) -> None:
        driver = executor.IOSSimulatorPlatformDriver(
            device_id="simulator-2",
            application_id="com.example.app",
            entrypoint="lib/main_prod.dart",
        )
        with mock.patch.object(
            vm_service,
            "launch_selected_simulator_application",
            return_value=_launch_identity(device_id="simulator-2"),
        ) as launch:
            driver.launch_application()
        with mock.patch.object(
            vm_service,
            "resolve_ios_simulator_debug_url",
            return_value="http://127.0.0.1:59042/token/",
        ) as resolve:
            result = driver.resolve_attach_debug_url(2.0)

        self.assertEqual(result, "http://127.0.0.1:59042/token/")
        self.assertEqual(
            launch.call_args,
            mock.call("simulator-2", "com.example.app"),
        )
        self.assertEqual(
            resolve.call_args,
            mock.call(
                _launch_identity(device_id="simulator-2"),
                timeout_seconds=2.0,
            ),
        )

    def test_device_scoped_launch_returns_exact_pid_and_clean_environment(self) -> None:
        completed = subprocess.CompletedProcess(
            ["xcrun"],
            0,
            stdout="com.example.app: 82001\n",
            stderr="",
        )
        with mock.patch.dict(
            os.environ,
            {"QWQ_ANDROID_RELEASE_STORE_PASSWORD": "secret"},
            clear=False,
        ), mock.patch.object(
            vm_service,
            "_terminate_selected_application",
        ) as terminate, mock.patch.object(
            vm_service.subprocess,
            "run",
            return_value=completed,
        ) as run:
            launch = vm_service.launch_selected_simulator_application(
                "simulator-2",
                "com.example.app",
            )

        self.assertEqual(launch.device_id, "simulator-2")
        self.assertEqual(launch.application_id, "com.example.app")
        self.assertEqual(launch.process_id, 82001)
        self.assertNotRegex(launch.log_start, r"\.\d{6}")
        parsed_log_start = datetime.strptime(
            launch.log_start,
            "%Y-%m-%d %H:%M:%S%z",
        )
        self.assertEqual(
            parsed_log_start.strftime("%Y-%m-%d %H:%M:%S%z"),
            launch.log_start,
        )
        terminate.assert_called_once_with("simulator-2", "com.example.app")
        self.assertEqual(
            run.call_args.args[0],
            [
                "xcrun",
                "simctl",
                "launch",
                "--terminate-running-process",
                "simulator-2",
                "com.example.app",
            ],
        )
        self.assertNotIn(
            "QWQ_ANDROID_RELEASE_STORE_PASSWORD",
            run.call_args.kwargs["env"],
        )

    def test_activation_process_is_terminated_before_launch(self) -> None:
        running = subprocess.CompletedProcess(
            ["launchctl"],
            0,
            stdout=(
                "123 - UIKitApplication:com.example.app[abcd][rb-legacy]\n"
            ),
            stderr="",
        )
        stopped = subprocess.CompletedProcess(
            ["launchctl"], 0, stdout="services = {}\n", stderr=""
        )
        terminated = subprocess.CompletedProcess(
            ["simctl"], 0, stdout="", stderr=""
        )
        with mock.patch.dict(
            os.environ,
            {"QWQ_ANDROID_RELEASE_STORE_PASSWORD": "secret"},
            clear=False,
        ), mock.patch.object(
            vm_service.subprocess,
            "run",
            side_effect=(terminated, running, stopped),
        ) as run, mock.patch.object(vm_service.time, "sleep") as sleep:
            vm_service._terminate_selected_application(
                "simulator-2",
                "com.example.app",
            )

        self.assertEqual(
            run.call_args_list[0].args[0],
            [
                "xcrun",
                "simctl",
                "terminate",
                "simulator-2",
                "com.example.app",
            ],
        )
        self.assertEqual(
            run.call_args_list[1].args[0],
            [
                "xcrun",
                "simctl",
                "spawn",
                "simulator-2",
                "launchctl",
                "print",
                f"user/{os.getuid()}",
            ],
        )
        self.assertEqual(run.call_args_list[2].args[0], run.call_args_list[1].args[0])
        for call in run.call_args_list:
            self.assertNotIn(
                "QWQ_ANDROID_RELEASE_STORE_PASSWORD",
                call.kwargs["env"],
            )
        sleep.assert_called_once_with(0.05)

    def test_prelaunch_log_readback_is_device_pid_bound_and_clean(self) -> None:
        attempt = (
            "QWQStartup ios_dart_startup_attempt attemptId=cold-a "
            "launchProvenance=canonical_launcher "
            "runtimeConfigSupplyMode=external_runtime_package hotRestart=false "
            "configurationState=complete effectiveLaunchManifestDigest=sha256:"
            + "a" * 64
        )
        terminal = (
            "QWQStartup ios_startup_safe_terminal surface=router_shell "
            "reportedElapsedMs=300 receivedMs=320 attemptId=cold-a "
            "nativeAttemptId=cold-a launchProvenance=canonical_launcher "
            "runtimeConfigSupplyMode=external_runtime_package"
        )
        output = "\n".join(
            json.dumps({"processID": 82001, "eventMessage": marker})
            for marker in (attempt, terminal)
        )
        with mock.patch.dict(
            os.environ,
            {"QWQ_ANDROID_RELEASE_STORE_PASSWORD": "secret"},
            clear=False,
        ), mock.patch.object(
            vm_service.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                ["log"], 0, stdout=output, stderr=""
            ),
        ) as run:
            evidence = vm_service.read_ios_simulator_startup_evidence(
                _launch_identity(device_id="simulator-2")
            )

        self.assertEqual(evidence, (attempt, terminal))
        command = run.call_args.args[0]
        self.assertEqual(command[:5], ["xcrun", "simctl", "spawn", "simulator-2", "log"])
        self.assertIn("processIdentifier == 82001", command[-1])
        self.assertNotIn(
            "QWQ_ANDROID_RELEASE_STORE_PASSWORD",
            run.call_args.kwargs["env"],
        )

    def test_prelaunch_log_readback_rejects_other_same_bundle_pid(self) -> None:
        token = "OtherSimulatorToken="
        output = json.dumps(
            {
                "processID": 81000,
                "eventMessage": (
                    "QWQStartup ios_dart_startup_attempt attemptId=other "
                    f"ws://127.0.0.1:59042/{token}/ws"
                ),
            }
        )
        with mock.patch.object(
            vm_service.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                ["log"], 0, stdout=output, stderr=""
            ),
        ), self.assertRaisesRegex(
            executor.CanonicalExecutorError,
            "identity is ambiguous",
        ) as raised:
            vm_service.read_ios_simulator_startup_evidence(
                _launch_identity(device_id="simulator-2")
            )

        self.assertNotIn(token, str(raised.exception))

    def test_lookup_process_cleanup_escalates_and_reaps(self) -> None:
        process = _Process(wait_timeouts=1)
        with mock.patch.object(vm_service.os, "killpg") as killpg:
            vm_service._terminate_lookup_process(process)

        self.assertEqual(
            killpg.call_args_list,
            [
                mock.call(process.pid, signal.SIGTERM),
                mock.call(process.pid, signal.SIGKILL),
            ],
        )
        self.assertEqual(
            process.wait_calls,
            [vm_service._PROCESS_TERMINATION_GRACE_SECONDS, None],
        )

    def test_flutter_machine_launch_evidence_requires_bound_vm_identity(self) -> None:
        for line in (
            '[{"event":"app.started","params":{"appId":"daemon-app-1"}}]',
            (
                '[{"event":"app.debugPort","params":'
                '{"appId":"daemon-app-1","port":57527,'
                '"wsUri":"ws://127.0.0.1:57527/token/ws"}}]'
            ),
        ):
            with self.subTest(line=line):
                self.assertTrue(executor._is_flutter_app_started_event(line))
        for line in (
            '[{"event":"daemon.connected","params":{"pid":123}}]',
            '[{"event":"app.start","params":{"appId":"daemon-app-1"}}]',
            '[{"event":"app.debugPort","params":{"appId":"daemon-app-1"}}]',
            (
                '[{"event":"app.debugPort","params":'
                '{"wsUri":"ws://127.0.0.1:57527/token/ws"}}]'
            ),
            '[{"event":"app.started","params":{}}]',
            '[{"event":"app.started"}]',
            '{"event":"app.started","params":{"appId":"daemon-app-1"}}',
            "not-json",
        ):
            with self.subTest(line=line):
                self.assertFalse(executor._is_flutter_app_started_event(line))

        attach_source = (
            APP_DIR / "scripts/device/canonical_app_instance/attach_session.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"--machine"', attach_source)
        self.assertIn('"--host-vmservice-port=0"', attach_source)
        self.assertIn('"--dds-port=0"', attach_source)
        self.assertNotIn('"--host-vmservice-port=8888"', attach_source)
        self.assertNotIn('"--dds-port=8889"', attach_source)
        self.assertNotIn("flutter-attach.pid", attach_source)
        launcher_source = (APP_DIR / "run.sh").read_text(encoding="utf-8")
        self.assertNotIn("tcp:8888", launcher_source)
        self.assertNotIn("QWQ_ANDROID_VM_FORWARD_PREEXISTING", launcher_source)

    def test_ios_attach_passes_debug_url_but_redacts_machine_output(self) -> None:
        token = "SensitiveToken"
        process = _Process(
            '[{"event":"app.start","params":{"appId":"daemon-app-1"}}]\n',
            '[{"event":"app.debugPort","params":'
            '{"appId":"daemon-app-1","port":57527,'
            f'"wsUri":"ws://127.0.0.1:57527/{token}/ws"}}}}]\n',
        )
        driver = executor.IOSSimulatorPlatformDriver(
            device_id="simulator-1",
            application_id="com.example.app",
            entrypoint="lib/main_prod.dart",
        )
        on_attached = mock.Mock()
        with mock.patch.dict(
            os.environ,
            {
                "QWQ_REAL_FLUTTER": "/sdk/bin/flutter",
                "QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON": '{"legacy":"keyring"}',
                "QWQ_ANDROID_RELEASE_STORE_PASSWORD": "secret",
            },
            clear=False,
        ), mock.patch.object(
            driver,
            "resolve_attach_debug_url",
            return_value=f"http://127.0.0.1:59042/{token}/",
        ), mock.patch.object(
            driver,
            "startup_evidence_lines",
            return_value=(),
        ), mock.patch.object(
            driver,
            "child_environment",
            side_effect=executor.compile_environment,
        ), mock.patch.object(
            executor.subprocess,
            "Popen",
            return_value=process,
        ) as popen, mock.patch.object(
            executor.threading,
            "Thread",
            _ImmediateThread,
        ), mock.patch("builtins.print") as emitted:
            result = driver.attach(
                ("--verbose",),
                timeout_seconds=1.0,
                on_attached=on_attached,
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            popen.call_args.args[0],
            [
                "/sdk/bin/flutter",
                "attach",
                "--machine",
                "-d",
                "simulator-1",
                "--app-id",
                "com.example.app",
                "--target",
                "lib/main_prod.dart",
                "--host-vmservice-port=0",
                "--dds-port=0",
                f"--debug-url=http://127.0.0.1:59042/{token}/",
                "--verbose",
            ],
        )
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        child_environment = popen.call_args.kwargs["env"]
        self.assertNotIn("QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON", child_environment)
        self.assertNotIn("QWQ_ANDROID_RELEASE_STORE_PASSWORD", child_environment)
        logged = "".join(str(call.args[0]) for call in emitted.call_args_list)
        self.assertNotIn(token, logged)
        self.assertIn("<redacted-vm-service-uri>", logged)
        on_attached.assert_called_once_with()

    def test_ios_attach_replays_early_pid_bound_markers_before_launch_callback(
        self,
    ) -> None:
        process = _Process(
            '[{"event":"app.debugPort","params":'
            '{"appId":"daemon-app-1","port":57527,'
            '"wsUri":"ws://127.0.0.1:57527/token/ws"}}]\n'
        )
        driver = executor.IOSSimulatorPlatformDriver(
            device_id="simulator-2",
            application_id="com.example.app",
            entrypoint="lib/main_prod.dart",
        )
        driver._ios_launch = _launch_identity(device_id="simulator-2")
        markers = (
            "QWQStartup ios_dart_startup_attempt attemptId=cold-a",
            (
                "QWQStartup ios_startup_safe_terminal surface=router_shell "
                "attemptId=cold-a"
            ),
        )
        observed: list[str] = []

        def observe_print(value: object, **_kwargs: object) -> None:
            observed.append(str(value))

        with mock.patch.object(
            driver,
            "resolve_attach_debug_url",
            return_value="http://127.0.0.1:59042/token/",
        ), mock.patch.object(
            vm_service,
            "read_ios_simulator_startup_evidence",
            return_value=markers,
        ) as readback, mock.patch.object(
            driver,
            "child_environment",
            side_effect=executor.compile_environment,
        ), mock.patch.object(
            executor.subprocess,
            "Popen",
            return_value=process,
        ), mock.patch.object(
            executor.threading,
            "Thread",
            _ImmediateThread,
        ), mock.patch(
            "builtins.print",
            side_effect=observe_print,
        ):
            result = driver.attach(
                (),
                timeout_seconds=1.0,
                on_attached=lambda: observed.append("launch-callback"),
            )

        self.assertEqual(result, 0)
        readback.assert_called_once_with(driver._ios_launch)
        self.assertLess(observed.index(markers[0]), observed.index("launch-callback"))
        self.assertLess(observed.index(markers[1]), observed.index("launch-callback"))


if __name__ == "__main__":
    unittest.main()

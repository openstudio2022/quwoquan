# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""设备PID日志单轨发现、全局listener绑定及token安全。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR.parent))
sys.path.insert(0, str(APP_DIR / "scripts/device"))
import canonical_app_instance.ios_vm_service as vm
import run_app_instance as executor


def launch():
    return vm.IOSSimulatorLaunch("simulator-2", "com.example.app", 82001, "2026-08-29 08:00:00+0800")


def record(url="http://127.0.0.1:59042/Secret=/", pid=82001):
    return json.dumps({"processID": pid, "eventMessage": "The Dart VM service is listening on " + url})


def completed(output, code=0):
    return subprocess.CompletedProcess([], code, stdout=output, stderr="")


class IOSSimulatorVMServiceContractTest(unittest.TestCase):
    def test_exact_device_pid_log_and_global_listener_replace_same_name_mdns(self):
        with mock.patch.dict(os.environ, {"QWQ_ANDROID_RELEASE_STORE_PASSWORD": "hidden"}), mock.patch.object(vm.subprocess, "run", side_effect=[completed(record()), completed("p82001\n")]) as run, mock.patch.object(vm.subprocess, "Popen") as mdns:
            result = vm.resolve_ios_simulator_debug_url(launch(), timeout_seconds=15)
        self.assertEqual(result, "http://127.0.0.1:59042/Secret%3D/")
        command = run.call_args_list[0].args[0]
        self.assertEqual(command[:4], ["xcrun", "simctl", "spawn", "simulator-2"])
        self.assertIn(launch().log_start, command)
        self.assertIn("processIdentifier == 82001", command[-1])
        self.assertEqual(run.call_args_list[1].args[0], ["/usr/sbin/lsof", "-nP", "-iTCP:59042", "-sTCP:LISTEN", "-Fp"])
        self.assertNotIn("QWQ_ANDROID_RELEASE_STORE_PASSWORD", run.call_args_list[0].kwargs["env"])
        mdns.assert_not_called()

    def test_wrong_pid_invalid_endpoint_and_ambiguous_records_never_expose_token(self):
        for output in [record(pid=81000), record("http://other-host:59042/Secret=/"), record("http://127.0.0.1:70000/Secret=/"), record()+"\n"+record("http://127.0.0.1:59043/Secret=/"), "malformed"]:
            with self.subTest(output=output), mock.patch.object(vm.subprocess, "run", return_value=completed(output)), self.assertRaises(executor.CanonicalExecutorError) as error:
                vm.resolve_ios_simulator_debug_url(launch(), timeout_seconds=1)
            self.assertNotIn("Secret", str(error.exception))

    def test_other_process_and_multiple_listener_owners_are_rejected(self):
        for pids in ["p81000\n", "p82001\np81000\n", ""]:
            with self.subTest(pids=pids), mock.patch.object(vm.subprocess, "run", side_effect=[completed(record()), completed(pids)]), self.assertRaisesRegex(executor.CanonicalExecutorError, "not bound"):
                vm.resolve_ios_simulator_debug_url(launch(), timeout_seconds=1)

    def test_duplicate_same_pid_log_is_same_identity(self):
        self.assertEqual(vm._vm_log_endpoint([json.loads(record()), json.loads(record())]), (59042, "Secret="))

    def test_no_record_waits_bounded_and_caps_at_fifteen_seconds(self):
        with mock.patch.object(vm.time, "monotonic", side_effect=[100, 116]), self.assertRaisesRegex(executor.CanonicalExecutorError, "within 15s"):
            vm.resolve_ios_simulator_debug_url(launch(), timeout_seconds=600)

    def test_poll_empty_then_current_record(self):
        with mock.patch.object(vm.subprocess, "run", side_effect=[completed(""), completed(record()), completed("p82001\n")]), mock.patch.object(vm.time, "sleep") as sleep:
            vm.resolve_ios_simulator_debug_url(launch(), timeout_seconds=1)
        sleep.assert_called_once()

    def test_log_subprocess_failure_and_timeout_fail_closed(self):
        with mock.patch.object(vm.subprocess, "run", return_value=completed("", 1)), self.assertRaisesRegex(executor.CanonicalExecutorError, "readback failed"):
            vm.resolve_ios_simulator_debug_url(launch(), timeout_seconds=1)
        with mock.patch.object(vm.subprocess, "run", side_effect=subprocess.TimeoutExpired("simctl", 1)), self.assertRaisesRegex(executor.CanonicalExecutorError, "timed out"):
            vm.resolve_ios_simulator_debug_url(launch(), timeout_seconds=1)

    def test_invalid_launch_identity_or_budget_is_rejected(self):
        for budget in [0, -1, float("inf"), float("nan")]:
            with self.subTest(budget=budget), self.assertRaises(executor.CanonicalExecutorError):
                vm.resolve_ios_simulator_debug_url(launch(), timeout_seconds=budget)
        with self.assertRaises(executor.CanonicalExecutorError):
            vm.resolve_ios_simulator_debug_url(vm.IOSSimulatorLaunch("", "app", 1, launch().log_start), timeout_seconds=1)

    def test_tokens_redacted(self):
        result = vm.redact_vm_service_tokens("authCode=Secret= ws://127.0.0.1:59042/Secret=/ws")
        self.assertNotIn("Secret", result)

    def test_launch_binds_simctl_pid_and_terminates_activation_first(self):
        with mock.patch.object(vm, "_terminate_selected_application") as terminate, mock.patch.object(vm.subprocess, "run", return_value=completed("com.example.app: 82001\n")) as run:
            observed = vm.launch_selected_simulator_application("simulator-2", "com.example.app")
        terminate.assert_called_once_with("simulator-2", "com.example.app")
        self.assertEqual(observed.process_id, 82001)
        self.assertEqual(run.call_args.args[0], ["xcrun", "simctl", "launch", "--terminate-running-process", "simulator-2", "com.example.app"])

    def test_termination_waits_for_exact_service(self):
        with mock.patch.object(vm.subprocess, "run", side_effect=[completed(""), completed("UIKitApplication:com.example.app[abcd]"), completed("")]), mock.patch.object(vm.time, "sleep") as sleep:
            vm._terminate_selected_application("simulator-2", "com.example.app")
        sleep.assert_called_once_with(0.05)

    def test_startup_evidence_is_pid_bound_and_redacted(self):
        row = json.dumps({"processID":82001,"eventMessage":"QWQStartup ios_startup_safe_terminal surface=router_shell"})
        with mock.patch.object(vm.subprocess, "run", return_value=completed(row)):
            self.assertEqual(len(vm.read_ios_simulator_startup_evidence(launch())), 1)
        with mock.patch.object(vm.subprocess, "run", return_value=completed(row.replace("82001", "81000"))), self.assertRaisesRegex(executor.CanonicalExecutorError, "identity is ambiguous"):
            vm.read_ios_simulator_startup_evidence(launch())

    def test_driver_passes_exact_launch_identity(self):
        driver = executor.IOSSimulatorPlatformDriver(device_id="simulator-2", application_id="com.example.app", entrypoint="lib/main_alpha.dart")
        with mock.patch.object(vm, "launch_selected_simulator_application", return_value=launch()):
            driver.launch_application()
        with mock.patch.object(vm, "resolve_ios_simulator_debug_url", return_value="http://127.0.0.1:59042/token/") as resolve:
            driver.resolve_attach_debug_url(2)
        resolve.assert_called_once_with(launch(), timeout_seconds=2)

    def test_attach_still_requires_bound_debug_url_and_redaction(self):
        source = (APP_DIR / "scripts/device/canonical_app_instance/attach_session.py").read_text()
        self.assertIn("resolve_attach_debug_url", source)
        self.assertIn('"--machine"', source)
        self.assertIn("redact_vm_service_tokens", source)
        self.assertIn("startup_evidence_lines", source)

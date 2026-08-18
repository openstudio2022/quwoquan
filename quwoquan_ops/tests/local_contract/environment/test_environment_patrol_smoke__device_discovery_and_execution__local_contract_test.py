"""environment patrol smoke：设备发现与租约、patrol 执行判定与远端 API 证据契约。

由 1000 行硬顶拆分自 test_environment_patrol_smoke__local_contract_test.py；
测试逐字搬移，共享 helper 基类见
quwoquan_ops/tests/support/environment_patrol_smoke_test_support.py。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke

# 入口拆为薄壳 + environment_patrol_smoke 子包后，mock.patch.object 必须打在
# 被测函数实际读取全局名的实现模块上，而不是入口 re-export 的绑定上。
from quwoquan_ops.cli.smoke.environment_patrol_smoke import (
    device_runtime as smoke_device_runtime,
    devices as smoke_devices,
    execution as smoke_execution,
)
from quwoquan_ops.cli.lib import flutter_android_device_proxy as flutter_proxy
from quwoquan_ops.tests.support.environment_patrol_smoke_test_support import (
    EnvironmentPatrolSmokeCaseBase,
)


class EnvironmentPatrolSmokeTest(EnvironmentPatrolSmokeCaseBase):
    def test_core_readback_requires_and_forwards_one_release_envelope(self) -> None:
        release_values = {
            destination: f"value-{index}"
            for index, (destination, _define_name) in enumerate(
                smoke.RELEASE_APP_UAT_DEFINES,
                start=1,
            )
        }
        args = self._args(
            target=smoke.CORE_READBACK_TARGET,
            **release_values,
        )
        device = {
            "id": "android-1",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }

        command = smoke.patrol_command(
            device,
            args,
            "patrol",
            dart_define_file=Path("/tmp/patrol-secrets.json"),
        )

        for destination, define_name in smoke.RELEASE_APP_UAT_DEFINES:
            self.assertIn(
                f"--dart-define={define_name}={release_values[destination]}",
                command,
            )

        missing = self._args(target=smoke.CORE_READBACK_TARGET)
        with self.assertRaisesRegex(ValueError, "immutable release envelope"):
            smoke.patrol_command(
                device,
                missing,
                "patrol",
                dart_define_file=Path("/tmp/patrol-secrets.json"),
            )

    @mock.patch.object(smoke_devices, "resolve_android_debug_bridge", return_value="/sdk/adb")
    @mock.patch.object(smoke.subprocess, "run")
    def test_explicit_android_device_discovery_uses_adb_without_flutter_lock(
        self,
        run: mock.Mock,
        _resolve_adb: mock.Mock,
    ) -> None:
        run.return_value = subprocess.CompletedProcess(
            [],
            0,
            "List of devices attached\n"
            "emulator-5554 device product:sdk model:Pixel_API_31 device:emulator64_arm64\n",
            "",
        )

        devices = smoke.discover_devices("android", ["emulator-5554"])

        self.assertEqual(devices[0]["id"], "emulator-5554")
        self.assertEqual(devices[0]["name"], "Pixel_API_31")
        self.assertEqual(devices[0]["targetPlatform"], "android-arm64")
        run.assert_called_once_with(
            ["/sdk/adb", "devices", "-l"],
            text=True,
            capture_output=True,
            check=False,
        )

    @mock.patch.object(smoke.shutil, "which", return_value="/sdk/flutter")
    @mock.patch.object(smoke_device_runtime, "resolve_android_debug_bridge", return_value="/sdk/adb")
    def test_android_patrol_uses_adb_inventory_for_flutter_device_discovery(
        self,
        _resolve_adb: mock.Mock,
        _which: mock.Mock,
    ) -> None:
        args = self._args()
        device = {
            "id": "emulator-5554",
            "name": "Pixel_API_31",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }

        env = smoke._device_command_env(args, device)
        inventory = json.loads(env[flutter_proxy.ANDROID_DEVICE_INVENTORY_ENV])

        self.assertEqual(inventory, [{**device, "isSupported": True}])
        self.assertEqual(env[flutter_proxy.REAL_FLUTTER_ENV], "/sdk/flutter")
        self.assertEqual(env["QWQ_APP_RUNTIME_ENV"], "gamma")
        self.assertEqual(env["QWQ_LAUNCH_TARGET"], "gamma-local")
        self.assertEqual(env["QWQ_RUN_DEVICE_ID"], "emulator-5554")
        self.assertEqual(env["ANDROID_SERIAL"], "emulator-5554")
        self.assertIn(
            str(smoke.ANDROID_DEVICE_PROXY),
            env[smoke.PATROL_FLUTTER_COMMAND_ENV],
        )

    @mock.patch.object(smoke_device_runtime, "acquire_consumer_lease")
    def test_android_patrol_acquires_consumer_lease_for_reversed_ports(
        self,
        acquire_consumer_lease: mock.Mock,
    ) -> None:
        args = self._args()
        command_env: dict[str, str] = {}
        acquire_consumer_lease.return_value = {"leaseId": "lease-android"}

        lease = smoke._acquire_patrol_consumer_lease(
            args,
            {
                "id": "emulator-5554",
                "targetPlatform": "android-arm64",
                "emulator": True,
            },
            {
                "status": "installed",
                "mappings": [
                    {"devicePort": 19000, "hostPort": 19000},
                    {"devicePort": 19100, "hostPort": 19100},
                ],
            },
            command_env,
        )

        self.assertEqual(lease[0:2], ("gamma-local", "emulator-5554"))
        self.assertEqual(lease[3], "lease-android")
        self.assertEqual(command_env["QWQ_CONSUMER_LEASE_ACQUIRED"], "1")
        self.assertEqual(command_env["QWQ_ANDROID_LOCAL_PORTS"], "19000,19100")
        acquire_consumer_lease.assert_called_once_with(
            target="gamma-local",
            device="emulator-5554",
            consumer=lease[2],
            package_name=smoke.android_release_uat_package("gamma", "debug"),
            ports=[19000, 19100],
            platform="android",
        )

    @mock.patch.object(smoke_device_runtime, "acquire_consumer_lease")
    def test_ios_simulator_patrol_acquires_consumer_lease_without_ports(
        self,
        acquire_consumer_lease: mock.Mock,
    ) -> None:
        args = self._args()
        command_env: dict[str, str] = {}
        acquire_consumer_lease.return_value = {"leaseId": "lease-ios"}

        lease = smoke._acquire_patrol_consumer_lease(
            args,
            {
                "id": "SIMULATOR-UDID",
                "targetPlatform": "ios",
                "emulator": True,
            },
            {"status": "not-required", "mappings": []},
            command_env,
        )

        self.assertEqual(lease[0:2], ("gamma-local", "SIMULATOR-UDID"))
        self.assertEqual(lease[3], "lease-ios")
        self.assertEqual(command_env["QWQ_CONSUMER_LEASE_ACQUIRED"], "1")
        self.assertNotIn("QWQ_ANDROID_LOCAL_PORTS", command_env)
        acquire_consumer_lease.assert_called_once_with(
            target="gamma-local",
            device="SIMULATOR-UDID",
            consumer=lease[2],
            package_name=smoke.ios_release_uat_bundle_ids("gamma", "debug")[0],
            ports=[],
            platform="ios-simulator",
        )

    def test_flutter_proxy_returns_only_validated_android_inventory(self) -> None:
        inventory = [
            {
                "id": "emulator-5554",
                "name": "Pixel_API_31",
                "targetPlatform": "android-arm64",
                "emulator": True,
                "isSupported": True,
            }
        ]
        with tempfile.SpooledTemporaryFile(mode="w+") as stdout:
            with mock.patch.dict(
                os.environ,
                {flutter_proxy.ANDROID_DEVICE_INVENTORY_ENV: json.dumps(inventory)},
                clear=False,
            ), mock.patch.object(flutter_proxy.sys, "stdout", stdout):
                self.assertEqual(flutter_proxy.main(["devices", "--machine"]), 0)
            stdout.seek(0)
            self.assertEqual(json.load(stdout), inventory)

    @mock.patch.object(flutter_proxy.subprocess, "run")
    @mock.patch.object(flutter_proxy.shutil, "which", return_value="/jdk/bin/javac")
    def test_flutter_proxy_checks_real_java_without_global_flutter_doctor(
        self,
        _which: mock.Mock,
        run: mock.Mock,
    ) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, "javac 17.0.12\n", "")
        with tempfile.SpooledTemporaryFile(mode="w+") as stdout:
            with mock.patch.object(flutter_proxy.sys, "stdout", stdout):
                self.assertEqual(flutter_proxy.main(["doctor", "--verbose"]), 0)
            stdout.seek(0)
            self.assertIn("Java version 17.0.12", stdout.read())
        run.assert_called_once_with(
            ["/jdk/bin/javac", "--version"],
            text=True,
            capture_output=True,
            check=False,
        )

    @mock.patch.object(smoke_execution, "_terminate_process_group", return_value="stopped")
    @mock.patch.object(smoke.subprocess, "Popen")
    def test_run_command_cleans_process_group_on_interrupt(
        self,
        popen: mock.Mock,
        terminate: mock.Mock,
    ) -> None:
        process = mock.Mock(pid=4321)
        process.communicate.side_effect = KeyboardInterrupt
        popen.return_value = process

        with self.assertRaises(KeyboardInterrupt):
            smoke.run_command(["patrol", "test"], cwd=ROOT)

        terminate.assert_called_once_with(process)

    def test_patrol_test_execution_prefers_xctest_over_zero_patrol_summary(self) -> None:
        summary = smoke.patrol_test_execution_summary(
            "Executed 1 test, with 0 failures (0 unexpected)\n"
            "📝 Total: 0\n❌ Failed: 0\n"
        )

        self.assertEqual(
            summary,
            {
                "framework": "xctest",
                "executed": 1,
                "failed": 0,
                "skipped": 0,
            },
        )

    def test_patrol_test_execution_requires_executed_without_failures_or_skips(
        self,
    ) -> None:
        passed = smoke.patrol_test_execution_summary(
            "📝 Total: 2\n✅ Successful: 2\n❌ Failed: 0\n"
            "⏩ Skipped: 0\n"
        )
        self.assertEqual(
            passed,
            {
                "framework": "patrol",
                "executed": 2,
                "failed": 0,
                "skipped": 0,
            },
        )
        self.assertEqual(smoke.patrol_test_execution_failure_reason(passed), "")

        skipped = smoke.patrol_test_execution_summary(
            "Executed 2 tests, with 1 test skipped and 0 failures"
        )
        self.assertEqual(skipped["skipped"], 1)
        self.assertIn(
            "1 skipped tests",
            smoke.patrol_test_execution_failure_reason(skipped),
        )

        zero = smoke.patrol_test_execution_summary(
            "📝 Total: 0\n❌ Failed: 0\n⏩ Skipped: 0\n"
        )
        self.assertIn(
            "zero executed tests",
            smoke.patrol_test_execution_failure_reason(zero),
        )

        incomplete = smoke.patrol_test_execution_summary(
            "patrol command exited successfully without a test summary"
        )
        self.assertIn(
            "missing or incomplete",
            smoke.patrol_test_execution_failure_reason(incomplete),
        )

    def test_non_dry_run_exit_zero_without_summary_cannot_pass(self) -> None:
        result = {"exitCode": 0, "outputSummary": "process exit 0"}

        smoke.apply_patrol_test_execution_summary(
            result,
            "Patrol process exited successfully without test totals",
            dry_run=False,
        )

        self.assertEqual(result["exitCode"], 1)
        self.assertEqual(
            result["testExecution"],
            {
                "framework": "unknown",
                "executed": None,
                "failed": None,
                "skipped": None,
            },
        )
        self.assertIn(
            "execution summary is missing or incomplete",
            result["outputSummary"],
        )

        passed_result = {"exitCode": 0, "outputSummary": "process exit 0"}
        smoke.apply_patrol_test_execution_summary(
            passed_result,
            "📝 Total: 1\n❌ Failed: 0\n⏩ Skipped: 0\n",
            dry_run=False,
        )
        self.assertEqual(passed_result["exitCode"], 0)

        dry_run_result = {"exitCode": 0, "outputSummary": "dry-run"}
        smoke.apply_patrol_test_execution_summary(
            dry_run_result,
            "",
            dry_run=True,
        )
        self.assertEqual(dry_run_result["exitCode"], 0)

    def test_first_typed_patrol_blocker_is_structured_without_payload(self) -> None:
        output = (
            "\x1b[31mCloudException(type: CloudErrorType.invalidResponse, "
            "message: private response detail, statusCode: null, code: "
            "APP.CONTRACT.invalid_json, requestId: req-private, "
            "traceId: trace-private, sourceOperationId: "
            "chat.conversation.CreateConversation)\x1b[0m"
        )

        self.assertEqual(
            smoke._first_typed_patrol_blocker(output),
            {
                "errorCode": "APP.CONTRACT.invalid_json",
                "sourceOperationId": "chat.conversation.CreateConversation",
                "httpStatus": None,
            },
        )

    def test_remote_api_evidence_requires_ids_and_effective_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "search-report.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "search-remote-api-uat-report",
                        "status": "passed",
                        "cases": {
                            "searchAndFeedbackRoundtrip": {
                                "evidence": {
                                    "schema": "search-remote-api-evidence",
                                    "status": "passed",
                                    "searchRequestId": "search.req.1",
                                    "events": [
                                        {
                                            "requestId": "search.req.1",
                                            "traceId": "trace.1",
                                            "succeeded": True,
                                        }
                                    ],
                                    "feedbackEvents": [
                                        {
                                            "eventType": "impression",
                                            "objectId": "post.1",
                                            "target": None,
                                            "rankPosition": 1,
                                            "dwellMs": None,
                                        },
                                        {
                                            "eventType": "click",
                                            "objectId": "post.1",
                                            "target": "posts",
                                            "rankPosition": 1,
                                            "dwellMs": None,
                                        },
                                        {
                                            "eventType": "dwell",
                                            "objectId": "post.1",
                                            "target": "posts",
                                            "rankPosition": 1,
                                            "dwellMs": 3000,
                                        },
                                    ],
                                }
                            },
                            "tagFilterPositiveAndNegative": {
                                "evidence": {
                                    "schema": "search-tag-filter-remote-evidence",
                                    "status": "passed",
                                    "positiveHitCount": 1,
                                    "negativeHitCount": 0,
                                }
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            evidence = smoke.load_remote_api_evidence(str(path))

        self.assertEqual(evidence["searchRequestId"], "search.req.1")
        self.assertEqual(evidence["events"][0]["traceId"], "trace.1")
        self.assertEqual(
            [event["eventType"] for event in evidence["feedbackEvents"]],
            ["impression", "click", "dwell"],
        )
        self.assertEqual(evidence["tagFilter"]["positiveHitCount"], 1)

    @mock.patch.object(smoke.subprocess, "run")
    def test_release_bound_ios_uat_resets_app_and_test_runner_state(
        self,
        run: mock.Mock,
    ) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        args = self._args(
            release_uat_cases="/tmp/homepage_verification_cases.json"
        )
        device = {
            "id": "ios-release-uat",
            "targetPlatform": "ios",
            "emulator": True,
        }

        result = smoke._reset_release_uat_device_state(args, device)

        expected_bundle_ids = smoke.ios_release_uat_bundle_ids("gamma", "debug")
        self.assertEqual(result["status"], "reset")
        self.assertEqual(
            [row["bundleId"] for row in result["applications"]],
            list(expected_bundle_ids),
        )
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["xcrun", "simctl", "uninstall", "ios-release-uat", bundle_id]
                for bundle_id in expected_bundle_ids
            ],
        )

    @mock.patch.object(smoke.subprocess, "run")
    def test_non_release_patrol_does_not_reset_app_state(
        self,
        run: mock.Mock,
    ) -> None:
        result = smoke._reset_release_uat_device_state(
            self._args(release_uat_cases=""),
            {"id": "ios-smoke", "targetPlatform": "ios", "emulator": True},
        )

        self.assertEqual(
            result,
            {"status": "skipped", "reason": "not-release-bound"},
        )
        run.assert_not_called()

    @mock.patch.object(smoke_device_runtime, "resolve_android_debug_bridge", return_value="/sdk/adb")
    @mock.patch.object(smoke.subprocess, "run")
    def test_release_bound_android_uat_treats_uninstalled_app_as_reset(
        self,
        run: mock.Mock,
        _resolve_adb: mock.Mock,
    ) -> None:
        run.return_value = subprocess.CompletedProcess([], 1, "", "")
        args = self._args(
            release_uat_cases="/tmp/homepage_verification_cases.json"
        )
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }

        result = smoke._reset_release_uat_device_state(args, device)

        self.assertTrue(result["applications"][0]["alreadyAbsent"])
        run.assert_called_once_with(
            [
                "/sdk/adb",
                "-s",
                "emulator-5554",
                "shell",
                "pm",
                "path",
                smoke.android_release_uat_package("gamma", "debug"),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_patrol_secret_define_file_is_private_and_ephemeral_ready(self) -> None:
        args = self._args(
            env_name="beta-local",
            runtime_env="beta",
            test_auth_token="remote-access",
            test_refresh_token="remote-refresh",
        )

        path = smoke._create_patrol_secret_define_file(args)
        try:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                '{"TEST_AUTH_TOKEN": "remote-access", '
                '"TEST_REFRESH_TOKEN": "remote-refresh", '
                '"APP_CURRENT_OWNER_ID": "fixture_owner_current", '
                '"APP_CURRENT_PERSONA_ID": "fixture_user_current", '
                '"APP_CURRENT_USER_ID": "fixture_user_current"}\n',
            )
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

"""environment patrol smoke：设备发现与租约、patrol 执行判定与远端 API 证据契约。

由 1000 行硬顶拆分自 test_environment_patrol_smoke__local_contract_test.py；
测试逐字搬移，共享 helper 基类见
quwoquan_ops/tests/support/environment_patrol_smoke_test_support.py。
"""

from __future__ import annotations

import hashlib
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

from quwoquan_ops.cli.lib import flutter_android_device_proxy as flutter_proxy
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke

# 入口拆为薄壳 + environment_patrol_smoke 子包后，mock.patch.object 必须打在
# 被测函数实际读取全局名的实现模块上，而不是入口 re-export 的绑定上。
from quwoquan_ops.cli.smoke.environment_patrol_smoke import (
    device_runtime as smoke_device_runtime,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke import devices as smoke_devices
from quwoquan_ops.cli.smoke.environment_patrol_smoke import execution as smoke_execution
from quwoquan_ops.tests.support.environment_patrol_smoke_test_support import (
    EnvironmentPatrolSmokeCaseBase,
)


def _managed_result(
    *,
    exit_code: int,
    output: str = "",
    timed_out: bool = False,
) -> dict[str, object]:
    return {
        "exitCode": exit_code,
        "timedOut": timed_out,
        "outputSummary": output,
        "logPath": "runs/device/device-preflight.log",
    }


class EnvironmentPatrolSmokeTest(EnvironmentPatrolSmokeCaseBase):
    def test_report_writer_emits_only_explicit_app_uat_case_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_plan_ref = "data/releases/release-a/uat/sample_plan.json"
            binding_ref = "target-uat-bindings/binding.json"
            sample_plan_path = root / sample_plan_ref
            binding_path = root / binding_ref
            sample_plan_path.parent.mkdir(parents=True)
            binding_path.parent.mkdir(parents=True)
            sample_plan_path.write_bytes(b"sample-plan\n")
            binding_path.write_bytes(b"target-binding\n")
            page_ref = "env/alpha/runs/app-content/page-evidence.json"
            page_path = root / page_ref
            page_path.parent.mkdir(parents=True)
            page_path.write_bytes(b"page-evidence\n")
            marker = {
                "schema": smoke.APP_UAT_CASE_EVIDENCE_SCHEMA,
                "sampleId": "baseline-article-001",
                "entrySurface": "direct_or_object_route",
                "carrier": "article",
                "objectId": "article-001",
                "specRef": "spec.md#gwt-001",
                "runnerIdentity": "qwq_app.content_uat.direct_or_object_route.article.v1",
                "status": "passed",
                "startedAt": "2026-08-30T00:00:00Z",
                "completedAt": "2026-08-30T00:01:00Z",
                "target": {"kind": "page", "id": "article-001"},
                "pageEvidence": {
                    "status": "present",
                    "ref": page_ref,
                    "sha256": "sha256:" + hashlib.sha256(page_path.read_bytes()).hexdigest(),
                },
            }
            report = {
                "status": "passed",
                "appUatAuthority": {
                    "samplePlanRef": sample_plan_ref,
                    "samplePlanSha256": "sha256:" + hashlib.sha256(sample_plan_path.read_bytes()).hexdigest(),
                    "targetUatBindingRef": binding_ref,
                    "targetUatBindingSha256": "sha256:" + hashlib.sha256(binding_path.read_bytes()).hexdigest(),
                    "targetUatBindingDigest": "sha256:" + "2" * 64,
                    "releaseId": "release-a",
                    "releaseDigest": "sha256:" + "3" * 64,
                    "sourceIdentitySetDigest": "sha256:" + "4" * 64,
                    "commitSha": "a" * 40,
                    "contractGraphSourceHash": "b" * 64,
                    "candidateManifestSha256": "c" * 64,
                    "provider": "first-party-https",
                },
                "runs": [
                    {
                        "exitCode": 0,
                        "patrolExitCode": 0,
                        "evidence": {
                            "structuredEvidenceLogPath": "runs/device/device-evidence.log"
                        },
                    }
                ],
            }
            log_path = root / "runs/device/device-evidence.log"
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                smoke.APP_UAT_CASE_EVIDENCE_PREFIX + json.dumps(marker) + "\n",
                encoding="utf-8",
            )
            report_path = root / "env/alpha/runs/app-content/report.json"

            with mock.patch.dict(os.environ, {"QWQ_OUTPUT_ROOT": str(root)}, clear=False):
                smoke.write_report(report_path, report)

            sources = report["appUatCaseExecutionReports"]
            self.assertEqual(len(sources), 1)
            receipt = json.loads((root / sources[0]["receiptRef"]).read_text())
            self.assertEqual(receipt["schema"], "quwoquan_ops.app_uat_case_execution.v1")
            self.assertEqual(receipt["sampleId"], "baseline-article-001")
            self.assertEqual(receipt["entrySurface"], "direct_or_object_route")
            self.assertEqual(receipt["status"], "passed")
            self.assertEqual(receipt["pageEvidence"]["ref"], page_ref)

    def test_report_writer_collects_16_markers_with_distinct_host_page_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_plan_ref = "data/releases/release-a/uat/sample_plan.json"
            binding_ref = "target-uat-bindings/binding.json"
            sample_plan_path = root / sample_plan_ref
            binding_path = root / binding_ref
            sample_plan_path.parent.mkdir(parents=True)
            binding_path.parent.mkdir(parents=True)
            sample_plan_path.write_bytes(b"sample-plan\n")
            binding_path.write_bytes(b"target-binding\n")
            entries = ("feed", "search", "recommendation", "direct_or_object_route")
            carriers = ("homepage", "article", "image", "video")
            evidence_by_capture: dict[str, dict[str, str]] = {}
            markers = []
            for entry in entries:
                for carrier in carriers:
                    sample_id = f"baseline-{carrier}-001"
                    capture_id = f"{sample_id}--{entry}--{carrier}"
                    page_ref = f"env/alpha/runs/app-content/page/{capture_id}.png"
                    page_path = root / page_ref
                    page_path.parent.mkdir(parents=True, exist_ok=True)
                    page_path.write_bytes(capture_id.encode())
                    evidence_by_capture[capture_id] = {
                        "status": "present",
                        "ref": page_ref,
                        "sha256": "sha256:" + hashlib.sha256(page_path.read_bytes()).hexdigest(),
                    }
                    markers.append(
                        {
                            "schema": smoke.APP_UAT_CASE_EVIDENCE_SCHEMA,
                            "sampleId": sample_id,
                            "entrySurface": entry,
                            "carrier": carrier,
                            "objectId": f"source-{carrier}",
                            "specRef": "spec.md#gwt-004",
                            "runnerIdentity": f"qwq_app.content_uat.{entry}.{carrier}.v1",
                            "status": "passed",
                            "startedAt": "2026-08-30T00:00:00Z",
                            "completedAt": "2026-08-30T00:01:00Z",
                            "target": {"kind": "object" if carrier == "homepage" else "page", "id": f"runtime-{carrier}"},
                            "pageEvidence": {"status": "host_captured", "captureId": capture_id},
                        }
                    )
            log_ref = "runs/device/device-evidence.log"
            log_path = root / log_ref
            log_path.parent.mkdir(parents=True)
            log_path.write_text(
                "".join(smoke.APP_UAT_CASE_EVIDENCE_PREFIX + json.dumps(marker) + "\n" for marker in markers),
                encoding="utf-8",
            )
            report = {
                # Parent failure is deliberately independent from the 16 explicit
                # marker statuses; no case may infer or lose passed from it.
                "status": "failed",
                "appUatAuthority": {
                    "samplePlanRef": sample_plan_ref,
                    "samplePlanSha256": "sha256:" + hashlib.sha256(sample_plan_path.read_bytes()).hexdigest(),
                    "targetUatBindingRef": binding_ref,
                    "targetUatBindingSha256": "sha256:" + hashlib.sha256(binding_path.read_bytes()).hexdigest(),
                    "targetUatBindingDigest": "sha256:" + "2" * 64,
                    "releaseId": "release-a",
                    "releaseDigest": "sha256:" + "3" * 64,
                    "sourceIdentitySetDigest": "sha256:" + "4" * 64,
                    "commitSha": "a" * 40,
                    "contractGraphSourceHash": "b" * 64,
                    "candidateManifestSha256": "c" * 64,
                    "provider": "first-party-https",
                },
                "runs": [{"exitCode": 1, "patrolExitCode": 0, "evidence": {"structuredEvidenceLogPath": log_ref}}],
            }
            report_path = root / "env/alpha/runs/app-content/report.json"
            resolver = lambda marker: evidence_by_capture[marker["pageEvidence"]["captureId"]]
            with mock.patch.dict(os.environ, {"QWQ_OUTPUT_ROOT": str(root)}, clear=False):
                smoke.write_report(
                    report_path,
                    report,
                    app_uat_page_evidence_resolver=resolver,
                )
            self.assertEqual(len(report["appUatCaseExecutionReports"]), 16)
            receipts = [json.loads((root / source["receiptRef"]).read_text()) for source in report["appUatCaseExecutionReports"]]
            self.assertEqual(len({receipt["pageEvidence"]["ref"] for receipt in receipts}), 16)
            self.assertEqual(len({receipt["pageEvidence"]["sha256"] for receipt in receipts}), 16)
            self.assertTrue(all(receipt["status"] == "passed" for receipt in receipts))

    def test_report_writer_blocks_authority_when_explicit_case_marker_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            sample_plan_ref = "data/releases/release-a/uat/sample_plan.json"
            binding_ref = "target-uat-bindings/binding.json"
            sample_plan_path = root / sample_plan_ref
            binding_path = root / binding_ref
            sample_plan_path.parent.mkdir(parents=True)
            binding_path.parent.mkdir(parents=True)
            sample_plan_path.write_bytes(b"sample-plan\n")
            binding_path.write_bytes(b"target-binding\n")
            report = {
                "status": "passed",
                "appUatAuthority": {
                    "samplePlanRef": sample_plan_ref,
                    "samplePlanSha256": "sha256:" + hashlib.sha256(sample_plan_path.read_bytes()).hexdigest(),
                    "targetUatBindingRef": binding_ref,
                    "targetUatBindingSha256": "sha256:" + hashlib.sha256(binding_path.read_bytes()).hexdigest(),
                    "targetUatBindingDigest": "sha256:" + "2" * 64,
                    "releaseId": "release-a",
                    "releaseDigest": "sha256:" + "3" * 64,
                    "sourceIdentitySetDigest": "sha256:" + "4" * 64,
                    "commitSha": "a" * 40,
                    "contractGraphSourceHash": "b" * 64,
                    "candidateManifestSha256": "c" * 64,
                    "provider": "first-party-https",
                },
                "runs": [
                    {
                        "exitCode": 0,
                        "patrolExitCode": 0,
                        "evidence": {
                            "structuredEvidenceLogPath": "runs/device/device-evidence.log"
                        },
                    }
                ],
            }
            log_path = root / "runs/device/device-evidence.log"
            log_path.parent.mkdir(parents=True)
            log_path.write_text("suite passed without per-case marker\n", encoding="utf-8")
            report_path = root / "env/alpha/runs/app-content/report.json"

            with mock.patch.dict(os.environ, {"QWQ_OUTPUT_ROOT": str(root)}, clear=False):
                smoke.write_report(report_path, report)

            self.assertEqual(report["status"], "gate_block")
            self.assertEqual(report["appUatCaseExecutionReports"], [])
            self.assertEqual(report["failureReason"], smoke.APP_UAT_CASE_EVIDENCE_MISSING)
            persisted = json.loads(report_path.read_text())
            self.assertEqual(persisted["status"], "gate_block")
            self.assertNotIn("passed", json.dumps(persisted["appUatCaseExecutionReports"]))

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

        # core readback 同时要求发布视频页数，由 app-content-uat 编排注入。
        with mock.patch.dict(
            os.environ,
            {smoke.APP_CONTENT_VIDEO_PAGE_COUNT_ENV: "2"},
            clear=False,
        ):
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
        self.assertIn("--dart-define=DATA_RELEASE_VIDEO_PAGE_COUNT=2", command)

        missing = self._args(target=smoke.CORE_READBACK_TARGET)
        with self.assertRaisesRegex(ValueError, "immutable release envelope"):
            smoke.patrol_command(
                device,
                missing,
                "patrol",
                dart_define_file=Path("/tmp/patrol-secrets.json"),
            )

    @mock.patch.object(
        smoke_devices, "resolve_android_debug_bridge", return_value="/sdk/adb"
    )
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
    @mock.patch.object(
        smoke_device_runtime, "resolve_android_debug_bridge", return_value="/sdk/adb"
    )
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

    @mock.patch.object(
        smoke_device_runtime.shutil, "which", return_value="/sdk/flutter"
    )
    def test_ios_patrol_uses_flutter_proxy_for_no_pub_builds(
        self,
        _which: mock.Mock,
    ) -> None:
        args = self._args()
        device = {
            "id": "SIMULATOR-UDID",
            "name": "iPhone",
            "targetPlatform": "ios",
            "emulator": True,
        }

        with mock.patch.dict(os.environ, {}, clear=True):
            env = smoke._device_command_env(args, device)

        self.assertEqual(env["QWQ_IOS_SIMULATOR_UDID"], "SIMULATOR-UDID")
        self.assertEqual(env[flutter_proxy.REAL_FLUTTER_ENV], "/sdk/flutter")
        self.assertIn(
            str(smoke.ANDROID_DEVICE_PROXY),
            env[smoke.PATROL_FLUTTER_COMMAND_ENV],
        )
        self.assertNotIn(flutter_proxy.ANDROID_DEVICE_INVENTORY_ENV, env)

    def test_patrol_device_env_requires_a_strict_boolean_emulator_field(self) -> None:
        args = self._args()
        for value in (None, 0, "false"):
            device = {
                "id": "emulator-5554",
                "name": "Pixel",
                "targetPlatform": "android-arm64",
            }
            if value is not None:
                device["emulator"] = value
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(
                    RuntimeError,
                    "emulator field must be an explicit boolean",
                ),
            ):
                smoke._device_command_env(args, device)

    @mock.patch.object(smoke.shutil, "which", return_value="/sdk/flutter")
    @mock.patch.object(
        smoke_device_runtime, "resolve_android_debug_bridge", return_value="/sdk/adb"
    )
    def test_physical_android_inventory_preserves_false_emulator_identity(
        self,
        _resolve_adb: mock.Mock,
        _which: mock.Mock,
    ) -> None:
        env = smoke._device_command_env(
            self._args(),
            {
                "id": "physical-android",
                "name": "Pixel",
                "targetPlatform": "android-arm64",
                "emulator": False,
            },
        )

        inventory = json.loads(env[flutter_proxy.ANDROID_DEVICE_INVENTORY_ENV])
        self.assertIs(inventory[0]["emulator"], False)

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
            with (
                mock.patch.dict(
                    os.environ,
                    {flutter_proxy.ANDROID_DEVICE_INVENTORY_ENV: json.dumps(inventory)},
                    clear=False,
                ),
                mock.patch.object(flutter_proxy.sys, "stdout", stdout),
            ):
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
        inventory = json.dumps(
            [
                {
                    "id": "emulator-5554",
                    "name": "Pixel",
                    "targetPlatform": "android-arm64",
                    "emulator": True,
                }
            ]
        )
        with tempfile.SpooledTemporaryFile(mode="w+") as stdout:
            with (
                mock.patch.dict(
                    os.environ,
                    {flutter_proxy.ANDROID_DEVICE_INVENTORY_ENV: inventory},
                    clear=False,
                ),
                mock.patch.object(flutter_proxy.sys, "stdout", stdout),
            ):
                self.assertEqual(flutter_proxy.main(["doctor", "--verbose"]), 0)
            stdout.seek(0)
            self.assertIn("Java version 17.0.12", stdout.read())
        run.assert_called_once_with(
            ["/jdk/bin/javac", "--version"],
            text=True,
            capture_output=True,
            check=False,
        )

    @mock.patch.object(flutter_proxy.os, "execv")
    def test_flutter_proxy_adds_no_pub_only_to_patrol_ios_and_apk_builds(
        self,
        execv: mock.Mock,
    ) -> None:
        real_flutter = "/sdk/flutter"
        cases = (
            (
                ["build", "apk", "--debug"],
                [real_flutter, "build", "apk", "--no-pub", "--debug"],
            ),
            (
                ["build", "ios", "--simulator"],
                [real_flutter, "build", "ios", "--no-pub", "--simulator"],
            ),
            (
                ["test", "--target", "test/canonical.dart"],
                [real_flutter, "test", "--target", "test/canonical.dart"],
            ),
            (
                ["build", "web", "--release"],
                [real_flutter, "build", "web", "--release"],
            ),
            (
                ["test", "--name", "build", "ios"],
                [real_flutter, "test", "--name", "build", "ios"],
            ),
            (
                ["build", "apk", "--no-pub", "--debug"],
                [real_flutter, "build", "apk", "--no-pub", "--debug"],
            ),
        )
        for args, expected in cases:
            with (
                self.subTest(args=args),
                mock.patch.dict(
                    os.environ,
                    {flutter_proxy.REAL_FLUTTER_ENV: real_flutter},
                    clear=True,
                ),
            ):
                execv.reset_mock()
                self.assertEqual(flutter_proxy.main(args), 127)
                execv.assert_called_once_with(real_flutter, expected)

    @mock.patch.object(
        smoke_execution, "_terminate_process_group", return_value="stopped"
    )
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

    def test_run_command_times_out_when_stdout_reaches_eof_before_process_exit(
        self,
    ) -> None:
        result = smoke.run_command(
            [
                sys.executable,
                "-c",
                "import os, time; os.close(1); os.close(2); time.sleep(1)",
            ],
            cwd=ROOT,
            timeout_seconds=0.1,
            output_line_handler=lambda _line: None,
        )

        self.assertEqual(result["exitCode"], 124)
        self.assertTrue(result["timedOut"])
        self.assertLess(result["durationMs"], 500)

    def test_run_command_keeps_timeout_primary_when_cleanup_and_log_both_fail(
        self,
    ) -> None:
        process = mock.Mock(pid=4321)
        process.communicate.side_effect = subprocess.TimeoutExpired("adb", 1)
        cleanup_secret = "cleanup-secret-value"
        log_secret = "log-secret-value"
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(
                smoke_execution.subprocess,
                "Popen",
                return_value=process,
            ),
            mock.patch.object(
                smoke_execution,
                "_terminate_process_group",
                side_effect=OSError(cleanup_secret),
            ),
            mock.patch.object(
                Path,
                "write_text",
                side_effect=OSError(log_secret),
            ),
        ):
            result = smoke.run_command(
                ["adb", "reverse"],
                cwd=ROOT,
                timeout_seconds=1,
                log_path=Path(temporary_dir) / "device-preflight.log",
            )

        self.assertEqual(result["exitCode"], 124)
        self.assertTrue(result["timedOut"])
        self.assertEqual(
            [failure["stage"] for failure in result["secondaryFailures"]],
            ["process-group-cleanup", "log-write"],
        )
        rendered = repr(result)
        self.assertNotIn(cleanup_secret, rendered)
        self.assertNotIn(log_secret, rendered)

    def test_run_command_log_failure_turns_unlogged_success_into_failure(self) -> None:
        process = mock.Mock(returncode=0)
        process.communicate.return_value = ("completed", None)
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(
                smoke_execution.subprocess,
                "Popen",
                return_value=process,
            ),
            mock.patch.object(
                Path,
                "write_text",
                side_effect=OSError("private log failure"),
            ),
        ):
            result = smoke.run_command(
                ["adb", "reverse"],
                cwd=ROOT,
                log_path=Path(temporary_dir) / "device-preflight.log",
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertFalse(result["timedOut"])
        self.assertEqual(result["secondaryFailures"][0]["stage"], "log-write")
        self.assertNotIn("private log failure", repr(result))

    def test_patrol_test_execution_prefers_xctest_over_zero_patrol_summary(
        self,
    ) -> None:
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
            "📝 Total: 2\n✅ Successful: 2\n❌ Failed: 0\n⏩ Skipped: 0\n"
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

    @mock.patch.object(smoke_device_runtime, "run_command")
    def test_release_bound_ios_uat_resets_app_and_test_runner_state(
        self,
        run: mock.Mock,
    ) -> None:
        run.return_value = {
            "exitCode": 0,
            "timedOut": False,
            "outputSummary": "",
            "logPath": "device-preflight.log",
        }
        args = self._args(release_uat_cases="/tmp/homepage_verification_cases.json")
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

    @mock.patch.object(smoke_device_runtime, "run_command")
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

    @mock.patch.object(
        smoke_device_runtime, "resolve_android_debug_bridge", return_value="/sdk/adb"
    )
    @mock.patch.object(smoke_device_runtime, "run_command")
    def test_release_bound_android_uat_treats_uninstalled_app_as_reset(
        self,
        run: mock.Mock,
        _resolve_adb: mock.Mock,
    ) -> None:
        run.return_value = {
            "exitCode": 1,
            "timedOut": False,
            "outputSummary": "",
            "logPath": "device-preflight.log",
        }
        args = self._args(release_uat_cases="/tmp/homepage_verification_cases.json")
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
            cwd=ROOT,
            env=mock.ANY,
            timeout_seconds=(
                smoke_device_runtime._DEVICE_PREFLIGHT_COMMAND_TIMEOUT_SECONDS
            ),
            log_path=mock.ANY,
            secret_values=mock.ANY,
        )

    @mock.patch.object(smoke_device_runtime, "run_command")
    def test_ios_uninstall_timeout_is_typed_and_stops_the_reset_sequence(
        self,
        run: mock.Mock,
    ) -> None:
        args = self._args(release_uat_cases="/tmp/release-cases.json")
        device = {
            "id": "ios-release-uat",
            "targetPlatform": "ios",
            "emulator": True,
        }

        for exit_code, timed_out in ((1, True), (124, False)):
            with self.subTest(exit_code=exit_code, timed_out=timed_out):
                run.reset_mock()
                run.return_value = _managed_result(
                    exit_code=exit_code,
                    output="application not installed; no such file",
                    timed_out=timed_out,
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    r"APP\.LAUNCH\.device_unavailable: ios-uninstall-1 timed out",
                ):
                    smoke._reset_release_uat_device_state(args, device)
                self.assertEqual(run.call_count, 1)
                self.assertIn(
                    "runs/ios-release-uat/device-preflight-ios-uninstall-1.log",
                    str(run.call_args.kwargs["log_path"]),
                )

    @mock.patch.object(
        smoke_device_runtime,
        "resolve_android_debug_bridge",
        return_value="/sdk/adb",
    )
    @mock.patch.object(smoke_device_runtime, "run_command")
    def test_android_pm_path_timeout_remains_primary_and_skips_clear(
        self,
        run: mock.Mock,
        _resolve_adb: mock.Mock,
    ) -> None:
        run.return_value = _managed_result(
            exit_code=124,
            output="pm path timed out",
            timed_out=True,
        )
        args = self._args(release_uat_cases="/tmp/release-cases.json")
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }

        with self.assertRaisesRegex(
            RuntimeError,
            r"APP\.LAUNCH\.device_unavailable: android-pm-path timed out",
        ):
            smoke._reset_release_uat_device_state(args, device)

        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][4:6], ["pm", "path"])

    @mock.patch.object(
        smoke_device_runtime,
        "resolve_android_debug_bridge",
        return_value="/sdk/adb",
    )
    @mock.patch.object(smoke_device_runtime, "run_command")
    def test_android_pm_clear_timeout_is_not_relabelled_as_presence_failure(
        self,
        run: mock.Mock,
        _resolve_adb: mock.Mock,
    ) -> None:
        run.side_effect = (
            _managed_result(exit_code=0, output="package:/data/app/base.apk"),
            _managed_result(
                exit_code=124,
                output="pm clear timed out",
                timed_out=True,
            ),
        )
        args = self._args(release_uat_cases="/tmp/release-cases.json")
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }

        with self.assertRaisesRegex(
            RuntimeError,
            r"APP\.LAUNCH\.device_unavailable: android-pm-clear timed out",
        ):
            smoke._reset_release_uat_device_state(args, device)

        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][4:6], ["pm", "path"])
        self.assertEqual(run.call_args_list[1].args[0][4:6], ["pm", "clear"])

    @mock.patch.object(
        smoke_device_runtime,
        "resolve_android_debug_bridge",
        return_value="/sdk/adb",
    )
    @mock.patch.object(smoke_device_runtime, "run_command")
    def test_android_pm_primary_failure_is_redacted_and_precedes_clear(
        self,
        run: mock.Mock,
        _resolve_adb: mock.Mock,
    ) -> None:
        secret = "uat-secret-token"
        run.return_value = _managed_result(
            exit_code=2,
            output=f"token={secret} log=/private/device-preflight.log",
        )
        args = self._args(release_uat_cases="/tmp/release-cases.json")
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }

        with (
            mock.patch.dict(
                os.environ,
                {"TEST_AUTH_TOKEN": secret, "PATH": "/usr/bin", "HOME": "/tmp"},
                clear=True,
            ),
            self.assertRaises(RuntimeError) as caught,
        ):
            smoke._reset_release_uat_device_state(args, device)

        rendered = str(caught.exception)
        self.assertIn("APP.LAUNCH.device_unavailable: android-pm-path failed", rendered)
        self.assertNotIn(secret, rendered)
        self.assertNotIn("/private/device-preflight.log", rendered)
        self.assertEqual(run.call_count, 1)
        kwargs = run.call_args.kwargs
        self.assertNotIn("TEST_AUTH_TOKEN", kwargs["env"])
        self.assertIn(secret, kwargs["secret_values"])

    @mock.patch.object(
        smoke_device_runtime,
        "resolve_android_debug_bridge",
        return_value="/sdk/adb",
    )
    @mock.patch.object(smoke_device_runtime, "run_command")
    def test_android_reverse_timeout_is_typed_and_stops_remaining_ports(
        self,
        run: mock.Mock,
        _resolve_adb: mock.Mock,
    ) -> None:
        run.return_value = _managed_result(
            exit_code=124,
            output="adb reverse timed out",
            timed_out=True,
        )
        args = self._args()
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }

        with self.assertRaisesRegex(
            RuntimeError,
            r"APP\.LAUNCH\.device_unavailable: android-reverse-19000 timed out",
        ):
            smoke._prepare_android_local_port_reverse(args, device)

        self.assertEqual(run.call_count, 1)
        self.assertEqual(
            run.call_args.args[0][3:], ["reverse", "tcp:19000", "tcp:19000"]
        )
        self.assertIn(
            "runs/emulator-5554/device-preflight-android-reverse-19000.log",
            str(run.call_args.kwargs["log_path"]),
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

"""environment patrol smoke：device 命令环境、TLS 证据与本地 runtime/release 组合契约。

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

from quwoquan_ops.ci.device_matrix import android as android_device
from quwoquan_ops.ci.device_matrix import evidence as device_evidence
from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.content_release_readiness import VerificationProfile
from quwoquan_ops.cli.lib.package_reuse import (
    patrol_command_envelope as envelope_contract,
)
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke

# 入口拆为薄壳 + environment_patrol_smoke 子包后，mock.patch.object 必须打在
# 被测函数实际读取全局名的实现模块上，而不是入口 re-export 的绑定上。
from quwoquan_ops.cli.smoke.environment_patrol_smoke import (
    device_runtime as smoke_device_runtime,
)
from quwoquan_ops.tests.support.environment_patrol_smoke_test_support import (
    EnvironmentPatrolSmokeCaseBase,
)


def _reverse_result(
    *, exit_code: int, output: str = "", timed_out: bool = False
) -> dict[str, object]:
    return {
        "exitCode": exit_code,
        "timedOut": timed_out,
        "outputSummary": output,
        "logPath": "/tmp/android-reverse.log",
    }


class EnvironmentPatrolSmokeTest(EnvironmentPatrolSmokeCaseBase):
    def _sealed_flutter_environment(self) -> tuple[dict[str, str], dict[str, str]]:
        identity = {
            "executable": "/private/sdk/flutter/bin/flutter",
            "flutterVersion": "3.47.0",
            "commandResolutionDigest": "sha256:" + "f" * 64,
        }
        envelope = envelope_contract.patrol_command_envelope(
            flutter_identity=identity,
            path="/private/sdk/flutter/bin:/usr/bin:/bin",
        )
        with mock.patch.object(
            envelope_contract,
            "resolved_flutter_identity",
            return_value=identity,
        ):
            environment = envelope_contract.rebuild_patrol_command_environment(
                envelope=envelope,
                ambient_environment={},
                dependency_environment={},
                command_environment={},
            )
        return environment, identity

    def test_device_command_env_configures_android_toolchain_without_private_ca(
        self,
    ) -> None:
        args = self._args()
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }

        with mock.patch.object(
            smoke_device_runtime,
            "resolve_android_debug_bridge",
            return_value="/sdk/platform-tools/adb",
        ):
            env = smoke._device_command_env(args, device)

        self.assertEqual(env["ANDROID_SERIAL"], "emulator-5554")
        self.assertEqual(
            env["PATH"].split(os.pathsep)[0],
            "/sdk/platform-tools",
        )

    def test_device_command_env_injects_selected_ios_simulator_udid(self) -> None:
        args = self._args()
        device = {
            "id": "selected-ios-simulator",
            "targetPlatform": "ios",
            "emulator": True,
        }

        env = smoke._device_command_env(args, device)

        self.assertEqual(env["QWQ_IOS_SIMULATOR_UDID"], "selected-ios-simulator")
        self.assertEqual(env["QWQ_LAUNCH_TARGET"], "gamma-local")

    def test_sealed_flutter_identity_is_exact_for_android_and_ios_without_proxy(
        self,
    ) -> None:
        sealed, identity = self._sealed_flutter_environment()
        ambient = {
            "JAVA_TOOL_OPTIONS": "-javaagent:/ambient/agent.jar",
            "GRADLE_OPTS": "-Dambient=true",
            "PUB_HOSTED_URL": "https://ambient-pub.invalid",
            "FLUTTER_STORAGE_BASE_URL": "https://ambient-flutter.invalid",
            "TEST_AUTH_TOKEN": "ambient-auth-token",
            "QWQ_TEST_DATA_ACCESS_TOKEN": "ambient-actor-token",
            **sealed,
            **{
                key: f"http://ambient-{key}.invalid"
                for key in envelope_contract.PROXY_ENVIRONMENT_KEYS
            },
        }
        devices = (
            {
                "id": "emulator-5554",
                "targetPlatform": "android-arm64",
                "emulator": True,
            },
            {
                "id": "SIMULATOR-UDID",
                "targetPlatform": "ios",
                "emulator": True,
            },
        )
        for device in devices:
            with (
                self.subTest(platform=device["targetPlatform"]),
                mock.patch.dict(os.environ, ambient, clear=True),
                mock.patch.object(
                    envelope_contract,
                    "resolved_flutter_identity",
                    return_value=identity,
                ),
                mock.patch.object(
                    smoke_device_runtime,
                    "resolve_android_debug_bridge",
                    return_value="/foreign/adb-parent/adb",
                ),
            ):
                env = smoke._device_command_env(self._args(), device)
            self.assertEqual(env["PATH"], sealed["PATH"])
            self.assertEqual(
                env[envelope_contract.PATROL_REAL_FLUTTER_ENV],
                identity["executable"],
            )
            self.assertTrue(
                all(key not in env for key in envelope_contract.PROXY_ENVIRONMENT_KEYS)
            )
            self.assertTrue(
                all(
                    key not in env
                    for key in (
                        "JAVA_TOOL_OPTIONS",
                        "GRADLE_OPTS",
                        "PUB_HOSTED_URL",
                        "FLUTTER_STORAGE_BASE_URL",
                    )
                )
            )
            self.assertEqual(env["TEST_AUTH_TOKEN"], "")
            self.assertEqual(env["QWQ_TEST_DATA_ACCESS_TOKEN"], "")

    def test_sealed_flutter_actual_identity_drift_fails_closed(self) -> None:
        sealed, identity = self._sealed_flutter_environment()
        drifted = {**identity, "flutterVersion": "3.48.0"}
        with (
            mock.patch.dict(os.environ, sealed, clear=True),
            mock.patch.object(
                envelope_contract,
                "resolved_flutter_identity",
                return_value=drifted,
            ),
            self.assertRaisesRegex(RuntimeError, "sealed command environment drifted"),
        ):
            smoke._device_command_env(
                self._args(),
                {
                    "id": "SIMULATOR-UDID",
                    "targetPlatform": "ios",
                    "emulator": True,
                },
            )

    def test_device_command_env_uses_canonical_alias_target_not_external_or_test_path(
        self,
    ) -> None:
        args = self._args(
            env_name="local-alpha",
            runtime_env="alpha",
            target="test/user_acceptance/prod-hosted.dart",
        )
        device = {
            "id": "selected-ios-simulator",
            "targetPlatform": "ios",
            "emulator": True,
        }

        with mock.patch.dict(
            os.environ,
            {"QWQ_LAUNCH_TARGET": "prod-hosted"},
        ):
            env = smoke._device_command_env(args, device)

        self.assertEqual(env["QWQ_LAUNCH_TARGET"], "alpha-local")

    def test_canonical_test_live_handoff_uses_device_transport_without_content(
        self,
    ) -> None:
        args = self._args()
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }
        command_env = {
            "QWQ_ANDROID_REVERSE_EXPECTED_PORTS": "19000,19010,19100,19130",
            "QWQ_ANDROID_REVERSE_ACTUAL_PORTS": "19000,19010,19100,19130",
            "QWQ_ANDROID_REVERSE_RECEIPT_DIGEST": "sha256:" + "6" * 64,
            "QWQ_CONSUMER_LEASE_ID": "sha256:" + "7" * 64,
        }
        handoff = self._launcher_handoff(args)
        completed = subprocess.CompletedProcess(
            args=[str(smoke.APP_LAUNCHER_HANDOFF_BUILDER)],
            returncode=0,
            stdout=json.dumps(handoff),
            stderr="",
        )

        def run_builder(
            command: list[str],
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            trust_option = command.index("--runtime-config-trust-output")
            Path(command[trust_option + 1]).write_text("{}", encoding="utf-8")
            return completed

        with (
            mock.patch.object(smoke.subprocess, "run", side_effect=run_builder) as run,
        ):
            actual = smoke._canonical_test_live_launcher_handoff(
                args,
                device,
                command_env,
            )

        self.assertEqual(actual, handoff)
        builder_command = run.call_args.args[0]
        self.assertIn("--launch-provenance", builder_command)
        self.assertEqual(
            builder_command[builder_command.index("--launch-provenance") + 1],
            "canonical_launcher",
        )
        self.assertIn("--launch-policy", builder_command)
        self.assertEqual(
            builder_command[builder_command.index("--launch-policy") + 1],
            "test_live",
        )
        # 内容激活是运行时服务端事实，launcher handoff 不得携带内容身份。
        self.assertNotIn("--content-release-id", builder_command)
        self.assertNotIn("--content-manifest-digest", builder_command)
        self.assertNotIn(
            "--content-readiness-receipt-digest",
            builder_command,
        )
        for option, value in (
            ("--reverse-expected-ports", "19000,19010,19100,19130"),
            ("--reverse-actual-ports", "19000,19010,19100,19130"),
            ("--reverse-receipt-digest", "sha256:" + "6" * 64),
            ("--consumer-lease-id", "sha256:" + "7" * 64),
        ):
            self.assertEqual(
                builder_command[builder_command.index(option) + 1],
                value,
            )

    @mock.patch.object(smoke.shutil, "which", return_value="/sdk/flutter")
    @mock.patch.object(
        smoke_device_runtime,
        "resolve_android_debug_bridge",
        return_value="/sdk/platform-tools/adb",
    )
    def test_same_handoff_drives_patrol_defines_and_raw_gradle_environment(
        self,
        _resolve_adb: mock.Mock,
        _which: mock.Mock,
    ) -> None:
        args = self._args()
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }
        handoff = self._launcher_handoff(args)
        poisoned = {
            "QWQ_DART_DEFINES_DIGEST": "sha256:" + "f" * 64,
            "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST": "sha256:" + "e" * 64,
            "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST": "sha256:" + "d" * 64,
            "QWQ_APP_LAUNCH_POLICY": "prod_release",
            "QWQ_CONTENT_RELEASE_ID": "stale-release",
        }

        with mock.patch.dict(os.environ, poisoned, clear=False):
            environment = smoke._device_command_env(
                args,
                device,
                launcher_handoff=handoff,
            )
            command = smoke.patrol_command(
                device,
                args,
                "patrol",
                dart_define_file=Path("/protected/session.json"),
                launcher_handoff=handoff,
            )

        # 编译期不再有 dart-define 摘要可比；单轨的是签名 package 与信任根摘要。
        self.assertNotIn("QWQ_DART_DEFINES_DIGEST", environment)
        self.assertEqual(
            environment["QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST"],
            handoff["runtimeConfigPackageDigest"],
        )
        self.assertEqual(
            environment["QWQ_EXPECTED_RUNTIME_CONFIG_TRUST_DIGEST"],
            handoff["runtimeConfigTrustEnvelopeDigest"],
        )
        self.assertEqual(
            environment["QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST"],
            handoff["effectiveLaunchManifestDigest"],
        )
        self.assertEqual(environment["QWQ_APP_BUILD_CONTEXT"], "runtime")
        self.assertEqual(
            environment["QWQ_APP_LAUNCH_PROVENANCE"],
            "canonical_launcher",
        )
        self.assertEqual(
            environment["QWQ_RUNTIME_CONFIG_SUPPLY_MODE"],
            "external_runtime_package",
        )
        self.assertEqual(environment["QWQ_APP_LAUNCH_POLICY"], "test_live")
        self.assertNotIn("QWQ_CONTENT_RELEASE_ID", environment)
        command_defines: dict[str, list[str]] = {}
        for argument in command:
            if not argument.startswith("--dart-define="):
                continue
            key, value = argument.removeprefix("--dart-define=").split("=", 1)
            command_defines.setdefault(key, []).append(value)
        # 测试宿主的 define 只能是签名 package runtime 值的投影。
        for key, value in smoke._test_host_dart_defines(handoff).items():
            self.assertEqual(command_defines[key], [value])

    def test_canonical_handoff_rejects_missing_define_or_nested_digest_drift(
        self,
    ) -> None:
        args = self._args()
        stale_field = self._launcher_handoff(args)
        stale_field["launch" + "Mode"] = "canonical_launcher"
        with self.assertRaisesRegex(ValueError, "generated contract"):
            smoke._canonical_handoff_projection(stale_field)

        missing_value = self._launcher_handoff(args)
        del missing_value["runtimeConfigPackage"]["runtime"]["legalBaseUrl"]
        with self.assertRaisesRegex(ValueError, "runtime value is missing"):
            smoke._canonical_handoff_projection(missing_value)

        digest_drift = self._launcher_handoff(args)
        digest_drift["effectiveLaunchManifest"]["runtimeConfigPackageDigest"] = (
            "sha256:" + "9" * 64
        )
        with self.assertRaisesRegex(ValueError, "effective manifest mismatch"):
            smoke._canonical_handoff_projection(digest_drift)

    def test_device_command_env_rejects_target_path_as_environment_alias(self) -> None:
        args = self._args()
        args.env_name = "test/user_acceptance/gamma-local.dart"

        with self.assertRaisesRegex(
            ValueError,
            "does not resolve to a canonical launch target",
        ):
            smoke._device_command_env(
                args,
                {
                    "id": "selected-ios-simulator",
                    "targetPlatform": "ios",
                    "emulator": True,
                },
            )

    def test_device_command_env_blocks_local_ios_simulator_without_id(self) -> None:
        args = self._args()

        with self.assertRaisesRegex(RuntimeError, "explicit device id"):
            smoke._device_command_env(
                args,
                {"targetPlatform": "ios", "emulator": True},
            )

    def test_android_debug_bridge_resolves_configured_sdk_when_adb_is_not_on_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            sdk_root = Path(temporary_dir)
            adb = sdk_root / "platform-tools" / "adb"
            adb.parent.mkdir(parents=True)
            adb.write_text("#!/bin/sh\n", encoding="utf-8")
            adb.chmod(0o755)

            with mock.patch.object(android_device.shutil, "which", return_value=None):
                resolved = android_device.resolve_android_debug_bridge(
                    environ={"ANDROID_SDK_ROOT": str(sdk_root)},
                    home_dir=Path("/no-sdk-home"),
                )

        self.assertEqual(resolved, str(adb))

    def test_android_evidence_capture_uses_resolved_sdk_adb(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            screenshot = Path(temporary_dir) / "capture.png"
            device = {"id": "emulator-5554", "targetPlatform": "android-arm64"}
            with (
                mock.patch.object(
                    device_evidence,
                    "resolve_android_debug_bridge",
                    return_value="/sdk/platform-tools/adb",
                ),
                mock.patch.object(
                    device_evidence.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        ["/sdk/platform-tools/adb"],
                        0,
                        stdout=b"png",
                        stderr=b"",
                    ),
                ),
            ):
                result = device_evidence.capture_device_screenshot(device, screenshot)

            self.assertEqual(result["status"], "captured")
            self.assertEqual(screenshot.read_bytes(), b"png")
            self.assertEqual(result["command"][0], "/sdk/platform-tools/adb")

    def test_screenshot_timeout_is_evidence_failure_not_an_uncaught_error(self) -> None:
        cases = (
            ({"id": "emulator-5554", "targetPlatform": "android-arm64"}, "Android"),
            ({"id": "ios-simulator", "targetPlatform": "ios", "emulator": True}, "iOS"),
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            for device, platform in cases:
                with (
                    self.subTest(platform=platform),
                    mock.patch.object(
                        device_evidence,
                        "resolve_android_debug_bridge",
                        return_value="/sdk/platform-tools/adb",
                    ),
                    mock.patch.object(
                        device_evidence.subprocess,
                        "run",
                        side_effect=subprocess.TimeoutExpired("screenshot", 30),
                    ),
                ):
                    result = device_evidence.capture_device_screenshot(
                        device,
                        Path(temporary_dir) / f"{platform}.png",
                    )

                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["failureKind"], "screenshot_timeout")

    def test_android_local_target_reverses_all_injected_authority_ports(self) -> None:
        args = self._args()
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }
        calls: list[list[str]] = []

        command_kwargs: list[dict[str, object]] = []

        def run_adb(command: list[str], **kwargs: object) -> dict[str, object]:
            calls.append(command)
            command_kwargs.append(dict(kwargs))
            return {
                "exitCode": 0,
                "timedOut": False,
                "outputSummary": "",
                "logPath": str(kwargs["log_path"]),
            }

        with (
            mock.patch.object(
                smoke_device_runtime,
                "resolve_android_debug_bridge",
                return_value="/usr/bin/adb",
            ),
            mock.patch.object(
                smoke_device_runtime,
                "run_command",
                side_effect=run_adb,
            ),
        ):
            result = smoke._prepare_android_local_port_reverse(args, device)

        self.assertEqual(result["status"], "installed")
        install_calls = [command for command in calls if command[-1] != "--list"]
        self.assertEqual(
            {command[-1] for command in install_calls},
            {"tcp:19000", "tcp:19010", "tcp:19100", "tcp:19130"},
        )
        self.assertTrue(
            all(command[3] == "reverse" for command in calls),
        )
        self.assertTrue(
            all(
                kwargs["timeout_seconds"]
                == smoke_device_runtime._DEVICE_PREFLIGHT_COMMAND_TIMEOUT_SECONDS
                for kwargs in command_kwargs
            )
        )
        self.assertEqual(
            len({str(kwargs["log_path"]) for kwargs in command_kwargs}),
            len(calls),
        )

    def test_android_reverse_cleanup_removes_only_owned_mapping(self) -> None:
        args = self._args()
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }
        results = [
            _reverse_result(
                exit_code=0,
                output=(
                    "UsbFfs tcp:19000 tcp:19000\n"
                    "UsbFfs tcp:19999 tcp:19999\n"
                ),
            ),
            _reverse_result(exit_code=0),
            _reverse_result(exit_code=0),
            _reverse_result(exit_code=0),
            _reverse_result(exit_code=0),
            _reverse_result(exit_code=0),
            _reverse_result(exit_code=0),
        ]
        with (
            mock.patch.object(
                smoke_device_runtime,
                "resolve_android_debug_bridge",
                return_value="/usr/bin/adb",
            ),
            mock.patch.object(
                smoke_device_runtime, "run_command", side_effect=results
            ) as run,
        ):
            state = smoke._prepare_android_local_port_reverse(args, device)
            teardown = smoke._cleanup_android_local_port_reverse(
                args, device, state
            )

        self.assertEqual(state["status"], "installed")
        self.assertEqual(teardown["status"], "passed")
        self.assertEqual(teardown["removedDevicePorts"], [19010, 19100, 19130])
        remove_commands = [
            call.args[0]
            for call in run.call_args_list
            if "--remove" in call.args[0]
        ]
        self.assertEqual(
            [command[-1] for command in remove_commands],
            ["tcp:19010", "tcp:19100", "tcp:19130"],
        )
        self.assertNotIn("tcp:19000", [command[-1] for command in remove_commands])
        self.assertNotIn("tcp:19999", [command[-1] for command in remove_commands])

    def test_android_reverse_mid_install_failure_rolls_back_owned_and_keeps_primary(self) -> None:
        args = self._args()
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }
        results = [
            _reverse_result(exit_code=0, output=""),
            _reverse_result(exit_code=0),
            _reverse_result(exit_code=2, output="install failed"),
            _reverse_result(exit_code=2, output="cleanup failed"),
        ]
        with (
            mock.patch.object(
                smoke_device_runtime,
                "resolve_android_debug_bridge",
                return_value="/usr/bin/adb",
            ),
            mock.patch.object(
                smoke_device_runtime, "run_command", side_effect=results
            ) as run,
            self.assertRaisesRegex(
                RuntimeError,
                r"APP\.LAUNCH\.device_unavailable: android-reverse-19010 failed",
            ) as caught,
        ):
            smoke._prepare_android_local_port_reverse(args, device)

        state = getattr(caught.exception, "android_port_reverse")
        self.assertEqual(state["firstBlocker"], str(caught.exception))
        self.assertEqual(state["teardown"]["status"], "failed")
        self.assertEqual(state["teardown"]["removedDevicePorts"], [])
        self.assertEqual(run.call_args.args[0][-2:], ["--remove", "tcp:19000"])
        self.assertNotIn("android-reverse-remove", str(caught.exception))

    def test_android_reverse_cleanup_failure_does_not_replace_main_blocker(self) -> None:
        args = self._args()
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }
        state = {
            "status": "installed",
            "deviceId": "emulator-5554",
            "adbExecutable": "/usr/bin/adb",
            "mappings": [
                {"devicePort": 19000, "hostPort": 19000, "owned": True}
            ],
            "ownedMappings": [
                {"devicePort": 19000, "hostPort": 19000, "owned": True}
            ],
        }
        with mock.patch.object(
            smoke_device_runtime,
            "run_command",
            return_value=_reverse_result(exit_code=2, output="cleanup failed"),
        ):
            teardown = smoke._cleanup_android_local_port_reverse(
                args, device, state
            )

        self.assertEqual(teardown["status"], "failed")
        self.assertIn("android-reverse-remove-19000", teardown["failures"][0])
        # teardown 是 best-effort evidence；调用方已有 blocker 时不抛异常。
        self.assertIs(teardown, state["teardown"])

    def test_patrol_tls_evidence_uses_system_public_ca_without_trust_install(
        self,
    ) -> None:
        self.assertEqual(
            smoke._local_tls_trust_evidence(dry_run=False),
            {"status": "system-public-ca", "reason": "dns-01"},
        )
        self.assertEqual(
            smoke._local_tls_trust_evidence(dry_run=True),
            {"status": "skipped", "reason": "not-required"},
        )

    def test_alpha_uses_the_shared_packaged_local_runtime_entrypoint(self) -> None:
        retired = ROOT / "quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh"
        stackctl_source = (ROOT / "quwoquan_ops/cli/commands/up_runtime.py").read_text(
            encoding="utf-8"
        )

        self.assertFalse(retired.exists())
        self.assertIn(
            'requested_target in {"alpha-local", "beta-local", "gamma-local"}',
            stackctl_source,
        )
        self.assertIn(
            "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
            stackctl_source,
        )
        self.assertNotIn("start_beta_stack.sh", stackctl_source)
        self.assertNotIn("run_alpha_content_release_stack.sh", stackctl_source)

    def test_local_launchers_and_tls_stacks_use_public_ca_helper(self) -> None:
        app_instance = (
            ROOT / "quwoquan_app/scripts/device/run_app_instance.sh"
        ).read_text(encoding="utf-8")
        beta_manual = (
            ROOT / "quwoquan_app/scripts/tools/device/beta_manual_app.sh"
        ).read_text(encoding="utf-8")
        dev_up = (ROOT / "quwoquan_ops/cli/lib/dev_up.py").read_text(encoding="utf-8")
        public_tls = (ROOT / "quwoquan_ops/cli/lib/public_domain_tls.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('public_domain_tls.py" verify', app_instance)
        self.assertIn('--target "$TARGET_NAME"', app_instance)
        self.assertIn('public_domain_tls.py" paths', beta_manual)
        self.assertIn("--target beta-local", beta_manual)
        self.assertIn("fullchain.pem", public_tls)
        self.assertIn("privkey.pem", public_tls)
        self.assertIn('command_env["QWQ_IOS_SIMULATOR_UDID"] = device_id', dev_up)
        self.assertFalse(
            (ROOT / "quwoquan_ops/cli/lib/local_target_tls.py").exists(),
        )

    def test_beta_uses_one_immutable_release_consumer_backend(self) -> None:
        beta_manual = (
            ROOT / "quwoquan_app/scripts/tools/device/beta_manual_app.sh"
        ).read_text(encoding="utf-8")
        beta_stack = (ROOT / "quwoquan_ops/cli/beta/start_beta_stack.sh").read_text(
            encoding="utf-8"
        )
        beta_backing_compose = (
            ROOT / "quwoquan_ops/environments/compose/docker-compose.beta-backing.yaml"
        ).read_text(encoding="utf-8")
        beta_service_compose = "\n".join(
            (
                ROOT
                / "quwoquan_service"
                / "services"
                / service
                / "deploy"
                / "compose.yaml"
            ).read_text(encoding="utf-8")
            for service in (
                "recommendation-service",
                "content-service",
                "user-service",
                "entity-service",
            )
        )
        data_plane = beta_manual.index("beta_manual_ensure_data_plane || return 1")
        media_runtime = beta_manual.index(
            "beta_manual_start_release_media_runtime || return 1",
            data_plane,
        )
        entity_runtime = beta_manual.index(
            "beta_manual_start_entity_service || return 1",
            media_runtime,
        )
        public_ingress = beta_manual.index(
            "beta_manual_start_tls_proxy || return 1",
            entity_runtime,
        )
        self.assertLess(data_plane, media_runtime)
        self.assertLess(media_runtime, entity_runtime)
        self.assertLess(entity_runtime, public_ingress)
        for token in (
            "docker-compose.beta-backing.yaml",
            "quwoquan-beta-backing",
            "mongodb://127.0.0.1:${BETA_MONGO_PORT}/?directConnection=true",
            "127.0.0.1:${BETA_REDIS_PORT}",
            'ENTITY_REDIS_GENERAL_ADDR="127.0.0.1:${BETA_REDIS_PORT}"',
            "export CONTENT_PORT",
            "export BETA_POSTGRES_PORT BETA_MONGO_PORT BETA_REDIS_PORT",
            "BETA_OBJECT_STORAGE_EDGE_PORT",
            "BETA_SERVICE_CONFIG_ROOT",
            "recommendation-service",
            "content-service",
            "https://${PUBLIC_API_HOST}:${GATEWAY_PORT}",
            "https://${PUBLIC_IMAGE_HOST}:${MEDIA_PORT}",
            '-p "${GATEWAY_PORT}:${GATEWAY_PORT}"',
            '-p "${MEDIA_PORT}:${MEDIA_PORT}"',
            "ship apply is the only writer of this directory",
            "respond 404",
        ):
            self.assertIn(token, beta_manual)
        self.assertNotIn("LOCAL_GAMMA_", beta_manual)
        for retired in (
            "contracts/metadata/_shared/test_fixtures",
            "dev_assistant_beta_gateway.py",
            "beta_manual_start_fixture_gateway",
            "beta_manual_start_notification_service",
            "go run ./cmd/seed-fixture",
            "go run ./services/user-service/cmd/seed",
            "fixture_user_current",
            "START_ASSISTANT",
            "CONTENT_RELEASE_ONLY",
            "CHAT_SEED_LOG",
            "BETA_FIXTURE_GATEWAY_PORT",
        ):
            self.assertNotIn(retired, beta_manual)
        self.assertIn("BETA_MONGO_PORT", beta_backing_compose)
        self.assertIn("BETA_REDIS_PORT", beta_backing_compose)
        self.assertIn("object-storage:", beta_backing_compose)
        self.assertNotIn("recommendation-service:", beta_backing_compose)
        self.assertNotIn("content-service:", beta_backing_compose)
        self.assertIn("recommendation-service:", beta_service_compose)
        self.assertIn("content-service:", beta_service_compose)
        self.assertIn("CONTENT_POSTGRES_REPORT_DSN", beta_service_compose)
        self.assertIn(
            'CONTENT_EMBEDDING_ENDPOINT: "${QWQ_COMPOSE_EMBEDDING_ENDPOINT:-}"',
            beta_service_compose,
        )
        self.assertIn(
            'CONTENT_EMBEDDING_API_KEY: "${QWQ_COMPOSE_EMBEDDING_API_KEY:-}"',
            beta_service_compose,
        )
        self.assertIn(
            'SEARCH_ES_ENABLED: "${QWQ_COMPOSE_SEARCH_ES_ENABLED:-true}"',
            beta_service_compose,
        )
        self.assertIn(
            "export QWQ_COMPOSE_SEARCH_ES_ENABLED=false",
            beta_manual,
        )
        self.assertIn(
            "SEARCH_ES_ENABLED=false",
            beta_manual,
        )
        self.assertIn(
            "beta_manual_require_content_embedding_binding",
            beta_manual,
        )
        self.assertNotIn("local_provider_credentials", beta_manual)
        self.assertIn(
            "stackctl did not inject protected Beta content embedding Provider material",
            beta_manual,
        )
        self.assertLess(
            beta_manual.index(
                "beta_manual_require_content_embedding_binding || return 1",
            ),
            beta_manual.index("beta_manual_ensure_docker_daemon || return 1"),
        )
        self.assertIn(
            'CONFIG_VERSION: "${QWQ_COMPOSE_CONTENT_SERVICE_CONFIG_VERSION:',
            beta_service_compose,
        )
        self.assertNotIn("BETA_CONTENT_RELEASE_CONFIG_VERSION", beta_manual)
        self.assertIn(
            'content-service) export CONTENT_CONFIG_VERSION="$config_version"',
            beta_manual,
        )
        self.assertIn(
            'recommendation-service) export RECOMMENDATION_CONFIG_VERSION="$config_version"',
            beta_manual,
        )
        self.assertNotIn("--write-report-account-backfill", beta_manual)
        self.assertIn(
            "recommendation_policy.yaml",
            beta_manual,
        )
        self.assertIn("quwoquan_ops/cli/stackctl.py", beta_stack)
        self.assertIn("--target beta-local", beta_stack)
        self.assertNotIn("APP_BETA_CMD", beta_stack)
        self.assertNotIn("go run", beta_stack)
        self.assertIn("beta_manual_start_content_release_stack", beta_manual)
        self.assertIn(
            "for service in content-service entity-service recommendation-service user-service",
            beta_manual,
        )
        self.assertIn(
            "@content_release path /content /content/* /config/app", beta_manual
        )
        self.assertIn("@homepage_release path /homepages /homepages/*", beta_manual)
        self.assertIn(
            "@creator_profile_release path /auth /auth/* /user /user/* /users /users/*",
            beta_manual,
        )

    def test_search_dependency_is_owned_by_each_environment_overlay_not_content_base(
        self,
    ) -> None:
        content_compose = (
            ROOT / "quwoquan_service/services/content-service/deploy/compose.yaml"
        ).read_text(encoding="utf-8")
        content_dependencies = content_compose.split("    depends_on:\n", 1)[1].split(
            "    ports:\n", 1
        )[0]

        self.assertNotIn(
            "elasticsearch:",
            content_dependencies,
            (
                "content-service base makes Alpha/Beta content-release depend on "
                "Elasticsearch even though only full/content-commercial loads the "
                "package-bound Product Ops Elasticsearch Compose"
            ),
        )
        for environment in ("alpha", "beta", "gamma"):
            with self.subTest(environment=environment):
                environment_overlay = (
                    ROOT
                    / "quwoquan_service"
                    / "services"
                    / "content-service"
                    / "environments"
                    / environment
                    / "deploy"
                    / "compose.yaml"
                ).read_text(encoding="utf-8")
                self.assertIn(
                    "elasticsearch:\n        condition: service_healthy",
                    environment_overlay,
                )


if __name__ == "__main__":
    unittest.main()

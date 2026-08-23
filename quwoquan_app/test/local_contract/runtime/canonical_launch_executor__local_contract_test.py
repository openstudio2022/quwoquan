# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

from __future__ import annotations

import json
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
sys.path.insert(0, str(APP_DIR / "test/support/runtime/launcher"))

import build_launcher_handoff as handoff_builder
import canonical_app_instance.activation as activation
import run_app_instance as executor
from canonical_launch_platform_test_support import (
    CanonicalLaunchPlatformContractMixin,
)
from launcher_package_fixture import (
    build_test_handoff_fixture,
    shared_nonprod_launcher_authority,
)
from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    runtime_config_activation_request_digest,
)


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


class _FakePlatformDriver:
    def __init__(self, *, active_receipt: bytes | None = None) -> None:
        self.events: list[str] = []
        self.files: dict[str, bytes] = {}
        if active_receipt is not None:
            self.files[executor.ACTIVE_RECEIPT_FILE_NAME] = active_receipt
        self.request: dict[str, object] | None = None

    def build(self, environment: dict[str, str]) -> None:
        self.events.append("build")
        for forbidden in executor.FORBIDDEN_COMPILE_ENVIRONMENT_KEYS:
            if forbidden.endswith("*"):
                prefix = forbidden[:-1]
                if any(key.startswith(prefix) for key in environment):
                    raise AssertionError(f"compile environment leaked prefix {prefix}")
            elif forbidden in environment:
                raise AssertionError(f"compile environment leaked {forbidden}")

    def install(self) -> None:
        self.events.append("install")

    def read_runtime_file(self, file_name: str) -> bytes | None:
        self.events.append(f"read:{file_name}")
        return self.files.get(file_name)

    def write_activation_request(self, payload: bytes) -> None:
        self.events.append("write-request")
        self.request = json.loads(payload)

    def launch_activation(self, request_digest: str) -> None:
        self.events.append("launch-activation")
        assert self.request is not None
        request = self.request
        receipt = {
            "schema": "app-runtime-config-activation-receipt",
            "schemaVersion": "1",
            "status": "activated",
            "requestDigest": request_digest,
            "environment": request["environment"],
            "buildProfile": request["buildProfile"],
            "target": request["target"],
            "packageDigest": request["packageDigest"],
            "trustEnvelopeDigest": request["trustEnvelopeDigest"],
            "effectiveLaunchManifestDigest": request[
                "effectiveLaunchManifestDigest"
            ],
            "previousActiveDigest": request["expectedActiveDigest"],
            "activePackageDigest": request["packageDigest"],
            "errorCode": "",
            "validationIssues": [],
        }
        encoded = executor.canonical_json_bytes(receipt)
        self.files[executor.RECEIPT_FILE_NAME] = encoded
        self.files[executor.ACTIVE_RECEIPT_FILE_NAME] = encoded

    def launch_application(self) -> None:
        self.events.append("launch-application")

    def attach(
        self,
        attach_arguments: tuple[str, ...],
        *,
        timeout_seconds: float,
        on_attached: object,
    ) -> int:
        del attach_arguments, timeout_seconds
        self.events.append("attach")
        on_attached()
        return 0


class CanonicalLaunchExecutorContractTest(
    CanonicalLaunchPlatformContractMixin,
    unittest.TestCase,
):
    def _handoff(self) -> tuple[dict[str, object], dict[str, object]]:
        with shared_nonprod_launcher_authority():
            return build_test_handoff_fixture(
                handoff_builder,
                "alpha",
                "alpha-local",
                launch_mode="canonical_launcher",
            )

    def _active_receipt(
        self,
        handoff: dict[str, object],
        *,
        package_digest: str | None = None,
    ) -> bytes:
        active_digest = package_digest or str(handoff["runtimeConfigPackageDigest"])
        return executor.canonical_json_bytes(
            {
                "schema": "app-runtime-config-activation-receipt",
                "schemaVersion": "1",
                "status": "activated",
                "requestDigest": "sha256:" + "1" * 64,
                "environment": "alpha",
                "buildProfile": "nonprod",
                "target": "alpha-local",
                "packageDigest": active_digest,
                "trustEnvelopeDigest": handoff[
                    "runtimeConfigTrustEnvelopeDigest"
                ],
                "effectiveLaunchManifestDigest": handoff[
                    "effectiveLaunchManifestDigest"
                ],
                "previousActiveDigest": "",
                "activePackageDigest": active_digest,
                "errorCode": "",
                "validationIssues": [],
            }
        )

    def test_first_install_uses_empty_cas_and_advances_only_after_bound_receipt(
        self,
    ) -> None:
        handoff, _ = self._handoff()
        driver = _FakePlatformDriver()
        phases: list[str] = []
        launch = executor.CanonicalLaunchExecutor(
            handoff=handoff,
            platform_driver=driver,
            inherited_environment={"PATH": os.environ.get("PATH", "")},
            attach_arguments=(),
            activation_timeout_seconds=1.0,
            attach_timeout_seconds=1.0,
            emit=phases.append,
        )

        self.assertEqual(launch.execute(), 0)
        assert driver.request is not None
        self.assertEqual(driver.request["expectedActiveDigest"], "")
        self.assertEqual(
            phases,
            [
                "QWQ_APP_LAUNCH_PHASE status=compiled",
                "QWQ_APP_LAUNCH_PHASE status=installing",
                "QWQ_APP_LAUNCH_PHASE status=installed",
                "QWQ_APP_LAUNCH_PHASE status=configuring",
                "QWQ_APP_LAUNCH_PHASE status=configured",
                "QWQ_APP_LAUNCH_PHASE status=launching",
                "QWQ_APP_LAUNCH_PHASE status=launched",
            ],
        )
        self.assertLess(
            driver.events.index("write-request"),
            driver.events.index("launch-activation"),
        )
        self.assertLess(
            driver.events.index("launch-activation"),
            driver.events.index("launch-application"),
        )
        receipt = json.loads(driver.files[executor.RECEIPT_FILE_NAME])
        self.assertEqual(
            receipt["requestDigest"],
            runtime_config_activation_request_digest(driver.request),
        )

    def test_existing_active_receipt_supplies_cas_without_launcher_guessing(self) -> None:
        handoff, _ = self._handoff()
        active_receipt = self._active_receipt(handoff)
        driver = _FakePlatformDriver(active_receipt=active_receipt)
        launch = executor.CanonicalLaunchExecutor(
            handoff=handoff,
            platform_driver=driver,
            inherited_environment={},
            attach_arguments=(),
            activation_timeout_seconds=1.0,
            attach_timeout_seconds=1.0,
            emit=lambda _: None,
        )

        self.assertEqual(launch.execute(), 0)
        assert driver.request is not None
        self.assertEqual(
            driver.request["expectedActiveDigest"],
            handoff["runtimeConfigPackageDigest"],
        )

    def test_malformed_active_receipt_blocks_before_request_write(self) -> None:
        handoff, _ = self._handoff()
        driver = _FakePlatformDriver(active_receipt=b'{"schema":"wrong"}')
        launch = executor.CanonicalLaunchExecutor(
            handoff=handoff,
            platform_driver=driver,
            inherited_environment={},
            attach_arguments=(),
            activation_timeout_seconds=1.0,
            attach_timeout_seconds=1.0,
            emit=lambda _: None,
        )

        with self.assertRaisesRegex(
            executor.CanonicalExecutorError,
            "active activation receipt",
        ):
            launch.execute()
        self.assertNotIn("write-request", driver.events)
        self.assertNotIn("launch-activation", driver.events)

    def test_active_receipt_read_failure_blocks_before_request_write(self) -> None:
        handoff, _ = self._handoff()
        driver = _FakePlatformDriver()
        phases: list[str] = []
        with mock.patch.object(
            driver,
            "read_runtime_file",
            side_effect=executor.CanonicalExecutorError("private active receipt read failed"),
        ):
            launch = executor.CanonicalLaunchExecutor(
                handoff=handoff,
                platform_driver=driver,
                inherited_environment={},
                attach_arguments=(),
                activation_timeout_seconds=1.0,
                attach_timeout_seconds=1.0,
                emit=phases.append,
            )
            with self.assertRaisesRegex(
                executor.CanonicalExecutorError,
                "private active receipt read failed",
            ):
                launch.execute()

        self.assertEqual(phases[-1], "QWQ_APP_LAUNCH_PHASE status=configuring")
        self.assertNotIn("write-request", driver.events)
        self.assertNotIn("launch-activation", driver.events)
        self.assertNotIn("launch-application", driver.events)

    def test_failed_activation_receipt_never_advances_to_configured(self) -> None:
        handoff, _ = self._handoff()
        driver = _FakePlatformDriver()
        phases: list[str] = []

        def fail_activation(request_digest: str) -> None:
            assert driver.request is not None
            request = driver.request
            driver.events.append("launch-activation")
            driver.files[executor.RECEIPT_FILE_NAME] = executor.canonical_json_bytes(
                {
                    "schema": "app-runtime-config-activation-receipt",
                    "schemaVersion": "1",
                    "status": "failed",
                    "requestDigest": request_digest,
                    "environment": request["environment"],
                    "buildProfile": request["buildProfile"],
                    "target": request["target"],
                    "packageDigest": request["packageDigest"],
                    "trustEnvelopeDigest": request["trustEnvelopeDigest"],
                    "effectiveLaunchManifestDigest": request[
                        "effectiveLaunchManifestDigest"
                    ],
                    "previousActiveDigest": request["expectedActiveDigest"],
                    "activePackageDigest": request["expectedActiveDigest"],
                    "errorCode": "runtime_config_active_digest_conflict",
                    "validationIssues": ["runtime_config_active_digest_conflict"],
                }
            )

        driver.launch_activation = fail_activation
        launch = executor.CanonicalLaunchExecutor(
            handoff=handoff,
            platform_driver=driver,
            inherited_environment={},
            attach_arguments=(),
            activation_timeout_seconds=1.0,
            attach_timeout_seconds=1.0,
            emit=phases.append,
        )
        with self.assertRaisesRegex(
            executor.CanonicalExecutorError,
            "runtime_config_active_digest_conflict",
        ):
            launch.execute()

        self.assertNotIn("QWQ_APP_LAUNCH_PHASE status=configured", phases)
        self.assertNotIn("launch-application", driver.events)

    def test_stale_activation_receipt_times_out_without_launching_application(self) -> None:
        handoff, _ = self._handoff()
        driver = _FakePlatformDriver()
        phases: list[str] = []
        original_launch_activation = driver.launch_activation

        def write_stale_receipt(request_digest: str) -> None:
            original_launch_activation(request_digest)
            stale = json.loads(driver.files[executor.RECEIPT_FILE_NAME])
            stale["requestDigest"] = "sha256:" + "9" * 64
            driver.files[executor.RECEIPT_FILE_NAME] = executor.canonical_json_bytes(stale)

        driver.launch_activation = write_stale_receipt
        launch = executor.CanonicalLaunchExecutor(
            handoff=handoff,
            platform_driver=driver,
            inherited_environment={},
            attach_arguments=(),
            activation_timeout_seconds=1.0,
            attach_timeout_seconds=1.0,
            emit=phases.append,
        )
        with mock.patch.object(
            activation.time,
            "monotonic",
            side_effect=(0.0, 0.1, 2.0),
        ), mock.patch.object(activation.time, "sleep"):
            with self.assertRaisesRegex(
                executor.CanonicalExecutorError,
                "not bound to the current request",
            ):
                launch.execute()

        self.assertNotIn("QWQ_APP_LAUNCH_PHASE status=configured", phases)
        self.assertNotIn("launch-application", driver.events)

    def test_missing_active_readback_after_activation_blocks_configured(self) -> None:
        handoff, _ = self._handoff()
        driver = _FakePlatformDriver()
        phases: list[str] = []
        original_launch_activation = driver.launch_activation

        def omit_active_readback(request_digest: str) -> None:
            original_launch_activation(request_digest)
            driver.files.pop(executor.ACTIVE_RECEIPT_FILE_NAME)

        driver.launch_activation = omit_active_readback
        launch = executor.CanonicalLaunchExecutor(
            handoff=handoff,
            platform_driver=driver,
            inherited_environment={},
            attach_arguments=(),
            activation_timeout_seconds=1.0,
            attach_timeout_seconds=1.0,
            emit=phases.append,
        )
        with self.assertRaisesRegex(
            executor.CanonicalExecutorError,
            "committed no active activation receipt",
        ):
            launch.execute()

        self.assertNotIn("QWQ_APP_LAUNCH_PHASE status=configured", phases)
        self.assertNotIn("launch-application", driver.events)

    def test_compile_environment_removes_runtime_package_and_target_identity(self) -> None:
        environment = executor.compile_environment(
            {
                "PATH": "/usr/bin",
                "QWQ_LAUNCH_HANDOFF_JSON": '{"runtimeConfigPackage":{}}',
                "QWQ_RUNTIME_CONFIG_PACKAGE_JSON": '{"schema":"app-runtime-config-package"}',
                "QWQ_APP_RUNTIME_ENV": "alpha",
                "QWQ_LAUNCH_TARGET": "alpha-local",
                "QWQ_RUNTIME_CONFIG_PACKAGE_DIGEST": "sha256:" + "a" * 64,
                "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST": "sha256:" + "b" * 64,
                "QWQ_CONTENT_RELEASE_ID": "release-1",
                "ANDROID_LOCAL_GATEWAY_BASE_URL": "http://127.0.0.1:8080",
                "QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT": "/tmp/profile-trust",
                "QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH": "/tmp/profile-trust.json",
                "QWQ_APP_RUNTIME_CONFIG_TRUST_PATH": "/tmp/profile-trust.json",
                "QWQ_APP_RUNTIME_CONFIG_SIGNING_KEY_ID": "nonprod-2026",
                "QWQ_APP_RUNTIME_CONFIG_SIGNING_PRIVATE_KEY_FILE": "/keys/private",
                "QWQ_APP_RUNTIME_CONFIG_TRUSTED_PUBLIC_KEYS_FILE": "/keys/keyring",
                "QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON": '{"legacy":"keyring"}',
                "QWQ_ANDROID_RELEASE_KEYSTORE_PATH": "/keys/release.jks",
                "QWQ_ANDROID_RELEASE_KEYSTORE_B64": "a2V5c3RvcmU=",
                "QWQ_ANDROID_RELEASE_STORE_PASSWORD": "store-secret",
                "QWQ_ANDROID_RELEASE_KEY_ALIAS": "release",
                "QWQ_ANDROID_RELEASE_KEY_PASSWORD": "key-secret",
                "QWQ_APP_BUILD_PROFILE": "nonprod",
            }
        )

        self.assertEqual(environment["PATH"], "/usr/bin")
        self.assertEqual(environment["QWQ_APP_BUILD_PROFILE"], "nonprod")
        self.assertIn("QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT", environment)
        self.assertIn("QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH", environment)
        self.assertNotIn("QWQ_APP_RUNTIME_CONFIG_TRUST_PATH", environment)
        self.assertNotIn("QWQ_APP_RUNTIME_CONFIG_SIGNING_KEY_ID", environment)
        self.assertNotIn("QWQ_APP_RUNTIME_CONFIG_SIGNING_PRIVATE_KEY_FILE", environment)
        self.assertNotIn("QWQ_APP_RUNTIME_CONFIG_TRUSTED_PUBLIC_KEYS_FILE", environment)
        self.assertNotIn("QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON", environment)
        self.assertFalse(
            any(key.startswith("QWQ_ANDROID_RELEASE_") for key in environment)
        )
        self.assertNotIn("QWQ_LAUNCH_HANDOFF_JSON", environment)
        self.assertNotIn("QWQ_RUNTIME_CONFIG_PACKAGE_JSON", environment)
        self.assertNotIn("QWQ_APP_RUNTIME_ENV", environment)
        self.assertNotIn("QWQ_LAUNCH_TARGET", environment)
        self.assertNotIn("QWQ_CONTENT_RELEASE_ID", environment)
        self.assertNotIn("ANDROID_LOCAL_GATEWAY_BASE_URL", environment)

    def test_flutter_attach_started_event_is_only_launch_milestone(self) -> None:
        self.assertTrue(
            executor._is_flutter_app_started_event(
                '[{"event":"app.started","params":{"appId":"daemon-app-1"}}]'
            )
        )
        for line in (
            '[{"event":"daemon.connected","params":{"pid":123}}]',
            '[{"event":"app.start","params":{"appId":"daemon-app-1"}}]',
            '[{"event":"app.started","params":{}}]',
            '[{"event":"app.started"}]',
            '{"event":"app.started","params":{"appId":"daemon-app-1"}}',
            "not-json",
        ):
            with self.subTest(line=line):
                self.assertFalse(executor._is_flutter_app_started_event(line))

        source = (APP_DIR / "scripts/device/run_app_instance.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"--machine"', source)
        self.assertIn('"--host-vmservice-port=0"', source)
        self.assertIn('"--dds-port=0"', source)
        self.assertNotIn('"--host-vmservice-port=8888"', source)
        self.assertNotIn('"--dds-port=8889"', source)
        self.assertNotIn("flutter-attach.pid", source)
        self.assertNotIn("pid_file.is_file()", source)

        launcher_source = (APP_DIR / "run.sh").read_text(encoding="utf-8")
        self.assertNotIn("tcp:8888", launcher_source)
        self.assertNotIn("QWQ_ANDROID_VM_FORWARD_PREEXISTING", launcher_source)

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
                "canonical executor owns Flutter attach argument",
            ),
            (
                ["-d", "device-a", "--debug-uri=http://127.0.0.1:9999/token/"],
                {},
                "canonical executor owns Flutter attach argument",
            ),
            (
                ["-d", "device-a", "--vm-service-port=4567"],
                {},
                "canonical executor owns Flutter attach argument",
            ),
            (
                ["-d", "device-a", "--device-timeout", "5"],
                {},
                "canonical executor owns Flutter attach argument",
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

    def test_attach_executes_dynamic_machine_command_with_clean_environment(self) -> None:
        process = _AttachProcess(
            '[{"event":"app.started","params":{"appId":"daemon-app-1"}}]\n'
        )
        driver = executor.AndroidPlatformDriver(
            device_id="device-1",
            application_id="com.leadwise.quwoquan.nonprod.debug",
            entrypoint="lib/main_prod.dart",
        )
        on_attached = mock.Mock()
        with mock.patch.dict(
            os.environ,
            {
                "QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON": '{"legacy":"keyring"}',
                "QWQ_ANDROID_RELEASE_STORE_PASSWORD": "secret",
            },
            clear=False,
        ), mock.patch.object(
            executor.subprocess, "Popen", return_value=process
        ) as popen, mock.patch.object(
            executor.threading, "Thread", _ImmediateThread
        ):
            self.assertEqual(
                driver.attach(
                    ("--verbose",),
                    timeout_seconds=1.0,
                    on_attached=on_attached,
                ),
                0,
            )

        self.assertEqual(
            popen.call_args.args[0],
            [
                "flutter",
                "attach",
                "--machine",
                "-d",
                "device-1",
                "--app-id",
                "com.leadwise.quwoquan.nonprod.debug",
                "--target",
                "lib/main_prod.dart",
                "--host-vmservice-port=0",
                "--dds-port=0",
                "--verbose",
            ],
        )
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        child_environment = popen.call_args.kwargs["env"]
        self.assertNotIn("QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON", child_environment)
        self.assertNotIn("QWQ_ANDROID_RELEASE_STORE_PASSWORD", child_environment)
        on_attached.assert_called_once_with()

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

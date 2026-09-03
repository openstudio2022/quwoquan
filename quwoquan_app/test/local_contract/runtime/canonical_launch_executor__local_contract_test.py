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
            "launchProvenance": request["effectiveLaunchManifest"][
                "launchProvenance"
            ],
            "runtimeConfigSupplyMode": request["effectiveLaunchManifest"][
                "runtimeConfigSupplyMode"
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
    def test_platform_drivers_execute_canonical_install_and_launch_commands(
        self,
    ) -> None:
        with mock.patch.dict(
            os.environ,
            {"QWQ_REAL_FLUTTER": "flutter"},
            clear=False,
        ):
            super().test_platform_drivers_execute_canonical_install_and_launch_commands()

    def test_private_runtime_file_allowlist_is_exact(self) -> None:
        for file_name in (
            executor.REQUEST_FILE_NAME,
            executor.RECEIPT_FILE_NAME,
            executor.ACTIVE_RECEIPT_FILE_NAME,
            executor.ACTIVE_PACKAGE_FILE_NAME,
        ):
            with self.subTest(file_name=file_name):
                executor._validate_runtime_file_name(file_name)

        with self.assertRaisesRegex(
            executor.CanonicalExecutorError,
            "unsupported private runtime file",
        ):
            executor._validate_runtime_file_name("../runtime-config-package.json")

    def _handoff(self) -> tuple[dict[str, object], dict[str, object]]:
        with shared_nonprod_launcher_authority():
            return build_test_handoff_fixture(
                handoff_builder,
                "alpha",
                "alpha-local",
                launch_provenance="canonical_launcher",
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
                "launchProvenance": handoff["launchProvenance"],
                "runtimeConfigSupplyMode": handoff[
                    "runtimeConfigSupplyMode"
                ],
                "previousActiveDigest": "",
                "activePackageDigest": active_digest,
                "errorCode": "",
                "validationIssues": [],
            }
        )

    def _predecessor_active_receipt(
        self,
        handoff: dict[str, object],
    ) -> bytes:
        receipt = json.loads(self._active_receipt(handoff))
        receipt.pop("launchProvenance")
        receipt.pop("runtimeConfigSupplyMode")
        return executor.canonical_json_bytes(receipt)

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

    def test_predecessor_active_receipt_blocks_before_request_write(self) -> None:
        handoff, _ = self._handoff()
        driver = _FakePlatformDriver(
            active_receipt=self._predecessor_active_receipt(handoff),
        )
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
            "active activation receipt fields are invalid",
        ):
            launch.execute()
        self.assertNotIn("write-request", driver.events)
        self.assertNotIn(
            f"read:{executor.ACTIVE_PACKAGE_FILE_NAME}",
            driver.events,
        )

    def test_predecessor_launch_receipt_blocks_instead_of_waiting(self) -> None:
        handoff, _ = self._handoff()
        driver = _FakePlatformDriver()
        stale_receipt = self._predecessor_active_receipt(handoff)
        original_launch_activation = driver.launch_activation
        original_read_runtime_file = driver.read_runtime_file
        activation_started = False
        stale_returned = False

        def launch_activation(request_digest: str) -> None:
            nonlocal activation_started
            original_launch_activation(request_digest)
            activation_started = True

        def read_runtime_file(file_name: str) -> bytes | None:
            nonlocal stale_returned
            if (
                activation_started
                and not stale_returned
                and file_name == executor.RECEIPT_FILE_NAME
            ):
                stale_returned = True
                return stale_receipt
            return original_read_runtime_file(file_name)

        driver.launch_activation = launch_activation
        driver.read_runtime_file = read_runtime_file
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
            "activation receipt fields are invalid",
        ):
            launch.execute()
        self.assertTrue(stale_returned)

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
                    "launchProvenance": request["effectiveLaunchManifest"][
                        "launchProvenance"
                    ],
                    "runtimeConfigSupplyMode": request["effectiveLaunchManifest"][
                        "runtimeConfigSupplyMode"
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
                "FLUTTER_STORAGE_BASE_URL": "https://ambient-flutter.invalid",
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
        self.assertNotIn("FLUTTER_STORAGE_BASE_URL", environment)

    def test_ios_child_environment_requires_exact_cocoapods_identity(self) -> None:
        driver = executor.IOSSimulatorPlatformDriver(
            device_id="simulator-1",
            application_id="com.leadwise.quwoquan.nonprod.debug",
            entrypoint="lib/main_prod.dart",
        )
        exact_environment = {"PATH": "/exact/bin"}
        ambient_build_settings = {
            key: f"/stale/projection/{key.lower()}"
            for key in executor.XCODE_BUILD_ISOLATION_ENVIRONMENT_KEYS
        }
        with mock.patch.object(
            activation,
            "validate_cocoapods_child_environment",
            return_value=(mock.sentinel.identity, exact_environment.copy()),
        ) as validate:
            child = driver.child_environment(
                {
                    "PATH": "/hostile/bin",
                    **ambient_build_settings,
                    "QWQ_APP_RUNTIME_ENV": "hostile",
                }
            )

        self.assertEqual(child, {"PATH": "/exact/bin"})
        validate.assert_called_once()
        validated_input = validate.call_args.args[0]
        self.assertEqual(validated_input["PATH"], "/hostile/bin")
        self.assertTrue(
            executor.XCODE_BUILD_ISOLATION_ENVIRONMENT_KEYS.isdisjoint(
                validated_input
            )
        )
        self.assertNotIn("QWQ_APP_RUNTIME_ENV", validated_input)

    def test_ios_builds_use_projection_private_xcode_build_settings(self) -> None:
        projection_root = Path(tempfile.gettempdir()).resolve() / "qwq-projections"
        projected_app_dirs = (
            projection_root / "projection-a/quwoquan_app",
            projection_root / "projection-b/quwoquan_app",
        )
        driver_contracts = (
            (
                executor.IOSSimulatorPlatformDriver,
                "build/ios/iphonesimulator/Runner.app",
            ),
            (
                executor.IOSPhysicalPlatformDriver,
                "build/ios/iphoneos/Runner.app",
            ),
        )
        observed_setting_sets: set[tuple[str, ...]] = set()

        for projected_app_dir in projected_app_dirs:
            for driver_type, artifact_relative_path in driver_contracts:
                with self.subTest(
                    projection=projected_app_dir,
                    driver=driver_type.__name__,
                ):
                    driver = driver_type(
                        device_id="ios-device-1",
                        application_id="com.leadwise.quwoquan.nonprod.debug",
                        entrypoint="lib/main_prod.dart",
                    )
                    ambient_build_settings = {
                        key: f"/stale/projection/{key.lower()}"
                        for key in (
                            executor.XCODE_BUILD_ISOLATION_ENVIRONMENT_KEYS
                        )
                    }

                    def validate_cocoapods(environment):
                        self.assertTrue(
                            executor.XCODE_BUILD_ISOLATION_ENVIRONMENT_KEYS.isdisjoint(
                                environment
                            )
                        )
                        return mock.sentinel.identity, dict(environment)

                    with mock.patch.object(
                        executor,
                        "APP_DIR",
                        projected_app_dir,
                    ), mock.patch.object(
                        activation,
                        "validate_cocoapods_child_environment",
                        side_effect=validate_cocoapods,
                    ) as validate, mock.patch.object(
                        executor,
                        "_run_checked",
                    ) as run_checked, mock.patch.object(
                        Path,
                        "exists",
                        return_value=True,
                    ):
                        driver.build(
                            {
                                "PATH": "/canonical/bin",
                                "CP_HOME_DIR": "/canonical/cocoapods",
                                **ambient_build_settings,
                                "QWQ_APP_RUNTIME_ENV": "hostile",
                                "QWQ_ANDROID_RELEASE_STORE_PASSWORD": "secret",
                            }
                        )
                        self.assertEqual(
                            driver.artifact_path(),
                            projected_app_dir / artifact_relative_path,
                        )

                    validate.assert_called_once()
                    child = run_checked.call_args.kwargs["environment"]
                    expected_build_settings = {
                        key: str(projected_app_dir / relative_path)
                        for key, relative_path in (
                            executor.IOS_XCODE_BUILD_ISOLATION_RELATIVE_PATHS.items()
                        )
                    }
                    actual_build_settings = {
                        key: value
                        for key, value in child.items()
                        if key.startswith("FLUTTER_XCODE_")
                    }
                    self.assertEqual(
                        actual_build_settings, expected_build_settings
                    )
                    self.assertEqual(
                        set(actual_build_settings),
                        {
                            "FLUTTER_XCODE_OBJROOT",
                            "FLUTTER_XCODE_MODULE_CACHE_DIR",
                            "FLUTTER_XCODE_SHARED_PRECOMPS_DIR",
                        },
                    )
                    self.assertEqual(
                        len(set(actual_build_settings.values())),
                        len(actual_build_settings),
                    )
                    self.assertEqual(child["PATH"], "/canonical/bin")
                    self.assertEqual(
                        child["CP_HOME_DIR"], "/canonical/cocoapods"
                    )
                    self.assertNotIn("QWQ_APP_RUNTIME_ENV", child)
                    self.assertFalse(
                        any(
                            key.startswith("QWQ_ANDROID_RELEASE_")
                            for key in child
                        )
                    )
                    observed_setting_sets.add(
                        tuple(sorted(actual_build_settings.values()))
                    )

        self.assertEqual(len(observed_setting_sets), len(projected_app_dirs))

    def test_android_build_does_not_receive_xcode_isolation_settings(self) -> None:
        driver = executor.AndroidPlatformDriver(
            device_id="android-device-1",
            application_id="com.leadwise.quwoquan.nonprod.debug",
            entrypoint="lib/main_prod.dart",
        )
        ambient_build_settings = {
            key: f"/stale/projection/{key.lower()}"
            for key in executor.XCODE_BUILD_ISOLATION_ENVIRONMENT_KEYS
        }
        with mock.patch.object(
            activation,
            "validate_cocoapods_child_environment",
        ) as validate, mock.patch.object(
            executor,
            "_run_checked",
        ) as run_checked, mock.patch.object(
            Path,
            "exists",
            return_value=True,
        ):
            driver.build(
                {
                    "PATH": "/canonical/bin",
                    **ambient_build_settings,
                    "QWQ_APP_RUNTIME_ENV": "hostile",
                }
            )

        validate.assert_not_called()
        child = run_checked.call_args.kwargs["environment"]
        self.assertEqual(child, {"PATH": "/canonical/bin"})
        self.assertEqual(
            driver.artifact_path(),
            executor.APP_DIR
            / "build/app/outputs/flutter-apk/app-nonprod-debug.apk",
        )

    def test_ios_build_only_settings_do_not_enter_attach_environment(self) -> None:
        driver = executor.IOSSimulatorPlatformDriver(
            device_id="simulator-1",
            application_id="com.leadwise.quwoquan.nonprod.debug",
            entrypoint="lib/main_prod.dart",
        )
        process = _AttachProcess(
            '[{"event":"app.started","params":{"appId":"daemon-app-1"}}]\n'
        )
        ambient_build_settings = {
            key: f"/stale/projection/{key.lower()}"
            for key in executor.XCODE_BUILD_ISOLATION_ENVIRONMENT_KEYS
        }

        def validate_cocoapods(environment):
            self.assertTrue(
                executor.XCODE_BUILD_ISOLATION_ENVIRONMENT_KEYS.isdisjoint(
                    environment
                )
            )
            return mock.sentinel.identity, dict(environment)

        with mock.patch.dict(
            os.environ,
            {
                "PATH": "/exact/attach/bin",
                "PHASE": "attach",
                **ambient_build_settings,
            },
            clear=True,
        ), mock.patch.object(
            activation,
            "validate_cocoapods_child_environment",
            side_effect=validate_cocoapods,
        ) as validate, mock.patch.object(
            executor,
            "_run_checked",
        ) as run_checked, mock.patch.object(
            driver,
            "artifact_path",
        ) as artifact_path, mock.patch.object(
            executor.subprocess,
            "Popen",
            return_value=process,
        ) as popen, mock.patch.object(
            executor.threading,
            "Thread",
            _ImmediateThread,
        ), mock.patch.object(
            driver,
            "resolve_attach_debug_url",
            return_value="http://127.0.0.1:1234/token/",
        ), mock.patch.object(
            driver,
            "startup_evidence_lines",
            return_value=(),
        ):
            artifact_path.return_value.exists.return_value = True
            driver.build(
                {
                    "PATH": "/exact/build/bin",
                    "PHASE": "build",
                    **ambient_build_settings,
                }
            )
            self.assertEqual(
                driver.attach((), timeout_seconds=10.0, on_attached=lambda: None),
                0,
            )

        self.assertEqual(validate.call_count, 2)
        build_child = run_checked.call_args.kwargs["environment"]
        expected_build_settings = {
            key: str(executor.APP_DIR / relative_path)
            for key, relative_path in (
                executor.IOS_XCODE_BUILD_ISOLATION_RELATIVE_PATHS.items()
            )
        }
        self.assertEqual(
            {
                key: value
                for key, value in build_child.items()
                if key.startswith("FLUTTER_XCODE_")
            },
            expected_build_settings,
        )
        self.assertEqual(build_child["PHASE"], "build")
        attach_child = popen.call_args.kwargs["env"]
        self.assertEqual(
            attach_child,
            {"PATH": "/exact/attach/bin", "PHASE": "attach"},
        )
        self.assertTrue(
            executor.XCODE_BUILD_ISOLATION_ENVIRONMENT_KEYS.isdisjoint(
                attach_child
            )
        )


if __name__ == "__main__":
    unittest.main()

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#open-007
"""Patrol UAT 宿主 runtime config activation 编排的判否与证据契约。

宿主没拿到 runtime config 时不存在「继续跑但结论可信」的中间态：一旦任何一步
降级为跳过，UAT 就会在没有 runtime config 的宿主上跑出一份通过态回执，而那份
回执正是 `content_live_passed` 的输入。本文件锚定四件事：

1. 每一步失败都收敛为 `PatrolHostActivationError`，不返回、不吞、不降级；
2. Android 走专用 activation 组件冷启动，iOS 不传组件（由 AppDelegate 消费请求）；
3. 通过态写入 active package digest 与 request digest，缺一不可；
4. 判否把设备级 run 落成 gate_block，而不是让该设备从 runs 里消失。
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "quwoquan_ops").is_dir() and (parent / "quwoquan_app").is_dir()
)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quwoquan_ops.cli.lib.flutter_android_device_proxy import REAL_FLUTTER_ENV
from quwoquan_ops.cli.lib.package_reuse import (
    patrol_command_envelope as envelope_contract,
)
from quwoquan_ops.cli.smoke.environment_patrol_smoke import host_activation
from quwoquan_ops.cli.smoke.environment_patrol_smoke.constants import (
    PATROL_ANDROID_ACTIVATION_COMPONENT,
    PATROL_ANDROID_PACKAGE,
    PATROL_IOS_BUNDLE_ID,
)

PACKAGE_DIGEST = "sha256:" + "a" * 64
TRUST_DIGEST = "sha256:" + "b" * 64
MANIFEST_DIGEST = "sha256:" + "c" * 64
REQUEST_DIGEST = "sha256:" + "d" * 64
COMPILE_BLOCKER = "APP.LAUNCH.compile_failed"
INSTALL_BLOCKER = "APP.LAUNCH.install_failed"
ACTIVATION_BLOCKER = "APP.LAUNCH.runtime_config_activation_failed"
HANDOFF: dict[str, Any] = {
    "schema": "app-launcher-handoff",
    "environment": "gamma",
    "buildProfile": "nonprod",
    "target": "gamma-local",
    "runtimeConfigPackageDigest": PACKAGE_DIGEST,
    "runtimeConfigTrustEnvelopeDigest": TRUST_DIGEST,
    "effectiveLaunchManifestDigest": MANIFEST_DIGEST,
}

ANDROID_DEVICE: dict[str, Any] = {
    "id": "emulator-5554",
    "targetPlatform": "android-x64",
    "emulator": True,
}
IOS_DEVICE: dict[str, Any] = {
    "id": "SIMULATOR-UDID",
    "targetPlatform": "ios",
    "emulator": True,
}


def _activation_receipt(**updates: Any) -> dict[str, Any]:
    receipt = {
        "schema": "app-runtime-config-activation-receipt",
        "status": "activated",
        "environment": HANDOFF["environment"],
        "buildProfile": HANDOFF["buildProfile"],
        "target": HANDOFF["target"],
        "packageDigest": PACKAGE_DIGEST,
        "trustEnvelopeDigest": TRUST_DIGEST,
        "effectiveLaunchManifestDigest": MANIFEST_DIGEST,
        "activePackageDigest": PACKAGE_DIGEST,
        "requestDigest": REQUEST_DIGEST,
    }
    receipt.update(updates)
    return receipt


class _Recorder:
    """记录编排实际发出的命令与 driver 构造参数。"""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.command_kwargs: list[dict[str, Any]] = []
        self.driver_kwargs: dict[str, Any] = {}
        self.activation_kwargs: dict[str, Any] = {}


def _install_doubles(
    testcase: unittest.TestCase,
    recorder: _Recorder,
    *,
    command_exit_code: int = 0,
    command_exit_codes: tuple[int, ...] | None = None,
    artifact_exists: bool = True,
    activation_result: dict[str, Any] | None = None,
    activation_error: Exception | None = None,
) -> None:
    """把编排的四个外部边界替换为 typed double：构建、安装、driver、激活。"""

    def fake_run_command(command, **kwargs):
        recorder.commands.append(list(command))
        recorder.command_kwargs.append(dict(kwargs))
        index = len(recorder.commands) - 1
        exit_code = (
            command_exit_codes[min(index, len(command_exit_codes) - 1)]
            if command_exit_codes
            else command_exit_code
        )
        return {"exitCode": exit_code}

    class _FakeArtifact:
        def __init__(self, path: Path) -> None:
            self._path = path

        def exists(self) -> bool:
            return artifact_exists

        def __str__(self) -> str:  # 判否消息里要能看到具体产物路径
            return str(self._path)

        def __truediv__(self, other: str) -> _FakeArtifact:
            return _FakeArtifact(self._path / other)

    real_artifact = host_activation._host_artifact

    def fake_host_artifact(device):
        return _FakeArtifact(real_artifact(device))

    def fake_build_platform_driver(**kwargs):
        recorder.driver_kwargs = dict(kwargs)
        return object()

    def fake_activate_runtime_config(**kwargs):
        recorder.activation_kwargs = dict(kwargs)
        if activation_error is not None:
            raise activation_error
        return activation_result or {}

    class _FakeModule:
        def __init__(self, **attributes: Any) -> None:
            for name, value in attributes.items():
                setattr(self, name, value)

    modules = {
        "canonical_app_instance.activation": _FakeModule(
            activate_runtime_config=fake_activate_runtime_config
        ),
        "run_app_instance": _FakeModule(
            build_platform_driver=fake_build_platform_driver
        ),
    }

    for name, replacement in (
        ("run_command", fake_run_command),
        ("_host_artifact", fake_host_artifact),
        ("_canonical_device_module", lambda name: modules[name]),
    ):
        original = getattr(host_activation, name)
        setattr(host_activation, name, replacement)
        testcase.addCleanup(setattr, host_activation, name, original)


class PatrolHostActivationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.recorder = _Recorder()
        self.log_root = Path(tempfile.mkdtemp(prefix="qwq-host-activation-")).resolve()
        self.flutter = self.log_root / "flutter"
        self.flutter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.flutter.chmod(0o700)
        self.adb = self.log_root / "adb"
        self.adb.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.adb.chmod(0o700)
        self.flutter_identity = {
            "executable": str(self.flutter),
            "flutterVersion": "3.47.0",
            "commandResolutionDigest": "sha256:" + "f" * 64,
        }
        envelope = envelope_contract.patrol_command_envelope(
            flutter_identity=self.flutter_identity,
            path=str(self.log_root),
        )
        identity_patch = mock.patch.object(
            envelope_contract,
            "resolved_flutter_identity",
            return_value=dict(self.flutter_identity),
        )
        identity_patch.start()
        self.addCleanup(identity_patch.stop)
        self.command_env = envelope_contract.rebuild_patrol_command_environment(
            envelope=envelope,
            ambient_environment={},
            dependency_environment={},
            command_environment={},
        )
        adb_patch = mock.patch.object(
            host_activation,
            "resolve_android_debug_bridge",
            return_value=str(self.adb),
        )
        self.resolve_adb = adb_patch.start()
        self.addCleanup(adb_patch.stop)
        self.args = argparse.Namespace()

    def test_error_code_set_is_canonical_and_closed(self) -> None:
        self.assertEqual(
            host_activation._ACTIVATION_ERROR_CODES,
            frozenset({COMPILE_BLOCKER, INSTALL_BLOCKER, ACTIVATION_BLOCKER}),
        )
        for code in (COMPILE_BLOCKER, INSTALL_BLOCKER, ACTIVATION_BLOCKER):
            with self.subTest(code=code):
                self.assertEqual(
                    host_activation.PatrolHostActivationError(code).code,
                    code,
                )
        with self.assertRaisesRegex(ValueError, "error code is invalid"):
            host_activation.PatrolHostActivationError("compile")

    def _activate(
        self,
        device: dict[str, Any],
        *,
        command_env: dict[str, str] | None = None,
        handoff: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return host_activation.activate_patrol_host_runtime_config(
            self.args,
            device,
            handoff or HANDOFF,
            self.command_env if command_env is None else command_env,
            self.log_root,
        )

    def test_android_activates_through_the_dedicated_component(self) -> None:
        _install_doubles(
            self,
            self.recorder,
            activation_result=_activation_receipt(),
        )

        receipt = self._activate(ANDROID_DEVICE)

        self.assertEqual(receipt["activePackageDigest"], PACKAGE_DIGEST)
        # 宿主必须先装到设备上，激活请求才能落进设备私有目录。
        self.assertEqual(
            [command[:3] for command in self.recorder.commands],
            [
                [str(self.flutter), "build", "apk"],
                [str(self.adb), "-s", "emulator-5554"],
            ],
        )
        self.assertEqual(
            self.recorder.commands[0],
            [str(self.flutter), "build", "apk", "--debug", "--no-pub"],
        )
        self.assertEqual(
            self.recorder.driver_kwargs["activation_component"],
            PATROL_ANDROID_ACTIVATION_COMPONENT,
        )
        self.assertEqual(
            self.recorder.driver_kwargs["application_id"],
            PATROL_ANDROID_PACKAGE,
        )
        self.assertEqual(
            self.recorder.driver_kwargs["device_kind"],
            "android_emulator",
        )

    def test_android_install_uses_absolute_adb_from_env_without_path_mutation(
        self,
    ) -> None:
        _install_doubles(
            self,
            self.recorder,
            activation_result=_activation_receipt(),
        )
        original_environment = dict(self.command_env)

        self._activate(ANDROID_DEVICE)

        install_command = self.recorder.commands[1]
        self.assertEqual(install_command[0], str(self.adb))
        self.assertTrue(Path(install_command[0]).is_absolute())
        self.assertEqual(self.command_env, original_environment)
        self.assertEqual(
            self.recorder.command_kwargs[1]["env"]["PATH"],
            original_environment["PATH"],
        )
        resolver_environment = self.resolve_adb.call_args.kwargs["environ"]
        self.assertEqual(resolver_environment["PATH"], original_environment["PATH"])

    def test_android_adb_resolution_fails_before_install_command(self) -> None:
        _install_doubles(self, self.recorder)
        self.resolve_adb.return_value = None

        with self.assertRaises(host_activation.PatrolHostActivationError) as caught:
            host_activation._install_host(
                ANDROID_DEVICE,
                self.command_env,
                self.log_root,
            )

        self.assertEqual(caught.exception.code, INSTALL_BLOCKER)
        self.assertEqual(self.recorder.commands, [])

    def test_android_physical_uses_the_physical_driver_kind(self) -> None:
        _install_doubles(
            self,
            self.recorder,
            activation_result=_activation_receipt(),
        )

        self._activate({**ANDROID_DEVICE, "id": "physical-1", "emulator": False})

        self.assertEqual(
            self.recorder.driver_kwargs["device_kind"],
            "android_physical",
        )

    def test_ios_activation_carries_no_component(self) -> None:
        """iOS 由 AppDelegate 在 Flutter 引擎之前消费请求，没有独立激活组件。"""
        _install_doubles(
            self,
            self.recorder,
            activation_result=_activation_receipt(),
        )

        self._activate(IOS_DEVICE)

        self.assertEqual(self.recorder.driver_kwargs["activation_component"], "")
        self.assertEqual(
            self.recorder.driver_kwargs["application_id"],
            PATROL_IOS_BUNDLE_ID,
        )
        self.assertEqual(
            self.recorder.commands[0][:3],
            [str(self.flutter), "build", "ios"],
        )
        self.assertEqual(
            self.recorder.commands[0],
            [
                str(self.flutter),
                "build",
                "ios",
                "--debug",
                "--simulator",
                "--no-codesign",
                "--no-pub",
            ],
        )
        self.assertEqual(self.recorder.commands[1][:2], ["xcrun", "simctl"])

    def test_ios_physical_uses_iphoneos_and_devicectl_actor(self) -> None:
        _install_doubles(
            self,
            self.recorder,
            activation_result=_activation_receipt(),
        )

        self._activate({**IOS_DEVICE, "id": "PHYSICAL-IOS-UDID", "emulator": False})

        self.assertEqual(
            self.recorder.commands[0],
            [str(self.flutter), "build", "ios", "--debug", "--no-pub"],
        )
        self.assertEqual(
            self.recorder.commands[1][:7],
            [
                "xcrun",
                "devicectl",
                "device",
                "install",
                "app",
                "--device",
                "PHYSICAL-IOS-UDID",
            ],
        )
        self.assertIn("build/ios/iphoneos/Runner.app", self.recorder.commands[1][-1])
        self.assertEqual(self.recorder.driver_kwargs["device_kind"], "ios-physical")
        self.assertEqual(self.recorder.driver_kwargs["activation_component"], "")

    def test_build_failure_is_a_gate_block(self) -> None:
        _install_doubles(self, self.recorder, command_exit_code=1)

        with self.assertRaises(host_activation.PatrolHostActivationError) as caught:
            self._activate(ANDROID_DEVICE)

        self.assertEqual(caught.exception.code, COMPILE_BLOCKER)
        # 构建失败即停，不得继续尝试安装或激活。
        self.assertEqual(len(self.recorder.commands), 1)
        self.assertEqual(self.recorder.activation_kwargs, {})

    def test_missing_build_artifact_is_a_gate_block(self) -> None:
        _install_doubles(self, self.recorder, artifact_exists=False)

        with self.assertRaises(host_activation.PatrolHostActivationError) as caught:
            self._activate(ANDROID_DEVICE)

        self.assertEqual(caught.exception.code, COMPILE_BLOCKER)

    def test_missing_device_id_is_a_gate_block(self) -> None:
        _install_doubles(self, self.recorder)

        with self.assertRaises(host_activation.PatrolHostActivationError) as caught:
            self._activate({**ANDROID_DEVICE, "id": "  "})

        self.assertEqual(caught.exception.code, INSTALL_BLOCKER)

    def test_install_failure_has_the_install_code(self) -> None:
        _install_doubles(
            self,
            self.recorder,
            command_exit_codes=(0, 1),
        )

        with self.assertRaises(host_activation.PatrolHostActivationError) as caught:
            self._activate(ANDROID_DEVICE)

        self.assertEqual(caught.exception.code, INSTALL_BLOCKER)

    def test_flutter_must_come_from_the_canonical_absolute_executable_env(self) -> None:
        _install_doubles(self, self.recorder)
        cases = ({}, {REAL_FLUTTER_ENV: "flutter"})

        for command_env in cases:
            with self.subTest(command_env=command_env):
                with self.assertRaises(
                    host_activation.PatrolHostActivationError
                ) as caught:
                    self._activate(ANDROID_DEVICE, command_env=command_env)
                self.assertEqual(caught.exception.code, COMPILE_BLOCKER)
        self.assertEqual(self.recorder.commands, [])

    def test_flutter_rejects_non_regular_non_executable_and_symlink_paths(self) -> None:
        _install_doubles(self, self.recorder)
        directory = self.log_root / "flutter-directory"
        directory.mkdir()
        not_executable = self.log_root / "not-executable-flutter"
        not_executable.write_text("#!/bin/sh\n", encoding="utf-8")
        symlink = self.log_root / "flutter-link"
        symlink.symlink_to(self.flutter)

        for candidate in (directory, not_executable, symlink):
            with self.subTest(candidate=candidate.name):
                with self.assertRaises(
                    host_activation.PatrolHostActivationError
                ) as caught:
                    self._activate(
                        ANDROID_DEVICE,
                        command_env={REAL_FLUTTER_ENV: str(candidate)},
                    )
                self.assertEqual(caught.exception.code, COMPILE_BLOCKER)

    def test_flutter_identity_or_proxy_drift_is_a_compile_gate_block(self) -> None:
        _install_doubles(self, self.recorder)
        cases = (
            {**self.command_env, "QWQ_FLUTTER_VERSION": "3.48.0"},
            {
                **self.command_env,
                "QWQ_COMMAND_RESOLUTION_DIGEST": "sha256:" + "e" * 64,
            },
            {**self.command_env, "PATH": "/foreign/flutter/bin"},
            {
                **self.command_env,
                "QWQ_REAL_FLUTTER": "/foreign/flutter/bin/flutter",
            },
            {**self.command_env, "HTTP_PROXY": "http://explicit.invalid"},
            {**self.command_env, "http_proxy": "http://explicit.invalid"},
        )

        for command_env in cases:
            with self.subTest(command_env=command_env):
                with self.assertRaises(
                    host_activation.PatrolHostActivationError
                ) as caught:
                    self._activate(ANDROID_DEVICE, command_env=command_env)
                self.assertEqual(caught.exception.code, COMPILE_BLOCKER)
        self.assertEqual(self.recorder.commands, [])

    def test_device_emulator_field_is_required_and_strictly_boolean(self) -> None:
        _install_doubles(self, self.recorder)
        for value in (None, 1, "true"):
            device = dict(ANDROID_DEVICE)
            if value is None:
                device.pop("emulator")
            else:
                device["emulator"] = value
            with self.subTest(value=value):
                with self.assertRaises(
                    host_activation.PatrolHostActivationError
                ) as caught:
                    self._activate(device)
                self.assertEqual(caught.exception.code, COMPILE_BLOCKER)

    def test_activation_failure_is_wrapped_not_swallowed(self) -> None:
        """底层激活异常必须收敛为宿主判否，不允许逃逸成裸异常或被吞掉。"""
        _install_doubles(
            self,
            self.recorder,
            activation_error=RuntimeError("activation receipt digest mismatch"),
        )

        with self.assertRaises(host_activation.PatrolHostActivationError) as caught:
            self._activate(ANDROID_DEVICE)

        self.assertEqual(caught.exception.code, ACTIVATION_BLOCKER)
        self.assertNotIn("digest mismatch", str(caught.exception))

    def test_receipt_requires_activated_status_and_complete_canonical_identity(
        self,
    ) -> None:
        cases = (
            {},
            _activation_receipt(status="failed"),
            _activation_receipt(requestDigest="not-a-digest"),
            _activation_receipt(activePackageDigest="not-a-digest"),
            _activation_receipt(packageDigest="sha256:" + "e" * 64),
            _activation_receipt(activePackageDigest="sha256:" + "e" * 64),
            _activation_receipt(effectiveLaunchManifestDigest="sha256:" + "e" * 64),
        )
        for receipt in cases:
            with self.subTest(receipt=receipt):
                recorder = _Recorder()
                _install_doubles(
                    self,
                    recorder,
                    activation_result=receipt,
                )
                with self.assertRaises(
                    host_activation.PatrolHostActivationError
                ) as caught:
                    self._activate(ANDROID_DEVICE)
                self.assertEqual(
                    caught.exception.code,
                    ACTIVATION_BLOCKER,
                )

    def test_success_writes_both_digests_into_evidence(self) -> None:
        _install_doubles(
            self,
            self.recorder,
            activation_result=_activation_receipt(),
        )
        report: dict[str, Any] = {"runs": []}

        host_activation.ensure_patrol_host_runtime_config(
            self.args,
            ANDROID_DEVICE,
            HANDOFF,
            self.command_env,
            self.log_root,
            report,
        )

        self.assertEqual(
            report["hostRuntimeConfigActivation"],
            {
                "status": "activated",
                "activePackageDigest": PACKAGE_DIGEST,
                "requestDigest": REQUEST_DIGEST,
            },
        )

    def test_gate_block_keeps_the_device_run_visible(self) -> None:
        """判否要落成该设备的 gate_block run，而不是让设备从 runs 里消失。"""
        report: dict[str, Any] = {"runs": []}
        error = host_activation.PatrolHostActivationError(ACTIVATION_BLOCKER)

        host_activation.record_patrol_host_activation_gate_block(
            error,
            report,
            ANDROID_DEVICE,
            "device-manifest.json",
            {"status": "installed"},
            {"status": "ready"},
            {"status": "reset"},
        )

        self.assertEqual(
            report["hostRuntimeConfigActivation"]["status"],
            "gate_block",
        )
        self.assertEqual(len(report["runs"]), 1)
        run = report["runs"][0]
        self.assertEqual(run["status"], "gate_block")
        self.assertEqual(run["device"], ANDROID_DEVICE)
        self.assertEqual(
            run["firstBlocker"],
            report["hostRuntimeConfigActivation"]["firstBlocker"],
        )
        self.assertEqual(run["firstBlocker"], ACTIVATION_BLOCKER)
        # preflight 证据必须随判否一起留下，否则排查只能靠猜。
        self.assertEqual(
            run["preflight"]["deviceManifestPath"],
            "device-manifest.json",
        )

    def test_gate_block_evidence_does_not_persist_raw_cause_or_path(self) -> None:
        _install_doubles(
            self,
            self.recorder,
            activation_error=RuntimeError(
                "secret-token-value at /private/temporary/runtime-config.json"
            ),
        )
        report: dict[str, Any] = {"runs": []}

        with self.assertRaises(host_activation.PatrolHostActivationError) as caught:
            self._activate(ANDROID_DEVICE)
        host_activation.record_patrol_host_activation_gate_block(
            caught.exception,
            report,
            ANDROID_DEVICE,
            "device-manifest.json",
            {"status": "installed"},
            {"status": "ready"},
            {"status": "reset"},
        )

        rendered = repr(report)
        self.assertNotIn("secret-token-value", rendered)
        self.assertNotIn("/private/temporary", rendered)
        self.assertEqual(
            report["runs"][0]["firstBlocker"],
            ACTIVATION_BLOCKER,
        )


if __name__ == "__main__":
    unittest.main()

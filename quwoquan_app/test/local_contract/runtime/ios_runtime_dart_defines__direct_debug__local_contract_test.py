# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

import base64
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = APP_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(APP_DIR / "scripts/runtime/platform"))
sys.path.insert(0, str(APP_DIR / "scripts/device"))
sys.path.insert(0, str(APP_DIR / "test/support/runtime/launcher"))

from ios_dart_defines_test_support import (
    BUILD_WRAPPER,
    CANONICAL_LAUNCHER,
    SCRIPT,
    _apply_handoff_identity,
    _decode_export,
    _install_direct_handoff,
    _write_passthrough_python,
)
from verify_startup_environment_matrix import _validate_runtime_evidence


class IosRuntimeDartDefinesDirectDebugContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime_directory.cleanup)
        self.runtime_root = Path(self.runtime_directory.name)
        self.runtime_python = _write_passthrough_python(self.runtime_root)

    def _environment(self, artifact_root: Path) -> dict[str, str]:
        environment = dict(os.environ)
        for key in (
            "QWQ_APP_RUNTIME_ENV",
            "QWQ_ENVIRONMENT",
            "QWQ_APP_LAUNCH_PROVENANCE",
            "QWQ_RUNTIME_CONFIG_SUPPLY_MODE",
            "QWQ_LAUNCH_TARGET",
            "QWQ_DART_DEFINES_DIGEST",
            "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
            "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
            "QWQ_LAUNCH_HANDOFF_JSON",
            "QWQ_IOS_RUNTIME_CONFIG_PACKAGE_PATH",
            "QWQ_APP_RUNTIME_TRUSTED_PUBLIC_KEYS_JSON",
            "QWQ_REAL_FLUTTER",
            "QWQ_REAL_FLUTTER_VERSION",
            "QWQ_REAL_FLUTTER_COMMAND_RESOLUTION_DIGEST",
            "FLUTTER_ROOT",
            "DART_DEFINES",
        ):
            environment.pop(key, None)
        environment["CONFIGURATION"] = "Debug-alpha"
        environment["PLATFORM_NAME"] = "iphoneos"
        environment["QWQ_IOS_STACKCTL_PYTHON"] = str(self.runtime_python)
        environment["BUILT_PRODUCTS_DIR"] = str(artifact_root / "products")
        environment["TARGET_BUILD_DIR"] = str(artifact_root / "build")
        environment["UNLOCALIZED_RESOURCES_FOLDER_PATH"] = "Runner.app"
        return environment

    def test_direct_debug_embeds_profile_trust_without_runtime_defines_or_package(self) -> None:
        flutter_define = base64.b64encode(b"FLUTTER_VERSION=test").decode("ascii")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for environment_name in ("alpha", "beta", "gamma"):
                with self.subTest(environment=environment_name):
                    artifact_root = root / environment_name
                    environment = self._environment(artifact_root)
                    handoff = _install_direct_handoff(
                        environment,
                        environment_name,
                        artifact_root,
                    )
                    environment["DART_DEFINES"] = flutter_define
                    result = subprocess.run(
                        ["bash", str(SCRIPT)],
                        cwd=APP_DIR,
                        env=environment,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(
                        _decode_export(result.stdout),
                        {"FLUTTER_VERSION": "test"},
                    )
                    resource_root = artifact_root / "build/Runner.app/qwq_runtime"
                    trust = json.loads(
                        (resource_root / "runtime-config-trust.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(trust["buildProfile"], "nonprod")
                    self.assertFalse(
                        (resource_root / "runtime-config-package.json").exists()
                    )
                    self.assertFalse(
                        (artifact_root / "build/Runner.app/QWQNativeRuntime.plist").exists()
                    )
                    self.assertEqual(handoff["environment"], environment_name)
                    self.assertIn("embeddedRuntimePackage=0", result.stderr)

    def test_remote_debug_and_profile_never_self_supply_or_accept_alpha_entrypoint(self) -> None:
        from quwoquan_ops.cli.lib.app_identity import resolve_app_identity
        for name in ("beta", "gamma"):
            for mode in ("debug", "profile"):
                with self.subTest(environment=name, mode=mode), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    environment = self._environment(root)
                    _install_direct_handoff(environment, name, root)
                    identity = resolve_app_identity(platform="ios", environment=name, build_mode=mode)
                    environment["CONFIGURATION"] = identity.configuration
                    environment["PRODUCT_BUNDLE_IDENTIFIER"] = identity.application_id
                    command = ["bash", str(SCRIPT)]
                    good = subprocess.run(command, cwd=APP_DIR, env=environment, capture_output=True, text=True)
                    self.assertEqual(good.returncode, 0, good.stderr)
                    self.assertIn("selfSupplyRequest=0", good.stderr)
                    if mode == "profile":
                        absent_target = {key: value for key, value in environment.items() if key != "FLUTTER_TARGET"}
                        blocked = subprocess.run(command, cwd=APP_DIR, env=absent_target, capture_output=True, text=True)
                        self.assertEqual(blocked.returncode, 2, blocked.stderr)
                        self.assertIn("Profile requires explicit", blocked.stderr)
                    environment["FLUTTER_TARGET"] = "lib/main_alpha.dart"
                    wrong = subprocess.run(command, cwd=APP_DIR, env=environment, capture_output=True, text=True)
                    self.assertEqual(wrong.returncode, 2, wrong.stderr)
                    self.assertIn("conflicts with canonical environment", wrong.stderr)
                    environment.pop("QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH")
                    missing = subprocess.run(command, cwd=APP_DIR, env=environment, capture_output=True, text=True)
                    self.assertEqual(missing.returncode, 2, missing.stderr)
                    self.assertIn("trust envelope is required", missing.stderr)
                    self.assertNotIn("runtimeConfigSupplyMode=build_time_self_supply", missing.stderr)

    def test_direct_debug_rejects_runtime_environment_define_without_bundle_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            environment = self._environment(root)
            _install_direct_handoff(environment, "beta", root)
            environment["DART_DEFINES"] = base64.b64encode(
                b"APP_RUNTIME_ENV=beta"
            ).decode("ascii")
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("compile inputs contain runtime configuration", result.stderr)
            self.assertFalse((root / "build/Runner.app/qwq_runtime").exists())

    def test_retired_environment_and_prod_debug_configurations_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for configuration in (
                "Debug-nonprod",
                "Profile-nonprod",
                "Debug-prod",
                "Profile-prod",
            ):
                with self.subTest(configuration=configuration):
                    environment = self._environment(root / configuration)
                    environment["CONFIGURATION"] = configuration
                    environment["QWQ_APP_BUILD_PROFILE"] = (
                        "prod" if configuration.endswith("-prod") else "nonprod"
                    )
                    result = subprocess.run(
                        ["bash", str(SCRIPT)],
                        cwd=APP_DIR,
                        env=environment,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("GATE_BLOCK", result.stderr)
                    self.assertFalse(
                        (
                            root
                            / configuration
                            / "build/Runner.app/qwq_runtime/runtime-config-trust.json"
                        ).exists()
                    )

    def test_xcode_wrapper_stops_before_backend_without_trust_envelope(self) -> None:
        # 非 Debug-alpha 配置 trust 缺席必须在 backend 之前停下，且不物化任何
        # runtime config 资源（REQ-003：自供给只服务 Debug-alpha）。
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            flutter_root = root / "flutter"
            backend = (
                flutter_root
                / "packages"
                / "flutter_tools"
                / "bin"
                / "xcode_backend.sh"
            )
            backend.parent.mkdir(parents=True)
            marker = root / "backend-called"
            backend.write_text(
                f"#!/bin/sh\ntouch {shlex.quote(str(marker))}\n",
                encoding="utf-8",
            )
            for configuration, build_profile in (
                ("Release-nonprod", "nonprod"),
                ("Profile-alpha", "nonprod"),
                ("Release-prod", "prod"),
            ):
                with self.subTest(configuration=configuration):
                    environment = self._environment(root)
                    environment["CONFIGURATION"] = configuration
                    environment["QWQ_APP_BUILD_PROFILE"] = build_profile
                    environment["FLUTTER_ROOT"] = str(flutter_root)
                    result = subprocess.run(
                        ["bash", str(BUILD_WRAPPER)],
                        cwd=APP_DIR,
                        env=environment,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertFalse(marker.exists())
                    self.assertIn("trust envelope is required", result.stderr)
                    self.assertFalse(
                        (root / "build/Runner.app/qwq_runtime").exists()
                    )

    def test_xcode_wrapper_self_supplies_debug_alpha_then_invokes_backend(self) -> None:
        # 共享工作树可能已有其他构建产物；只验证本次没有新增源码落点。
        source_roots = tuple(APP_DIR / name for name in ("ios", "android", "lib", "scripts", "assets"))
        before = {path for source in source_roots for path in source.glob("**/runtime-config-self-supply-request.json")}
        # Debug-alpha 无外部 handoff：构建阶段现场签发 alpha trust + 自供给激活请求，
        # 嵌入资源后才进入 backend；raw `flutter run` 由此不再依赖 PATH facade。
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            flutter_root = root / "flutter"
            backend = (
                flutter_root
                / "packages"
                / "flutter_tools"
                / "bin"
                / "xcode_backend.sh"
            )
            backend.parent.mkdir(parents=True)
            marker = root / "backend-called"
            backend.write_text(
                f"#!/bin/sh\ntouch {shlex.quote(str(marker))}\n",
                encoding="utf-8",
            )
            environment = self._environment(root)
            environment["CONFIGURATION"] = "Debug-alpha"
            environment["QWQ_APP_BUILD_PROFILE"] = "nonprod"
            environment["FLUTTER_ROOT"] = str(flutter_root)
            environment.pop("QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH", None)
            result = subprocess.run(
                ["bash", str(BUILD_WRAPPER)],
                cwd=APP_DIR,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(marker.exists())
            self.assertIn("runtimeConfigSupplyMode=build_time_self_supply", result.stderr)
            self.assertIn("selfSupplyRequest=1", result.stderr)
            runtime_dir = root / "build/Runner.app/qwq_runtime"
            self.assertEqual(
                sorted(path.name for path in runtime_dir.iterdir()),
                ["runtime-config-self-supply-request.json", "runtime-config-trust.json"],
            )
            request = json.loads(
                (runtime_dir / "runtime-config-self-supply-request.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                request["effectiveLaunchManifest"]["runtimeConfigSupplyMode"],
                "build_time_self_supply",
            )
            self.assertEqual(request["expectedActiveDigest"], "")
            # 自供给材料不落源码目录（build/ 产物除外），且构建阶段私有临时目录已清理。
            after = {path for source in source_roots for path in source.glob("**/runtime-config-self-supply-request.json")}
            self.assertEqual(after, before)

    def test_xcode_wrapper_invokes_backend_after_trust_materialization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            flutter_root = root / "flutter"
            backend = (
                flutter_root
                / "packages"
                / "flutter_tools"
                / "bin"
                / "xcode_backend.sh"
            )
            backend.parent.mkdir(parents=True)
            marker = root / "backend-env"
            backend.write_text(
                "#!/bin/sh\n"
                f"printf '%s|%s\\n' \"$QWQ_IOS_DART_DEFINES_READY\" \"$FLUTTER_TARGET\" > {shlex.quote(str(marker))}\n",
                encoding="utf-8",
            )
            environment = self._environment(root)
            handoff = _apply_handoff_identity(
                environment,
                "alpha",
                artifact_root=root,
                runtime_python=self.runtime_python,
            )
            environment["QWQ_LAUNCH_HANDOFF_JSON"] = json.dumps(
                handoff,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            environment["FLUTTER_ROOT"] = str(flutter_root)
            result = subprocess.run(
                ["bash", str(BUILD_WRAPPER)],
                cwd=APP_DIR,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                marker.read_text(encoding="utf-8").strip(),
                "1|lib/main_alpha.dart",
            )
            self.assertTrue(
                (root / "build/Runner.app/qwq_runtime/runtime-config-trust.json").is_file()
            )
            self.assertFalse(
                (root / "build/Runner.app/qwq_runtime/runtime-config-package.json").exists()
            )
            self.assertIn("embeddedRuntimePackage=0", result.stderr)

    def test_canonical_launcher_still_exports_handoff_for_post_install_integration(self) -> None:
        source = CANONICAL_LAUNCHER.read_text(encoding="utf-8")
        build_handoff = source.index('HANDOFF_JSON="$("${HANDOFF_CMD[@]}")"')
        export_handoff = source.index('export QWQ_LAUNCH_HANDOFF_JSON="$HANDOFF_JSON"')
        canonical_executor = source.index('scripts/device/run_app_instance.py"')
        self.assertLess(build_handoff, export_handoff)
        self.assertLess(export_handoff, canonical_executor)

    def test_package_probe_selects_environment_configuration_and_entrypoint(self) -> None:
        from unittest import mock
        from startup_environment_matrix import package_probe

        def handoff(name, *, trust_output):
            environment = {}
            return _apply_handoff_identity(environment, name,
                                           artifact_root=Path(trust_output).parent,
                                           runtime_python=self.runtime_python)

        with mock.patch.object(package_probe, "_launcher_handoff", side_effect=handoff):
            for name in ("alpha", "beta", "gamma", "prod"):
                with self.subTest(environment=name):
                    self.assertEqual(package_probe._ios_compile_defines(name), {})
                    self.assertEqual(package_probe._xcode_configuration(name),
                                     "Release-prod" if name == "prod" else f"Debug-{name}")

    def test_runtime_evidence_requires_one_correlated_safe_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "ios.json"
            path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "attemptId": "attempt_ios_1",
                        "runtimeEnv": "alpha",
                        "launchProvenance": "canonical_launcher",
                        "runtimeConfigSupplyMode": "external_runtime_package",
                        "runtimeConfigurationState": "complete",
                        "rendererFirstFrameMs": 1400,
                        "safeTerminalMs": 2100,
                        "reportedSafeTerminalMs": 2100,
                        "nativeReceivedSafeTerminalMs": 2140,
                        "watchdogOutcome": "not_triggered",
                        "canonicalTerminal": "routerShell",
                        "startupSequenceMotionCurrent": True,
                        "telemetryAcknowledged": True,
                        "failureCode": "",
                    }
                ),
                encoding="utf-8",
            )
            issues, _ = _validate_runtime_evidence(path)
            self.assertEqual(issues, [])

            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["canonicalTerminal"] = "safeRecovery"
            path.write_text(json.dumps(payload), encoding="utf-8")
            issues, _ = _validate_runtime_evidence(path)
            self.assertIn("canonical terminal must be routerShell", issues[0])


if __name__ == "__main__":
    unittest.main()

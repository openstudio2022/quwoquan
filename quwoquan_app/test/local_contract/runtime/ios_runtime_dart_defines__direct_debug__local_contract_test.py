# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
#
# 由 1000 行硬顶拆分自 ios_runtime_dart_defines__local_contract_test.py：
# 本文件承载 direct flutter run / xcode wrapper / canonical launcher /
# runtime evidence 组；测试逐字搬移，共享常量与构造 helper 下沉
# test/support/runtime/launcher/ios_dart_defines_test_support.py。

import base64
import json
import os
import plistlib
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/runtime/platform"))
sys.path.insert(0, str(APP_DIR / "scripts/device"))
sys.path.insert(0, str(APP_DIR / "test/support/runtime/launcher"))

from ios_dart_defines_test_support import (
    BUILD_WRAPPER,
    CANONICAL_LAUNCHER,
    REQUIRED_KEYS,
    SCRIPT,
    _apply_handoff_identity,
    _decode_export,
    _install_direct_handoff,
    _write_hard_blocked_preflight_python,
    _write_preflight_python,
)
from verify_startup_environment_matrix import _validate_runtime_evidence


class IosRuntimeDartDefinesContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime_directory.cleanup)
        self.runtime_python = _write_preflight_python(
            Path(self.runtime_directory.name)
        )

    def test_direct_ios_debug_selects_canonical_nonprod_handoff(self) -> None:
        flutter_define = base64.b64encode(b"FLUTTER_VERSION=test").decode("ascii")
        with tempfile.TemporaryDirectory() as temporary_directory:
            preflight_python = _write_preflight_python(Path(temporary_directory))
            for environment in ("alpha", "beta", "gamma"):
                with self.subTest(environment=environment):
                    env = dict(os.environ)
                    for key in (
                        "QWQ_APP_RUNTIME_ENV",
                        "QWQ_APP_LAUNCH_MODE",
                        "QWQ_LAUNCH_TARGET",
                        "QWQ_DART_DEFINES_DIGEST",
                        "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
                        "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
                    ):
                        env.pop(key, None)
                    env["QWQ_ENVIRONMENT"] = environment
                    env["QWQ_IOS_STACKCTL_PYTHON"] = str(preflight_python)
                    _install_direct_handoff(env, environment)
                    env["DART_DEFINES"] = flutter_define
                    env["CONFIGURATION"] = f"Debug-{environment}"
                    env["PLATFORM_NAME"] = "iphoneos"
                    build_dir = Path(temporary_directory) / environment
                    env["TARGET_BUILD_DIR"] = str(build_dir)
                    env["UNLOCALIZED_RESOURCES_FOLDER_PATH"] = "Runner.app"
                    result = subprocess.run(
                        ["bash", str(SCRIPT)],
                        cwd=APP_DIR,
                        env=env,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    values = _decode_export(result.stdout)
                    self.assertEqual(values["APP_RUNTIME_ENV"], environment)
                    self.assertEqual(
                        values["QWQ_APP_LAUNCH_MODE"],
                        "direct_flutter_run",
                    )
                    self.assertEqual(values["FLUTTER_VERSION"], "test")
                    self.assertEqual(values["APP_LAUNCH_POLICY"], "test_live")
                    self.assertNotIn("CONTENT_BINDING_STATE", values)
                    self.assertTrue(REQUIRED_KEYS.issubset(values))
                    self.assertIn(
                        f"direct Debug uses canonical {environment}-local handoff",
                        result.stderr,
                    )
                    self.assertIn(
                        "WARN: target startup status is not running: stopped",
                        result.stderr,
                    )
                    with (
                        build_dir / "Runner.app" / "QWQNativeRuntime.plist"
                    ).open("rb") as stream:
                        native_manifest = plistlib.load(stream)
                    self.assertNotIn("contentReleaseId", native_manifest)
                    self.assertNotIn("contentBindingState", native_manifest)
                    self.assertEqual(native_manifest["launchPolicy"], "test_live")
                    self.assertRegex(
                        native_manifest["effectiveLaunchManifestDigest"],
                        r"^sha256:[0-9a-f]{64}$",
                    )

    def test_direct_ios_debug_reports_the_first_hard_safety_blocker(
        self,
    ) -> None:
        env = dict(os.environ)
        for key in (
            "QWQ_APP_RUNTIME_ENV",
            "QWQ_APP_LAUNCH_MODE",
            "QWQ_LAUNCH_TARGET",
            "QWQ_DART_DEFINES_DIGEST",
            "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
            "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
            "DART_DEFINES",
        ):
            env.pop(key, None)
        with tempfile.TemporaryDirectory() as temporary_directory:
            env["QWQ_IOS_STACKCTL_PYTHON"] = str(
                _write_hard_blocked_preflight_python(Path(temporary_directory))
            )
            env["CONFIGURATION"] = "Debug-alpha"
            env["PLATFORM_NAME"] = "iphoneos"
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "first blocker: api endpoint escapes the selected alpha namespace",
            result.stderr,
        )
        self.assertNotIn("target content is not ready", result.stderr)
        self.assertIn("retry the same flutter run command", result.stderr)

    def test_flutter_run_define_synthesizes_beta_debug_handoff(self) -> None:
        runtime_env = base64.b64encode(b"APP_RUNTIME_ENV=beta").decode("ascii")
        env = dict(os.environ)
        for key in (
            "QWQ_APP_RUNTIME_ENV",
            "QWQ_APP_LAUNCH_MODE",
            "QWQ_LAUNCH_TARGET",
            "QWQ_DART_DEFINES_DIGEST",
            "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
            "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
        ):
            env.pop(key, None)
        env["DART_DEFINES"] = runtime_env
        with tempfile.TemporaryDirectory() as temporary_directory:
            env["QWQ_IOS_STACKCTL_PYTHON"] = str(
                _write_preflight_python(Path(temporary_directory))
            )
            _install_direct_handoff(env, "beta")
            env["CONFIGURATION"] = "Debug-beta"
            env["PLATFORM_NAME"] = "iphoneos"
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
        values = _decode_export(result.stdout)
        self.assertEqual(values["APP_RUNTIME_ENV"], "beta")
        self.assertEqual(values["QWQ_APP_LAUNCH_MODE"], "direct_flutter_run")
        self.assertIn("canonical beta-local handoff", result.stderr)

    def test_direct_debug_rejects_mismatched_flavor_without_mutation(self) -> None:
        env = dict(os.environ)
        for key in (
            "QWQ_APP_RUNTIME_ENV",
            "QWQ_APP_LAUNCH_MODE",
            "QWQ_LAUNCH_TARGET",
            "QWQ_DART_DEFINES_DIGEST",
            "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
            "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
            "DART_DEFINES",
        ):
            env.pop(key, None)
        with tempfile.TemporaryDirectory() as temporary_directory:
            env["QWQ_IOS_STACKCTL_PYTHON"] = str(
                _write_preflight_python(Path(temporary_directory))
            )
            _install_direct_handoff(env, "beta")
            env["QWQ_ENVIRONMENT"] = "beta"
            env["CONFIGURATION"] = "Debug-alpha"
            env["PLATFORM_NAME"] = "iphonesimulator"
            env["PRODUCT_BUNDLE_IDENTIFIER"] = "com.example.quwoquanApp.alpha.debug"
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("configuration Debug-alpha does not match environment=beta", result.stderr)
        self.assertFalse((APP_DIR / "ios/Flutter/QWQEnvironment.xcconfig").exists())
        self.assertFalse((APP_DIR / "scripts/ios/write_environment_xcconfig.sh").exists())

    def test_release_without_canonical_launcher_fails_closed(self) -> None:
        env = dict(os.environ)
        for key in (
            "QWQ_APP_RUNTIME_ENV",
            "DART_DEFINES",
            "QWQ_APP_LAUNCH_MODE",
            "QWQ_LAUNCH_TARGET",
            "QWQ_DART_DEFINES_DIGEST",
            "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
            "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
        ):
            env.pop(key, None)
        env["CONFIGURATION"] = "Release-alpha"
        env["PLATFORM_NAME"] = "iphonesimulator"
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=APP_DIR,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("canonical runtime handoff is required", result.stderr)

    def test_xcode_wrapper_propagates_prepare_failure_before_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            flutter_root = Path(temporary_directory) / "flutter"
            backend = (
                flutter_root
                / "packages"
                / "flutter_tools"
                / "bin"
                / "xcode_backend.sh"
            )
            backend.parent.mkdir(parents=True)
            marker = Path(temporary_directory) / "backend-called"
            backend.write_text(
                f"#!/bin/sh\ntouch {shlex.quote(str(marker))}\n",
                encoding="utf-8",
            )
            env = dict(os.environ)
            env.pop("QWQ_APP_RUNTIME_ENV", None)
            env.pop("DART_DEFINES", None)
            env["FLUTTER_ROOT"] = str(flutter_root)
            result = subprocess.run(
                ["bash", str(BUILD_WRAPPER)],
                cwd=APP_DIR,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(marker.exists())
            self.assertIn("GATE_BLOCK", result.stderr)

    def test_xcode_wrapper_direct_debug_invokes_backend_after_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            flutter_root = Path(temporary_directory) / "flutter"
            backend = (
                flutter_root
                / "packages"
                / "flutter_tools"
                / "bin"
                / "xcode_backend.sh"
            )
            backend.parent.mkdir(parents=True)
            marker = Path(temporary_directory) / "runtime-ready"
            backend.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$QWQ_IOS_DART_DEFINES_READY\" > "
                f"{shlex.quote(str(marker))}\n",
                encoding="utf-8",
            )
            env = dict(os.environ)
            for key in (
                "QWQ_APP_RUNTIME_ENV",
                "DART_DEFINES",
                "QWQ_APP_LAUNCH_MODE",
                "QWQ_LAUNCH_TARGET",
                "QWQ_DART_DEFINES_DIGEST",
                "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
                "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
            ):
                env.pop(key, None)
            env["PLATFORM_NAME"] = "iphoneos"
            env["QWQ_IOS_STACKCTL_PYTHON"] = str(
                _write_preflight_python(Path(temporary_directory))
            )
            _install_direct_handoff(env, "alpha")
            env["CONFIGURATION"] = "Debug-alpha"
            env["FLUTTER_ROOT"] = str(flutter_root)
            result = subprocess.run(
                ["bash", str(BUILD_WRAPPER)],
                cwd=APP_DIR,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), "1")
            self.assertIn(
                "direct Debug uses canonical alpha-local handoff",
                result.stderr,
            )

    def test_xcode_wrapper_runs_backend_only_after_verified_defines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            flutter_root = Path(temporary_directory) / "flutter"
            backend = (
                flutter_root
                / "packages"
                / "flutter_tools"
                / "bin"
                / "xcode_backend.sh"
            )
            backend.parent.mkdir(parents=True)
            marker = Path(temporary_directory) / "backend-env"
            backend.write_text(
                "#!/bin/sh\n"
                f"printf '%s|%s\\n' \"$QWQ_IOS_DART_DEFINES_READY\" \"$FLUTTER_TARGET\" > {shlex.quote(str(marker))}\n",
                encoding="utf-8",
            )
            env = dict(os.environ)
            env["QWQ_APP_RUNTIME_ENV"] = "alpha"
            _apply_handoff_identity(
                env,
                "alpha",
                runtime_python=self.runtime_python,
            )
            env["FLUTTER_ROOT"] = str(flutter_root)
            subprocess.run(
                ["bash", str(BUILD_WRAPPER)],
                cwd=APP_DIR,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                marker.read_text(encoding="utf-8").strip(),
                "1|lib/main_prod.dart",
            )

    def test_flutter_run_define_selects_environment_without_xcode_variable(self) -> None:
        runtime_env = base64.b64encode(b"APP_RUNTIME_ENV=beta").decode("ascii")
        env = dict(os.environ)
        env.pop("QWQ_APP_RUNTIME_ENV", None)
        env["DART_DEFINES"] = runtime_env
        _apply_handoff_identity(
            env,
            "beta",
            runtime_python=self.runtime_python,
        )
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=APP_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(_decode_export(result.stdout)["APP_RUNTIME_ENV"], "beta")

    def test_canonical_launcher_launch_mode_survives_xcode_build_phase(self) -> None:
        runtime_env = base64.b64encode(b"APP_RUNTIME_ENV=gamma").decode("ascii")
        env = dict(os.environ)
        env["QWQ_APP_RUNTIME_ENV"] = "gamma"
        env["QWQ_APP_LAUNCH_MODE"] = "canonical_launcher"
        env["DART_DEFINES"] = runtime_env
        handoff = _apply_handoff_identity(
            env,
            "gamma",
            launch_mode="canonical_launcher",
            runtime_python=self.runtime_python,
        )
        env["QWQ_LAUNCH_HANDOFF_JSON"] = json.dumps(
            handoff,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=APP_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            _decode_export(result.stdout)["QWQ_APP_LAUNCH_MODE"],
            "canonical_launcher",
        )

    def test_canonical_launcher_exports_exact_handoff_to_xcode_build_phase(self) -> None:
        source = CANONICAL_LAUNCHER.read_text(encoding="utf-8")
        build_handoff = source.index('HANDOFF_JSON="$("${HANDOFF_CMD[@]}")"')
        export_handoff = source.index(
            'export QWQ_LAUNCH_HANDOFF_JSON="$HANDOFF_JSON"'
        )
        flutter_run = source.index("flutter run \\")
        self.assertLess(build_handoff, export_handoff)
        self.assertLess(export_handoff, flutter_run)

    def test_conflicting_launcher_and_flutter_environment_fails_build(self) -> None:
        runtime_env = base64.b64encode(b"APP_RUNTIME_ENV=gamma").decode("ascii")
        env = dict(os.environ)
        env["QWQ_APP_RUNTIME_ENV"] = "prod"
        env["DART_DEFINES"] = runtime_env
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=APP_DIR,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("conflicts with DART_DEFINES", result.stderr)

    def test_runtime_evidence_requires_one_correlated_safe_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "android.json"
            path.write_text(
                """
{
  "passed": true,
  "attemptId": "attempt_android_1",
  "runtimeEnv": "alpha",
  "launchMode": "canonical_launcher",
  "runtimeConfigurationState": "complete",
  "rendererFirstFrameMs": 1400,
  "safeTerminalMs": 2100,
  "reportedSafeTerminalMs": 2100,
  "nativeReceivedSafeTerminalMs": 2140,
  "watchdogOutcome": "not_triggered",
  "canonicalTerminal": "routerShell",
  "startupSequenceMotionCurrent": true,
  "telemetryAcknowledged": true,
  "failureCode": ""
}
""".strip(),
                encoding="utf-8",
            )
            issues, _ = _validate_runtime_evidence(path)
            self.assertEqual(issues, [])

            safe_recovery_payload = json.loads(path.read_text(encoding="utf-8"))
            safe_recovery_payload["canonicalTerminal"] = "safeRecovery"
            path.write_text(
                json.dumps(safe_recovery_payload),
                encoding="utf-8",
            )
            issues, _ = _validate_runtime_evidence(path)
            self.assertIn("canonical terminal must be routerShell", issues[0])

            path.write_text(
                """
{
  "attemptId": "",
  "runtimeEnv": "alpha",
  "launchMode": "canonical_launcher",
  "runtimeConfigurationState": "complete",
  "rendererFirstFrameMs": 6100,
  "safeTerminalMs": 6200,
  "reportedSafeTerminalMs": 6200,
  "nativeReceivedSafeTerminalMs": 6210,
  "watchdogOutcome": "native_recovery",
  "canonicalTerminal": "unresolved",
  "failureCode": ""
}
""".strip(),
                encoding="utf-8",
            )
            issues, _ = _validate_runtime_evidence(path)
            self.assertGreaterEqual(len(issues), 5)


if __name__ == "__main__":
    unittest.main()

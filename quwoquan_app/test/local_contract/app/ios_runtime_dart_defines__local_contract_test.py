# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

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
sys.path.insert(0, str(APP_DIR / "scripts/runtime"))

from verify_startup_environment_matrix import _validate_runtime_evidence


SCRIPT = APP_DIR / "scripts/ios/prepare_dart_defines.sh"
BUILD_WRAPPER = APP_DIR / "scripts/ios/xcode_backend_build.sh"
HANDOFF_BUILDER = APP_DIR / "scripts/device/build_launcher_handoff.py"
STACKCTL_PYTHON_RESOLVER = APP_DIR / "scripts/ios/resolve_stackctl_python.sh"
RUNTIME_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}
REQUIRED_KEYS = {
    "APP_RUNTIME_ENV",
    "CLOUD_GATEWAY_BASE_URL",
    "APP_LEGAL_BASE_URL",
    "PUBLIC_WEB_BASE_URL",
    "MEDIA_AVATAR_CDN_BASE_URL",
    "MEDIA_IMAGE_CDN_BASE_URL",
    "MEDIA_VIDEO_CDN_BASE_URL",
    "MEDIA_UPLOAD_BASE_URL",
    "RTC_MEDIA_CONNECTION_URL",
}


def _build_handoff(
    environment: str,
    *,
    launch_mode: str = "xcode_build",
) -> dict[str, object]:
    command = [
        "python3",
        str(HANDOFF_BUILDER),
        "--env",
        environment,
        "--target",
        RUNTIME_TARGETS[environment],
        "--launch-mode",
        launch_mode,
    ]
    if launch_mode in {"canonical_launcher", "direct_flutter_run"}:
        command.extend(
            [
                "--content-release-id",
                f"release-{environment}",
                "--content-manifest-digest",
                "sha256:" + "1" * 64,
                "--content-readiness-receipt-digest",
                "sha256:" + "2" * 64,
            ]
        )
    result = subprocess.run(
        command,
        cwd=APP_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _apply_handoff_identity(
    env: dict[str, str],
    environment: str,
    *,
    launch_mode: str = "xcode_build",
) -> dict[str, object]:
    handoff = _build_handoff(environment, launch_mode=launch_mode)
    env["QWQ_APP_LAUNCH_MODE"] = launch_mode
    env["QWQ_LAUNCH_TARGET"] = str(handoff["target"])
    env["QWQ_DART_DEFINES_DIGEST"] = str(handoff["dartDefinesDigest"])
    env["QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST"] = str(
        handoff["runtimeConfigDigest"]
    )
    env["QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST"] = str(
        handoff["effectiveLaunchManifestDigest"]
    )
    for environment_key, handoff_key in (
        ("QWQ_CONTENT_RELEASE_ID", "contentReleaseId"),
        ("QWQ_CONTENT_MANIFEST_DIGEST", "contentManifestDigest"),
        (
            "QWQ_CONTENT_READINESS_RECEIPT_DIGEST",
            "contentReadinessReceiptDigest",
        ),
    ):
        value = str(handoff.get(handoff_key) or "")
        if value:
            env[environment_key] = value
    return handoff


def _decode_export(stdout: str) -> dict[str, str]:
    line = next(
        item for item in stdout.splitlines() if item.startswith("export DART_DEFINES=")
    )
    assignment = shlex.split(line.removeprefix("export "))[0]
    encoded = assignment.split("=", 1)[1]
    values: dict[str, str] = {}
    for item in encoded.split(","):
        decoded = base64.b64decode(item).decode("utf-8")
        key, value = decoded.split("=", 1)
        values[key] = value
    return values


def _write_preflight_python(directory: Path) -> Path:
    executable = directory / "preflight-python"
    preflight = json.dumps(
        {
            "status": "passed",
            "releaseId": "release-test",
            "manifestDigest": "sha256:" + "1" * 64,
            "readinessReceiptDigest": "sha256:" + "2" * 64,
        }
    )
    executable.write_text(
        "#!/usr/bin/env bash\n"
        "for argument in \"$@\"; do\n"
        "  if [[ \"$argument\" == \"app-debug-preflight\" ]]; then\n"
        f"    printf '%s\\n' {shlex.quote(preflight)}\n"
        "    exit 0\n"
        "  fi\n"
        "done\n"
        f"exec {shlex.quote(sys.executable)} \"$@\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _write_blocked_preflight_python(directory: Path) -> Path:
    executable = directory / "blocked-preflight-python"
    preflight = json.dumps(
        {
            "status": "gate_block",
            "details": [
                "target startup status is not running: stopped",
                "api-edge is not ready: network_error",
            ],
        }
    )
    executable.write_text(
        "#!/usr/bin/env bash\n"
        "for argument in \"$@\"; do\n"
        "  if [[ \"$argument\" == \"app-debug-preflight\" ]]; then\n"
        f"    printf '%s\\n' {shlex.quote(preflight)}\n"
        "    exit 2\n"
        "  fi\n"
        "done\n"
        f"exec {shlex.quote(sys.executable)} \"$@\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


class IosRuntimeDartDefinesContractTest(unittest.TestCase):
    def test_xcode_stackctl_python_resolver_skips_incompatible_path_python(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            invalid_python = temporary_root / "bin" / "python3"
            invalid_python.parent.mkdir()
            invalid_python.write_text(
                "#!/usr/bin/env bash\nexit 1\n",
                encoding="utf-8",
            )
            invalid_python.chmod(0o755)
            compatible_python = (
                temporary_root / "python-cache" / "quwoquan-data" / "bin" / "python3"
            )
            compatible_python.parent.mkdir(parents=True)
            compatible_python.symlink_to(Path(sys.executable))
            env = dict(os.environ)
            env.pop("QWQ_IOS_STACKCTL_PYTHON", None)
            env["PATH"] = (
                str(invalid_python.parent) + os.pathsep + env["PATH"]
            )
            env["QWQ_PYTHON_CACHE_ROOT"] = str(temporary_root / "python-cache")
            result = subprocess.run(
                ["bash", str(STACKCTL_PYTHON_RESOLVER)],
                cwd=APP_DIR.parent,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                Path(result.stdout.strip()).resolve(),
                compatible_python.resolve(),
            )

    def test_all_environment_packages_produce_complete_defines(self) -> None:
        flutter_define = base64.b64encode(b"FLUTTER_VERSION=test").decode("ascii")
        for env_name in ("alpha", "beta", "gamma", "prod"):
            with self.subTest(env=env_name):
                env = dict(os.environ)
                env["QWQ_APP_RUNTIME_ENV"] = env_name
                env["DART_DEFINES"] = flutter_define
                _apply_handoff_identity(env, env_name)
                result = subprocess.run(
                    ["bash", str(SCRIPT)],
                    cwd=APP_DIR,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                values = _decode_export(result.stdout)
                self.assertEqual(values["APP_RUNTIME_ENV"], env_name)
                self.assertEqual(values["QWQ_APP_LAUNCH_MODE"], "xcode_build")
                self.assertTrue(REQUIRED_KEYS.issubset(values))
                self.assertEqual(values["FLUTTER_VERSION"], "test")
                self.assertIn(
                    "export FLUTTER_TARGET=lib/main_prod.dart",
                    result.stdout,
                )
                self.assertIn(f"env={env_name}", result.stderr)

    def test_xcode_build_writes_native_recovery_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = dict(os.environ)
            env["QWQ_APP_RUNTIME_ENV"] = "alpha"
            _apply_handoff_identity(env, "alpha")
            env["TARGET_BUILD_DIR"] = temporary_directory
            env["UNLOCALIZED_RESOURCES_FOLDER_PATH"] = "Runner.app"
            subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            manifest_path = (
                Path(temporary_directory)
                / "Runner.app"
                / "QWQNativeRuntime.plist"
            )
            with manifest_path.open("rb") as stream:
                manifest = plistlib.load(stream)
            self.assertEqual(manifest["runtimeEnvironment"], "alpha")
            self.assertRegex(
                manifest["runtimeConfigDigest"],
                r"^sha256:[0-9a-f]{64}$",
            )
            self.assertEqual(
                manifest["recoveryBaseURL"],
                "https://api.alpha.quwoquan.com:17000",
            )
            self.assertEqual(
                manifest["publicWebURL"],
                "https://alpha.quwoquan.com:17000",
            )
            self.assertEqual(
                manifest["appDownloadBaseURL"],
                "https://cdn.alpha.quwoquan.com:17100/download",
            )
            self.assertEqual(
                manifest["runtimeDefines"]["APP_RUNTIME_ENV"],
                "alpha",
            )
            self.assertEqual(
                manifest["runtimeDefines"]["QWQ_APP_LAUNCH_MODE"],
                "xcode_build",
            )

    def test_invalid_environment_fails_before_flutter_build(self) -> None:
        env = dict(os.environ)
        env["QWQ_APP_RUNTIME_ENV"] = "staging"
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=APP_DIR,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be alpha|beta|gamma|prod", result.stderr)

    def test_missing_canonical_handoff_fails_closed(self) -> None:
        env = dict(os.environ)
        env.pop("QWQ_APP_RUNTIME_ENV", None)
        env.pop("DART_DEFINES", None)
        env.pop("CONFIGURATION", None)
        env.pop("PLATFORM_NAME", None)
        env.pop("EFFECTIVE_PLATFORM_NAME", None)
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
        self.assertIn("./run.sh -d <device>", result.stderr)

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
                    env["DART_DEFINES"] = flutter_define
                    env["CONFIGURATION"] = "Debug"
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
                    self.assertTrue(REQUIRED_KEYS.issubset(values))
                    self.assertIn(
                        f"direct Debug uses canonical {environment}-local handoff",
                        result.stderr,
                    )
                    with (
                        build_dir / "Runner.app" / "QWQNativeRuntime.plist"
                    ).open("rb") as stream:
                        native_manifest = plistlib.load(stream)
                    self.assertEqual(
                        native_manifest["contentReleaseId"],
                        "release-test",
                    )
                    self.assertRegex(
                        native_manifest["contentManifestDigest"],
                        r"^sha256:[0-9a-f]{64}$",
                    )
                    self.assertRegex(
                        native_manifest["contentReadinessReceiptDigest"],
                        r"^sha256:[0-9a-f]{64}$",
                    )
                    self.assertRegex(
                        native_manifest["effectiveLaunchManifestDigest"],
                        r"^sha256:[0-9a-f]{64}$",
                    )

    def test_direct_ios_debug_reports_the_first_runtime_readiness_blocker(
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
                _write_blocked_preflight_python(Path(temporary_directory))
            )
            env["CONFIGURATION"] = "Debug"
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
            "first blocker: target startup status is not running: stopped",
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
            env["CONFIGURATION"] = "Debug"
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
        env["CONFIGURATION"] = "Release"
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
            env["CONFIGURATION"] = "Debug"
            env["PLATFORM_NAME"] = "iphoneos"
            env["QWQ_IOS_STACKCTL_PYTHON"] = str(
                _write_preflight_python(Path(temporary_directory))
            )
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
            _apply_handoff_identity(env, "alpha")
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
        _apply_handoff_identity(env, "beta")
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
        _apply_handoff_identity(
            env,
            "gamma",
            launch_mode="canonical_launcher",
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

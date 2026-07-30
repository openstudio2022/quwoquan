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


class IosRuntimeDartDefinesContractTest(unittest.TestCase):
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

    def test_direct_ios_simulator_debug_is_rejected_before_install(self) -> None:
        flutter_define = base64.b64encode(b"FLUTTER_VERSION=test").decode("ascii")
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
        env["DART_DEFINES"] = flutter_define
        env["CONFIGURATION"] = "Debug"
        env["PLATFORM_NAME"] = "iphonesimulator"
        env["TARGET_DEVICE_IDENTIFIER"] = (
            "DA74CDF7-1E16-4F85-BA5B-7D4320FD27DB"
        )
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

    def test_direct_debug_does_not_synthesize_non_alpha_handoff(self) -> None:
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
        env["CONFIGURATION"] = "Debug"
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
        self.assertIn("canonical launch mode is required", result.stderr)

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

    def test_xcode_wrapper_direct_debug_never_invokes_backend(self) -> None:
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
            marker = Path(temporary_directory) / "flutter-target"
            backend.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$FLUTTER_TARGET\" > {shlex.quote(str(marker))}\n",
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
            env["PLATFORM_NAME"] = "iphonesimulator"
            env["TARGET_DEVICE_IDENTIFIER"] = (
                "DA74CDF7-1E16-4F85-BA5B-7D4320FD27DB"
            )
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
            self.assertIn("use quwoquan_app/run.sh -d <simulator>", result.stderr)

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
                f"printf '%s\\n' \"$QWQ_IOS_DART_DEFINES_READY\" > {shlex.quote(str(marker))}\n",
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
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), "1")

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

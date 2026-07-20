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
sys.path.insert(0, str(APP_DIR / "scripts/runtime"))

from verify_startup_environment_matrix import _validate_runtime_evidence


SCRIPT = APP_DIR / "scripts/ios/prepare_dart_defines.sh"
REQUIRED_KEYS = {
    "APP_RUNTIME_ENV",
    "CLOUD_GATEWAY_BASE_URL",
    "APP_LEGAL_BASE_URL",
    "MEDIA_AVATAR_CDN_BASE_URL",
    "MEDIA_IMAGE_CDN_BASE_URL",
    "MEDIA_VIDEO_CDN_BASE_URL",
    "MEDIA_UPLOAD_BASE_URL",
}


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

    def test_missing_environment_does_not_fall_back_to_alpha(self) -> None:
        env = dict(os.environ)
        env.pop("QWQ_APP_RUNTIME_ENV", None)
        env.pop("DART_DEFINES", None)
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=APP_DIR,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("explicit QWQ_APP_RUNTIME_ENV", result.stderr)

    def test_flutter_run_define_selects_environment_without_xcode_variable(self) -> None:
        runtime_env = base64.b64encode(b"APP_RUNTIME_ENV=beta").decode("ascii")
        env = dict(os.environ)
        env.pop("QWQ_APP_RUNTIME_ENV", None)
        env["DART_DEFINES"] = runtime_env
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

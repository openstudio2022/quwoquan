# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
#
# 由 1000 行硬顶拆分：本文件保留 xcode_build 阶段 defines 生成与 canonical
# handoff 校验组；direct flutter run / xcode wrapper / runtime evidence 组见
# ios_runtime_dart_defines__direct_debug__local_contract_test.py；共享常量与
# 构造 helper 下沉 test/support/runtime/launcher/ios_dart_defines_test_support.py。

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
    REQUIRED_KEYS,
    SCRIPT,
    STACKCTL_PYTHON_RESOLVER,
    _apply_handoff_identity,
    _bound_test_live_handoff,
    _decode_export,
    _encode_defines,
    _write_preflight_python,
)


class IosRuntimeDartDefinesContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime_directory.cleanup)
        self.runtime_python = _write_preflight_python(
            Path(self.runtime_directory.name)
        )

    def test_xcode_build_phase_reuses_resolved_python_for_every_python_step(
        self,
    ) -> None:
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("python3", source)
        self.assertIn('"$RUNTIME_PYTHON" -c', source)
        self.assertGreaterEqual(source.count('"$RUNTIME_PYTHON" -'), 5)

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
                env["QWQ_ENVIRONMENT"] = env_name if env_name != "prod" else ""
                env["CONFIGURATION"] = f"Debug-{env_name}"
                env["DART_DEFINES"] = flutter_define
                _apply_handoff_identity(
                    env,
                    env_name,
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
            _apply_handoff_identity(
                env,
                "alpha",
                runtime_python=self.runtime_python,
            )
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

    def test_canonical_handoff_drives_dart_and_native_manifest(self) -> None:
        handoff = _bound_test_live_handoff()
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = dict(os.environ)
            env["QWQ_IOS_STACKCTL_PYTHON"] = str(self.runtime_python)
            env["QWQ_LAUNCH_HANDOFF_JSON"] = json.dumps(
                handoff,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            env["DART_DEFINES"] = _encode_defines(
                {
                    **handoff["dartDefines"],
                    "FLUTTER_VERSION": "test",
                }
            )
            env["TARGET_BUILD_DIR"] = temporary_directory
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
            # 内容激活是运行时服务端事实：Dart defines 与 native manifest
            # 都不得携带内容绑定身份。
            self.assertNotIn("CONTENT_BINDING_STATE", values)
            self.assertEqual(values["FLUTTER_VERSION"], "test")
            manifest_path = (
                Path(temporary_directory)
                / "Runner.app"
                / "QWQNativeRuntime.plist"
            )
            with manifest_path.open("rb") as stream:
                manifest = plistlib.load(stream)
            self.assertNotIn("contentBindingState", manifest)
            self.assertNotIn("contentReleaseId", manifest)
            self.assertNotIn("contentManifestDigest", manifest)
            self.assertNotIn("contentReadinessReceiptDigest", manifest)
            self.assertNotIn(
                "CONTENT_BINDING_STATE",
                manifest["runtimeDefines"],
            )
            self.assertEqual(
                manifest["launchPolicy"],
                handoff["launchPolicy"],
            )

    def test_patrol_handoff_preserves_canonical_test_bundle_entrypoint(self) -> None:
        handoff = _bound_test_live_handoff()
        patrol_entrypoint = (
            APP_DIR / "test/user_acceptance/patrol/test_bundle.dart"
        ).resolve()
        with tempfile.TemporaryDirectory() as temporary_directory:
            env = dict(os.environ)
            env["QWQ_IOS_STACKCTL_PYTHON"] = str(self.runtime_python)
            env["QWQ_LAUNCH_HANDOFF_JSON"] = json.dumps(handoff)
            env["DART_DEFINES"] = _encode_defines(
                {
                    **handoff["dartDefines"],
                    "RUN_PATROL_ACCEPTANCE": "true",
                }
            )
            env["FLUTTER_TARGET"] = str(patrol_entrypoint)
            env["TARGET_BUILD_DIR"] = temporary_directory
            env["UNLOCALIZED_RESOURCES_FOLDER_PATH"] = "Runner.app"
            result = subprocess.run(
                ["bash", str(SCRIPT)],
                cwd=APP_DIR,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            target_export = next(
                line
                for line in result.stdout.splitlines()
                if line.startswith("export FLUTTER_TARGET=")
            )
            target_assignment = shlex.split(
                target_export.removeprefix("export ")
            )[0]
            self.assertEqual(
                target_assignment.split("=", 1)[1],
                str(patrol_entrypoint),
            )
            manifest_path = (
                Path(temporary_directory)
                / "Runner.app"
                / "QWQNativeRuntime.plist"
            )
            with manifest_path.open("rb") as stream:
                manifest = plistlib.load(stream)
            self.assertEqual(
                manifest["entrypoint"],
                "test/user_acceptance/patrol/test_bundle.dart",
            )

    def test_patrol_handoff_rejects_noncanonical_test_entrypoint(self) -> None:
        handoff = _bound_test_live_handoff()
        env = dict(os.environ)
        env["QWQ_IOS_STACKCTL_PYTHON"] = str(self.runtime_python)
        env["QWQ_LAUNCH_HANDOFF_JSON"] = json.dumps(handoff)
        env["DART_DEFINES"] = _encode_defines(
            {
                **handoff["dartDefines"],
                "RUN_PATROL_ACCEPTANCE": "true",
            }
        )
        env["FLUTTER_TARGET"] = str(
            APP_DIR
            / "test/user_acceptance/service/content_service/content/"
            "feed_delivery_page/feed_load__user_acceptance_test.dart"
        )
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=APP_DIR,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 5)
        self.assertIn(
            "Patrol build must use the canonical",
            result.stderr,
        )

    def test_canonical_handoff_rejects_conflicting_existing_defines(self) -> None:
        handoff = _bound_test_live_handoff()
        poisoned_defines = dict(handoff["dartDefines"])
        # 任何与 canonical handoff 不同的值都必须被拒；此处刻意使用
        # 非环境形状的中性值，冲突检测与具体取值无关。
        poisoned_defines["APP_LAUNCH_POLICY"] = "conflicting_policy"
        env = dict(os.environ)
        env["QWQ_IOS_STACKCTL_PYTHON"] = str(self.runtime_python)
        env["QWQ_LAUNCH_HANDOFF_JSON"] = json.dumps(handoff)
        env["DART_DEFINES"] = _encode_defines(poisoned_defines)
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
            "DART_DEFINES conflict with canonical launcher handoff",
            result.stderr,
        )

    def test_canonical_handoff_rejects_conflicting_environment_identity(self) -> None:
        handoff = _bound_test_live_handoff()
        env = dict(os.environ)
        env["QWQ_IOS_STACKCTL_PYTHON"] = str(self.runtime_python)
        env["QWQ_LAUNCH_HANDOFF_JSON"] = json.dumps(handoff)
        env["QWQ_APP_RUNTIME_ENV"] = "beta"
        env["DART_DEFINES"] = _encode_defines(handoff["dartDefines"])
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
            "QWQ_APP_RUNTIME_ENV conflicts with canonical launcher handoff",
            result.stderr,
        )

    def test_patrol_launch_mode_without_handoff_fails_closed(self) -> None:
        handoff = _bound_test_live_handoff()
        env = dict(os.environ)
        env["QWQ_IOS_STACKCTL_PYTHON"] = str(self.runtime_python)
        env["QWQ_APP_RUNTIME_ENV"] = "alpha"
        env["QWQ_APP_LAUNCH_MODE"] = "environment_patrol_smoke"
        env["QWQ_APP_LAUNCH_POLICY"] = "test_live"
        env["QWQ_LAUNCH_TARGET"] = "alpha-local"
        env["QWQ_DART_DEFINES_DIGEST"] = str(handoff["dartDefinesDigest"])
        env["QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST"] = str(
            handoff["runtimeConfigDigest"]
        )
        env["QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST"] = str(
            handoff["effectiveLaunchManifestDigest"]
        )
        env.pop("QWQ_LAUNCH_HANDOFF_JSON", None)
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
            "environment_patrol_smoke requires QWQ_LAUNCH_HANDOFF_JSON",
            result.stderr,
        )

    def test_invalid_environment_fails_before_flutter_build(self) -> None:
        env = dict(os.environ)
        env["QWQ_APP_RUNTIME_ENV"] = "staging"
        env["QWQ_ENVIRONMENT"] = ""
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


if __name__ == "__main__":
    unittest.main()

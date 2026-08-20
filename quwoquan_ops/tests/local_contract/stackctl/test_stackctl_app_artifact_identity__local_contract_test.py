"""stackctl package --kind app-artifact 的 local_contract 测试。

绑定 deliver-deploy-prod-pipeline DEC-004：canonical App 制品入口显式接收
env/platform/build-mode/distribution-class/device，真 Debug 不进入市场/官网，
store 渠道要求已登记的 Prod 正式 ID，身份推导与 metadata 单轨。
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.commands.package_app_artifact import (
    _CAPSULE_ROOTS,
    _ios_unsigned_release_command,
    _read_android_identity,
    _signing_digest,
    command_package_app_artifact,
)


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "env": "alpha",
        "target": "",
        "app_platform": "android",
        "app_build_mode": "debug",
        "distribution_class": "dev_direct",
        "device": "",
        "artifact_path": "",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _fake_build(**values: object) -> dict[str, str]:
    attempt_dir = Path(str(values["attempt_dir"]))
    artifact = attempt_dir / "app.apk"
    artifact.write_bytes(b"artifact-bytes")
    digest = "sha256:" + hashlib.sha256(b"artifact-bytes").hexdigest()
    return {
        "artifactPath": str(artifact),
        "artifactDigest": digest,
        "launchManifestDigest": "sha256:" + "1" * 64,
        "signingIdentityDigest": "sha256:" + "2" * 64,
        "sourceCapsuleDigest": "sha256:" + "3" * 64,
        "sourceStatusDigest": (
            "sha256:e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        ),
    }


def _snapshot() -> dict[str, object]:
    return {
        "deploymentInputRoots": ["quwoquan_app"],
        "deploymentInputDigest": "sha256:" + "3" * 64,
        "deploymentInputFileCount": 1,
        "sourceRevision": "a" * 40,
        "workspaceStatusDigest": (
            "sha256:e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        ),
        "baselineId": "sha256:" + "5" * 64,
    }


class StackctlAppArtifactIdentityTest(unittest.TestCase):
    def test_aab_identity_and_signature_use_bundle_aware_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "app-release.aab"
            artifact.write_bytes(b"signed-bundle")
            identity_result = mock.Mock(
                returncode=0,
                stdout="com.quwoquan.quwoquan_app\n",
            )
            # keytool 打印的是 32 个冒号分隔的十六进制字节对，fixture 用满长
            # 指纹，避免断言一个长度不合法的摘要。
            signature_result = mock.Mock(
                returncode=0,
                stdout="SHA256: " + ":".join(["AB"] * 32) + "\n",
            )
            with mock.patch(
                "quwoquan_ops.cli.commands.package_app_artifact._bundletool_command",
                return_value=["bundletool"],
            ), mock.patch(
                "quwoquan_ops.cli.commands.package_app_artifact.subprocess.run",
                side_effect=[identity_result, signature_result],
            ) as run, mock.patch(
                "quwoquan_ops.cli.commands.package_app_artifact.shutil.which",
                return_value="/usr/bin/keytool",
            ):
                identity = _read_android_identity(
                    artifact,
                    "com.quwoquan.quwoquan_app",
                )
                signature = _signing_digest("android", artifact)
            self.assertEqual(identity, "com.quwoquan.quwoquan_app")
            self.assertEqual(signature, "sha256:" + "ab" * 32)
            self.assertIn("dump", run.call_args_list[0].args[0])
            self.assertIn("-jarfile", run.call_args_list[1].args[0])

    def test_source_capsule_includes_every_production_local_path_dependency(self) -> None:
        self.assertIn("quwoquan_app", _CAPSULE_ROOTS)
        self.assertIn(
            "quwoquan_service/contracts/runtime_errors/packages/dart/quwoquan_runtime_errors",
            _CAPSULE_ROOTS,
        )
        expected_environment_roots = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "quwoquan_service/services").glob("*/environments")
            if path.is_dir()
        }
        self.assertTrue(expected_environment_roots)
        self.assertTrue(expected_environment_roots.issubset(set(_CAPSULE_ROOTS)))

    def test_ios_release_uses_unsigned_device_aot_and_simulator_release_is_blocked(self) -> None:
        flutter_command = _ios_unsigned_release_command(
            environment="beta",
            entrypoint="lib/main_prod.dart",
            defines=["--dart-define=APP_RUNTIME_ENV=beta"],
        )
        self.assertIn("--release", flutter_command)
        self.assertIn("--no-codesign", flutter_command)
        self.assertIn("--flavor", flutter_command)
        self.assertIn("beta", flutter_command)
        self.assertNotIn("--simulator", flutter_command)
        self.assertNotIn("--debug", flutter_command)
        blocked = command_package_app_artifact(
            _args(
                app_platform="ios",
                app_build_mode="release",
                distribution_class="simulator",
            )
        )
        self.assertEqual(blocked["exitCode"], 2)
        self.assertTrue(
            any(
                "APP.PACKAGE.ios_simulator_debug_only" in item
                for item in blocked["details"]
            )
        )

    def test_prod_ios_release_requires_registered_identity_for_every_distribution(self) -> None:
        result = command_package_app_artifact(
            _args(
                env="prod",
                target="prod-hosted",
                app_platform="ios",
                app_build_mode="release",
                distribution_class="dev_direct",
            )
        )
        self.assertEqual(result["exitCode"], 2)
        self.assertTrue(
            any(
                "APP.PACKAGE.prod_ios_identity_unregistered" in item
                for item in result["details"]
            )
        )

    def test_debug_artifact_is_blocked_from_store_and_official_web(self) -> None:
        for distribution_class in ("store", "official_web", "hosted_web"):
            result = command_package_app_artifact(
                _args(distribution_class=distribution_class)
            )
            self.assertEqual(result["exitCode"], 2, distribution_class)
            self.assertTrue(
                any("buildMode=debug" in item for item in result["details"]),
                result["details"],
            )

    def test_ios_store_requires_registered_production_id(self) -> None:
        result = command_package_app_artifact(
            _args(
                env="prod",
                app_platform="ios",
                app_build_mode="release",
                distribution_class="store",
            )
        )
        self.assertEqual(result["exitCode"], 2)
        self.assertTrue(
            any("registered" in item for item in result["details"]),
            result["details"],
        )
        self.assertFalse(result["decision"]["promotable"])

    def test_android_prod_release_store_is_promotable(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "quwoquan_ops.cli.stackctl.deployment_target_path",
            return_value=Path(directory),
        ) as deployment_path, mock.patch(
            "quwoquan_ops.cli.commands.package_app_artifact._build_from_capsule",
            side_effect=_fake_build,
        ), mock.patch(
            "quwoquan_ops.cli.commands.package_app_artifact.workspace_snapshot",
            side_effect=[_snapshot(), _snapshot()],
        ):
            result = command_package_app_artifact(
                _args(
                    env="prod",
                    target="prod-hosted",
                    app_platform="android",
                    app_build_mode="release",
                    distribution_class="store",
                )
            )
            deployment_path.assert_called_once_with(
                "prod-hosted", "packages", "app"
            )
        self.assertEqual(result["exitCode"], 0, result)
        decision = result["decision"]
        self.assertEqual(decision["applicationId"], "com.quwoquan.quwoquan_app")
        self.assertTrue(decision["promotable"])

    def test_registered_device_distribution_requires_device(self) -> None:
        result = command_package_app_artifact(
            _args(distribution_class="registered_device")
        )
        self.assertEqual(result["exitCode"], 2)
        self.assertTrue(
            any("--device" in item for item in result["details"]),
            result["details"],
        )
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "quwoquan_ops.cli.stackctl.deployment_target_path",
            return_value=Path(directory),
        ), mock.patch(
            "quwoquan_ops.cli.commands.package_app_artifact._build_from_capsule",
            side_effect=_fake_build,
        ), mock.patch(
            "quwoquan_ops.cli.commands.package_app_artifact.workspace_snapshot",
            side_effect=[_snapshot(), _snapshot()],
        ):
            allowed = command_package_app_artifact(
                _args(distribution_class="registered_device", device="udid-1")
            )
        self.assertEqual(allowed["exitCode"], 0, allowed)

    def test_non_prod_debug_identity_is_isolated_and_not_promotable(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "quwoquan_ops.cli.stackctl.deployment_target_path",
            return_value=Path(directory),
        ), mock.patch(
            "quwoquan_ops.cli.commands.package_app_artifact._build_from_capsule",
            side_effect=_fake_build,
        ), mock.patch(
            "quwoquan_ops.cli.commands.package_app_artifact.workspace_snapshot",
            side_effect=[_snapshot(), _snapshot()],
        ):
            result = command_package_app_artifact(_args())
        self.assertEqual(result["exitCode"], 0, result)
        decision = result["decision"]
        self.assertEqual(
            decision["applicationId"], "com.quwoquan.quwoquan_app.alpha.debug"
        )
        self.assertFalse(decision["promotable"])

    def test_artifact_path_bypass_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "app-debug.apk"
            artifact.write_bytes(b"artifact-bytes")
            result = command_package_app_artifact(
                _args(artifact_path=str(artifact))
            )
        self.assertEqual(result["exitCode"], 2)
        self.assertTrue(
            any("--artifact-path bypass is forbidden" in item for item in result["details"])
        )

    def test_source_drift_during_compile_is_a_typed_concurrent_writer_block(self) -> None:
        changed = _snapshot()
        changed["deploymentInputDigest"] = "sha256:" + "9" * 64
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "quwoquan_ops.cli.stackctl.deployment_target_path",
            return_value=Path(directory),
        ), mock.patch(
            "quwoquan_ops.cli.commands.package_app_artifact._build_from_capsule",
            side_effect=_fake_build,
        ), mock.patch(
            "quwoquan_ops.cli.commands.package_app_artifact.workspace_snapshot",
            side_effect=[_snapshot(), changed],
        ):
            result = command_package_app_artifact(_args())
        self.assertEqual(result["exitCode"], 2)
        self.assertIn("WORKSPACE.CONCURRENT_WRITER", result["details"][0])


if __name__ == "__main__":
    unittest.main()

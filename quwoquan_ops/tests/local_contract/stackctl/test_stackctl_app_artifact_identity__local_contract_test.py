"""stackctl package --kind app-artifact 的 local_contract 测试。

绑定 deliver-deploy-prod-pipeline DEC-004：canonical App 制品入口显式接收
env/platform/build-mode/distribution-class/device，真 Debug 不进入市场/官网，
store 渠道要求已登记的 Prod 正式 ID，身份推导与 metadata 单轨。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.commands.package_app_artifact import (
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


class StackctlAppArtifactIdentityTest(unittest.TestCase):
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
        result = command_package_app_artifact(
            _args(
                env="prod",
                app_platform="android",
                app_build_mode="release",
                distribution_class="store",
            )
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
        allowed = command_package_app_artifact(
            _args(distribution_class="registered_device", device="udid-1")
        )
        self.assertEqual(allowed["exitCode"], 0, allowed)

    def test_non_prod_debug_identity_is_isolated_and_not_promotable(self) -> None:
        result = command_package_app_artifact(_args())
        self.assertEqual(result["exitCode"], 0, result)
        decision = result["decision"]
        self.assertEqual(
            decision["applicationId"], "com.quwoquan.quwoquan_app.alpha.debug"
        )
        self.assertFalse(decision["promotable"])

    def test_artifact_binding_writes_identity_decision_with_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "app-debug.apk"
            artifact.write_bytes(b"artifact-bytes")
            package_dir = root / "packages" / "app"
            with mock.patch(
                "quwoquan_ops.cli.stackctl.app_deployment_package_dir",
                return_value=package_dir,
            ):
                result = command_package_app_artifact(
                    _args(artifact_path=str(artifact))
                )
            self.assertEqual(result["exitCode"], 0, result)
            payload = json.loads(
                (package_dir / "app_artifact_identity.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(payload["schema"], "app-artifact-identity-decision")
        self.assertRegex(payload["artifactDigest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            payload["applicationId"], "com.quwoquan.quwoquan_app.alpha.debug"
        )


if __name__ == "__main__":
    unittest.main()

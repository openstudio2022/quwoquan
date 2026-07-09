from __future__ import annotations

import argparse
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke


class EnvironmentPatrolSmokeTest(unittest.TestCase):
    def _args(self, **overrides: object) -> argparse.Namespace:
        values = {
            "env_name": "gamma-local",
            "runtime_env": "gamma",
            "api_contract_env": "gamma",
            "data_source": "remote",
            "gateway_base_url": "https://gamma-api.quwoquan-env.test:19000",
            "product_ops_base_url": "https://gamma-product-ops.quwoquan-env.test:19010",
            "media_base_url": "https://gamma-image.quwoquan-env.test:19100",
            "test_auth_token": "local-gamma-token",
            "current_user_id": "",
            "target": "test/patrol/environment/basic_viability_test.dart",
            "platform": "all",
            "device_id": [],
            "dry_run": False,
            "timeout_seconds": 1200,
            "report": ".qwq_output/runs/device-matrix/environment-smoke/report.json",
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_effective_base_urls_rewrite_local_ios_simulator(self) -> None:
        args = self._args()
        device = {"targetPlatform": "ios", "emulator": True}

        actual = smoke._effective_base_urls_for_device(args, device)

        self.assertEqual(actual["gatewayBaseUrl"], "https://gamma-api.localhost:19000")
        self.assertEqual(actual["productOpsBaseUrl"], "https://gamma-product-ops.localhost:19010")
        self.assertEqual(actual["mediaBaseUrl"], "https://gamma-image.localhost:19100")

    def test_effective_base_urls_keep_public_for_hosted_target(self) -> None:
        args = self._args(
            env_name="prod-hosted",
            runtime_env="prod",
            api_contract_env="prod",
            gateway_base_url="https://118.31.239.122:19000",
            product_ops_base_url="https://118.31.239.122:19010",
            media_base_url="https://118.31.239.122:19100",
        )
        device = {"targetPlatform": "ios", "emulator": True}

        actual = smoke._effective_base_urls_for_device(args, device)

        self.assertEqual(actual["gatewayBaseUrl"], "https://118.31.239.122:19000")
        self.assertEqual(actual["productOpsBaseUrl"], "https://118.31.239.122:19010")
        self.assertEqual(actual["mediaBaseUrl"], "https://118.31.239.122:19100")

    def test_resolved_current_user_id_defaults_fixture_for_local_target(self) -> None:
        args = self._args(current_user_id="")

        self.assertEqual(smoke._resolved_current_user_id(args), "fixture_user_current")

    def test_patrol_command_includes_localhost_and_current_user(self) -> None:
        args = self._args()
        device = {"id": "sim-1", "targetPlatform": "ios", "emulator": True}

        command = smoke.patrol_command(device, args, patrol_executable="patrol")
        joined = "\n".join(command)

        self.assertIn("--dart-define=CLOUD_GATEWAY_BASE_URL=https://gamma-api.localhost:19000", joined)
        self.assertIn("--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL=https://gamma-product-ops.localhost:19010", joined)
        self.assertIn("--dart-define=MEDIA_IMAGE_CDN_BASE_URL=https://gamma-image.localhost:19100", joined)
        self.assertIn("--dart-define=APP_CURRENT_USER_ID=fixture_user_current", joined)

    def test_device_command_env_injects_android_ca_for_local_target(self) -> None:
        args = self._args()
        device = {"targetPlatform": "android-arm64", "emulator": True}
        fake_cert = Path("/tmp/local-root.crt")

        with mock.patch.object(smoke, "_local_debug_ca_path", return_value=fake_cert):
            env = smoke._device_command_env(args, device)

        self.assertEqual(env[smoke.ANDROID_LOCAL_DEBUG_CA_ENV], str(fake_cert))
        self.assertEqual(env[smoke.ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV], "1")

    def test_device_command_env_skips_android_ca_for_ios(self) -> None:
        args = self._args()
        device = {"targetPlatform": "ios", "emulator": True}

        with mock.patch.object(smoke, "_local_debug_ca_path", return_value=Path("/tmp/local-root.crt")):
            env = smoke._device_command_env(args, device)

        self.assertEqual(env.get(smoke.ANDROID_LOCAL_DEBUG_CA_ENV, ""), os.environ.get(smoke.ANDROID_LOCAL_DEBUG_CA_ENV, ""))


if __name__ == "__main__":
    unittest.main()

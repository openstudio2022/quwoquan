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
from quwoquan_ops.cli import stackctl


class EnvironmentPatrolSmokeTest(unittest.TestCase):
    def _args(self, **overrides: object) -> argparse.Namespace:
        values = {
            "env_name": "local-gamma",
            "runtime_env": "gamma",
            "api_contract_env": "gamma",
            "data_source": "remote",
            "gateway_base_url": "https://gamma-api.quwoquan-env.test:19000",
            "product_ops_base_url": "https://gamma-product-ops.quwoquan-env.test:19010",
            "media_base_url": "https://gamma-image.quwoquan-env.test:19100",
            "test_auth_token": "local-gamma-token",
            "test_refresh_token": "local-gamma-refresh",
            "release_uat_cases": "",
            "release_uat_cases_b64": "",
            "current_owner_id": "fixture_owner_current",
            "current_sub_account_id": "fixture_user_current",
            "target": "test/user_acceptance/patrol/environment/basic_viability__user_acceptance_test.dart",
            "platform": "all",
            "device_id": [],
            "dry_run": False,
            "timeout_seconds": 1200,
            "report": ".qwq_output/env/repo/runs/device-matrix/environment-smoke/report.json",
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

    def test_prepare_gamma_session_uses_real_anonymous_login_actor(self) -> None:
        args = self._args(
            test_auth_token="",
            test_refresh_token="",
            current_owner_id="",
            current_sub_account_id="",
        )
        source = smoke._prepare_execution_session(args)

        self.assertEqual(source, "gamma_local_anonymous_runtime")
        self.assertEqual(args.test_auth_token, "")
        self.assertEqual(args.test_refresh_token, "")
        self.assertEqual(smoke._resolved_owner_id(args), "")
        self.assertEqual(smoke._resolved_sub_account_id(args), "")

    def test_local_gamma_alias_resolves_to_concrete_tls_target(self) -> None:
        self.assertTrue(smoke._is_local_target("local-gamma"))
        self.assertEqual(
            smoke._local_target_for_environment_alias("local-gamma"),
            "gamma-local",
        )

    def test_patrol_command_includes_localhost_and_current_user(self) -> None:
        args = self._args()
        device = {
            "id": "sim-1",
            "targetPlatform": "ios",
            "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
            "emulator": True,
        }

        command = smoke.patrol_command(
            device,
            args,
            "patrol",
            dart_define_file=Path("/tmp/patrol-secrets.json"),
        )
        joined = "\n".join(command)

        self.assertIn("--dart-define=CLOUD_GATEWAY_BASE_URL=https://gamma-api.localhost:19000", joined)
        self.assertIn("--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL=https://gamma-product-ops.localhost:19010", joined)
        self.assertIn("--dart-define=MEDIA_IMAGE_CDN_BASE_URL=https://gamma-image.localhost:19100", joined)
        self.assertIn("--dart-define=QWQ_PATROL_SESSION_MODE=local_gamma_anonymous", joined)
        self.assertNotIn("--dart-define=APP_CURRENT_OWNER_ID=", joined)
        self.assertNotIn("--dart-define=APP_CURRENT_SUB_ACCOUNT_ID=", joined)
        self.assertNotIn("--dart-define-from-file=", joined)
        self.assertNotIn("local-gamma-token", joined)
        self.assertNotIn("local-gamma-refresh", joined)
        self.assertIn("--ios=17.2", command)

    def test_ios_auto_selection_uses_highest_xcode_compatible_runtime(self) -> None:
        devices = [
            {
                "id": "ios-17",
                "name": "iPhone 15",
                "targetPlatform": "ios",
                "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                "emulator": True,
            },
            {
                "id": "ios-26-3",
                "name": "iPhone 17",
                "targetPlatform": "ios",
                "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-26-3",
                "emulator": True,
            },
        ]

        selected = smoke._select_compatible_ios_devices(
            devices,
            simulator_sdk_version=(26, 2),
        )

        self.assertEqual([device["id"] for device in selected], ["ios-17"])

    def test_ios_auto_selection_rejects_duplicate_patrol_destination(self) -> None:
        devices = [
            {
                "id": "ios-a",
                "name": "iPhone 15",
                "targetPlatform": "ios",
                "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                "emulator": True,
            },
            {
                "id": "ios-b",
                "name": "iPhone 15",
                "targetPlatform": "ios",
                "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                "emulator": True,
            },
        ]

        with self.assertRaisesRegex(RuntimeError, "duplicate iOS devices"):
            smoke._select_compatible_ios_devices(
                devices,
                simulator_sdk_version=(26, 2),
            )

    def test_patrol_command_includes_release_bound_uat_cases_without_exposing_auth_token(self) -> None:
        args = self._args(
            release_uat_cases_b64="eyJjYXNlcyI6W119",
            test_auth_token="",
            test_refresh_token="",
            current_owner_id="",
            current_sub_account_id="",
        )
        device = {"id": "android-1", "targetPlatform": "android-arm64", "emulator": True}

        command = smoke.patrol_command(
            device,
            args,
            "patrol",
            dart_define_file=Path("/tmp/patrol-secrets.json"),
        )

        self.assertIn("--dart-define=QWQ_TWO_PROVINCE_UAT_CASES_B64=eyJjYXNlcyI6W119", command)
        self.assertNotIn("local-gamma-token", smoke._redact_command(command))
        self.assertNotIn("local-gamma-refresh", smoke._redact_command(command))

    def test_patrol_secret_define_file_is_private_and_ephemeral_ready(self) -> None:
        args = self._args(
            env_name="beta-local",
            runtime_env="beta",
            test_auth_token="remote-access",
            test_refresh_token="remote-refresh",
        )

        path = smoke._create_patrol_secret_define_file(args)
        try:
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                '{"TEST_AUTH_TOKEN": "remote-access", '
                '"TEST_REFRESH_TOKEN": "remote-refresh"}\n',
            )
        finally:
            path.unlink(missing_ok=True)

    def test_patrol_output_redacts_access_and_refresh_secrets(self) -> None:
        output = "argv access-secret refresh-secret\nrequest failed"

        self.assertEqual(
            smoke._redact_text(output, ("access-secret", "refresh-secret")),
            "argv <redacted> <redacted>\nrequest failed",
        )

    def test_remote_session_missing_actor_is_gate_blocked(self) -> None:
        args = self._args(
            env_name="beta-local",
            runtime_env="beta",
            test_auth_token="remote-access",
            test_refresh_token="remote-refresh",
            current_owner_id="",
            current_sub_account_id="",
        )

        self.assertEqual(
            smoke._missing_required_args(args),
            ["current_owner_id", "current_sub_account_id"],
        )

    def test_local_gamma_rejects_host_injected_session(self) -> None:
        args = self._args(test_auth_token="host-token")

        with self.assertRaisesRegex(ValueError, "device-runtime anonymous login"):
            smoke._prepare_execution_session(args)

    def test_output_evidence_ref_removes_repo_output_prefix(self) -> None:
        path = ROOT / ".qwq_output/env/gamma/runs/data-release/release/apply/app_uat_cases.json"

        self.assertEqual(
            smoke._output_evidence_ref(path),
            "env/gamma/runs/data-release/release/apply/app_uat_cases.json",
        )

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

    def test_stackctl_gamma_smoke_never_installs_a_fake_token(self) -> None:
        target = {
            "env": "gamma",
            "publicBases": {
                "api": "https://gamma-api.quwoquan-env.test:19000",
                "productOps": "https://gamma-product-ops.quwoquan-env.test:19010",
                "mediaImage": "https://gamma-image.quwoquan-env.test:19100",
            },
        }
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value=target),
            mock.patch.object(stackctl, "_resolve_test_auth_token", return_value=""),
            mock.patch.dict(
                os.environ,
                {
                    "TEST_REFRESH_TOKEN": "host-refresh-must-not-leak",
                    "APP_CURRENT_OWNER_ID": "host-owner-must-not-leak",
                    "APP_CURRENT_SUB_ACCOUNT_ID": "host-persona-must-not-leak",
                },
                clear=False,
            ),
        ):
            command = stackctl._environment_page_smoke_tier_command(
                "gamma",
                "gamma-local",
                Path("/tmp/gamma-report"),
            )

        self.assertIsNotNone(command)
        argv = command["argv"]
        self.assertNotIn("--test-auth-token", argv)
        self.assertNotIn("local-gamma-local-token", "\n".join(argv))
        self.assertEqual(argv[argv.index("--data-source") + 1], "remote")
        self.assertEqual(argv[argv.index("--env-name") + 1], "local-gamma")
        self.assertNotIn("env", command)

    def test_gamma_runtime_readiness_only_requires_declared_gamma_planes(self) -> None:
        roles = stackctl._expected_local_roles("gamma-local")

        self.assertIn("api-edge", roles)
        self.assertIn("product-ops-edge", roles)
        self.assertIn("media-edge", roles)
        self.assertNotIn("platform-ops-edge", roles)
        self.assertNotIn("ops-portal", roles)

    def test_stackctl_passes_explicit_remote_token_only_via_process_environment(self) -> None:
        target = {
            "env": "beta",
            "publicBases": {
                "api": "https://beta-api.quwoquan-env.test:18000",
                "productOps": "https://beta-product-ops.quwoquan-env.test:18010",
                "mediaImage": "https://beta-image.quwoquan-env.test:18100",
            },
        }
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value=target),
            mock.patch.object(stackctl, "_resolve_test_auth_token", return_value="secret-access"),
            mock.patch.dict(
                os.environ,
                {
                    "TEST_REFRESH_TOKEN": "secret-refresh",
                    "APP_CURRENT_OWNER_ID": "owner-real",
                    "APP_CURRENT_SUB_ACCOUNT_ID": "persona-real",
                },
                clear=False,
            ),
        ):
            command = stackctl._environment_page_smoke_tier_command(
                "beta",
                "beta-local",
                Path("/tmp/beta-report"),
            )

        self.assertIsNotNone(command)
        self.assertNotIn("secret-access", "\n".join(command["argv"]))
        self.assertEqual(command["argv"][command["argv"].index("--env-name") + 1], "beta-local")
        self.assertEqual(
            command["env"],
            {
                "TEST_AUTH_TOKEN": "secret-access",
                "TEST_REFRESH_TOKEN": "secret-refresh",
                "APP_CURRENT_OWNER_ID": "owner-real",
                "APP_CURRENT_SUB_ACCOUNT_ID": "persona-real",
            },
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.device_matrix import android as android_device
from quwoquan_ops.ci.device_matrix import evidence as device_evidence
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke
from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import flutter_android_device_proxy as flutter_proxy
from quwoquan_ops.cli.lib.content_release_readiness import VerificationProfile


class EnvironmentPatrolSmokeTest(unittest.TestCase):
    def _args(self, **overrides: object) -> argparse.Namespace:
        values = {
            "env_name": "local-gamma",
            "runtime_env": "gamma",
            "api_contract_env": "gamma",
            "data_source": "remote",
            "gateway_base_url": "https://gamma-api.quwoquan-env.test:19000",
            "product_ops_base_url": "https://gamma-product-ops.quwoquan-env.test:19010",
            "media_avatar_base_url": "https://gamma-avatar.quwoquan-env.test:19100",
            "media_image_base_url": "https://gamma-image.quwoquan-env.test:19100",
            "media_video_base_url": "https://gamma-video.quwoquan-env.test:19100",
            "media_upload_base_url": "https://gamma-upload.quwoquan-env.test:19130",
            "video_playback_canary_work_id": "fixture_video_001",
            "test_auth_token": "local-gamma-token",
            "test_refresh_token": "local-gamma-refresh",
            "release_uat_cases": "",
            "release_uat_cases_b64": "",
            "current_owner_id": "fixture_owner_current",
            "current_sub_account_id": "fixture_user_current",
            "target": (
                "test/user_acceptance/patrol/environment/"
                "video_playback_canary__user_acceptance_test.dart"
            ),
            "platform": "all",
            "device_id": [],
            "dry_run": False,
            "timeout_seconds": 1200,
            "report": ".qwq_output/env/repo/runs/device-matrix/environment-smoke/report.json",
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_default_target_is_the_video_playback_canary(self) -> None:
        self.assertEqual(
            smoke.DEFAULT_TARGET,
            (
                "test/user_acceptance/patrol/environment/"
                "video_playback_canary__user_acceptance_test.dart"
            ),
        )

    def test_native_video_evidence_only_accepts_patrol_log_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            patrol_log = Path(temporary_dir) / "patrol.log"
            patrol_log.write_text(
                "\n".join(
                    [
                        "controller ready",
                        (
                            "QWQ_VIDEO_PLAYBACK_EVIDENCE "
                            '{"nativeFirstFrame":true,"nativeSeekSettled":true}'
                        ),
                    ],
                ),
                encoding="utf-8",
            )

            evidence = smoke._read_video_playback_evidence(patrol_log)

        self.assertEqual(
            evidence,
            {"nativeFirstFrame": True, "nativeSeekSettled": True},
        )

    def test_alpha_playback_canary_uses_bundled_mock_video_not_remote_fixture_id(self) -> None:
        topology = stackctl.load_environment_topology()
        target = stackctl.get_target(topology, "alpha-local")
        canary = target["playbackCanary"]

        self.assertEqual(canary["workId"], "v1")
        self.assertEqual(canary["source"], "alpha-bundled-contract")

    def test_effective_base_urls_rewrite_local_ios_simulator(self) -> None:
        args = self._args()
        device = {"targetPlatform": "ios", "emulator": True}

        actual = smoke._effective_base_urls_for_device(args, device)

        self.assertEqual(actual["gatewayBaseUrl"], "https://gamma-api.localhost:19000")
        self.assertEqual(actual["productOpsBaseUrl"], "https://gamma-product-ops.localhost:19010")
        self.assertEqual(actual["mediaAvatarBaseUrl"], "https://gamma-avatar.localhost:19100")
        self.assertEqual(actual["mediaImageBaseUrl"], "https://gamma-image.localhost:19100")
        self.assertEqual(actual["mediaVideoBaseUrl"], "https://gamma-video.localhost:19100")
        self.assertEqual(actual["mediaUploadBaseUrl"], "https://gamma-upload.localhost:19130")
        self.assertNotIn("mediaBaseUrl", actual)

    def test_effective_base_urls_use_exact_localhost_for_android_native_player(self) -> None:
        args = self._args()
        device = {"targetPlatform": "android-arm64", "emulator": True}

        actual = smoke._effective_base_urls_for_device(args, device)

        self.assertEqual(actual["gatewayBaseUrl"], "https://localhost:19000")
        self.assertEqual(actual["productOpsBaseUrl"], "https://localhost:19010")
        self.assertEqual(actual["mediaAvatarBaseUrl"], "https://localhost:19100")
        self.assertEqual(actual["mediaImageBaseUrl"], "https://localhost:19100")
        self.assertEqual(actual["mediaVideoBaseUrl"], "https://localhost:19100")
        self.assertEqual(actual["mediaUploadBaseUrl"], "https://localhost:19130")

    def test_ios_build_preserves_only_authorized_local_transport_authority(self) -> None:
        def resolved_gateway(supplied_gateway: str) -> str:
            entries = {
                "APP_RUNTIME_ENV": "gamma",
                "CLOUD_GATEWAY_BASE_URL": supplied_gateway,
            }
            encoded = ",".join(
                base64.b64encode(f"{key}={value}".encode("utf-8")).decode("ascii")
                for key, value in entries.items()
            )
            environment = {
                **os.environ,
                "DART_DEFINES": encoded,
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            result = subprocess.run(
                [
                    "bash",
                    str(
                        ROOT
                        / "quwoquan_app"
                        / "scripts"
                        / "ios"
                        / "prepare_dart_defines.sh"
                    ),
                ],
                cwd=ROOT / "quwoquan_app",
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            export = next(
                line
                for line in result.stdout.splitlines()
                if line.startswith("export DART_DEFINES=")
            )
            merged = {
                key: value
                for key, value in (
                    base64.b64decode(item).decode("utf-8").split("=", 1)
                    for item in export.split("=", 1)[1].split(",")
                )
            }
            return merged["CLOUD_GATEWAY_BASE_URL"]

        self.assertEqual(
            resolved_gateway("https://gamma-api.localhost:19000"),
            "https://gamma-api.localhost:19000",
        )
        self.assertEqual(
            resolved_gateway("https://untrusted.localhost:19000"),
            "https://gamma-api.quwoquan-env.test:19000",
        )

    def test_effective_base_urls_keep_public_for_hosted_target(self) -> None:
        args = self._args(
            env_name="prod-hosted",
            runtime_env="prod",
            api_contract_env="prod",
            gateway_base_url="https://api.quwoquan.com",
            product_ops_base_url="https://ops.quwoquan.com",
            media_avatar_base_url="https://cdn.quwoquan.com",
            media_image_base_url="https://cdn.quwoquan.com",
            media_video_base_url="https://cdn.quwoquan.com",
            media_upload_base_url="https://upload.quwoquan.com",
        )
        device = {"targetPlatform": "ios", "emulator": True}

        actual = smoke._effective_base_urls_for_device(args, device)

        self.assertEqual(actual["gatewayBaseUrl"], "https://api.quwoquan.com")
        self.assertEqual(actual["productOpsBaseUrl"], "https://ops.quwoquan.com")
        self.assertEqual(actual["mediaImageBaseUrl"], "https://cdn.quwoquan.com")
        self.assertEqual(actual["mediaUploadBaseUrl"], "https://upload.quwoquan.com")
        self.assertNotIn("mediaBaseUrl", actual)

    def test_gamma_public_video_canary_allows_anonymous_read_only_session(
        self,
    ) -> None:
        args = self._args(
            test_auth_token="",
            test_refresh_token="",
            current_owner_id="",
            current_sub_account_id="",
        )
        source = smoke._prepare_execution_session(args)

        self.assertEqual(source, "gamma_local_anonymous_public_video")
        self.assertEqual(args.test_auth_token, "")
        self.assertEqual(args.test_refresh_token, "")
        self.assertEqual(smoke._resolved_owner_id(args), "")
        self.assertEqual(smoke._resolved_sub_account_id(args), "")
        self.assertEqual(smoke._missing_required_args(args), [])
        command = smoke.patrol_command(
            {
                "id": "android-gamma",
                "targetPlatform": "android-arm64",
                "emulator": True,
            },
            args,
            "patrol",
            dart_define_file=None,
        )
        self.assertIn(
            "--dart-define=QWQ_PATROL_SESSION_MODE="
            "gamma_local_anonymous_public_video",
            command,
        )
        self.assertIn(
            "--dart-define=REQUIRE_NATIVE_VIDEO_PLAYBACK_SIGNALS=true",
            command,
        )
        self.assertNotIn("--dart-define-from-file=", command)

    def test_beta_public_video_canary_allows_anonymous_read_only_session(self) -> None:
        args = self._args(
            env_name="beta-local",
            runtime_env="beta",
            api_contract_env="beta",
            data_source="remote",
            gateway_base_url="https://beta-api.quwoquan-env.test:18000",
            product_ops_base_url="https://beta-product-ops.quwoquan-env.test:18010",
            media_avatar_base_url="https://beta-avatar.quwoquan-env.test:18100",
            media_image_base_url="https://beta-image.quwoquan-env.test:18100",
            media_video_base_url="https://beta-video.quwoquan-env.test:18100",
            media_upload_base_url="https://beta-upload.quwoquan-env.test:18100",
            test_auth_token="",
            test_refresh_token="",
            current_owner_id="",
            current_sub_account_id="",
        )

        source = smoke._prepare_execution_session(args)

        self.assertEqual(source, "beta_local_anonymous_public_video")
        self.assertEqual(smoke._missing_required_args(args), [])
        command = smoke.patrol_command(
            {"id": "android-beta", "targetPlatform": "android-arm64", "emulator": True},
            args,
            "patrol",
            dart_define_file=None,
        )
        self.assertIn(
            "--dart-define=QWQ_PATROL_SESSION_MODE="
            "beta_local_anonymous_public_video",
            command,
        )
        self.assertNotIn("--dart-define-from-file=", command)

    def test_local_gamma_alias_resolves_to_concrete_tls_target(self) -> None:
        self.assertTrue(smoke._is_local_target("local-gamma"))
        self.assertEqual(
            smoke._local_target_for_environment_alias("local-gamma"),
            "gamma-local",
        )

    def test_stackctl_resolves_every_local_public_target_to_loopback(self) -> None:
        topology = stackctl.load_environment_topology()
        for target_name in ("alpha-local", "beta-local", "gamma-local", "prod-sim"):
            target = stackctl.get_target(topology, target_name)
            media_video_url = target["publicBases"]["mediaVideo"]
            self.assertEqual(
                stackctl._local_public_connect_host(
                    topology,
                    target_name,
                    media_video_url,
                ),
                "127.0.0.1",
            )

        hosted = stackctl.get_target(topology, "prod-hosted")
        self.assertEqual(
            stackctl._local_public_connect_host(
                topology,
                "prod-hosted",
                hosted["publicBases"]["mediaVideo"],
            ),
            "",
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
        self.assertIn("--dart-define=MEDIA_AVATAR_CDN_BASE_URL=https://gamma-avatar.localhost:19100", joined)
        self.assertIn("--dart-define=MEDIA_IMAGE_CDN_BASE_URL=https://gamma-image.localhost:19100", joined)
        self.assertIn("--dart-define=MEDIA_VIDEO_CDN_BASE_URL=https://gamma-video.localhost:19100", joined)
        self.assertIn("--dart-define=MEDIA_UPLOAD_BASE_URL=https://gamma-upload.localhost:19130", joined)
        self.assertIn(
            "--dart-define=VIDEO_PLAYBACK_CANARY_WORK_ID=fixture_video_001",
            joined,
        )
        self.assertIn(
            "--dart-define=REQUIRE_NATIVE_VIDEO_PLAYBACK_SIGNALS=false",
            joined,
        )
        self.assertIn("--dart-define=QWQ_PATROL_SESSION_MODE=local_gamma_anonymous", joined)
        self.assertNotIn("--dart-define=APP_CURRENT_OWNER_ID=", joined)
        self.assertNotIn("--dart-define=APP_CURRENT_SUB_ACCOUNT_ID=", joined)
        self.assertNotIn("--dart-define-from-file=", joined)
        self.assertNotIn("local-gamma-token", joined)
        self.assertNotIn("local-gamma-refresh", joined)
        self.assertNotIn("--ios=17.2", command)

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

    @mock.patch.object(smoke, "resolve_android_debug_bridge", return_value="/sdk/adb")
    @mock.patch.object(smoke.subprocess, "run")
    def test_explicit_android_device_discovery_uses_adb_without_flutter_lock(
        self,
        run: mock.Mock,
        _resolve_adb: mock.Mock,
    ) -> None:
        run.return_value = subprocess.CompletedProcess(
            [],
            0,
            "List of devices attached\n"
            "emulator-5554 device product:sdk model:Pixel_API_31 device:emulator64_arm64\n",
            "",
        )

        devices = smoke.discover_devices("android", ["emulator-5554"])

        self.assertEqual(devices[0]["id"], "emulator-5554")
        self.assertEqual(devices[0]["name"], "Pixel_API_31")
        self.assertEqual(devices[0]["targetPlatform"], "android-arm64")
        run.assert_called_once_with(
            ["/sdk/adb", "devices", "-l"],
            text=True,
            capture_output=True,
            check=False,
        )

    @mock.patch.object(smoke.shutil, "which", return_value="/sdk/flutter")
    @mock.patch.object(smoke, "resolve_android_debug_bridge", return_value="/sdk/adb")
    def test_android_patrol_uses_adb_inventory_for_flutter_device_discovery(
        self,
        _resolve_adb: mock.Mock,
        _which: mock.Mock,
    ) -> None:
        args = self._args()
        device = {
            "id": "emulator-5554",
            "name": "Pixel_API_31",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }

        env = smoke._device_command_env(args, device)
        inventory = json.loads(env[flutter_proxy.ANDROID_DEVICE_INVENTORY_ENV])

        self.assertEqual(inventory, [{**device, "isSupported": True}])
        self.assertEqual(env[flutter_proxy.REAL_FLUTTER_ENV], "/sdk/flutter")
        self.assertIn(
            str(smoke.ANDROID_DEVICE_PROXY),
            env[smoke.PATROL_FLUTTER_COMMAND_ENV],
        )

    def test_flutter_proxy_returns_only_validated_android_inventory(self) -> None:
        inventory = [
            {
                "id": "emulator-5554",
                "name": "Pixel_API_31",
                "targetPlatform": "android-arm64",
                "emulator": True,
                "isSupported": True,
            }
        ]
        with tempfile.SpooledTemporaryFile(mode="w+") as stdout:
            with mock.patch.dict(
                os.environ,
                {flutter_proxy.ANDROID_DEVICE_INVENTORY_ENV: json.dumps(inventory)},
                clear=False,
            ), mock.patch.object(flutter_proxy.sys, "stdout", stdout):
                self.assertEqual(flutter_proxy.main(["devices", "--machine"]), 0)
            stdout.seek(0)
            self.assertEqual(json.load(stdout), inventory)

    @mock.patch.object(flutter_proxy.subprocess, "run")
    @mock.patch.object(flutter_proxy.shutil, "which", return_value="/jdk/bin/javac")
    def test_flutter_proxy_checks_real_java_without_global_flutter_doctor(
        self,
        _which: mock.Mock,
        run: mock.Mock,
    ) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, "javac 17.0.12\n", "")
        with tempfile.SpooledTemporaryFile(mode="w+") as stdout:
            with mock.patch.object(flutter_proxy.sys, "stdout", stdout):
                self.assertEqual(flutter_proxy.main(["doctor", "--verbose"]), 0)
            stdout.seek(0)
            self.assertIn("Java version 17.0.12", stdout.read())
        run.assert_called_once_with(
            ["/jdk/bin/javac", "--version"],
            text=True,
            capture_output=True,
            check=False,
        )

    @mock.patch.object(smoke, "_terminate_process_group", return_value="stopped")
    @mock.patch.object(smoke.subprocess, "Popen")
    def test_run_command_cleans_process_group_on_interrupt(
        self,
        popen: mock.Mock,
        terminate: mock.Mock,
    ) -> None:
        process = mock.Mock(pid=4321)
        process.communicate.side_effect = KeyboardInterrupt
        popen.return_value = process

        with self.assertRaises(KeyboardInterrupt):
            smoke.run_command(["patrol", "test"], cwd=ROOT)

        terminate.assert_called_once_with(process)

    @mock.patch.object(smoke.subprocess, "run")
    def test_release_bound_ios_uat_resets_app_and_test_runner_state(
        self,
        run: mock.Mock,
    ) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        args = self._args(
            release_uat_cases="/tmp/homepage_verification_cases.json"
        )
        device = {
            "id": "ios-release-uat",
            "targetPlatform": "ios",
            "emulator": True,
        }

        result = smoke._reset_release_uat_device_state(args, device)

        self.assertEqual(result["status"], "reset")
        self.assertEqual(
            [row["bundleId"] for row in result["applications"]],
            list(smoke.IOS_RELEASE_UAT_BUNDLE_IDS),
        )
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["xcrun", "simctl", "uninstall", "ios-release-uat", bundle_id]
                for bundle_id in smoke.IOS_RELEASE_UAT_BUNDLE_IDS
            ],
        )

    @mock.patch.object(smoke.subprocess, "run")
    def test_non_release_patrol_does_not_reset_app_state(
        self,
        run: mock.Mock,
    ) -> None:
        result = smoke._reset_release_uat_device_state(
            self._args(release_uat_cases=""),
            {"id": "ios-smoke", "targetPlatform": "ios", "emulator": True},
        )

        self.assertEqual(
            result,
            {"status": "skipped", "reason": "not-release-bound"},
        )
        run.assert_not_called()

    @mock.patch.object(smoke, "resolve_android_debug_bridge", return_value="/sdk/adb")
    @mock.patch.object(smoke.subprocess, "run")
    def test_release_bound_android_uat_treats_uninstalled_app_as_reset(
        self,
        run: mock.Mock,
        _resolve_adb: mock.Mock,
    ) -> None:
        run.return_value = subprocess.CompletedProcess([], 1, "", "")
        args = self._args(
            release_uat_cases="/tmp/homepage_verification_cases.json"
        )
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }

        result = smoke._reset_release_uat_device_state(args, device)

        self.assertTrue(result["applications"][0]["alreadyAbsent"])
        run.assert_called_once_with(
            [
                "/sdk/adb",
                "-s",
                "emulator-5554",
                "shell",
                "pm",
                "path",
                smoke.ANDROID_RELEASE_UAT_PACKAGE,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

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

    def test_release_bound_homepage_uat_does_not_require_video_canary(self) -> None:
        args = self._args(
            target=(
                "test/user_acceptance/patrol/entity/"
                "two_province_homepage__rollout_render__functional__user_acceptance_test.dart"
            ),
            release_uat_cases="/tmp/homepage_verification_cases.json",
            video_playback_canary_work_id="",
        )

        self.assertNotIn(
            "video_playback_canary_work_id",
            smoke._missing_required_args(args),
        )

    def test_local_gamma_rejects_host_injected_session(self) -> None:
        args = self._args(test_auth_token="host-token")

        with self.assertRaisesRegex(ValueError, "device-runtime anonymous login"):
            smoke._prepare_execution_session(args)

    def test_output_evidence_ref_removes_repo_output_prefix(self) -> None:
        path = ROOT / ".qwq_output/env/gamma/runs/data-release/release/apply/homepage_verification_cases.json"

        self.assertEqual(
            smoke._output_evidence_ref(path),
            "env/gamma/runs/data-release/release/apply/homepage_verification_cases.json",
        )

    def test_device_command_env_injects_android_ca_for_local_target(self) -> None:
        args = self._args()
        device = {"targetPlatform": "android-arm64", "emulator": True}
        fake_cert = Path("/tmp/local-root.crt")

        with (
            mock.patch.object(smoke, "_local_debug_ca_path", return_value=fake_cert),
            mock.patch.object(
                smoke,
                "resolve_android_debug_bridge",
                return_value="/sdk/platform-tools/adb",
            ),
        ):
            env = smoke._device_command_env(args, device)

        self.assertEqual(env[smoke.ANDROID_LOCAL_DEBUG_CA_ENV], str(fake_cert))
        self.assertEqual(env[smoke.ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV], "1")
        self.assertEqual(
            env["PATH"].split(os.pathsep)[0],
            "/sdk/platform-tools",
        )

    def test_device_command_env_injects_selected_ios_simulator_udid(self) -> None:
        args = self._args()
        device = {
            "id": "selected-ios-simulator",
            "targetPlatform": "ios",
            "emulator": True,
        }

        with mock.patch.object(smoke, "_local_debug_ca_path", return_value=Path("/tmp/local-root.crt")):
            env = smoke._device_command_env(args, device)

        self.assertEqual(env.get(smoke.ANDROID_LOCAL_DEBUG_CA_ENV, ""), os.environ.get(smoke.ANDROID_LOCAL_DEBUG_CA_ENV, ""))
        self.assertEqual(env["QWQ_IOS_SIMULATOR_UDID"], "selected-ios-simulator")

    def test_device_command_env_blocks_local_ios_simulator_without_id(self) -> None:
        args = self._args()

        with self.assertRaisesRegex(RuntimeError, "explicit device id"):
            smoke._device_command_env(
                args,
                {"targetPlatform": "ios", "emulator": True},
            )

    def test_android_debug_bridge_resolves_configured_sdk_when_adb_is_not_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            sdk_root = Path(temporary_dir)
            adb = sdk_root / "platform-tools" / "adb"
            adb.parent.mkdir(parents=True)
            adb.write_text("#!/bin/sh\n", encoding="utf-8")
            adb.chmod(0o755)

            with mock.patch.object(android_device.shutil, "which", return_value=None):
                resolved = android_device.resolve_android_debug_bridge(
                    environ={"ANDROID_SDK_ROOT": str(sdk_root)},
                    home_dir=Path("/no-sdk-home"),
                )

        self.assertEqual(resolved, str(adb))

    def test_android_evidence_capture_uses_resolved_sdk_adb(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            screenshot = Path(temporary_dir) / "capture.png"
            device = {"id": "emulator-5554", "targetPlatform": "android-arm64"}
            with (
                mock.patch.object(
                    device_evidence,
                    "resolve_android_debug_bridge",
                    return_value="/sdk/platform-tools/adb",
                ),
                mock.patch.object(
                    device_evidence.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        ["/sdk/platform-tools/adb"], 0, stdout=b"png", stderr=b"",
                    ),
                ),
            ):
                result = device_evidence.capture_device_screenshot(device, screenshot)

            self.assertEqual(result["status"], "captured")
            self.assertEqual(screenshot.read_bytes(), b"png")
            self.assertEqual(result["command"][0], "/sdk/platform-tools/adb")

    def test_android_local_target_reverses_all_injected_authority_ports(self) -> None:
        args = self._args()
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }
        calls: list[list[str]] = []

        def run_adb(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with (
            mock.patch.object(
                smoke,
                "resolve_android_debug_bridge",
                return_value="/usr/bin/adb",
            ),
            mock.patch.object(smoke.subprocess, "run", side_effect=run_adb),
        ):
            result = smoke._prepare_android_local_port_reverse(args, device)

        self.assertEqual(result["status"], "installed")
        self.assertEqual(
            {command[-1] for command in calls},
            {"tcp:19000", "tcp:19010", "tcp:19100", "tcp:19130"},
        )
        self.assertTrue(
            all(command[3] == "reverse" for command in calls),
        )

    def test_simulator_ca_install_targets_selected_device_not_booted_alias(self) -> None:
        with mock.patch.object(
            smoke,
            "install_ios_simulator_root_ca",
            return_value={
                "status": "installed",
                "target": "gamma-local",
                "deviceId": "selected-simulator",
                "certPath": "/tmp/root.crt",
            },
        ) as install:
            result = smoke._install_simulator_root_ca(
                "local-gamma",
                "selected-simulator",
            )

        self.assertEqual(result["status"], "installed")
        install.assert_called_once_with("gamma-local", "selected-simulator")

    def test_alpha_stack_has_no_best_effort_booted_simulator_install(self) -> None:
        script = (
            ROOT / "quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh"
        ).read_text(encoding="utf-8")

        self.assertNotIn("simctl keychain booted add-root-cert", script)
        self.assertIn("--simulator-udid \"$simulator_udid\"", script)

    def test_local_app_launchers_delegate_ios_trust_to_shared_fail_closed_helper(self) -> None:
        app_instance = (
            ROOT / "quwoquan_app/scripts/device/start_app_instance.sh"
        ).read_text(encoding="utf-8")
        beta_manual = (
            ROOT / "quwoquan_app/scripts/device/start_app_beta_manual.sh"
        ).read_text(encoding="utf-8")
        dev_up = (
            ROOT / "quwoquan_ops/cli/lib/dev_up.py"
        ).read_text(encoding="utf-8")

        self.assertIn("install-ios-simulator-ca", app_instance)
        self.assertIn("QWQ_IOS_SIMULATOR_UDID", app_instance)
        self.assertNotIn("add-root-cert || true", app_instance)
        self.assertIn("is-ios-simulator", beta_manual)
        self.assertIn("QWQ_IOS_SIMULATOR_UDID", beta_manual)
        self.assertIn('command_env["QWQ_IOS_SIMULATOR_UDID"] = device_id', dev_up)
        self.assertNotIn("install_ios_simulator_root_ca(target_name, device_id)", dev_up)

    def test_beta_starts_backing_services_before_assistant(self) -> None:
        beta_manual = (
            ROOT / "quwoquan_app/scripts/device/start_app_beta_manual.sh"
        ).read_text(encoding="utf-8")
        beta_stack = (
            ROOT / "quwoquan_ops/cli/beta/start_beta_stack.sh"
        ).read_text(encoding="utf-8")
        beta_backing_compose = (
            ROOT / "quwoquan_ops/environments/compose/docker-compose.beta-backing.yaml"
        ).read_text(encoding="utf-8")
        beta_gateway = (
            ROOT
            / "quwoquan_ops"
            / "tests"
            / "acceptance"
            / "user_acceptance"
            / "service_ops"
            / "assistant-service"
            / "smoke"
            / "dev_assistant_beta_gateway.py"
        ).read_text(encoding="utf-8")
        backing_ready = beta_manual.index(
            "real beta content data plane must be ready before beta services start",
        )
        assistant_start = beta_manual.index(
            'echo "[app-beta-manual] starting assistant-service beta',
        )

        self.assertLess(backing_ready, assistant_start)
        for token in (
            "docker-compose.beta-backing.yaml",
            "quwoquan-beta-backing",
            'mongodb://127.0.0.1:${BETA_MONGO_PORT}/?directConnection=true',
            '127.0.0.1:${BETA_REDIS_PORT}',
            'MONGODB_URI="$CHAT_MONGO_URI"',
            'MONGODB_DATABASE="quwoquan_assistant"',
            'REDIS_GENERAL_ADDR="$CHAT_REDIS_ADDR"',
            'REDIS_REC_ADDR="$CHAT_REDIS_ADDR"',
            'ENTITY_REDIS_ADDR="127.0.0.1:${BETA_REDIS_PORT}"',
            "export CONTENT_PORT",
            "export BETA_POSTGRES_PORT BETA_MONGO_PORT BETA_REDIS_PORT",
            "BETA_OBJECT_STORAGE_EDGE_PORT",
            "BETA_SERVICE_CONFIG_ROOT",
            "rec-model-service",
            "content-service",
            'mkdir -p "$(dirname "$CHAT_SEED_LOG")"',
            'python3 "$BETA_MANUAL_RUNTIME_LOG_PROCESS"',
            '--event "chat-seed"',
            'CIRCLE_SERVICE_BASE_URL="$INTERNAL_GATEWAY_BASE_URL"',
            'CONTENT_SERVICE_BASE_URL="$INTERNAL_GATEWAY_BASE_URL"',
            'https://localhost:${GATEWAY_PORT}',
            'https://localhost:${PRODUCT_OPS_PORT}',
            'https://localhost:${MEDIA_PORT}',
            '-p "${GATEWAY_PORT}:${GATEWAY_PORT}"',
            '-p "${PRODUCT_OPS_PORT}:${PRODUCT_OPS_PORT}"',
            '-p "${MEDIA_PORT}:${MEDIA_PORT}"',
        ):
            self.assertIn(token, beta_manual)
        self.assertNotIn("LOCAL_GAMMA_", beta_manual)
        self.assertNotIn(') >"$CHAT_SEED_LOG" 2>&1', beta_manual)
        self.assertIn("BETA_MONGO_PORT", beta_backing_compose)
        self.assertIn("BETA_REDIS_PORT", beta_backing_compose)
        self.assertIn("object-storage:", beta_backing_compose)
        self.assertIn("rec-model-service:", beta_backing_compose)
        self.assertIn("content-service:", beta_backing_compose)
        self.assertIn("REPORT_DATABASE_URL", beta_backing_compose)
        self.assertIn(
            'CONTENT_EMBEDDING_ENDPOINT: "${CONTENT_EMBEDDING_ENDPOINT:-}"',
            beta_backing_compose,
        )
        self.assertIn(
            'CONTENT_EMBEDDING_API_KEY: "${CONTENT_EMBEDDING_API_KEY:-}"',
            beta_backing_compose,
        )
        self.assertIn(
            "beta_manual_require_content_embedding_binding",
            beta_manual,
        )
        self.assertIn(
            "beta content embedding provider prerequisite is missing",
            beta_manual,
        )
        self.assertLess(
            beta_manual.index(
                "beta_manual_require_content_embedding_binding || return 1",
            ),
            beta_manual.index("beta_manual_ensure_docker_daemon || return 1"),
        )
        self.assertIn(
            'CONFIG_VERSION: "${CONTENT_CONFIG_VERSION:-}"',
            beta_backing_compose,
        )
        self.assertIn(
            "BETA_CONTENT_RELEASE_CONFIG_VERSION",
            beta_manual,
        )
        self.assertIn(
            "CONTENT_CONFIG_VERSION=\"$BETA_CONTENT_RELEASE_CONFIG_VERSION\"",
            beta_manual,
        )
        self.assertIn("--write-report-account-backfill", beta_manual)
        self.assertIn('NOTIFICATION_SERVICE_ADDR=":${BETA_NOTIFICATION_PORT}"', beta_manual)
        self.assertIn("@content_report path /content/reports", beta_manual)
        self.assertIn("@notification_app_messages", beta_manual)
        self.assertIn("BETA_FIXTURE_GATEWAY_PORT", beta_manual)
        self.assertIn('if path == "/user/sync":', beta_gateway)
        self.assertNotIn(
            'path.startswith("/chat") or path == "/user/sync"',
            beta_gateway,
        )
        self.assertIn("--skip-assistant", beta_manual)
        self.assertIn('if [[ "$START_ASSISTANT" == "1" ]]; then', beta_manual)
        self.assertIn(
            'if [[ "$WORKLOAD" == "content-release" ]]; then',
            beta_stack,
        )
        self.assertIn("APP_BETA_CMD+=(--content-release)", beta_stack)
        self.assertIn("beta_manual_start_content_release_stack", beta_manual)
        self.assertIn('if [[ "$CONTENT_RELEASE_ONLY" == "1" ]]; then', beta_manual)
        self.assertIn("beta_manual_start_notification_service", beta_manual)
        self.assertLess(
            beta_manual.index('if [[ "$CONTENT_RELEASE_ONLY" == "1" ]]; then'),
            beta_manual.index('beta_manual_ensure_port_available "$CHAT_PORT"'),
        )
        self.assertNotIn("_rewrite_media_urls", beta_gateway)
        self.assertNotIn("_join_media_base", beta_gateway)
        self.assertIn(
            "canonical publicSliceKey",
            beta_gateway,
        )

    def test_prod_sim_tls_exposes_exact_localhost_per_public_plane(self) -> None:
        prod_sim = (
            ROOT / "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh"
        ).read_text(encoding="utf-8")

        for token in (
            'https://localhost:${API_EDGE_PORT}',
            'https://localhost:${PRODUCT_OPS_PORT}',
            'https://localhost:${MEDIA_EDGE_PORT}',
            '-p "${API_EDGE_PORT}:${API_EDGE_PORT}"',
            '-p "${PRODUCT_OPS_PORT}:${PRODUCT_OPS_PORT}"',
            '-p "${MEDIA_EDGE_PORT}:${MEDIA_EDGE_PORT}"',
        ):
            self.assertIn(token, prod_sim)

    def test_local_gamma_tls_exposes_exact_localhost_per_public_plane(self) -> None:
        caddyfile = (
            ROOT / "quwoquan_ops/environments/local-gamma/Caddyfile"
        ).read_text(encoding="utf-8")
        compose = (
            ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
        ).read_text(encoding="utf-8")
        ports = (
            ROOT / "quwoquan_ops/cli/print_local_port_profile.py"
        ).read_text(encoding="utf-8")

        for token in (
            "https://localhost:{$LOCAL_GAMMA_HTTP_PORT:",
            "https://localhost:{$LOCAL_GAMMA_PRODUCT_OPS_PORT:",
            "https://localhost:{$LOCAL_GAMMA_MEDIA_EDGE_PORT:",
        ):
            self.assertIn(token, caddyfile)
        self.assertNotIn("LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT", caddyfile)
        # object-storage-edge 由带 TLS 的 MinIO workload 独占；Caddy 不能再次
        # 绑定同一宿主端口，否则 gamma-proxy 永远无法启动。
        self.assertIn(
            '"${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:?LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT is required}:${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:?LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT is required}"',
            compose,
        )
        self.assertNotIn(
            '"${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:-19130}:${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:-19130}"',
            compose,
        )
        self.assertIn(
            '"LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT": "object-storage-edge"',
            ports,
        )
        gamma_start = (
            ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'CONTENT_EMBEDDING_ENDPOINT: "${LOCAL_GAMMA_EMBEDDING_ENDPOINT:-}"',
            compose,
        )
        self.assertIn(
            'CONTENT_EMBEDDING_API_KEY: "${LOCAL_GAMMA_EMBEDDING_API_KEY:-}"',
            compose,
        )
        self.assertIn(
            'if [[ "$WORKLOAD" == "content-release" ]]; then',
            gamma_start,
        )
        self.assertIn("embedding:", gamma_start)
        self.assertIn("--write-report-account-backfill", gamma_start)

    def test_video_range_mime_preflight_precedes_patrol(self) -> None:
        with mock.patch.object(stackctl, "_local_target_runtime_ready", return_value=True):
            commands = stackctl._selected_profile_commands(
                "gamma",
                "gamma-local",
                VerificationProfile.RELEASE,
                Path("/tmp/gamma-report"),
            )

        names = [item["name"] for item in commands]
        preflight_index = names.index("gamma-local-video-range-mime-preflight")
        media_surface_index = names.index("seeded-media-surface")
        patrol_index = names.index("gamma-local-environment-page-smoke")
        self.assertLess(preflight_index, media_surface_index)
        self.assertLess(media_surface_index, patrol_index)
        self.assertTrue(commands[preflight_index]["stopOnFailure"])
        self.assertTrue(commands[media_surface_index]["stopOnFailure"])

    def test_prod_hosted_patrol_requires_release_video_canary_preflight(self) -> None:
        command = stackctl._target_media_preflight_profile_command(
            "prod-hosted",
            Path("/tmp/prod-report"),
        )

        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command["name"], "prod-hosted-release-video-canary-preflight")
        self.assertTrue(
            any("verify_video_playback_canary.py" in value for value in command["argv"])
        )
        self.assertIn("--report", command["argv"])
        self.assertEqual(
            command["reportPath"],
            "/tmp/prod-report/video-range-mime-preflight/report.json",
        )
        self.assertTrue(command["stopOnFailure"])

    def test_prod_playback_canary_rejects_fixture_identity(self) -> None:
        args = self._args(
            env_name="prod-sim",
            runtime_env="prod",
            video_playback_canary_work_id="fixture_video_001",
        )

        with self.assertRaisesRegex(ValueError, "published release work"):
            smoke._validate_video_playback_canary_work_id(args, "prod")

    def test_stackctl_t4_evidence_binds_same_range_and_player_ready_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            health_report = root / "health.json"
            smoke_report = root / "smoke.json"
            patrol_log = root / "patrol.log"
            patrol_log.write_text(
                (
                    "QWQ_VIDEO_PLAYBACK_EVIDENCE "
                    '{"nativeFirstFrame":true,"nativeSeekSettled":true}\n'
                ),
                encoding="utf-8",
            )
            health_report.write_text(
                json.dumps(
                    {
                        "checks": [
                            {
                                "name": "media-public-content-video-primary",
                                "statusCode": 206,
                                "contentType": "video/mp4",
                            },
                        ],
                    },
                ),
                encoding="utf-8",
            )
            smoke_report.write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "runs": [
                            {
                                "exitCode": 0,
                                "device": {
                                    "targetPlatform": "android-arm64",
                                    "emulator": False,
                                },
                                "evidence": {
                                    "afterScreenshot": {
                                        "path": "evidence/after.png",
                                    },
                                    "videoPlayback": {
                                        "nativeFirstFrame": True,
                                        "nativeSeekSettled": True,
                                    },
                                    "rawLogPath": str(patrol_log),
                                },
                            },
                            {
                                "exitCode": 0,
                                "device": {
                                    "targetPlatform": "ios",
                                    "emulator": False,
                                },
                                "evidence": {},
                            },
                        ],
                    },
                ),
                encoding="utf-8",
            )

            with mock.patch.dict(
                os.environ,
                {
                    "VIDEO_PLAYBACK_QOE_READBACK_PATH": "qoe.json",
                    "VIDEO_PLAYBACK_PERFETTO_TRACE_PATH": "perfetto.trace",
                    "VIDEO_PLAYBACK_PERFETTO_SUMMARY_PATH": "perfetto-summary.json",
                },
                clear=False,
            ):
                evidence = stackctl._runtime_media_t4_evidence(
                    target_name="gamma-local",
                    steps=[
                        {
                            "name": "gamma-local-video-range-mime-preflight",
                            "reportPath": str(health_report),
                        },
                        {
                            "name": "gamma-local-environment-page-smoke",
                            "reportPath": str(smoke_report),
                        },
                    ],
                    started_at="2026-07-16T00:00:00Z",
                    ended_at="2026-07-16T00:01:00Z",
                )

        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(evidence["environment"]["target"], "gamma-local")
        self.assertEqual(evidence["serviceEvidence"]["videoRange"]["statusCode"], 206)
        self.assertTrue(evidence["uiEvidence"]["stageRendered"])
        self.assertTrue(evidence["uiEvidence"]["playerReady"])
        self.assertFalse(evidence["uiEvidence"]["playerError"])
        self.assertTrue(evidence["uiEvidence"]["nativeFirstFrame"])
        self.assertTrue(evidence["uiEvidence"]["nativeSeekSettled"])
        self.assertTrue(
            evidence["uiEvidence"]["nativeEvidenceFromPhysicalAndroidDevice"],
        )
        self.assertTrue(evidence["uiEvidence"]["physicalIosPatrolPassed"])
        self.assertEqual(evidence["uiEvidence"]["playerState"], "ready")

    def test_stackctl_t4_evidence_rejects_emulator_native_signal_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            health_report = root / "health.json"
            smoke_report = root / "smoke.json"
            health_report.write_text(
                json.dumps(
                    {
                        "checks": [
                            {
                                "name": "media-public-content-video-primary",
                                "statusCode": 206,
                                "contentType": "video/mp4",
                            },
                        ],
                    },
                ),
                encoding="utf-8",
            )
            smoke_report.write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "runs": [
                            {
                                "exitCode": 0,
                                "device": {
                                    "targetPlatform": "android-arm64",
                                    "emulator": True,
                                },
                                "evidence": {
                                    "videoPlayback": {
                                        "nativeFirstFrame": True,
                                        "nativeSeekSettled": True,
                                    },
                                },
                            },
                        ],
                    },
                ),
                encoding="utf-8",
            )

            evidence = stackctl._runtime_media_t4_evidence(
                target_name="gamma-local",
                steps=[
                    {
                        "name": "gamma-local-video-range-mime-preflight",
                        "reportPath": str(health_report),
                    },
                    {
                        "name": "gamma-local-environment-page-smoke",
                        "reportPath": str(smoke_report),
                    },
                ],
                started_at="2026-07-16T00:00:00Z",
                ended_at="2026-07-16T00:01:00Z",
            )

        self.assertEqual(evidence["status"], "failed")
        self.assertFalse(evidence["uiEvidence"]["nativeFirstFrame"])
        self.assertFalse(evidence["uiEvidence"]["nativeSeekSettled"])
        self.assertFalse(
            evidence["uiEvidence"]["nativeEvidenceFromPhysicalAndroidDevice"],
        )
        self.assertEqual(evidence["uiEvidence"]["seekEvidenceSource"], "unverified")

    def test_stackctl_t4_evidence_does_not_mislabel_missing_stage_as_player_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            health_report = root / "health.json"
            smoke_report = root / "smoke.json"
            health_report.write_text(
                json.dumps(
                    {
                        "checks": [
                            {
                                "name": "media-public-content-video-primary",
                                "statusCode": 206,
                                "contentType": "video/mp4",
                            },
                        ],
                    },
                ),
                encoding="utf-8",
            )
            smoke_report.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "runs": [
                            {
                                "exitCode": 1,
                                "outputSummary": (
                                    "Expected: not null\n"
                                    "configured video canary stage should render"
                                ),
                            },
                        ],
                    },
                ),
                encoding="utf-8",
            )

            evidence = stackctl._runtime_media_t4_evidence(
                target_name="gamma-local",
                steps=[
                    {
                        "name": "gamma-local-video-range-mime-preflight",
                        "reportPath": str(health_report),
                    },
                    {
                        "name": "gamma-local-environment-page-smoke",
                        "reportPath": str(smoke_report),
                    },
                ],
                started_at="2026-07-16T00:00:00Z",
                ended_at="2026-07-16T00:01:00Z",
            )

        self.assertEqual(evidence["status"], "failed")
        self.assertFalse(evidence["uiEvidence"]["stageRendered"])
        self.assertFalse(evidence["uiEvidence"]["playerReady"])
        self.assertIsNone(evidence["uiEvidence"]["playerError"])
        self.assertEqual(evidence["uiEvidence"]["playerState"], "stage-not-rendered")

    def test_stackctl_gamma_smoke_never_installs_a_fake_token(self) -> None:
        target = {
            "env": "gamma",
            "publicBases": {
                "api": "https://gamma-api.quwoquan-env.test:19000",
                "productOps": "https://gamma-product-ops.quwoquan-env.test:19010",
                "mediaAvatar": "https://gamma-avatar.quwoquan-env.test:19100",
                "mediaImage": "https://gamma-image.quwoquan-env.test:19100",
                "mediaVideo": "https://gamma-video.quwoquan-env.test:19100",
                "mediaUpload": "https://gamma-upload.quwoquan-env.test:19130",
            },
            "playbackCanary": {
                "workIdEnv": "GAMMA_CANARY_WORK_ID",
            },
        }
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value=target),
            mock.patch.object(stackctl, "_resolve_test_auth_token", return_value=""),
            mock.patch.dict(
                os.environ,
                {
                    "GAMMA_CANARY_WORK_ID": "fixture_video_001",
                    "TEST_REFRESH_TOKEN": "host-refresh-must-not-leak",
                    "APP_CURRENT_OWNER_ID": "host-owner-must-not-leak",
                    "APP_CURRENT_SUB_ACCOUNT_ID": "host-persona-must-not-leak",
                },
                clear=False,
            ),
        ):
            command = stackctl._environment_page_smoke_profile_command(
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
        self.assertEqual(
            argv[argv.index("--media-upload-base-url") + 1],
            "https://gamma-upload.quwoquan-env.test:19130",
        )
        self.assertEqual(
            argv[argv.index("--media-image-base-url") + 1],
            "https://gamma-image.quwoquan-env.test:19100",
        )
        self.assertEqual(
            argv[argv.index("--video-playback-canary-work-id") + 1],
            "fixture_video_001",
        )
        self.assertEqual(
            argv[argv.index("--target") + 1],
            "test/user_acceptance/patrol/environment/video_playback_canary__user_acceptance_test.dart",
        )
        self.assertNotIn("env", command)

    def test_gamma_runtime_readiness_only_requires_declared_gamma_planes(self) -> None:
        roles = stackctl._expected_local_roles("gamma-local")

        self.assertIn("api-edge", roles)
        self.assertIn("product-ops-edge", roles)
        self.assertIn("media-edge", roles)
        self.assertNotIn("platform-ops-edge", roles)
        self.assertNotIn("ops-portal", roles)

    def test_beta_runtime_readiness_requires_real_report_dependencies(self) -> None:
        roles = stackctl._expected_local_roles("beta-local")

        self.assertIn("content-service", roles)
        self.assertIn("notification-service", roles)
        self.assertIn("fixture-gateway", roles)

    def test_stackctl_passes_explicit_remote_token_only_via_process_environment(self) -> None:
        target = {
            "env": "beta",
            "publicBases": {
                "api": "https://beta-api.quwoquan-env.test:18000",
                "productOps": "https://beta-product-ops.quwoquan-env.test:18010",
                "mediaAvatar": "https://beta-avatar.quwoquan-env.test:18100",
                "mediaImage": "https://beta-image.quwoquan-env.test:18100",
                "mediaVideo": "https://beta-video.quwoquan-env.test:18100",
                "mediaUpload": "https://beta-upload.quwoquan-env.test:18100",
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
            command = stackctl._environment_page_smoke_profile_command(
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

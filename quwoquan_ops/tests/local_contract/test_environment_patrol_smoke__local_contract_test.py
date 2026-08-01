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
from urllib.parse import urlsplit
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
            "gateway_base_url": "https://api.gamma.quwoquan.com:19000",
            "product_ops_base_url": "https://ops.gamma.quwoquan.com:19010",
            "media_avatar_base_url": "https://cdn.gamma.quwoquan.com:19100",
            "media_image_base_url": "https://cdn.gamma.quwoquan.com:19100",
            "media_video_base_url": "https://cdn.gamma.quwoquan.com:19100",
            "media_upload_base_url": "https://upload.gamma.quwoquan.com:19130",
            "rtc_media_connection_url": "wss://rtc.gamma.quwoquan.com:19000",
            "video_playback_canary_work_id": "fixture_video_001",
            "patrol_install_id": "",
            "account_closure_disposable_ack": False,
            "persisted_device_session": False,
            "test_auth_token": "local-gamma-token",
            "test_refresh_token": "local-gamma-refresh",
            "release_uat_cases": "",
            "release_uat_cases_b64": "",
            "current_owner_id": "fixture_owner_current",
            "current_persona_id": "fixture_user_current",
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
        target_name = smoke._local_target_for_environment_alias(
            str(values["env_name"])
        )
        public_bases = smoke.get_target(
            smoke.load_environment_topology(),
            target_name,
        )["publicBases"]
        for argument, role in (
            ("gateway_base_url", "api"),
            ("product_ops_base_url", "productOps"),
            ("media_avatar_base_url", "mediaAvatar"),
            ("media_image_base_url", "mediaImage"),
            ("media_video_base_url", "mediaVideo"),
            ("media_upload_base_url", "mediaUpload"),
            ("rtc_media_connection_url", "rtc"),
        ):
            if argument not in overrides:
                values[argument] = public_bases[role]
        return argparse.Namespace(**values)

    def test_patrol_build_workspace_rejects_overlapping_runners(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            lock_path = Path(temporary_dir) / "patrol.lock"
            first = smoke._acquire_patrol_execution_lock(
                env_name="local-beta",
                target=smoke.DEFAULT_TARGET,
                lock_path=lock_path,
            )
            try:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Patrol build workspace is already in use",
                ):
                    smoke._acquire_patrol_execution_lock(
                        env_name="local-gamma",
                        target=smoke.DEFAULT_TARGET,
                        lock_path=lock_path,
                    )
            finally:
                first.close()

            replacement = smoke._acquire_patrol_execution_lock(
                env_name="local-gamma",
                target=smoke.DEFAULT_TARGET,
                lock_path=lock_path,
            )
            replacement.close()

    def test_default_target_is_the_video_playback_canary(self) -> None:
        self.assertEqual(
            smoke.DEFAULT_TARGET,
            (
                "test/user_acceptance/patrol/environment/"
                "video_playback_canary__user_acceptance_test.dart"
            ),
        )

    def test_runtime_recovery_evidence_is_exact_and_privacy_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            log_path = Path(temporary_dir) / "patrol.log"
            log_path.write_text(
                "QWQ_RUNTIME_RECOVERY_EVIDENCE "
                + json.dumps(
                    {
                        "authenticatedBefore": True,
                        "authenticatedAfter": True,
                        "sameOwner": True,
                        "samePersona": True,
                        "homeRestored": True,
                        "secondFaultNoReentry": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            evidence = smoke._read_runtime_recovery_evidence(log_path)
            self.assertTrue(all(evidence.values()))

            log_path.write_text(
                'QWQ_RUNTIME_RECOVERY_EVIDENCE {"sameOwner":true}\n',
                encoding="utf-8",
            )
            self.assertEqual(smoke._read_runtime_recovery_evidence(log_path), {})

    def test_runtime_recovery_requires_persisted_session_without_injected_identity(self) -> None:
        target = smoke.RUNTIME_RECOVERY_TARGET
        with self.assertRaisesRegex(
            ValueError,
            "requires --persisted-device-session",
        ):
            smoke._prepare_execution_session(
                self._args(
                    target=target,
                    test_auth_token="",
                    test_refresh_token="",
                    current_owner_id="",
                    current_persona_id="",
                )
            )

        args = self._args(
            target=target,
            persisted_device_session=True,
            test_auth_token="",
            test_refresh_token="",
            current_owner_id="",
            current_persona_id="",
        )
        self.assertEqual(
            smoke._prepare_execution_session(args),
            "persisted_device_session",
        )
        with self.assertRaisesRegex(ValueError, "forbids injected auth"):
            smoke._prepare_execution_session(
                self._args(
                    target=target,
                    persisted_device_session=True,
                )
            )

    def test_runtime_recovery_requires_dual_physical_device_matrix(self) -> None:
        args = self._args(
            target=smoke.RUNTIME_RECOVERY_TARGET,
            persisted_device_session=True,
        )
        with self.assertRaisesRegex(RuntimeError, "physical Android"):
            smoke._validate_runtime_recovery_device_matrix(
                args,
                [
                    {"targetPlatform": "android-arm64", "emulator": False},
                    {"targetPlatform": "ios", "emulator": True},
                ],
            )
        smoke._validate_runtime_recovery_device_matrix(
            args,
            [
                {"targetPlatform": "android-arm64", "emulator": False},
                {"targetPlatform": "ios", "emulator": False},
            ],
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

    def test_alpha_playback_canary_uses_the_current_published_release(self) -> None:
        topology = stackctl.load_environment_topology()
        target = stackctl.get_target(topology, "alpha-local")
        canary = target["playbackCanary"]

        self.assertEqual(canary["source"], "published-release")
        self.assertEqual(canary["workIdEnv"], "VIDEO_PLAYBACK_CANARY_WORK_ID")
        self.assertEqual(
            canary["publicSliceKeyEnv"],
            "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY",
        )
        self.assertEqual(
            smoke._evidence_class_for_runtime("alpha"),
            "user_acceptance_remote",
        )
        self.assertEqual(
            smoke._evidence_class_for_runtime("beta"),
            "user_acceptance_remote",
        )

    def test_beta_playback_canary_uses_the_current_published_release(self) -> None:
        topology = stackctl.load_environment_topology()
        target = stackctl.get_target(topology, "beta-local")
        canary = target["playbackCanary"]

        self.assertEqual(canary["source"], "published-release")
        self.assertEqual(
            canary["workIdEnv"],
            "VIDEO_PLAYBACK_CANARY_WORK_ID",
        )
        self.assertEqual(
            canary["publicSliceKeyEnv"],
            "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY",
        )

    def test_remote_patrol_keeps_125s_video_contract_without_app_bundle(self) -> None:
        scenarios = ROOT / (
            "quwoquan_service/services/content-service/tests/support/"
            "contract_fixtures/scenarios/content_scenarios.json"
        )
        payload = json.loads(scenarios.read_text(encoding="utf-8"))
        posts = payload["seedSets"]["content_discovery_core"]["posts"]
        canary_posts = [
            item
            for item in posts
            if item.get("postId") == "video_tokyo_midnight"
        ]
        self.assertEqual(
            len(canary_posts),
            1,
            "fixture video coverage requires the canonical Tokyo midnight video object",
        )
        canary = canary_posts[0]
        self.assertEqual(canary.get("contentType"), "video")
        self.assertEqual(canary.get("durationMs"), 125000)
        self.assertEqual(canary.get("mediaAssetId"), "media-canary-seek-125s")
        self.assertIn("media-canary-seek-125s", str(canary.get("videoUrl", "")))

        profile = ROOT / "quwoquan_data/reference/media_canary/video_playback.yaml"
        self.assertTrue(profile.is_file(), "mediaCanary.profileRef must resolve")
        profile_text = profile.read_text(encoding="utf-8")
        self.assertIn("media-canary-seek-125s", profile_text)
        self.assertIn("media-canary-hour-boundary-3595s", profile_text)

        patrol_main = (
            ROOT / "quwoquan_app/test/user_acceptance/patrol/patrol_test_main.dart"
        ).read_text(encoding="utf-8")
        self.assertNotIn("runQuwoquanApp(", patrol_main)
        harness = (
            ROOT
            / "quwoquan_app/test/support/patrol/patrol_environment_harness.dart"
        ).read_text(encoding="utf-8")
        self.assertNotIn("buildAlphaCloudOverrides", harness)
        self.assertNotIn("providerScopeOverrides", harness)
        self.assertIn("launchPatrolAppOnce($)", harness)

    def test_effective_base_urls_keep_canonical_public_hosts_for_local_ios(self) -> None:
        args = self._args()
        device = {"targetPlatform": "ios", "emulator": True}

        actual = smoke._effective_base_urls_for_device(args, device)

        self.assertEqual(actual["gatewayBaseUrl"], "https://api.gamma.quwoquan.com:19000")
        self.assertEqual(actual["productOpsBaseUrl"], "https://ops.gamma.quwoquan.com:19010")
        self.assertEqual(actual["mediaAvatarBaseUrl"], "https://cdn.gamma.quwoquan.com:19100/media/avatar")
        self.assertEqual(actual["mediaImageBaseUrl"], "https://cdn.gamma.quwoquan.com:19100/media/image")
        self.assertEqual(actual["mediaVideoBaseUrl"], "https://cdn.gamma.quwoquan.com:19100/media/video")
        self.assertEqual(actual["mediaUploadBaseUrl"], "https://upload.gamma.quwoquan.com:19130")
        self.assertNotIn("mediaBaseUrl", actual)

    def test_effective_base_urls_keep_public_tls_hostname_for_android(self) -> None:
        args = self._args()
        device = {"targetPlatform": "android-arm64", "emulator": True}

        actual = smoke._effective_base_urls_for_device(args, device)

        self.assertEqual(actual["gatewayBaseUrl"], "https://api.gamma.quwoquan.com:19000")
        self.assertEqual(actual["productOpsBaseUrl"], "https://ops.gamma.quwoquan.com:19010")
        self.assertEqual(actual["mediaAvatarBaseUrl"], "https://cdn.gamma.quwoquan.com:19100/media/avatar")
        self.assertEqual(actual["mediaImageBaseUrl"], "https://cdn.gamma.quwoquan.com:19100/media/image")
        self.assertEqual(actual["mediaVideoBaseUrl"], "https://cdn.gamma.quwoquan.com:19100/media/video")
        self.assertEqual(actual["mediaUploadBaseUrl"], "https://upload.gamma.quwoquan.com:19130")

    def test_ios_build_restores_canonical_public_transport_authority(self) -> None:
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
                "QWQ_APP_RUNTIME_ENV": "gamma",
                "QWQ_APP_LAUNCH_MODE": "canonical_launcher",
                "QWQ_LAUNCH_TARGET": "gamma-local",
                "QWQ_DART_DEFINES_DIGEST": "sha256:" + ("0" * 64),
                "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST": "sha256:" + ("1" * 64),
                "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST": "sha256:" + ("2" * 64),
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
            resolved_gateway("https://legacy.invalid:19000"),
            "https://api.gamma.quwoquan.com:19000",
        )
        self.assertEqual(
            resolved_gateway("https://untrusted.localhost:19000"),
            "https://api.gamma.quwoquan.com:19000",
        )

    def test_effective_base_urls_keep_public_for_hosted_target(self) -> None:
        args = self._args(
            env_name="prod-hosted",
            runtime_env="prod",
            api_contract_env="prod",
            gateway_base_url="https://api.quwoquan.com",
            product_ops_base_url="https://ops.quwoquan.com",
            media_avatar_base_url="https://cdn.quwoquan.com/media/avatar",
            media_image_base_url="https://cdn.quwoquan.com/media/image",
            media_video_base_url="https://cdn.quwoquan.com/media/video",
            media_upload_base_url="https://upload.quwoquan.com",
        )
        device = {"targetPlatform": "ios", "emulator": True}

        actual = smoke._effective_base_urls_for_device(args, device)

        self.assertEqual(actual["gatewayBaseUrl"], "https://api.quwoquan.com")
        self.assertEqual(actual["productOpsBaseUrl"], "https://ops.quwoquan.com")
        self.assertEqual(actual["mediaImageBaseUrl"], "https://cdn.quwoquan.com/media/image")
        self.assertEqual(actual["mediaUploadBaseUrl"], "https://upload.quwoquan.com")
        self.assertNotIn("mediaBaseUrl", actual)

    def test_gamma_public_video_canary_allows_anonymous_read_only_session(
        self,
    ) -> None:
        args = self._args(
            test_auth_token="",
            test_refresh_token="",
            current_owner_id="",
            current_persona_id="",
        )
        source = smoke._prepare_execution_session(args)

        self.assertEqual(source, "gamma_local_anonymous_public_video")
        self.assertEqual(args.test_auth_token, "")
        self.assertEqual(args.test_refresh_token, "")
        self.assertEqual(smoke._resolved_owner_id(args), "")
        self.assertEqual(smoke._resolved_persona_id(args), "")
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
        self.assertEqual(command[:3], ["patrol", "test", "--verbose"])
        self.assertIn(
            "--dart-define=QWQ_PATROL_SESSION_MODE="
            "gamma_local_anonymous_public_video",
            command,
        )
        self.assertIn(
            "--dart-define=REQUIRE_NATIVE_VIDEO_PLAYBACK_SIGNALS=true",
            command,
        )
        self.assertIn(
            "--dart-define=APP_LEGAL_BASE_URL=https://gamma.quwoquan.com:19000/legal",
            command,
        )
        self.assertNotIn("--dart-define-from-file=", command)

    def test_beta_public_video_canary_allows_anonymous_read_only_session(self) -> None:
        args = self._args(
            env_name="beta-local",
            runtime_env="beta",
            api_contract_env="beta",
            gateway_base_url="https://api.beta.quwoquan.com:18000",
            product_ops_base_url="https://ops.beta.quwoquan.com:18010",
            media_avatar_base_url="https://cdn.beta.quwoquan.com:18100/media/avatar",
            media_image_base_url="https://cdn.beta.quwoquan.com:18100/media/image",
            media_video_base_url="https://cdn.beta.quwoquan.com:18100/media/video",
            media_upload_base_url="https://upload.beta.quwoquan.com:18100",
            test_auth_token="",
            test_refresh_token="",
            current_owner_id="",
            current_persona_id="",
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

    def test_stackctl_uses_canonical_public_hosts_without_host_rewrite(self) -> None:
        topology = stackctl.load_environment_topology()
        expected_hosts = {
            "alpha-local": "cdn.alpha.quwoquan.com",
            "beta-local": "cdn.beta.quwoquan.com",
            "gamma-local": "cdn.gamma.quwoquan.com",
            "prod-sim": "cdn.sim.quwoquan.com",
            "prod-hosted": "cdn.quwoquan.com",
        }
        for target_name, expected_host in expected_hosts.items():
            target = stackctl.get_target(topology, target_name)
            media_video_url = target["publicBases"]["mediaVideo"]
            parsed = urlsplit(media_video_url)
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(parsed.hostname, expected_host)
            self.assertNotIn("resolveHost", target)
            self.assertNotIn("connectHost", target)

    def test_patrol_command_includes_canonical_public_hosts_and_current_user(self) -> None:
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

        self.assertIn("--dart-define=CLOUD_GATEWAY_BASE_URL=https://api.gamma.quwoquan.com:19000", joined)
        self.assertIn("--dart-define=API_CONTRACT_PRODUCT_OPS_BASE_URL=https://ops.gamma.quwoquan.com:19010", joined)
        self.assertIn("--dart-define=MEDIA_AVATAR_CDN_BASE_URL=https://cdn.gamma.quwoquan.com:19100/media/avatar", joined)
        self.assertIn("--dart-define=MEDIA_IMAGE_CDN_BASE_URL=https://cdn.gamma.quwoquan.com:19100/media/image", joined)
        self.assertIn("--dart-define=MEDIA_VIDEO_CDN_BASE_URL=https://cdn.gamma.quwoquan.com:19100/media/video", joined)
        self.assertIn("--dart-define=MEDIA_UPLOAD_BASE_URL=https://upload.gamma.quwoquan.com:19130", joined)
        self.assertIn(
            "--dart-define=RTC_MEDIA_CONNECTION_URL=wss://rtc.gamma.quwoquan.com:19000",
            joined,
        )
        self.assertIn(
            "--dart-define=VIDEO_PLAYBACK_CANARY_WORK_ID=fixture_video_001",
            joined,
        )
        self.assertIn(
            "--dart-define=REQUIRE_NATIVE_VIDEO_PLAYBACK_SIGNALS=false",
            joined,
        )
        self.assertIn(
            "--dart-define=QWQ_PATROL_SESSION_MODE=gamma_local_anonymous_runtime",
            joined,
        )
        self.assertNotIn("--dart-define=APP_CURRENT_OWNER_ID=", joined)
        self.assertNotIn("--dart-define=APP_CURRENT_PERSONA_ID=", joined)
        self.assertNotIn("--dart-define-from-file=", joined)
        self.assertNotIn("local-gamma-token", joined)
        self.assertNotIn("local-gamma-refresh", joined)
        self.assertIn("--ios=17.2", command)

    def test_patrol_command_forwards_disposable_account_install_id(self) -> None:
        args = self._args(
            target=(
                "test/user_acceptance/patrol/settings/"
                "account_closure_journey__user_acceptance_test.dart"
            ),
            patrol_install_id="account-closure-ci-run-1-{device}",
        )
        command = smoke.patrol_command(
            {
                "id": "sim-1",
                "targetPlatform": "ios",
                "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                "emulator": True,
            },
            args,
            "patrol",
            dart_define_file=None,
        )

        self.assertIn(
            "--dart-define=QWQ_PATROL_INSTALL_ID=account-closure-ci-run-1-sim-1",
            command,
        )

    def test_account_closure_matrix_rejects_shared_install_identity(self) -> None:
        args = self._args(
            target=smoke.ACCOUNT_CLOSURE_TARGET,
            patrol_install_id="account-closure-shared",
        )

        with self.assertRaisesRegex(ValueError, r"\{device\} placeholder"):
            smoke.patrol_command(
                {
                    "id": "sim-1",
                    "targetPlatform": "ios",
                    "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                    "emulator": True,
                },
                args,
                "patrol",
                dart_define_file=None,
            )

    def test_prod_account_closure_requires_explicit_destructive_ack(self) -> None:
        args = self._args(
            env_name="prod-hosted",
            runtime_env="prod",
            api_contract_env="prod",
            target=smoke.ACCOUNT_CLOSURE_TARGET,
            patrol_install_id="account-closure-prod-{device}",
        )

        with self.assertRaisesRegex(
            ValueError,
            "--account-closure-disposable-ack",
        ):
            smoke._prepare_execution_session(args)

    def test_prod_account_closure_forwards_destructive_ack(self) -> None:
        args = self._args(
            env_name="prod-hosted",
            runtime_env="prod",
            api_contract_env="prod",
            target=smoke.ACCOUNT_CLOSURE_TARGET,
            patrol_install_id="account-closure-prod-{device}",
            account_closure_disposable_ack=True,
        )

        command = smoke.patrol_command(
            {
                "id": "prod-sim-1",
                "targetPlatform": "ios",
                "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                "emulator": True,
            },
            args,
            "patrol",
            dart_define_file=Path("/tmp/private-defines.json"),
        )

        self.assertIn(
            "--dart-define=QWQ_PATROL_INSTALL_ID=account-closure-prod-prod-sim-1",
            command,
        )
        self.assertIn(
            "--dart-define=QWQ_ACCOUNT_CLOSURE_DISPOSABLE_ACK=true",
            command,
        )
        joined = "\n".join(command)
        self.assertNotIn("fixture_owner_current", joined)
        self.assertNotIn("fixture_user_current", joined)
        self.assertIn(
            "--dart-define-from-file=/tmp/private-defines.json",
            command,
        )

    def test_runtime_anonymous_mode_is_available_to_each_local_remote_target(
        self,
    ) -> None:
        cases = (
            ("local-beta", "beta_local_anonymous_runtime"),
            ("local-gamma", "gamma_local_anonymous_runtime"),
            ("local-prod-sim", "prod_sim_anonymous_runtime"),
        )
        for alias, expected_mode in cases:
            with self.subTest(alias=alias):
                args = self._args(
                    env_name=alias,
                    target=(
                        "test/user_acceptance/patrol/content/"
                        "media_publication_remote__user_acceptance_test.dart"
                    ),
                    test_auth_token="",
                    test_refresh_token="",
                    current_owner_id="",
                    current_persona_id="",
                )
                command = smoke.patrol_command(
                    {
                        "id": "sim-1",
                        "targetPlatform": "ios",
                        "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                        "emulator": True,
                    },
                    args,
                    "patrol",
                    dart_define_file=None,
                )

                self.assertIn(
                    f"--dart-define=QWQ_PATROL_SESSION_MODE={expected_mode}",
                    command,
                )
                self.assertNotIn("--dart-define-from-file=", "\n".join(command))

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

    def test_ios_patrol_uses_simctl_semantic_runtime_version(self) -> None:
        inventory = json.dumps(
            {
                "runtimes": [
                    {
                        "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-3",
                        "version": "26.3.1",
                        "isAvailable": True,
                    }
                ],
                "devices": {
                    "com.apple.CoreSimulator.SimRuntime.iOS-26-3": [
                        {
                            "udid": "ios-26-3",
                            "name": "iPhone 17",
                            "isAvailable": True,
                        }
                    ]
                },
            }
        )
        device = {
            "id": "ios-26-3",
            "name": "iPhone 17",
            "targetPlatform": "ios",
            "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-26-3",
            "emulator": True,
        }

        enriched = smoke._enrich_ios_simulator_runtime_versions(
            [device],
            xcrun_path="/usr/bin/xcrun",
            command_runner=lambda argv, **_: subprocess.CompletedProcess(
                argv,
                0,
                stdout=inventory,
                stderr="",
            ),
        )

        self.assertEqual(enriched[0]["runtimeVersion"], "26.3.1")
        self.assertEqual(
            smoke.patrol_ios_runtime_argument(enriched[0]),
            "--ios=26.3.1",
        )

    def test_ios_runtime_resolution_fails_closed_when_device_is_unmapped(
        self,
    ) -> None:
        inventory = json.dumps({"runtimes": [], "devices": {}})
        with self.assertRaisesRegex(RuntimeError, "exact iOS Simulator runtime"):
            smoke._enrich_ios_simulator_runtime_versions(
                [
                    {
                        "id": "missing-ios",
                        "targetPlatform": "ios",
                        "emulator": True,
                    }
                ],
                xcrun_path="/usr/bin/xcrun",
                command_runner=lambda argv, **_: subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout=inventory,
                    stderr="",
                ),
            )

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
            current_persona_id="",
        )
        device = {"id": "android-1", "targetPlatform": "android-arm64", "emulator": True}

        command = smoke.patrol_command(
            device,
            args,
            "patrol",
            dart_define_file=Path("/tmp/patrol-secrets.json"),
        )

        self.assertIn("--dart-define=QWQ_RELEASE_HOMEPAGE_UAT_CASES_B64=eyJjYXNlcyI6W119", command)
        self.assertNotIn("local-gamma-token", smoke._redact_command(command))
        self.assertNotIn("local-gamma-refresh", smoke._redact_command(command))

    def test_core_readback_requires_and_forwards_one_release_envelope(self) -> None:
        release_values = {
            destination: f"value-{index}"
            for index, (destination, _define_name) in enumerate(
                smoke.RELEASE_APP_UAT_DEFINES,
                start=1,
            )
        }
        args = self._args(
            target=smoke.CORE_READBACK_TARGET,
            **release_values,
        )
        device = {
            "id": "android-1",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }

        command = smoke.patrol_command(
            device,
            args,
            "patrol",
            dart_define_file=Path("/tmp/patrol-secrets.json"),
        )

        for destination, define_name in smoke.RELEASE_APP_UAT_DEFINES:
            self.assertIn(
                f"--dart-define={define_name}={release_values[destination]}",
                command,
            )

        missing = self._args(target=smoke.CORE_READBACK_TARGET)
        with self.assertRaisesRegex(ValueError, "immutable release envelope"):
            smoke.patrol_command(
                device,
                missing,
                "patrol",
                dart_define_file=Path("/tmp/patrol-secrets.json"),
            )

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
        self.assertEqual(env["QWQ_APP_RUNTIME_ENV"], "gamma")
        self.assertEqual(env["QWQ_RUN_DEVICE_ID"], "emulator-5554")
        self.assertEqual(env["ANDROID_SERIAL"], "emulator-5554")
        self.assertIn(
            str(smoke.ANDROID_DEVICE_PROXY),
            env[smoke.PATROL_FLUTTER_COMMAND_ENV],
        )

    @mock.patch.object(smoke, "acquire_consumer_lease")
    def test_android_patrol_acquires_consumer_lease_for_reversed_ports(
        self,
        acquire_consumer_lease: mock.Mock,
    ) -> None:
        args = self._args()
        command_env: dict[str, str] = {}

        lease = smoke._acquire_android_patrol_consumer_lease(
            args,
            {
                "id": "emulator-5554",
                "targetPlatform": "android-arm64",
                "emulator": True,
            },
            {
                "status": "installed",
                "mappings": [
                    {"devicePort": 19000, "hostPort": 19000},
                    {"devicePort": 19100, "hostPort": 19100},
                ],
            },
            command_env,
        )

        self.assertEqual(lease[0:2], ("gamma-local", "emulator-5554"))
        self.assertEqual(command_env["QWQ_CONSUMER_LEASE_ACQUIRED"], "1")
        self.assertEqual(command_env["QWQ_ANDROID_LOCAL_PORTS"], "19000,19100")
        acquire_consumer_lease.assert_called_once_with(
            target="gamma-local",
            device="emulator-5554",
            consumer=lease[2],
            package_name="com.quwoquan.quwoquan_app",
            ports=[19000, 19100],
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

    def test_patrol_test_execution_prefers_xctest_over_zero_patrol_summary(self) -> None:
        summary = smoke.patrol_test_execution_summary(
            "Executed 1 test, with 0 failures (0 unexpected)\n"
            "📝 Total: 0\n❌ Failed: 0\n"
        )

        self.assertEqual(
            summary,
            {"framework": "xctest", "executed": 1, "failed": 0},
        )

    def test_remote_api_evidence_requires_ids_and_effective_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "search-report.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "search-remote-api-uat-report",
                        "status": "passed",
                        "cases": {
                            "searchAndFeedbackRoundtrip": {
                                "evidence": {
                                    "schema": "search-remote-api-evidence",
                                    "status": "passed",
                                    "searchRequestId": "search.req.1",
                                    "events": [
                                        {
                                            "requestId": "search.req.1",
                                            "traceId": "trace.1",
                                            "succeeded": True,
                                        }
                                    ],
                                    "feedbackEvents": [
                                        {
                                            "eventType": "impression",
                                            "objectId": "post.1",
                                            "target": None,
                                            "rankPosition": 1,
                                            "dwellMs": None,
                                        },
                                        {
                                            "eventType": "click",
                                            "objectId": "post.1",
                                            "target": "posts",
                                            "rankPosition": 1,
                                            "dwellMs": None,
                                        },
                                        {
                                            "eventType": "dwell",
                                            "objectId": "post.1",
                                            "target": "posts",
                                            "rankPosition": 1,
                                            "dwellMs": 3000,
                                        },
                                    ],
                                }
                            },
                            "tagFilterPositiveAndNegative": {
                                "evidence": {
                                    "schema": "search-tag-filter-remote-evidence",
                                    "status": "passed",
                                    "positiveHitCount": 1,
                                    "negativeHitCount": 0,
                                }
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            evidence = smoke.load_remote_api_evidence(str(path))

        self.assertEqual(evidence["searchRequestId"], "search.req.1")
        self.assertEqual(evidence["events"][0]["traceId"], "trace.1")
        self.assertEqual(
            [event["eventType"] for event in evidence["feedbackEvents"]],
            ["impression", "click", "dwell"],
        )
        self.assertEqual(evidence["tagFilter"]["positiveHitCount"], 1)

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
                '"TEST_REFRESH_TOKEN": "remote-refresh", '
                '"APP_CURRENT_OWNER_ID": "fixture_owner_current", '
                '"APP_CURRENT_PERSONA_ID": "fixture_user_current", '
                '"APP_CURRENT_USER_ID": "fixture_user_current"}\n',
            )
        finally:
            path.unlink(missing_ok=True)

    def test_provider_uat_defines_are_explicit_private_inputs(self) -> None:
        args = self._args(
            env_name="gamma-local",
            runtime_env="gamma",
            test_auth_token="remote-access",
            test_refresh_token="remote-refresh",
        )
        environment = {
            "QWQ_PROVIDER_UAT_DART_DEFINE_KEYS": (
                "QWQ_PROVIDER_UAT_LOCATION_QUERY,"
                "QWQ_PROVIDER_UAT_LOCATION_EXPECTED_TEXT"
            ),
            "QWQ_PROVIDER_UAT_LOCATION_QUERY": "天安门",
            "QWQ_PROVIDER_UAT_LOCATION_EXPECTED_TEXT": "天安门",
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            path = smoke._create_patrol_secret_define_file(args)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["QWQ_PROVIDER_UAT_LOCATION_QUERY"],
                "天安门",
            )
            self.assertEqual(
                payload["QWQ_PROVIDER_UAT_LOCATION_EXPECTED_TEXT"],
                "天安门",
            )
        finally:
            path.unlink(missing_ok=True)

    def test_unauthenticated_auth_entry_rejects_preloaded_session(self) -> None:
        args = self._args(
            target=(
                "test/user_acceptance/patrol/user/"
                "sms_otp_provider__user_acceptance_test.dart"
            ),
            unauthenticated_auth_entry=True,
        )
        with self.assertRaisesRegex(
            ValueError,
            "cannot preload a session",
        ):
            smoke._prepare_execution_session(args)

        args.test_auth_token = ""
        args.test_refresh_token = ""
        args.current_owner_id = ""
        args.current_persona_id = ""
        self.assertEqual(
            smoke._prepare_execution_session(args),
            "unauthenticated_auth_entry",
        )
        self.assertEqual(smoke._missing_required_args(args), [])

    def test_patrol_output_redacts_access_and_refresh_secrets(self) -> None:
        output = "argv access-secret refresh-secret\nrequest failed"

        self.assertEqual(
            smoke._redact_text(output, ("access-secret", "refresh-secret")),
            "argv <redacted> <redacted>\nrequest failed",
        )

    def test_remote_session_missing_actor_is_gate_blocked(self) -> None:
        args = self._args(
            env_name="prod-hosted",
            runtime_env="prod",
            test_auth_token="remote-access",
            test_refresh_token="remote-refresh",
            current_owner_id="",
            current_persona_id="",
        )

        self.assertEqual(
            smoke._missing_required_args(args),
            ["current_owner_id", "current_persona_id"],
        )

    def test_release_bound_homepage_uat_does_not_require_video_canary(self) -> None:
        args = self._args(
            target=(
                "test/user_acceptance/patrol/entity/"
                "release_homepage__consumer_render__functional__user_acceptance_test.dart"
            ),
            release_uat_cases="/tmp/homepage_verification_cases.json",
            video_playback_canary_work_id="",
        )

        self.assertNotIn(
            "video_playback_canary_work_id",
            smoke._missing_required_args(args),
        )

    def test_release_bound_dry_run_does_not_touch_ios_device_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            cases = root / "homepage_verification_cases.json"
            cases.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_data.homepage_verification_case_manifest",
                        "environment": "gamma",
                        "releaseId": "release-a",
                        "runId": "apply-a",
                        "importerReportRef": "env/gamma/runs/data-release/release-a/apply-a/homepage-import.json",
                        "generatedAt": "2026-07-24T00:00:00Z",
                        "cases": [
                            {
                                "entityRef": "地点/景区/test-entity-a",
                                "homepageId": "homepage-a",
                                "title": "test-entity-a",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = self._args(
                dry_run=True,
                platform="ios",
                release_uat_cases=str(cases),
                report=str(root / "report.json"),
            )
            device = {
                "id": "dry-run-ios",
                "name": "Dry Run iPhone",
                "targetPlatform": "ios",
                "emulator": True,
                "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                "screenClass": "phone",
            }
            with (
                mock.patch.object(smoke, "parse_args", return_value=args),
                mock.patch.object(smoke, "dry_run_devices", return_value=[device]),
                mock.patch.object(smoke, "ensure_patrol_ios_products_bridge") as bridge,
                mock.patch.object(smoke, "capture_device_screenshot") as screenshot,
            ):
                self.assertEqual(smoke.main(), 0)

            bridge.assert_not_called()
            screenshot.assert_not_called()
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "passed")
            self.assertNotIn("currentOwnerId", report)
            self.assertNotIn("currentPersonaId", report)
            self.assertTrue(report["hasCurrentOwnerIdentity"])
            self.assertTrue(report["hasCurrentPersonaIdentity"])
            self.assertEqual(report["runs"][0]["evidence"]["localTlsTrust"]["reason"], "not-required")
            self.assertEqual(report["runs"][0]["evidence"]["beforeScreenshot"]["reason"], "dry-run")

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

    def test_device_command_env_configures_android_toolchain_without_private_ca(
        self,
    ) -> None:
        args = self._args()
        device = {
            "id": "emulator-5554",
            "targetPlatform": "android-arm64",
            "emulator": True,
        }

        with mock.patch.object(
            smoke,
            "resolve_android_debug_bridge",
            return_value="/sdk/platform-tools/adb",
        ):
            env = smoke._device_command_env(args, device)

        self.assertEqual(env["ANDROID_SERIAL"], "emulator-5554")
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

        env = smoke._device_command_env(args, device)

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

    def test_patrol_tls_evidence_uses_system_public_ca_without_trust_install(
        self,
    ) -> None:
        self.assertEqual(
            smoke._local_tls_trust_evidence(dry_run=False),
            {"status": "system-public-ca", "reason": "dns-01"},
        )
        self.assertEqual(
            smoke._local_tls_trust_evidence(dry_run=True),
            {"status": "skipped", "reason": "not-required"},
        )

    def test_alpha_uses_the_shared_packaged_local_runtime_entrypoint(self) -> None:
        retired = ROOT / "quwoquan_ops/cli/alpha/start_alpha_mock_stack.sh"
        stackctl_source = (
            ROOT / "quwoquan_ops/cli/stackctl.py"
        ).read_text(encoding="utf-8")

        self.assertFalse(retired.exists())
        self.assertIn(
            'requested_target in {"alpha-local", "beta-local", "gamma-local"}',
            stackctl_source,
        )
        self.assertIn(
            "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
            stackctl_source,
        )
        self.assertNotIn("start_beta_stack.sh", stackctl_source)
        self.assertNotIn("start_alpha_content_release_stack.sh", stackctl_source)

    def test_local_launchers_and_tls_stacks_use_public_ca_helper(self) -> None:
        app_instance = (
            ROOT / "quwoquan_app/scripts/device/start_app_instance.sh"
        ).read_text(encoding="utf-8")
        beta_manual = (
            ROOT / "quwoquan_app/scripts/device/start_app_beta_manual.sh"
        ).read_text(encoding="utf-8")
        dev_up = (
            ROOT / "quwoquan_ops/cli/lib/dev_up.py"
        ).read_text(encoding="utf-8")
        public_tls = (
            ROOT / "quwoquan_ops/cli/lib/public_domain_tls.py"
        ).read_text(encoding="utf-8")

        self.assertIn("public_domain_tls.py\" verify", app_instance)
        self.assertIn("--target \"$TARGET_NAME\"", app_instance)
        self.assertIn("public_domain_tls.py\" paths", beta_manual)
        self.assertIn("--target beta-local", beta_manual)
        self.assertIn("fullchain.pem", public_tls)
        self.assertIn("privkey.pem", public_tls)
        self.assertIn('command_env["QWQ_IOS_SIMULATOR_UDID"] = device_id', dev_up)
        self.assertFalse(
            (ROOT / "quwoquan_ops/cli/lib/local_target_tls.py").exists(),
        )

    def test_beta_uses_one_immutable_release_consumer_backend(self) -> None:
        beta_manual = (
            ROOT / "quwoquan_app/scripts/device/start_app_beta_manual.sh"
        ).read_text(encoding="utf-8")
        beta_stack = (
            ROOT / "quwoquan_ops/cli/beta/start_beta_stack.sh"
        ).read_text(encoding="utf-8")
        beta_backing_compose = (
            ROOT / "quwoquan_ops/environments/compose/docker-compose.beta-backing.yaml"
        ).read_text(encoding="utf-8")
        beta_service_compose = "\n".join(
            (
                ROOT
                / "quwoquan_service"
                / "services"
                / service
                / "deploy"
                / "compose.yaml"
            ).read_text(encoding="utf-8")
            for service in (
                "recommendation-service",
                "content-service",
                "user-service",
                "entity-service",
            )
        )
        data_plane = beta_manual.index("beta_manual_ensure_data_plane || return 1")
        media_runtime = beta_manual.index(
            "beta_manual_start_release_media_runtime || return 1",
            data_plane,
        )
        entity_runtime = beta_manual.index(
            "beta_manual_start_entity_service || return 1",
            media_runtime,
        )
        public_ingress = beta_manual.index(
            "beta_manual_start_tls_proxy || return 1",
            entity_runtime,
        )
        self.assertLess(data_plane, media_runtime)
        self.assertLess(media_runtime, entity_runtime)
        self.assertLess(entity_runtime, public_ingress)
        for token in (
            "docker-compose.beta-backing.yaml",
            "quwoquan-beta-backing",
            'mongodb://127.0.0.1:${BETA_MONGO_PORT}/?directConnection=true',
            '127.0.0.1:${BETA_REDIS_PORT}',
            'ENTITY_REDIS_ADDR="127.0.0.1:${BETA_REDIS_PORT}"',
            "export CONTENT_PORT",
            "export BETA_POSTGRES_PORT BETA_MONGO_PORT BETA_REDIS_PORT",
            "BETA_OBJECT_STORAGE_EDGE_PORT",
            "BETA_SERVICE_CONFIG_ROOT",
            "recommendation-service",
            "content-service",
            'https://${PUBLIC_API_HOST}:${GATEWAY_PORT}',
            'https://${PUBLIC_IMAGE_HOST}:${MEDIA_PORT}',
            '-p "${GATEWAY_PORT}:${GATEWAY_PORT}"',
            '-p "${MEDIA_PORT}:${MEDIA_PORT}"',
            "ship apply is the only writer of this directory",
            "respond 404",
        ):
            self.assertIn(token, beta_manual)
        self.assertNotIn("LOCAL_GAMMA_", beta_manual)
        for retired in (
            "contracts/metadata/_shared/test_fixtures",
            "dev_assistant_beta_gateway.py",
            "beta_manual_start_fixture_gateway",
            "beta_manual_start_notification_service",
            "go run ./cmd/seed-fixture",
            "go run ./services/user-service/cmd/seed",
            "fixture_user_current",
            "START_ASSISTANT",
            "CONTENT_RELEASE_ONLY",
            "CHAT_SEED_LOG",
            "BETA_FIXTURE_GATEWAY_PORT",
        ):
            self.assertNotIn(retired, beta_manual)
        self.assertIn("BETA_MONGO_PORT", beta_backing_compose)
        self.assertIn("BETA_REDIS_PORT", beta_backing_compose)
        self.assertIn("object-storage:", beta_backing_compose)
        self.assertNotIn("recommendation-service:", beta_backing_compose)
        self.assertNotIn("content-service:", beta_backing_compose)
        self.assertIn("recommendation-service:", beta_service_compose)
        self.assertIn("content-service:", beta_service_compose)
        self.assertIn("REPORT_DATABASE_URL", beta_service_compose)
        self.assertIn(
            'CONTENT_EMBEDDING_ENDPOINT: "${QWQ_COMPOSE_EMBEDDING_ENDPOINT:-}"',
            beta_service_compose,
        )
        self.assertIn(
            'CONTENT_EMBEDDING_API_KEY: "${QWQ_COMPOSE_EMBEDDING_API_KEY:-}"',
            beta_service_compose,
        )
        self.assertIn(
            'SEARCH_ES_ENABLED: "${QWQ_COMPOSE_SEARCH_ES_ENABLED:-true}"',
            beta_service_compose,
        )
        self.assertIn(
            "export QWQ_COMPOSE_SEARCH_ES_ENABLED=false",
            beta_manual,
        )
        self.assertIn(
            "SEARCH_ES_ENABLED=false",
            beta_manual,
        )
        self.assertIn(
            "beta_manual_require_content_embedding_binding",
            beta_manual,
        )
        self.assertNotIn("local_provider_credentials", beta_manual)
        self.assertIn(
            "stackctl did not inject protected Beta content embedding Provider material",
            beta_manual,
        )
        self.assertLess(
            beta_manual.index(
                "beta_manual_require_content_embedding_binding || return 1",
            ),
            beta_manual.index("beta_manual_ensure_docker_daemon || return 1"),
        )
        self.assertIn(
            'CONFIG_VERSION: "${QWQ_COMPOSE_CONTENT_SERVICE_CONFIG_VERSION:',
            beta_service_compose,
        )
        self.assertNotIn("BETA_CONTENT_RELEASE_CONFIG_VERSION", beta_manual)
        self.assertIn(
            'content-service) export CONTENT_CONFIG_VERSION="$config_version"',
            beta_manual,
        )
        self.assertIn(
            'recommendation-service) export RECOMMENDATION_CONFIG_VERSION="$config_version"',
            beta_manual,
        )
        self.assertNotIn("--write-report-account-backfill", beta_manual)
        self.assertIn(
            "recommendation_policy.yaml",
            beta_manual,
        )
        self.assertEqual(beta_stack.count("APP_BETA_CMD+=(--content-release)"), 1)
        self.assertIn("beta_manual_start_content_release_stack", beta_manual)
        self.assertIn(
            "for service in content-service entity-service recommendation-service user-service",
            beta_manual,
        )
        self.assertIn("@content_release path /content /content/* /config/app", beta_manual)
        self.assertIn("@homepage_release path /homepages /homepages/*", beta_manual)
        self.assertIn("@creator_profile_release path /auth /auth/* /user /user/* /users /users/*", beta_manual)

    def test_search_dependency_is_owned_by_gamma_overlay_not_content_base(self) -> None:
        content_compose = (
            ROOT / "quwoquan_service/services/content-service/deploy/compose.yaml"
        ).read_text(encoding="utf-8")
        gamma_content_overlay = (
            ROOT
            / "quwoquan_service"
            / "services"
            / "content-service"
            / "environments"
            / "gamma"
            / "deploy"
            / "compose.yaml"
        ).read_text(encoding="utf-8")
        content_dependencies = content_compose.split("    depends_on:\n", 1)[1].split(
            "    ports:\n", 1
        )[0]

        self.assertNotIn("elasticsearch:", content_dependencies)
        self.assertIn("elasticsearch:\n        condition: service_healthy", gamma_content_overlay)

    def test_prod_sim_tls_uses_canonical_hosts_and_public_certificate(self) -> None:
        prod_sim = (
            ROOT / "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh"
        ).read_text(encoding="utf-8")

        for token in (
            'public_domain_tls.py" paths',
            'https://${PUBLIC_API_HOST}:${API_EDGE_PORT}',
            'https://${PUBLIC_PRODUCT_OPS_HOST}:${PRODUCT_OPS_PORT}',
            'https://${PUBLIC_CDN_HOST}:${MEDIA_EDGE_PORT}',
            "$QWQ_PUBLIC_TLS_CERT_FILE:/etc/caddy/tls/fullchain.pem:ro",
            '-p "${API_EDGE_PORT}:${API_EDGE_PORT}"',
            '-p "${PRODUCT_OPS_PORT}:${PRODUCT_OPS_PORT}"',
            '-p "${MEDIA_EDGE_PORT}:${MEDIA_EDGE_PORT}"',
        ):
            self.assertIn(token, prod_sim)

    def test_local_gamma_tls_uses_canonical_hosts_and_public_certificate(self) -> None:
        caddyfile = (
            ROOT / "quwoquan_ops/environments/gamma/local/Caddyfile"
        ).read_text(encoding="utf-8")
        compose = (
            ROOT / "quwoquan_service/services/content-service/deploy/compose.yaml"
        ).read_text(encoding="utf-8")
        infrastructure_compose = (
            ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
        ).read_text(encoding="utf-8")
        ports = (
            ROOT / "quwoquan_ops/cli/print_local_port_profile.py"
        ).read_text(encoding="utf-8")

        for token in (
            "https://{$QWQ_PUBLIC_API_HOST}:{$LOCAL_GAMMA_HTTP_PORT:",
            "https://{$QWQ_PUBLIC_OPS_HOST}:{$LOCAL_GAMMA_PRODUCT_OPS_PORT:",
            "https://{$QWQ_PUBLIC_CDN_HOST}:{$LOCAL_GAMMA_MEDIA_EDGE_PORT:",
            "tls {$QWQ_PUBLIC_TLS_CERT_FILE} {$QWQ_PUBLIC_TLS_KEY_FILE}",
        ):
            self.assertIn(token, caddyfile)
        self.assertNotIn("LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT", caddyfile)
        # object-storage-edge 由带 TLS 的 MinIO workload 独占；Caddy 不能再次
        # 绑定同一宿主端口，否则 gamma-proxy 永远无法启动。
        self.assertIn(
            '"${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:?LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT is required}:${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:?LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT is required}"',
            infrastructure_compose,
        )
        self.assertNotIn(
            '"${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:-19130}:${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:-19130}"',
            infrastructure_compose,
        )
        self.assertIn(
            '"LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT": "object-storage-edge"',
            ports,
        )
        gamma_start = (
            ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('public_domain_tls.py" paths', gamma_start)
        self.assertIn('--target "$QWQ_LOCAL_RELEASE_TARGET"', gamma_start)
        self.assertIn(
            'QWQ_LOCAL_RELEASE_TARGET="${QWQ_LOCAL_RELEASE_TARGET:-${QWQ_LOCAL_RELEASE_ENV}-local}"',
            gamma_start,
        )
        self.assertIn(
            'CONTENT_EMBEDDING_ENDPOINT: "${QWQ_COMPOSE_EMBEDDING_ENDPOINT:-}"',
            compose,
        )
        self.assertIn(
            'CONTENT_EMBEDDING_API_KEY: "${QWQ_COMPOSE_EMBEDDING_API_KEY:-}"',
            compose,
        )
        self.assertIn(
            'if [[ "$WORKLOAD" == "content-release" ]]; then',
            gamma_start,
        )
        self.assertIn("export_service_compose_environment", gamma_start)
        self.assertIn('export "$source_name"', gamma_start)
        self.assertIn("QWQ_COMPOSE_${source_name#LOCAL_GAMMA_}", gamma_start)
        self.assertNotIn("--write-report-account-backfill", gamma_start)

    def test_video_range_mime_preflight_precedes_patrol(self) -> None:
        commands = stackctl._selected_profile_commands(
            "gamma",
            "gamma-local",
            VerificationProfile.RELEASE,
            Path("/tmp/gamma-report"),
        )

        names = [item["name"] for item in commands]
        preflight_index = names.index("gamma-local-release-video-canary-preflight")
        patrol_index = names.index("gamma-local-environment-page-smoke")
        search_patrol_index = names.index("gamma-local-search-remote-patrol")
        self.assertLess(preflight_index, patrol_index)
        self.assertLess(patrol_index, search_patrol_index)
        self.assertTrue(commands[preflight_index]["stopOnFailure"])
        self.assertTrue(
            any(
                "verify_video_playback_canary.py" in value
                for value in commands[preflight_index]["argv"]
            ),
        )
        self.assertNotIn("seeded-media-surface", names)

        search_patrol = commands[search_patrol_index]
        self.assertEqual(
            search_patrol["argv"][
                search_patrol["argv"].index("--target") + 1
            ],
            (
                "test/user_acceptance/patrol/search/"
                "cross_domain_search_journey__user_acceptance_test.dart"
            ),
        )
        self.assertNotIn("--video-playback-canary-work-id", search_patrol["argv"])

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

    def test_prod_sim_is_not_part_of_the_local_release_profile(self) -> None:
        readiness_path = Path(
            "/tmp/prod-runs/data-release/release-a/verify-a/release-readiness.json"
        )
        commands = stackctl._selected_profile_commands(
            "prod",
            "prod-sim",
            VerificationProfile.RELEASE,
            Path("/tmp/prod-report"),
            data_readiness_path=readiness_path,
        )

        self.assertNotIn("prod-sim-up", {item["name"] for item in commands})

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
                        "schema": "quwoquan_ops.release_video_delivery_evidence",
                        "status": "passed",
                        "target": "gamma-local",
                        "release": {
                            "releaseId": "release-20260716",
                            "sourceOwner": "qwq_data",
                            "manifestDigest": f"sha256:{'1' * 64}",
                            "mediaManifestDigest": f"sha256:{'2' * 64}",
                            "importRunId": "import-gamma-20260716",
                            "verifyRunId": "verify-gamma-20260716",
                            "readinessReceiptRef": (
                                "env/gamma/runs/data-release/release-20260716/"
                                "verify-gamma-20260716/release-readiness.json"
                            ),
                        },
                        "video": {
                            "postId": "release-post-20260716",
                            "assetId": "asset-release-20260716",
                            "assetVersion": 7,
                            "publicSliceKey": (
                                "media/video/s/asset/asset-release-20260716/"
                                "v7/source.mp4"
                            ),
                            "expectedHash": f"sha256:{'3' * 64}",
                        },
                        "delivery": {
                            "rangeStatus": 206,
                            "mimeType": "video/mp4",
                        },
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
                    "VIDEO_PLAYBACK_IOS_PERFORMANCE_TRACE_PATH": (
                        "ios-performance.trace"
                    ),
                    "VIDEO_PLAYBACK_IOS_PERFORMANCE_SUMMARY_PATH": (
                        "ios-performance-summary.json"
                    ),
                },
                clear=False,
            ):
                evidence = stackctl._runtime_media_t4_evidence(
                    target_name="gamma-local",
                    steps=[
                        {
                            "name": "gamma-local-release-video-canary-preflight",
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
        self.assertEqual(evidence["release"]["releaseId"], "release-20260716")
        self.assertEqual(evidence["release"]["importRunId"], "import-gamma-20260716")
        self.assertEqual(evidence["media"]["assetId"], "asset-release-20260716")
        self.assertEqual(evidence["media"]["assetVersion"], 7)
        self.assertEqual(evidence["media"]["probeHash"], f"sha256:{'3' * 64}")
        self.assertEqual(evidence["post"]["postId"], "release-post-20260716")
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
        self.assertEqual(
            evidence["uiEvidence"]["iosPerformanceSummaryPath"],
            "ios-performance-summary.json",
        )
        self.assertEqual(evidence["uiEvidence"]["playerState"], "ready")

    def test_stackctl_t4_evidence_rejects_emulator_native_signal_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            health_report = root / "health.json"
            smoke_report = root / "smoke.json"
            health_report.write_text(
                json.dumps(
                    {
                        "rangeStatus": 206,
                        "contentType": "video/mp4",
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
                        "name": "gamma-local-release-video-canary-preflight",
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
                        "rangeStatus": 206,
                        "contentType": "video/mp4",
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
                        "name": "gamma-local-release-video-canary-preflight",
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
                "api": "https://api.gamma.quwoquan.com:19000",
                "productOps": "https://ops.gamma.quwoquan.com:19010",
                "rtc": "wss://rtc.gamma.quwoquan.com:19000",
                "mediaAvatar": "https://cdn.gamma.quwoquan.com:19100",
                "mediaImage": "https://cdn.gamma.quwoquan.com:19100",
                "mediaVideo": "https://cdn.gamma.quwoquan.com:19100",
                "mediaUpload": "https://upload.gamma.quwoquan.com:19130",
            },
            "playbackCanary": {
                "workIdEnv": "GAMMA_CANARY_WORK_ID",
            },
        }
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value=target),
            mock.patch.object(
                stackctl,
                "get_environment",
                return_value={},
            ),
            mock.patch.object(stackctl, "_resolve_test_auth_token", return_value=""),
            mock.patch.dict(
                os.environ,
                {
                    "GAMMA_CANARY_WORK_ID": "fixture_video_001",
                    "TEST_REFRESH_TOKEN": "host-refresh-must-not-leak",
                    "APP_CURRENT_OWNER_ID": "host-owner-must-not-leak",
                    "APP_CURRENT_PERSONA_ID": "host-persona-must-not-leak",
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
        self.assertNotIn("--data-source", argv)
        self.assertEqual(argv[argv.index("--env-name") + 1], "local-gamma")
        self.assertEqual(
            argv[argv.index("--media-upload-base-url") + 1],
            "https://upload.gamma.quwoquan.com:19130",
        )
        self.assertEqual(
            argv[argv.index("--media-image-base-url") + 1],
            "https://cdn.gamma.quwoquan.com:19100",
        )
        self.assertEqual(
            argv[argv.index("--rtc-media-connection-url") + 1],
            "wss://rtc.gamma.quwoquan.com:19000",
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

    def test_stackctl_runtime_recovery_uses_persisted_device_session_only(self) -> None:
        target = {
            "env": "gamma",
            "publicBases": {
                "api": "https://api.gamma.quwoquan.com:19000",
                "productOps": "https://ops.gamma.quwoquan.com:19010",
                "rtc": "wss://rtc.gamma.quwoquan.com:19000",
                "mediaAvatar": "https://cdn.gamma.quwoquan.com:19100",
                "mediaImage": "https://cdn.gamma.quwoquan.com:19100",
                "mediaVideo": "https://cdn.gamma.quwoquan.com:19100",
                "mediaUpload": "https://upload.gamma.quwoquan.com:19130",
            },
        }
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value=target),
            mock.patch.dict(
                os.environ,
                {
                    "TEST_AUTH_TOKEN": "must-not-be-used",
                    "TEST_REFRESH_TOKEN": "must-not-be-used",
                    "APP_CURRENT_OWNER_ID": "must-not-be-used",
                    "APP_CURRENT_PERSONA_ID": "must-not-be-used",
                },
                clear=False,
            ),
        ):
            command = stackctl._environment_page_smoke_profile_command(
                "gamma",
                "gamma-local",
                Path("/tmp/gamma-report"),
                suite_name="runtime-recovery-patrol",
                patrol_target=stackctl.RUNTIME_RECOVERY_UAT_TEST_TARGET,
                persisted_device_session=True,
            )

        self.assertIsNotNone(command)
        self.assertEqual(
            command["argv"][command["argv"].index("--target") + 1],
            stackctl.RUNTIME_RECOVERY_UAT_TEST_TARGET,
        )
        self.assertIn("--persisted-device-session", command["argv"])
        self.assertNotIn("env", command)

    def test_gamma_release_profile_binds_search_remote_api_evidence(self) -> None:
        command = stackctl._search_remote_api_integration_profile_command(
            "gamma-local",
            VerificationProfile.RELEASE,
            Path("/tmp/gamma-release"),
        )

        self.assertIsNotNone(command)
        self.assertEqual(
            command["name"],
            "gamma-local-search-remote-api-integration",
        )
        self.assertEqual(
            command["argv"],
            [
                "bash",
                "quwoquan_app/scripts/gamma/run_local_gamma_search_api_uat.sh",
            ],
        )
        self.assertTrue(command["stopOnFailure"])
        self.assertEqual(
            command["reportPath"],
            "/tmp/gamma-release/search-remote-api-integration/"
            "search_remote_api_uat_report.json",
        )
        self.assertIsNone(
            stackctl._search_remote_api_integration_profile_command(
                "gamma-local",
                VerificationProfile.INTEGRATION,
                Path("/tmp/gamma-release"),
            )
        )

    def test_content_uat_uses_topology_and_release_runtime_cases(self) -> None:
        target = {
            "env": "gamma",
            "publicBases": {
                "api": "https://api.gamma.quwoquan.com:19000",
                "productOps": "https://ops.gamma.quwoquan.com:19010",
                "rtc": "wss://rtc.gamma.quwoquan.com:19000",
                "mediaAvatar": "https://cdn.gamma.quwoquan.com:19100",
                "mediaImage": "https://cdn.gamma.quwoquan.com:19100",
                "mediaVideo": "https://cdn.gamma.quwoquan.com:19100",
                "mediaUpload": "https://upload.gamma.quwoquan.com:19130",
            },
        }
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value=target),
            mock.patch.object(
                stackctl,
                "get_environment",
                return_value={},
            ),
        ):
            command = stackctl._content_release_uat_command(
                target_name="gamma-local",
                release_uat_cases=Path(
                    ".qwq_output/env/gamma/runs/data-release/release/apply/homepage_verification_cases.json"
                ),
                platform="android",
                device_ids=["emulator-5554"],
                report_dir=Path("/tmp/gamma-content-uat"),
            )

        argv = command["argv"]
        self.assertEqual(command["name"], "gamma-local-content-release-uat")
        self.assertEqual(
            argv[argv.index("--target") + 1],
            stackctl.RELEASE_HOMEPAGE_UAT_TEST_TARGET,
        )
        self.assertEqual(
            argv[argv.index("--release-uat-cases") + 1],
            ".qwq_output/env/gamma/runs/data-release/release/apply/homepage_verification_cases.json",
        )
        self.assertEqual(argv[argv.index("--platform") + 1], "android")
        self.assertEqual(argv[argv.index("--device-id") + 1], "emulator-5554")
        self.assertEqual(argv[argv.index("--gateway-base-url") + 1], target["publicBases"]["api"])

    def test_content_uat_rejects_cases_outside_gamma_release_evidence(self) -> None:
        args = argparse.Namespace(
            command="content-uat",
            target="gamma-local",
            release_uat_cases="/tmp/not-release-cases.json",
            platform="android",
            device_id=[],
            report_dir="/tmp/content-uat-report",
        )

        with mock.patch.object(stackctl, "env_runs_root", return_value=Path("/tmp/gamma-runs")):
            payload = stackctl.command_content_uat(args)

        self.assertEqual(payload["exitCode"], 2)
        self.assertIn("No such file", "\n".join(payload["details"]))

    def test_three_nonprod_full_runtimes_share_one_required_role_set(self) -> None:
        roles = stackctl._expected_local_roles("gamma-local")

        self.assertIn("api-edge", roles)
        self.assertIn("product-ops-edge", roles)
        self.assertIn("media-edge", roles)
        self.assertIn("object-storage-edge", roles)
        self.assertIn("rtc-service", roles)
        self.assertIn("livekit-http", roles)
        self.assertNotIn("platform-ops-edge", roles)
        self.assertNotIn("ops-portal", roles)
        self.assertEqual(roles, stackctl._expected_local_roles("alpha-local"))
        self.assertEqual(roles, stackctl._expected_local_roles("beta-local"))

    def test_beta_runtime_readiness_requires_real_report_dependencies(self) -> None:
        roles = stackctl._expected_local_roles("beta-local")

        self.assertIn("content-service", roles)
        self.assertIn("notification-service", roles)
        self.assertNotIn("fixture-gateway", roles)

    def test_beta_content_release_readiness_excludes_full_workload_planes(self) -> None:
        roles = set(
            stackctl._expected_local_roles(
                "beta-local",
                workload="content-release",
            )
        )

        self.assertEqual(
            roles,
            {
                "api-edge",
                "media-edge",
                "media-origin",
                "content-service",
                "user-service",
                "entity-service",
            },
        )
        self.assertNotIn("assistant-service", roles)
        self.assertNotIn("chat-service", roles)
        self.assertNotIn("notification-service", roles)
        self.assertNotIn("fixture-gateway", roles)

    def test_alpha_content_release_diagnostic_profile_is_not_full_green(self) -> None:
        roles = set(
            stackctl._expected_local_roles(
                "alpha-local",
                workload="content-release",
            )
        )

        self.assertEqual(
            roles,
            {
                "api-edge",
                "media-edge",
                "media-origin",
                "content-service",
                "user-service",
                "entity-service",
            },
        )
        self.assertNotIn("product-ops-edge", roles)

    def test_stackctl_passes_explicit_remote_token_only_via_process_environment(self) -> None:
        target = {
            "env": "beta",
            "publicBases": {
                "api": "https://api.beta.quwoquan.com:18000",
                "productOps": "https://ops.beta.quwoquan.com:18010",
                "rtc": "wss://rtc.beta.quwoquan.com:18000",
                "mediaAvatar": "https://cdn.beta.quwoquan.com:18100",
                "mediaImage": "https://cdn.beta.quwoquan.com:18100",
                "mediaVideo": "https://cdn.beta.quwoquan.com:18100",
                "mediaUpload": "https://upload.beta.quwoquan.com:18100",
            },
        }
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value=target),
            mock.patch.object(
                stackctl,
                "get_environment",
                return_value={},
            ),
            mock.patch.object(stackctl, "_resolve_test_auth_token", return_value="secret-access"),
            mock.patch.dict(
                os.environ,
                {
                    "TEST_REFRESH_TOKEN": "secret-refresh",
                    "APP_CURRENT_OWNER_ID": "owner-real",
                    "APP_CURRENT_PERSONA_ID": "persona-real",
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
                "APP_CURRENT_PERSONA_ID": "persona-real",
            },
        )


if __name__ == "__main__":
    unittest.main()

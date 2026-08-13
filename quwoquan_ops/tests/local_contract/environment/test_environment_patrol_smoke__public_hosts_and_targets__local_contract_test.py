"""environment patrol smoke：公网 host、匿名会话与设备/账号巡逻目标契约。

由 1000 行硬顶拆分自 test_environment_patrol_smoke__local_contract_test.py；
测试逐字搬移，共享 helper 基类见
quwoquan_ops/tests/support/environment_patrol_smoke_test_support.py。
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke

from quwoquan_ops.cli import stackctl
from quwoquan_ops.tests.support.environment_patrol_smoke_test_support import (
    EnvironmentPatrolSmokeCaseBase,
)


class EnvironmentPatrolSmokeTest(EnvironmentPatrolSmokeCaseBase):
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

    def test_ios_build_uses_canonical_handoff_public_transport_authority(self) -> None:
        # Isolate deploy/output roots so a host active candidate with legacy
        # legal-static/current symlink cannot pollute this contract. Safety
        # validation stays fail-closed; this test must not read that candidate.
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            output_root = work / "output"
            deploy_root = work / "deploy"
            package_app = deploy_root / "gamma-local" / "packages" / "app"
            package_app.mkdir(parents=True, exist_ok=True)
            (package_app / "app_runtime.yaml").write_text(
                "\n".join(
                    [
                        "schema: app-runtime-config",
                        "runtime:",
                        "  appRuntimeEnv: gamma",
                        "  gatewayBaseUrl: https://api.gamma.quwoquan.com:19000",
                        "  legalBaseUrl: https://gamma.quwoquan.com:19000/legal",
                        "  publicWebBaseUrl: https://gamma.quwoquan.com:19000",
                        "  appDownloadBaseUrl: https://cdn.gamma.quwoquan.com:19100/download",
                        "  realtimeBaseUrl: wss://api.gamma.quwoquan.com:19000",
                        "  mediaAvatarCdnBaseUrl: https://cdn.gamma.quwoquan.com:19100/media/avatar",
                        "  mediaImageCdnBaseUrl: https://cdn.gamma.quwoquan.com:19100/media/image",
                        "  mediaVideoCdnBaseUrl: https://cdn.gamma.quwoquan.com:19100/media/video",
                        "  mediaUploadBaseUrl: https://upload.gamma.quwoquan.com:19130",
                        "  rtcMediaConnectionUrl: wss://rtc.gamma.quwoquan.com:19000",
                        "  currentUserId: ''",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (package_app / "report.json").write_text(
                json.dumps(
                    {
                        "status": "packaged",
                        "env": "gamma",
                        "target": "gamma-local",
                        "runtimeEnv": "gamma",
                        "composition": "production_remote",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            isolated_env = {
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "QWQ_OUTPUT_ROOT": str(output_root),
                "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
            }
            handoff_result = subprocess.run(
                [
                    sys.executable,
                    str(
                        ROOT
                        / "quwoquan_app"
                        / "scripts"
                        / "device"
                        / "build_launcher_handoff.py"
                    ),
                    "--env",
                    "gamma",
                    "--target",
                    "gamma-local",
                    "--launch-mode",
                    "canonical_launcher",
                    "--content-release-id",
                    "release-gamma",
                    "--content-manifest-digest",
                    "sha256:" + ("1" * 64),
                    "--content-readiness-receipt-digest",
                    "sha256:" + ("2" * 64),
                ],
                cwd=ROOT / "quwoquan_app",
                env=isolated_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                handoff_result.returncode,
                0,
                handoff_result.stderr or handoff_result.stdout,
            )
            handoff = json.loads(handoff_result.stdout)

            def prepare_defines(
                supplied_gateway: str,
            ) -> subprocess.CompletedProcess[str]:
                entries = {
                    "APP_RUNTIME_ENV": "gamma",
                    "CLOUD_GATEWAY_BASE_URL": supplied_gateway,
                }
                encoded = ",".join(
                    base64.b64encode(f"{key}={value}".encode("utf-8")).decode(
                        "ascii"
                    )
                    for key, value in entries.items()
                )
                environment = {
                    **isolated_env,
                    "DART_DEFINES": encoded,
                    "QWQ_LAUNCH_HANDOFF_JSON": json.dumps(
                        handoff,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    "QWQ_APP_RUNTIME_ENV": "gamma",
                    "QWQ_APP_LAUNCH_MODE": "canonical_launcher",
                    "QWQ_LAUNCH_TARGET": "gamma-local",
                    "QWQ_DART_DEFINES_DIGEST": handoff["dartDefinesDigest"],
                    "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST": handoff[
                        "runtimeConfigDigest"
                    ],
                    "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST": handoff[
                        "effectiveLaunchManifestDigest"
                    ],
                    "QWQ_CONTENT_RELEASE_ID": handoff["contentReleaseId"],
                    "QWQ_CONTENT_MANIFEST_DIGEST": handoff[
                        "contentManifestDigest"
                    ],
                    "QWQ_CONTENT_READINESS_RECEIPT_DIGEST": handoff[
                        "contentReadinessReceiptDigest"
                    ],
                }
                result = subprocess.run(
                    [
                        "bash",
                        str(
                            ROOT
                            / "quwoquan_app"
                            / "scripts"
                            / "ios"
                            / "build_prepare_dart_defines.sh"
                        ),
                    ],
                    cwd=ROOT / "quwoquan_app",
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                return result

            canonical_result = prepare_defines(
                handoff["dartDefines"]["CLOUD_GATEWAY_BASE_URL"]
            )
            self.assertEqual(canonical_result.returncode, 0, canonical_result.stderr)
            export = next(
                line
                for line in canonical_result.stdout.splitlines()
                if line.startswith("export DART_DEFINES=")
            )
            merged = {
                key: value
                for key, value in (
                    base64.b64decode(item).decode("utf-8").split("=", 1)
                    for item in export.split("=", 1)[1].split(",")
                )
            }
            self.assertEqual(
                merged["CLOUD_GATEWAY_BASE_URL"],
                "https://api.gamma.quwoquan.com:19000",
            )

            for drifted_gateway in (
                "https://legacy.invalid:19000",
                "https://untrusted.localhost:19000",
            ):
                result = prepare_defines(drifted_gateway)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(
                    "DART_DEFINES conflict with canonical launcher handoff",
                    result.stderr,
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

        self.assertEqual(source, "anonymous_public_video_session")
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
            "anonymous_public_video_session",
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
            media_upload_base_url="https://upload.beta.quwoquan.com:18130",
            test_auth_token="",
            test_refresh_token="",
            current_owner_id="",
            current_persona_id="",
        )

        source = smoke._prepare_execution_session(args)

        self.assertEqual(source, "anonymous_public_video_session")
        self.assertEqual(smoke._missing_required_args(args), [])
        command = smoke.patrol_command(
            {"id": "android-beta", "targetPlatform": "android-arm64", "emulator": True},
            args,
            "patrol",
            dart_define_file=None,
        )
        self.assertIn(
            "--dart-define=QWQ_PATROL_SESSION_MODE="
            "anonymous_public_video_session",
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
            "--dart-define=QWQ_PATROL_SESSION_MODE=runtime_anonymous_session",
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
                "test/user_acceptance/service/user_service/account/user_account/"
                "account_closure_remote__user_acceptance_test.dart"
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
            ("local-beta", "runtime_anonymous_session"),
            ("local-gamma", "runtime_anonymous_session"),
            ("local-prod-sim", "runtime_anonymous_session"),
        )
        for alias, expected_mode in cases:
            with self.subTest(alias=alias):
                args = self._args(
                    env_name=alias,
                    target=(
                        "test/user_acceptance/service/content_service/media/media_upload_session/"
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


if __name__ == "__main__":
    unittest.main()

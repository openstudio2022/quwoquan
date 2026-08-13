"""environment patrol smoke：stackctl 播放证据、smoke/readback 注入与环境 profile 契约。

由 1000 行硬顶拆分自 test_environment_patrol_smoke__local_contract_test.py；
测试逐字搬移，共享 helper 基类见
quwoquan_ops/tests/support/environment_patrol_smoke_test_support.py。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.content_release_readiness import VerificationProfile
from quwoquan_ops.tests.support.environment_patrol_smoke_test_support import (
    EnvironmentPatrolSmokeCaseBase,
)


class EnvironmentPatrolSmokeTest(EnvironmentPatrolSmokeCaseBase):
    def test_stackctl_runtime_media_playback_evidence_binds_same_range_and_player_ready_reports(self) -> None:
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
                evidence = stackctl._runtime_media_playback_evidence(
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

    def test_stackctl_runtime_media_playback_evidence_rejects_emulator_native_signal_claim(self) -> None:
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

            evidence = stackctl._runtime_media_playback_evidence(
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

    def test_stackctl_runtime_media_playback_evidence_does_not_mislabel_missing_stage_as_player_error(
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

            evidence = stackctl._runtime_media_playback_evidence(
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
            "test/user_acceptance/journeys/home_video_playback/video_playback_canary__user_acceptance_test.dart",
        )
        self.assertNotIn("env", command)

    def test_stackctl_home_video_smoke_injects_the_release_video_work_id(self) -> None:
        target = {
            "env": "alpha",
            "publicBases": {
                "api": "https://api.alpha.quwoquan.com:17000",
                "productOps": "https://ops.alpha.quwoquan.com:17010",
                "rtc": "wss://rtc.alpha.quwoquan.com:17000",
                "mediaAvatar": "https://cdn.alpha.quwoquan.com:17100",
                "mediaImage": "https://cdn.alpha.quwoquan.com:17100",
                "mediaVideo": "https://cdn.alpha.quwoquan.com:17100",
                "mediaUpload": "https://upload.alpha.quwoquan.com:17130",
            },
            "playbackCanary": {"workId": "release-video-001"},
        }
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value=target),
            mock.patch.object(stackctl, "_resolve_test_auth_token", return_value=""),
        ):
            command = stackctl._environment_page_smoke_profile_command(
                "alpha",
                "alpha-local",
                Path("/tmp/alpha-home-video-report"),
                patrol_target=stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
            )

        self.assertIsNotNone(command)
        argv = command["argv"]
        self.assertEqual(
            argv[argv.index("--target") + 1],
            stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
        )
        self.assertEqual(
            argv[argv.index("--video-playback-canary-work-id") + 1],
            "release-video-001",
        )

    def test_stackctl_core_readback_injects_the_release_video_work_id(self) -> None:
        target = {
            "env": "alpha",
            "publicBases": {
                "api": "https://api.alpha.quwoquan.com:17000",
                "productOps": "https://ops.alpha.quwoquan.com:17010",
                "rtc": "wss://rtc.alpha.quwoquan.com:17000",
                "mediaAvatar": "https://cdn.alpha.quwoquan.com:17100",
                "mediaImage": "https://cdn.alpha.quwoquan.com:17100",
                "mediaVideo": "https://cdn.alpha.quwoquan.com:17100",
                "mediaUpload": "https://upload.alpha.quwoquan.com:17130",
            },
            "playbackCanary": {"workId": "release-video-001"},
        }
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value=target),
            mock.patch.object(stackctl, "_resolve_test_auth_token", return_value=""),
        ):
            command = stackctl._environment_page_smoke_profile_command(
                "alpha",
                "alpha-local",
                Path("/tmp/alpha-core-readback-report"),
                patrol_target=stackctl.APP_CORE_READBACK_UAT_TEST_TARGET,
            )

        self.assertIsNotNone(command)
        argv = command["argv"]
        self.assertEqual(
            argv[argv.index("--video-playback-canary-work-id") + 1],
            "release-video-001",
        )

    def test_stackctl_core_readback_uses_the_validated_app_uat_video_binding(
        self,
    ) -> None:
        target = {
            "env": "alpha",
            "publicBases": {
                "api": "https://api.alpha.quwoquan.com:17000",
                "productOps": "https://ops.alpha.quwoquan.com:17010",
                "rtc": "wss://rtc.alpha.quwoquan.com:17000",
                "mediaAvatar": "https://cdn.alpha.quwoquan.com:17100",
                "mediaImage": "https://cdn.alpha.quwoquan.com:17100",
                "mediaVideo": "https://cdn.alpha.quwoquan.com:17100",
                "mediaUpload": "https://upload.alpha.quwoquan.com:17130",
            },
            "playbackCanary": {"workId": "stale-environment-video"},
        }
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value=target),
            mock.patch.object(stackctl, "_resolve_test_auth_token", return_value=""),
            mock.patch.object(stackctl, "load_release_video_binding") as load_binding,
        ):
            command = stackctl._environment_page_smoke_profile_command(
                "alpha",
                "alpha-local",
                Path("/tmp/alpha-core-readback-report"),
                patrol_target=stackctl.APP_CORE_READBACK_UAT_TEST_TARGET,
                data_readiness_path=Path("/tmp/release-readiness.json"),
                release_video_work_id="release-video-from-app-uat-envelope",
            )

        self.assertIsNotNone(command)
        argv = command["argv"]
        self.assertEqual(
            argv[argv.index("--video-playback-canary-work-id") + 1],
            "release-video-from-app-uat-envelope",
        )
        load_binding.assert_not_called()

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
        roles = self._expected_roles_from_current_provider_source("gamma-local")

        self.assertIn("api-edge", roles)
        self.assertIn("product-ops-edge", roles)
        self.assertIn("media-edge", roles)
        self.assertIn("object-storage-edge", roles)
        self.assertIn("rtc-service", roles)
        self.assertIn("livekit-http", roles)
        self.assertNotIn("platform-ops-edge", roles)
        self.assertNotIn("ops-portal", roles)
        self.assertEqual(
            roles,
            self._expected_roles_from_current_provider_source("alpha-local"),
        )
        self.assertEqual(
            roles,
            self._expected_roles_from_current_provider_source("beta-local"),
        )

    def test_beta_runtime_readiness_requires_real_report_dependencies(self) -> None:
        roles = self._expected_roles_from_current_provider_source("beta-local")

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

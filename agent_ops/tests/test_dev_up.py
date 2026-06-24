from __future__ import annotations

import io
import unittest
from pathlib import Path
from unittest import mock

from agent_ops.deploy.lib.dev_up import (
    ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV,
    app_target_for_env,
    pick_dev_up_env,
    resolve_app_endpoint_overrides,
    runtime_env_for_dev_env,
)
from agent_ops.deploy.lib.environment_topology import load_environment_topology
from agent_ops.deploy.lib.local_media_origin import LocalMediaOriginHandler
from agent_ops.deploy.lib.mock_public_plane import MockPublicPlaneHandler
from agent_ops.deploy.stackctl import _health_checks_for_target
from agent_ops.assistant.dev_assistant_beta_gateway import (
    AssistantBetaGateway,
    app_message_unread_count,
)

ROOT = Path(__file__).resolve().parents[2]


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class DevUpTest(unittest.TestCase):
    def test_alpha_android_physical_uses_plain_localhost_https_transport(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "alpha",
            "android_physical",
            topology=topology,
        )
        self.assertEqual(
            overrides["gatewayBaseUrl"],
            "https://localhost:17000",
        )
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://localhost:17100",
        )

    def test_beta_android_emulator_uses_local_loopback_https_transport(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "beta",
            "android_emulator",
            topology=topology,
        )
        self.assertEqual(app_target_for_env("beta"), "beta-local")
        self.assertEqual(
            overrides["gatewayBaseUrl"],
            "https://beta-api.localhost:18000",
        )
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://beta-image.localhost:18100",
        )

    def test_beta_android_physical_uses_local_loopback_https_transport(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "beta",
            "android_physical",
            topology=topology,
        )
        self.assertEqual(
            overrides["gatewayBaseUrl"],
            "https://beta-api.localhost:18000",
        )
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://beta-image.localhost:18100",
        )

    def test_gamma_web_uses_local_gamma_public_bases(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "gamma",
            "web",
            topology=topology,
        )
        self.assertEqual(app_target_for_env("gamma"), "gamma-local")
        self.assertEqual(
            overrides["gatewayBaseUrl"],
            "https://gamma-api.quwoquan-env.test:19000",
        )
        self.assertEqual(
            overrides["mediaImageBaseUrl"],
            "https://gamma-image.quwoquan-env.test:19100",
        )

    def test_prod_sim_maps_to_prod_runtime_env(self) -> None:
        self.assertEqual(runtime_env_for_dev_env("prod-sim"), "prod")

    def test_pick_dev_up_env_requires_tty_when_missing(self) -> None:
        with (
            mock.patch("sys.stdin.isatty", return_value=False),
            mock.patch("sys.stderr.isatty", return_value=False),
        ):
            with self.assertRaisesRegex(RuntimeError, "dev-up environment is missing"):
                pick_dev_up_env()

    def test_pick_dev_up_env_accepts_numeric_choice(self) -> None:
        with (
            mock.patch("sys.stdin", new=_TtyStringIO("2\n")),
            mock.patch("sys.stderr", new=_TtyStringIO()),
        ):
            self.assertEqual(
                pick_dev_up_env(("alpha", "beta", "gamma")),
                "beta",
            )

    def test_local_media_origin_resolves_conversation_avatar_alias(self) -> None:
        handler = LocalMediaOriginHandler.__new__(LocalMediaOriginHandler)
        # alpha / prod-sim 启用 alias 时才会解析占位会话头像。
        handler.conversation_avatar_alias_enabled = True
        self.assertEqual(
            handler._resolve_alias("/media/avatar/conversation/conv_002/v1/mock.png"),
            "media/avatar/s/archived-avatar/group/fixture_conv_group/v1/composite.png",
        )
        self.assertEqual(
            handler._resolve_alias("/media/avatar/conversation/conv_006/v1/mock.png"),
            "media/avatar/s/archived-avatar/group/fixture_conv_photo_group/v1/composite.png",
        )
        self.assertEqual(
            handler._resolve_alias(
                "/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png"
            ),
            "media/avatar/s/archived-avatar/group/fixture_conv_group/v1/composite.png",
        )
        self.assertEqual(
            handler._resolve_alias(
                "/media/avatar/s/archived-avatar/conversation/conv_grid_11/v1/mock.png"
            ),
            "media/avatar/s/archived-avatar/group/fixture_conv_photo_group/v1/composite.png",
        )
        self.assertIsNone(handler._resolve_alias("/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png"))

    def test_local_media_origin_alias_disabled_by_default(self) -> None:
        handler = LocalMediaOriginHandler.__new__(LocalMediaOriginHandler)
        # gamma-local 默认关闭 alias：会话占位路径不再被改写。
        self.assertIsNone(
            handler._resolve_alias("/media/avatar/conversation/conv_002/v1/mock.png")
        )
        self.assertIsNone(
            handler._resolve_alias(
                "/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png"
            )
        )

    def test_local_media_origin_supports_byte_range_probe(self) -> None:
        self.assertEqual(
            LocalMediaOriginHandler._parse_byte_range("bytes=0-1", 1128375),
            (0, 1),
        )

    def test_stackctl_media_health_checks_include_video_range(self) -> None:
        topology = load_environment_topology()
        checks = _health_checks_for_target(topology, "alpha-local", "media")
        video_check = next(
            item for item in checks if item["name"] == "media-video-range-sample"
        )
        self.assertEqual(video_check["headers"], {"Range": "bytes=0-1"})
        self.assertEqual(video_check["expectedStatus"], 206)
        self.assertIn(
            "/media/video/s/archived-video/beta-sample.mp4",
            video_check["url"],
        )

    def test_alpha_stack_checks_current_app_group_avatar_contract(self) -> None:
        script = (
            ROOT / "agent_ops/deploy/alpha/start_alpha_mock_stack.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "/media/avatar/s/archived-avatar/conversation/conv_grid_7/v1/mock.png",
            script,
        )
        self.assertIn(
            "/media/avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png",
            script,
        )

    def test_beta_manual_uses_range_aware_media_origin(self) -> None:
        script = (ROOT / "quwoquan_app/scripts/device/start_app_beta_manual.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("agent_ops/deploy/lib/local_media_origin.py", script)
        self.assertIn("beta_manual_wait_http_range_ok", script)
        self.assertNotIn("python3 -m http.server", script)

    def test_android_local_debug_ca_is_required_for_supported_launchers(self) -> None:
        build_gradle = (ROOT / "quwoquan_app/android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        alpha_run = (ROOT / "quwoquan_app/run.sh").read_text(encoding="utf-8")
        beta_manual = (
            ROOT / "quwoquan_app/scripts/device/start_app_beta_manual.sh"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV,
            "QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED",
        )
        self.assertIn(ANDROID_LOCAL_DEBUG_CA_REQUIRED_ENV, build_gradle)
        self.assertIn("export QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED=1", alpha_run)
        self.assertIn("export QWQ_ANDROID_LOCAL_ENV_CA_REQUIRED=1", beta_manual)

    def test_plain_android_flutter_run_is_env_package_backed(self) -> None:
        build_gradle = (ROOT / "quwoquan_app/android/app/build.gradle.kts").read_text(
            encoding="utf-8"
        )
        alpha_script = (
            ROOT / "agent_ops/deploy/alpha/start_alpha_mock_stack.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("tasks.withType<FlutterTask>()", build_gradle)
        self.assertIn('"APP_RUNTIME_ENV" to "alpha"', build_gradle)
        self.assertIn(
            '"CLOUD_GATEWAY_BASE_URL" to "https://localhost:17000"',
            build_gradle,
        )
        self.assertIn(
            '"MEDIA_IMAGE_CDN_BASE_URL" to "https://localhost:17100"',
            build_gradle,
        )
        self.assertIn("prepareAndroidLocalAlphaStack", build_gradle)
        self.assertIn(
            'environment("QWQ_ALPHA_LOCAL_PUBLIC_HOST_SETUP", "skip")',
            build_gradle,
        )
        self.assertIn("prepareAndroidLocalAdbReverse", build_gradle)
        self.assertIn("android.adbExecutable", build_gradle)
        self.assertIn('"reverse",', build_gradle)
        self.assertIn("agent_ops/deploy/lib/tls_reverse_proxy.py", alpha_script)
        self.assertIn("ensure_public_hosts_mapping", alpha_script)
        self.assertIn("security add-trusted-cert", alpha_script)
        self.assertIn("simctl keychain booted add-root-cert", alpha_script)
        self.assertIn("IP.2 = 10.0.2.2", alpha_script)
        self.assertNotIn("--resolve", alpha_script)
        self.assertNotIn("curl -k", alpha_script)
        self.assertNotIn("docker.io/library/caddy", alpha_script)

    def test_plain_ios_flutter_run_prepares_alpha_https_stack(self) -> None:
        project = (
            ROOT / "quwoquan_app/ios/Runner.xcodeproj/project.pbxproj"
        ).read_text(encoding="utf-8")
        prepare_script = (
            ROOT / "quwoquan_app/scripts/ios/prepare_alpha_local_https.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("Prepare Alpha HTTPS Local Plane", project)
        self.assertIn("../scripts/ios/prepare_alpha_local_https.sh", project)
        self.assertIn("QWQ_IOS_LOCAL_AUTO_PREPARE", prepare_script)
        self.assertIn("APP_RUNTIME_ENV=", prepare_script)
        self.assertIn("start_alpha_mock_stack.sh\" up", prepare_script)

    def test_android_local_network_security_forbids_cleartext(self) -> None:
        debug_config = (
            ROOT
            / "quwoquan_app/android/app/src/debug/res/xml/beta_debug_network_security_config.xml"
        ).read_text(encoding="utf-8")
        profile_config = (
            ROOT
            / "quwoquan_app/android/app/src/profile/res/xml/beta_debug_network_security_config.xml"
        ).read_text(encoding="utf-8")
        self.assertIn('cleartextTrafficPermitted="false"', debug_config)
        self.assertIn('cleartextTrafficPermitted="false"', profile_config)
        self.assertNotIn('cleartextTrafficPermitted="true"', debug_config)
        self.assertNotIn('cleartextTrafficPermitted="true"', profile_config)
        debug_manifest = (
            ROOT / "quwoquan_app/android/app/src/debug/AndroidManifest.xml"
        ).read_text(encoding="utf-8")
        profile_manifest = (
            ROOT / "quwoquan_app/android/app/src/profile/AndroidManifest.xml"
        ).read_text(encoding="utf-8")
        self.assertIn('android:usesCleartextTraffic="false"', debug_manifest)
        self.assertIn('android:usesCleartextTraffic="false"', profile_manifest)
        self.assertNotIn(
            'android:usesCleartextTraffic="true"',
            debug_manifest + profile_manifest,
        )

    def test_android_dart_http_client_trusts_packaged_local_ca(self) -> None:
        app_bootstrap = (ROOT / "quwoquan_app/lib/app_bootstrap.dart").read_text(
            encoding="utf-8"
        )
        local_https_trust = (
            ROOT / "quwoquan_app/lib/cloud/runtime/local_dev_https_trust_io.dart"
        ).read_text(encoding="utf-8")
        main_activity = (
            ROOT
            / "quwoquan_app/android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java"
        ).read_text(encoding="utf-8")
        self.assertIn("LocalDevHttpsTrust.installForCurrentRuntime()", app_bootstrap)
        self.assertIn(
            "await _installLocalDevHttpsTrustBeforeMediaClients();",
            app_bootstrap,
        )
        self.assertNotIn("_installLocalDevHttpsTrustAfterFirstFrame", app_bootstrap)
        self.assertIn(
            "SecurityContext.defaultContext.setTrustedCertificatesBytes",
            local_https_trust,
        )
        self.assertNotIn("badCertificateCallback", local_https_trust)
        self.assertIn("localEnvDebugRootCertificate", main_activity)
        self.assertIn("local_env_debug_root", main_activity)

    def test_gamma_local_mirror_persists_caddy_state_on_host(self) -> None:
        gamma_script = (
            ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        gamma_compose = (
            ROOT / "quwoquan_service/docker-compose.gamma-local.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'LOCAL_GAMMA_CADDY_DATA_ROOT="${LOCAL_GAMMA_CADDY_DATA_ROOT:-${LOCAL_GAMMA_STATE_ROOT}/caddy-data}"',
            gamma_script,
        )
        self.assertIn(
            'LOCAL_GAMMA_CADDY_CONFIG_ROOT="${LOCAL_GAMMA_CADDY_CONFIG_ROOT:-${LOCAL_GAMMA_STATE_ROOT}/caddy-config}"',
            gamma_script,
        )
        self.assertIn('-v "${LOCAL_GAMMA_CADDY_DATA_ROOT}:/data" \\', gamma_script)
        self.assertIn('-v "${LOCAL_GAMMA_CADDY_CONFIG_ROOT}:/config" \\', gamma_script)
        self.assertIn(
            '${LOCAL_GAMMA_CADDY_DATA_ROOT:-../state/local/gamma/caddy-data}:/data',
            gamma_compose,
        )
        self.assertIn(
            '${LOCAL_GAMMA_CADDY_CONFIG_ROOT:-../state/local/gamma/caddy-config}:/config',
            gamma_compose,
        )
        self.assertNotIn("local-gamma-caddy-data:/data", gamma_compose)
        self.assertNotIn("local-gamma-caddy-config:/config", gamma_compose)

    def test_alpha_mock_public_plane_ops_event_endpoints(self) -> None:
        handler = MockPublicPlaneHandler.__new__(MockPublicPlaneHandler)
        MockPublicPlaneHandler.ops_event_ids = set()
        MockPublicPlaneHandler.ops_events = []
        ack = handler._record_ops_events(
            {
                "events": [
                    {
                        "eventId": "evt-1",
                        "eventType": "exposure",
                        "eventName": "page.enter",
                        "occurredAt": "2026-06-04T10:50:00Z",
                        "pageName": "discovery_page",
                        "surfaceId": "discovery.home",
                    }
                ]
            }
        )
        self.assertEqual(ack["acceptedCount"], 1)
        summary = handler._build_ops_event_summary({"pageName": ["discovery_page"]})
        self.assertEqual(summary["totalCount"], 1)
        drilldown = handler._build_ops_event_drilldown({"limit": ["5"]})
        self.assertEqual(drilldown["totalCount"], 1)
        self.assertEqual(drilldown["items"][0]["eventId"], "evt-1")

    def test_alpha_mock_public_plane_ops_visit_and_experiment_endpoints(self) -> None:
        handler = MockPublicPlaneHandler.__new__(MockPublicPlaneHandler)
        MockPublicPlaneHandler.ops_visits = []
        MockPublicPlaneHandler.ops_experiment_assignments = {}
        record = handler._record_ops_visit(
            {
                "userId": "user-1",
                "targetType": "page",
                "targetKey": "discovery_recommend",
                "sessionId": "sess-1",
            }
        )
        self.assertEqual(record["visitCount"], 1)
        stats = handler._build_ops_visit_stats(
            {
                "targetType": ["page"],
                "targetKey": ["discovery_recommend"],
            }
        )
        self.assertEqual(stats["totalVisits"], 1)
        assignment = handler._resolve_experiment_assignment("discovery_feed_v3", "user-1")
        self.assertEqual(assignment["experimentId"], "discovery_feed_v3")
        experiment_stats = handler._build_experiment_stats("discovery_feed_v3")
        self.assertEqual(experiment_stats["assignedSubjects"], 1)

    def test_beta_gateway_notification_fixture_family(self) -> None:
        handler = AssistantBetaGateway.__new__(AssistantBetaGateway)
        listing = handler._fixture_response("/v1/app-messages")
        self.assertIsInstance(listing, dict)
        self.assertGreaterEqual(listing["unreadCount"], 0)
        unread = handler._fixture_response("/v1/app-messages/unread-count")
        self.assertEqual(unread["unreadCount"], listing["unreadCount"])
        aggregate = handler._fixture_response("/v1/notifications/unread-count")
        self.assertEqual(aggregate["unreadCount"], listing["unreadCount"])
        first_message = listing["items"][0]
        message_id = first_message["messageId"]
        detail = handler._fixture_response(f"/v1/app-messages/{message_id}")
        self.assertEqual(detail["messageId"], message_id)
        read = handler._fixture_response(f"/v1/app-messages/{message_id}/read")
        self.assertTrue(read["read"])

    def test_beta_gateway_unread_count_falls_back_to_message_scan(self) -> None:
        notification = {
            "appMessages": [
                {"messageId": "a", "read": False},
                {"messageId": "b", "read": True},
                {"messageId": "c", "read": False},
            ]
        }
        self.assertEqual(app_message_unread_count(notification), 2)

    def test_beta_gateway_intersection_fixture_family(self) -> None:
        handler = AssistantBetaGateway.__new__(AssistantBetaGateway)
        summary = handler._fixture_response("/v1/content/intersections/summary")
        self.assertGreater(summary["totalCount"], 0)
        listing = handler._fixture_response("/v1/content/intersections", "dimension=interest&limit=5")
        self.assertTrue(all(item["dimension"] == "interest" for item in listing["items"]))
        feed = handler._fixture_response(
            "/v1/content/feed/intersections",
            "channel=recommend&limit=2",
        )
        self.assertEqual(len(feed["items"]), 2)
        self.assertEqual(
            handler._fixture_response("/v1/content/intersections/visit"),
            {"accepted": True},
        )
        self.assertEqual(
            handler._fixture_response("/v1/content/intersections/exposure"),
            {"accepted": True},
        )


if __name__ == "__main__":
    unittest.main()

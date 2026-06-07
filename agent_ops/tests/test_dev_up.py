from __future__ import annotations

import io
import unittest
from unittest import mock

from agent_ops.deploy.lib.dev_up import (
    app_target_for_env,
    pick_dev_up_env,
    resolve_app_endpoint_overrides,
    runtime_env_for_dev_env,
)
from agent_ops.deploy.lib.environment_topology import load_environment_topology
from agent_ops.deploy.lib.alpha_media_origin import AlphaMediaOriginHandler
from agent_ops.deploy.lib.mock_public_plane import MockPublicPlaneHandler
from agent_ops.assistant.dev_assistant_beta_gateway import (
    AssistantBetaGateway,
    app_message_unread_count,
)


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class DevUpTest(unittest.TestCase):
    def test_beta_android_emulator_uses_android_loopback(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "beta",
            "android_emulator",
            topology=topology,
        )
        self.assertEqual(app_target_for_env("beta"), "beta-local")
        self.assertEqual(overrides["gatewayBaseUrl"], "http://10.0.2.2:18000")
        self.assertEqual(overrides["mediaImageBaseUrl"], "http://10.0.2.2:18100")

    def test_gamma_web_uses_local_gamma_public_bases(self) -> None:
        topology = load_environment_topology()
        overrides = resolve_app_endpoint_overrides(
            "gamma",
            "web",
            topology=topology,
        )
        self.assertEqual(app_target_for_env("gamma"), "gamma-local")
        self.assertEqual(overrides["gatewayBaseUrl"], "http://127.0.0.1:19000")
        self.assertEqual(overrides["mediaImageBaseUrl"], "http://127.0.0.1:19100")

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

    def test_alpha_media_origin_resolves_conversation_avatar_alias(self) -> None:
        handler = AlphaMediaOriginHandler.__new__(AlphaMediaOriginHandler)
        self.assertEqual(
            handler._resolve_alias("/media/avatar/conversation/conv_002/v1/mock.png"),
            "media/avatar/s/archived-avatar/group/fixture_conv_group/v1/composite.png",
        )
        self.assertEqual(
            handler._resolve_alias("/media/avatar/conversation/conv_006/v1/mock.png"),
            "media/avatar/s/archived-avatar/group/fixture_conv_photo_group/v1/composite.png",
        )
        self.assertIsNone(handler._resolve_alias("/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png"))

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

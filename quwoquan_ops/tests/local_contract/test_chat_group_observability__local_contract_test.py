from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
ALERTS = ROOT / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
DASHBOARD = (
    ROOT / "quwoquan_ops/observability/monitoring/dashboards/l2_business_journey.json"
)
SYNC_METRICS = ROOT / "quwoquan_service/runtime/sync/metrics.go"
CHAT_MAIN = ROOT / "quwoquan_service/services/chat-service/cmd/api/main.go"
PROMETHEUS_CONFIG = ROOT / "quwoquan_ops/observability/monitoring/prometheus.yml"


class ChatGroupObservabilityLocalContractTest(unittest.TestCase):
    def test_chat_alerts_use_emitted_labels_and_metadata_slo(self) -> None:
        document = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
        rules = {
            rule["alert"]: rule
            for group in document["groups"]
            for rule in group.get("rules", [])
            if "alert" in rule
        }
        create_latency = rules["ChatConversationCreateLatencyHigh"]
        self.assertIn("> 0.5", create_latency["expr"])
        self.assertIn("500ms", create_latency["annotations"]["summary"])

        for name in (
            "ChatSyncHintToPullLatencyHigh",
            "ChatSyncPatchFanoutFailureRateHigh",
            "ChatSyncRequiresResync",
        ):
            expression = rules[name]["expr"]
            self.assertIn('instance=~"chat-service(:[0-9]+)?"', expression)
            self.assertNotIn('service="chat-service"', expression)

    def test_sync_alert_metrics_have_real_emitters_and_scrape_target(self) -> None:
        source = SYNC_METRICS.read_text(encoding="utf-8")
        for metric in (
            "quwoquan_runtime_media_sync_hint_to_pull_delay_ms",
            "quwoquan_runtime_media_sync_patch_fanout_total",
            "quwoquan_runtime_media_sync_requires_resync_total",
        ):
            self.assertIn(metric, source)
        prometheus = PROMETHEUS_CONFIG.read_text(encoding="utf-8")
        self.assertIn("chat-service:18081", prometheus)

    def test_health_checks_and_dashboard_share_runtime_truth_sources(self) -> None:
        main_source = CHAT_MAIN.read_text(encoding="utf-8")
        for check in (
            "message_outbox_relay",
            "conversation_outbox_relay",
            "membership_outbox_relay",
            "user_state_outbox_relay",
            "inbox_projection",
        ):
            self.assertIn(check, main_source)

        dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
        expressions = "\n".join(
            target["expr"]
            for panel in dashboard["dashboard"]["panels"]
            for target in panel.get("targets", [])
            if isinstance(target.get("expr"), str)
        )
        self.assertIn("runtime_health_check_status", expressions)
        self.assertIn(
            'quwoquan_runtime_media_sync_hint_to_pull_delay_ms_bucket'
            '{instance=~"chat-service(:[0-9]+)?"}',
            expressions,
        )
        self.assertNotIn(
            'quwoquan_runtime_media_sync_patch_fanout_total{service="chat-service"',
            expressions,
        )


if __name__ == "__main__":
    unittest.main()

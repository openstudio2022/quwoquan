from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
ALERTS = ROOT / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
DASHBOARD = (
    ROOT / "quwoquan_ops/observability/monitoring/dashboards/"
    "l2_assistant_runtime.json"
)
METRICS = (
    ROOT
    / "quwoquan_service/services/assistant-service/internal/assistant/"
    "assistant_conversation/application/proactive_metrics.go"
)


class AssistantSubscriptionObservabilityLocalContractTest(unittest.TestCase):
    def test_scheduler_alert_consumes_emitted_tick_metric(self) -> None:
        document = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
        assistant_group = next(
            group
            for group in document["groups"]
            if group["name"] == "quwoquan_l2_assistant_objects"
        )
        rules = {rule["alert"]: rule for rule in assistant_group["rules"]}
        stalled = rules["AssistantSubscriptionCronStalled"]
        self.assertIn(
            "assistant_subscription_cron_tick_total{outcome=\"succeeded\"}",
            stalled["expr"],
        )
        self.assertEqual("30m", stalled["for"])
        self.assertEqual("warning", stalled["labels"]["severity"])

        metric_source = METRICS.read_text(encoding="utf-8")
        for metric_name in (
            "cron_tick_total",
            "delivery_attempt_total",
            "delivery_suppressed_total",
        ):
            self.assertIn(metric_name, metric_source)

    def test_dashboard_exposes_subscription_control_plane(self) -> None:
        dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))["dashboard"]
        panels = {panel["title"]: panel for panel in dashboard["panels"]}
        expected_metrics = {
            "订阅 scheduler tick": "assistant_subscription_cron_tick_total",
            "主动订阅外部投递": "assistant_subscription_delivery_attempt_total",
            "投递前业务抑制": "assistant_subscription_delivery_suppressed_total",
            "错发防线与 @小趣 DLQ": "assistant_wrong_destination_incidents_total",
        }
        for title, metric in expected_metrics.items():
            queries = "\n".join(
                target["expr"] for target in panels[title]["targets"]
            )
            self.assertIn(metric, queries)


if __name__ == "__main__":
    unittest.main()

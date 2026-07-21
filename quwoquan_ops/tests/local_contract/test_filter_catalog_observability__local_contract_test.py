from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
ALERTS = ROOT / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
DASHBOARD = (
    ROOT / "quwoquan_ops/observability/monitoring/dashboards/l2_content_objects.json"
)
METRICS = (
    ROOT
    / "quwoquan_service/services/content-service/internal/infrastructure/content/"
    "filter_catalog_release/observability/metrics.go"
)


class FilterCatalogObservabilityLocalContractTest(unittest.TestCase):
    def test_alerts_consume_emitted_catalog_metrics_and_metadata_slos(self) -> None:
        document = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
        content_group = next(
            group
            for group in document["groups"]
            if group["name"] == "quwoquan_l2_content_objects"
        )
        rules = {rule["alert"]: rule for rule in content_group["rules"]}

        availability = rules["ContentFilterCatalogAvailabilityLow"]
        self.assertIn("content_filter_catalog_get_total", availability["expr"])
        self.assertIn("unavailable|storage_unavailable", availability["expr"])
        self.assertIn("> 0.001", availability["expr"])
        self.assertIn("[5m]", availability["expr"])
        self.assertEqual("5m", availability["for"])
        self.assertEqual("critical", availability["labels"]["severity"])

        latency = rules["ContentFilterCatalogReadLatencyHigh"]
        self.assertIn(
            "content_filter_catalog_operation_duration_seconds_bucket",
            latency["expr"],
        )
        self.assertIn('operation="get"', latency["expr"])
        self.assertIn("> 0.3", latency["expr"])
        self.assertEqual("5m", latency["for"])

        publish_storage = rules["ContentFilterCatalogPublishStorageUnavailable"]
        self.assertIn(
            "content_filter_catalog_(stage|activate|rollback)_total",
            publish_storage["expr"],
        )
        self.assertIn('outcome="storage_unavailable"', publish_storage["expr"])
        self.assertIn("[5m]", publish_storage["expr"])
        self.assertEqual("5m", publish_storage["for"])
        self.assertEqual("critical", publish_storage["labels"]["severity"])

        metric_source = METRICS.read_text(encoding="utf-8")
        for metric in (
            "content_filter_catalog_stage_total",
            "content_filter_catalog_activate_total",
            "content_filter_catalog_rollback_total",
            "content_filter_catalog_get_total",
            "content_filter_catalog_operation_duration_seconds",
        ):
            self.assertIn(metric, metric_source)

    def test_dashboard_exposes_active_reader_and_publish_plane(self) -> None:
        dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))["dashboard"]
        panels = {panel["title"]: panel for panel in dashboard["panels"]}
        active_reader = panels["Filter catalog active reader"]
        control_plane = panels["Filter catalog release control plane"]

        active_queries = "\n".join(
            target["expr"] for target in active_reader["targets"]
        )
        self.assertIn("content_filter_catalog_get_total", active_queries)
        self.assertIn(
            "content_filter_catalog_operation_duration_seconds_bucket",
            active_queries,
        )

        control_queries = "\n".join(
            target["expr"] for target in control_plane["targets"]
        )
        self.assertIn(
            "content_filter_catalog_(stage|activate|rollback)_total",
            control_queries,
        )
        self.assertIn(
            'operation=~"stage|activate|rollback"',
            control_queries,
        )


if __name__ == "__main__":
    unittest.main()

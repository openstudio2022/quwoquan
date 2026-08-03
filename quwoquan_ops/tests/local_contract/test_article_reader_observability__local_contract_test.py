# spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-013

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


class ArticleReaderObservabilityContractTest(unittest.TestCase):
    def test_catalog_rollup_alerts_and_dashboard_share_lifecycle_contract(self) -> None:
        catalog = yaml.safe_load(
            (
                ROOT
                / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/event_catalog.yaml"
            ).read_text(encoding="utf-8")
        )
        events = {item["event_type"]: item for item in catalog["events"]}
        required = {"surfaceId", "objectType", "objectId", "durationMs", "result"}
        for event_type in (
            "article_reader_enter",
            "article_reader_dwell",
            "article_reader_exit",
        ):
            self.assertEqual(set(events[event_type]["required_extensions"]), required)
        self.assertEqual(
            set(events["article_reader_error"]["required_extensions"]),
            {"surfaceId", "objectType", "objectId", "errorCode", "recoveryAction", "result"},
        )
        self.assertEqual(
            set(events["article_reader_recovery"]["required_extensions"]),
            {"surfaceId", "objectType", "objectId", "recoveryAction", "result"},
        )
        self.assertEqual(events["article_reader_dwell"]["normal_sample_rate"], 0.1)
        for event_type in (
            "article_reader_enter",
            "article_reader_exit",
            "article_reader_error",
            "article_reader_recovery",
        ):
            self.assertEqual(events[event_type]["normal_sample_rate"], 1.0)

        rollups = yaml.safe_load(
            (
                ROOT
                / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/rollups.yaml"
            ).read_text(encoding="utf-8")
        )
        jobs = {item["row_kind"]: item for item in rollups["jobs"]}
        lifecycle = jobs["article_reader_lifecycle"]
        self.assertIn("errorCode", lifecycle["dimensions"])
        self.assertIn("recoveryAction", lifecycle["dimensions"])
        self.assertIn("durationHistogram", {item["name"] for item in lifecycle["measures"]})
        self.assertNotIn("objectId", lifecycle["dimensions"])
        self.assertIn("sessionHll", {item["name"] for item in lifecycle["measures"]})
        self.assertNotIn("sessionId", lifecycle["dimensions"])

        alert_policy = yaml.safe_load(
            (ROOT / "quwoquan_ops/observability/elasticsearch/product_telemetry_alerts.yaml").read_text(encoding="utf-8")
        )["spec"]
        alerts = {item["name"]: item for item in alert_policy["alerts"]}
        expected_alerts = {
            "product-article-reader-enter-p95-high": (
                "sampleCount >= 100",
                "p95Ms > 1200",
            ),
            "product-article-reader-error-rate-high": (
                "enterCount >= 100",
                "errorRate > 0.01",
            ),
            "product-article-reader-recovery-failure": (
                "recoveryFailureCount > 0",
            ),
        }
        for name, conditions in expected_alerts.items():
            for condition in conditions:
                self.assertIn(condition, alerts[name]["condition"])

        dashboard = json.loads(
            (
                ROOT / "quwoquan_ops/observability/monitoring/dashboards/l2_content_objects.json"
            ).read_text(encoding="utf-8")
        )["dashboard"]
        rendered = json.dumps(dashboard, ensure_ascii=False)
        self.assertIn("ops_article_reader_events_total", rendered)
        self.assertIn("app-product-telemetry-article-reader-lifecycle-hourly", rendered)
        self.assertIn("dwell` 为 10% 采样", rendered)

    def test_prometheus_alerts_use_the_same_slos(self) -> None:
        alerts = yaml.safe_load(
            (
                ROOT
                / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
            ).read_text(encoding="utf-8")
        )
        rules = {
            rule["alert"]: rule
            for group in alerts["groups"]
            for rule in group["rules"]
            if "alert" in rule
        }
        self.assertIn("ops_article_reader_enter_duration_seconds_bucket", rules["ArticleReaderEnterLatencyHigh"]["expr"])
        self.assertIn('> 1.2', rules["ArticleReaderEnterLatencyHigh"]["expr"])
        self.assertIn("ops_article_reader_events_total", rules["ArticleReaderErrorRateHigh"]["expr"])
        self.assertIn("> 0.01", rules["ArticleReaderErrorRateHigh"]["expr"])


if __name__ == "__main__":
    unittest.main()

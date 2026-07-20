from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


class SearchCommercialObservabilityContractTest(unittest.TestCase):
    def test_catalog_rollup_alerts_and_dashboard_share_one_search_funnel(self) -> None:
        catalog = yaml.safe_load(
            (
                ROOT
                / "quwoquan_service/contracts/metadata/ops/event_record/event_catalog.yaml"
            ).read_text(encoding="utf-8")
        )
        events = {item["event_type"]: item for item in catalog["events"]}
        expected_extensions = {
            "search_query_submit": {"requestId", "surfaceId"},
            "search_result_impression": {"requestId", "resultCount", "durationMs"},
            "search_result_click": {"requestId", "objectType", "rankPosition"},
            "search_refine": {"requestId", "action"},
            "search_zero_result": {"requestId", "durationMs"},
            "search_result_dwell": {"requestId", "durationMs", "resultCount"},
        }
        for event_type, required in expected_extensions.items():
            event = events[event_type]
            self.assertEqual(set(event["required_extensions"]), required)
            self.assertEqual(event["normal_sample_rate"], 1.0)
            allowed = required | set(event["optional_extensions"])
            self.assertNotIn("query", allowed)
            self.assertNotIn("objectId", allowed)
            self.assertNotIn("userId", allowed)

        resource = yaml.safe_load(
            (
                ROOT
                / "quwoquan_ops/environments/cloud-providers/aliyun/sls/product_telemetry.yaml"
            ).read_text(encoding="utf-8")
        )["spec"]
        jobs = {item["name"]: item for item in resource["scheduledSql"]["jobs"]}
        funnel = jobs["app-product-telemetry-search-funnel-hourly"]
        self.assertEqual(funnel["rowKind"], "search_funnel")
        for metric in (
            "querySubmitCount",
            "nonEmptyResultCount",
            "effectiveActionRequestCount",
            "firstActionableHistogram",
        ):
            self.assertIn(metric, funnel["sql"])
        for forbidden_dimension in ("objectId", "userId", "sessionId"):
            self.assertNotIn(forbidden_dimension, funnel["sql"])

        alerts = {item["name"]: item for item in resource["alerts"]}
        expected_alerts = {
            "product-search-effective-success-rate-low": (
                "submitCount >= 100",
                "effectiveSuccessRate < 0.35",
            ),
            "product-search-first-actionable-p95-high": (
                "sampleCount >= 100",
                "p95Ms > 1500",
            ),
            "product-search-effective-action-rate-low": (
                "resultCount >= 100",
                "effectiveActionRate < 0.20",
            ),
        }
        for alert_name, thresholds in expected_alerts.items():
            alert = alerts[alert_name]
            for threshold in thresholds:
                self.assertIn(threshold, alert["condition"])

        dashboard = json.loads(
            (
                ROOT
                / "quwoquan_ops/observability/monitoring/dashboards/l2_search_commercial.json"
            ).read_text(encoding="utf-8")
        )["dashboard"]
        rendered = json.dumps(dashboard, ensure_ascii=False)
        self.assertIn("app-product-telemetry-search-funnel-hourly", rendered)
        self.assertIn("effectiveActionRequestCount / querySubmitCount", rendered)
        self.assertIn("effectiveActionRequestCount / nonEmptyResultCount", rendered)
        self.assertIn("firstActionableHistogram", rendered)

    def test_delivery_and_pre_release_gates_keep_search_smoke_explicit(self) -> None:
        delivery = (ROOT / ".github/workflows/delivery-gate.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("search_contract_smoke:", delivery)
        self.assertIn(
            "go test ./services/search-service/tests/api_integration -count=1",
            delivery,
        )
        self.assertIn(
            'expect_success_or_skipped "search_contract_smoke"',
            delivery,
        )

        pre_release = (ROOT / ".github/workflows/pre-release-gate.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("search_runtime_smoke:", pre_release)
        self.assertIn("--only-check global_search", pre_release)
        self.assertIn("requires search_base_url", pre_release)
        self.assertIn(
            'elif [ "${SEARCH_RESULT}" != "success" ]',
            pre_release,
        )


if __name__ == "__main__":
    unittest.main()

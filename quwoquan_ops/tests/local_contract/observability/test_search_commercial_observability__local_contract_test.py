from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]


class SearchCommercialObservabilityContractTest(unittest.TestCase):
    def test_catalog_rollup_alerts_and_dashboard_share_one_search_funnel(self) -> None:
        catalog = yaml.safe_load(
            (
                ROOT
                / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/event_catalog.yaml"
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

        rollups = yaml.safe_load(
            (
                ROOT
                / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/rollups.yaml"
            ).read_text(encoding="utf-8")
        )
        funnel = next(item for item in rollups["jobs"] if item["row_kind"] == "search_funnel")
        measures = {item["name"] for item in funnel["measures"]}
        for metric in (
            "querySubmitCount",
            "nonEmptyResultCount",
            "effectiveActionRequestCount",
            "firstActionableHistogram",
        ):
            self.assertIn(metric, measures)
        for forbidden_dimension in ("objectId", "userId", "sessionId"):
            self.assertNotIn(forbidden_dimension, funnel["dimensions"])

        alert_policy = yaml.safe_load((ROOT / "quwoquan_ops/observability/elasticsearch/product_telemetry_alerts.yaml").read_text(encoding="utf-8"))["spec"]
        alerts = {item["name"]: item for item in alert_policy["alerts"]}
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
        )
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
            "go test ./services/search-service/tests/api_integration/search/search_index_view -count=1",
            delivery,
        )
        self.assertIn(
            'expect_success_or_skipped "search_contract_smoke"',
            delivery,
        )

        pre_release = (ROOT / ".github/workflows/pre-release-gate.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Pre-Release — PR Light Governance", pre_release)
        self.assertIn("search_runtime_smoke:", pre_release)
        self.assertIn("--only-check global_search", pre_release)
        self.assertIn("requires search_base_url", pre_release)
        self.assertIn('if [[ "$PROFILE" != pr_light ]]; then test "$SEARCH_RESULT" = success; fi', pre_release)


if __name__ == "__main__":
    unittest.main()

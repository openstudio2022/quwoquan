from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]


class AuthLoginObservabilityContractTest(unittest.TestCase):
    def test_dashboard_uses_http_metrics_and_sls_owns_login_funnel(self) -> None:
        path = (
            ROOT
            / "quwoquan_ops/observability/monitoring/dashboards/l2_auth_login_commercial.json"
        )
        dashboard = json.loads(path.read_text(encoding="utf-8"))["dashboard"]
        self.assertEqual(dashboard["uid"], "qwq-l2-auth-login")
        expressions = "\n".join(
            target["expr"]
            for panel in dashboard["panels"]
            for target in panel.get("targets", [])
        )
        self.assertNotIn("ops_events_total", expressions)
        self.assertIn("http_server_requests_total", expressions)
        self.assertIn("http_server_duration_seconds_bucket", expressions)
        self.assertIn("http_server_error_codes_total", expressions)

        sls_path = (
            ROOT
            / "quwoquan_ops/environments/cloud-providers/aliyun/sls/product_telemetry.yaml"
        )
        sls = yaml.safe_load(sls_path.read_text(encoding="utf-8"))["spec"]
        jobs = {item["name"]: item for item in sls["scheduledSql"]["jobs"]}
        dimensions_sql = jobs[
            "app-product-telemetry-event-dimensions-hourly"
        ]["sql"]
        for dimension in ("journey", "action", "result"):
            self.assertIn(dimension, dimensions_sql)

    def test_alerts_enforce_two_windows_and_contract_thresholds(self) -> None:
        path = (
            ROOT
            / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
        )
        groups = yaml.safe_load(path.read_text(encoding="utf-8"))["groups"]
        group = next(item for item in groups if item["name"] == "quwoquan_l2_auth_login")
        rules = {item["alert"]: item for item in group["rules"]}

        provider = rules["AuthProviderErrorRateHigh"]
        self.assertEqual(provider["for"], "10m")
        self.assertIn("> 0.02", provider["expr"])
        self.assertIn("status!~\"2..\"", provider["expr"])

        challenge = rules["AuthChallengeLatencyHigh"]
        self.assertEqual(challenge["for"], "10m")
        self.assertIn("> 1.2", challenge["expr"])

        login = rules["AuthLoginLatencyHigh"]
        self.assertEqual(login["for"], "10m")
        self.assertIn("> 1.5", login["expr"])

    def test_control_plane_declares_sampling_and_retention_keys(self) -> None:
        path = (
            ROOT
            / "quwoquan_service/services/user-service/config/schema.yaml"
        )
        configs = yaml.safe_load(path.read_text(encoding="utf-8"))["configs"]
        values = {item["key"]: item for item in configs}
        self.assertEqual(
            values["sys.user.auth.success_detail_sample_ratio"]["default"],
            0.1,
        )
        self.assertEqual(
            values["sys.user.auth.raw_event_retention_days"]["default"],
            30,
        )
        self.assertEqual(
            values["sys.user.auth.aggregate_metric_retention_days"]["default"],
            180,
        )
        for key in (
            "sys.user.auth.success_detail_sample_ratio",
            "sys.user.auth.raw_event_retention_days",
            "sys.user.auth.aggregate_metric_retention_days",
        ):
            self.assertEqual(values[key]["rollout"], "progressive")


if __name__ == "__main__":
    unittest.main()

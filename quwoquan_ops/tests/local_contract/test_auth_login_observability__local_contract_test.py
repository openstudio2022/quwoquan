from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml

from quwoquan_ops.cli.lib.storage_contract_view import load_storage_contract_view


ROOT = Path(__file__).resolve().parents[3]


class AuthLoginObservabilityContractTest(unittest.TestCase):
    def test_product_ops_projects_only_bounded_login_metric_dimensions(self) -> None:
        path = (
            ROOT
            / "quwoquan_service/services/product-ops-service/cmd/api/telemetry_metrics.go"
        )
        source = path.read_text(encoding="utf-8")
        for metric in (
            "ops_login_funnel_events_total",
            "ops_login_operation_events_total",
            "ops_login_operation_duration_seconds",
            "ops_login_state_dwell_seconds",
        ):
            self.assertIn(metric, source)
        for sanitizer in (
            "boundedLoginAction",
            "boundedLoginResult",
            "boundedLoginStep",
            "boundedLoginProvider",
            "boundedLoginOperation",
            "boundedLoginFailureKind",
        ):
            self.assertIn(sanitizer, source)
        for forbidden_label in (
            '[]string{"flowId"',
            '[]string{"requestId"',
            '[]string{"traceId"',
            '[]string{"copyKey"',
        ):
            self.assertNotIn(forbidden_label, source)

    def test_dashboard_uses_http_metrics_and_elasticsearch_owns_login_funnel(self) -> None:
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
        self.assertIn("ops_login_funnel_events_total", expressions)
        self.assertIn("ops_login_operation_events_total", expressions)
        self.assertIn("ops_login_state_dwell_seconds_bucket", expressions)

        rollup_path = (
            ROOT
            / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/rollups.yaml"
        )
        rollups = yaml.safe_load(rollup_path.read_text(encoding="utf-8"))
        storage_path = (
            ROOT
            / "quwoquan_service/services/product-ops-service/contracts/product_ops/"
            "event_record/storage.yaml"
        )
        storage = load_storage_contract_view(storage_path)
        jobs = {item["row_kind"]: item for item in rollups["jobs"]}
        dimensions = jobs["event_dimensions"]["dimensions"]
        for dimension in ("journey", "action", "result"):
            self.assertIn(dimension, dimensions)

        self.assertEqual(storage["logstores"]["raw"]["ttl_days"], 3)
        self.assertEqual(storage["logstores"]["aggregate"]["ttl_days"], 90)
        indexed_fields = set(storage["logstores"]["raw"]["indexed_fields"])
        for field in (
            "flowId",
            "step",
            "failureKind",
            "copyKey",
            "feedbackSurface",
            "requestId",
            "traceId",
        ):
            self.assertIn(field, indexed_fields)

        login = jobs["login_lifecycle"]
        login_dimensions = set(login["dimensions"])
        for dimension in (
            "eventType",
            "action",
            "operationId",
            "step",
            "provider",
            "failureKind",
            "recoveryAction",
            "copyKey",
            "feedbackSurface",
        ):
            self.assertIn(dimension, login_dimensions)
        for sensitive in (
            "phone",
            "otpCode",
            "bindingTicket",
            "providerTicket",
            "token",
            "requestId",
            "traceId",
        ):
            self.assertNotIn(sensitive, login_dimensions)

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

        stalled = rules["LoginClientStateStalled"]
        self.assertEqual(stalled["for"], "1m")
        self.assertIn('result="stalled"', stalled["expr"])
        self.assertIn("ops_login_funnel_events_total", stalled["expr"])

        duplicate = rules["LoginTerminalDuplicateSuppressed"]
        self.assertIn('result="duplicate_suppressed"', duplicate["expr"])

        operation_failure = rules["LoginClientOperationFailureRateHigh"]
        self.assertIn("ops_login_operation_events_total", operation_failure["expr"])
        self.assertIn("> 0.05", operation_failure["expr"])

        binding = rules["LoginPhoneBindingAbandonmentHigh"]
        self.assertIn('action="login_phone_binding"', binding["expr"])
        self.assertIn('result="cancelled"', binding["expr"])
        self.assertIn('result="required"', binding["expr"])

    def test_user_control_plane_owns_sampling_but_not_logstore_retention(self) -> None:
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
            values["sys.user.auth.success_detail_sample_ratio"]["rollout"],
            "progressive",
        )
        for key in (
            "sys.user.auth.raw_event_retention_days",
            "sys.user.auth.aggregate_metric_retention_days",
        ):
            self.assertNotIn(key, values)


if __name__ == "__main__":
    unittest.main()

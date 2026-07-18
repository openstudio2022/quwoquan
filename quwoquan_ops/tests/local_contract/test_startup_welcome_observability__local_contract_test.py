import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


class StartupWelcomeObservabilityContractTest(unittest.TestCase):
    def test_event_payload_versions_the_petal_bloom_motion_spec(self) -> None:
        timeline = (
            REPO_ROOT
            / "quwoquan_app/lib/ui/welcome/welcome_motion_timeline.dart"
        ).read_text(encoding="utf-8")
        self.assertIn("'motionSpecVersion': motionSpecVersion", timeline)
        self.assertIn("'petal_bloom_v2'", timeline)

    def test_dashboard_uses_only_real_low_cardinality_startup_metrics(self) -> None:
        dashboards_root = (
            REPO_ROOT / "quwoquan_ops/observability/monitoring/dashboards"
        )
        dashboard_path = dashboards_root / "l1_user_experience.json"
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        encoded = json.dumps(dashboard, ensure_ascii=False)
        for token in (
            "ops_startup_phase_duration_seconds",
            "ops_startup_phase_total",
            "journal_drop",
        ):
            self.assertIn(token, encoded)
        all_dashboards = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(dashboards_root.glob("*.json"))
        )
        for retired_metric in (
            "ops_event_metrics_bucket",
            "ops_events_total",
            "app_api_latency_ms_bucket",
        ):
            self.assertNotIn(retired_metric, all_dashboards)

    def test_online_alerts_and_release_thresholds_have_distinct_owners(self) -> None:
        alerts = (
            REPO_ROOT
            / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
        ).read_text(encoding="utf-8")
        thresholds = (
            REPO_ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
        ).read_text(encoding="utf-8")
        sls = (
            REPO_ROOT
            / "quwoquan_ops/environments/cloud-providers/aliyun/sls/product_telemetry.yaml"
        ).read_text(encoding="utf-8")

        for alert in (
            "StartupFlutterFirstFrameP95High",
            "StartupShellFirstPaintP95High",
            "StartupRecoveryRateHigh",
            "StartupTerminalFunnelIncomplete",
            "StartupTelemetryJournalDrop",
        ):
            self.assertIn(alert, alerts)
        for sls_contract in (
            "app-product-telemetry-performance-hourly",
            "eventType:app_startup",
            "product-startup-content-p95-high",
            "condition: p95Ms > 3000",
            "product-startup-error-rate-high",
            "condition: errorRate > 0.001",
        ):
            self.assertIn(sls_contract, sls)
        for threshold in (
            "shell_first_paint_target_ms: 3000",
            "welcome_exit_hard_ms: 6000",
            "overlay_removed_hard_ms: 6000",
            "replay_1_rate_warn: 0.05",
            "replay_2_rate_warn: 0.005",
            "degraded_or_deadline_rate_critical: 0.001",
        ):
            self.assertIn(threshold, thresholds)

    def test_restricted_startup_metrics_have_a_real_service_producer(self) -> None:
        metrics = (
            REPO_ROOT
            / "quwoquan_service/services/product-ops-service/cmd/api/startup_telemetry_metrics.go"
        ).read_text(encoding="utf-8")
        handler = (
            REPO_ROOT
            / "quwoquan_service/services/product-ops-service/cmd/api/startup_telemetry_handler.go"
        ).read_text(encoding="utf-8")
        for token in (
            "ops_startup_phase_total",
            "ops_startup_phase_duration_seconds",
            "recordStartupTelemetryMetrics",
            "ReportStartupDiagnostics",
        ):
            self.assertIn(token, metrics + handler)


if __name__ == "__main__":
    unittest.main()

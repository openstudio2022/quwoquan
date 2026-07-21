from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


class RtcMediaQoeObservabilityContractTest(unittest.TestCase):
    def test_rtc_qoe_rollup_and_release_alerts_share_low_cardinality_facts(self) -> None:
        resource = yaml.safe_load(
            (
                ROOT
                / "quwoquan_ops/environments/cloud-providers/aliyun/sls/product_telemetry.yaml"
            ).read_text(encoding="utf-8")
        )
        jobs = {
            item["name"]: item for item in resource["spec"]["scheduledSql"]["jobs"]
        }
        job = jobs["app-product-telemetry-rtc-qoe-hourly"]
        self.assertEqual(job["rowKind"], "rtc_qoe")
        self.assertIn(
            "callType,result,mediaConnected,networkQuality,disconnectReason,failReasonCode",
            job["sql"],
        )
        self.assertIn("connectTimeHistogram", job["sql"])
        self.assertIn("reconnectCount", job["sql"])
        self.assertNotIn("callId", job["sql"])
        self.assertNotIn("userId", job["sql"])
        self.assertNotIn("sessionId", job["sql"])

        alerts = {item["name"]: item for item in resource["spec"]["alerts"]}
        for name in (
            "product-rtc-media-connect-rate-low",
            "product-rtc-media-connect-p95-high",
            "product-rtc-unexpected-disconnect-rate-high",
        ):
            self.assertIn(name, alerts)
            self.assertIn("sampleCount >= 50", alerts[name]["condition"])

        self.assertIn(
            "connectRate < 0.98",
            alerts["product-rtc-media-connect-rate-low"]["condition"],
        )
        self.assertIn(
            "result<>'abandoned'",
            alerts["product-rtc-media-connect-rate-low"]["query"],
        )
        self.assertIn(
            "result<>'abandoned' AND mediaConnected='true'",
            alerts["product-rtc-media-connect-rate-low"]["query"],
        )
        self.assertIn(
            "p95Ms > 3000",
            alerts["product-rtc-media-connect-p95-high"]["condition"],
        )
        self.assertIn(
            "disconnectRate > 0.02",
            alerts["product-rtc-unexpected-disconnect-rate-high"]["condition"],
        )

        dashboard = json.loads(
            (
                ROOT
                / "quwoquan_ops/observability/monitoring/dashboards/l2_rtc_media_commercial.json"
            ).read_text(encoding="utf-8")
        )["dashboard"]
        rendered = json.dumps(dashboard, ensure_ascii=False)
        self.assertIn("livekit_packet_loss_percent_bucket", rendered)
        self.assertNotIn("livekit_node_dropped_packets", rendered)
        self.assertIn("GetRtcMediaQoeSummary", rendered)
        self.assertIn("app-product-telemetry-rtc-qoe-hourly", rendered)
        self.assertNotIn("callId", rendered)
        self.assertNotIn("userId", rendered)

        prometheus_rules = yaml.safe_load(
            (
                ROOT
                / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
            ).read_text(encoding="utf-8")
        )
        media_group = next(
            group
            for group in prometheus_rules["groups"]
            if group["name"] == "quwoquan_l2_rtc_call"
        )
        media_alerts = {rule["alert"]: rule for rule in media_group["rules"]}
        packet_loss = media_alerts["LiveKitPacketLossP95High"]
        self.assertIn("livekit_packet_loss_percent_bucket", packet_loss["expr"])
        self.assertNotIn("livekit_node_dropped_packets", packet_loss["expr"])
        self.assertIn(
            "livekit_quality_score_bucket",
            media_alerts["LiveKitMedianQualityLow"]["expr"],
        )
        self.assertIn(
            "result='connection_lost'",
            alerts["product-rtc-unexpected-disconnect-rate-high"]["query"],
        )

        alert_drill = yaml.safe_load(
            (
                ROOT
                / "quwoquan_ops/tests/fixtures/rtc_media_alerts.promtest.yaml"
            ).read_text(encoding="utf-8")
        )
        scenarios = {item["name"]: item for item in alert_drill["tests"]}
        self.assertTrue(
            scenarios[
                "livekit_packet_loss_p95_crosses_threshold_and_holds"
            ]["alert_rule_test"][0]["exp_alerts"]
        )
        self.assertEqual(
            scenarios[
                "livekit_packet_loss_p95_below_threshold_stays_clear"
            ]["alert_rule_test"][0]["exp_alerts"],
            [],
        )


if __name__ == "__main__":
    unittest.main()

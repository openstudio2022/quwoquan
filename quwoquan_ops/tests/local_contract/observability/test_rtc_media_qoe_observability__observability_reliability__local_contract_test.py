from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]


class RtcMediaQoeObservabilityContractTest(unittest.TestCase):
    def test_rtc_qoe_rollup_and_release_alerts_share_low_cardinality_facts(self) -> None:
        rollups = yaml.safe_load(
            (
                ROOT
                / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/rollups.yaml"
            ).read_text(encoding="utf-8")
        )
        job = next(item for item in rollups["jobs"] if item["row_kind"] == "rtc_qoe")
        for dimension in ("callType", "result", "mediaConnected", "networkQuality", "disconnectReason", "failReasonCode"):
            self.assertIn(dimension, job["dimensions"])
        measures = {item["name"] for item in job["measures"]}
        self.assertIn("connectTimeHistogram", measures)
        self.assertIn("reconnectCount", measures)
        self.assertNotIn("callId", job["dimensions"])
        self.assertNotIn("userId", job["dimensions"])
        self.assertNotIn("sessionId", job["dimensions"])

        alert_policy = yaml.safe_load((ROOT / "quwoquan_ops/observability/elasticsearch/product_telemetry_alerts.yaml").read_text(encoding="utf-8"))["spec"]
        alerts = {item["name"]: item for item in alert_policy["alerts"]}
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
        # 分子（mediaConnected=true）由字段级 where 承载，filter 只排除用户主动放弃；
        # 若 filter 同时携带 connected=true 会让 connectRate 恒为 1。
        self.assertEqual(
            alerts["product-rtc-media-connect-rate-low"]["filter"],
            {"excludeResult": "abandoned"},
        )
        self.assertEqual(
            alerts["product-rtc-media-connect-rate-low"]["fields"]["connectedCount"],
            "sum(count) where mediaConnected = true",
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
        )
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
        self.assertEqual(
            alerts["product-rtc-unexpected-disconnect-rate-high"]["fields"]["disconnectCount"],
            "sum(count) where result = connection_lost",
        )
        self.assertEqual(
            alerts["product-rtc-unexpected-disconnect-rate-high"]["filter"],
            {"mediaConnected": True},
        )

        # 该文件已随 make verify-prometheus-rule-tests 真实执行（promtool test rules），
        # 此处只做场景结构断言，不再是未执行的 fixture。
        alert_drill = yaml.safe_load(
            (
                ROOT
                / "quwoquan_ops/observability/monitoring/promtool_tests/rtc_media_alerts_test.yaml"
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

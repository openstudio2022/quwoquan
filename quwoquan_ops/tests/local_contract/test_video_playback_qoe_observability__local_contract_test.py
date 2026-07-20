import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]


class VideoPlaybackQoeObservabilityContractTest(unittest.TestCase):
    def test_qoe_aggregate_and_alerts_keep_low_cardinality_dimensions(self) -> None:
        path = (
            REPO_ROOT
            / "quwoquan_ops/environments/cloud-providers/aliyun/sls/product_telemetry.yaml"
        )
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        jobs = {item["name"]: item for item in document["spec"]["scheduledSql"]["jobs"]}
        qoe_job = jobs["app-product-telemetry-video-qoe-hourly"]

        self.assertEqual(qoe_job["rowKind"], "video_qoe")
        self.assertIn("playbackMode,result", qoe_job["sql"])
        self.assertIn("seekEvidenceSource", qoe_job["sql"])
        self.assertIn("devicePlatform", qoe_job["sql"])
        self.assertIn("networkClass", qoe_job["sql"])
        self.assertIn("effectivePlaybackMs", qoe_job["sql"])
        self.assertIn("nativeFirstFrameSuccessCount", qoe_job["sql"])
        self.assertIn("rebufferSessionCount", qoe_job["sql"])
        self.assertIn("terminalFailureCount", qoe_job["sql"])
        self.assertIn("seekFailureCount", qoe_job["sql"])
        self.assertIn("seekCommandHistogram", qoe_job["sql"])
        self.assertIn("seekSettleHistogram", qoe_job["sql"])
        self.assertNotIn("approx_percentile(", qoe_job["sql"])
        self.assertIn("droppedFrames", qoe_job["sql"])
        self.assertIn("processedVideoFrames", qoe_job["sql"])
        self.assertIn("audioUnderrunCount", qoe_job["sql"])
        self.assertIn("rendererMode", qoe_job["sql"])
        self.assertIn("decoderQueueMode", qoe_job["sql"])
        self.assertNotIn("sessionId", qoe_job["sql"])
        self.assertNotIn("postId", qoe_job["sql"])
        raw_logstore = next(
            item
            for item in document["spec"]["logstores"]
            if item["name"] == "app-product-telemetry-raw"
        )
        indexed_fields = set(raw_logstore["indexes"]["fields"])
        self.assertIn("devicePlatform", indexed_fields)
        self.assertIn("effectivePlaybackMs", indexed_fields)

        alerts = {item["name"]: item for item in document["spec"]["alerts"]}
        for alert_name in (
            "product-video-ready-p95-high",
            "product-video-rebuffer-rate-high",
            "product-video-duration-mismatch-rate-high",
            "product-video-dropped-frame-ratio-high",
            "product-video-audio-underrun-detected",
        ):
            self.assertIn(alert_name, alerts)
            self.assertIn("sampleCount >= 100", alerts[alert_name]["condition"])
        seek_alert = alerts["product-video-seek-command-failure-rate-high"]
        self.assertIn("seekCount >= 100", seek_alert["condition"])
        self.assertIn("failureRate >= 0.005", seek_alert["condition"])
        dropped_frame_alert = alerts["product-video-dropped-frame-ratio-high"]
        self.assertIn("processedFrames >= 1000", dropped_frame_alert["condition"])
        self.assertIn("droppedFrameRatio >= 0.01", dropped_frame_alert["condition"])


if __name__ == "__main__":
    unittest.main()

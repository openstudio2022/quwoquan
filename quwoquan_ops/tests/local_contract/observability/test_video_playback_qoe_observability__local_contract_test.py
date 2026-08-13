import unittest
from pathlib import Path

import yaml

from quwoquan_ops.cli.lib.storage_contract_view import load_storage_contract_view


REPO_ROOT = Path(__file__).resolve().parents[4]


class VideoPlaybackQoeObservabilityContractTest(unittest.TestCase):
    def test_qoe_aggregate_and_alerts_keep_low_cardinality_dimensions(self) -> None:
        path = (
            REPO_ROOT
            / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/rollups.yaml"
        )
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        qoe_job = next(item for item in document["jobs"] if item["row_kind"] == "video_qoe")
        measures = {item["name"] for item in qoe_job["measures"]}

        self.assertIn("playbackMode", qoe_job["dimensions"])
        self.assertIn("result", qoe_job["dimensions"])
        self.assertIn("seekEvidenceSource", qoe_job["dimensions"])
        self.assertIn("devicePlatform", qoe_job["dimensions"])
        self.assertIn("networkClass", qoe_job["dimensions"])
        for measure in (
            "effectivePlaybackMs",
            "nativeFirstFrameSuccessCount",
            "rebufferSessionCount",
            "terminalFailureCount",
            "seekFailureCount",
            "seekCommandHistogram",
            "seekSettleHistogram",
            "droppedFrames",
            "processedVideoFrames",
            "audioUnderrunCount",
        ):
            self.assertIn(measure, measures)
        self.assertIn("rendererMode", qoe_job["dimensions"])
        self.assertIn("decoderQueueMode", qoe_job["dimensions"])
        self.assertNotIn("sessionId", qoe_job["dimensions"])
        self.assertNotIn("postId", qoe_job["dimensions"])
        storage = load_storage_contract_view(
            REPO_ROOT
            / "quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/storage.yaml"
        )
        indexed_fields = set(storage["logstores"]["raw"]["indexed_fields"])
        self.assertIn("devicePlatform", indexed_fields)
        self.assertIn("effectivePlaybackMs", indexed_fields)

        alert_policy = yaml.safe_load(
            (
                REPO_ROOT
                / "quwoquan_ops/observability/elasticsearch/product_telemetry_alerts.yaml"
            ).read_text(encoding="utf-8")
        )["spec"]
        alerts = {item["name"]: item for item in alert_policy["alerts"]}
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

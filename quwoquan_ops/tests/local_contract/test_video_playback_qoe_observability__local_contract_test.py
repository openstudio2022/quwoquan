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
        self.assertNotIn("sessionId", qoe_job["sql"])
        self.assertNotIn("postId", qoe_job["sql"])

        alerts = {item["name"]: item for item in document["spec"]["alerts"]}
        for alert_name in (
            "product-video-ready-p95-high",
            "product-video-rebuffer-rate-high",
            "product-video-duration-mismatch-rate-high",
        ):
            self.assertIn(alert_name, alerts)
            self.assertIn("sampleCount >= 100", alerts[alert_name]["condition"])


if __name__ == "__main__":
    unittest.main()

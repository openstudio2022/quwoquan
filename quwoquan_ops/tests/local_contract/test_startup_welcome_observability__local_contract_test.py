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

    def test_dashboard_exposes_startup_exit_replay_and_frame_metrics(self) -> None:
        dashboard_path = (
            REPO_ROOT
            / "quwoquan_ops/observability/monitoring/dashboards/l1_user_experience.json"
        )
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        encoded = json.dumps(dashboard, ensure_ascii=False)
        for token in (
            "startup_welcome_sequence",
            "shellFirstPaintMs",
            "welcomeExitMs",
            "overlayRemovedMs",
            "replay_count",
            "exit_reason",
            "buildFrameP95Ms",
            "rasterFrameP95Ms",
        ):
            self.assertIn(token, encoded)

    def test_alerts_and_slo_thresholds_match_3s_6s_contract(self) -> None:
        alerts = (
            REPO_ROOT
            / "quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml"
        ).read_text(encoding="utf-8")
        thresholds = (
            REPO_ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
        ).read_text(encoding="utf-8")

        for alert in (
            "StartupWelcomeReplay1RateHigh",
            "StartupWelcomeReplay2RateHigh",
            "StartupWelcomeDegradedRateHigh",
            "StartupWelcomeExitOverDeadline",
            "StartupWelcomeOverlayRemovalOverDeadline",
            "StartupWelcomeConsecutiveSlowFrames",
        ):
            self.assertIn(alert, alerts)
        for threshold in (
            "shell_first_paint_target_ms: 3000",
            "welcome_exit_hard_ms: 6000",
            "overlay_removed_hard_ms: 6000",
            "replay_1_rate_warn: 0.05",
            "replay_2_rate_warn: 0.005",
            "degraded_or_deadline_rate_critical: 0.001",
        ):
            self.assertIn(threshold, thresholds)


if __name__ == "__main__":
    unittest.main()

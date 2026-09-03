"""environment patrol smoke：已发布播放 canary 与远端 Patrol 基线契约。

由综合 smoke 测试按发布播放职责拆出；测试方法与断言保持不变。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke
from quwoquan_ops.tests.support.environment_patrol_smoke_test_support import (
    EnvironmentPatrolSmokeCaseBase,
)


class EnvironmentPatrolSmokePublishedPlaybackContractTest(
    EnvironmentPatrolSmokeCaseBase
):
    def test_alpha_playback_canary_uses_the_current_published_release(self) -> None:
        topology = stackctl.load_environment_topology()
        target = stackctl.get_target(topology, "alpha-local")
        canary = target["playbackCanary"]

        self.assertEqual(canary["source"], "published-release")
        self.assertEqual(canary["workIdEnv"], "VIDEO_PLAYBACK_CANARY_WORK_ID")
        self.assertEqual(
            canary["publicSliceKeyEnv"],
            "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY",
        )
        self.assertEqual(
            smoke._evidence_class_for_runtime("alpha"),
            "user_acceptance_remote",
        )
        self.assertEqual(
            smoke._evidence_class_for_runtime("beta"),
            "user_acceptance_remote",
        )

    def test_beta_playback_canary_uses_the_current_published_release(self) -> None:
        topology = stackctl.load_environment_topology()
        target = stackctl.get_target(topology, "beta-local")
        canary = target["playbackCanary"]

        self.assertEqual(canary["source"], "published-release")
        self.assertEqual(
            canary["workIdEnv"],
            "VIDEO_PLAYBACK_CANARY_WORK_ID",
        )
        self.assertEqual(
            canary["publicSliceKeyEnv"],
            "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY",
        )

    def test_remote_patrol_keeps_125s_video_contract_without_app_bundle(self) -> None:
        profile = ROOT / "quwoquan_data/reference/media_canary/video_playback.yaml"
        self.assertTrue(profile.is_file(), "mediaCanary.profileRef must resolve")
        profile_text = profile.read_text(encoding="utf-8")
        self.assertIn("media-canary-seek-125s", profile_text)
        self.assertIn("durationMs: 125000", profile_text)
        self.assertIn("publicSlicePrefix: media/video/s/media-canary-seek-125s/v1", profile_text)
        self.assertIn("media-canary-hour-boundary-3595s", profile_text)

        # Patrol runner shell 由 APP_PATROL_RUNNER_FILES 门禁要求存在（见
        # quwoquan_ops/gate/scaffold/test_directory_layout/app_layout.py）。
        # "without app bundle" 的判据是该入口只装 setUp/tearDown hook，不预启动
        # App、不聚合用例；真实用例各自 launchPatrolAppOnce。
        runner_main = (
            ROOT / "quwoquan_app/test/user_acceptance/patrol/patrol_test_main.dart"
        ).read_text(encoding="utf-8")
        self.assertIn("patrolSetUp(", runner_main)
        self.assertIn("patrolTearDown(", runner_main)
        self.assertNotIn("patrolTest(", runner_main)
        self.assertNotIn("launchPatrolAppOnce", runner_main)
        harness = (
            ROOT
            / "quwoquan_app/test/support/runtime/patrol/"
            "patrol_environment_harness.dart"
        ).read_text(encoding="utf-8")
        self.assertNotIn("buildAlphaCloudOverrides", harness)
        self.assertNotIn("providerScopeOverrides", harness)
        self.assertIn("launchPatrolAppOnce($)", harness)


if __name__ == "__main__":
    unittest.main()

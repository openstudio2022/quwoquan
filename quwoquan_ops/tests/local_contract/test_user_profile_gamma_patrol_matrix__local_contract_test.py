"""R-UPROF-004：用户主页 Patrol 必须实际进入 Gamma 设备矩阵。

仅在 ``uiJourneys`` 登记测试文件不足以形成 UAT 证据；release profile 必须选择
``user-profile`` matrix kind，而 self-hosted workflow 必须从同一注册表解析 Patrol
target 后执行，避免另写路径造成漂移。
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
SUITES_PATH = ROOT / "quwoquan_ops/environments/gamma_validation_suites.json"
WORKFLOW_PATH = (
    ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml"
)


class UserProfileGammaPatrolMatrixContractTest(unittest.TestCase):
    def test_release_profiles_schedule_registered_profile_patrol(self) -> None:
        suites = json.loads(SUITES_PATH.read_text(encoding="utf-8"))
        journey = suites["uiJourneys"]["user_profile_journey_patrol"]

        self.assertEqual(journey["runner"], "patrol")
        target = str(journey["target"]).strip()
        self.assertTrue(target)
        self.assertTrue(
            (ROOT / "quwoquan_app" / target).is_file()
            if not target.startswith("quwoquan_app/")
            else (ROOT / target).is_file(),
            "用户主页 Gamma Patrol target 必须存在",
        )

        for profile_name in ("nightly_full", "release_candidate"):
            profile = suites["profiles"][profile_name]
            self.assertIn(
                "user_profile_journey_patrol",
                profile["uiJourneys"],
                f"{profile_name} 必须声明用户主页 UAT 旅程",
            )
            self.assertIn(
                "user-profile",
                profile["deviceMatrix"]["matrixKinds"],
                f"{profile_name} 必须在设备矩阵实际调度用户主页 UAT",
            )

    def test_self_hosted_workflow_resolves_registered_target(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        self.assertIn(
            'matrix_kind}" = "user-profile"',
            workflow,
            "self-hosted workflow 必须识别 user-profile matrix kind",
        )
        self.assertIn(
            'suites["uiJourneys"].get("user_profile_journey_patrol")',
            workflow,
            "workflow 必须从 gamma registry 解析用户主页 Patrol target",
        )
        self.assertIn(
            "run_local_gamma_t4.sh",
            workflow,
            "workflow 必须经统一 Gamma Patrol runner 记录设备证据",
        )


if __name__ == "__main__":
    unittest.main()

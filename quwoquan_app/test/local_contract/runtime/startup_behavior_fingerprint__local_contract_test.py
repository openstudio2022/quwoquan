# spec_ref: specs/feature-tree/spec.md#uat-003
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
#
# BehaviorFingerprint 派生投影契约：对同一 runtime 输入改变 launch
# provenance / install channel / BuildMode / 设备形态，规范化行为指纹
# 必须不变；行为语义位（配置完成态、canonical terminal、failureCode、
# release identity、恢复动作）变化必须被等价断言抓住。

import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/runtime/platform"))

from startup_environment_matrix.behavior_fingerprint import (
    derive_behavior_fingerprint,
    fingerprint_equivalence_issues,
)


def _sample(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "runtimeEnv": "gamma",
        "runtimeTarget": "gamma-local",
        "platform": "android",
        "runtimeConfigurationState": "complete",
        "missingDefineKeys": [],
        "canonicalTerminal": "routerShell",
        "watchdogOutcome": "flutter_first_frame",
        "failureCode": "",
        "launcherResolution": {"matchesExpectedGate": True},
        # 入口/身份/时序维度：指纹必须对它们不敏感。
        "launchProvenance": "canonical_launcher",
        "deviceKind": "android-simulator",
        "deviceId": "emulator-5554",
        "attemptId": "attempt-a",
        "rendererFirstFrameMs": 812,
        "safeTerminalMs": 1450,
    }
    payload.update(overrides)
    return payload


class BehaviorFingerprintContractTest(unittest.TestCase):
    def test_entry_dimensions_do_not_change_the_fingerprint(self) -> None:
        base = derive_behavior_fingerprint(_sample(), release_id="rel-1")
        varied = derive_behavior_fingerprint(
            _sample(
                launchProvenance="workspace_ide_debug",
                deviceKind="android-physical",
                deviceId="R5CT10ABCDE",
                attemptId="attempt-b",
                rendererFirstFrameMs=2200,
                safeTerminalMs=3900,
            ),
            release_id="rel-1",
        )
        self.assertEqual(base, varied)

    def test_behavior_bits_change_the_fingerprint(self) -> None:
        base = derive_behavior_fingerprint(_sample())
        for overrides in (
            {"canonicalTerminal": "safeShell"},
            {"failureCode": "STARTUP.CONTENT.PROTOCOL_FAILURE"},
            {"runtimeConfigurationState": "incomplete"},
            {"watchdogOutcome": "native_recovery"},
            {"launcherResolution": {"matchesExpectedGate": False}},
        ):
            varied = derive_behavior_fingerprint(_sample(**overrides))
            self.assertNotEqual(base, varied, overrides)

    def test_release_identity_is_part_of_the_fingerprint(self) -> None:
        bound = derive_behavior_fingerprint(_sample(), release_id="rel-1")
        other = derive_behavior_fingerprint(_sample(), release_id="rel-2")
        self.assertNotEqual(bound, other)

    def test_equivalence_passes_across_entries_and_platform_groups(self) -> None:
        samples = [
            _sample(),
            _sample(
                launchProvenance="release_package",
                deviceKind="android-physical",
                attemptId="attempt-b",
            ),
            _sample(
                platform="ios",
                launchProvenance="workspace_ide_debug",
                deviceKind="ios-simulator",
                attemptId="attempt-c",
                launcherResolution=None,
            ),
        ]
        self.assertEqual(
            fingerprint_equivalence_issues(samples, label="evidence.json"),
            [],
        )

    def test_equivalence_reports_divergence_within_a_platform(self) -> None:
        samples = [
            _sample(),
            _sample(
                launchProvenance="release_package",
                attemptId="attempt-b",
                canonicalTerminal="safeShell",
            ),
        ]
        issues = fingerprint_equivalence_issues(samples, label="evidence.json")
        self.assertEqual(len(issues), 1)
        self.assertIn("behavior fingerprint diverged", issues[0])
        self.assertIn("launchProvenance=release_package", issues[0])


if __name__ == "__main__":
    unittest.main()

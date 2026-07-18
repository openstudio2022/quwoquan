from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.verify_runtime_media_t4_evidence import (
    MATRIX_SCHEMA,
    MATRIX_SCENARIO,
    REPORT_SCHEMA,
    SCENARIO,
    validate_evidence_document,
)


def _report(*, target: str = "gamma-local", env: str = "gamma") -> dict[str, object]:
    return {
        "schema": REPORT_SCHEMA,
        "scenario": SCENARIO,
        "status": "passed",
        "dryRun": False,
        "startedAt": "2026-07-16T00:00:00Z",
        "endedAt": "2026-07-16T00:01:00Z",
        "environment": {
            "target": target,
            "env": env,
            "rolloutStage": "gray-initial" if target == "prod-hosted" else "local",
            "mediaVideoBaseUrl": "https://gamma-video.example.test",
            "commitSha": "abcdef0123456789",
            "configHash": "sha256:config",
        },
        "media": {
            "publicSliceKey": "media/video/s/release-video/post/canary.mp4",
        },
        "serviceEvidence": {
            "videoRange": {"statusCode": 206, "mimeType": "video/mp4"},
        },
        "uiEvidence": {
            "stageRendered": True,
            "playerReady": True,
            "playerError": False,
            "reportPath": ".qwq_output/env/gamma/runs/report.json",
            "screenshotPath": ".qwq_output/env/gamma/runs/after.png",
        },
    }


class RuntimeMediaT4EvidenceContractTest(unittest.TestCase):
    def test_accepts_non_dry_run_gamma_ready_report(self) -> None:
        self.assertEqual(validate_evidence_document(_report()), [])

    def test_rejects_missing_native_player_ready_evidence(self) -> None:
        evidence = _report()
        evidence["uiEvidence"]["playerReady"] = False  # type: ignore[index]

        issues = validate_evidence_document(evidence)

        self.assertTrue(any("playerReady" in issue for issue in issues), issues)

    def test_rejects_missing_video_stage_evidence(self) -> None:
        evidence = _report()
        evidence["uiEvidence"]["stageRendered"] = False  # type: ignore[index]

        issues = validate_evidence_document(evidence)

        self.assertTrue(any("stageRendered" in issue for issue in issues), issues)

    def test_rejects_dry_run_and_non_range_video_evidence(self) -> None:
        evidence = _report()
        evidence["dryRun"] = True
        evidence["serviceEvidence"]["videoRange"]["statusCode"] = 200  # type: ignore[index]

        issues = validate_evidence_document(evidence)

        self.assertTrue(any("dryRun" in issue for issue in issues), issues)
        self.assertTrue(any("statusCode" in issue for issue in issues), issues)

    def test_rejects_production_fixture_and_wrong_rollout_stage(self) -> None:
        evidence = _report(target="prod-hosted", env="prod")
        evidence["environment"]["rolloutStage"] = "full"  # type: ignore[index]
        evidence["media"]["publicSliceKey"] = "media/video/s/fixture-video/post/sample.mp4"  # type: ignore[index]

        issues = validate_evidence_document(evidence)

        self.assertTrue(any("gray-initial" in issue for issue in issues), issues)
        self.assertTrue(any("fixture/mock/seed/test" in issue for issue in issues), issues)

    def test_matrix_validates_every_report(self) -> None:
        beta = _report(target="beta-local", env="beta")
        gamma = _report()
        production = _report(target="prod-hosted", env="prod")
        production["media"]["publicSliceKey"] = (  # type: ignore[index]
            "media/video/s/release-video-20260716/post/canary.mp4"
        )
        matrix = {
            "schema": MATRIX_SCHEMA,
            "scenario": MATRIX_SCENARIO,
            "reports": [beta, gamma, production],
        }

        self.assertEqual(validate_evidence_document(matrix), [])

        broken = copy.deepcopy(matrix)
        broken["reports"][1]["uiEvidence"]["playerError"] = True
        issues = validate_evidence_document(broken)
        self.assertTrue(any("reports[1].uiEvidence.playerError" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()

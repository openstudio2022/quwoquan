"""App content live probe phase-scope contracts.

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl


def _plan(*, include_search: bool) -> dict[str, object]:
    plan: dict[str, object] = {
        "videoPagination": {"pageSize": 20, "expectedWorkIds": ["video-001"]},
        "mediaChecks": {"automatic": True},
        "orderedSamples": [
            {
                "sampleId": "video-001",
                "carrier": "video",
                "objectId": "video-001",
                "objectRef": "objects/posts/video/title/1",
                "objectDigest": "sha256:" + "7" * 64,
            }
        ],
    }
    if include_search:
        plan["searchCanaries"] = [
            {
                "kind": kind,
                "query": f"query-{kind}",
                "expectedObjectType": object_type,
                "expectedObjectId": f"id-{kind}",
            }
            for kind, object_type in (
                ("post", "content.post"),
                ("homepage", "entity.homepage"),
                ("persona", "user.profile"),
            )
        ]
    return plan


def _readiness(tmp_path: Path, *, phase: str) -> Path:
    path = tmp_path / phase / "release-readiness.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"readinessPhase": phase}), encoding="utf-8")
    return path


class StackctlAppContentReleaseProbePhaseScopeTest(unittest.TestCase):
    def test_consumer_skips_search_but_keeps_page_media_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            captured: dict[str, object] = {}

            def probe(*args: object, **kwargs: object):
                captured.update(kwargs)
                report_path = Path(str(args[2])) / "integration-probe.json"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                sample = kwargs["release_samples"][0]
                report_path.write_text(
                    json.dumps(
                        {
                            "status": "passed",
                            "checks": [
                                {
                                    "name": "release_sample",
                                    "url": "https://alpha.example/content/posts/runtime-video-001",
                                    "statusCode": 200,
                                    "ok": True,
                                    **sample,
                                    "returnedObjectId": sample["readObjectId"],
                                    "returnedContentType": sample["expectedContentType"],
                                    "responseDigest": "sha256:" + "1" * 64,
                                    "responseBytes": 1,
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                return {"ok": True, "reportPath": str(report_path)}, "", []

            with (
                mock.patch.object(
                    stackctl,
                    "_run_environment_integration_probe",
                    side_effect=probe,
                ),
                mock.patch.object(stackctl, "output_root", return_value=root),
                mock.patch.object(
                    stackctl,
                    "resolve_release_sample_requests",
                    return_value={
                        "milestone": "",
                        "releaseUatSamplePlanRef": "uat/sample_plan.json",
                        "releaseUatSamplePlanDigest": "sha256:" + "2" * 64,
                        "readinessReceiptRef": "consumer/release-readiness.json",
                        "readinessReceiptFileSha256": "sha256:" + "3" * 64,
                        "homepageApiVerificationRef": "consumer/homepage.json",
                        "homepageApiVerificationFileSha256": "sha256:" + "4" * 64,
                        "contentImportReportRef": "consumer/import.json",
                        "contentImportReportFileSha256": "sha256:" + "5" * 64,
                        "samples": [
                            {
                                "sampleId": "video-001",
                                "carrier": "video",
                                "objectRef": "objects/posts/video/title/1",
                                "objectDigest": "sha256:" + "7" * 64,
                                "sourceReadback": "feedQueries.typed_video",
                                "sourceObjectId": "video-001",
                                "ordinal": 1,
                                "readObjectId": "runtime-video-001",
                                "expectedContentType": "video",
                            }
                        ]
                    },
                ),
            ):
                result = stackctl._run_app_content_release_probe(
                    target="alpha-local",
                    readiness_path=_readiness(root, phase="consumer"),
                    app_uat_plan=_plan(include_search=False),
                    report_dir=root / "probe",
                )

        self.assertEqual(
            captured["only_checks"],
            (
                "video_book_feed",
                "premium_feed",
                "feed_media_slices",
                "media_sample",
                "release_sample",
            ),
        )
        self.assertEqual(captured["release_search_canaries"], [])
        self.assertEqual(result["readinessPhase"], "consumer")
        self.assertIs(result["searchCanariesRequired"], False)
        self.assertEqual(result["searchCanaries"], [])

    def test_lifecycle_phases_still_require_search_canaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for phase in ("research", "commercial"):
                with self.subTest(phase=phase):
                    with self.assertRaisesRegex(
                        ValueError,
                        "App content UAT plan is incomplete",
                    ):
                        stackctl._run_app_content_release_probe(
                            target="alpha-local",
                            readiness_path=_readiness(root, phase=phase),
                            app_uat_plan=_plan(include_search=False),
                            report_dir=root / "probe",
                        )


if __name__ == "__main__":
    unittest.main()

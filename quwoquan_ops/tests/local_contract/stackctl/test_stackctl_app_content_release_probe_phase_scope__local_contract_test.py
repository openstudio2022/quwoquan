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

            def probe(*_args: object, **kwargs: object):
                captured.update(kwargs)
                return {"ok": True, "reportPath": "consumer-probe.json"}, "", []

            with mock.patch.object(
                stackctl,
                "_run_environment_integration_probe",
                side_effect=probe,
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

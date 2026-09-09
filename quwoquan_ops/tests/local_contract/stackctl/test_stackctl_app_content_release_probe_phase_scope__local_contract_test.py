"""App content live probe phase-scope contracts.

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
"""

from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl

def _plan(*, include_search: bool) -> dict[str, object]:
    plan: dict[str, object] = {
        "videoPagination": {"pageSize": 20, "expectedWorkIds": ["video-001"]},
        "mediaChecks": {
            "automatic": True,
            **{name: {"expectedPostIds": ["runtime-video-001"]} for name in (
                "homepageRecommendation", "typedVideo", "premiumVideo",
            )},
        },
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
                ("article", "content.post"),
                ("homepage", "entity.homepage"),
                ("image", "content.post"),
                ("video", "content.post"),
            )
        ]
    return plan


def _readiness(tmp_path: Path) -> Path:
    from quwoquan_ops.tests.support.test_data_verification_test_support import _readiness as receipt

    path = tmp_path / "release-readiness.json"
    path.write_text(json.dumps(receipt(
        environment="alpha", post_ids=("runtime-video-001",),
    )), encoding="utf-8")
    return path


class StackctlAppContentReleaseProbePhaseScopeTest(unittest.TestCase):
    def test_retired_research_modules_are_physically_absent(self) -> None:
        for module in (
            "quwoquan_ops.cli.commands.research_consumer_credential",
            "quwoquan_ops.cli.commands.research_isolation_probe",
            "quwoquan_ops.cli.lib.research_consumer_credential",
            "quwoquan_ops.cli.lib.research_content_isolation",
            "quwoquan_ops.cli.lib.research_isolation_proof_document",
            "quwoquan_ops.cli.lib.research_isolation_runtime_probe",
            "quwoquan_ops.cli.lib.research_isolation_runtime_probe_media",
            "quwoquan_ops.cli.lib.local_environment_auth.research_identity",
        ):
            with self.subTest(module=module):
                self.assertIsNone(importlib.util.find_spec(module))

    def test_retired_research_commands_are_not_registered(self) -> None:
        parser = stackctl.build_parser()
        for command in ("research-consumer-credential", "research-isolation-probe"):
            with self.subTest(command=command), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    parser.parse_args([command, "--help"])
                self.assertEqual(error.exception.code, 2)

    def test_all_environment_declarations_are_category_free(self) -> None:
        environments = Path(stackctl.__file__).resolve().parents[1] / "environments"
        for environment in ("alpha", "beta", "gamma", "prod"):
            with self.subTest(environment=environment):
                declaration = json.loads(
                    (environments / environment / "runtime.yaml").read_text(encoding="utf-8")
                )
                self.assertNotIn("productLifecycleState", declaration)
                self.assertNotIn("researchIsolationPolicy", declaration)
                for target in declaration["targets"].values():
                    self.assertNotIn("researchIdentity", target)

    def test_release_schema_and_cli_reject_category_and_phase_selectors(self) -> None:
        root = Path(stackctl.__file__).resolve().parents[2]
        for name in ("release_attestation", "environment_release_readiness"):
            schema = json.loads((root / f"quwoquan_data/schema/release/{name}.schema.json").read_text(encoding="utf-8"))
            self.assertIs(schema["additionalProperties"], False)
            for field in ("releaseClass", "productLifecycleState", "readinessPhase"):
                self.assertNotIn(field, schema["properties"])
        parser = stackctl.build_parser()
        for environment in ("alpha", "beta", "gamma", "prod"):
            args = parser.parse_args(["content-readiness", "--env", environment])
            self.assertEqual(args.env, environment)
            self.assertFalse(hasattr(args, "phase"))
            for phase in ("import", "consumer", "production", "research", "commercial"):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    parser.parse_args(["content-readiness", "--phase", phase, "--env", environment])
                self.assertEqual(error.exception.code, 2)

    def test_resource_group_remains_independent_of_release_lifecycle(self) -> None:
        environments = Path(stackctl.__file__).resolve().parents[1] / "environments"
        schema = json.loads((environments / "evidence/environment_execution_request.schema.json").read_text(encoding="utf-8"))
        resource_group = schema["properties"]["resourceGroup"]["const"]
        self.assertEqual(resource_group, "workstation-commercial-runtime")
        for environment in ("alpha", "beta", "gamma", "prod"):
            declaration = json.loads((environments / environment / "runtime.yaml").read_text(encoding="utf-8"))
            for target in declaration["targets"].values():
                if target["backend"] == "local":
                    self.assertEqual(target["localResourceGroup"], resource_group)

    def test_default_release_requires_search_and_exact_page_media_checks(self) -> None:
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
                    readiness_path=_readiness(root),
                    app_uat_plan=_plan(include_search=True),
                    report_dir=root / "probe",
                )

        self.assertEqual(
            captured["only_checks"],
            (
                "content_feed", "homepage_recommend", "video_book_feed",
                "premium_feed", "feed_media_slices", "global_search",
                "media_sample", "release_sample", "author_posts_contract",
            ),
        )
        self.assertEqual(len(captured["release_search_canaries"]), 4)
        self.assertNotIn("readinessPhase", result)
        self.assertIs(result["searchCanariesRequired"], True)
        self.assertEqual(len(result["searchCanaries"]), 4)

    def test_default_release_rejects_missing_search_or_exact_media_before_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for missing in ("searchCanaries", "homepageRecommendation", "typedVideo", "premiumVideo"):
                plan = _plan(include_search=True)
                (plan if missing == "searchCanaries" else plan["mediaChecks"]).pop(missing)
                with self.subTest(missing=missing), mock.patch.object(
                    stackctl, "_run_environment_integration_probe"
                ) as probe, self.assertRaisesRegex(ValueError, "App content UAT plan is incomplete"):
                    stackctl._run_app_content_release_probe(
                        target="alpha-local", readiness_path=_readiness(root),
                        app_uat_plan=plan, report_dir=root / "probe",
                    )
                probe.assert_not_called()

if __name__ == "__main__":
    unittest.main()

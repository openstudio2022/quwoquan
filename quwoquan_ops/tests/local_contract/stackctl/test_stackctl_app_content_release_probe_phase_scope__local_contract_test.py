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
from quwoquan_ops.cli.lib.deployment_candidate_manifest.constants import (
    RELEASE_INPUT_CLASSIFICATIONS,
    _RELEASE_LIFECYCLE_CLASSES,
)


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

    def test_all_environment_declarations_use_one_production_lifecycle(self) -> None:
        environments = Path(stackctl.__file__).resolve().parents[1] / "environments"
        for environment in ("alpha", "beta", "gamma", "prod"):
            with self.subTest(environment=environment):
                declaration = json.loads(
                    (environments / environment / "runtime.yaml").read_text(encoding="utf-8")
                )
                self.assertEqual(declaration["productLifecycleState"], "production")
                self.assertNotIn("researchIsolationPolicy", declaration)
                for target in declaration["targets"].values():
                    self.assertNotIn("researchIdentity", target)

    def test_release_schema_cli_and_declarations_share_production_identity(self) -> None:
        root = Path(stackctl.__file__).resolve().parents[2]
        self.assertEqual(_RELEASE_LIFECYCLE_CLASSES, {"production"})
        self.assertEqual(RELEASE_INPUT_CLASSIFICATIONS, {"production_inputs"})
        for name in ("release_attestation", "environment_release_readiness"):
            schema = json.loads((root / f"quwoquan_data/schema/release/{name}.schema.json").read_text(encoding="utf-8"))
            for field in ("releaseClass", "productLifecycleState"):
                self.assertEqual(schema["properties"][field]["enum"], ["production"])
        self.assertEqual(schema["properties"]["readinessPhase"]["enum"], ["production"])
        # import/consumer 是 Ops 能力探针阶段，不是第二种 immutable release 类别。
        parser = stackctl.build_parser()
        for environment in ("alpha", "beta", "gamma", "prod"):
            for phase in ("import", "consumer", "production"):
                args = parser.parse_args(["content-readiness", "--phase", phase, "--env", environment])
                self.assertEqual((args.phase, args.env), (phase, environment))
            for phase in ("research", "commercial"):
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

    def test_retired_lifecycle_phases_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for phase in ("research", "commercial"):
                with self.subTest(phase=phase):
                    with self.assertRaisesRegex(
                        ValueError,
                        "requires consumer or production readiness",
                    ):
                        stackctl._run_app_content_release_probe(
                            target="alpha-local",
                            readiness_path=_readiness(root, phase=phase),
                            app_uat_plan=_plan(include_search=False),
                            report_dir=root / "probe",
                        )


if __name__ == "__main__":
    unittest.main()

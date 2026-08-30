"""app-content-uat immutable candidate/startup/release identity contract.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.test_data.capabilities.user_service import (
    AUTHENTICATED_ACTORS,
)


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


BASELINE = _digest("1")
RELEASE_TRAIN = _digest("2")
MANIFEST_DIGEST = _digest("3")
PACKAGE_DIGEST = _digest("4")
CONFIGURATION_DIGEST = _digest("5")
RUNTIME_CONFIG_DIGEST = _digest("6")
ENVIRONMENT_RUNTIME_DIGEST = _digest("7")
PROVIDER_DIGEST = _digest("8")
OBSERVABILITY_DIGEST = _digest("9")
ARTIFACT_DIGEST = _digest("a")
SOURCE_CAPSULE_DIGEST = _digest("b")
CONTRACT_GRAPH_DIGEST = _digest("e")


class AppContentPreflightUatImmutableBindingTest(unittest.TestCase):
    def _fixture(self, root: Path) -> dict[str, object]:
        readiness_path = (
            root
            / "env/alpha/runs/data-release/release-a/verify-a/release-readiness.json"
        )
        readiness_path.parent.mkdir(parents=True)
        readiness: dict[str, object] = {
            "passed": True,
            "environment": "alpha",
            "releaseId": "release-a",
            "verifyRunId": "verify-a",
            "manifestDigest": MANIFEST_DIGEST,
            "readinessPhase": "research",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "importRunId": "import-a",
            "sourceIdentities": [{"executionId": "execution-a"}],
            "sourceIdentitySetDigest": _digest("d"),
            "postIds": ["article-a", "image-a", "video-a"],
            "creatorIds": ["creator-a"],
            "entityRefs": ["/entity/entity-a"],
            "tagRefs": ["tag-a"],
            "mediaAssetIds": ["media-a"],
        }
        unsigned = dict(readiness)
        readiness["verificationChecksum"] = stackctl._canonical_document_checksum(
            unsigned
        )
        readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
        selection_evidence = {
            "poolDigest": _digest("1"),
            "sourceIdentitySetDigest": _digest("d"),
            "canonicalMerkle": _digest("2"),
            "releaseContentsDigest": _digest("3"),
            "releaseEntityCohortDigest": _digest("4"),
        }
        release_digest = stackctl._canonical_document_checksum(
            {
                "schema": "quwoquan_data.release_uat_sample_plan_identity",
                "releaseId": "release-a",
                "canonicalMerkle": selection_evidence["canonicalMerkle"],
                "selectionEvidence": selection_evidence,
            }
        )
        sample_distribution = {
            "homepage": 1,
            "article": 1,
            "image": 1,
            "video": 1,
        }
        entry_carrier_cells = [
            {
                "entry": entry,
                "carrier": carrier,
                "applicability": "required",
                "specRef": (
                    "specs/feature-tree/runtime/runtime-config/"
                    "environment-topology-and-packaging/spec.md#req-006"
                ),
                "runnerClass": f"qwq_app.content_uat.{entry}.{carrier}.v1",
            }
            for entry in (
                "feed",
                "search",
                "recommendation",
                "direct_or_object_route",
            )
            for carrier in ("homepage", "article", "image", "video")
        ]
        samples = [
            {
                "sampleId": "canary-homepage-001",
                "carrier": "homepage",
                "objectId": "/entity/entity-a",
                "objectRef": "objects/entities/entity-a",
                "objectDigest": "sha256:" + "8" * 64,
            },
            {
                "sampleId": "canary-article-001",
                "carrier": "article",
                "objectId": "article-a",
                "objectRef": "objects/posts/article/work-a/1",
                "objectDigest": "sha256:" + "7" * 64,
            },
            {
                "sampleId": "canary-image-001",
                "carrier": "image",
                "objectId": "image-a",
                "objectRef": "objects/posts/image/work-a/1",
                "objectDigest": "sha256:" + "5" * 64,
            },
            {
                "sampleId": "canary-video-001",
                "carrier": "video",
                "objectId": "video-a",
                "objectRef": "objects/posts/video/work-a/1",
                "objectDigest": "sha256:" + "5" * 64,
            },
        ]
        sample_plan = {
            "schema": "quwoquan_data.release_uat_sample_plan",
            "releaseId": "release-a",
            "releaseDigest": release_digest,
            "milestone": None,
            "selectionEvidence": selection_evidence,
            "eligiblePopulationCounts": dict(sample_distribution),
            "exactCohortCounts": dict(sample_distribution),
            "entryCarrierCells": entry_carrier_cells,
            "sampleStrategy": {
                "name": "baseline_per_required_carrier",
                "version": 1,
                "seedDigest": stackctl._canonical_document_checksum(
                    {
                        "releaseDigest": release_digest,
                        "sampleDistribution": sample_distribution,
                    }
                ),
                "carrierOrder": ["homepage", "article", "image", "video"],
                "sortKey": "identity",
                "direction": "ascending",
                "objectDigestAlgorithm": "sha256-path-blob-merkle",
                "sampleDistribution": sample_distribution,
            },
            "sampleCount": 4,
            "samples": samples,
        }
        sample_plan_path = root / "release/payload/uat/sample_plan.json"
        sample_plan_path.parent.mkdir(parents=True)
        sample_plan_path.write_text(
            json.dumps(sample_plan, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        sample_plan_digest = (
            "sha256:"
            + __import__("hashlib").sha256(sample_plan_path.read_bytes()).hexdigest()
        )
        release_header = {
            "schema": "quwoquan_data.release",
            "releaseId": "release-a",
            "sourceOwner": "qwq_data",
            "releaseKind": "content",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "selectionScope": "target_environment",
            "poolDigest": selection_evidence["poolDigest"],
            "canonicalMerkle": selection_evidence["canonicalMerkle"],
            "sourceIdentities": readiness["sourceIdentities"],
            "sourceIdentitySetDigest": readiness["sourceIdentitySetDigest"],
            "contents": [
                {"contentId": "article-a", "postRef": "article/work-a/1"},
                {"contentId": "image-a", "postRef": "image/work-a/1"},
                {"contentId": "video-a", "postRef": "video/work-a/1"},
            ],
            "samplePlanRef": "uat/sample_plan.json",
            "samplePlanDigest": sample_plan_digest,
        }
        release_header_path = root / "release/payload/release.json"
        release_header_path.write_text(json.dumps(release_header), encoding="utf-8")
        release_header_digest = (
            "sha256:"
            + __import__("hashlib").sha256(release_header_path.read_bytes()).hexdigest()
        )
        carrier_identities = {
            "homepage": "/entity/entity-a",
            "article": "article-a",
            "image": "image-a",
            "video": "video-a",
        }
        plan = {
            "releaseIdentity": {
                "releaseId": "release-a",
                "payloadSha256": MANIFEST_DIGEST,
                "milestone": None,
            },
            "releaseUatSamplePlanRef": "uat/sample_plan.json",
            "releaseUatSamplePlanDigest": sample_plan_digest,
            "orderedSamples": samples,
            "requiredCasePlan": entry_carrier_cells,
            "carrierIdentities": carrier_identities,
            "searchCanaries": [
                {
                    "kind": carrier,
                    "query": object_id,
                    "expectedObjectType": (
                        "entity.homepage" if carrier == "homepage" else "content.post"
                    ),
                    "expectedObjectId": object_id,
                }
                for carrier, object_id in carrier_identities.items()
            ],
            "videoPagination": {
                "pageSize": 20,
                "expectedWorkIds": ["video-a"],
            },
            "mediaChecks": {
                "automatic": True,
                "imageWorkId": "image-a",
                "videoWorkIds": ["video-a"],
            },
        }
        manifest = {
            "environment": "alpha",
            "target": "alpha-local",
            "baselineId": BASELINE,
            "sourceRevision": "a" * 40,
            "packageDigest": PACKAGE_DIGEST,
            "configurationDigest": CONFIGURATION_DIGEST,
            "runtimeConfigDigest": RUNTIME_CONFIG_DIGEST,
            "environmentRuntimeDigest": ENVIRONMENT_RUNTIME_DIGEST,
            "contractGraphDigest": CONTRACT_GRAPH_DIGEST,
            "release": {
                "candidate": {
                    "releaseId": "release-a",
                    "releaseDigest": MANIFEST_DIGEST,
                }
            },
            "environmentArtifact": {
                "environment": "alpha",
                "target": "alpha-local",
                "releaseTrainId": RELEASE_TRAIN,
                "environmentArtifactDigest": ARTIFACT_DIGEST,
                "contractGraphDigest": CONTRACT_GRAPH_DIGEST,
                "sourceCapsule": {
                    "baselineId": BASELINE,
                    "digest": SOURCE_CAPSULE_DIGEST,
                    "sourceRevision": "a" * 40,
                    "workspaceStatusDigest": _digest("f"),
                },
                "packageDigest": PACKAGE_DIGEST,
                "configuration": {
                    "serviceDigest": CONFIGURATION_DIGEST,
                    "appRuntimeDigest": RUNTIME_CONFIG_DIGEST,
                    "environmentRuntimeDigest": ENVIRONMENT_RUNTIME_DIGEST,
                },
                "provider": {"runtimeCompositionDigest": PROVIDER_DIGEST},
            },
        }
        startup = {
            "status": "running",
            "failure": None,
            "env": "alpha",
            "target": "alpha-local",
            "workload": "full",
            "attemptId": "alpha-candidate-attempt",
            "composeProject": "quwoquan_alpha_release_1",
            "runRoot": str(root / "run"),
            "candidateDigest": BASELINE,
            "configurationDigest": CONFIGURATION_DIGEST,
            "providerRuntimeDigest": PROVIDER_DIGEST,
            "observabilityLogSinkDigest": OBSERVABILITY_DIGEST,
            "imageTransportTag": "candidate-alpha",
        }
        preflight = {
            "exitCode": 0,
            "target": "alpha-local",
            "environment": "alpha",
            "purpose": "content_live",
            "launchPolicy": "immutable_candidate",
            "nonPromotable": False,
            "contentBindingState": "bound",
            "contentLive": "passed",
            "status": "passed",
            "packageBaseline": BASELINE,
            "sourceRevision": "a" * 40,
            "configurationDigest": CONFIGURATION_DIGEST,
            "providerRuntimeDigest": PROVIDER_DIGEST,
            "releaseId": "release-a",
            "manifestDigest": MANIFEST_DIGEST,
            "readinessReceiptRef": readiness_path.relative_to(root).as_posix(),
            "readinessReceiptDigest": stackctl._canonical_document_checksum(readiness),
            "lifecycleExitRef": "",
            "releaseHeader": release_header,
            "releaseHeaderRef": str(release_header_path),
            "releaseHeaderDigest": release_header_digest,
            "releaseUatSamplePlan": sample_plan,
            "releaseUatSamplePlanRef": "uat/sample_plan.json",
            "releaseUatSamplePlanDigest": sample_plan_digest,
            "appUatPlan": plan,
            "appUatPlanDigest": stackctl._canonical_document_checksum(plan),
        }
        snapshot = {"manifest": manifest}
        return {
            "readinessPath": readiness_path,
            "readiness": readiness,
            "manifest": manifest,
            "startup": startup,
            "preflight": preflight,
            "snapshot": snapshot,
            "provider": {
                "baselineId": BASELINE,
                "composition": {"runtimeCompositionDigest": PROVIDER_DIGEST},
            },
            "observability": {
                "baselineId": BASELINE,
                "composition": {"composeDigest": OBSERVABILITY_DIGEST},
            },
        }

    def _binding(self, root: Path, fixture: dict[str, object]) -> dict[str, object]:
        with (
            patch.object(stackctl, "output_root", return_value=root),
            patch.object(
                stackctl,
                "active_deployment_candidate_snapshot",
                return_value=fixture["snapshot"],
            ),
            patch.object(
                stackctl,
                "_fixed_candidate_identity",
                return_value=(BASELINE, root / "candidate", fixture["manifest"]),
            ),
            patch.object(
                stackctl,
                "_candidate_bindings_from_snapshot",
                return_value=(fixture["provider"], fixture["observability"]),
            ),
            patch.object(
                stackctl,
                "load_startup_attempt",
                return_value=fixture["startup"],
            ),
            patch.object(
                stackctl,
                "_load_data_release_readiness",
                return_value=(fixture["readiness"], fixture["readinessPath"]),
            ),
            patch.object(
                stackctl,
                "assert_active_deployment_candidate_snapshot",
            ) as assert_snapshot,
            patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                side_effect=AssertionError("mutable startup must not be read"),
            ),
            patch.object(
                stackctl,
                "load_test_live_content_binding",
                side_effect=AssertionError("mutable content must not be read"),
            ),
        ):
            binding = stackctl._app_content_test_live_runtime_binding(
                fixture["preflight"]
            )
        assert_snapshot.assert_called_once()
        return binding

    def test_binding_emits_exact_candidate_startup_and_release_train(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            binding = self._binding(root, fixture)

        self.assertEqual(binding["launchPolicy"], "immutable_candidate")
        self.assertFalse(binding["nonPromotable"])
        self.assertEqual(binding["packageBaseline"], BASELINE)
        self.assertEqual(binding["candidateDigest"], BASELINE)
        self.assertEqual(binding["releaseTrainId"], RELEASE_TRAIN)
        self.assertEqual(binding["environmentArtifactDigest"], ARTIFACT_DIGEST)
        self.assertEqual(binding["contractGraphDigest"], CONTRACT_GRAPH_DIGEST)
        self.assertEqual(binding["startupAttemptId"], "alpha-candidate-attempt")
        self.assertEqual(binding["composeProject"], "quwoquan_alpha_release_1")
        self.assertEqual(
            binding["releaseUatSamplePlan"],
            fixture["preflight"]["releaseUatSamplePlan"],
        )
        self.assertNotIn("appUatEnvelope", binding)
        self.assertEqual(
            binding["startupIdentity"],
            {
                "candidateDigest": BASELINE,
                "configurationDigest": CONFIGURATION_DIGEST,
                "providerRuntimeDigest": PROVIDER_DIGEST,
                "observabilityLogSinkDigest": OBSERVABILITY_DIGEST,
                "imageTransportTag": "candidate-alpha",
            },
        )

    def test_typed_actor_uses_the_real_candidate_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = self._fixture(root)
            binding = self._binding(root, fixture)
            preflight = {
                **fixture["preflight"],
                "provider": {
                    "adapterId": "ext.sms.local_capture",
                    "environment": "alpha",
                    "configurationDigest": CONFIGURATION_DIGEST,
                    "nonPromotable": True,
                    "ready": True,
                },
                "loginJourney": {
                    "status": "passed",
                    "launchPolicy": "immutable_candidate",
                    "baselineId": BASELINE,
                    "sourceRevision": "a" * 40,
                    "runtimeConfigDigest": RUNTIME_CONFIG_DIGEST,
                    "configurationDigest": CONFIGURATION_DIGEST,
                    "providerRuntimeDigest": PROVIDER_DIGEST,
                    "challengePresent": True,
                    "sessionPresent": True,
                    "startupAttemptId": "alpha-candidate-attempt",
                    "nonPromotable": True,
                    "receiptRef": "env/alpha/runs/login/report.json",
                    "receiptDigest": _digest("e"),
                },
            }
            with (
                patch.object(stackctl, "output_root", return_value=root),
                patch.object(
                    stackctl,
                    "_load_data_release_readiness",
                    return_value=(fixture["readiness"], fixture["readinessPath"]),
                ),
                patch.object(
                    stackctl,
                    "active_deployment_candidate_snapshot",
                    return_value=fixture["snapshot"],
                ),
                patch.object(
                    stackctl,
                    "_fixed_candidate_identity",
                    return_value=(BASELINE, root / "candidate", fixture["manifest"]),
                ),
                patch.object(
                    stackctl,
                    "assert_active_deployment_candidate_snapshot",
                ),
                patch.object(
                    stackctl,
                    "build_candidate_binding",
                    wraps=stackctl.build_candidate_binding,
                ) as build_candidate,
            ):
                context = stackctl._app_content_test_live_actor_context(
                    preflight=preflight,
                    runtime_binding=binding,
                    readiness_path=fixture["readinessPath"],
                    report_dir=root / "uat",
                )

        self.assertIs(
            build_candidate.call_args.kwargs["manifest"],
            fixture["manifest"],
        )
        self.assertNotIn(
            "mutableStateDigest",
            build_candidate.call_args.kwargs["manifest"],
        )
        self.assertEqual(context.candidate.baseline_id, BASELINE)
        self.assertEqual(context.candidate.package_digest, PACKAGE_DIGEST)
        self.assertEqual(context.candidate.readiness_phase, "research")
        self.assertEqual(
            tuple(item.object_id for item in context.candidate.release_posts),
            ("article-a", "image-a", "video-a"),
        )
        self.assertEqual(
            context.provider_evidence[
                AUTHENTICATED_ACTORS.required_provider_capabilities[0].value
            ]["candidateBindingDigest"],
            context.candidate.digest,
        )

    def test_baseline_and_startup_drift_block_before_first_patrol(self) -> None:
        for drift in ("baseline", "startup"):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture = self._fixture(root)
                if drift == "baseline":
                    fixture["preflight"] = {
                        **fixture["preflight"],
                        "packageBaseline": _digest("e"),
                    }
                else:
                    fixture["startup"] = {
                        **fixture["startup"],
                        "configurationDigest": _digest("e"),
                    }
                with (
                    patch.object(stackctl, "output_root", return_value=root),
                    patch.object(
                        stackctl,
                        "command_app_debug_preflight",
                        return_value=fixture["preflight"],
                    ),
                    patch.object(
                        stackctl,
                        "active_deployment_candidate_snapshot",
                        return_value=fixture["snapshot"],
                    ),
                    patch.object(
                        stackctl,
                        "_fixed_candidate_identity",
                        return_value=(
                            BASELINE,
                            root / "candidate",
                            fixture["manifest"],
                        ),
                    ),
                    patch.object(
                        stackctl,
                        "_candidate_bindings_from_snapshot",
                        return_value=(
                            fixture["provider"],
                            fixture["observability"],
                        ),
                    ),
                    patch.object(
                        stackctl,
                        "load_startup_attempt",
                        return_value=fixture["startup"],
                    ),
                    patch.object(
                        stackctl,
                        "_load_data_release_readiness",
                        return_value=(
                            fixture["readiness"],
                            fixture["readinessPath"],
                        ),
                    ),
                    patch.object(
                        stackctl,
                        "_environment_page_smoke_profile_command",
                    ) as patrol,
                ):
                    result = stackctl._command_app_content_uat(
                        argparse.Namespace(
                            targets="alpha-local",
                            platform="android",
                            device_id="emulator-5554",
                            dry_run=True,
                            report_dir=str(root / "uat"),
                        )
                    )

                self.assertEqual(result["exitCode"], 2)
                self.assertEqual(result["runs"], [])
                patrol.assert_not_called()
                self.assertIn(
                    "baseline" if drift == "baseline" else "startup identity",
                    result["details"][0],
                )

    def test_release_train_drift_blocks_before_first_patrol(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = {
                "releaseId": "release-a",
                "videoPagination": {"expectedWorkIds": ["video-a"]},
            }

            def preflight(args: object) -> dict[str, object]:
                target = str(vars(args)["target"])
                environment = target.removesuffix("-local")
                return {
                    "exitCode": 0,
                    "target": target,
                    "environment": environment,
                    "releaseId": "release-a",
                    "manifestDigest": MANIFEST_DIGEST,
                    "appUatPlan": plan,
                }

            def binding(item: dict[str, object]) -> dict[str, object]:
                target = str(item["target"])
                marker = {"alpha-local": "1", "beta-local": "2", "gamma-local": "3"}[
                    target
                ]
                return {
                    "target": target,
                    "candidateDigest": _digest(marker),
                    "releaseTrainId": (
                        _digest("f") if target == "gamma-local" else RELEASE_TRAIN
                    ),
                }

            with (
                patch.object(
                    stackctl,
                    "command_app_debug_preflight",
                    side_effect=preflight,
                ),
                patch.object(
                    stackctl,
                    "_app_content_test_live_runtime_binding",
                    side_effect=binding,
                ),
                patch.object(
                    stackctl,
                    "_environment_page_smoke_profile_command",
                ) as patrol,
            ):
                result = stackctl._command_app_content_uat(
                    argparse.Namespace(
                        targets="alpha-local,beta-local,gamma-local",
                        platform="android",
                        device_id="emulator-5554",
                        dry_run=True,
                        report_dir=str(root / "uat"),
                    )
                )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["runs"], [])
        self.assertEqual(result["releaseTrainId"], "")
        self.assertIn("releaseTrainId is not identical", result["details"][0])
        patrol.assert_not_called()


if __name__ == "__main__":
    unittest.main()

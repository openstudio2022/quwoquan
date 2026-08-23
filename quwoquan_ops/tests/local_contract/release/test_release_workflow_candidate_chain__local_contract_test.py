from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.ci.plan_service_release_images import (
    ALL_SERVICES,
    ENVIRONMENTS,
    RUNTIME_IMAGE_OWNERS,
    TRUST_DOMAINS,
    affected_services,
    build_plan,
)
from quwoquan_ops.ci.verify_workflow_release_candidate import validate


DIGEST = "sha256:" + "a" * 64
ARTIFACT_DIGEST = "sha256:" + "d" * 64
SOURCE_SHA = "b" * 40
RUN_ID = "123456"
REPOSITORY = "owner/repo"
RELEASE_REF = "ghcr.io/owner/repo/release-artifact@" + DIGEST


class ServiceReleaseImagePlanTest(unittest.TestCase):
    def test_runtime_owner_set_is_derived_as_six_canonical_images(self) -> None:
        self.assertEqual(
            set(RUNTIME_IMAGE_OWNERS),
            {
                "service-core",
                "recommendation-service",
                "realtime-gateway",
                "rtc-service",
                "product-ops-service",
                "platform-ops-service",
            },
        )

    def _previous_manifest(self, root: Path) -> Path:
        environment_artifacts: dict[str, dict[str, object]] = {}
        for environment in ENVIRONMENTS:
            trust_domain = "prod" if environment == "prod" else "nonprod"
            images = {}
            for owner_index, owner in enumerate(RUNTIME_IMAGE_OWNERS, start=1):
                digest = f"sha256:{(200 if trust_domain == 'prod' else 100) + owner_index:064x}"
                images[owner] = {
                    "digest": digest,
                    "ref": f"ghcr.io/owner/repo/{owner}-{trust_domain}@{digest}",
                }
            environment_artifacts[environment] = {"images": images}
        path = root / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "release-evidence-manifest",
                    "releaseTrainId": DIGEST,
                    "candidateId": DIGEST,
                    "artifactDigest": ARTIFACT_DIGEST,
                    "status": "candidate-ready",
                    "environmentArtifacts": environment_artifacts,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_service_change_rebuilds_owner_and_reuses_verified_digests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plan, _ = build_plan(
                ["quwoquan_service/services/chat-service/internal/chat.go"],
                self._previous_manifest(Path(directory)),
            )
        actions = {
            (item["trust_domain"], item["runtime_image_owner"]): item["action"]
            for item in plan
        }
        self.assertEqual(len(plan), len(TRUST_DOMAINS) * len(RUNTIME_IMAGE_OWNERS))
        for trust_domain in TRUST_DOMAINS:
            self.assertEqual(actions[(trust_domain, "service-core")], "build")
            self.assertEqual(
                actions[(trust_domain, "recommendation-service")], "reuse"
            )
        self.assertTrue(
            all(
                item["image_name"]
                == f"{item['runtime_image_owner']}-{item['trust_domain']}"
                for item in plan
            )
        )

    def test_app_only_change_reuses_every_cloud_image_without_builds(self) -> None:
        # DEC-005/DEC-006：App-only change 复用原 Cloud 摘要，Cloud builder
        # invocation 必须为 0；复用仍逐格绑定上一 immutable candidate 的 exact ref。
        with tempfile.TemporaryDirectory() as directory:
            previous = self._previous_manifest(Path(directory))
            plan, reasons = build_plan(
                [
                    "quwoquan_app/lib/service/content_service/content/post/presentation/home_page.dart",
                    "quwoquan_app/test/local_contract/runtime/bootstrap_recovery__local_contract_test.dart",
                ],
                previous,
            )
            artifacts = json.loads(previous.read_text(encoding="utf-8"))[
                "environmentArtifacts"
            ]
            expected_refs = {
                ("nonprod", owner): descriptor["ref"]
                for owner, descriptor in artifacts["alpha"]["images"].items()
            }
            expected_refs.update(
                {
                    ("prod", owner): descriptor["ref"]
                    for owner, descriptor in artifacts["prod"]["images"].items()
                }
            )
        self.assertEqual(sum(item["action"] == "build" for item in plan), 0)
        self.assertEqual(len(plan), len(TRUST_DOMAINS) * len(RUNTIME_IMAGE_OWNERS))
        for item in plan:
            self.assertEqual(item["action"], "reuse")
            self.assertEqual(
                item["source_ref"],
                expected_refs[(item["trust_domain"], item["runtime_image_owner"])],
            )
        self.assertNotIn("previous-canonical-evidence-unavailable", reasons)

    def test_shared_contract_change_expands_to_every_service(self) -> None:
        affected, reasons = affected_services(
            ["quwoquan_service/contracts/metadata/_shared/errors.yaml"]
        )
        self.assertEqual(affected, ALL_SERVICES)
        self.assertTrue(reasons[0].startswith("shared-change:"))

    def test_retired_travel_service_is_never_an_image_candidate(self) -> None:
        self.assertNotIn("travel-service", ALL_SERVICES)

        affected, _ = affected_services(
            ["specs/feature-tree/travel-journey/spec.md"]
        )

        self.assertEqual(affected, frozenset({"service-core"}))

    def test_service_contract_change_expands_to_every_consumer(self) -> None:
        affected, reasons = affected_services(
            ["quwoquan_service/services/chat-service/contracts/message.yaml"]
        )
        self.assertEqual(affected, ALL_SERVICES)
        self.assertEqual(reasons, ["service-wide-impact:chat-service/contracts"])

    def test_unclassified_service_shared_path_fails_closed_to_all_images(self) -> None:
        affected, reasons = affected_services(
            ["quwoquan_service/runtime/new-shared-package/runtime.go"]
        )
        self.assertEqual(affected, ALL_SERVICES)
        self.assertTrue(reasons[0].startswith("unclassified-service-change:"))

    def test_unclassified_feature_owner_fails_closed_to_all_images(self) -> None:
        affected, reasons = affected_services(
            ["specs/feature-tree/new-domain/new-capability/spec.md"]
        )
        self.assertEqual(affected, ALL_SERVICES)
        self.assertTrue(reasons[0].startswith("unclassified-feature-owner:"))

    def test_feature_tree_owner_expands_cross_domain_services(self) -> None:
        affected, _ = affected_services(
            ["specs/feature-tree/chat-conversation/realtime-call/spec.md"]
        )
        self.assertEqual(
            affected,
            {
                "service-core",
                "realtime-gateway",
                "rtc-service",
            },
        )

    def test_missing_previous_evidence_rebuilds_all(self) -> None:
        plan, reasons = build_plan(
            ["quwoquan_service/services/chat-service/internal/chat.go"], None
        )
        self.assertTrue(all(item["action"] == "build" for item in plan))
        self.assertIn("previous-canonical-evidence-unavailable", reasons)

    def test_previous_flat_images_are_rejected_without_compatibility_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "release-evidence-manifest",
                        "releaseTrainId": DIGEST,
                        "candidateId": DIGEST,
                        "artifactDigest": ARTIFACT_DIGEST,
                        "status": "candidate-ready",
                        "images": {},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "retired flat images"):
                build_plan(
                    ["quwoquan_service/services/chat-service/internal/chat.go"],
                    path,
                )

    def test_previous_nonprod_digest_divergence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._previous_manifest(Path(directory))
            payload = json.loads(path.read_text(encoding="utf-8"))
            owner = RUNTIME_IMAGE_OWNERS[0]
            divergent_digest = "sha256:" + "f" * 64
            payload["environmentArtifacts"]["beta"]["images"][owner] = {
                "digest": divergent_digest,
                "ref": f"ghcr.io/owner/repo/{owner}-nonprod@{divergent_digest}",
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nonprod environments"):
                build_plan(
                    ["quwoquan_service/services/chat-service/internal/chat.go"],
                    path,
                )

    def test_previous_prod_digest_must_fork_from_nonprod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._previous_manifest(Path(directory))
            payload = json.loads(path.read_text(encoding="utf-8"))
            owner = RUNTIME_IMAGE_OWNERS[0]
            payload["environmentArtifacts"]["prod"]["images"][owner] = payload[
                "environmentArtifacts"
            ]["alpha"]["images"][owner]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "prod image reuses the nonprod"):
                build_plan(
                    ["quwoquan_service/services/chat-service/internal/chat.go"],
                    path,
                )


class WorkflowCandidateBindingTest(unittest.TestCase):
    def _validate(self, args: argparse.Namespace) -> None:
        with patch(
            "quwoquan_ops.ci.verify_workflow_release_candidate.validate_manifest"
        ):
            validate(args)

    def _args(self, manifest: Path, **overrides: object) -> argparse.Namespace:
        values: dict[str, object] = {
            "manifest": manifest,
            "expected_candidate": DIGEST,
            "expected_artifact_digest": ARTIFACT_DIGEST,
            "expected_workflow_run_id": RUN_ID,
            "expected_source_sha": SOURCE_SHA,
            "expected_repository": REPOSITORY,
            "expected_release_ref": RELEASE_REF,
            "discovered_release_ref": RELEASE_REF,
            "require_deployable": False,
            "expect_component_ready": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def _manifest(self, root: Path, *, deployable: bool = False) -> Path:
        payload = {
            "schema": "release-evidence-manifest",
            "candidateId": DIGEST,
            "artifactDigest": ARTIFACT_DIGEST,
            "status": "deployable" if deployable else "candidate-ready",
            "source": {
                "gitSha": SOURCE_SHA,
                "treeDigest": "sha256:" + hashlib.sha256(b"tree").hexdigest(),
                "repository": REPOSITORY,
                "workflowRunId": RUN_ID,
                "sourceArchiveDigest": None,
            },
            "environmentReceipts": (
                {"alpha": {}, "beta": {}, "gamma": {}} if deployable else {}
            ),
            "providerEvidence": {"provider": {}} if deployable else {},
        }
        path = root / "manifest.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_exact_candidate_workflow_source_and_ref_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._validate(self._args(self._manifest(Path(directory))))

    def test_source_tag_discovery_cannot_override_exact_oci_ref(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = self._args(
                self._manifest(Path(directory)),
                discovered_release_ref=(
                    "ghcr.io/owner/repo/release-artifact@sha256:" + "c" * 64
                ),
            )
            with self.assertRaisesRegex(ValueError, "did not resolve"):
                self._validate(args)

    def test_real_prod_requires_provider_and_environment_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = self._args(
                self._manifest(Path(directory)), require_deployable=True
            )
            with self.assertRaisesRegex(ValueError, "real Prod apply"):
                self._validate(args)

    def test_component_ready_has_no_candidate_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._manifest(Path(directory))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["candidateId"] = None
            payload["status"] = "component-ready"
            path.write_text(json.dumps(payload), encoding="utf-8")
            args = self._args(
                path,
                expected_candidate="",
                expect_component_ready=True,
            )
            self._validate(args)

    def test_real_prod_invokes_canonical_validator_as_deployable(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "quwoquan_ops.ci.verify_workflow_release_candidate.validate_manifest"
        ) as canonical:
            args = self._args(
                self._manifest(Path(directory), deployable=True),
                require_deployable=True,
            )
            validate(args)
        canonical.assert_called_once()
        self.assertEqual(canonical.call_args.kwargs["allowed_statuses"], {"deployable"})


if __name__ == "__main__":
    unittest.main()

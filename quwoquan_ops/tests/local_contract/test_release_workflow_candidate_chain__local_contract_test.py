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
    def _previous_manifest(self, root: Path) -> Path:
        images = {
            service: {
                "digest": DIGEST,
                "ref": f"ghcr.io/owner/repo/{service}@{DIGEST}",
            }
            for service in ALL_SERVICES
        }
        path = root / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "release-evidence-manifest",
                    "candidateId": DIGEST,
                    "artifactDigest": ARTIFACT_DIGEST,
                    "status": "candidate-ready",
                    "images": images,
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
        actions = {item["service"]: item["action"] for item in plan}
        self.assertEqual(actions["chat-service"], "build")
        self.assertEqual(actions["content-service"], "reuse")

    def test_shared_contract_change_expands_to_every_service(self) -> None:
        affected, reasons = affected_services(
            ["quwoquan_service/contracts/metadata/_shared/errors.yaml"]
        )
        self.assertEqual(affected, ALL_SERVICES)
        self.assertTrue(reasons[0].startswith("shared-change:"))

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
                "chat-service",
                "notification-service",
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

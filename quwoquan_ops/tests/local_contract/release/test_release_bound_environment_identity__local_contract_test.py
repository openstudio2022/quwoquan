# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002.t2
"""release bound environment identity 投影的本地契约。

Python 1000 行硬顶治理：证据常量、digest/checksum helper 与 Fixture 已
逐字下沉到
quwoquan_ops/tests/support/release_bound_environment_identity_test_support.py。
本文件保留全部投影 fail-closed 测试。测试逐字搬移。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.ci import generate_release_bound_environment_identity as renderer
from quwoquan_ops.ci import release_bound_data_evidence as data_validator
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    canonical_candidate_digest,
    canonical_manifest_digest,
)
from quwoquan_ops.tests.support.release_bound_environment_identity_test_support import (
    BASELINE_ID,
    DIGEST_A,
    DIGEST_B,
    ENTITY_CATALOG_DIGEST,
    RELEASE_DIGEST,
    RELEASE_ID,
    SOURCE_DIGEST,
    SOURCE_REVISION,
    SUBJECT_HASH,
    Fixture,
    _checksum,
    _document_digest,
    _write,
)


class ReleaseBoundEnvironmentIdentityContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest_files = mock.patch.object(
            renderer,
            "validate_manifest_files",
        ).start()
        self.data_evidence = mock.patch.object(
            renderer,
            "validate_data_evidence",
            return_value={
                "deliveryMode": "private_signed",
                "releaseId": RELEASE_ID,
                "manifestDigest": RELEASE_DIGEST,
                "subjectHash": SUBJECT_HASH,
                "receiptRef": "env/alpha/runs/data-release/research-isolation.json",
                "receiptDigest": DIGEST_A,
                "anonymousContentStatus": 403,
                "anonymousMediaStatus": 403,
                "signedMediaTtlSeconds": 300,
                "mediaAuditEventId": "audit-media-001",
            },
        ).start()
        self.app_readback_patcher = mock.patch.object(
            renderer,
            "_validate_app_readback_receipts",
        )
        self.app_readback = self.app_readback_patcher.start()
        self.telemetry_backend_patcher = mock.patch.object(
            renderer,
            "_validate_telemetry_backend_receipt",
        )
        self.telemetry_backend = self.telemetry_backend_patcher.start()
        self.addCleanup(mock.patch.stopall)

    def test_projection_writes_identity_when_owner_validators_are_stubbed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            output = Path(directory) / "out/identity.json"
            self.assertEqual(renderer.main(fixture.argv(output)), 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], renderer.SCHEMA)
            self.assertEqual(payload["status"], "passed")
            self.assertEqual(payload["identity"]["baselineId"], BASELINE_ID)
            self.assertEqual(payload["identity"]["releaseId"], RELEASE_ID)
            self.assertEqual(payload["identity"]["releaseClass"], "research")
            self.assertEqual(payload["identity"]["productLifecycleState"], "research")
            self.assertEqual(
                payload["identity"]["dataSourceIdentity"],
                {
                    "sourceRevision": SOURCE_REVISION,
                    "sourceDigest": SOURCE_DIGEST,
                    "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
                },
            )
            self.assertEqual(
                payload["identity"]["activationEnvelopeDigest"],
                _document_digest(payload["identity"]["activationEnvelope"]),
            )
            self.assertEqual(
                set(payload["identity"]["appArtifacts"]),
                {"android-nonprod-apk", "ios-nonprod-app", "web-shared"},
            )
            self.assertEqual(
                payload["identity"]["objectIds"]["entityRefs"],
                ["entity:west-lake"],
            )
            self.assertEqual(
                payload["identity"]["mediaProbe"]["premiumPlayableVideos"], 1
            )
            self.assertEqual(payload["identity"]["mediaProbe"]["avatarAssets"], 4)
            self.assertEqual(payload["identity"]["mediaProbe"]["imageAssets"], 1)
            self.assertEqual(
                payload["identity"]["mediaReadback"]["deliveryMode"],
                "private_signed",
            )
            self.assertNotIn("publicUrl", payload["identity"]["mediaReadback"])
            self.manifest_files.assert_called_once()
            self.data_evidence.assert_called_once()
            self.app_readback.assert_called_once()
            self.assertTrue(
                all(
                    "sha256" in value
                    for key, value in payload["evidence"].items()
                    if key != "appArtifactReceipts"
                )
            )

    def test_research_media_validation_never_enters_public_video_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            readiness_path = _write(root / "release-readiness.json", {"passed": True})
            receipt_ref = "env/alpha/runs/data-release/research/isolation.json"
            receipt_path = _write(root / receipt_ref, {"outcome": "PASS"})
            summary = {
                "releaseId": RELEASE_ID,
                "manifestDigest": RELEASE_DIGEST,
                "subjectHash": SUBJECT_HASH,
                "receiptRef": receipt_ref,
                "receiptDigest": DIGEST_A,
                "anonymousContentStatus": 403,
                "anonymousMediaStatus": 403,
                "signedMediaTtlSeconds": 300,
                "mediaAuditEventId": "audit-media-001",
            }
            with (
                mock.patch.object(data_validator, "output_root", return_value=root),
                mock.patch.object(
                    data_validator,
                    "verify_research_content_isolation",
                    return_value=summary,
                ) as isolation,
                mock.patch.object(
                    data_validator,
                    "load_release_content_identity",
                    side_effect=AssertionError("public video path must not run"),
                ),
            ):
                result = data_validator.validate_data_evidence(
                    data_output_root=root,
                    readiness_path=readiness_path,
                    rollback_path=root / "unused-rollback.json",
                    media_readback_path=receipt_path,
                    environment="alpha",
                    target="alpha-local",
                    expected_release={
                        "releaseId": RELEASE_ID,
                        "releaseDigest": RELEASE_DIGEST,
                        "verifyRunId": "verify-001",
                        "releaseClass": "research",
                    },
                )
            isolation.assert_called_once()
            self.assertEqual(result["deliveryMode"], "private_signed")
            self.assertNotIn("publicUrl", result)

    def test_every_required_input_class_is_fail_closed_and_writes_nothing(self) -> None:
        missing = [
            "manifest",
            "readiness",
            "import",
            "replay",
            "launch",
            "case",
            "telemetry",
            "rollback",
            "media",
            "app",
        ]
        for label in missing:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                fixture = Fixture(Path(directory))
                target = (
                    fixture.app_paths[0] if label == "app" else fixture.paths[label]
                )
                target.unlink()
                output = Path(directory) / "identity.json"
                self.assertEqual(renderer.main(fixture.argv(output)), 2)
                self.assertFalse(output.exists())

    def test_canonical_bundle_and_data_recomputation_are_fail_closed(self) -> None:
        for validator in ("manifest", "data"):
            with (
                self.subTest(validator=validator),
                tempfile.TemporaryDirectory() as directory,
            ):
                fixture = Fixture(Path(directory))
                output = Path(directory) / "identity.json"
                if validator == "manifest":
                    self.manifest_files.side_effect = ValueError("bundle file drift")
                else:
                    self.data_evidence.side_effect = renderer.DataEvidenceError(
                        "canonical Data lifecycle failed"
                    )
                self.assertEqual(renderer.main(fixture.argv(output)), 2)
                self.assertFalse(output.exists())
                self.manifest_files.side_effect = None
                self.data_evidence.side_effect = None

    def test_unverifiable_telemetry_backend_receipt_is_gate_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            output = Path(directory) / "identity.json"
            self.telemetry_backend_patcher.stop()
            self.assertEqual(renderer.main(fixture.argv(output)), 2)
            self.assertFalse(output.exists())

    def test_unverifiable_app_readback_references_are_gate_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            output = Path(directory) / "identity.json"
            self.app_readback_patcher.stop()
            self.assertEqual(renderer.main(fixture.argv(output)), 2)
            self.assertFalse(output.exists())

    def test_input_mutation_during_validation_is_gate_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory))
            output = Path(directory) / "identity.json"
            projected_video = self.data_evidence.return_value

            def mutate_bound_input(**_: object) -> dict[str, object]:
                telemetry = json.loads(fixture.paths["telemetry"].read_text())
                telemetry["backendReceiptRef"] = f"receipt:hosted:changed:{DIGEST_A}"
                _write(fixture.paths["telemetry"], telemetry)
                return projected_video

            self.data_evidence.side_effect = mutate_bound_input
            self.assertEqual(renderer.main(fixture.argv(output)), 2)
            self.assertFalse(output.exists())

    def test_source_identity_and_research_commercial_drift_are_gate_block(self) -> None:
        for mutation in ("source", "lifecycle"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                fixture = Fixture(Path(directory))
                readiness = json.loads(fixture.paths["readiness"].read_text())
                readiness.pop("verificationChecksum")
                if mutation == "source":
                    readiness["activationEnvelope"]["sourceDigest"] = DIGEST_B
                    readiness["activationEnvelopeDigest"] = _document_digest(
                        readiness["activationEnvelope"]
                    )
                else:
                    readiness["productLifecycleState"] = "commercial"
                _write(fixture.paths["readiness"], _checksum(readiness))
                output = Path(directory) / "identity.json"
                self.assertEqual(renderer.main(fixture.argv(output)), 2)
                self.assertFalse(output.exists())

    def test_identity_drift_skipped_unknown_synthetic_and_attempt_reuse_block(
        self,
    ) -> None:
        mutations = ("identity", "skipped", "unknown", "synthetic", "reuse")
        for mutation in mutations:
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                fixture = Fixture(Path(directory))
                if mutation == "identity":
                    payload = json.loads(fixture.paths["telemetry"].read_text())
                    payload["releaseId"] = "different-release"
                    _write(fixture.paths["telemetry"], payload)
                elif mutation == "skipped":
                    payload = json.loads(fixture.paths["case"].read_text())
                    payload["skipped"] = 1
                    _write(fixture.paths["case"], payload)
                elif mutation == "unknown":
                    payload = json.loads(fixture.paths["telemetry"].read_text())
                    payload["deviceIds"][0] = "unknown"
                    _write(fixture.paths["telemetry"], payload)
                elif mutation == "synthetic":
                    payload = json.loads(fixture.paths["telemetry"].read_text())
                    payload["telemetryBackend"] = "mock-local"
                    _write(fixture.paths["telemetry"], payload)
                else:
                    payload = json.loads(fixture.paths["case"].read_text())
                    wrappers = list(payload["runtimeEvidence"].values())
                    wrappers[1]["evidence"]["samples"][0]["attemptId"] = wrappers[0][
                        "evidence"
                    ]["samples"][0]["attemptId"]
                    _write(fixture.paths["case"], payload)
                output = Path(directory) / "identity.json"
                _write(output, {"schema": renderer.SCHEMA, "status": "passed"})
                self.assertEqual(renderer.main(fixture.argv(output)), 2)
                self.assertFalse(output.exists())

    def test_manifest_readiness_and_prod_twenty_run_contract_are_fail_closed(
        self,
    ) -> None:
        for mutation in ("manifest-shape", "object-closure", "prod-run-count"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                fixture = Fixture(
                    Path(directory),
                    environment="prod" if mutation == "prod-run-count" else "alpha",
                )
                if mutation == "manifest-shape":
                    payload = json.loads(fixture.paths["manifest"].read_text())
                    payload["secondTruth"] = True
                    payload["candidateId"] = canonical_candidate_digest(payload)
                    payload["artifactDigest"] = canonical_manifest_digest(payload)
                    _write(fixture.paths["manifest"], payload)
                elif mutation == "object-closure":
                    payload = json.loads(fixture.paths["readiness"].read_text())
                    payload.pop("verificationChecksum")
                    payload["mediaAssetIds"].pop()
                    _write(fixture.paths["readiness"], _checksum(payload))
                else:
                    payload = json.loads(fixture.paths["case"].read_text())
                    runtime = next(iter(payload["runtimeEvidence"].values()))[
                        "evidence"
                    ]
                    runtime["samples"].pop()
                    runtime["runs"] = 19
                    _write(fixture.paths["case"], payload)
                output = Path(directory) / "identity.json"
                self.assertEqual(renderer.main(fixture.argv(output)), 2)
                self.assertFalse(output.exists())

    def test_prod_dry_run_and_incomplete_rollback_are_not_terminal(self) -> None:
        for mutation in ("dry-run", "incomplete-rollback"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                fixture = Fixture(Path(directory), environment="prod")
                if mutation == "dry-run":
                    payload = json.loads(fixture.paths["import"].read_text())
                    payload["status"] = "dry_run"
                    payload.pop("verificationChecksum")
                    _write(fixture.paths["import"], _checksum(payload))
                else:
                    payload = json.loads(fixture.paths["rollback"].read_text())
                    payload.pop("verificationChecksum")
                    payload["replayVerifyResultRef"] = ""
                    _write(fixture.paths["rollback"], _checksum(payload))
                output = Path(directory) / "identity.json"
                self.assertEqual(renderer.main(fixture.argv(output)), 2)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

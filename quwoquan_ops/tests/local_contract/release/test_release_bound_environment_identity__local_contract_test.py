# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002.t2
"""无类别 release identity、不可变 Data 绑定与普通媒体权限的本地契约。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.ci import generate_release_bound_environment_identity as renderer
from quwoquan_ops.ci.release_bound_environment_acceptance import (
    validate_environment_acceptance_authority,
)
from quwoquan_ops.ci import release_bound_data_evidence as data_validator
from quwoquan_ops.ci.release_evidence_reader import (
    canonical_candidate_digest,
    canonical_manifest_digest,
    validate_historical_release_snapshot as validate_release_snapshot,
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
    TEST_SIGNING_ENVIRONMENT,
    ENVIRONMENT_ACCEPTANCE_SCHEMA,
    Fixture,
    verify_environment_acceptance_signature,
    _checksum,
    _document_digest,
    _sha,
    _sign_environment_acceptance,
    _write,
    _write_canonical,
)


class ReleaseBoundEnvironmentIdentityContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest_files = mock.patch.object(
            renderer,
            "validate_historical_release_snapshot",
        ).start()
        self.data_evidence = mock.patch.object(
            renderer,
            "validate_data_evidence",
            return_value={
                "deliveryMode": "public_immutable",
                "assetId": "media-video",
                "postId": "post-video",
                "publicSliceKey": "release/video/media-video/v1/video.mp4",
                "publicUrl": "https://media.example.test/release/video/media-video/v1/video.mp4",
                "contentType": "video/mp4",
                "bytes": 32,
                "sha256": DIGEST_A,
                "durationMs": 1000,
                "firstFrameDecoded": True,
                "rangeStatus": 206,
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
        mock.patch.dict("os.environ", TEST_SIGNING_ENVIRONMENT, clear=False).start()
        self.addCleanup(mock.patch.stopall)

    @staticmethod
    def _validate_fixture_acceptance(
        fixture: Fixture,
        *,
        acceptance_path: Path | None = None,
        evidence_root: Path | None = None,
    ) -> dict[str, object]:
        manifest = json.loads(fixture.paths["manifest"].read_text(encoding="utf-8"))
        return validate_environment_acceptance_authority(
            acceptance_path or fixture.paths["acceptance"],
            evidence_root=evidence_root or fixture.authority_root,
            environment=fixture.environment,
            candidate_id=str(manifest["candidateId"]),
            commit=str(manifest["source"]["gitSha"]),
            tree=str(manifest["source"]["treeDigest"]).removeprefix("sha1:"),
            signature_verifier=verify_environment_acceptance_signature,
        )

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
            for field in ("releaseClass", "productLifecycleState", "readinessPhase"):
                self.assertNotIn(field, payload["identity"])
                self.assertNotIn(field, payload["identity"]["activationEnvelope"])
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
            self.assertNotIn("appUatEnvelope", payload["identity"])
            self.assertNotIn("appUatEnvelopeDigest", payload["identity"])
            self.assertNotIn(
                "appUatEnvelopeDigest", payload["identity"]["activationEnvelope"]
            )
            authority = payload["identity"]["environmentAcceptanceFact"]
            acceptance_payload = json.loads(
                fixture.paths["acceptance"].read_text(encoding="utf-8")
            )
            self.assertEqual(authority["factId"], acceptance_payload["factId"])
            self.assertEqual(
                authority["ref"],
                fixture.paths["acceptance"]
                .relative_to(fixture.authority_root)
                .as_posix(),
            )
            self.assertEqual(authority["digest"], _sha(fixture.paths["acceptance"]))
            self.assertEqual(
                authority["caseResultRefs"], acceptance_payload["caseResultRefs"]
            )
            self.assertEqual(
                set(authority["namedEvidenceRefs"]),
                {
                    "runtimeIdentity",
                    "dataLifecycle",
                    "providerReadiness",
                    "observabilityReadiness",
                    "inspectEvidence",
                    "doctorEvidence",
                    "cleanupEvidence",
                    "leaseClosureEvidence",
                },
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
                "public_immutable",
            )
            self.assertEqual(
                payload["identity"]["mediaReadback"]["publicUrl"],
                self.data_evidence.return_value["publicUrl"],
            )
            self.assertEqual(self.manifest_files.call_count, 2)
            self.assertNotIn(
                "artifact_dir", self.manifest_files.call_args_list[0].kwargs
            )
            self.assertEqual(
                self.manifest_files.call_args_list[1].kwargs["artifact_dir"],
                fixture.paths["manifest"].resolve().parent,
            )
            self.data_evidence.assert_called_once()
            self.app_readback.assert_called_once()
            self.assertTrue(
                all(
                    "sha256" in value
                    for key, value in payload["evidence"].items()
                    if key != "appArtifactReceipts"
                )
            )

    def test_canonical_acceptance_rejects_v1_candidate_drift_and_source_drift(self) -> None:
        for mutation in ("v1", "candidate", "source"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                fixture = Fixture(Path(directory))
                acceptance = json.loads(
                    fixture.paths["acceptance"].read_text(encoding="utf-8")
                )
                manifest = json.loads(
                    fixture.paths["manifest"].read_text(encoding="utf-8")
                )
                expected_candidate_id = str(manifest["candidateId"])
                expected_commit = str(manifest["source"]["gitSha"])
                expected_tree = str(manifest["source"]["treeDigest"]).removeprefix(
                    "sha1:"
                )
                if mutation == "v1":
                    acceptance = {
                        "schema": ENVIRONMENT_ACCEPTANCE_SCHEMA.removesuffix("2") + "1",
                        "environment": "alpha",
                        "factId": DIGEST_A,
                    }
                    _write_canonical(fixture.paths["acceptance"], acceptance)
                elif mutation == "candidate":
                    expected_candidate_id = DIGEST_B
                else:
                    expected_commit = "f" * 40
                with self.assertRaisesRegex(ValueError, "EnvironmentAcceptanceFact"):
                    validate_environment_acceptance_authority(
                        fixture.paths["acceptance"],
                        evidence_root=fixture.authority_root,
                        environment="alpha",
                        candidate_id=expected_candidate_id,
                        commit=expected_commit,
                        tree=expected_tree,
                        signature_verifier=verify_environment_acceptance_signature,
                    )

    def test_acceptance_rejects_tamper_path_escape_and_symlink_refs(self) -> None:
        for mutation in ("tamper", "path-escape", "symlink"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                fixture = Fixture(Path(directory))
                acceptance = json.loads(
                    fixture.paths["acceptance"].read_text(encoding="utf-8")
                )
                runtime_ref = str(acceptance["runtimeIdentity"]["ref"])
                runtime_path = fixture.authority_root / runtime_ref
                if mutation == "tamper":
                    runtime_path.write_bytes(runtime_path.read_bytes() + b" ")
                elif mutation == "path-escape":
                    outside = fixture.root / "outside-runtime-identity.json"
                    outside.write_bytes(runtime_path.read_bytes())
                    acceptance["runtimeIdentity"] = {
                        "ref": "../outside-runtime-identity.json",
                        "digest": _sha(outside),
                    }
                    _write_canonical(
                        fixture.paths["acceptance"],
                        _sign_environment_acceptance(acceptance),
                    )
                else:
                    outside = fixture.root / "outside-runtime-identity.json"
                    outside.write_bytes(runtime_path.read_bytes())
                    runtime_path.unlink()
                    runtime_path.symlink_to(outside)
                with self.assertRaisesRegex(
                    ValueError, "EnvironmentAcceptanceFact authority is invalid"
                ):
                    self._validate_fixture_acceptance(fixture)

    def test_acceptance_rejects_missing_symlink_or_external_authority_root(
        self,
    ) -> None:
        for mutation in ("missing-root", "symlink-root", "external-fact"):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as directory,
            ):
                fixture = Fixture(Path(directory))
                acceptance_path = fixture.paths["acceptance"]
                evidence_root = fixture.authority_root
                if mutation == "missing-root":
                    evidence_root = fixture.root / "missing-authority"
                    acceptance_path = evidence_root / "environment-acceptance.json"
                elif mutation == "symlink-root":
                    evidence_root = fixture.root / "linked-authority"
                    evidence_root.symlink_to(
                        fixture.authority_root, target_is_directory=True
                    )
                    acceptance_path = evidence_root / acceptance_path.name
                else:
                    acceptance_path = fixture.root / "external-acceptance.json"
                    acceptance_path.write_bytes(
                        fixture.paths["acceptance"].read_bytes()
                    )
                with self.assertRaises(ValueError):
                    self._validate_fixture_acceptance(
                        fixture,
                        acceptance_path=acceptance_path,
                        evidence_root=evidence_root,
                    )

    def test_prod_rejects_environment_acceptance_before_other_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Fixture(Path(directory), environment="prod")
            output = Path(directory) / "identity.json"
            self.assertEqual(renderer.main(fixture.argv(output)), 2)
            self.assertFalse(output.exists())
            self.manifest_files.assert_not_called()
            self.data_evidence.assert_not_called()

    def test_unclassified_media_keeps_immutable_delivery_security_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            readiness_path = _write(root / "release-readiness.json", {"passed": True})
            content = {
                "releaseId": RELEASE_ID, "sourceOwner": "qwq_data",
                "manifestDigest": RELEASE_DIGEST, "mediaManifestDigest": DIGEST_A,
                "importRunId": "import-001", "verifyRunId": "verify-001",
                "readinessReceiptRef": "env/alpha/runs/data-release/readiness.json",
            }
            binding = {
                "workId": "work-video", "postId": "post-video", "postRef": "post:video",
                "assetId": "media-video", "assetVersion": 1,
                "publicSliceKey": "release/video/media-video/v1/video.mp4",
                "expectedMimeType": "video/mp4", "expectedBytes": 32,
                "expectedHash": DIGEST_A,
            }
            authority = "https://media.example.test"
            public_url = data_validator.build_release_video_url({"mediaVideo": authority}, binding)
            delivery = {
                "tlsSystemTrust": True, "fullStatus": 200, "rangeStatus": 206,
                "mimeType": "video/mp4", "rangeMimeType": "video/mp4",
                "contentLength": 32, "observedBytes": 32, "observedHash": DIGEST_A,
                "etag": "video-v1", "rangeEtag": "video-v1",
                "contentRange": "bytes 0-31/32", "rangeBytes": 32, "rangeSha256": DIGEST_A,
                "requestPath": "/" + binding["publicSliceKey"], "requestQuery": "",
                "cacheControl": "public, max-age=31536000, immutable",
                "rangeCacheControl": "public, max-age=31536000, immutable",
                "corsAllowOrigin": "*", "rangeCorsAllowOrigin": "*",
                "cacheKey": "/" + binding["publicSliceKey"],
                "rangeCacheKey": "/" + binding["publicSliceKey"],
                "signedQueryStatus": 403, "signedQueryCacheControl": "no-store",
                "signedQueryCacheKey": "",
            }
            evidence = {
                "schema": data_validator.DELIVERY_EVIDENCE_SCHEMA, "status": "passed",
                "environment": "alpha", "target": "alpha-local", "rolloutStage": "local",
                "release": content, "videoAuthority": authority,
                "video": {**binding, "publicUrl": public_url}, "delivery": delivery,
                "playback": {"durationMs": 1000, "firstFrameDecoded": True},
                "publicSliceKey": binding["publicSliceKey"],
                "rangeStatus": 206, "contentType": "video/mp4",
            }
            receipt_path = root / "media-readback.json"
            with (
                mock.patch.object(data_validator, "output_root", return_value=root),
                mock.patch.object(data_validator, "load_release_content_identity", return_value=content),
                mock.patch.object(data_validator, "load_release_video_binding", return_value=binding),
            ):
                def validate() -> dict[str, object]:
                    return data_validator.validate_data_evidence(
                        data_output_root=root, readiness_path=readiness_path,
                        rollback_path=root / "unused-rollback.json", media_readback_path=receipt_path,
                        environment="alpha", target="alpha-local",
                        expected_release={
                            "releaseId": RELEASE_ID, "releaseDigest": RELEASE_DIGEST,
                            "importRunId": "import-001", "verifyRunId": "verify-001",
                            "mediaProbe": {"mediaManifestDigest": DIGEST_A},
                        },
                    )

                _write(receipt_path, evidence)
                self.assertEqual(validate()["deliveryMode"], "public_immutable")
                mutations = (
                    ("delivery", "tlsSystemTrust", False),
                    ("delivery", "observedHash", DIGEST_B),
                    ("delivery", "rangeStatus", 200),
                    ("delivery", "signedQueryCacheControl", "public"),
                    ("delivery", "signedQueryCacheKey", "/public/cache"),
                    ("release", "manifestDigest", DIGEST_B),
                    ("video", "assetVersion", "v2"),
                    ("playback", "firstFrameDecoded", False),
                )
                for section, field, replacement in mutations:
                    with self.subTest(section=section, field=field):
                        changed = json.loads(json.dumps(evidence))
                        changed[section][field] = replacement
                        _write(receipt_path, changed)
                        with self.assertRaises(data_validator.DataEvidenceError):
                            validate()

    def test_current_data_schema_preserves_immutable_source_and_run_binding(self) -> None:
        source = {
            "sourceRevision": SOURCE_REVISION, "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
        }
        run_ref = f"env/alpha/runs/data-release/{RELEASE_ID}/import-001/import.json"
        activation = {
            "schema": "quwoquan_data.environment_activation_envelope",
            "environment": "alpha", "releaseId": RELEASE_ID, "manifestDigest": RELEASE_DIGEST,
            **source, "importRunId": "import-001", "verifyRunId": "verify-001",
            "importReportRef": run_ref, "importReportDigest": DIGEST_B,
        }
        operation = {
            "path": "/content/feed", "pageId": "content.feed.list", "status": 200,
            "requestId": "request-001", "traceId": "trace-001",
            "startedAt": "2026-09-09T08:00:00Z", "endedAt": "2026-09-09T08:00:01Z",
            "durationMs": 1000,
        }
        readiness = {
            "schema": "quwoquan_data.environment_release_readiness", "environment": "alpha",
            "releaseId": RELEASE_ID, "releaseKind": "content", "sourceOwner": "qwq_data",
            "containsUnverifiedAssets": False,
            "rightsStatusCounts": {"verified": 3, "unverified": 0, "restricted": 0, "unknown": 0},
            "authorizationRequiredAssetIds": [], "acceptedCount": 3,
            "guestActorHash": DIGEST_A,
            "guestLogin": {**operation, "path": "/auth/login/anonymous", "pageId": "user.login.anonymous"},
            **source, "manifestDigest": RELEASE_DIGEST, "mediaManifestDigest": DIGEST_A,
            "importRunId": "import-001", "verifyRunId": "verify-001",
            "counts": {field: 1 for field in renderer._READINESS_COUNTS},
            "entityRefs": ["entity:lake"], "postIds": ["post-video"], "creatorIds": ["creator-001"],
            "tagRefs": ["Topic/travel"], "mediaAssetIds": ["media-video"],
            "feedQueries": [
                {"name": name, "path": "/content/feed", "query": query, "status": 200,
                 "releaseBound": True, "matchedPostIds": ["post-video"], "requests": [operation]}
                for name, query in (
                    ("discovery_work", "identity=work&limit=1"),
                    ("typed_article", "identity=work&type=article&limit=1"),
                    ("typed_image", "identity=work&type=image&limit=1"),
                    ("typed_video", "identity=work&type=video&limit=1"),
                    ("homepage_recommend", "sort=recommend&channelId=recommend&limit=1"),
                    ("premium_stream", "sort=recommend&channelId=premium_stream&limit=1"),
                )
            ],
            "contentImportReportRef": run_ref, "creatorAttributionRef": run_ref,
            "tagAttributionRef": run_ref, "homepageApiVerificationRef": run_ref,
            "postApiVerificationRef": run_ref,
            "mediaManifestRef": f"data/releases/{RELEASE_ID}/payload/media_manifest.json",
            "activationEnvelope": activation, "activationEnvelopeDigest": _document_digest(activation),
            "verifiedAt": "2026-09-09T08:00:01Z", "passed": True,
        }
        self.assertEqual(renderer._validate_readiness(_checksum(readiness), environment="alpha")["sourceIdentity"], source)
        for field in ("releaseClass", "productLifecycleState", "readinessPhase", "researchIsolationPolicy"):
            for document in ("readiness", "activation"):
                with self.subTest(field=field, document=document):
                    changed = json.loads(json.dumps(readiness))
                    (changed if document == "readiness" else changed["activationEnvelope"])[field] = "retired"
                    changed["activationEnvelopeDigest"] = _document_digest(changed["activationEnvelope"])
                    with self.assertRaisesRegex(renderer.IdentityEvidenceError, "schema mismatch"):
                        renderer._validate_readiness(_checksum(changed), environment="alpha")
        rows = [{**source, "executionIds": ["execution-001"]}]
        source_set = {"sourceIdentities": rows, "sourceIdentitySetDigest": _document_digest(
            {"schema": "quwoquan_data.source_identity_set", "sourceIdentities": rows}
        )}
        for document in (readiness, activation):
            for field in source:
                document.pop(field)
            document.update(source_set)
        readiness["activationEnvelopeDigest"] = _document_digest(activation)
        self.assertEqual(renderer._validate_readiness(_checksum(readiness), environment="alpha")["sourceIdentity"], source_set)
        activation["sourceIdentitySetDigest"] = DIGEST_B
        readiness["activationEnvelopeDigest"] = _document_digest(activation)
        with self.assertRaisesRegex(renderer.IdentityEvidenceError, "activationEnvelope.sourceIdentitySetDigest drift"):
            renderer._validate_readiness(_checksum(readiness), environment="alpha")
        run = {
            "schema": "quwoquan_data.environment_release_result", "environment": "alpha",
            "releaseId": RELEASE_ID, "containsUnverifiedAssets": False, "manifestDigest": RELEASE_DIGEST,
            "admissionKind": "producer_handoff", "handoffRef": f"handoff-ref-v1:{DIGEST_A}:{DIGEST_B}",
            "handoffArtifactRef": f"data/releases/{RELEASE_ID}/producer_release_handoff.json",
            "handoffArtifactDigest": DIGEST_A, "runId": "import-001", "status": "completed",
            "startedAt": "2026-09-09T08:00:00Z", "endedAt": "2026-09-09T08:00:01Z", "durationMs": 1000,
        }
        for mutation in (None, "manifestDigest", "handoffArtifactDigest", "verificationChecksum"):
            with self.subTest(run_mutation=mutation):
                changed = _checksum(run)
                if mutation == "manifestDigest":
                    changed = _checksum({**run, "manifestDigest": DIGEST_B})
                elif mutation == "handoffArtifactDigest":
                    changed.pop(mutation)
                elif mutation == "verificationChecksum":
                    changed[mutation] = DIGEST_B
                kwargs = {"label": "import-receipt", "environment": "alpha", "release_id": RELEASE_ID,
                          "release_digest": RELEASE_DIGEST}
                if mutation is None:
                    self.assertEqual(renderer._validate_run(changed, **kwargs), "import-001")
                else:
                    with self.assertRaises(renderer.IdentityEvidenceError):
                        renderer._validate_run(changed, **kwargs)

    def test_every_required_input_class_is_fail_closed_and_writes_nothing(self) -> None:
        missing = [
            "manifest",
            "readiness",
            "import",
            "replay",
            "launch",
            "acceptance",
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

    def test_source_identity_and_immutable_release_drift_are_gate_block(self) -> None:
        for mutation in ("source", "release"):
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
                    readiness["activationEnvelope"]["manifestDigest"] = DIGEST_B
                    readiness["activationEnvelopeDigest"] = _document_digest(
                        readiness["activationEnvelope"]
                    )
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
                self.manifest_files.side_effect = None
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
                    self.manifest_files.side_effect = validate_release_snapshot
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

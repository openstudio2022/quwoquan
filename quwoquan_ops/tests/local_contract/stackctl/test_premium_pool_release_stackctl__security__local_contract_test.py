# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-004

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import (
    local_environment_auth,
    premium_pool_release,
    public_domain_tls,
)
from quwoquan_ops.tests.support.derivable_release_payload_test_support import (
    write_derivable_release_payload,
)
from quwoquan_ops.tests.support.test_data_verification_test_support import _readiness, _with_checksum


def _jwt(claims: dict[str, object], *, alg: str = "HS256") -> str:
    def encode(value: dict[str, object]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return encode({"alg": alg, "typ": "JWT"}) + "." + encode(claims) + ".signature"


def _test_live_readiness_fixture(
    root: Path,
    *,
    video_work_id: str = "video-1",
) -> tuple[Path, dict[str, object]]:
    receipt_ref = (
        "env/alpha/runs/data-release/release-1/verify-1/release-readiness.json"
    )
    receipt = root / receipt_ref
    receipt.parent.mkdir(parents=True)
    # readiness keeps environment verification only; release samples are carried
    # by the exact header-bound ReleaseUatSamplePlan projected into appUatPlan.
    readiness = _readiness(
        environment="alpha", manifest_digest="sha256:" + "a" * 64,
        post_ids=("article-1", "image-1", video_work_id), entity_ref="homepage-1",
    )
    encoded = json.dumps(readiness, sort_keys=True).encode("utf-8")
    receipt.write_bytes(encoded)
    runtime_identity = {
        "sourceRevision": "revision-1",
        "workspaceStatusDigest": "sha256:" + "b" * 64,
        "mutableStateDigest": "sha256:" + "c" * 64,
        "composeDigest": "sha256:" + "d" * 64,
        "configurationDigest": "sha256:" + "e" * 64,
        "providerRuntimeDigest": "sha256:" + "f" * 64,
        "resolverHandoffDigest": "sha256:" + "1" * 64,
    }
    content_binding: dict[str, object] = {
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "bound",
        "retentionClass": "run_bound",
        "environment": "alpha",
        "target": "alpha-local",
        "startupAttemptId": "attempt-alpha-1",
        "startupIdentity": runtime_identity,
        "releaseId": "release-1",
        "verifyRunId": "verify-1",
        "manifestDigest": "sha256:" + "a" * 64,
        "readinessReceiptRef": receipt_ref,
        "readinessReceiptDigest": ("sha256:" + hashlib.sha256(encoded).hexdigest()),
        "releaseUatSamplePlanRef": "uat/sample_plan.json",
        "releaseUatSamplePlanDigest": "sha256:" + "2" * 64,
        "appUatPlan": {
            "orderedSamples": [
                {
                    "sampleId": "canary-video-001",
                    "carrier": "video",
                    "objectId": video_work_id,
                    "objectRef": f"objects/posts/video/{video_work_id}/1",
                    "objectDigest": "sha256:" + "7" * 64,
                }
            ],
            "carrierIdentities": {
                "homepage": "homepage-1",
                "article": "article-1",
                "image": "image-1",
                "video": video_work_id,
            },
        },
    }
    return receipt, content_binding


def _checksum(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _write_candidate_release_fixture(
    root: Path,
    *,
    release_id: str,
    manifest_digest: str,
) -> tuple[Path, str]:
    scalar_identity = {
        "sourceRevision": "sha256:" + "2" * 64,
        "sourceDigest": "sha256:" + "3" * 64,
        "entityCatalogDigest": "sha256:" + "4" * 64,
    }
    source_identities = [{**scalar_identity, "executionIds": ["execution-1"]}]
    source_identity_set_digest = _checksum(
        {
            "schema": "quwoquan_data.source_identity_set",
            "sourceIdentities": source_identities,
        }
    )
    pool_digest = "sha256:" + "5" * 64
    canonical_merkle = "sha256:" + "6" * 64
    content_source_identity_digest = _checksum(
        {"schema": "quwoquan_data.object_source_identity", **scalar_identity}
    )
    contents = [
        {
            "contentId": f"{carrier}-1",
            "version": 1,
            "postRef": f"{carrier}/{carrier}-1/1",
            "selectionIdentityDigest": content_source_identity_digest,
            "canonicalObjectDigest": "sha256:" + "7" * 64,
            "contentLibraryBindingDigest": "sha256:" + "8" * 64,
        }
        for carrier in ("article", "image", "video")
    ]
    release_root = root / "data/releases" / release_id
    header = {
        "schema": "quwoquan_data.release",
        "releaseId": release_id,
        "sourceOwner": "qwq_data",
        "releaseKind": "content",
        "sourceIdentities": source_identities,
        "sourceIdentitySetDigest": source_identity_set_digest,
        "poolDigest": pool_digest,
        "canonicalMerkle": canonical_merkle,
        "containsUnverifiedAssets": True,
        "rightsStatusCounts": {"verified": 0, "unverified": 1, "restricted": 0, "unknown": 0},
        "authorizationRequiredAssetIds": ["media-1"],
        "researchAcceptedCount": 1,
        "commercialAcceptedCount": 0,
        "executionIds": ["execution-1"],
        "sourceDigests": [{"algorithm": "sha256", "digest": "sha256:" + "9" * 64, "inputs": ["quwoquan_data"]}],
        "counts": {"homepage": 1, "article": 1, "image": 1, "video": 1, "total": 4},
        "contents": contents,
        "authors": [],
        "buildResult": "completed",
    }
    # sample plan 由下游从 payload 派生；fixture 写最小可派生 payload。
    write_derivable_release_payload(
        release_root / "payload",
        release_header=header,
        entity_refs=["homepage-1"],
    )
    attestation = {
        "schema": "quwoquan_data.release_attestation",
        "releaseId": release_id,
        "sourceOwner": "qwq_data",
        "releaseKind": "content",
        "payloadSha256": manifest_digest,
        **{key: header[key] for key in (
            "containsUnverifiedAssets", "rightsStatusCounts", "authorizationRequiredAssetIds",
            "researchAcceptedCount", "commercialAcceptedCount", "executionIds", "sourceDigests",
            "sourceIdentities", "sourceIdentitySetDigest", "canonicalMerkle",
        )},
        "carrierCounts": {"homepage": 1, "article": 1, "image": 1, "video": 1, "total": 4},
        "entityCount": 1, "postCount": 3, "creatorCount": 0, "tagCount": 0,
        "recordedAt": "2026-09-09T00:00:00Z",
    }
    premium_pool_release._validate_release_document(header, "release_header")
    premium_pool_release._validate_release_document(attestation, "release_attestation")
    attestation_path = release_root / "attestations/release.json"
    attestation_path.parent.mkdir(parents=True, exist_ok=True)
    attestation_path.write_text(
        json.dumps(attestation, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return (
        attestation_path,
        "sha256:" + hashlib.sha256(attestation_path.read_bytes()).hexdigest(),
    )


class PremiumPoolReleaseStackctlSecurityLocalContractTest(unittest.TestCase):
    def test_alpha_operator_is_short_lived_typed_and_never_returned_in_receipt(
        self,
    ) -> None:
        token = _jwt(
            {
                "sub": "operator:content-commercial:alpha",
                "roles": ["operator"],
                "scope": (
                    "ops.experiment.read ops.experiment.write "
                    "ops.product.dashboard.read "
                    "ops.reco.read ops.reco.write ops.telemetry.read"
                ),
                "iss": "quwoquan.alpha.local",
                "aud": "quwoquan-app",
                "iat": 100,
                "exp": 1000,
            }
        )
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=token + "\n", stderr=""
        )
        with (
            mock.patch.object(
                local_environment_auth,
                "prepare_local_environment_auth",
                return_value=local_environment_auth.LocalEnvironmentAuth(
                    environment={
                        "AUTH_JWT_SECRET": "s" * 48,
                        "AUTH_JWT_ISSUER": "quwoquan.alpha.local",
                        "AUTH_JWT_AUDIENCE": "quwoquan-app",
                        "AUTH_JWT_TOKEN_VERSION": "1",
                    },
                    secret_path=Path("/tmp/auth.env"),
                ),
            ),
            mock.patch.object(
                local_environment_auth.subprocess,
                "run",
                return_value=completed,
            ) as run,
        ):
            actual = local_environment_auth.mint_local_product_ops_operator_token(
                "alpha", "alpha-local"
            )

        self.assertEqual(actual, token)
        self.assertEqual(
            run.call_args.args[0],
            ["go", "run", "./cmd/local-product-ops-operator-credential"],
        )
        self.assertEqual(run.call_args.kwargs["env"]["APP_ENV"], "alpha")

    def test_prod_cannot_use_nonprod_operator_port(self) -> None:
        with (
            mock.patch.object(local_environment_auth.subprocess, "run") as run,
            self.assertRaisesRegex(ValueError, "Alpha/Beta/Gamma"),
        ):
            local_environment_auth.mint_local_product_ops_operator_token(
                "prod", "prod-sim"
            )
        run.assert_not_called()

    def test_gamma_uses_same_target_scoped_nonprod_operator_port(self) -> None:
        expected = local_environment_auth.LocalAcceptanceSession(
            owner_id="operator:content-commercial:gamma",
            persona_id="",
            access_token="gamma-token",
        )
        with mock.patch.object(
            premium_pool_release,
            "mint_local_product_ops_operator_token",
            return_value=expected.access_token,
        ) as mint:
            session, kind = premium_pool_release.open_premium_pool_operator_session(
                environment="gamma", target="gamma-local"
            )
        self.assertEqual(session, expected)
        self.assertEqual(kind, "managed_local_hs256_operator")
        mint.assert_called_once_with("gamma", "gamma-local")

    def test_attestation_rejects_old_tracks_before_sample_projection(self) -> None:
        # spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path, _ = _write_candidate_release_fixture(
                root, release_id="release-1", manifest_digest="sha256:" + "a" * 64
            )
            original = json.loads(path.read_bytes())
            for field in ("releaseClass", "productLifecycleState", "readinessPhase"):
                for phase in ("production", "default", "research", "commercial", "consumer", "import", "", None):
                    with self.subTest(field=field, phase=phase):
                        raw = json.dumps({**original, field: phase}).encode("utf-8")
                        path.write_bytes(raw)
                        with self.assertRaisesRegex(
                            premium_pool_release.PremiumPoolReleaseError,
                            "release_attestation schema",
                        ):
                            premium_pool_release._load_release_sample_plan_documents_from_attestation(
                                release_id="release-1",
                                manifest_digest="sha256:" + "a" * 64,
                                attestation_ref=str(path),
                                attestation_digest="sha256:" + hashlib.sha256(raw).hexdigest(),
                            )

    def test_release_header_rejects_category_fields_with_current_attestation(self) -> None:
        # spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path, digest = _write_candidate_release_fixture(
                root, release_id="release-1", manifest_digest="sha256:" + "a" * 64
            )
            header_path = path.parents[1] / "payload/release.json"
            original = json.loads(header_path.read_bytes())
            for field in ("releaseClass", "productLifecycleState", "readinessPhase"):
                for phase in ("production", "default", "research", "commercial", "consumer", "import", "", None):
                    with self.subTest(field=field, phase=phase):
                        header_path.write_text(
                            json.dumps({**original, field: phase}), encoding="utf-8"
                        )
                        with self.assertRaisesRegex(
                            premium_pool_release.PremiumPoolReleaseError,
                            "release_header schema",
                        ):
                            premium_pool_release._load_release_sample_plan_documents_from_attestation(
                                release_id="release-1",
                                manifest_digest="sha256:" + "a" * 64,
                                attestation_ref=str(path),
                                attestation_digest=digest,
                            )

    def test_candidate_binding_rejects_video_outside_active_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            release_id = "release-1"
            manifest_digest = "sha256:" + "a" * 64
            attestation_path, attestation_digest = _write_candidate_release_fixture(
                root,
                release_id=release_id,
                manifest_digest=manifest_digest,
            )
            receipt = root / "data-release/release-1/verify-1/release-readiness.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps(_readiness(
                environment="alpha", release_id=release_id, manifest_digest=manifest_digest,
                post_ids=("article-1", "image-1", "video-1"), entity_ref="homepage-1",
                source_identities=json.loads(attestation_path.read_bytes())["sourceIdentities"],
            )), encoding="utf-8")
            with (
                mock.patch.object(
                    premium_pool_release,
                    "active_deployment_candidate",
                    return_value={"baselineId": "sha256:" + "b" * 64},
                ),
                mock.patch.object(
                    premium_pool_release,
                    "load_candidate_manifest",
                    return_value={
                        "baselineId": "sha256:" + "b" * 64,
                        "packageDigest": "sha256:" + "c" * 64,
                        "sourceRevision": "revision-1",
                        "release": {
                            "candidate": {
                                "releaseId": release_id,
                                "releaseDigest": manifest_digest,
                                "attestationRef": str(attestation_path),
                                "attestationDigest": attestation_digest,
                            }
                        },
                    },
                ),
                mock.patch.object(
                    premium_pool_release,
                    "env_runs_root",
                    return_value=root,
                ),
            ):
                readiness = json.loads(receipt.read_text(encoding="utf-8"))
                for field in ("readinessPhase", "releaseClass", "productLifecycleState"):
                    for phase in ("production", "default", "research", "commercial", "consumer", "import", "", None):
                        with self.subTest(field=field, phase=phase):
                            receipt.write_text(
                                json.dumps({**readiness, field: phase}), encoding="utf-8"
                            )
                            with self.assertRaisesRegex(
                                premium_pool_release.PremiumPoolReleaseError,
                                "environment_release_readiness schema",
                            ):
                                premium_pool_release.load_premium_pool_candidate_binding(
                                    environment="alpha",
                                    target="alpha-local",
                                    readiness_receipt=receipt,
                                    content_id="video-1",
                                )
                receipt.write_text(json.dumps(readiness), encoding="utf-8")
                binding = premium_pool_release.load_premium_pool_candidate_binding(
                    environment="alpha", target="alpha-local",
                    readiness_receipt=receipt, content_id="video-1",
                )
                self.assertEqual(binding.import_run_id, readiness["importRunId"])
                plan = premium_pool_release._load_release_sample_plan_from_attestation(
                    release_id=release_id, manifest_digest=manifest_digest, readiness=readiness,
                    attestation_ref=attestation_path, attestation_digest=attestation_digest,
                )
                self.assertEqual(len(plan["requiredCasePlan"]), 16)
                self.assertEqual(len(plan["orderedSamples"]), 4)
                for field in ("readinessPhase", "releaseClass", "productLifecycleState"):
                    self.assertNotIn(field, plan["releaseIdentity"])
                self.assertTrue(readiness["containsUnverifiedAssets"])
                with self.assertRaisesRegex(
                    premium_pool_release.PremiumPoolReleaseError,
                    "ReleaseUatSamplePlan video sample",
                ):
                    premium_pool_release.load_premium_pool_candidate_binding(
                        environment="alpha",
                        target="alpha-local",
                        readiness_receipt=receipt,
                        content_id="video-other",
                    )

    def test_bootstrap_preserves_prepared_import_and_object_rights_without_category(self) -> None:
        # spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            digest = "sha256:" + "a" * 64
            attestation, attestation_digest = _write_candidate_release_fixture(
                root, release_id="release-1", manifest_digest=digest,
            )
            report = {
                "schema": "quwoquan.content_import_report", "environment": "alpha",
                "releaseId": "release-1", "manifestDigest": digest, "sourceOwner": "qwq_data",
                "status": "staged", "activationMode": "stage-only", "mode": "upsert", "deletePolicy": "none",
                "counts": {"postsLoaded": 1, "entitiesLoaded": 1}, "auditEvents": [],
                "postBindings": [{"postRef": "video/video-1/1", "postId": "post-video-1",
                                  "contentId": "video-1", "contentVersion": 1, "contentType": "video",
                                  "usageScope": "research", "authorId": "author-1"}],
                "stageResult": {"postsExpected": 1, "postsProjected": 1, "mediaExpected": 1,
                                "mediaProjected": 1, "outboxExpected": 1, "outboxProjected": 1,
                                "projectionVersion": 1, "replayed": False},
            }
            premium_pool_release._validate_release_document(report, "import_report")
            path = root / "data-release/release-1/apply-1/import.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(report), encoding="utf-8")
            with (
                mock.patch.object(premium_pool_release, "env_runs_root", return_value=root),
                mock.patch.object(premium_pool_release, "active_deployment_candidate", return_value={"baselineId": "sha256:" + "b" * 64}),
                mock.patch.object(premium_pool_release, "load_candidate_manifest", return_value={
                    "packageDigest": "sha256:" + "c" * 64, "sourceRevision": "a" * 40,
                    "release": {"candidate": {"releaseId": "release-1", "releaseDigest": digest,
                                               "attestationRef": str(attestation), "attestationDigest": attestation_digest}},
                }),
            ):
                binding = premium_pool_release.load_premium_pool_bootstrap_binding(
                    environment="alpha", target="alpha-local", import_report=path,
                    content_id="post-video-1", pool_is_empty=True,
                )
                self.assertEqual(binding.import_run_id, "apply-1")
                self.assertEqual(binding.content_id, "post-video-1")
                self.assertEqual(json.loads(path.read_bytes())["postBindings"][0]["usageScope"], "research")
                for field in ("readinessPhase", "releaseClass", "productLifecycleState"):
                    path.write_text(json.dumps({**report, field: "production"}), encoding="utf-8")
                    with self.subTest(field=field), self.assertRaisesRegex(premium_pool_release.PremiumPoolReleaseError, "import_report schema"):
                        premium_pool_release.load_premium_pool_bootstrap_binding(
                            environment="alpha", target="alpha-local", import_report=path,
                            content_id="post-video-1", pool_is_empty=True,
                        )

    def test_test_live_rejects_unknown_schema_and_symlink_receipt_ancestors(self) -> None:
        # spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            receipt, binding = _test_live_readiness_fixture(root)
            source = receipt.read_bytes()
            with (
                mock.patch.object(premium_pool_release, "output_root", return_value=root),
                mock.patch.object(premium_pool_release, "load_test_live_content_binding", return_value=binding),
            ):
                for field, value in (("unknownCategory", "default"), ("guestLogin", {}), ("verificationChecksum", "sha256:" + "0" * 64)):
                    raw = json.dumps({**json.loads(source), field: value}).encode()
                    receipt.write_bytes(raw)
                    binding["readinessReceiptDigest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
                    with self.subTest(field=field), self.assertRaises(premium_pool_release.PremiumPoolReleaseError):
                        premium_pool_release.load_premium_pool_test_live_binding(
                            environment="alpha", target="alpha-local", readiness_receipt=receipt, content_id="video-1",
                        )
                receipt.write_bytes(source)
                binding["readinessReceiptDigest"] = "sha256:" + hashlib.sha256(source).hexdigest()
                real_parent = receipt.parent.with_name("actual-verify")
                receipt.parent.rename(real_parent)
                receipt.parent.symlink_to(real_parent, target_is_directory=True)
                with self.assertRaisesRegex(premium_pool_release.PremiumPoolReleaseError, "non-symlink"):
                    premium_pool_release.load_premium_pool_test_live_binding(
                        environment="alpha", target="alpha-local", readiness_receipt=receipt, content_id="video-1",
                    )

    def test_test_live_binding_accepts_no_category_and_rejects_category_fields(
        self,
    ) -> None:
        # spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
        cases = [(None, None)] + [
            (field, phase)
            for field in ("readinessPhase", "releaseClass", "productLifecycleState")
            for phase in ("production", "default", "consumer", "commercial", "research", "import", "", None)
        ]
        for field, phase in cases:
            with self.subTest(field=field, phase=phase), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                receipt, content_binding = _test_live_readiness_fixture(root)
                if field is not None:
                    readiness = json.loads(receipt.read_bytes())
                    readiness[field] = phase
                    receipt.write_text(json.dumps(_with_checksum(readiness)), encoding="utf-8")
                    content_binding["readinessReceiptDigest"] = "sha256:" + hashlib.sha256(receipt.read_bytes()).hexdigest()
                original_receipt = receipt.read_bytes()
                with (
                    mock.patch.object(
                        premium_pool_release,
                        "output_root",
                        return_value=root,
                    ),
                    mock.patch.object(
                        premium_pool_release,
                        "load_test_live_content_binding",
                        return_value=content_binding,
                    ),
                ):
                    if field is not None:
                        with self.assertRaisesRegex(
                            premium_pool_release.PremiumPoolReleaseError,
                            "environment_release_readiness schema",
                        ):
                            premium_pool_release.load_premium_pool_test_live_binding(
                                environment="alpha",
                                target="alpha-local",
                                readiness_receipt=receipt,
                                content_id="video-1",
                            )
                        continue
                    binding = premium_pool_release.load_premium_pool_test_live_binding(
                        environment="alpha",
                        target="alpha-local",
                        readiness_receipt=receipt,
                        content_id="video-1",
                    )

                self.assertEqual(receipt.read_bytes(), original_receipt)
                self.assertTrue(json.loads(original_receipt)["containsUnverifiedAssets"])
                self.assertFalse(hasattr(binding, "readiness_phase"))
                self.assertEqual(binding.startup_attempt_id, "attempt-alpha-1")
                self.assertEqual(binding.content_id, "video-1")

    def test_test_live_binding_requires_a_video_sample_and_never_guesses_query(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            receipt, content_binding = _test_live_readiness_fixture(root)
            readiness = json.loads(receipt.read_text(encoding="utf-8"))
            for query in readiness["feedQueries"]:
                if query["name"] == "typed_video":
                    query["matchedPostIds"] = ["image-1"]
            encoded = json.dumps(_with_checksum(readiness), sort_keys=True).encode("utf-8")
            receipt.write_bytes(encoded)
            content_binding["readinessReceiptDigest"] = (
                "sha256:" + hashlib.sha256(encoded).hexdigest()
            )
            with (
                mock.patch.object(
                    premium_pool_release, "output_root", return_value=root
                ),
                mock.patch.object(
                    premium_pool_release,
                    "load_test_live_content_binding",
                    return_value=content_binding,
                ),
            ):
                binding = premium_pool_release.load_premium_pool_test_live_binding(
                    environment="alpha",
                    target="alpha-local",
                    readiness_receipt=receipt,
                    content_id="video-1",
                )
            self.assertEqual(binding.content_id, "video-1")

            content_binding["appUatPlan"] = {
                **content_binding["appUatPlan"],
                "orderedSamples": [],
            }
            with (
                mock.patch.object(
                    premium_pool_release, "output_root", return_value=root
                ),
                mock.patch.object(
                    premium_pool_release,
                    "load_test_live_content_binding",
                    return_value=content_binding,
                ),
                self.assertRaisesRegex(
                    premium_pool_release.PremiumPoolReleaseError,
                    "no required video sample",
                ),
            ):
                premium_pool_release.load_premium_pool_test_live_binding(
                    environment="alpha",
                    target="alpha-local",
                    readiness_receipt=receipt,
                    content_id="video-1",
                )

    def test_test_live_binding_rejects_unbound_cross_target_stale_or_wrong_video(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            receipt, content_binding = _test_live_readiness_fixture(root)
            with (
                mock.patch.object(
                    premium_pool_release,
                    "output_root",
                    return_value=root,
                ),
                mock.patch.object(
                    premium_pool_release,
                    "load_test_live_content_binding",
                    return_value=None,
                ),
                self.assertRaisesRegex(
                    premium_pool_release.PremiumPoolReleaseError,
                    "current test-live content binding is required",
                ),
            ):
                premium_pool_release.load_premium_pool_test_live_binding(
                    environment="alpha",
                    target="alpha-local",
                    readiness_receipt=receipt,
                    content_id="video-1",
                )

            with (
                mock.patch.object(
                    premium_pool_release,
                    "load_test_live_content_binding",
                    return_value={
                        **content_binding,
                        "startupAttemptId": "",
                    },
                ),
                self.assertRaisesRegex(
                    premium_pool_release.PremiumPoolReleaseError,
                    "binding is partial",
                ),
            ):
                premium_pool_release.load_premium_pool_test_live_binding(
                    environment="alpha",
                    target="alpha-local",
                    readiness_receipt=receipt,
                    content_id="video-1",
                )

            for environment, target in (
                ("alpha", "beta-local"),
                ("prod", "prod-local"),
            ):
                with (
                    self.subTest(environment=environment, target=target),
                    self.assertRaisesRegex(
                        premium_pool_release.PremiumPoolReleaseError,
                        "exact Alpha/Beta/Gamma local target",
                    ),
                ):
                    premium_pool_release.load_premium_pool_test_live_binding(
                        environment=environment,
                        target=target,
                        readiness_receipt=receipt,
                        content_id="video-1",
                    )

            with (
                mock.patch.object(
                    premium_pool_release,
                    "load_test_live_content_binding",
                    return_value={
                        **content_binding,
                        "contentBindingState": "unbound",
                    },
                ),
                self.assertRaisesRegex(
                    premium_pool_release.PremiumPoolReleaseError,
                    "identity mismatch",
                ),
            ):
                premium_pool_release.load_premium_pool_test_live_binding(
                    environment="alpha",
                    target="alpha-local",
                    readiness_receipt=receipt,
                    content_id="video-1",
                )

            for label, supplied_receipt, supplied_content_id, binding_patch in (
                (
                    "stale path",
                    root / "other/release-readiness.json",
                    "video-1",
                    content_binding,
                ),
                (
                    "stale digest",
                    receipt,
                    "video-1",
                    {
                        **content_binding,
                        "readinessReceiptDigest": "sha256:" + "9" * 64,
                    },
                ),
                ("wrong video", receipt, "video-other", content_binding),
            ):
                with (
                    self.subTest(label=label),
                    mock.patch.object(
                        premium_pool_release,
                        "output_root",
                        return_value=root,
                    ),
                    mock.patch.object(
                        premium_pool_release,
                        "load_test_live_content_binding",
                        return_value=binding_patch,
                    ),
                    self.assertRaises(premium_pool_release.PremiumPoolReleaseError),
                ):
                    premium_pool_release.load_premium_pool_test_live_binding(
                        environment="alpha",
                        target="alpha-local",
                        readiness_receipt=supplied_receipt,
                        content_id=supplied_content_id,
                    )

    def test_test_live_receipt_and_tokens_bind_attempt_and_mutable_identity(
        self,
    ) -> None:
        runtime_identity = {
            "mutableStateDigest": "sha256:" + "a" * 64,
            "configurationDigest": "sha256:" + "b" * 64,
            "providerRuntimeDigest": "sha256:" + "c" * 64,
        }
        binding = premium_pool_release.PremiumPoolTestLiveBinding(
            environment="alpha",
            target="alpha-local",
            release_id="release-1",
            manifest_digest="sha256:" + "d" * 64,
            import_run_id="apply-1",
            verify_run_id="verify-1",
            content_id="video-1",
            readiness_receipt_ref="env/alpha/runs/readiness.json",
            readiness_receipt_digest="sha256:" + "e" * 64,
            startup_attempt_id="attempt-alpha-1",
            runtime_identity=runtime_identity,
        )
        changed_attempt = replace(
            binding,
            startup_attempt_id="attempt-alpha-2",
        )
        changed_mutable = replace(
            binding,
            runtime_identity={
                **runtime_identity,
                "mutableStateDigest": "sha256:" + "f" * 64,
            },
        )

        receipt_binding = premium_pool_release._premium_receipt_binding(binding)

        self.assertNotIn("candidate", receipt_binding)
        self.assertNotIn("packageDigest", json.dumps(receipt_binding))
        self.assertEqual(
            receipt_binding["testLiveBinding"]["launchPolicy"],
            "test_live",
        )
        self.assertIs(
            receipt_binding["testLiveBinding"]["nonPromotable"],
            True,
        )
        for changed in (changed_attempt, changed_mutable):
            self.assertNotEqual(
                premium_pool_release._premium_idempotency_identity(binding),
                premium_pool_release._premium_idempotency_identity(changed),
            )
            self.assertNotEqual(
                premium_pool_release._premium_rollback_token(binding),
                premium_pool_release._premium_rollback_token(changed),
            )

        with mock.patch.object(
            premium_pool_release,
            "_wait_for_premium_projection",
            return_value=["video-1"],
        ):
            receipt = premium_pool_release.execute_premium_pool_readback(
                binding=binding,
                api_base_url="https://api.alpha.quwoquan.local",
                ssl_cafile="/tmp/root.pem",
                projection_deadline_seconds=1.0,
            )
        self.assertNotIn("candidate", receipt)
        self.assertEqual(
            receipt["testLiveBinding"]["startupAttemptId"],
            "attempt-alpha-1",
        )
        self.assertEqual(
            receipt["testLiveBinding"]["readinessReceiptDigest"],
            "sha256:" + "e" * 64,
        )

    def test_stackctl_test_live_dispatch_never_reads_active_candidate(self) -> None:
        binding = premium_pool_release.PremiumPoolTestLiveBinding(
            environment="alpha",
            target="alpha-local",
            release_id="release-1",
            manifest_digest="sha256:" + "a" * 64,
            import_run_id="apply-1",
            verify_run_id="verify-1",
            content_id="video-1",
            readiness_receipt_ref="env/alpha/runs/readiness.json",
            readiness_receipt_digest="sha256:" + "b" * 64,
            startup_attempt_id="attempt-alpha-1",
            runtime_identity={
                "mutableStateDigest": "sha256:" + "c" * 64,
                "configurationDigest": "sha256:" + "d" * 64,
                "providerRuntimeDigest": "sha256:" + "e" * 64,
            },
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(
                stackctl,
                "get_target",
                return_value={
                    "env": "alpha",
                    "publicBases": {
                        "api": "https://api.alpha.quwoquan.com",
                        "productOps": "https://ops.alpha.quwoquan.com",
                    },
                },
            ),
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary),
            ),
            mock.patch.object(
                stackctl,
                "load_premium_pool_candidate_binding",
            ) as candidate_loader,
            mock.patch.object(
                stackctl,
                "load_premium_pool_test_live_binding",
                return_value=binding,
            ) as test_live_loader,
            mock.patch.object(
                public_domain_tls,
                "root_certificate_path",
                return_value=Path("/tmp/root.pem"),
            ),
            mock.patch.object(
                stackctl,
                "execute_premium_pool_readback",
                return_value={"status": "passed"},
            ) as execute_readback,
        ):
            result = stackctl.command_premium_pool(
                argparse.Namespace(
                    target="alpha-local",
                    action="verify-readback",
                    launch_policy="test-live",
                    readiness_receipt="receipt.json",
                    content_id="video-1",
                    quality_score=None,
                    expires_at=None,
                    projection_deadline_seconds=1.0,
                )
            )

        self.assertEqual(result["exitCode"], 0)
        candidate_loader.assert_not_called()
        test_live_loader.assert_called_once_with(
            environment="alpha",
            target="alpha-local",
            readiness_receipt="receipt.json",
            content_id="video-1",
        )
        execute_readback.assert_called_once()

    def test_stackctl_gamma_gate_block_report_never_contains_bearer(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary),
            ),
            mock.patch.object(
                stackctl,
                "load_premium_pool_candidate_binding",
                return_value=mock.sentinel.binding,
            ),
            mock.patch.object(
                public_domain_tls,
                "root_certificate_path",
                return_value=Path("/tmp/root.pem"),
            ),
            mock.patch.object(
                stackctl,
                "open_premium_pool_operator_session",
                side_effect=premium_pool_release.PremiumPoolReleaseError(
                    "GATE_BLOCK: target-scoped operator material is unavailable"
                ),
            ),
        ):
            result = stackctl.command_premium_pool(
                argparse.Namespace(
                    target="gamma-local",
                    action="upsert-and-verify",
                    readiness_receipt="receipt.json",
                    content_id="video-1",
                    quality_score=0.88,
                    expires_at="2099-01-01T00:00:00Z",
                    projection_deadline_seconds=1.0,
                )
            )
            report = json.loads(
                (Path(temporary) / "report.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(report["status"], "gate_block")
        self.assertNotIn("Bearer", json.dumps(report))

    def test_content_release_readback_needs_no_operator_credential(self) -> None:
        binding = premium_pool_release.PremiumPoolCandidateBinding(
            environment="alpha",
            target="alpha-local",
            baseline_id="sha256:" + "a" * 64,
            package_digest="sha256:" + "b" * 64,
            source_revision="revision-1",
            release_id="release-1",
            manifest_digest="sha256:" + "c" * 64,
            import_run_id="apply-1",
            verify_run_id="verify-1",
            content_id="video-1",
            readiness_receipt_ref="run/release-readiness.json",
        )
        with mock.patch.object(
            premium_pool_release,
            "_wait_for_premium_projection",
            return_value=["video-1"],
        ) as wait:
            receipt = premium_pool_release.execute_premium_pool_readback(
                binding=binding,
                api_base_url="https://api.alpha.quwoquan.local",
                ssl_cafile="/tmp/root.pem",
                projection_deadline_seconds=1.0,
            )

        self.assertEqual(receipt["schema"], "qwq.premium_pool_readback_receipt")
        self.assertEqual(receipt["recommendationReadback"]["contentId"], "video-1")
        self.assertEqual(
            receipt["candidate"],
            {
                "baselineId": "sha256:" + "a" * 64,
                "packageDigest": "sha256:" + "b" * 64,
                "sourceRevision": "revision-1",
                "releaseId": "release-1",
                "manifestDigest": "sha256:" + "c" * 64,
                "importRunId": "apply-1",
                "verifyRunId": "verify-1",
                "readinessReceiptRef": "run/release-readiness.json",
            },
        )
        self.assertNotIn("testLiveBinding", receipt)
        self.assertNotIn("operator", receipt)
        wait.assert_called_once()

    def test_premium_feed_readback_uses_canonical_client_session_header(self) -> None:
        with mock.patch.object(
            premium_pool_release,
            "_request_json",
            return_value={"items": [{"id": "video-1"}]},
        ) as request_json:
            matched = premium_pool_release._wait_for_premium_projection(
                api_base_url="https://api.alpha.quwoquan.local",
                content_id="video-1",
                client_session_id="premium-readback-session",
                ssl_cafile="/tmp/root.pem",
                deadline_seconds=1.0,
            )

        self.assertEqual(matched, ["video-1"])
        self.assertEqual(
            request_json.call_args.kwargs["headers"],
            {"X-Client-Session-Id": "premium-readback-session"},
        )

    def test_parser_requires_explicit_test_live_launch_policy(self) -> None:
        args = stackctl.build_parser().parse_args(
            [
                "premium-pool",
                "--target",
                "alpha-local",
                "--action",
                "upsert-and-verify",
                "--readiness-receipt",
                "receipt.json",
                "--content-id",
                "video-1",
                "--quality-score",
                "0.88",
                "--expires-at",
                "2099-01-01T00:00:00Z",
            ]
        )
        self.assertEqual(args.command, "premium-pool")
        self.assertEqual(args.target, "alpha-local")
        self.assertEqual(args.launch_policy, "immutable-candidate")

        readback_args = stackctl.build_parser().parse_args(
            [
                "premium-pool",
                "--target",
                "alpha-local",
                "--action",
                "verify-readback",
                "--readiness-receipt",
                "receipt.json",
                "--content-id",
                "video-1",
            ]
        )
        self.assertEqual(readback_args.action, "verify-readback")
        self.assertIsNone(readback_args.quality_score)

        test_live_args = stackctl.build_parser().parse_args(
            [
                "premium-pool",
                "--target",
                "alpha-local",
                "--launch-policy",
                "test-live",
                "--action",
                "verify-readback",
                "--readiness-receipt",
                "receipt.json",
                "--content-id",
                "video-1",
            ]
        )
        self.assertEqual(test_live_args.launch_policy, "test-live")


if __name__ == "__main__":
    unittest.main()

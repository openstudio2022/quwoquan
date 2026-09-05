# spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-002
# spec_ref: specs/feature-tree/platform-ops-governance/security-privacy-audit/spec.md#sit-001
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.lib.app_identity import resolve_build_product
from quwoquan_ops.cli.lib.official_distribution_release import (
    OfficialDistributionReleaseError,
    deploy_official_distribution,
    inspect_official_distribution,
    prevalidate_android_distribution_candidate,
)
from quwoquan_ops.cli.lib.web_official_release import web_official_content_digest
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.tests.support.app_artifact_manifest_test_support import (
    app_artifact_manifest,
)
from quwoquan_ops.tests.support.app_pipeline_web_artifact_test_support import (
    write_valid_web_artifact,
)

APP_EVIDENCE_REF = (
    "oci://ghcr.io/owner/repo/app-candidate@sha256:" + ("e" * 64)
)


class OfficialDistributionReleaseTest(unittest.TestCase):
    def test_android_candidate_prevalidates_download_object_and_latest_pointer(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            android_manifest = _android_package(
                root / "android-package",
                build="18201",
            )

            report = prevalidate_android_distribution_candidate(
                package_manifest_path=android_manifest,
                scratch_root=root / "preflight",
            )

            self.assertEqual(report["status"], "component-ready")
            self.assertTrue(report["downloadObjectValidated"])
            self.assertTrue(report["latestPointerValidated"])
            self.assertEqual(report["buildNumber"], "18201")

    def test_web_and_android_are_bound_to_one_release_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web_manifest = _web_package(root / "web-package")
            android_manifest = _android_package(root / "android-package", build="18201")
            release_manifest = _release_manifest(
                root / "candidate",
                web_manifest=web_manifest,
                android_manifest=android_manifest,
            )
            distribution = root / "origin"

            web_receipt = deploy_official_distribution(
                kind="web",
                package_manifest_path=web_manifest,
                release_manifest_path=release_manifest,
                distribution_root=distribution,
            )
            android_receipt = deploy_official_distribution(
                kind="app-release",
                package_manifest_path=android_manifest,
                release_manifest_path=release_manifest,
                distribution_root=distribution,
            )

            self.assertEqual(
                web_receipt["artifactDigest"],
                android_receipt["artifactDigest"],
            )
            release = json.loads(release_manifest.read_text(encoding="utf-8"))
            for build_product_id in ("web-shared", "android-prod-apk"):
                descriptor = release["applicationPackages"][build_product_id]
                evidence = json.loads(
                    (release_manifest.parent / descriptor["path"]).read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(descriptor["packageDigest"], evidence["packageDigest"])
                self.assertNotEqual(
                    descriptor["packageDigest"],
                    evidence["artifactManifest"]["artifactDigest"],
                )
            self.assertTrue((distribution / "web" / "current").is_symlink())
            latest = json.loads(
                (distribution / "download" / "android" / "latest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(latest["buildNumber"], "18201")
            product_ops_environment = (
                distribution / "product-ops/app-release/current.env"
            ).read_text(encoding="utf-8")
            self.assertIn("PRODUCT_OPS_ANDROID_LATEST_BUILD=18201", product_ops_environment)
            self.assertIn(
                "PRODUCT_OPS_ANDROID_MINIMUM_SUPPORTED_BUILD=17000",
                product_ops_environment,
            )
            self.assertNotIn(
                "PRODUCT_OPS_APP_RELEASE_RECOVERY_URL", product_ops_environment
            )
            self.assertEqual(
                inspect_official_distribution(distribution_root=distribution)["status"],
                "ready",
            )

    def test_android_latest_pointer_uses_cas_and_preserves_old_apk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web_manifest = _web_package(root / "web-package")
            first = _android_package(root / "android-18201", build="18201")
            first_release = _release_manifest(
                root / "candidate-1",
                web_manifest=web_manifest,
                android_manifest=first,
            )
            distribution = root / "origin"
            deploy_official_distribution(
                kind="app-release",
                package_manifest_path=first,
                release_manifest_path=first_release,
                distribution_root=distribution,
            )

            second = _android_package(root / "android-18301", build="18301")
            second_release = _release_manifest(
                root / "candidate-2",
                web_manifest=web_manifest,
                android_manifest=second,
            )
            with self.assertRaisesRegex(
                OfficialDistributionReleaseError,
                "CAS conflict",
            ):
                deploy_official_distribution(
                    kind="app-release",
                    package_manifest_path=second,
                    release_manifest_path=second_release,
                    distribution_root=distribution,
                    expected_current="wrong-build",
                )
            deploy_official_distribution(
                kind="app-release",
                package_manifest_path=second,
                release_manifest_path=second_release,
                distribution_root=distribution,
                expected_current="18201",
            )
            self.assertTrue(
                (
                    distribution
                    / "download/android/1.8.2/18201/quwoquan-18201.apk"
                ).is_file()
            )
            self.assertEqual(
                json.loads(
                    (distribution / "download/android/latest.json").read_text()
                )["buildNumber"],
                "18301",
            )

    def test_web_deploy_rejects_digest_bound_nonofficial_artifact_before_pointer(
        self,
    ) -> None:
        for invalid_artifact in (
            "missing-bootstrap",
            "missing-font",
            "embedded-runtime",
        ):
            with (
                self.subTest(invalid_artifact=invalid_artifact),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                web_manifest = _web_package(root / "web-package")
                public = web_manifest.parent / "public"
                if invalid_artifact == "missing-bootstrap":
                    (public / "qwq_bootstrap.js").unlink()
                elif invalid_artifact == "missing-font":
                    next(public.rglob("NotoSansSC*.ttf")).unlink()
                else:
                    (public / "runtime-config-trust.json").write_text(
                        "{}", encoding="utf-8"
                    )
                _rebind_web_package(web_manifest)
                android_manifest = _android_package(
                    root / "android-package",
                    build="18201",
                )
                release_manifest = _release_manifest(
                    root / "candidate",
                    web_manifest=web_manifest,
                    android_manifest=android_manifest,
                )
                distribution = root / "origin"

                with self.assertRaisesRegex(
                    OfficialDistributionReleaseError,
                    "deployed Web artifact is not official",
                ):
                    deploy_official_distribution(
                        kind="web",
                        package_manifest_path=web_manifest,
                        release_manifest_path=release_manifest,
                        distribution_root=distribution,
                    )
                current = distribution / "web/current"
                self.assertFalse(current.exists() or current.is_symlink())

    def test_rejects_package_not_bound_by_candidate_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web_manifest = _web_package(root / "web-package")
            android_manifest = _android_package(root / "android-package", build="18201")
            release_manifest = _release_manifest(
                root / "candidate",
                web_manifest=web_manifest,
                android_manifest=android_manifest,
            )
            package = json.loads(android_manifest.read_text(encoding="utf-8"))
            package["apkSHA256"] = "e" * 64
            android_manifest.write_text(json.dumps(package), encoding="utf-8")
            with self.assertRaisesRegex(
                OfficialDistributionReleaseError,
                "distribution artifact digest mismatch",
            ):
                deploy_official_distribution(
                    kind="app-release",
                    package_manifest_path=android_manifest,
                    release_manifest_path=release_manifest,
                    distribution_root=root / "origin",
                )

    def test_rejects_descriptor_only_url_drift_before_first_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web_manifest = _web_package(root / "web-package")
            android_manifest = _android_package(root / "android-package", build="18201")
            release_manifest = _release_manifest(
                root / "candidate",
                web_manifest=web_manifest,
                android_manifest=android_manifest,
            )
            drifted = json.loads(android_manifest.read_text(encoding="utf-8"))
            drifted["apkUrl"] = (
                "https://cdn.quwoquan.com/download/android/1.8.2/18201/other.apk"
            )
            _write_json(android_manifest, drifted)
            distribution = root / "origin"

            with self.assertRaisesRegex(
                OfficialDistributionReleaseError,
                "distribution evidence mismatch",
            ):
                deploy_official_distribution(
                    kind="app-release",
                    package_manifest_path=android_manifest,
                    release_manifest_path=release_manifest,
                    distribution_root=distribution,
                )
            self.assertFalse(distribution.exists())

    def test_rejects_distribution_source_identity_drift_before_first_write(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web_manifest = _web_package(root / "web-package")
            drifted = json.loads(web_manifest.read_text(encoding="utf-8"))
            drifted["sourceGitSha"] = "f" * 40
            _write_json(web_manifest, drifted)
            android_manifest = _android_package(root / "android-package", build="18201")
            release_manifest = _release_manifest(
                root / "candidate",
                web_manifest=web_manifest,
                android_manifest=android_manifest,
            )
            distribution = root / "origin"

            with self.assertRaisesRegex(
                OfficialDistributionReleaseError,
                "source identity mismatch",
            ):
                deploy_official_distribution(
                    kind="web",
                    package_manifest_path=web_manifest,
                    release_manifest_path=release_manifest,
                    distribution_root=distribution,
                )
            self.assertFalse(distribution.exists())

    def test_rejects_noncanonical_distribution_fields_before_first_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            web_manifest = _web_package(root / "web-package")
            android_manifest = _android_package(root / "android-package", build="18201")
            release_manifest = _release_manifest(
                root / "candidate",
                web_manifest=web_manifest,
                android_manifest=android_manifest,
            )
            drifted = json.loads(web_manifest.read_text(encoding="utf-8"))
            drifted["compatibilityUrl"] = "https://quwoquan.com/legacy"
            _write_json(web_manifest, drifted)
            distribution = root / "origin"

            with self.assertRaisesRegex(
                OfficialDistributionReleaseError,
                "fields are not canonical",
            ):
                deploy_official_distribution(
                    kind="web",
                    package_manifest_path=web_manifest,
                    release_manifest_path=release_manifest,
                    distribution_root=distribution,
                )
            self.assertFalse(distribution.exists())


def _web_package(root: Path) -> Path:
    public = root / "public"
    root.mkdir(parents=True)
    write_valid_web_artifact(public)
    content_digest = _tree_sha256(public)
    manifest = {
        "schema": "client-app.web.official-release",
        "sourceGitSha": "b" * 40,
        "sourceTreeDigest": "sha1:" + ("c" * 40),
        "environment": "prod",
        "publicOrigin": "https://quwoquan.com",
        "releaseId": content_digest[:20],
        "contentSHA256": content_digest,
        "noindex": False,
        "spaFallback": "/index.html",
        "htmlContentType": "text/html; charset=utf-8",
        "assetCacheControl": "no-cache, must-revalidate",
        "serviceWorker": "flutter_service_worker.js",
        "artifactManifest": app_artifact_manifest(
            build_product_id="web-shared",
            source_git_sha="b" * 40,
            source_tree_digest="sha1:" + ("c" * 40),
            artifact_digest="sha256:" + content_digest,
        ),
    }
    path = root / "manifest.json"
    _write_json(path, manifest)
    return path


def _rebind_web_package(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = _tree_sha256(manifest_path.parent / "public")
    manifest["releaseId"] = digest[:20]
    manifest["contentSHA256"] = digest
    manifest["artifactManifest"]["artifactDigest"] = "sha256:" + digest
    _write_json(manifest_path, manifest)


def _android_package(
    root: Path,
    *,
    build: str,
    source_git_sha: str = "b" * 40,
    source_tree_digest: str = "sha1:" + ("c" * 40),
) -> Path:
    root.mkdir(parents=True)
    apk = root / f"quwoquan-{build}.apk"
    apk.write_bytes(f"signed-apk-{build}".encode("utf-8"))
    manifest = {
        "schema": "client-app.android.official-release",
        "sourceGitSha": source_git_sha,
        "sourceTreeDigest": source_tree_digest,
        "platform": "android",
        "versionName": "1.8.2",
        "buildNumber": build,
        "minAndroidVersion": "26",
        "packageName": "com.leadwise.quwoquan",
        "apkUrl": (
            "https://cdn.quwoquan.com/download/android/1.8.2/"
            f"{build}/quwoquan-{build}.apk"
        ),
        "apkSHA256": hashlib.sha256(apk.read_bytes()).hexdigest(),
        "apkSizeBytes": apk.stat().st_size,
        "apkSigningCertificateSHA256": "a" * 64,
        "apkHostAllowlist": ["cdn.quwoquan.com"],
        "publicOrigin": "https://quwoquan.com",
        "recoveryUrl": "https://quwoquan.com/download",
        "updateUrl": (
            "https://cdn.quwoquan.com/download/android/1.8.2/"
            f"{build}/quwoquan-{build}.apk"
        ),
        "minimumSupportedVersion": "1.7.0",
        "minimumSupportedBuild": "17000",
        "packagedAPK": apk.name,
        "remoteVerified": False,
        "artifactManifest": app_artifact_manifest(
            build_product_id="android-prod-apk",
            source_git_sha=source_git_sha,
            source_tree_digest=source_tree_digest,
            artifact_digest="sha256:" + hashlib.sha256(apk.read_bytes()).hexdigest(),
        ),
    }
    path = root / "manifest.json"
    _write_json(path, manifest)
    return path


def _release_manifest(
    root: Path,
    *,
    web_manifest: Path,
    android_manifest: Path,
    application_package_sources: dict[str, Path] | None = None,
) -> Path:
    root.mkdir(parents=True)
    official_payloads = {
        "web-shared": json.loads(web_manifest.read_text(encoding="utf-8")),
        "android-prod-apk": json.loads(
            android_manifest.read_text(encoding="utf-8")
        ),
    }
    source_git_sha = str(
        official_payloads["web-shared"]["artifactManifest"]["sourceGitSha"]
    )
    source_tree_digest = str(
        official_payloads["web-shared"]["artifactManifest"]["sourceTreeDigest"]
    )
    if any(
        payload["artifactManifest"]["sourceGitSha"] != source_git_sha
        or payload["artifactManifest"]["sourceTreeDigest"] != source_tree_digest
        for payload in official_payloads.values()
    ):
        raise AssertionError("test distribution inputs must share one source identity")
    application_package_sources = application_package_sources or {}
    application_packages: dict[str, dict[str, str]] = {}
    for build_product_id in finalizer.APPLICATION_PACKAGES:
        destination = (
            root / "packages/applications" / build_product_id / "manifest.json"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        product = resolve_build_product(build_product_id)
        source_path = application_package_sources.get(build_product_id)
        if source_path is not None:
            destination.write_bytes(source_path.read_bytes())
            application_evidence = json.loads(
                destination.read_text(encoding="utf-8")
            )
        else:
            package_digest = "sha256:" + hashlib.sha256(
                f"payload-tree:{build_product_id}".encode("utf-8")
            ).hexdigest()
            official = official_payloads.get(build_product_id)
            artifact_manifest = (
                official["artifactManifest"]
                if official is not None
                else app_artifact_manifest(
                    build_product_id=build_product_id,
                    source_git_sha=source_git_sha,
                    source_tree_digest=source_tree_digest,
                    artifact_digest="sha256:" + hashlib.sha256(
                        f"artifact:{build_product_id}".encode("utf-8")
                    ).hexdigest(),
                )
            )
            application_evidence = {
                "schema": finalizer.APPLICATION_PACKAGE_SCHEMA,
                "buildProductId": product.build_product_id,
                "buildProfile": product.build_profile,
                "platform": product.platform,
                "sourceGitSha": source_git_sha,
                "sourceTreeDigest": source_tree_digest,
                "packageDigest": package_digest,
                "artifactManifest": artifact_manifest,
            }
            _write_json(destination, application_evidence)
        application_packages[build_product_id] = {
            "path": destination.relative_to(root).as_posix(),
            "digest": _sha256_prefixed(destination),
            "packageDigest": str(application_evidence["packageDigest"]),
            "sourceRef": APP_EVIDENCE_REF,
        }

    distribution_descriptors: dict[str, dict[str, str]] = {}
    for evidence_key, source_path in (
        ("publicWeb", web_manifest),
        ("androidOfficialRelease", android_manifest),
    ):
        destination = root / finalizer.DISTRIBUTION_EVIDENCE_PATHS[evidence_key]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_path.read_bytes())
        distribution_descriptors[evidence_key] = {
            "path": destination.relative_to(root).as_posix(),
            "digest": _sha256_prefixed(destination),
        }

    # opsPortal 不是 App build product，它在 ReleaseEvidence 里是独立顶层证据。
    ops_portal_manifest = root / "packages/opsPortal/manifest.json"
    ops_portal_manifest.parent.mkdir(parents=True, exist_ok=True)
    ops_portal_manifest.write_text(
        json.dumps(
            {
                "schema": "qwq.ops_portal_package",
                "sourceGitSha": source_git_sha,
                "sourceTreeDigest": source_tree_digest,
                "packageDigest": "sha256:" + ("d" * 64),
            }
        ),
        encoding="utf-8",
    )
    ops_portal_package = {
        "path": ops_portal_manifest.relative_to(root).as_posix(),
        "digest": _sha256_prefixed(ops_portal_manifest),
        "packageDigest": "sha256:" + ("d" * 64),
        "sourceRef": APP_EVIDENCE_REF,
    }

    configuration_packages: dict[str, dict[str, dict[str, str]]] = {}
    for environment in finalizer.ENVIRONMENTS:
        config = (
            root
            / "packages/environments"
            / environment
            / "services/content-service/config/config.yaml"
        )
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(
            f"config:\n  environment: {environment}\n", encoding="utf-8"
        )
        configuration_packages[environment] = {
            "content-service": {
                "path": config.relative_to(root).as_posix(),
                "digest": _sha256_prefixed(config),
            }
        }
    repository = "ghcr.io/owner/repo/content-service"
    image_digest = "sha256:" + ("a" * 64)
    image_ref = f"{repository}@{image_digest}"

    evidence = root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    contract_graph = evidence / "contractGraph.json"
    contract_graph.write_text("{}", encoding="utf-8")
    provider_readiness = {
        environment: {
            "fixture.capability": {
                "required": True,
                "capability_ready": True,
            }
        }
        for environment in finalizer.ENVIRONMENTS
    }
    provider_evidence_count = (
        finalizer.expected_required_cell_count_from_readiness(provider_readiness)
    )
    provider_raw_files: dict[str, str] = {}
    for index in range(provider_evidence_count):
        provider_raw = root / f"evidence/raw/provider/{index:03d}.json"
        provider_raw.parent.mkdir(parents=True, exist_ok=True)
        _write_json(provider_raw, {"status": "passed", "cell": index})
        provider_raw_files[provider_raw.relative_to(root).as_posix()] = (
            _sha256_prefixed(provider_raw)
        )
    provider_transport_digest = "sha256:" + ("d" * 64)
    provider = evidence / "providerEvidence.json"
    _write_json(
        provider,
        {
            "schema": "provider-conformance-readiness",
            "status": "passed",
            "evidenceCount": provider_evidence_count,
            "readiness": provider_readiness,
            "sourceEvidence": {
                "ref": (
                    "oci://ghcr.io/owner/repo/provider-evidence@"
                    + provider_transport_digest
                ),
                "digest": provider_transport_digest,
                "files": provider_raw_files,
            },
        },
    )
    test_evidence_files: dict[str, dict[str, str]] = {}
    for label, relative in finalizer.RELEASE_CLOSURE_PATHS.items():
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        _write_json(source, {"label": label, "status": "passed"})
        test_evidence_files[label] = {
            "path": relative,
            "digest": _sha256_prefixed(source),
        }
    test_evidence = {
        "schema": "qwq.three-layer-case-results",
        "status": "passed",
        "layers": {
            layer: {"status": "passed", "artifactDigest": image_digest}
            for layer in finalizer.TEST_LAYERS
        },
        "evidence": {"files": test_evidence_files},
    }
    tests = evidence / "testEvidence.json"
    _write_json(tests, test_evidence)

    manifest = finalizer.seal_manifest({
        "schema": finalizer.SCHEMA,
        "releaseTrainId": None,
        "releaseCompositionId": None,
        "status": "qualified",
        "generatedAt": "2026-07-28T00:00:00Z",
        "source": {
            "gitSha": source_git_sha,
            "treeDigest": source_tree_digest,
            "repository": "owner/repo",
            "workflowRunId": "42",
            "sourceArchiveDigest": None,
        },
        "artifactDigest": None,
        "environmentArtifacts": {
            environment: {
                "environment": environment,
                "environmentArtifactDigest": None,
                "images": {
                    "content-service": {
                        "repository": (
                            repository
                            + "-"
                            + ("prod" if environment == "prod" else "nonprod")
                        ),
                        "transportRef": (
                            repository
                            + "-"
                            + ("prod" if environment == "prod" else "nonprod")
                            + ":sha-candidate"
                        ),
                        "digest": f"sha256:{(2 if environment == 'prod' else 1):064x}",
                        "ref": (
                            repository
                            + "-"
                            + ("prod" if environment == "prod" else "nonprod")
                            + "@"
                            + f"sha256:{(2 if environment == 'prod' else 1):064x}"
                        ),
                        "attestations": {
                            "spdxSbom": (
                                "oci://"
                                + repository
                                + "-"
                                + ("prod" if environment == "prod" else "nonprod")
                                + "@"
                                + f"sha256:{(2 if environment == 'prod' else 1):064x}"
                                + "#spdxSbom"
                            ),
                            "slsaProvenance": (
                                "oci://"
                                + repository
                                + "-"
                                + ("prod" if environment == "prod" else "nonprod")
                                + "@"
                                + f"sha256:{(2 if environment == 'prod' else 1):064x}"
                                + "#slsaProvenance"
                            ),
                        },
                    },
                },
                "configurationPackages": configuration_packages[environment],
            }
            for index, environment in enumerate(finalizer.ENVIRONMENTS, start=1)
        },
        "applicationPackages": application_packages,
        "publicWeb": distribution_descriptors["publicWeb"],
        "androidOfficialRelease": distribution_descriptors[
            "androidOfficialRelease"
        ],
        "opsPortal": ops_portal_package,
        "contractGraphDigest": _sha256_prefixed(contract_graph),
        "requiredEvidence": {
            "environmentArtifacts": {
                environment: ["content-service"]
                for environment in finalizer.ENVIRONMENTS
            },
            "configurationPackages": {
                environment: ["content-service"]
                for environment in finalizer.ENVIRONMENTS
            },
            "applicationPackages": list(finalizer.APPLICATION_PACKAGES),
            "opsPortal": True,
            "contractGraphDigest": True,
            "providerEvidence": True,
            "testEvidence": list(finalizer.TEST_LAYERS),
            "environmentReceipts": list(finalizer.ENVIRONMENTS),
            "rolloutReceipt": True,
            "rollbackReceipt": True,
        },
        "testEvidence": {
            "path": tests.relative_to(root).as_posix(),
            "digest": _sha256_prefixed(tests),
            "status": "passed",
            "layers": {
                layer: {"status": "passed", "artifactDigest": image_digest}
                for layer in finalizer.TEST_LAYERS
            },
            "evidence": test_evidence["evidence"],
        },
        "providerEvidence": {
            "path": provider.relative_to(root).as_posix(),
            "digest": _sha256_prefixed(provider),
            "status": "passed",
            "evidenceCount": provider_evidence_count,
        },
        "environmentReceipts": {},
        "rolloutReceipt": None,
        "rollbackReceipt": None,
        "blockers": ["environment-qualification-evidence-pending"],
        "missingEvidence": [
            *(f"environmentReceipts.{environment}" for environment in finalizer.ENVIRONMENTS),
            "rollbackReceipt.ready",
            "rolloutReceipt",
            "rollbackReceipt.outcome",
        ],
    })
    source = manifest["source"]
    raw = root / "evidence/raw/release-proof.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    _write_json(raw, {"status": "passed"})
    evidence = {
        "files": {
            "releaseProof": {
                "path": raw.relative_to(root).as_posix(),
                "digest": _sha256_prefixed(raw),
            }
        }
    }
    evidence_digest = "sha256:" + hashlib.sha256(
        json.dumps(evidence, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    environment_receipts: dict[str, dict[str, object]] = {}
    for environment in finalizer.PRE_PROD_ENVIRONMENTS:
        payload = {
            "schema": finalizer.ENVIRONMENT_RECEIPT_SCHEMA,
            "environment": environment,
            "status": "passed",
            "releaseCompositionId": manifest["releaseCompositionId"],
            "sourceGitSha": source["gitSha"],
            "sourceTreeDigest": source["treeDigest"],
            "evidenceDigest": evidence_digest,
            "evidence": evidence,
            "verifiedAt": "2026-07-28T00:05:00Z",
        }
        receipt_path = root / f"evidence/receipts/environment/{environment}.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(receipt_path, payload)
        environment_receipts[environment] = {
            **payload,
            "path": receipt_path.relative_to(root).as_posix(),
            "digest": _sha256_prefixed(receipt_path),
        }
    rollback_payload = {
        "schema": finalizer.ROLLBACK_RECEIPT_SCHEMA,
        "environment": "prod",
        "status": "ready",
        "releaseCompositionId": manifest["releaseCompositionId"],
        "sourceGitSha": source["gitSha"],
        "sourceTreeDigest": source["treeDigest"],
        "evidenceDigest": evidence_digest,
        "evidence": evidence,
        "verifiedAt": "2026-07-28T00:05:00Z",
    }
    rollback_path = root / "evidence/receipts/rollback/ready.json"
    rollback_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(rollback_path, rollback_payload)
    manifest["environmentReceipts"] = environment_receipts
    manifest["rollbackReceipt"] = {
        **rollback_payload,
        "path": rollback_path.relative_to(root).as_posix(),
        "digest": _sha256_prefixed(rollback_path),
    }
    manifest["status"] = "main-admitted"
    manifest["blockers"] = ["prod-release-evidence-pending"]
    manifest["missingEvidence"] = [
        "environmentReceipts.prod",
        "rolloutReceipt",
        "rollbackReceipt.outcome",
    ]
    manifest = finalizer.seal_manifest(manifest)
    finalizer.validate_manifest_files(root, manifest)
    path = root / "manifest.json"
    _write_json(path, manifest)
    return path


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256_prefixed(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(root: Path) -> str:
    return web_official_content_digest(root)


if __name__ == "__main__":
    unittest.main()

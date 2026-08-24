# spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-002
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.lib.official_distribution_release import (
    OfficialDistributionReleaseError,
    deploy_official_distribution,
    inspect_official_distribution,
    prevalidate_android_distribution_candidate,
)
from quwoquan_ops.cli.lib.app_identity import resolve_build_product
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.tests.support.app_artifact_manifest_test_support import (
    app_artifact_manifest,
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
                "distribution digest mismatch",
            ):
                deploy_official_distribution(
                    kind="app-release",
                    package_manifest_path=android_manifest,
                    release_manifest_path=release_manifest,
                    distribution_root=root / "origin",
                )


def _web_package(root: Path) -> Path:
    public = root / "public"
    public.mkdir(parents=True)
    (public / "index.html").write_text(
        '<html lang="zh-CN"><head><meta charset="utf-8"></head></html>',
        encoding="utf-8",
    )
    (public / "main.dart.js").write_text("main();", encoding="utf-8")
    (public / "manifest.json").write_text(
        json.dumps({"display": "standalone", "start_url": "/", "scope": "/"}),
        encoding="utf-8",
    )
    (public / "flutter_service_worker.js").write_text("worker();", encoding="utf-8")
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


def _android_package(root: Path, *, build: str) -> Path:
    root.mkdir(parents=True)
    apk = root / f"quwoquan-{build}.apk"
    apk.write_bytes(f"signed-apk-{build}".encode("utf-8"))
    manifest = {
        "schema": "client-app.android.official-release",
        "sourceGitSha": "b" * 40,
        "sourceTreeDigest": "sha1:" + ("c" * 40),
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
        "artifactManifest": app_artifact_manifest(
            build_product_id="android-prod-apk",
            source_git_sha="b" * 40,
            source_tree_digest="sha1:" + ("c" * 40),
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
) -> Path:
    root.mkdir(parents=True)
    # ReleaseEvidence 只登记通用包；对外分发的 web/android 描述文件是另一份
    # 产物，两者通过产品的内容摘要绑定，而不是同一个文件。
    distribution_content_digests = {
        "web-shared": "sha256:"
        + str(json.loads(web_manifest.read_text())["contentSHA256"]),
        "android-prod-apk": "sha256:"
        + str(json.loads(android_manifest.read_text())["apkSHA256"]),
    }
    application_packages: dict[str, dict[str, str]] = {}
    for build_product_id in finalizer.APPLICATION_PACKAGES:
        destination = (
            root / "packages/applications" / build_product_id / "manifest.json"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        product = resolve_build_product(build_product_id)
        package_digest = distribution_content_digests.get(
            build_product_id, "sha256:" + ("d" * 64)
        )
        destination.write_text(
            json.dumps(
                {
                    "schema": finalizer.APPLICATION_PACKAGE_SCHEMA,
                    "buildProductId": product.build_product_id,
                    "buildProfile": product.build_profile,
                    "platform": product.platform,
                    "sourceGitSha": "b" * 40,
                    "sourceTreeDigest": "sha1:" + ("c" * 40),
                    "packageDigest": package_digest,
                    "artifactManifest": app_artifact_manifest(
                        build_product_id=build_product_id,
                        source_git_sha="b" * 40,
                        source_tree_digest="sha1:" + ("c" * 40),
                        artifact_digest=package_digest,
                    ),
                }
            ),
            encoding="utf-8",
        )
        application_packages[build_product_id] = {
            "path": destination.relative_to(root).as_posix(),
            "digest": _sha256_prefixed(destination),
            "packageDigest": package_digest,
            "sourceRef": APP_EVIDENCE_REF,
        }

    # opsPortal 不是 App build product，它在 ReleaseEvidence 里是独立顶层证据。
    ops_portal_manifest = root / "packages/opsPortal/manifest.json"
    ops_portal_manifest.parent.mkdir(parents=True, exist_ok=True)
    ops_portal_manifest.write_text(
        json.dumps(
            {
                "schema": "qwq.ops_portal_package",
                "sourceGitSha": "b" * 40,
                "sourceTreeDigest": "sha1:" + ("c" * 40),
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
        "candidateId": None,
        "status": "candidate-ready",
        "generatedAt": "2026-07-28T00:00:00Z",
        "source": {
            "gitSha": "b" * 40,
            "treeDigest": "sha1:" + ("c" * 40),
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
            "candidateId": manifest["candidateId"],
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
        "candidateId": manifest["candidateId"],
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
    manifest["status"] = "deployable"
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
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.read_bytes())
    return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()

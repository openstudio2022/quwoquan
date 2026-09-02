"""release bound environment identity 本地契约的共享 fixture。

由 test_release_bound_environment_identity__local_contract_test.py
（Python 1000 行硬顶治理）下沉：release 证据常量、文档 digest/checksum
helper 与构造完整环境证据树的 Fixture。常量、helper 与 Fixture 逐字搬移。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from quwoquan_ops.ci import generate_release_bound_environment_identity as renderer
from quwoquan_ops.cli.lib.app_identity import (
    build_profile_for_environment,
    resolve_build_product,
    supported_build_products,
)
from quwoquan_ops.tests.support.app_artifact_manifest_test_support import (
    app_artifact_manifest,
)
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    APPLICATION_PACKAGES,
    DISTRIBUTION_EVIDENCE_PATHS,
    ENVIRONMENTS,
    RELEASE_CLOSURE_PATHS,
    canonical_candidate_digest,
    canonical_environment_artifact_digest,
    canonical_manifest_digest,
    canonical_release_train_digest,
)

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
GIT_SHA = "c" * 40
TREE_DIGEST = "sha1:" + "d" * 40
BASELINE_ID = "app-stability-baseline--20260728T210000Z"
RELEASE_ID = "20260728--travel-golden-release--hangzhou-west-lake--pilot-002"
RELEASE_DIGEST = "sha256:" + "e" * 64
SOURCE_REVISION = "sha256:" + "3" * 64
SOURCE_DIGEST = "sha256:" + "4" * 64
ENTITY_CATALOG_DIGEST = "sha256:" + "5" * 64
ISOLATION_DIGEST = "sha256:" + "6" * 64
SUBJECT_HASH = "sha256:" + "7" * 64


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _document_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _checksum(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["verificationChecksum"] = _document_digest(result)
    return result


def _research_activation_fields(environment: str) -> dict[str, Any]:
    verification_ref = (
        f"env/{environment}/runs/data-release/{RELEASE_ID}/verify-001/"
        "research-isolation-verification.json"
    )
    activation = {
        "schema": "quwoquan_data.environment_activation_envelope",
        "environment": environment,
        "releaseId": RELEASE_ID,
        "manifestDigest": RELEASE_DIGEST,
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "readinessPhase": "research",
        "importRunId": "import-001",
        "verifyRunId": "verify-001",
        "importReportRef": (
            f"env/{environment}/runs/data-release/{RELEASE_ID}/import-001/import.json"
        ),
        "importReportDigest": DIGEST_B,
        "researchIsolationPolicy": {
            "policyRef": f"quwoquan_ops/environments/{environment}/runtime.yaml",
            "policyDigest": ISOLATION_DIGEST,
            "verificationRef": verification_ref,
            "verificationDigest": DIGEST_A,
            "subjectHash": SUBJECT_HASH,
        },
    }
    return {
        "releaseClass": "research",
        "productLifecycleState": "research",
        "sourceRevision": SOURCE_REVISION,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
        "readinessPhase": "research",
        "activationEnvelope": activation,
        "activationEnvelopeDigest": _document_digest(activation),
        "internalSubjectHash": SUBJECT_HASH,
        "researchIsolationVerificationRef": verification_ref,
        "researchIsolationVerificationDigest": DIGEST_A,
    }


class Fixture:
    def __init__(self, root: Path, *, environment: str = "alpha") -> None:
        self.root = root
        self.environment = environment
        self.target = renderer.ENVIRONMENT_TARGETS[environment]
        self.paths: dict[str, Path] = {}
        self.app_paths: list[Path] = []
        self._build()

    def _build(self) -> None:
        application_packages: dict[str, dict[str, str]] = {}
        application_source_ref = f"oci://ghcr.io/owner/app@{DIGEST_B}"
        profile = build_profile_for_environment(self.environment)
        required_products = {
            product.build_product_id
            for product in supported_build_products()
            if product.build_profile in {profile, "shared"}
        }
        for build_product_id in APPLICATION_PACKAGES:
            package_digest = (
                "sha256:"
                + hashlib.sha256(build_product_id.encode()).hexdigest()
            )
            descriptor_digest = DIGEST_A
            if build_product_id in required_products:
                product = resolve_build_product(build_product_id)
                payload = {
                    "schema": "release-application-package",
                    "buildProductId": build_product_id,
                    "buildProfile": product.build_profile,
                    "platform": product.platform,
                    "sourceGitSha": GIT_SHA,
                    "sourceTreeDigest": TREE_DIGEST,
                    "packageDigest": package_digest,
                    "artifactManifest": app_artifact_manifest(
                        build_product_id=build_product_id,
                        source_git_sha=GIT_SHA,
                        source_tree_digest=TREE_DIGEST,
                        artifact_digest=package_digest,
                    ),
                }
                app_path = _write(
                    self.root / f"app-{build_product_id}.json",
                    payload,
                )
                self.app_paths.append(app_path)
                descriptor_digest = _sha(app_path)
            application_packages[build_product_id] = {
                "path": f"packages/applications/{build_product_id}/receipt.json",
                "digest": descriptor_digest,
                "packageDigest": package_digest,
                "sourceRef": application_source_ref,
            }
        distribution_descriptors: dict[str, dict[str, str]] = {}
        distribution_schemas = {
            "publicWeb": "client-app.web.official-release",
            "androidOfficialRelease": "client-app.android.official-release",
        }
        for evidence_key, relative in DISTRIBUTION_EVIDENCE_PATHS.items():
            distribution_path = _write(
                self.root / relative,
                {
                    "schema": distribution_schemas[evidence_key],
                    "sourceGitSha": GIT_SHA,
                    "sourceTreeDigest": TREE_DIGEST,
                },
            )
            distribution_descriptors[evidence_key] = {
                "path": relative,
                "digest": _sha(distribution_path),
            }
        manifest: dict[str, Any] = {
            "schema": "release-evidence-manifest",
            "releaseTrainId": None,
            "candidateId": None,
            "status": "candidate-ready",
            "generatedAt": "2026-07-28T21:00:00Z",
            "source": {
                "gitSha": GIT_SHA,
                "treeDigest": TREE_DIGEST,
                "repository": "owner/quwoquan",
                "workflowRunId": "100",
                "sourceArchiveDigest": DIGEST_A,
            },
            "artifactDigest": None,
            "environmentArtifacts": {
                environment: {
                    "environment": environment,
                    "environmentArtifactDigest": None,
                    "images": {
                        "content-service": {
                            "repository": (
                                "ghcr.io/owner/content-service-"
                                + ("prod" if environment == "prod" else "nonprod")
                            ),
                            "transportRef": (
                                "ghcr.io/owner/content-service-"
                                + ("prod" if environment == "prod" else "nonprod")
                                + ":candidate-100"
                            ),
                            "digest": f"sha256:{(2 if environment == 'prod' else 1):064x}",
                            "ref": (
                                "ghcr.io/owner/content-service-"
                                + ("prod" if environment == "prod" else "nonprod")
                                + "@"
                                + f"sha256:{(2 if environment == 'prod' else 1):064x}"
                            ),
                            "attestations": {
                                "spdxSbom": (
                                    "oci://ghcr.io/owner/content-service-"
                                    + ("prod" if environment == "prod" else "nonprod")
                                    + "@"
                                    + f"sha256:{(2 if environment == 'prod' else 1):064x}"
                                    + "#spdxSbom"
                                ),
                                "slsaProvenance": (
                                    "oci://ghcr.io/owner/content-service-"
                                    + ("prod" if environment == "prod" else "nonprod")
                                    + "@"
                                    + f"sha256:{(2 if environment == 'prod' else 1):064x}"
                                    + "#slsaProvenance"
                                ),
                            },
                        }
                    },
                    "configurationPackages": {
                        "content-service": {
                            "path": (
                                f"packages/environments/{environment}/"
                                "services/content-service/config/config.yaml"
                            ),
                            "digest": DIGEST_A,
                        }
                    },
                }
                for index, environment in enumerate(ENVIRONMENTS, start=1)
            },
            "applicationPackages": application_packages,
            "publicWeb": distribution_descriptors["publicWeb"],
            "androidOfficialRelease": distribution_descriptors[
                "androidOfficialRelease"
            ],
            "opsPortal": {
                "path": "evidence/ops-portal/provenance.json",
                "digest": DIGEST_A,
                "packageDigest": DIGEST_B,
                "sourceRef": "oci://ghcr.io/owner/ops-portal@" + DIGEST_B,
            },
            "contractGraphDigest": DIGEST_A,
            "requiredEvidence": {
                "environmentArtifacts": {
                    environment: ["content-service"] for environment in ENVIRONMENTS
                },
                "configurationPackages": {
                    environment: ["content-service"] for environment in ENVIRONMENTS
                },
                "applicationPackages": list(APPLICATION_PACKAGES),
                "opsPortal": True,
                "contractGraphDigest": True,
                "providerEvidence": True,
                "testEvidence": [
                    "local_contract",
                    "api_integration",
                    "user_acceptance",
                ],
                "environmentReceipts": list(ENVIRONMENTS),
                "rolloutReceipt": True,
                "rollbackReceipt": True,
            },
            "providerEvidence": {
                "path": "evidence/provider/readiness.json",
                "digest": DIGEST_A,
                "status": "passed",
                "evidenceCount": 1,
            },
            "testEvidence": {
                "path": "evidence/tests/three-layer.json",
                "digest": DIGEST_A,
                "status": "passed",
                "evidence": {
                    "files": {
                        label: {"path": relative, "digest": DIGEST_A}
                        for label, relative in RELEASE_CLOSURE_PATHS.items()
                    }
                },
                "layers": {
                    layer: {"status": "passed", "artifactDigest": DIGEST_A}
                    for layer in (
                        "local_contract",
                        "api_integration",
                        "user_acceptance",
                    )
                },
            },
            "environmentReceipts": {},
            "rolloutReceipt": None,
            "rollbackReceipt": None,
            "blockers": ["environment-qualification-evidence-pending"],
            "missingEvidence": [
                *(f"environmentReceipts.{environment}" for environment in ENVIRONMENTS),
                "rollbackReceipt.ready",
                "rolloutReceipt",
                "rollbackReceipt.outcome",
            ],
        }
        for environment in ENVIRONMENTS:
            manifest["environmentArtifacts"][environment][
                "environmentArtifactDigest"
            ] = canonical_environment_artifact_digest(manifest, environment)
        manifest["releaseTrainId"] = canonical_release_train_digest(manifest)
        manifest["candidateId"] = canonical_candidate_digest(manifest)
        if self.environment == "prod":

            def receipt(kind: str, environment: str, status: str) -> dict[str, Any]:
                evidence = {
                    "candidateId": manifest["candidateId"],
                    "environment": environment,
                    "kind": kind,
                }
                evidence_digest = renderer._canonical_digest(evidence)
                return {
                    "schema": f"release-{kind}-receipt",
                    "environment": environment,
                    "status": status,
                    "candidateId": manifest["candidateId"],
                    "sourceGitSha": GIT_SHA,
                    "sourceTreeDigest": TREE_DIGEST,
                    "evidenceDigest": evidence_digest,
                    "evidence": evidence,
                    "verifiedAt": "2026-07-28T21:10:00Z",
                    "path": f"evidence/{kind}/{environment}.json",
                    "digest": DIGEST_A,
                }

            manifest["status"] = "deployable"
            manifest["environmentReceipts"] = {
                environment: receipt("environment", environment, "passed")
                for environment in ("alpha", "beta", "gamma")
            }
            manifest["rollbackReceipt"] = receipt("rollback", "prod", "ready")
            manifest["blockers"] = ["prod-release-evidence-pending"]
            manifest["missingEvidence"] = [
                "environmentReceipts.prod",
                "rolloutReceipt",
                "rollbackReceipt.outcome",
            ]
        manifest["artifactDigest"] = canonical_manifest_digest(manifest)
        self.paths["manifest"] = _write(self.root / "manifest.json", manifest)

        self.paths["acceptance"] = _write(
            self.root / "environment-acceptance.json",
            {
                "schema": "quwoquan_ops.environment_acceptance_fact.v1",
                "acceptanceProfile": "environment_promotion",
                "factId": DIGEST_A,
                "environment": self.environment,
                "target": self.target,
                "releaseId": RELEASE_ID,
                "releaseDigest": RELEASE_DIGEST,
                "requiredRawResults": [
                    {
                        "ref": f"env/{self.environment}/raw/readiness-case.json",
                        "digest": DIGEST_B,
                        "slotId": DIGEST_A,
                        "status": "passed",
                    }
                ],
            },
        )
        self.paths["readiness"] = _write(
            self.root / "release-readiness.json",
            _checksum(
                {
                    "schema": "quwoquan_data.environment_release_readiness",
                    "environment": self.environment,
                    "releaseId": RELEASE_ID,
                    "releaseKind": "content",
                    "sourceOwner": "qwq_data",
                    **_research_activation_fields(self.environment),
                    "manifestDigest": RELEASE_DIGEST,
                    "mediaManifestDigest": DIGEST_A,
                    "importRunId": "import-001",
                    "verifyRunId": "verify-001",
                    "counts": {
                        "entities": 1,
                        "posts": 3,
                        "creators": 4,
                        "avatarAssets": 4,
                        "imageAssets": 1,
                        "tags": 2,
                        "mediaAssets": 3,
                        "discoveryPosts": 3,
                        "premiumPlayableVideos": 1,
                    },
                    "entityRefs": ["entity:west-lake"],
                    "postIds": ["post-article", "post-image", "post-video"],
                    "creatorIds": [
                        "creator-1",
                        "creator-2",
                        "creator-3",
                        "creator-4",
                    ],
                    "tagRefs": ["Topic/旅行", "Topic/旅行/景区"],
                    "mediaAssetIds": ["media-avatar", "media-image", "media-video"],
                    "feedQueries": [
                        {
                            "name": name,
                            "path": "/content/feed",
                            "query": query,
                            "status": 200,
                            "releaseBound": True,
                            "matchedPostIds": [post_id],
                        }
                        for name, query, post_id in (
                            ("discovery_work", "identity=work&limit=3", "post-article"),
                            (
                                "typed_article",
                                "identity=work&type=article&limit=1",
                                "post-article",
                            ),
                            (
                                "typed_image",
                                "identity=work&type=image&limit=1",
                                "post-image",
                            ),
                            (
                                "typed_video",
                                "identity=work&type=video&limit=1",
                                "post-video",
                            ),
                            (
                                "homepage_recommend",
                                "homepageRef=entity:west-lake&limit=3",
                                "post-image",
                            ),
                            (
                                "premium_stream",
                                "sort=recommend&channelId=premium_stream&limit=1",
                                "post-video",
                            ),
                        )
                    ],
                    "contentImportReportRef": (
                        f"env/{self.environment}/runs/data-release/{RELEASE_ID}/"
                        "import-001/import.json"
                    ),
                    "creatorAttributionRef": (
                        f"env/{self.environment}/runs/data-release/{RELEASE_ID}/"
                        "verify-001/creator-attribution.json"
                    ),
                    "tagAttributionRef": (
                        f"env/{self.environment}/runs/data-release/{RELEASE_ID}/"
                        "verify-001/tag-attribution.json"
                    ),
                    "homepageApiVerificationRef": (
                        f"env/{self.environment}/runs/data-release/{RELEASE_ID}/"
                        "verify-001/homepage-api-verification.json"
                    ),
                    "postApiVerificationRef": (
                        f"env/{self.environment}/runs/data-release/{RELEASE_ID}/"
                        "verify-001/post-api-verification.json"
                    ),
                    "mediaManifestRef": (
                        f"data/releases/{RELEASE_ID}/payload/media_manifest.json"
                    ),
                    "verifiedAt": "2026-07-28T21:15:00Z",
                    "passed": True,
                }
            ),
        )
        import_refs = {
            "homepageVerificationCasesRef": "homepage-verification-cases.json",
            "tagImportReportRef": "tag-import.json",
            "creatorImportReportRef": "creator-import.json",
            "contentImportReportRef": "import.json",
            "homepageImportReportRef": "homepage-import.json",
        }
        self.paths["import"] = _write(
            self.root / "import.json",
            _checksum(
                {
                    "schema": "quwoquan_data.environment_release_result",
                    "environment": self.environment,
                    "releaseId": RELEASE_ID,
                    "runId": "import-001",
                    "status": "completed",
                    **{
                        field: (
                            f"env/{self.environment}/runs/data-release/{RELEASE_ID}/"
                            f"import-001/{name}"
                        )
                        for field, name in import_refs.items()
                    },
                }
            ),
        )
        self.paths["replay"] = _write(
            self.root / "replay.json",
            _checksum(
                {
                    "schema": "quwoquan_data.environment_release_result",
                    "environment": self.environment,
                    "releaseId": RELEASE_ID,
                    "runId": "replay-001",
                    "status": "completed",
                    **{
                        field: (
                            f"env/{self.environment}/runs/data-release/{RELEASE_ID}/"
                            f"replay-001/{name}"
                        )
                        for field, name in import_refs.items()
                    },
                }
            ),
        )
        transport = {
            "required": self.environment != "prod",
            "reverseExpectedPorts": "17000" if self.environment != "prod" else "",
            "reverseActualPorts": "17000" if self.environment != "prod" else "",
            "reverseReceiptDigest": DIGEST_A if self.environment != "prod" else "",
            "consumerLeaseId": DIGEST_B if self.environment != "prod" else "",
        }
        launch = {
            "schema": "app-effective-launch-manifest",
            "environment": self.environment,
            "buildProfile": build_profile_for_environment(self.environment),
            "target": self.target,
            "entrypoint": "lib/main_prod.dart",
            "launchProvenance": "release_package",
            "runtimeConfigSupplyMode": "external_runtime_package",
            "launchPolicy": (
                "prod_release" if self.environment == "prod" else "test_live"
            ),
            "runtimeConfigPackageDigest": DIGEST_A,
            "runtimeConfigTrustEnvelopeDigest": DIGEST_B,
            "requiresLocalTransport": self.environment != "prod",
            "transport": transport,
        }
        self.launch_digest = renderer._canonical_digest(launch)
        self.paths["launch"] = _write(self.root / "launch.json", launch)
        artifacts = {
            build_product_id: application_packages[build_product_id]["packageDigest"]
            for build_product_id in sorted(required_products)
        }
        profiles = sorted(renderer.EXPECTED_DEVICE_PROFILES[self.environment])
        runtime_evidence: dict[str, Any] = {}
        readback_evidence: dict[str, Any] = {}
        attempts: list[str] = []
        devices: list[str] = []
        for index, profile in enumerate(profiles, start=1):
            platform = profile.split("-", 1)[0]
            device = f"device-{self.environment}-{index:02d}"
            devices.append(device)
            device_kind = (
                "simulator"
                if profile.endswith("-simulator")
                else ("physical" if profile == "ios-physical" else "true_device")
            )
            run_count = 20 if self.environment == "prod" else 1
            samples: list[dict[str, Any]] = []
            for run_index in range(1, run_count + 1):
                attempt = f"attempt-{self.environment}-{index:02d}-{run_index:02d}"
                attempts.append(attempt)
                sample: dict[str, Any] = {
                    "passed": True,
                    "attemptId": attempt,
                    "deviceId": device,
                    "runtimeEnv": self.environment,
                    "runtimeTarget": self.target,
                    "platform": platform,
                    "deviceKind": device_kind,
                    "sourceReport": f"evidence/startup/{attempt}.json",
                    "launchProvenance": "release_package",
                    "runtimeConfigSupplyMode": "external_runtime_package",
                    "hotRestart": False,
                    "runtimeConfigurationState": "complete",
                    "missingDefineKeys": [],
                    "failureCode": "",
                    "rendererFirstFrameMs": 900,
                    "safeTerminalMs": 1200,
                    "reportedSafeTerminalMs": 1200,
                    "nativeReceivedSafeTerminalMs": 1250,
                    "watchdogOutcome": "safe_terminal",
                    "canonicalTerminal": "routerShell",
                    "startupSequenceMotionCurrent": True,
                    "telemetryAcknowledged": True,
                    "effectiveLaunchManifestDigest": self.launch_digest,
                }
                if platform == "android":
                    sample.update(
                        {
                            "launcherIntentUsed": True,
                            "launcherStarted": True,
                            "launcherResolution": {"matchesExpectedGate": True},
                            "gateMainOrderObserved": True,
                            "taskSnapshot": {
                                "singleMainTask": True,
                                "mainActivityInstances": 1,
                            },
                            "launchVisual": {
                                "contractVerified": True,
                                "sourceDigest": "f" * 64,
                                "profile": "default",
                            },
                        }
                    )
                else:
                    sample.update(
                        {
                            "sceneLaunchUsed": True,
                            "sceneStarted": True,
                            "sceneLauncher": (
                                "xcrun_simctl"
                                if device_kind == "simulator"
                                else "xcrun_devicectl"
                            ),
                        }
                    )
                samples.append(sample)
            runtime_evidence[f"{self.target}/{profile}"] = {
                "status": "passed",
                "evidence": {
                    "schema": "qwq.startup-runtime-evidence",
                    "baselineId": BASELINE_ID,
                    "releaseId": RELEASE_ID,
                    "releaseDigest": RELEASE_DIGEST,
                    "runtimeEnv": self.environment,
                    "runtimeTarget": self.target,
                    "platform": platform,
                    "runs": run_count,
                    "passed": True,
                    "specRefs": list(renderer.SPEC_REFS),
                    "samples": samples,
                },
            }
            readback_evidence[f"{self.target}/{profile}"] = {
                "status": "passed",
                "evidence": {
                    "schema": "qwq.app-core-readback-evidence",
                    "status": "passed",
                    "baselineId": BASELINE_ID,
                    "releaseId": RELEASE_ID,
                    "releaseDigest": RELEASE_DIGEST,
                    "environment": self.environment,
                    "target": self.target,
                    "platform": platform,
                    "deviceKind": device_kind,
                    "deviceId": device,
                    "effectiveLaunchManifestDigest": self.launch_digest,
                    "specRefs": list(renderer.SPEC_REFS),
                    "required": 1,
                    "executed": 1,
                    "skipped": 0,
                    "failed": 0,
                    "caseResults": [
                        {
                            "caseId": f"core-readback-{profile}",
                            "status": "passed",
                            "deviceId": device,
                            "testExecution": {
                                "executed": 1,
                                "passed": 1,
                                "failed": 0,
                            },
                            "evidence": {
                                "commandPath": f"commands/{profile}.json",
                                "patrolLogPath": f"logs/{profile}.log",
                                "remoteApi": {"status": "passed"},
                            },
                        }
                    ],
                    "sourceReport": f"evidence/readback/{profile}.json",
                    "failureReason": "",
                },
            }
        case_result = {
            "schema": "qwq.startup-environment-case-result",
            "status": "passed",
            "required": len(profiles),
            "executed": len(profiles),
            "skipped": 0,
            "failed": 0,
            "specRefs": list(renderer.SPEC_REFS),
            "baselineId": BASELINE_ID,
            "releaseId": RELEASE_ID,
            "releaseDigest": RELEASE_DIGEST,
            "sourceGitSha": GIT_SHA,
            "sourceTreeDigest": TREE_DIGEST,
            "applicationArtifacts": artifacts,
            "packages": {
                self.environment: {
                    "status": "component_ready",
                    "runtimeTarget": self.target,
                    "effectiveLaunchManifestDigest": self.launch_digest,
                }
            },
            "runtimeEvidence": runtime_evidence,
            "readbackEvidence": readback_evidence,
        }
        self.paths["case"] = _write(self.root / "case-result.json", case_result)
        self.paths["telemetry"] = _write(
            self.root / "telemetry.json",
            {
                "schema": "qwq.startup-observability-readback",
                "status": "passed",
                "baselineId": BASELINE_ID,
                "releaseId": RELEASE_ID,
                "releaseDigest": RELEASE_DIGEST,
                "environment": self.environment,
                "target": self.target,
                "effectiveLaunchManifestDigest": self.launch_digest,
                "telemetryBackend": "elasticsearch",
                "backendReceiptRef": f"receipt:hosted:{DIGEST_A}",
                "attemptIds": attempts,
                "deviceIds": devices,
                "required": len(attempts),
                "executed": len(attempts),
                "skipped": 0,
                "failed": 0,
                "specRefs": list(renderer.SPEC_REFS),
            },
        )
        rollback = {
            "schema": "quwoquan_data.environment_release_lifecycle_exit",
            "environment": self.environment,
            "sourceOwner": "qwq_data",
            "exitRunId": "exit-001",
            "originalReleaseId": RELEASE_ID,
            "originalManifestDigest": RELEASE_DIGEST,
            "originalImportRunId": "import-001",
            "originalVerifyRunId": "verify-001",
            "originalImportResultRef": f"env/{self.environment}/runs/data-release/{RELEASE_ID}/import-001/result.json",
            "originalVerifyResultRef": f"env/{self.environment}/runs/data-release/{RELEASE_ID}/verify-001/result.json",
            "rollbackToReleaseId": "previous-release",
            "rollbackToManifestDigest": DIGEST_B,
            "rollbackRunId": "rollback-001",
            "rollbackVerifyRunId": "rollback-verify-001",
            "rollbackResultRef": f"env/{self.environment}/runs/data-release/previous-release/rollback-001/result.json",
            "rollbackVerifyResultRef": f"env/{self.environment}/runs/data-release/previous-release/rollback-verify-001/result.json",
            "replayImportRunId": "replay-001",
            "replayVerifyRunId": "replay-verify-001",
            "replayManifestDigest": RELEASE_DIGEST,
            "replayImportResultRef": f"env/{self.environment}/runs/data-release/{RELEASE_ID}/replay-001/result.json",
            "replayVerifyResultRef": f"env/{self.environment}/runs/data-release/{RELEASE_ID}/replay-verify-001/result.json",
            "recordedAt": "2026-07-28T21:20:00Z",
            "passed": True,
        }
        self.paths["rollback"] = _write(
            self.root / "rollback.json", _checksum(rollback)
        )
        self.paths["media"] = _write(
            self.root / "research-media-readback.json",
            {"schema": "quwoquan_ops.research_content_isolation"},
        )

    def argv(self, output: Path) -> list[str]:
        values = [
            "--baseline-id",
            BASELINE_ID,
            "--environment",
            self.environment,
            "--target",
            self.target,
            "--release-evidence-manifest",
            str(self.paths["manifest"]),
            "--data-output-root",
            str(self.root),
            "--release-readiness",
            str(self.paths["readiness"]),
            "--import-receipt",
            str(self.paths["import"]),
            "--replay-receipt",
            str(self.paths["replay"]),
            "--effective-launch-manifest",
            str(self.paths["launch"]),
            "--environment-acceptance-fact",
            str(self.paths["acceptance"]),
        ]
        for path in self.app_paths:
            values.extend(["--app-artifact-receipt", str(path)])
        values.extend(
            [
                "--startup-device-case-result",
                str(self.paths["case"]),
                "--telemetry-readback",
                str(self.paths["telemetry"]),
                "--rollback-receipt",
                str(self.paths["rollback"]),
                "--release-media-readback",
                str(self.paths["media"]),
                "--output",
                str(output),
            ]
        )
        return values

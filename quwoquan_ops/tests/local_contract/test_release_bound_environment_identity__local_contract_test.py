# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from quwoquan_ops.ci import render_release_bound_environment_identity as renderer
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    APPLICATION_PACKAGES,
    ENVIRONMENTS,
    canonical_candidate_digest,
    canonical_manifest_digest,
)


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
GIT_SHA = "c" * 40
TREE_DIGEST = "sha1:" + "d" * 40
BASELINE_ID = "app-stability-baseline--20260728T210000Z"
RELEASE_ID = "20260728--travel-golden-release--hangzhou-west-lake--pilot-002"
RELEASE_DIGEST = "sha256:" + "e" * 64


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _checksum(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    encoded = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    result["verificationChecksum"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    return result


class Fixture:
    def __init__(self, root: Path, *, environment: str = "alpha") -> None:
        self.root = root
        self.environment = environment
        self.target = renderer.ENVIRONMENT_TARGETS[environment]
        self.paths: dict[str, Path] = {}
        self.app_paths: list[Path] = []
        self._build()

    def _build(self) -> None:
        package_digests = {
            "android": "sha256:" + "1" * 64,
            "ios": "sha256:" + "2" * 64,
        }
        for surface in ("android", "ios"):
            payload: dict[str, Any]
            if self.environment == "prod" and surface == "android":
                payload = {
                    "schema": "qwq.android.official-release",
                    "sourceGitSha": GIT_SHA,
                    "sourceTreeDigest": TREE_DIGEST,
                    "packagedAPK": "quwoquan.apk",
                    "apkSHA256": package_digests[surface].removeprefix("sha256:"),
                }
            else:
                payload = {
                    "schema": "release-application-package",
                    "environment": self.environment,
                    "surface": surface,
                    "sourceGitSha": GIT_SHA,
                    "sourceTreeDigest": TREE_DIGEST,
                    "packageDigest": package_digests[surface],
                }
            self.app_paths.append(
                _write(
                    self.root / f"app-{surface}.json",
                    payload,
                )
            )

        application_packages: dict[str, dict[str, dict[str, str]]] = {}
        application_source_ref = f"oci://ghcr.io/owner/app@{DIGEST_B}"
        for environment in ENVIRONMENTS:
            application_packages[environment] = {}
            for surface in APPLICATION_PACKAGES[environment]:
                package_digest = "sha256:" + hashlib.sha256(
                    f"{environment}/{surface}".encode("utf-8")
                ).hexdigest()
                descriptor_digest = DIGEST_A
                if environment == self.environment and surface in package_digests:
                    index = 0 if surface == "android" else 1
                    package_digest = package_digests[surface]
                    descriptor_digest = _sha(self.app_paths[index])
                application_packages[environment][surface] = {
                    "path": f"packages/applications/{environment}/{surface}/receipt.json",
                    "digest": descriptor_digest,
                    "packageDigest": package_digest,
                    "sourceRef": application_source_ref,
                }
        manifest: dict[str, Any] = {
            "schema": "release-evidence-manifest",
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
            "images": {
                "content-service": {
                    "repository": "ghcr.io/owner/content-service",
                    "transportRef": "ghcr.io/owner/content-service:candidate-100",
                    "digest": DIGEST_A,
                    "ref": f"ghcr.io/owner/content-service@{DIGEST_A}",
                    "attestations": {
                        "spdxSbom": f"oci://ghcr.io/owner/content-service@{DIGEST_A}#spdxSbom",
                        "slsaProvenance": f"oci://ghcr.io/owner/content-service@{DIGEST_A}#slsaProvenance",
                    },
                }
            },
            "configurationPackages": {
                environment: {
                    "content-service": {
                        "path": (
                            f"packages/environments/{environment}/"
                            "services/content-service/config/config.yaml"
                        ),
                        "digest": DIGEST_A,
                    }
                }
                for environment in ENVIRONMENTS
            },
            "applicationPackages": application_packages,
            "contractGraphDigest": DIGEST_A,
            "requiredEvidence": {
                "images": ["content-service"],
                "configurationPackages": {
                    environment: ["content-service"] for environment in ENVIRONMENTS
                },
                "applicationPackages": {
                    environment: list(APPLICATION_PACKAGES[environment])
                    for environment in ENVIRONMENTS
                },
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
                "layers": {
                    layer: {"status": "passed", "artifactDigest": DIGEST_A}
                    for layer in ("local_contract", "api_integration", "user_acceptance")
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

        self.paths["readiness"] = _write(
            self.root / "release-readiness.json",
            _checksum(
                {
                    "schema": "quwoquan_data.environment_release_readiness",
                    "environment": self.environment,
                    "releaseId": RELEASE_ID,
                    "releaseKind": "content",
                    "sourceOwner": "qwq_data",
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
                            ("typed_article", "identity=work&type=article&limit=1", "post-article"),
                            ("typed_image", "identity=work&type=image&limit=1", "post-image"),
                            ("typed_video", "identity=work&type=video&limit=1", "post-video"),
                            ("homepage_recommend", "homepageRef=entity:west-lake&limit=3", "post-image"),
                            ("premium_stream", "sort=recommend&channelId=premium_stream&limit=1", "post-video"),
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
            "target": self.target,
            "entrypoint": "lib/main_prod.dart",
            "launchMode": "matrix_uat",
            "dartDefinesDigest": DIGEST_A,
            "runtimeConfigDigest": DIGEST_B,
            "recoveryBaseUrl": "https://api.example.com",
            "publicWebBaseUrl": "https://example.com",
            "appDownloadBaseUrl": "https://cdn.example.com/download",
            "requiresLocalTransport": self.environment != "prod",
            "transport": transport,
        }
        self.launch_digest = renderer._canonical_digest(launch)
        self.paths["launch"] = _write(self.root / "launch.json", launch)
        artifacts = dict(package_digests)
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
                attempt = (
                    f"attempt-{self.environment}-{index:02d}-{run_index:02d}"
                )
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
                    "launchMode": "matrix_uat",
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
                "telemetryBackend": "aliyun-sls",
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
        self.paths["video"] = _write(
            self.root / "release-video-delivery.json",
            {"schema": "quwoquan_ops.release_video_delivery_evidence"},
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
                "--release-video-delivery",
                str(self.paths["video"]),
                "--output",
                str(output),
            ]
        )
        return values


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
                "assetId": "media-video",
                "postId": "post-video",
                "publicSliceKey": "media/video/s/asset/video/v1/source.mp4",
                "publicUrl": "https://cdn.example.net/media/video/source.mp4",
                "contentType": "video/mp4",
                "bytes": 4,
                "sha256": DIGEST_A,
                "durationMs": 1200,
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
            self.assertEqual(set(payload["identity"]["appArtifacts"]), {"android", "ios"})
            self.assertEqual(
                payload["identity"]["objectIds"]["entityRefs"],
                ["entity:west-lake"],
            )
            self.assertEqual(
                payload["identity"]["mediaProbe"]["premiumPlayableVideos"], 1
            )
            self.assertEqual(
                payload["identity"]["mediaProbe"]["avatarAssets"], 4
            )
            self.assertEqual(
                payload["identity"]["mediaProbe"]["imageAssets"], 1
            )
            self.assertEqual(payload["identity"]["videoDelivery"]["rangeStatus"], 206)
            self.manifest_files.assert_called_once()
            self.data_evidence.assert_called_once()
            self.app_readback.assert_called_once()
            self.assertTrue(all("sha256" in value for key, value in payload["evidence"].items() if key != "appArtifactReceipts"))

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
            "video",
            "app",
        ]
        for label in missing:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                fixture = Fixture(Path(directory))
                target = fixture.app_paths[0] if label == "app" else fixture.paths[label]
                target.unlink()
                output = Path(directory) / "identity.json"
                self.assertEqual(renderer.main(fixture.argv(output)), 2)
                self.assertFalse(output.exists())

    def test_canonical_bundle_and_data_recomputation_are_fail_closed(self) -> None:
        for validator in ("manifest", "data"):
            with self.subTest(validator=validator), tempfile.TemporaryDirectory() as directory:
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

    def test_identity_drift_skipped_unknown_synthetic_and_attempt_reuse_block(self) -> None:
        mutations = ("identity", "skipped", "unknown", "synthetic", "reuse")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
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
                    wrappers[1]["evidence"]["samples"][0]["attemptId"] = wrappers[0]["evidence"]["samples"][0]["attemptId"]
                    _write(fixture.paths["case"], payload)
                output = Path(directory) / "identity.json"
                _write(output, {"schema": renderer.SCHEMA, "status": "passed"})
                self.assertEqual(renderer.main(fixture.argv(output)), 2)
                self.assertFalse(output.exists())

    def test_manifest_readiness_and_prod_twenty_run_contract_are_fail_closed(self) -> None:
        for mutation in ("manifest-shape", "object-closure", "prod-run-count"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
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
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
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

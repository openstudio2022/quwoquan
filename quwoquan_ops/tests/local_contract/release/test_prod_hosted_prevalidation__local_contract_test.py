from __future__ import annotations

import contextlib
import fcntl
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.app_identity import resolve_build_product
from quwoquan_ops.ci import release_evidence_reader as historical_reader
from quwoquan_ops.cli.prod import inspect_prod_plane_runtime as inspect_runtime
from quwoquan_ops.cli.prod import load_prod_plane_images as image_loader
from quwoquan_ops.cli.prod import prevalidate_prod_hosted as prevalidate
from quwoquan_ops.tests.support.app_artifact_manifest_test_support import (
    app_artifact_manifest,
)


def _seal_snapshot(payload: dict[str, object]) -> dict[str, object]:
    payload["releaseTrainId"] = historical_reader.canonical_release_train_digest(payload)
    for environment in historical_reader.ENVIRONMENTS:
        payload["environmentArtifacts"][environment]["environmentArtifactDigest"] = (
            historical_reader.canonical_environment_artifact_digest(payload, environment)
        )
    try:
        payload["candidateId"] = historical_reader.canonical_candidate_digest(payload)
    except ValueError:
        payload["candidateId"] = None
    payload["artifactDigest"] = historical_reader.canonical_manifest_digest(payload)
    return payload


APP_EVIDENCE_REF = (
    "oci://ghcr.io/owner/repo/app-candidate@sha256:" + ("e" * 64)
)


class ProdHostedPrevalidationContractTest(unittest.TestCase):
    """不可提升的 prod-hosted 第一方容器预验证合同。

    spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-008
    spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md#gwt-003
    """

    def _artifact(self, root: Path, *, image_version: str = "1.20260726.42") -> Path:
        _, projections = prevalidate.load_projection()
        services = sorted(
            {
                service
                for projection in projections.values()
                for service in (
                    projection.startup_services + projection.image_only_services
                )
            }
        )
        configuration_packages: dict[str, dict[str, dict[str, str]]] = {
            environment: {} for environment in historical_reader.ENVIRONMENTS
        }
        for environment in historical_reader.ENVIRONMENTS:
            for service in services:
                relative = (
                    f"packages/environments/{environment}/services/"
                    f"{service}/config/config.yaml"
                )
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    f"config:\n  environment: {environment}\n", encoding="utf-8"
                )
                configuration_packages[environment][service] = {
                    "path": relative,
                    "digest": "sha256:"
                    + hashlib.sha256(path.read_bytes()).hexdigest(),
                }
        # DEC-005：alpha/beta/gamma 共享 nonprod 镜像，prod 使用独立信任域。
        # 环境差异只存在于 configurationPackages。
        environment_images: dict[str, dict[str, dict[str, object]]] = {}
        for environment in historical_reader.ENVIRONMENTS:
            trust_domain = "prod" if environment == "prod" else "nonprod"
            digest = (
                "sha256:"
                + hashlib.sha256(f"image-{trust_domain}".encode("utf-8")).hexdigest()
            )
            environment_images[environment] = {
                service: {
                    "repository": f"ghcr.io/owner/repo/{service}-{trust_domain}",
                    "transportRef": (
                        f"ghcr.io/owner/repo/{service}-{trust_domain}:{image_version}"
                    ),
                    "digest": digest,
                    "ref": f"ghcr.io/owner/repo/{service}-{trust_domain}@{digest}",
                    "attestations": {
                        "spdxSbom": (
                            f"oci://ghcr.io/owner/repo/{service}-{trust_domain}"
                            f"@{digest}#spdxSbom"
                        ),
                        "slsaProvenance": (
                            f"oci://ghcr.io/owner/repo/{service}-{trust_domain}"
                            f"@{digest}#slsaProvenance"
                        ),
                    },
                }
                for service in services
            }
        # App 包按 canonical build product 编址，四环境共用同一批产品；
        # opsPortal 不是 build product，它是 ReleaseEvidence 的独立顶层证据。
        application_packages: dict[str, dict[str, str]] = {}
        for build_product_id in historical_reader.APPLICATION_PACKAGES:
            relative = f"packages/applications/{build_product_id}/manifest.json"
            package_path = root / relative
            package_path.parent.mkdir(parents=True, exist_ok=True)
            product = resolve_build_product(build_product_id)
            package_payload = {
                "schema": historical_reader.APPLICATION_PACKAGE_SCHEMA,
                "buildProductId": product.build_product_id,
                "buildProfile": product.build_profile,
                "platform": product.platform,
                "sourceGitSha": "a" * 40,
                "sourceTreeDigest": "sha1:" + ("b" * 40),
                "packageDigest": "sha256:" + ("d" * 64),
                "artifactManifest": app_artifact_manifest(
                    build_product_id=build_product_id,
                    source_git_sha="a" * 40,
                    source_tree_digest="sha1:" + ("b" * 40),
                    artifact_digest="sha256:" + ("d" * 64),
                ),
            }
            package_path.write_text(json.dumps(package_payload), encoding="utf-8")
            application_packages[build_product_id] = {
                "path": relative,
                "digest": "sha256:"
                + hashlib.sha256(package_path.read_bytes()).hexdigest(),
                "packageDigest": "sha256:" + ("d" * 64),
                "sourceRef": APP_EVIDENCE_REF,
            }

        ops_portal_relative = "packages/opsPortal/manifest.json"
        ops_portal_path = root / ops_portal_relative
        ops_portal_path.parent.mkdir(parents=True, exist_ok=True)
        ops_portal_path.write_text(
            json.dumps(
                {
                    "schema": historical_reader.OPS_PORTAL_SCHEMA,
                    "sourceGitSha": "a" * 40,
                    "sourceTreeDigest": "sha1:" + ("b" * 40),
                    "packageDigest": "sha256:" + ("d" * 64),
                }
            ),
            encoding="utf-8",
        )
        ops_portal_package = {
            "path": ops_portal_relative,
            "digest": "sha256:"
            + hashlib.sha256(ops_portal_path.read_bytes()).hexdigest(),
            "packageDigest": "sha256:" + ("d" * 64),
            "sourceRef": APP_EVIDENCE_REF,
        }
        evidence_root = root / "evidence"
        evidence_root.mkdir(parents=True, exist_ok=True)
        contract_graph = evidence_root / "contractGraph.json"
        contract_graph.write_text("{}", encoding="utf-8")
        provider_readiness = {
            environment: {
                "fixture.capability": {
                    "required": True,
                    "capability_ready": True,
                }
            }
            for environment in historical_reader.ENVIRONMENTS
        }
        provider_evidence_count = (
            historical_reader.expected_required_cell_count_from_readiness(provider_readiness)
        )
        provider_raw_files: dict[str, str] = {}
        for index in range(provider_evidence_count):
            provider_raw = root / f"evidence/raw/provider/{index:03d}.json"
            provider_raw.parent.mkdir(parents=True, exist_ok=True)
            provider_raw.write_text(
                json.dumps({"status": "passed", "cell": index}),
                encoding="utf-8",
            )
            provider_raw_files[provider_raw.relative_to(root).as_posix()] = (
                "sha256:" + hashlib.sha256(provider_raw.read_bytes()).hexdigest()
            )
        provider_source_digest = "sha256:" + ("f" * 64)
        provider = evidence_root / "providerEvidence.json"
        provider.write_text(
            json.dumps(
                {
                    "schema": "provider-conformance-readiness",
                    "status": "passed",
                    "evidenceCount": provider_evidence_count,
                    "readiness": provider_readiness,
                    "sourceEvidence": {
                        "ref": (
                            "oci://ghcr.io/owner/repo/provider-evidence@"
                            + provider_source_digest
                        ),
                        "digest": provider_source_digest,
                        "files": provider_raw_files,
                    },
                }
            ),
            encoding="utf-8",
        )
        test_evidence_files: dict[str, dict[str, str]] = {}
        for label, relative in historical_reader.RELEASE_CLOSURE_PATHS.items():
            source = root / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(
                json.dumps({"label": label, "status": "passed"}),
                encoding="utf-8",
            )
            test_evidence_files[label] = {
                "path": relative,
                "digest": "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        evidence_layer_digest = "sha256:" + ("c" * 64)
        test_evidence = {
            "schema": "qwq.three-layer-case-results",
            "status": "passed",
            "layers": {
                layer: {"status": "passed", "artifactDigest": evidence_layer_digest}
                for layer in historical_reader.TEST_LAYERS
            },
            "evidence": {"files": test_evidence_files},
        }
        test = evidence_root / "testEvidence.json"
        test.write_text(json.dumps(test_evidence), encoding="utf-8")
        distribution_descriptors: dict[str, dict[str, str]] = {}
        distribution_schemas = {
            "publicWeb": "client-app.web.official-release",
            "androidOfficialRelease": "client-app.android.official-release",
        }
        for evidence_key, relative in historical_reader.DISTRIBUTION_EVIDENCE_PATHS.items():
            distribution_path = root / relative
            distribution_path.parent.mkdir(parents=True, exist_ok=True)
            distribution_path.write_text(
                json.dumps(
                    {
                        "schema": distribution_schemas[evidence_key],
                        "sourceGitSha": "a" * 40,
                        "sourceTreeDigest": "sha1:" + ("b" * 40),
                    }
                ),
                encoding="utf-8",
            )
            distribution_descriptors[evidence_key] = {
                "path": relative,
                "digest": "sha256:"
                + hashlib.sha256(distribution_path.read_bytes()).hexdigest(),
            }
        payload = _seal_snapshot({
            "schema": historical_reader.SCHEMA,
            "releaseTrainId": None,
            "candidateId": None,
            "status": "candidate-ready",
            "generatedAt": "2026-07-28T00:00:00Z",
            "source": {
                "gitSha": "a" * 40,
                "treeDigest": "sha1:" + ("b" * 40),
                "repository": "owner/repo",
                "workflowRunId": "42",
                "sourceArchiveDigest": None,
            },
            "artifactDigest": None,
            "environmentArtifacts": {
                environment: {
                    "environment": environment,
                    "environmentArtifactDigest": None,
                    "images": environment_images[environment],
                    "configurationPackages": configuration_packages[environment],
                }
                for environment in historical_reader.ENVIRONMENTS
            },
            "applicationPackages": application_packages,
            "publicWeb": distribution_descriptors["publicWeb"],
            "androidOfficialRelease": distribution_descriptors[
                "androidOfficialRelease"
            ],
            "opsPortal": ops_portal_package,
            "contractGraphDigest": "sha256:"
            + hashlib.sha256(contract_graph.read_bytes()).hexdigest(),
            "requiredEvidence": {
                "environmentArtifacts": {
                    environment: services for environment in historical_reader.ENVIRONMENTS
                },
                "configurationPackages": {
                    environment: services for environment in historical_reader.ENVIRONMENTS
                },
                "applicationPackages": list(historical_reader.APPLICATION_PACKAGES),
                "opsPortal": True,
                "contractGraphDigest": True,
                "providerEvidence": True,
                "testEvidence": list(historical_reader.TEST_LAYERS),
                "environmentReceipts": list(historical_reader.ENVIRONMENTS),
                "rolloutReceipt": True,
                "rollbackReceipt": True,
            },
            "testEvidence": {
                "path": test.relative_to(root).as_posix(),
                "digest": "sha256:" + hashlib.sha256(test.read_bytes()).hexdigest(),
                "status": "passed",
                "layers": {
                    layer: {"status": "passed", "artifactDigest": evidence_layer_digest}
                    for layer in historical_reader.TEST_LAYERS
                },
                "evidence": test_evidence["evidence"],
            },
            "providerEvidence": {
                "path": provider.relative_to(root).as_posix(),
                "digest": "sha256:"
                + hashlib.sha256(provider.read_bytes()).hexdigest(),
                "status": "passed",
                "evidenceCount": provider_evidence_count,
            },
            "environmentReceipts": {},
            "rolloutReceipt": None,
            "rollbackReceipt": None,
            "blockers": ["environment-qualification-evidence-pending"],
            "missingEvidence": [
                *(f"environmentReceipts.{environment}" for environment in historical_reader.ENVIRONMENTS),
                "rollbackReceipt.ready",
                "rolloutReceipt",
                "rollbackReceipt.outcome",
            ],
        })
        source = payload["source"]
        raw = root / "evidence/raw/release-proof.json"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
        evidence = {
            "files": {
                "releaseProof": {
                    "path": raw.relative_to(root).as_posix(),
                    "digest": "sha256:" + hashlib.sha256(raw.read_bytes()).hexdigest(),
                }
            }
        }
        evidence_digest = "sha256:" + hashlib.sha256(
            json.dumps(evidence, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        receipts: dict[str, dict[str, object]] = {}
        for environment in historical_reader.PRE_PROD_ENVIRONMENTS:
            receipt_payload = {
                "schema": historical_reader.ENVIRONMENT_RECEIPT_SCHEMA,
                "environment": environment,
                "status": "passed",
                "candidateId": payload["candidateId"],
                "sourceGitSha": source["gitSha"],
                "sourceTreeDigest": source["treeDigest"],
                "evidenceDigest": evidence_digest,
                "evidence": evidence,
                "verifiedAt": "2026-07-28T00:05:00Z",
            }
            receipt_path = root / f"evidence/receipts/environment/{environment}.json"
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(receipt_payload), encoding="utf-8")
            receipts[environment] = {
                **receipt_payload,
                "path": receipt_path.relative_to(root).as_posix(),
                "digest": "sha256:"
                + hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            }
        rollback_payload = {
            "schema": historical_reader.ROLLBACK_RECEIPT_SCHEMA,
            "environment": "prod",
            "status": "ready",
            "candidateId": payload["candidateId"],
            "sourceGitSha": source["gitSha"],
            "sourceTreeDigest": source["treeDigest"],
            "evidenceDigest": evidence_digest,
            "evidence": evidence,
            "verifiedAt": "2026-07-28T00:05:00Z",
        }
        rollback_path = root / "evidence/receipts/rollback/ready.json"
        rollback_path.parent.mkdir(parents=True, exist_ok=True)
        rollback_path.write_text(json.dumps(rollback_payload), encoding="utf-8")
        payload["environmentReceipts"] = receipts
        payload["rollbackReceipt"] = {
            **rollback_payload,
            "path": rollback_path.relative_to(root).as_posix(),
            "digest": "sha256:"
            + hashlib.sha256(rollback_path.read_bytes()).hexdigest(),
        }
        payload["status"] = "deployable"
        payload["blockers"] = ["prod-release-evidence-pending"]
        payload["missingEvidence"] = [
            "environmentReceipts.prod",
            "rolloutReceipt",
            "rollbackReceipt.outcome",
        ]
        payload = _seal_snapshot(payload)
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        return manifest

    def test_parser_exposes_non_promotable_prevalidation_surface(self) -> None:
        args = stackctl.build_parser().parse_args(
            [
                "deploy",
                "--target",
                "prod-hosted",
                "--mode",
                "prevalidate",
                "--ssh-host",
                "192.0.2.10",
                "--data-mode",
                "isolated",
                "--prevalidate-scope",
                "first-party",
            ]
        )
        self.assertEqual(args.mode, "prevalidate")
        self.assertEqual(args.ssh_host, "192.0.2.10")
        self.assertEqual(args.data_mode, "isolated")

    def test_projection_is_pinned_empty_and_excludes_external_providers(self) -> None:
        spec, projections = prevalidate.load_projection()
        self.assertFalse(spec["promotable"])
        self.assertEqual(
            projections["service"].image_only_services,
            ("integration-service",),
        )
        self.assertNotIn("integration-service", projections["service"].startup_services)
        self.assertEqual(
            set(projections["edge"].startup_services),
            {"realtime-gateway", "rtc-service"},
        )
        self.assertTrue(spec["isolatedData"]["empty"])
        self.assertFalse(spec["isolatedData"]["seedAllowed"])
        self.assertEqual(
            spec["readinessPolicy"]["providerReadinessStatus"], "GATE_BLOCK"
        )
        self.assertEqual(
            spec["readinessPolicy"]["providerBoundServices"],
            ["product-ops-service"],
        )
        for ref in spec["isolatedData"]["images"].values():
            self.assertRegex(ref, r"@sha256:[0-9a-f]{64}$")
        self.assertTrue({"livekit", "coturn"}.issubset(spec["excluded"]["workloads"]))

    def test_host_thresholds_and_ports_fail_closed(self) -> None:
        spec, projections = prevalidate.load_projection()
        snapshot = {
            "architecture": "x86_64",
            "cpuCores": 1,
            "memoryBytes": 1024**3,
            "containerFreeBytes": 1024**3,
            "containerEffectiveFreeBytes": 2 * 1024**3,
            "listeningPorts": [39000],
            "podmanRootless": True,
            "linger": True,
            "userSystemd": "running",
        }
        issues = prevalidate.evaluate_host_snapshots(
            {"service": snapshot, "edge": snapshot},
            spec,
            projections,
            data_mode="isolated",
        )
        self.assertTrue(any("CPU cores insufficient" in item for item in issues))
        self.assertTrue(any("memory bytes insufficient" in item for item in issues))
        self.assertTrue(any("container free bytes insufficient" in item for item in issues))
        self.assertTrue(
            any("effective container free bytes insufficient" in item for item in issues)
        )
        self.assertTrue(any("target ports already occupied" in item for item in issues))

    def test_constrained_host_policy_never_removes_volumes(self) -> None:
        spec, _ = prevalidate.load_projection()
        self.assertEqual(spec["capacityStrategy"], "constrained-per-replica-host")
        reclaim = spec["staleRuntimeReclaimPolicy"]
        self.assertTrue(reclaim["enabled"])
        self.assertFalse(reclaim["removeVolumes"])
        self.assertIn("quwoquan-data-recovery-mongodb", reclaim["preservedContainers"])
        external = reclaim["externalBuildContainers"]
        self.assertTrue(external["enabled"])
        self.assertEqual(external["allowedStates"], ["storage"])
        self.assertTrue(external["requirePidZero"])
        self.assertGreaterEqual(external["minimumAgeSeconds"], 86400)
        self.assertRegex("golang-working-container", external["namePattern"])
        self.assertRegex("327ccb6c43b2-working-container-1", external["namePattern"])
        self.assertNotRegex("quwoquan-data-recovery-mongodb", external["namePattern"])
        self.assertGreaterEqual(
            spec["minimumHostResources"]["containerEffectiveFreeBytes"],
            spec["minimumHostResources"]["postReclaimContainerFreeBytes"],
        )

    def test_remote_reclaim_script_supports_host_python_3_6(self) -> None:
        spec, projections = prevalidate.load_projection()
        script = prevalidate._remote_reclaim_script(
            projection=projections["service"],
            policy=spec["staleRuntimeReclaimPolicy"],
        )
        compile(script, "<prod-hosted-reclaim>", "exec")
        self.assertIn("universal_newlines=True", script)
        self.assertNotIn("text=True", script)
        self.assertNotIn("capture_output=True", script)
        self.assertIn("while remaining:", script)
        self.assertIn('["podman", "rm", name]', script)
        self.assertNotIn('["podman", "rm", *sorted(set(selected))]', script)

    def test_remote_reclaim_removes_only_scoped_dependents_in_safe_order(self) -> None:
        spec, projections = prevalidate.load_projection()
        script = prevalidate._remote_reclaim_script(
            projection=projections["service"],
            policy=spec["staleRuntimeReclaimPolicy"],
        )
        self.assertIn("while remaining:", script)
        self.assertIn('["podman", "rm", name]', script)
        self.assertIn("dependency-order retries", script)
        self.assertIn('"ps", "--external", "-a", "--format", "json"', script)
        self.assertIn('state not in external_states', script)
        self.assertIn('pid != 0', script)
        self.assertIn('now - created < minimum_age_seconds', script)
        self.assertIn('external_name_pattern.fullmatch', script)
        self.assertIn('["podman", "rm", container_id]', script)
        self.assertNotIn('["podman", "rm", *sorted(set(selected))]', script)
        self.assertNotIn('["podman", "rm", "-f"', script)
        self.assertNotIn("--volumes", script)
        self.assertNotIn('["podman", "image", "prune"', script)
        self.assertIn('"imagePrune": "skipped-candidate-preservation"', script)

    def test_oci_release_artifact_is_materialized_by_digest_only(self) -> None:
        digest = "d" * 64
        expected = Path("/tmp/release-artifacts")
        completed = subprocess.CompletedProcess(
            ["fetch"], 0, stdout='{"manifest":"ok"}\n', stderr=""
        )
        with (
            mock.patch.object(
                stackctl, "deployment_target_path", return_value=expected
            ),
            mock.patch.object(stackctl, "run", return_value=completed) as invoked,
        ):
            manifest = stackctl._materialize_frozen_diagnostic_snapshot(
                "oci://ghcr.io/owner/repo/release-artifact@sha256:" + digest
            )
        self.assertEqual(manifest, expected / "manifest.json")
        self.assertIn("--ref", invoked.call_args.args[0])
        with self.assertRaisesRegex(RuntimeError, "GHCR digest ref"):
            stackctl._materialize_frozen_diagnostic_snapshot(
                "oci://ghcr.io/owner/repo/release-artifact:latest"
            )

    def test_external_data_mode_requires_real_listeners(self) -> None:
        spec, projections = prevalidate.load_projection()
        snapshot = {
            "architecture": "x86_64",
            "cpuCores": 4,
            "memoryBytes": 16 * 1024**3,
            "containerFreeBytes": 40 * 1024**3,
            "listeningPorts": [],
            "podmanRootless": True,
            "linger": True,
            "userSystemd": "running",
        }
        issues = prevalidate.evaluate_host_snapshots(
            {"service": snapshot, "edge": snapshot},
            spec,
            projections,
            data_mode="external",
        )
        self.assertIn("external data ports are not listening: [19400, 19410, 19420]", issues)

    def test_image_id_normalization_rejects_invalid_readback(self) -> None:
        for raw in ("a" * 64, "sha256:" + "a" * 64):
            self.assertEqual(image_loader.normalize_image_id(raw), "sha256:" + "a" * 64)
        for raw in (None, "", "a" * 12, "A" * 64, "sha512:" + "a" * 64, "a" * 64 + "\n", "latest"):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "IMAGE_ID_INVALID"):
                image_loader.normalize_image_id(raw)
        with mock.patch.object(image_loader.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "invalid\n", "")):
            self.assertIsNone(image_loader._local_image_digest("image"))
            with self.assertRaisesRegex(ValueError, "IMAGE_ID_INVALID"):
                image_loader._remote_image_digest("image", "account", "host", Path("key"))
        with mock.patch.object(image_loader, "_stream_image") as stream:
            with self.assertRaisesRegex(SystemExit, "local image content digest unavailable"):
                image_loader._deliver_images(["service"], image_refs={"service": "image"},
                                             local_digests={"service": None}, account="account", host="host", key_file=Path("key"))
            stream.assert_not_called()

    def _runtime_fixture(self):
        spec, projections = prevalidate.load_projection()
        projection = projections["service"]
        names = [*projection.startup_services, "gamma-proxy", *spec["isolatedData"]["services"]]
        containers = {
            name: {"composeService": name, "imageId": "sha256:" + "a" * 64,
                   "running": True, "status": "running", "health": "healthy", "exitCode": 0}
            for name in names
        }
        for name in ("mongo-init", "object-storage-init"):
            containers[name].update(running=False, status="exited", health="not-configured")
        report = {"containers": list(containers.values()), "unit": {"enabled": True, "active": True}}
        delivery = {"contentDigestVerified": True, "remoteImageContentDigests": {
            name: "sha256:" + "a" * 64
            for name in (*projection.startup_services, *projection.image_only_services)
        }}
        return spec, projection, containers, report, delivery

    def test_required_runtime_health_gate_rejects_missing_probe_and_proxy(self) -> None:
        spec, projection, containers, report, delivery = self._runtime_fixture()
        check = lambda: prevalidate._runtime_blockers(report, projection, spec, delivery, data_mode="isolated")
        self.assertEqual(check(), [])
        for name in (*projection.startup_services, "gamma-proxy", "mongodb"):
            with self.subTest(service=name):
                containers[name]["health"] = "not-configured"
                self.assertEqual(check()[0]["code"], "HEALTHCHECK_NOT_CONFIGURED")
                containers[name]["health"] = "healthy"
        for service in projection.startup_services:
            containers[service]["imageId"] = "a" * 64
        self.assertEqual(check(), [])
        containers[projection.startup_services[0]]["imageId"] = "invalid"
        self.assertEqual(check()[0]["code"], "IMAGE_ID_INVALID")
        containers[projection.startup_services[0]]["imageId"] = "sha256:" + "b" * 64
        self.assertEqual(check()[0]["code"], "IMAGE_DIGEST_MISMATCH")
        containers[projection.startup_services[0]]["imageId"] = "a" * 64
        for name in ("gamma-proxy", "api-edge"):
            report["containers"] = [item for service, item in containers.items() if service != name]
            self.assertEqual(check()[0]["code"], "CONTAINER_UNSCHEDULED")
            self.assertEqual(check()[0]["service"], name)

    def test_initializer_must_exit_zero_and_oom_is_distinct(self) -> None:
        spec, projection, containers, report, delivery = self._runtime_fixture()
        check = lambda: prevalidate._runtime_blockers(report, projection, spec, delivery, data_mode="isolated")
        for name in ("mongo-init", "object-storage-init"):
            with self.subTest(service=name):
                containers[name].update(running=True, status="running")
                self.assertEqual(check()[0]["code"], "INITIALIZATION_PENDING")
                containers[name].update(running=False, status="exited", exitCode=1)
                self.assertEqual(check()[0]["code"], "INITIALIZATION_FAILED")
                containers[name]["exitCode"] = None
                self.assertEqual(check()[0]["code"], "INITIALIZATION_FAILED")
                containers[name].update(exitCode=0, oomKilled=True)
                self.assertEqual(check()[0]["code"], "CONTAINER_OOM")
                containers[name]["oomKilled"] = False
        self.assertEqual(check(), [])

    def test_phase_timeouts_are_bounded_and_typed(self) -> None:
        timeout = subprocess.TimeoutExpired(["test-command"], 1)
        for phase in ("transfer", "activation", "readiness"):
            with self.subTest(phase=phase), mock.patch.object(prevalidate.subprocess, "run", side_effect=timeout) as run:
                with self.assertRaises(prevalidate.PrevalidationError) as raised:
                    prevalidate._run(["test-command"], phase=phase, timeout=1)
                self.assertEqual(raised.exception.blocker["code"], phase.upper() + "_TIMEOUT")
                self.assertEqual(run.call_args.kwargs["timeout"], 1)
        with mock.patch.object(prevalidate.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "FAIL: IMAGE_TRANSFER_TIMEOUT: image")):
            with self.assertRaises(prevalidate.PrevalidationError) as raised:
                prevalidate._run(["loader"], phase="transfer")
            self.assertEqual(raised.exception.blocker["code"], "TRANSFER_TIMEOUT")
            self.assertEqual(raised.exception.blocker["causeCode"], "IMAGE_TRANSFER_TIMEOUT")
        with mock.patch.object(inspect_runtime.subprocess, "run", side_effect=timeout):
            with self.assertRaisesRegex(SystemExit, "RUNTIME_INSPECTION_TIMEOUT"):
                inspect_runtime._inspect_remote(["ssh"], "")
        with mock.patch.object(image_loader.subprocess, "run", side_effect=timeout):
            with self.assertRaisesRegex(SystemExit, "IMAGE_COMMAND_TIMEOUT"):
                image_loader._local_image_digest("image")

    def test_transfer_timeout_and_load_failure_preserve_first_cause(self) -> None:
        for result, code in (
            (subprocess.TimeoutExpired(["ssh"], 1), "IMAGE_TRANSFER_TIMEOUT"),
            (subprocess.CompletedProcess([], 125, "", "load-first-cause"), "IMAGE_LOAD_FAILED.*load-first-cause"),
        ):
            save = mock.Mock()
            save.poll.return_value = None
            save.wait.return_value = 1
            with (
                self.subTest(code=code),
                mock.patch.object(image_loader.subprocess, "Popen", return_value=save),
                mock.patch.object(image_loader.subprocess, "run", side_effect=result if isinstance(result, Exception) else None,
                                  return_value=result) as run,
                mock.patch.object(image_loader, "_remote_image_digest") as readback,
            ):
                with self.assertRaisesRegex(SystemExit, code):
                    image_loader._stream_image("image", "account", "host", Path("key"))
                self.assertGreater(run.call_args.kwargs["timeout"], 0)
                self.assertLessEqual(run.call_args.kwargs["timeout"], image_loader.TRANSFER_TIMEOUT_SECONDS)
                save.stdout.close.assert_called()
                save.kill.assert_called_once()
                save.wait.assert_called_with(timeout=5)
                readback.assert_not_called()

    def _activation_script(self, remote_root: str = "/stack") -> str:
        _, projections = prevalidate.load_projection()
        with (
            mock.patch.object(prevalidate, "_resolve_key", return_value=Path("key")),
            mock.patch.object(prevalidate.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, '{"status":"passed"}', "")) as run,
        ):
            prevalidate._install_unit(host="host", projection=projections["service"], key_dir=Path("keys"),
                                      replica_id="r0", remote_root=remote_root)
        self.assertGreater(run.call_args.kwargs["timeout"], prevalidate.ACTIVATION_TIMEOUT_SECONDS)
        self.assertLessEqual(run.call_args.kwargs["timeout"], prevalidate.ACTIVATION_TIMEOUT_SECONDS + 150)
        return run.call_args.kwargs["input"]

    def _execute_activation_script(self, script, config_root, run):
        output = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(config_root)}),
            mock.patch.object(prevalidate.subprocess, "run", side_effect=run),
            contextlib.redirect_stdout(output),
        ):
            try:
                exec(compile(script, "<prevalidate-activation>", "exec"), {})
            except SystemExit as error:
                self.assertEqual(error.code, 2)
        return json.loads(output.getvalue())

    def test_active_retry_reexecutes_managed_unit_without_compose_down(self) -> None:
        """spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-003.t3"""
        unit = "quwoquan-service-prevalidate-r0.service"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "payload/systemd" / unit
            source.parent.mkdir(parents=True)
            config = root / "config"
            calls = []
            def run(argv, **kwargs):
                self.assertGreater(kwargs["timeout"], 0)
                calls.append(argv)
                if "restart" in argv:
                    override = config / "systemd/user" / (unit + ".d/activate.conf")
                    self.assertIn("\nExecStop=\n", override.read_text())
                    self.assertEqual((config / "systemd/user" / unit).read_bytes(), source.read_bytes())
                return subprocess.CompletedProcess(argv, 0, "", "")
            for candidate in ("same", "same", "new"):
                with self.subTest(candidate=candidate):
                    source.write_text("[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/usr/bin/true\nExecStop=/usr/bin/false\n# " + candidate)
                    script = self._activation_script(str(source.parent.parent))
                    self.assertNotIn("text=True", script)
                    self.assertNotIn("capture_output=True", script)
                    calls.clear()
                    report = self._execute_activation_script(script, config, run)
                    self.assertEqual(report["status"], "passed")
                    self.assertEqual(calls, [
                        ["systemctl", "--user", "daemon-reload"],
                        ["systemctl", "--user", "enable", unit],
                        ["systemctl", "--user", "restart", unit],
                        ["systemctl", "--user", "is-enabled", "--quiet", unit],
                        ["systemctl", "--user", "is-active", "--quiet", unit],
                    ])
                    self.assertNotIn("sub2api", script)
                    self.assertNotIn("down", script)
                    self.assertNotIn("--volumes", script)

    def test_activation_failure_diagnostic_is_bounded_and_preserves_first_cause(self) -> None:
        unit = "quwoquan-service-prevalidate-r0.service"
        for failure, diagnostic, code in (
            (125, "Result=exit-code\nExecMainCode=1\nExecMainStatus=125\nSECRET=do-not-print", "ACTIVATION_FAILED"),
            (1, "Result=timeout\nExecMainStatus=15", "ACTIVATION_TIMEOUT"),
            (125, subprocess.TimeoutExpired(["show"], 15, stderr="secret"), "ACTIVATION_FAILED"),
            (subprocess.TimeoutExpired(["restart"], 330, stderr="secret"), "Result=success\nActiveState=activating", "ACTIVATION_TIMEOUT"),
        ):
            with self.subTest(code=code, diagnostic=diagnostic), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "payload/systemd" / unit
                source.parent.mkdir(parents=True)
                source.write_text("[Service]\nExecStop=/usr/bin/false\n")
                calls = []
                def run(argv, **kwargs):
                    calls.append(argv)
                    self.assertGreater(kwargs["timeout"], 0)
                    if "restart" in argv:
                        self.assertGreater(kwargs["timeout"], prevalidate.ACTIVATION_TIMEOUT_SECONDS)
                        if isinstance(failure, Exception):
                            raise failure
                        return subprocess.CompletedProcess(argv, failure, "", "secret-first-cause")
                    if "show" in argv:
                        self.assertLessEqual(kwargs["timeout"], 15)
                        if isinstance(diagnostic, Exception):
                            raise diagnostic
                        return subprocess.CompletedProcess(argv, 0, diagnostic, "secret")
                    return subprocess.CompletedProcess(argv, 0, "", "")
                report = self._execute_activation_script(self._activation_script(str(source.parent.parent)), root / "config", run)
                self.assertEqual(report["firstBlocker"]["code"], code)
                self.assertEqual(report["firstBlocker"]["step"], "restart")
                self.assertNotIn("secret", json.dumps(report).lower())
                self.assertFalse(any("is-active" in call for call in calls))
                if failure == 125:
                    self.assertEqual(report["firstBlocker"]["exitCode"], 125)
                if isinstance(diagnostic, Exception):
                    self.assertEqual(report["diagnosticBlocker"]["code"], "ACTIVATION_DIAGNOSTIC_TIMEOUT")
                with (
                    mock.patch.object(prevalidate, "_resolve_key", return_value=Path("key")),
                    mock.patch.object(prevalidate.subprocess, "run", return_value=subprocess.CompletedProcess([], 2, json.dumps(report), "secret")),
                    self.assertRaises(prevalidate.PrevalidationError) as raised,
                ):
                    _, projections = prevalidate.load_projection()
                    prevalidate._install_unit(host="host", projection=projections["service"], key_dir=Path("keys"), replica_id="r0", remote_root="/stack")
                self.assertEqual(raised.exception.blocker["code"], code)
                self.assertEqual(raised.exception.blocker["firstReason"], report["firstBlocker"])
                self.assertNotIn("secret", str(raised.exception).lower())

    def test_activation_transport_timeout_and_invalid_readback_fail_closed(self) -> None:
        _, projections = prevalidate.load_projection()
        for result, code in (
            (subprocess.TimeoutExpired(["ssh", "secret"], 450, output="secret", stderr="secret"), "ACTIVATION_TIMEOUT"),
            (subprocess.CompletedProcess([], 0, "secret", "secret"), "ACTIVATION_FAILED"),
        ):
            with (
                self.subTest(code=code),
                mock.patch.object(prevalidate, "_resolve_key", return_value=Path("secret")),
                mock.patch.object(prevalidate.subprocess, "run", side_effect=result if isinstance(result, Exception) else None, return_value=result),
                self.assertRaises(prevalidate.PrevalidationError) as raised,
            ):
                prevalidate._install_unit(host="host", projection=projections["service"], key_dir=Path("keys"), replica_id="r0", remote_root="/stack")
            self.assertEqual(raised.exception.blocker["code"], code)
            self.assertNotIn("secret", json.dumps(raised.exception.blocker))
            if code == "ACTIVATION_TIMEOUT":
                self.assertEqual(raised.exception.blocker["firstReason"]["code"], "ACTIVATION_TRANSPORT_TIMEOUT")

    def test_activation_preparation_failure_stops_before_restart(self) -> None:
        unit = "quwoquan-service-prevalidate-r0.service"
        for failed_step in ("daemon-reload", "enable"):
            with self.subTest(step=failed_step), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "payload/systemd" / unit
                source.parent.mkdir(parents=True)
                source.write_text("[Service]\n")
                calls = []
                def run(argv, **kwargs):
                    calls.append(argv)
                    return subprocess.CompletedProcess(argv, 1 if failed_step in argv else 0, "secret", "secret")
                report = self._execute_activation_script(self._activation_script(str(source.parent.parent)), root / "config", run)
                self.assertEqual(report["firstBlocker"]["step"], failed_step)
                self.assertEqual(report["firstBlocker"]["exitCode"], 1)
                self.assertFalse(any("restart" in call or "show" in call for call in calls))
                self.assertNotIn("secret", json.dumps(report))

    def test_activation_lock_conflict_cannot_install_or_restart(self) -> None:
        unit = "quwoquan-service-prevalidate-r0.service"
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            unit_dir = config / "systemd/user"
            unit_dir.mkdir(parents=True)
            lock_path = unit_dir / (unit + ".activate.lock")
            with lock_path.open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                run = mock.Mock()
                report = self._execute_activation_script(self._activation_script(), config, run)
                self.assertEqual(report["firstBlocker"]["code"], "ACTIVATION_BUSY")
                run.assert_not_called()
                self.assertFalse((unit_dir / unit).exists())

    def test_direct_ssh_calls_require_pinned_host_and_bounded_transport(self) -> None:
        spec, projections = prevalidate.load_projection()
        projection = projections["service"]
        success = subprocess.CompletedProcess([], 0, json.dumps({"account": projection.account, "status": "passed"}), "")
        with (
            mock.patch.object(prevalidate, "_resolve_key", return_value=Path("key")),
            mock.patch.object(prevalidate.subprocess, "run", return_value=success) as run,
        ):
            prevalidate.collect_host_snapshots("host", {"service": projection}, Path("keys"))
            prevalidate._reclaim_stale_runtime(host="host", projection=projection, key_dir=Path("keys"), policy=spec["staleRuntimeReclaimPolicy"])
            prevalidate._install_unit(host="host", projection=projection, key_dir=Path("keys"), replica_id="r0", remote_root="/stack")
        self.assertEqual(len(run.call_args_list), 3)
        for call in run.call_args_list:
            argv = call.args[0]
            self.assertEqual(argv[:3], ["ssh", "-F", "/dev/null"])
            for option in ("BatchMode=yes", "StrictHostKeyChecking=yes", "ConnectTimeout=12", "ServerAliveInterval=10", "ServerAliveCountMax=3"):
                self.assertIn(option, argv)

    def test_direct_ssh_failure_does_not_echo_remote_secrets(self) -> None:
        spec, projections = prevalidate.load_projection()
        projection = projections["service"]
        for invoke in (
            lambda: prevalidate.collect_host_snapshots("host", {"service": projection}, Path("keys")),
            lambda: prevalidate._reclaim_stale_runtime(host="host", projection=projection, key_dir=Path("keys"), policy=spec["staleRuntimeReclaimPolicy"]),
            lambda: prevalidate._install_unit(host="host", projection=projection, key_dir=Path("keys"), replica_id="r0", remote_root="/stack"),
        ):
            with (
                mock.patch.object(prevalidate, "_resolve_key", return_value=Path("key")),
                mock.patch.object(prevalidate.subprocess, "run", return_value=subprocess.CompletedProcess([], 255, "TOKEN=secret", "PASSWORD=secret")),
                self.assertRaises(prevalidate.PrevalidationError) as raised,
            ):
                invoke()
            self.assertNotIn("secret", json.dumps(raised.exception.blocker).lower())

    def test_readiness_deadline_preserves_first_unscheduled_reason(self) -> None:
        spec, projection, containers, report, delivery = self._runtime_fixture()
        report["containers"] = [item for name, item in containers.items() if name != "gamma-proxy"]
        clock = [0.0]
        def advance(seconds):
            clock[0] += seconds
        with (
            mock.patch.object(prevalidate, "READINESS_TIMEOUT_SECONDS", 6),
            mock.patch.object(prevalidate.time, "monotonic", side_effect=lambda: clock[0]),
            mock.patch.object(prevalidate.time, "sleep", side_effect=advance),
            mock.patch.object(prevalidate, "_run", return_value={"stdout": json.dumps(report)}) as run,
        ):
            with self.assertRaises(prevalidate.PrevalidationError) as raised:
                prevalidate._wait_for_readiness(
                    SimpleNamespace(host="", key_dir=Path("key"), data_mode="isolated"), spec,
                    {"service": projection}, {"service": SimpleNamespace(host_id="host", replica_id="replica")},
                    {"service": delivery},
                )
        blocker = raised.exception.blocker
        self.assertEqual(blocker["code"], "READINESS_TIMEOUT")
        self.assertEqual(blocker["firstReason"]["code"], "CONTAINER_UNSCHEDULED")
        self.assertEqual(blocker["firstReason"]["service"], "gamma-proxy")
        self.assertEqual(clock[0], 6)
        self.assertEqual([call.kwargs["timeout"] for call in run.call_args_list], [6, 1])

    def test_runtime_inspection_reads_systemd_and_container_image_identity(self) -> None:
        source = inspect_runtime._remote_python()
        self.assertIn('"systemctl", "--user", "is-enabled"', source)
        self.assertIn('"systemctl", "--user", "is-active"', source)
        self.assertIn('"imageId": item.get("Image")', source)
        self.assertIn('state.get("Health") or state.get("Healthcheck")', source)
        self.assertIn('"oomKilled": state.get("OOMKilled") is True', source)
        compile(source, "<runtime-inspection>", "exec")
        for raw in ("a" * 64, "sha256:" + "a" * 64):
            result = inspect_runtime._normalize_runtime_images({"containers": [{"imageId": raw}]})
            self.assertEqual(result["containers"][0]["imageId"], "sha256:" + "a" * 64)
        for raw in (None, "bad", "sha256:" + "a" * 12):
            with self.assertRaisesRegex(ValueError, "IMAGE_ID_INVALID"):
                inspect_runtime._normalize_runtime_images({"containers": [{"imageId": raw}]})

    def test_manifest_requires_clean_reviewed_main_and_ghcr_digests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._artifact(Path(tmp))
            git_results = [
                subprocess.CompletedProcess(["git"], 0, stdout=("a" * 40) + "\n", stderr=""),
                subprocess.CompletedProcess(["git"], 0, stdout="", stderr=""),
                subprocess.CompletedProcess(["git"], 0, stdout="", stderr=""),
            ]
            with mock.patch.object(stackctl, "run", side_effect=git_results):
                resolved = stackctl._frozen_diagnostic_snapshot(str(manifest))
            self.assertEqual(resolved[3], "1.20260726.42")
            self.assertEqual(resolved[4], resolved[2]["candidateId"])

            dirty_results = [
                subprocess.CompletedProcess(["git"], 0, stdout=("a" * 40) + "\n", stderr=""),
                subprocess.CompletedProcess(["git"], 0, stdout=" M tracked.py\n", stderr=""),
            ]
            with mock.patch.object(stackctl, "run", side_effect=dirty_results):
                with self.assertRaisesRegex(RuntimeError, "uncommitted worktree"):
                    stackctl._frozen_diagnostic_snapshot(str(manifest))

    def test_latest_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._artifact(Path(tmp), image_version="latest")
            with self.assertRaisesRegex(RuntimeError, "must not use latest"):
                stackctl._frozen_diagnostic_snapshot(str(manifest))

    def test_missing_manifest_never_enters_release_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = stackctl.build_parser().parse_args(
                [
                    "deploy",
                    "--target",
                    "prod-hosted",
                    "--mode",
                    "prevalidate",
                    "--ssh-host",
                    "192.0.2.10",
                    "--data-mode",
                    "isolated",
                    "--prevalidate-scope",
                    "first-party",
                    "--report-dir",
                    tmp,
                ]
            )
            planned = {
                "hostPreflight": {"status": "checked"},
                "containerDeployment": {"status": "planned"},
            }
            with (
                mock.patch.object(stackctl, "_validate_prod_prevalidation_public_bases"),
                mock.patch.object(
                    stackctl,
                    "_prod_prevalidation_executor",
                    return_value=(
                        subprocess.CompletedProcess(["prevalidate"], 0, stdout="{}", stderr=""),
                        planned,
                    ),
                ),
                mock.patch.object(stackctl, "_run_hosted_release_ledger") as ledger,
                mock.patch.object(stackctl, "_prod_release_lock") as release_lock,
            ):
                result = stackctl.command_deploy(args)
            self.assertEqual(result["exitCode"], 2)
            self.assertEqual(result["releaseEligibility"], "GATE_BLOCK")
            self.assertEqual(result["providerReadiness"], "GATE_BLOCK")
            ledger.assert_not_called()
            release_lock.assert_not_called()

    def test_prevalidation_rejects_rollout_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            args = stackctl.build_parser().parse_args(
                [
                    "deploy",
                    "--target",
                    "prod-hosted",
                    "--mode",
                    "prevalidate",
                    "--stage",
                    "canary",
                    "--ssh-host",
                    "192.0.2.10",
                    "--data-mode",
                    "isolated",
                    "--prevalidate-scope",
                    "first-party",
                    "--report-dir",
                    tmp,
                ]
            )
            with (
                mock.patch.object(stackctl, "_validate_prod_prevalidation_public_bases"),
                mock.patch.object(
                    stackctl,
                    "_prod_prevalidation_executor",
                    return_value=(
                        subprocess.CompletedProcess(["prevalidate"], 0, stdout="{}", stderr=""),
                        {"containerDeployment": {"status": "planned"}},
                    ),
                ),
            ):
                result = stackctl.command_deploy(args)
            self.assertEqual(result["exitCode"], 2)
            self.assertTrue(
                any("rejects formal rollout" in item for item in result["details"])
            )

    def test_raw_ip_public_base_is_rejected(self) -> None:
        with (
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(
                stackctl,
                "get_target",
                return_value={"publicBases": {"api": "https://192.0.2.10"}},
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "canonical public HTTPS DNS"):
                stackctl._validate_prod_prevalidation_public_bases()


if __name__ == "__main__":
    unittest.main()

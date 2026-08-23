from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.cli.prod import inspect_prod_plane_runtime as inspect_runtime
from quwoquan_ops.cli.prod import prevalidate_prod_hosted as prevalidate
from quwoquan_ops.tests.support.app_artifact_manifest_test_support import (
    app_artifact_manifest,
)


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
            environment: {} for environment in finalizer.ENVIRONMENTS
        }
        for environment in finalizer.ENVIRONMENTS:
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
        for environment in finalizer.ENVIRONMENTS:
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
        application_packages: dict[str, dict[str, dict[str, str]]] = {
            environment: {} for environment in finalizer.ENVIRONMENTS
        }
        for environment in finalizer.ENVIRONMENTS:
            for surface in finalizer.APPLICATION_PACKAGES[environment]:
                relative = (
                    f"packages/applications/{environment}/{surface}/manifest.json"
                )
                package_path = root / relative
                package_path.parent.mkdir(parents=True, exist_ok=True)
                artifact_manifest = app_artifact_manifest(
                    environment=environment,
                    surface=surface,
                    source_git_sha="a" * 40,
                    source_tree_digest="sha1:" + ("b" * 40),
                    artifact_digest="sha256:" + ("d" * 64),
                )
                if environment == "prod" and surface in {
                    "web",
                    "android",
                    "opsPortal",
                }:
                    schema = finalizer.PROD_APPLICATION_SOURCE_SCHEMAS[surface]
                    package_payload = {
                        "schema": schema,
                        "sourceGitSha": "a" * 40,
                        "sourceTreeDigest": "sha1:" + ("b" * 40),
                    }
                    if surface == "web":
                        package_payload["contentSHA256"] = "d" * 64
                        package_payload["artifactManifest"] = artifact_manifest
                    elif surface == "android":
                        package_payload["apkSHA256"] = "d" * 64
                        package_payload["artifactManifest"] = artifact_manifest
                    else:
                        package_payload["packageDigest"] = "sha256:" + ("d" * 64)
                else:
                    package_payload = {
                        "schema": finalizer.APPLICATION_PACKAGE_SCHEMA,
                        "environment": environment,
                        "surface": surface,
                        "sourceGitSha": "a" * 40,
                        "sourceTreeDigest": "sha1:" + ("b" * 40),
                        "packageDigest": "sha256:" + ("d" * 64),
                        "artifactManifest": artifact_manifest,
                    }
                package_path.write_text(json.dumps(package_payload), encoding="utf-8")
                application_packages[environment][surface] = {
                    "path": relative,
                    "digest": "sha256:"
                    + hashlib.sha256(package_path.read_bytes()).hexdigest(),
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
            for environment in finalizer.ENVIRONMENTS
        }
        provider_evidence_count = (
            finalizer.expected_required_cell_count_from_readiness(provider_readiness)
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
        for label, relative in finalizer.RELEASE_CLOSURE_PATHS.items():
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
                for layer in finalizer.TEST_LAYERS
            },
            "evidence": {"files": test_evidence_files},
        }
        test = evidence_root / "testEvidence.json"
        test.write_text(json.dumps(test_evidence), encoding="utf-8")
        payload = finalizer.seal_manifest({
            "schema": finalizer.SCHEMA,
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
                for environment in finalizer.ENVIRONMENTS
            },
            "applicationPackages": application_packages,
            "contractGraphDigest": "sha256:"
            + hashlib.sha256(contract_graph.read_bytes()).hexdigest(),
            "requiredEvidence": {
                "environmentArtifacts": {
                    environment: services for environment in finalizer.ENVIRONMENTS
                },
                "configurationPackages": {
                    environment: services for environment in finalizer.ENVIRONMENTS
                },
                "applicationPackages": {
                    environment: list(finalizer.APPLICATION_PACKAGES[environment])
                    for environment in finalizer.ENVIRONMENTS
                },
                "contractGraphDigest": True,
                "providerEvidence": True,
                "testEvidence": list(finalizer.TEST_LAYERS),
                "environmentReceipts": list(finalizer.ENVIRONMENTS),
                "rolloutReceipt": True,
                "rollbackReceipt": True,
            },
            "testEvidence": {
                "path": test.relative_to(root).as_posix(),
                "digest": "sha256:" + hashlib.sha256(test.read_bytes()).hexdigest(),
                "status": "passed",
                "layers": {
                    layer: {"status": "passed", "artifactDigest": evidence_layer_digest}
                    for layer in finalizer.TEST_LAYERS
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
                *(f"environmentReceipts.{environment}" for environment in finalizer.ENVIRONMENTS),
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
        for environment in finalizer.PRE_PROD_ENVIRONMENTS:
            receipt_payload = {
                "schema": finalizer.ENVIRONMENT_RECEIPT_SCHEMA,
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
            "schema": finalizer.ROLLBACK_RECEIPT_SCHEMA,
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
        payload = finalizer.seal_manifest(payload)
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
                "118.31.239.122",
                "--data-mode",
                "isolated",
                "--prevalidate-scope",
                "first-party",
            ]
        )
        self.assertEqual(args.mode, "prevalidate")
        self.assertEqual(args.ssh_host, "118.31.239.122")
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
            manifest = stackctl._materialize_prevalidation_release_manifest(
                "oci://ghcr.io/owner/repo/release-artifact@sha256:" + digest
            )
        self.assertEqual(manifest, expected / "manifest.json")
        self.assertIn("--ref", invoked.call_args.args[0])
        with self.assertRaisesRegex(RuntimeError, "GHCR digest ref"):
            stackctl._materialize_prevalidation_release_manifest(
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

    def test_runtime_inspection_reads_systemd_and_container_image_identity(self) -> None:
        source = inspect_runtime._remote_python()
        self.assertIn('"systemctl", "--user", "is-enabled"', source)
        self.assertIn('"systemctl", "--user", "is-active"', source)
        self.assertIn('"imageId": item.get("Image")', source)

    def test_manifest_requires_clean_reviewed_main_and_ghcr_digests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._artifact(Path(tmp))
            git_results = [
                subprocess.CompletedProcess(["git"], 0, stdout=("a" * 40) + "\n", stderr=""),
                subprocess.CompletedProcess(["git"], 0, stdout="", stderr=""),
                subprocess.CompletedProcess(["git"], 0, stdout="", stderr=""),
            ]
            with mock.patch.object(stackctl, "run", side_effect=git_results):
                resolved = stackctl._prevalidation_release_manifest(str(manifest))
            self.assertEqual(resolved[3], "1.20260726.42")
            self.assertEqual(resolved[4], resolved[2]["candidateId"])

            dirty_results = [
                subprocess.CompletedProcess(["git"], 0, stdout=("a" * 40) + "\n", stderr=""),
                subprocess.CompletedProcess(["git"], 0, stdout=" M tracked.py\n", stderr=""),
            ]
            with mock.patch.object(stackctl, "run", side_effect=dirty_results):
                with self.assertRaisesRegex(RuntimeError, "uncommitted worktree"):
                    stackctl._prevalidation_release_manifest(str(manifest))

    def test_latest_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._artifact(Path(tmp), image_version="latest")
            with self.assertRaisesRegex(RuntimeError, "must not use latest"):
                stackctl._prevalidation_release_manifest(str(manifest))

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
                    "118.31.239.122",
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
                    "118.31.239.122",
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
                return_value={"publicBases": {"api": "https://118.31.239.122"}},
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "canonical public HTTPS DNS"):
                stackctl._validate_prod_prevalidation_public_bases()


if __name__ == "__main__":
    unittest.main()

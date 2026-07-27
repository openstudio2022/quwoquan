from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.prod import inspect_prod_plane_runtime as inspect_runtime
from quwoquan_ops.cli.prod import prevalidate_prod_hosted as prevalidate


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
        release_files: dict[str, str] = {}
        release_digests: dict[str, str] = {}
        for service in services:
            relative = f"packages/services/{service}/config/config.yaml"
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("config:\n  version: sha256:" + ("b" * 64) + "\n", encoding="utf-8")
            release_files[service] = relative
            release_digests[service] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        digest = "sha256:" + ("c" * 64)
        images = {
            service: {
                "repository": f"ghcr.io/owner/repo/{service}",
                "tag": image_version,
                "digest": digest,
                "ref": f"ghcr.io/owner/repo/{service}@{digest}",
                "attestations": {
                    "spdxSbom": f"oci://ghcr.io/owner/repo/{service}@{digest}#spdxSbom",
                    "slsaProvenance": f"oci://ghcr.io/owner/repo/{service}@{digest}#slsaProvenance",
                },
            }
            for service in services
        }
        payload = {
            "schema": "mainline-release-artifact",
            "artifactName": "mainline-release-artifact",
            "status": "deployable",
            "source": {
                "gitSha": "a" * 40,
                "runNumber": 42,
                "repository": "owner/repo",
            },
            "versions": {
                "imageVersion": image_version,
                "configVersion": "v2026.07.26.42",
            },
            "requiredImages": services,
            "images": images,
            "releaseFiles": release_files,
            "releaseFileDigests": release_digests,
        }
        payload["manifestDigest"] = "sha256:" + hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
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
        self.assertEqual(spec["capacityStrategy"], "constrained-single-host")
        reclaim = spec["staleRuntimeReclaimPolicy"]
        self.assertTrue(reclaim["enabled"])
        self.assertFalse(reclaim["removeVolumes"])
        self.assertIn("quwoquan-data-recovery-mongodb", reclaim["preservedContainers"])
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

    def test_remote_reclaim_removes_only_scoped_dependents_in_safe_order(self) -> None:
        spec, projections = prevalidate.load_projection()
        script = prevalidate._remote_reclaim_script(
            projection=projections["service"],
            policy=spec["staleRuntimeReclaimPolicy"],
        )
        self.assertIn("while remaining:", script)
        self.assertIn('["podman", "rm", name]', script)
        self.assertIn("dependency-order retries", script)
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
            self.assertEqual(resolved[4], "v2026.07.26.42")

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
            with self.assertRaisesRegex(RuntimeError, "versions must be immutable"):
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
                    "full",
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

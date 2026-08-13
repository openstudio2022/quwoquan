from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.prod import collect_mainline_image_descriptors as collector
from quwoquan_ops.cli.prod import fetch_mainline_release_artifact as fetcher
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.cli.prod import load_prod_plane_images as image_loader
from quwoquan_ops.cli.prod import registry_transport


def _build_input_manifest(
    *,
    repository: str = "ghcr.io/owner/repo/content-service",
    transport_ref: str = "ghcr.io/owner/repo/content-service:sha-candidate",
) -> dict[str, object]:
    return finalizer.seal_manifest(
        {
            "schema": finalizer.SCHEMA,
            "candidateId": None,
            "status": "build-input",
            "generatedAt": "2026-07-28T00:00:00Z",
            "source": {
                "gitSha": "a" * 40,
                "treeDigest": "sha1:" + ("b" * 40),
                "repository": "owner/repo",
                "workflowRunId": "42",
                "sourceArchiveDigest": None,
            },
            "artifactDigest": None,
            "images": {
                "content-service": {
                    "repository": repository,
                    "transportRef": transport_ref,
                }
            },
            "configurationPackages": {
                environment: {
                    "content-service": {
                        "path": (
                            f"packages/environments/{environment}/services/"
                            "content-service/config/config.yaml"
                        ),
                        "digest": "sha256:" + ("c" * 64),
                    }
                }
                for environment in finalizer.ENVIRONMENTS
            },
            "applicationPackages": {
                environment: {} for environment in finalizer.ENVIRONMENTS
            },
            "contractGraphDigest": None,
            "requiredEvidence": {
                "images": ["content-service"],
                "configurationPackages": {
                    environment: ["content-service"]
                    for environment in finalizer.ENVIRONMENTS
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
            "testEvidence": {},
            "providerEvidence": {},
            "environmentReceipts": {},
            "rolloutReceipt": None,
            "rollbackReceipt": None,
            "blockers": [
                "immutable-image-evidence-pending",
                "whole-application-evidence-pending",
            ],
            "missingEvidence": [
                "images.content-service.digest",
                *(
                    f"applicationPackages.{environment}.{surface}"
                    for environment in finalizer.ENVIRONMENTS
                    for surface in finalizer.APPLICATION_PACKAGES[environment]
                ),
                "contractGraphDigest",
                "providerEvidence",
                "testEvidence",
                *(f"environmentReceipts.{environment}" for environment in finalizer.ENVIRONMENTS),
                "rollbackReceipt.ready",
                "rolloutReceipt",
                "rollbackReceipt.outcome",
            ],
        }
    )


def _component_manifest(config_bytes: bytes) -> dict[str, object]:
    repository = "ghcr.io/owner/repo/content-service"
    transport_ref = repository + ":sha-candidate"
    digest = "sha256:" + ("d" * 64)
    ref = f"{repository}@{digest}"
    manifest = _build_input_manifest(
        repository=repository,
        transport_ref=transport_ref,
    )
    manifest["status"] = "component-ready"
    manifest["images"] = {
        "content-service": {
            "repository": repository,
            "transportRef": transport_ref,
            "digest": digest,
            "ref": ref,
            "attestations": {
                "spdxSbom": f"oci://{ref}#spdxSbom",
                "slsaProvenance": f"oci://{ref}#slsaProvenance",
            },
        }
    }
    for environment in finalizer.ENVIRONMENTS:
        manifest["configurationPackages"][environment]["content-service"][
            "digest"
        ] = "sha256:" + hashlib.sha256(config_bytes).hexdigest()
    manifest["blockers"] = ["whole-application-evidence-pending"]
    manifest["missingEvidence"] = [
        *(
            f"applicationPackages.{environment}.{surface}"
            for environment in finalizer.ENVIRONMENTS
            for surface in finalizer.APPLICATION_PACKAGES[environment]
        ),
        "contractGraphDigest",
        "providerEvidence",
        "testEvidence",
        *(f"environmentReceipts.{environment}" for environment in finalizer.ENVIRONMENTS),
        "rollbackReceipt.ready",
        "rolloutReceipt",
        "rollbackReceipt.outcome",
    ]
    return finalizer.seal_manifest(manifest)


class MainlineReleaseOCITransportContractTest(unittest.TestCase):
    """Actions Artifact 配额不得降级不可变发布制品。

    spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-003
    spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-008
    """

    def test_fetcher_accepts_every_canonical_online_lifecycle_status(self) -> None:
        self.assertEqual(
            fetcher.FETCHABLE_STATUSES,
            {
                "component-ready",
                "candidate-ready",
                "deployable",
                "released",
                "rolled-back",
                "rollback-failed",
            },
        )

    def test_registry_transport_retries_same_command_with_bounded_backoff(self) -> None:
        command = mock.Mock(
            side_effect=[
                subprocess.CompletedProcess(["docker"], 1, stdout="", stderr="EOF"),
                subprocess.CompletedProcess(["docker"], 1, stdout="", stderr="EOF"),
                subprocess.CompletedProcess(["docker"], 0, stdout="ok", stderr=""),
            ]
        )
        with mock.patch.object(registry_transport.time, "sleep") as sleep_mock:
            result = registry_transport.run_with_bounded_retry(command)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(command.call_count, 3)
        self.assertEqual(
            sleep_mock.call_args_list,
            [mock.call(5), mock.call(15)],
        )

    def test_registry_transport_entrypoints_bootstrap_repo_package(self) -> None:
        root = Path(__file__).resolve().parents[4]
        for script_name in (
            "collect_mainline_image_descriptors.py",
            "fetch_mainline_release_artifact.py",
            "load_prod_plane_images.py",
        ):
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "quwoquan_ops/cli/prod" / script_name),
                    "--help",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"{script_name}: {result.stdout}{result.stderr}",
            )

    def test_collector_resolves_ghcr_tag_to_digest_descriptor(self) -> None:
        manifest = _build_input_manifest()
        digest = "sha256:" + ("a" * 64)
        completed = subprocess.CompletedProcess(
            ["docker"],
            0,
            stdout=f"Name: image\nMediaType: application/vnd.oci.image.index.v1+json\nDigest: {digest}\n",
            stderr="",
        )
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(collector.subprocess, "run", return_value=completed),
            mock.patch.object(collector, "verify_oci_supply_chain") as verify,
        ):
            output = Path(tmp)
            descriptors = collector.collect(manifest, output)
            recorded = json.loads(
                output.joinpath("content-service.json").read_text(encoding="utf-8")
            )
        self.assertEqual(descriptors["content-service"]["digest"], digest)
        self.assertEqual(
            recorded["ref"],
            f"ghcr.io/owner/repo/content-service@{digest}",
        )
        verify.assert_called_once_with(
            f"ghcr.io/owner/repo/content-service@{digest}",
            repository="owner/repo",
            signer_workflow="owner/repo/.github/workflows/service_pipeline.yml",
        )

    def test_collector_resolves_independent_images_concurrently(self) -> None:
        manifest = _build_input_manifest()
        repository = "ghcr.io/owner/repo/user-service"
        manifest["images"]["user-service"] = {
            "repository": repository,
            "transportRef": repository + ":sha-candidate",
        }
        manifest["requiredEvidence"]["images"] = [
            "content-service",
            "user-service",
        ]
        for environment in finalizer.ENVIRONMENTS:
            manifest["configurationPackages"][environment]["user-service"] = {
                "path": (
                    f"packages/environments/{environment}/services/"
                    "user-service/config/config.yaml"
                ),
                "digest": "sha256:" + ("c" * 64),
            }
            manifest["requiredEvidence"]["configurationPackages"][environment] = [
                "content-service",
                "user-service",
            ]
        manifest["missingEvidence"].insert(1, "images.user-service.digest")
        manifest = finalizer.seal_manifest(manifest)
        rendezvous = threading.Barrier(2, timeout=2)
        digest = "sha256:" + ("a" * 64)

        def resolve(_ref: str) -> str:
            rendezvous.wait()
            return digest

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(collector, "resolve_registry_digest", side_effect=resolve),
            mock.patch.object(collector, "verify_oci_supply_chain"),
        ):
            descriptors = collector.collect(manifest, Path(tmp))

        self.assertEqual(
            list(descriptors),
            ["content-service", "user-service"],
        )

    def test_collector_rejects_latest_and_non_ghcr(self) -> None:
        base = _build_input_manifest(
            transport_ref="ghcr.io/owner/repo/content-service:latest"
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "must not use latest"):
                collector.collect(base, Path(tmp))
            base = _build_input_manifest(
                repository="docker.io/owner/content",
                transport_ref="docker.io/owner/content:sha-candidate",
            )
            with self.assertRaisesRegex(ValueError, "transport reference is invalid"):
                collector.collect(base, Path(tmp))

    def test_fetcher_requires_release_artifact_digest(self) -> None:
        with self.assertRaisesRegex(ValueError, "digest ref"):
            fetcher.fetch(
                "ghcr.io/owner/repo/release-artifact:latest",
                Path("/tmp/not-used"),
            )

    def test_discovery_resolves_source_sha_tag_to_digest(self) -> None:
        digest_ref = (
            "ghcr.io/owner/repo/release-artifact@sha256:" + ("b" * 64)
        )
        results = [
            subprocess.CompletedProcess(["docker", "pull"], 0, stdout="ok", stderr=""),
            subprocess.CompletedProcess(
                ["docker", "inspect"],
                0,
                stdout=json.dumps([digest_ref]),
                stderr="",
            ),
        ]
        with mock.patch.object(fetcher, "run", side_effect=results):
            resolved = fetcher.discover("owner/repo", "c" * 40)
        self.assertEqual(resolved, digest_ref)

    def test_release_transport_pins_linux_amd64_on_arm_hosts(self) -> None:
        digest_ref = (
            "ghcr.io/owner/repo/release-artifact@sha256:" + ("d" * 64)
        )
        calls: list[list[str]] = []
        config_bytes = b"config: canonical\n"
        manifest = _component_manifest(config_bytes)

        def fake_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            if argv[1:3] == ["image", "inspect"]:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout=json.dumps([digest_ref]),
                    stderr="",
                )
            if argv[1] == "create":
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout="release-container\n",
                    stderr="",
                )
            if argv[1] == "cp":
                root = Path(argv[-1])
                root.joinpath("manifest.json").write_text(
                    json.dumps(manifest), encoding="utf-8"
                )
                for environment in finalizer.ENVIRONMENTS:
                    config = (
                        root
                        / "packages/environments"
                        / environment
                        / "services/content-service/config/config.yaml"
                    )
                    config.parent.mkdir(parents=True, exist_ok=True)
                    config.write_bytes(config_bytes)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            fetcher,
            "run",
            side_effect=fake_run,
        ):
            fetcher.fetch(digest_ref, Path(tmp) / "release")

        self.assertIn(
            ["docker", "pull", "--platform", "linux/amd64", digest_ref],
            calls,
        )
        self.assertIn(
            ["docker", "create", "--platform", "linux/amd64", digest_ref],
            calls,
        )

    def test_service_image_pull_pins_linux_amd64(self) -> None:
        source_ref = "ghcr.io/owner/repo/content-service@sha256:" + ("e" * 64)
        target_ref = "localhost/quwoquan_service_content-service:1.2.3"
        completed = subprocess.CompletedProcess(
            ["docker"],
            0,
            stdout="",
            stderr="",
        )
        with mock.patch.object(
            image_loader.subprocess,
            "run",
            return_value=completed,
        ) as run_mock:
            image_loader._pull_and_tag_release_image(
                source_ref,
                target_ref,
                platform="linux/amd64",
            )

        self.assertEqual(
            run_mock.call_args_list[0].args[0],
            ["docker", "pull", "--platform", "linux/amd64", source_ref],
        )


if __name__ == "__main__":
    unittest.main()

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
from quwoquan_ops.ci import release_evidence_reader as finalizer
from quwoquan_ops.cli.prod import load_prod_plane_images as image_loader
from quwoquan_ops.cli.prod import registry_transport


def _seal_snapshot(payload: dict[str, object]) -> dict[str, object]:
    payload["releaseTrainId"] = finalizer.canonical_release_train_digest(payload)
    for environment in finalizer.ENVIRONMENTS:
        artifact = payload["environmentArtifacts"][environment]
        if all("digest" in descriptor for descriptor in artifact["images"].values()):
            artifact["environmentArtifactDigest"] = (
                finalizer.canonical_environment_artifact_digest(payload, environment)
            )
    try:
        payload["candidateId"] = finalizer.canonical_candidate_digest(payload)
    except ValueError:
        payload["candidateId"] = None
    payload["blockers"], payload["missingEvidence"] = finalizer._expected_gaps(
        payload, str(payload["status"])
    )
    payload["artifactDigest"] = finalizer.canonical_manifest_digest(payload)
    return payload


def _build_input_manifest(
    *,
    repository: str = "ghcr.io/owner/repo/content-service",
    transport_ref: str = "ghcr.io/owner/repo/content-service:sha-candidate",
) -> dict[str, object]:
    return _seal_snapshot(
        {
            "schema": finalizer.SCHEMA,
            "releaseTrainId": None,
            "releaseCompositionId": None,
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
            "environmentArtifacts": {
                environment: {
                    "environment": environment,
                    "environmentArtifactDigest": None,
                    "images": {
                        "content-service": {
                            "repository": repository.replace(
                                "/content-service",
                                "/content-service-"
                                + ("prod" if environment == "prod" else "nonprod"),
                            ),
                            "transportRef": transport_ref.replace(
                                "/content-service:",
                                "/content-service-"
                                + ("prod" if environment == "prod" else "nonprod")
                                + ":",
                            ),
                        }
                    },
                    "configurationPackages": {
                        "content-service": {
                            "path": (
                                f"packages/environments/{environment}/services/"
                                "content-service/config/config.yaml"
                            ),
                            "digest": "sha256:" + ("c" * 64),
                        }
                    },
                }
                for environment in finalizer.ENVIRONMENTS
            },
            "applicationPackages": {},
            "publicWeb": None,
            "androidOfficialRelease": None,
            "opsPortal": None,
            "contractGraphDigest": None,
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
                *(
                    f"environmentArtifacts.{environment}.images.content-service.digest"
                    for environment in finalizer.ENVIRONMENTS
                ),
                *(
                    f"applicationPackages.{build_product_id}"
                    for build_product_id in finalizer.APPLICATION_PACKAGES
                ),
                "publicWeb",
                "androidOfficialRelease",
                "opsPortal",
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
    manifest = _build_input_manifest(
        repository=repository,
        transport_ref=transport_ref,
    )
    manifest["status"] = "component-ready"
    # DEC-005：alpha/beta/gamma 共享 nonprod digest，prod digest 分叉。
    for environment in finalizer.ENVIRONMENTS:
        image = manifest["environmentArtifacts"][environment]["images"][
            "content-service"
        ]
        environment_digest = (
            f"sha256:{2:064x}" if environment == "prod" else f"sha256:{1:064x}"
        )
        environment_repository = image["repository"]
        environment_ref = f"{environment_repository}@{environment_digest}"
        manifest["environmentArtifacts"][environment]["images"] = {
            "content-service": {
                "repository": environment_repository,
                "transportRef": image["transportRef"],
                "digest": environment_digest,
                "ref": environment_ref,
                "attestations": {
                    "spdxSbom": f"oci://{environment_ref}#spdxSbom",
                    "slsaProvenance": f"oci://{environment_ref}#slsaProvenance",
                },
            }
        }
        manifest["environmentArtifacts"][environment]["configurationPackages"][
            "content-service"
        ]["digest"] = "sha256:" + hashlib.sha256(config_bytes).hexdigest()
    manifest["blockers"] = ["whole-application-evidence-pending"]
    manifest["missingEvidence"] = [
        *(
            f"applicationPackages.{build_product_id}"
            for build_product_id in finalizer.APPLICATION_PACKAGES
        ),
        "publicWeb",
        "androidOfficialRelease",
        "opsPortal",
        "contractGraphDigest",
        "providerEvidence",
        "testEvidence",
        *(f"environmentReceipts.{environment}" for environment in finalizer.ENVIRONMENTS),
        "rollbackReceipt.ready",
        "rolloutReceipt",
        "rollbackReceipt.outcome",
    ]
    return _seal_snapshot(manifest)


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
                "artifact-complete",
                "qualified",
                "main-admitted",
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
        digest = "sha256:" + f"{1:064x}"

        def resolve(ref: str) -> str:
            # DEC-005：nonprod 三环境同一 digest，prod 分叉。
            return f"sha256:{2:064x}" if "-prod:" in ref else digest

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(
                collector,
                "resolve_registry_digest",
                side_effect=resolve,
            ),
            mock.patch.object(collector, "verify_oci_supply_chain") as verify,
        ):
            output = Path(tmp)
            descriptors = collector.collect(manifest, output)
            recorded = json.loads(
                output.joinpath("alpha/content-service.json").read_text(encoding="utf-8")
            )
        self.assertEqual(descriptors["alpha"]["content-service"]["digest"], digest)
        self.assertEqual(
            recorded["ref"],
            f"ghcr.io/owner/repo/content-service-nonprod@{digest}",
        )
        self.assertEqual(verify.call_count, 4)
        verify.assert_any_call(
            f"ghcr.io/owner/repo/content-service-nonprod@{digest}",
            repository="owner/repo",
            signer_workflow="owner/repo/.github/workflows/service_pipeline.yml",
        )

    def test_collector_resolves_independent_images_concurrently(self) -> None:
        manifest = _build_input_manifest()
        rendezvous = threading.Barrier(4, timeout=2)

        def resolve(ref: str) -> str:
            rendezvous.wait()
            return f"sha256:{2:064x}" if "-prod:" in ref else f"sha256:{1:064x}"

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(collector, "resolve_registry_digest", side_effect=resolve),
            mock.patch.object(collector, "verify_oci_supply_chain"),
        ):
            descriptors = collector.collect(manifest, Path(tmp))

        self.assertEqual(list(descriptors), list(finalizer.ENVIRONMENTS))
        self.assertTrue(
            all(list(images) == ["content-service"] for images in descriptors.values())
        )

    def test_collector_rejects_latest_and_non_ghcr(self) -> None:
        base = _build_input_manifest(
            transport_ref="ghcr.io/owner/repo/content-service:latest"
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "must not use latest"):
                collector.collect(base, Path(tmp))
            base = _build_input_manifest(
                repository="docker.io/owner/content-service",
                transport_ref="docker.io/owner/content-service:sha-candidate",
            )
            with self.assertRaisesRegex(ValueError, "transport reference is invalid"):
                collector.collect(base, Path(tmp))

    def test_fetcher_requires_release_artifact_digest(self) -> None:
        with self.assertRaisesRegex(ValueError, "digest ref"):
            fetcher.fetch(
                "ghcr.io/owner/repo/release-artifact:latest",
                Path("/tmp/not-used"),
            )

    def test_fetcher_cli_rejects_mutable_discovery_arguments(self) -> None:
        root = Path(__file__).resolve().parents[4]
        for retired_argument in ("--source-sha", "--repository"):
            result = subprocess.run(
                [
                    sys.executable,
                    str(
                        root
                        / "quwoquan_ops/cli/prod/fetch_mainline_release_artifact.py"
                    ),
                    "--ref",
                    "ghcr.io/owner/repo/release-artifact@sha256:" + "b" * 64,
                    "--output-dir",
                    "/tmp/not-used",
                    retired_argument,
                    "c" * 40 if retired_argument == "--source-sha" else "owner/repo",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("unrecognized arguments", result.stderr)
            self.assertIn(retired_argument, result.stderr)
        self.assertFalse(hasattr(fetcher, "discover"))

    def test_fetcher_help_describes_non_promotable_exact_digest_reader(self) -> None:
        root = Path(__file__).resolve().parents[4]
        result = subprocess.run(
            [
                sys.executable,
                str(root / "quwoquan_ops/cli/prod/fetch_mainline_release_artifact.py"),
                "--help",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--ref REF", result.stdout)
        self.assertIn("non-promotable prevalidation", result.stdout)
        self.assertIn("or historical inspection", result.stdout)
        self.assertNotIn("--source-sha", result.stdout)
        self.assertNotIn("--repository", result.stdout)

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

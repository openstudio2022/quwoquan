from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.prod import collect_mainline_image_descriptors as collector
from quwoquan_ops.cli.prod import fetch_mainline_release_artifact as fetcher
from quwoquan_ops.cli.prod import load_prod_plane_images as image_loader
from quwoquan_ops.cli.prod import registry_transport


class MainlineReleaseOCITransportContractTest(unittest.TestCase):
    """Actions Artifact 配额不得降级不可变发布制品。

    spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-003
    spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-008
    """

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
        root = Path(__file__).resolve().parents[3]
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
        manifest = {
            "status": "build-input",
            "requiredImages": ["content-service"],
            "imageRepositories": {
                "content-service": "ghcr.io/owner/repo/content-service"
            },
            "versions": {"imageVersion": "1.20260727.42"},
        }
        digest = "sha256:" + ("a" * 64)
        completed = subprocess.CompletedProcess(
            ["docker"],
            0,
            stdout=f"Name: image\nMediaType: application/vnd.oci.image.index.v1+json\nDigest: {digest}\n",
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            collector.subprocess, "run", return_value=completed
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

    def test_collector_rejects_latest_and_non_ghcr(self) -> None:
        base = {
            "status": "build-input",
            "requiredImages": ["content-service"],
            "imageRepositories": {"content-service": "docker.io/owner/content"},
            "versions": {"imageVersion": "latest"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "not immutable"):
                collector.collect(base, Path(tmp))
            base["versions"]["imageVersion"] = "1.2.3"
            with self.assertRaisesRegex(ValueError, "not GHCR"):
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
                Path(argv[-1]).joinpath("manifest.json").write_text(
                    "{}",
                    encoding="utf-8",
                )
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

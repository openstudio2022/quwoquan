from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.prod import collect_mainline_image_descriptors as collector
from quwoquan_ops.cli.prod import fetch_mainline_release_artifact as fetcher


class MainlineReleaseOCITransportContractTest(unittest.TestCase):
    """Actions Artifact 配额不得降级不可变发布制品。

    spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-003
    spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-008
    """

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


if __name__ == "__main__":
    unittest.main()

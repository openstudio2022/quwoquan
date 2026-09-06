from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli.prod import load_prod_plane_images


class ProdImageContentDigestContractTest(unittest.TestCase):
    def test_rtc_source_images_use_exact_candidate_digest(self) -> None:
        refs = load_prod_plane_images._compose_image_refs(
            ["realtime-gateway", "rtc-service"],
            candidate_digest="sha256:" + "d" * 64,
        )
        self.assertEqual(
            refs["realtime-gateway"],
            "localhost/quwoquan_service_realtime-gateway:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        )
        self.assertNotIn("latest", refs["rtc-service"])

    @patch.object(load_prod_plane_images.subprocess, "run")
    def test_local_digest_accepts_only_content_addressed_image_id(
        self,
        run,
    ) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="sha256:" + ("a" * 64) + "\n",
            stderr="",
        )
        self.assertEqual(
            load_prod_plane_images._local_image_digest("localhost/realtime"),
            "sha256:" + ("a" * 64),
        )

        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="latest\n",
            stderr="",
        )
        self.assertIsNone(
            load_prod_plane_images._local_image_digest("localhost/realtime")
        )

    @patch.object(load_prod_plane_images.subprocess, "run")
    def test_remote_digest_uses_podman_inspect_and_rejects_tag(
        self,
        run,
    ) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="sha256:" + ("b" * 64) + "\n",
            stderr="",
        )
        digest = load_prod_plane_images._remote_image_digest(
            "localhost/realtime-gateway:release",
            "svc-edge",
            "203.0.113.10",
            Path("/tmp/test-key"),
        )
        self.assertEqual(digest, "sha256:" + ("b" * 64))
        command = run.call_args.args[0]
        self.assertIn("podman", command)
        self.assertIn("inspect", command)
        self.assertNotIn("latest", command)

    @patch.object(load_prod_plane_images.subprocess, "run")
    def test_remote_digest_normalizes_legacy_podman_bare_image_id(
        self,
        run,
    ) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=("c" * 64) + "\n",
            stderr="",
        )

        self.assertEqual(
            load_prod_plane_images._remote_image_digest(
                "localhost/realtime-gateway:release",
                "svc-edge",
                "203.0.113.10",
                Path("/tmp/test-key"),
            ),
            "sha256:" + ("c" * 64),
        )


if __name__ == "__main__":
    unittest.main()

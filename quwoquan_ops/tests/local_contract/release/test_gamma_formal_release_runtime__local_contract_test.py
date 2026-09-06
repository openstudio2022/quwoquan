from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

from quwoquan_ops.cli import stackctl


DIGEST = "sha256:" + "a" * 64
REF = f"ghcr.io/example/quwoquan/content-service@{DIGEST}"


def completed(stdout: str = "", *, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


class GammaFormalReleaseRuntimeTest(unittest.TestCase):
    def _composition(self) -> dict[str, object]:
        return {
            "releaseCompositionId": "sha256:" + "b" * 64,
            "artifactDigest": "sha256:" + "c" * 64,
            "images": {
                "content-service": {
                    "ref": REF,
                    "digest": DIGEST,
                }
            },
        }

    @staticmethod
    def _container(*, image_ref: str = REF, status: str = "running") -> str:
        return json.dumps(
            [
                {
                    "Config": {"Image": image_ref},
                    "Image": "sha256:" + "d" * 64,
                    "State": {"Status": status, "Health": {"Status": "healthy"}},
                }
            ]
        )

    def test_exact_running_digest_is_retained_as_runtime_evidence(self) -> None:
        with patch.object(
            stackctl,
            "run",
            side_effect=[
                completed("container-id\n"),
                completed(self._container()),
                completed(json.dumps([{"RepoDigests": [REF]}])),
            ],
        ):
            runtime = stackctl._inspect_gamma_release_runtime(
                self._composition(),
                {"LOCAL_GAMMA_COMPOSE_PROJECT_NAME": "quwoquan_service"},
            )
        self.assertEqual(runtime["content-service"]["ref"], REF)
        self.assertEqual(runtime["content-service"]["digest"], DIGEST)
        self.assertEqual(runtime["content-service"]["status"], "running")

    def test_container_config_ref_mismatch_is_gate_block(self) -> None:
        with patch.object(
            stackctl,
            "run",
            side_effect=[
                completed("container-id\n"),
                completed(self._container(image_ref="content-service:mutable")),
            ],
        ):
            with self.assertRaisesRegex(ValueError, "differs from candidate"):
                stackctl._inspect_gamma_release_runtime(self._composition(), {})

    def test_missing_local_repo_digest_is_gate_block(self) -> None:
        with patch.object(
            stackctl,
            "run",
            side_effect=[
                completed("container-id\n"),
                completed(self._container()),
                completed(json.dumps([{"RepoDigests": []}])),
            ],
        ):
            with self.assertRaisesRegex(ValueError, "no exact pulled digest"):
                stackctl._inspect_gamma_release_runtime(self._composition(), {})


if __name__ == "__main__":
    unittest.main()

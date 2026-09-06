from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import package_runtime
from quwoquan_ops.cli.lib import deployment_candidate_manifest as deployment_candidate
from quwoquan_ops.cli.lib.deployment_candidate_manifest import manifest as candidate_manifest
from quwoquan_ops.tests.support.deployment_candidate_manifest_test_support import (
    DeploymentCandidateManifestContractBase,
)


class ProdHostedPackageOciManifestContractTest(unittest.TestCase):
    def test_stackctl_has_no_release_manifest_writer_or_finalizer_surface(self) -> None:
        self.assertFalse(hasattr(stackctl, "finalize_mainline_release_artifact"))
        self.assertFalse(hasattr(stackctl, "_command_package_release_manifest"))
        with self.assertRaises(SystemExit):
            stackctl.build_parser().parse_args(
                [
                    "package",
                    "--env",
                    "prod",
                    "--target",
                    "prod-hosted",
                    "--kind",
                    "release-manifest",
                ]
            )


class LocalPackageOciRequirementContractTest(
    DeploymentCandidateManifestContractBase
):
    def test_local_candidate_still_requires_package_bound_oci_manifest(self) -> None:
        (self.shared / "oci-images.json").unlink()

        with self.assertRaisesRegex(
            ValueError,
            "full candidate has no safe package-bound OCI manifest",
        ):
            deployment_candidate.write_candidate_manifest(
                "alpha",
                "alpha-local",
                package_snapshot=self.snapshot,
                release_attestation=str(self.release),
                rollback_release_attestation=str(self.rollback),
            )


def test_package_receipt_redacts_assignment_shaped_process_output() -> None:
    raw = "failed to fetch anonymous token: Get https://registry.example/token"

    redacted = package_runtime._receipt_safe_text(raw)

    assert "token: <redacted>" in redacted
    assert "token: Get" not in redacted


if __name__ == "__main__":
    unittest.main()

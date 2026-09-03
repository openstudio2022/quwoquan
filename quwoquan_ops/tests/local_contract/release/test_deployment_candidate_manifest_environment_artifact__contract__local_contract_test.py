"""deployment candidate 的 environmentArtifact 可复算身份契约。

# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-wave-deployment/spec.md#gwt-001.t2
"""

from __future__ import annotations

import copy
import json
import unittest

from quwoquan_ops.cli.lib import deployment_candidate_manifest as subject
from quwoquan_ops.tests.support.deployment_candidate_manifest_test_support import (
    DeploymentCandidateManifestContractBase,
)


class DeploymentCandidateEnvironmentArtifactContractTest(
    DeploymentCandidateManifestContractBase
):
    def _write_candidate(self) -> dict[str, object]:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        return json.loads(path.read_text(encoding="utf-8"))

    def test_environment_artifact_binds_complete_recomputable_identity(self) -> None:
        payload = self._write_candidate()
        artifact = payload["environmentArtifact"]

        self.assertEqual(artifact["environment"], "alpha")
        self.assertEqual(artifact["target"], "alpha-local")
        self.assertEqual(artifact["sourceCapsule"]["baselineId"], self.snapshot["baselineId"])
        self.assertEqual(artifact["sourceCapsule"]["digest"], self.workspace_digest)
        self.assertEqual(artifact["packageDigest"], payload["packageDigest"])
        self.assertEqual(artifact["imageBuildInputDigest"], payload["buildInputDigest"])
        self.assertEqual(artifact["imageSetDigest"], payload["imageDigest"])
        self.assertEqual(
            artifact["configuration"],
            {
                "serviceDigest": payload["configurationDigest"],
                "appRuntimeDigest": payload["runtimeConfigDigest"],
                "environmentRuntimeDigest": payload["environmentRuntimeDigest"],
            },
        )
        self.assertEqual(
            artifact["provider"],
            {
                "bindingDigest": payload["providerRuntime"]["composition"]["bindingDigest"],
                "runtimeCompositionDigest": payload["providerRuntime"]["composition"][
                    "runtimeCompositionDigest"
                ],
            },
        )
        self.assertEqual(
            artifact["contractGraphDigest"], payload["contractGraphDigest"]
        )
        self.assertEqual(
            artifact["identityCoreDigest"],
            subject.environment_artifact_identity_core_digest(artifact),
        )
        self.assertEqual(
            artifact["environmentArtifactDigest"],
            subject.environment_artifact_digest(artifact),
        )
        self.assertFalse(self.environment_artifact_schema["additionalProperties"])
        self.assertEqual(
            set(self.environment_artifact_schema["required"]),
            set(artifact),
        )
        self.assertEqual(
            set(self.environment_artifact_schema["properties"]),
            set(artifact),
        )

    def test_environment_artifact_identity_core_avoids_image_digest_self_reference(
        self,
    ) -> None:
        artifact = self._write_candidate()["environmentArtifact"]
        changed = copy.deepcopy(artifact)
        changed["imageSetDigest"] = "sha256:" + "9" * 64

        self.assertEqual(
            subject.environment_artifact_identity_core_digest(changed),
            artifact["identityCoreDigest"],
        )
        self.assertNotEqual(
            subject.environment_artifact_digest(changed),
            artifact["environmentArtifactDigest"],
        )

    def test_environment_artifact_rejects_unknown_or_missing_fields(self) -> None:
        payload = self._write_candidate()
        canonical = payload["environmentArtifact"]
        malformed_artifacts: list[dict[str, object]] = []
        missing = copy.deepcopy(canonical)
        missing.pop("runtimeTopologyDigest")
        malformed_artifacts.append(missing)
        extra = copy.deepcopy(canonical)
        extra["legacyImageDigest"] = extra["imageSetDigest"]
        malformed_artifacts.append(extra)

        for artifact in malformed_artifacts:
            with self.subTest(fields=sorted(artifact)), self.assertRaisesRegex(
                ValueError,
                "environmentArtifact fields mismatch",
            ):
                malformed = copy.deepcopy(payload)
                malformed["environmentArtifact"] = artifact
                subject.validate_candidate_manifest(
                    malformed,
                    expected_environment="alpha",
                    expected_target="alpha-local",
                    require_full=True,
                    candidate_root=self.candidate,
                )

    def test_environment_artifact_rejects_target_environment_mismatch(self) -> None:
        payload = self._write_candidate()
        malformed = copy.deepcopy(payload)
        malformed["environmentArtifact"]["target"] = "beta-local"

        with self.assertRaisesRegex(ValueError, "target identity mismatch"):
            subject.validate_candidate_manifest(
                malformed,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )
    def test_environment_artifact_rejects_cross_environment_reuse_and_tampering(
        self,
    ) -> None:
        payload = self._write_candidate()
        for field, value in (
            ("environment", "beta"),
            ("endpointAuthorityDigest", "sha256:" + "8" * 64),
            ("runtimeTopologyDigest", "sha256:" + "7" * 64),
            ("contractGraphDigest", "sha256:" + "6" * 64),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError,
                "target identity mismatch|binding drifted|digest drifted",
            ):
                malformed = copy.deepcopy(payload)
                malformed["environmentArtifact"][field] = value
                subject.validate_candidate_manifest(
                    malformed,
                    expected_environment="alpha",
                    expected_target="alpha-local",
                    require_full=True,
                    candidate_root=self.candidate,
                )

    def test_environment_artifact_rejects_retired_runtime_topology_schema(self) -> None:
        payload = self._write_candidate()
        topology = json.loads(self.runtime_topology_path.read_text(encoding="utf-8"))
        topology["schema"] = "qwq.runtime_topology_package.v3"
        self.runtime_topology_path.write_text(
            json.dumps(topology, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "runtime topology schema mismatch"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_environment_artifact_rejects_package_owned_topology_tampering(self) -> None:
        payload = self._write_candidate()
        self.runtime_topology_path.write_text(
            json.dumps({"schema": "tampered"}) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "runtime topology"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )


if __name__ == "__main__":
    unittest.main()

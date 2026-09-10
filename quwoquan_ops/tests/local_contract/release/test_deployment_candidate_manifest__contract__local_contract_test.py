"""deployment candidate manifest 身份与 release 绑定的本地契约。

Python 1000 行硬顶治理：provider/observability 工件与 symlink/payload
安全场景已按场景拆到同目录
test_deployment_candidate_manifest_<facet>__contract__local_contract_test.py
兄弟文件，共享 fixture 下沉到
quwoquan_ops/tests/support/deployment_candidate_manifest_test_support.py。
本文件保留 manifest 字段闭集、配置/OCI/运行时身份漂移与双 release
attestation 绑定语义。

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
"""

from __future__ import annotations

import json
import unittest

from quwoquan_ops.cli.lib import deployment_candidate_manifest as subject
from quwoquan_ops.tests.support.deployment_candidate_manifest_test_support import (
    DeploymentCandidateManifestContractBase,
)


class DeploymentCandidateManifestContractTest(
    DeploymentCandidateManifestContractBase
):
    def test_full_candidate_binds_package_oci_runtime_and_both_releases(self) -> None:
        package_bytes_before = {
            path.relative_to(self.candidate): path.read_bytes()
            for path in self.candidate.joinpath("packages").rglob("*")
            if path.is_file()
        }
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        package_bytes_after = {
            item.relative_to(self.candidate): item.read_bytes()
            for item in self.candidate.joinpath("packages").rglob("*")
            if item.is_file()
        }

        self.assertEqual(package_bytes_after, package_bytes_before)
        self.assertEqual(payload["schema"], subject.CANDIDATE_MANIFEST_SCHEMA)
        self.assertEqual(payload["candidateType"], subject.RUNTIME_CANDIDATE_TYPE)
        self.assertEqual(payload["baselineId"], self.snapshot["baselineId"])
        self.assertEqual(
            payload["configurationDigest"],
            self.configuration_digest,
        )
        self.assertEqual(
            payload["runtimeConfigDigest"],
            self.runtime_config_digest,
        )
        self.assertNotEqual(
            payload["configurationDigest"],
            payload["runtimeConfigDigest"],
        )
        self.assertEqual(
            payload["runtimeSchemaVersion"],
            "environment-runtime-package",
        )
        self.assertEqual(
            payload["release"]["candidate"]["releaseId"],
            "west-lake-canonical-20260729",
        )
        self.assertEqual(payload["release"]["rollback"]["releaseId"], "pilot-002")
        self.assertNotIn("releaseInputClassification", payload)
        self.assertFalse(hasattr(subject, "release_input_classification"))
        for binding in payload["release"].values():
            self.assertEqual(
                set(binding),
                {"releaseId", "releaseDigest", "attestationRef", "attestationDigest"},
            )
        self.assertEqual(
            payload["contractGraphDigest"],
            self.contract_graph_digest,
        )
        self.assertEqual(
            payload["observabilityLogSink"]["adapterId"],
            "ext.obs.elasticsearch",
        )
        self.assertEqual(
            payload["observabilityLogSink"],
            self.observability_log_sink,
        )
        self.assertEqual(
            payload["providerRuntime"]["composition"]["runtimeCompositionDigest"],
            self.provider_runtime["runtimeCompositionDigest"],
        )
        self.assertEqual(
            payload["providerRuntime"]["images"],
            self.provider_images,
        )
        subject.validate_candidate_manifest(
            payload,
            expected_environment="alpha",
            expected_target="alpha-local",
            require_full=True,
            candidate_root=self.candidate,
        )

    def test_teardown_projects_only_previous_non_prod_sim_nullable_field(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        canonical = json.loads(path.read_text(encoding="utf-8"))
        previous = dict(canonical)
        previous.pop("appLaunchBundle")

        projected = subject.validate_candidate_manifest(
            previous,
            expected_environment="alpha",
            expected_target="alpha-local",
            require_full=True,
            candidate_root=self.candidate,
            purpose="teardown",
        )

        self.assertIsNone(projected["appLaunchBundle"])
        self.assertNotIn("appLaunchBundle", previous)
        with self.assertRaisesRegex(ValueError, "manifest fields mismatch"):
            subject.validate_candidate_manifest(
                previous,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
                purpose="self_verify",
            )

        prod_sim_previous = {**previous, "environment": "prod", "target": "prod-sim"}
        with self.assertRaisesRegex(ValueError, "manifest fields mismatch"):
            subject.validate_candidate_manifest(
                prod_sim_previous,
                expected_environment="prod",
                expected_target="prod-sim",
                require_full=True,
                candidate_root=self.candidate,
                purpose="teardown",
            )

        missing_other_field = dict(previous)
        missing_other_field.pop("runtimeConfigDigest")
        with self.assertRaisesRegex(ValueError, "manifest fields mismatch"):
            subject.validate_candidate_manifest(
                missing_other_field,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
                purpose="teardown",
            )

        extra_field = {**previous, "unexpectedField": None}
        with self.assertRaisesRegex(ValueError, "manifest fields mismatch"):
            subject.validate_candidate_manifest(
                extra_field,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
                purpose="teardown",
            )

    def test_candidate_binding_artifact_and_manifest_tamper_are_blocked(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        canonical = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(canonical["dataPlaneBinding"], self.data_plane_binding)
        serialized = json.dumps(canonical["dataPlaneBinding"])
        self.assertNotIn("actual-password", serialized)

        drifted = dict(canonical)
        drifted["dataPlaneBinding"] = {
            **canonical["dataPlaneBinding"],
            "bindingDigest": "sha256:" + "9" * 64,
        }
        with self.assertRaisesRegex(ValueError, "dataPlaneBinding identity drifted"):
            subject.validate_candidate_manifest(
                drifted,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

        artifact = self.shared / "data-plane-binding.json"
        artifact.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "data-plane binding is invalid"):
            subject.validate_candidate_manifest(
                canonical,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_missing_configuration_identity(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))

        for field in ("configurationDigest", "runtimeConfigDigest"):
            with self.subTest(field=field):
                malformed = dict(payload)
                malformed.pop(field)
                with self.assertRaisesRegex(
                    ValueError,
                    "deployment candidate manifest fields mismatch",
                ):
                    subject.validate_candidate_manifest(
                        malformed,
                        expected_environment="alpha",
                        expected_target="alpha-local",
                        require_full=True,
                        candidate_root=self.candidate,
                    )

    def test_candidate_rejects_missing_or_drifted_package_identity(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        canonical = json.loads(path.read_text(encoding="utf-8"))
        for field in ("contractGraphDigest",):
            with self.subTest(field=field):
                malformed = dict(canonical)
                malformed.pop(field)
                with self.assertRaisesRegex(
                    ValueError,
                    "deployment candidate manifest fields mismatch",
                ):
                    subject.validate_candidate_manifest(
                        malformed,
                        expected_environment="alpha",
                        expected_target="alpha-local",
                        require_full=True,
                        candidate_root=self.candidate,
                    )

        classification_drift = dict(canonical)
        classification_drift["releaseInputClassification"] = "research_inputs"
        with self.assertRaisesRegex(ValueError, "manifest fields mismatch"):
            subject.validate_candidate_manifest(
                classification_drift,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_teardown_rejects_retired_classification(self) -> None:
        # 退出仍验证封存身份，不补默认类别或改写旧候选。
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        canonical = json.loads(path.read_text(encoding="utf-8"))
        sealed_by_previous_policy = {**canonical, "releaseInputClassification": "mixed_inputs"}
        with self.assertRaisesRegex(ValueError, "manifest fields mismatch"):
            subject.validate_candidate_manifest(
                sealed_by_previous_policy,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )
        with self.assertRaisesRegex(ValueError, "manifest fields mismatch"):
            subject.validate_candidate_manifest(
                sealed_by_previous_policy,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
                purpose="teardown",
            )
        unknown_classification = {**canonical, "releaseInputClassification": "legacy_inputs"}
        with self.assertRaisesRegex(ValueError, "manifest fields mismatch"):
            subject.validate_candidate_manifest(
                unknown_classification,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
                purpose="teardown",
            )

        graph_drift = dict(canonical)
        graph_drift["contractGraphDigest"] = "sha256:" + "9" * 64
        # The environment artifact binds the contract graph digest into its own
        # identity, so a drifted graph breaks that binding before the package
        # fingerprint is ever compared.
        with self.assertRaisesRegex(
            ValueError,
            "environmentArtifact binding drifted or digest drifted",
        ):
            subject.validate_candidate_manifest(
                graph_drift,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_self_verify_is_independent_of_current_source(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        release_bytes = self.release.read_bytes()
        rollback_bytes = self.rollback.read_bytes()
        self.contract_graph.write_text(
            json.dumps({"objects": [{"id": "drift"}], "operations": []}) + "\n",
            encoding="utf-8",
        )
        self.release.unlink()
        self.rollback.unlink()
        subject.validate_candidate_manifest(
            payload,
            expected_environment="alpha",
            expected_target="alpha-local",
            require_full=True,
            candidate_root=self.candidate,
            purpose="self_verify",
        )

        with self.assertRaisesRegex(
            ValueError,
            "candidate release attestation is unreadable",
        ):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
                purpose="currentness",
            )

        self.release.write_bytes(release_bytes)
        self.rollback.write_bytes(rollback_bytes)
        with self.assertRaisesRegex(ValueError, "ContractGraph bytes drifted"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
                purpose="currentness",
            )

        self.contract_graph.write_text(
            json.dumps({"objects": [], "operations": []}) + "\n",
            encoding="utf-8",
        )
        fingerprint_path = self.app / "package-fingerprint.json"
        fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
        fingerprint["releaseInputClassification"] = "mixed_inputs"
        fingerprint_path.write_text(json.dumps(fingerprint) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "package fingerprint release identity"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_extra_configuration_identity(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["legacyConfigurationDigest"] = self.configuration_digest

        with self.assertRaisesRegex(
            ValueError,
            "deployment candidate manifest fields mismatch",
        ):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_swapped_configuration_identities(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["configurationDigest"], payload["runtimeConfigDigest"] = (
            payload["runtimeConfigDigest"],
            payload["configurationDigest"],
        )

        with self.assertRaisesRegex(
            ValueError,
            "deployment candidate App runtime identity drifted",
        ):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_oci_configuration_drift(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["configurationDigest"] = "sha256:" + "3" * 64

        with self.assertRaisesRegex(
            ValueError,
            "deployment candidate OCI identity drifted",
        ):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_app_runtime_configuration_drift(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["runtimeConfigDigest"] = "sha256:" + "4" * 64

        with self.assertRaisesRegex(
            ValueError,
            "deployment candidate App runtime identity drifted",
        ):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_full_candidate_rejects_missing_release_binding(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "candidate release attestation is required"
        ):
            subject.write_candidate_manifest(
                "alpha",
                "alpha-local",
                package_snapshot=self.snapshot,
            )

    def test_package_preflight_rejects_same_candidate_and_rollback(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "must have distinct releaseId and releaseDigest",
        ):
            subject.validate_release_attestations(
                str(self.release),
                str(self.release),
            )

    def test_release_bindings_reject_retired_fields_for_every_validation_purpose(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha", "alpha-local", package_snapshot=self.snapshot,
            release_attestation=str(self.release), rollback_release_attestation=str(self.rollback),
        )
        canonical = json.loads(path.read_text(encoding="utf-8"))
        for purpose in ("self_verify", "currentness", "teardown"):
            for label in ("candidate", "rollback"):
                for field in ("releaseClass", "productLifecycleState", "unexpectedField"):
                    malformed = json.loads(json.dumps(canonical))
                    malformed["release"][label][field] = "production"
                    with self.subTest(purpose=purpose, label=label, field=field), self.assertRaisesRegex(
                        ValueError, "release fields mismatch"
                    ):
                        subject.validate_candidate_manifest(
                            malformed, expected_environment="alpha", expected_target="alpha-local",
                            require_full=True, candidate_root=self.candidate, purpose=purpose,
                        )

    def test_release_attestation_rejects_old_fields_and_missing_source_identity(self) -> None:
        canonical = json.loads(self.release.read_text(encoding="utf-8"))
        cases = {
            field: {**canonical, field: value}
            for field, value in (
                ("releaseClass", "production"), ("productLifecycleState", "production"),
                ("releaseInputClassification", "production_inputs"), ("unexpectedField", "value"),
            )
        }
        cases["missing_source_identity"] = {k: v for k, v in canonical.items() if k != "sourceDigest"}
        cases["wrong_source_owner"] = {**canonical, "sourceOwner": "other"}
        for label, payload in cases.items():
            path = self.root / f"{label}.json"
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, "attestation schema mismatch"):
                subject.validate_release_attestations(str(path), str(self.rollback))

    def test_candidate_validation_rechecks_exact_attestation_bytes(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        changed = json.loads(self.release.read_text(encoding="utf-8"))
        self.release.write_text(
            json.dumps(changed, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ValueError,
            "candidate release attestation bytes drifted",
        ):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
                purpose="currentness",
            )


if __name__ == "__main__":
    unittest.main()

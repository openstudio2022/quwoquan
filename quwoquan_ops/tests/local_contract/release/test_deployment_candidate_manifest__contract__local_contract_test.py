"""deployment candidate manifest 身份与 release 绑定的本地契约。

Python 1000 行硬顶治理：provider/observability 工件与 symlink/payload
安全场景已按场景拆到同目录
test_deployment_candidate_manifest_<facet>__contract__local_contract_test.py
兄弟文件，共享 fixture 下沉到
quwoquan_ops/tests/support/deployment_candidate_manifest_test_support.py。
本文件保留 manifest 字段闭集、配置/OCI/运行时身份漂移与双 release
attestation 绑定语义。测试逐字搬移。
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
        self.assertEqual(
            payload["release"]["candidate"]["releaseClass"],
            "commercial",
        )
        self.assertEqual(
            subject.release_input_classification(payload["release"]),
            "commercial_inputs",
        )
        self.assertEqual(
            payload["releaseInputClassification"],
            "commercial_inputs",
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
        for field in ("releaseInputClassification", "contractGraphDigest"):
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
        with self.assertRaisesRegex(ValueError, "release input classification"):
            subject.validate_candidate_manifest(
                classification_drift,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
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

    def test_release_input_classification_is_closed_over_both_bindings(self) -> None:
        cases = {
            ("research", "research"): "research_inputs",
            ("commercial", "commercial"): "commercial_inputs",
            ("research", "commercial"): "mixed_inputs",
            ("commercial", "research"): "mixed_inputs",
        }
        for (candidate_class, rollback_class), expected in cases.items():
            bindings: dict[str, dict[str, str]] = {}
            for label, release_class in (
                ("candidate", candidate_class),
                ("rollback", rollback_class),
            ):
                bindings[label] = {
                    "releaseId": label,
                    "releaseDigest": "sha256:" + "1" * 64,
                    "attestationRef": f"/{label}.json",
                    "attestationDigest": "sha256:" + "2" * 64,
                    "releaseClass": release_class,
                    "productLifecycleState": release_class,
                }
            with self.subTest(
                candidate=candidate_class,
                rollback=rollback_class,
            ):
                self.assertEqual(
                    subject.release_input_classification(bindings),
                    expected,
                )

    def test_release_binding_rejects_simplified_unknown_or_mismatched_lifecycle(
        self,
    ) -> None:
        cases = {
            "simplified": {},
            "unknown": {
                "releaseClass": "preview",
                "productLifecycleState": "preview",
            },
            "mismatch": {
                "releaseClass": "commercial",
                "productLifecycleState": "research",
            },
        }
        for label, lifecycle in cases.items():
            path = self.root / f"{label}.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_data.release_attestation",
                        "releaseId": label,
                        "payloadSha256": "sha256:" + "9" * 64,
                        **lifecycle,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with self.subTest(label=label), self.assertRaisesRegex(
                ValueError,
                "releaseClass|productLifecycleState|lifecycle",
            ):
                subject.validate_release_attestations(
                    str(path),
                    str(self.rollback),
                )

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

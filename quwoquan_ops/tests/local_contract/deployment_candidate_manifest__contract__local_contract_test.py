from __future__ import annotations

import json
import os
import unittest
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from quwoquan_ops.cli.lib import deployment_candidate_manifest as subject


class DeploymentCandidateManifestContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provider_runtime_fixture = subject.compile_provider_runtime_composition(
            environment="alpha",
            target="alpha-local",
        )

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # Production candidate paths are canonicalized by output_paths before
        # this module performs its descriptor-by-descriptor nofollow walk.
        self.root = Path(self.temporary.name).resolve()
        self.candidate = self.root / "candidate"
        self.app = self.candidate / "packages/app"
        self.shared = self.candidate / "packages/runtime-shared"
        self.legal = self.candidate / "packages/legal-static"
        self.app.mkdir(parents=True)
        self.shared.mkdir(parents=True)
        legal_current = self.legal / "current"
        (legal_current / "public/legal").mkdir(parents=True)
        for relative in (
            "release_metadata.json",
            "checksums.json",
            "public/legal/manifest.json",
        ):
            (legal_current / relative).write_text("{}\n", encoding="utf-8")
        digest = "sha256:" + "a" * 64
        self.snapshot = {
            "baselineId": "sha256:" + "b" * 64,
            "sourceRevision": "c" * 40,
            "workspaceStatusDigest": "sha256:" + "d" * 64,
        }
        (self.app / "environment_runtime.yaml").write_text(
            json.dumps(
                {
                    "schema": "environment-runtime-package",
                    "environment": "alpha",
                    "target": "alpha-local",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (self.app / "report.json").write_text(
            json.dumps({"runtimeConfigDigest": digest}) + "\n",
            encoding="utf-8",
        )
        (self.app / "package-fingerprint.json").write_text(
            json.dumps(
                {
                    "candidateType": subject.RUNTIME_CANDIDATE_TYPE,
                    "includeServices": True,
                    "deploymentInputs": {"digest": digest},
                    "packageContent": {"digest": digest},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (self.shared / "oci-images.json").write_text(
            json.dumps(
                {
                    "buildInputDigest": digest,
                    "imageDigest": "sha256:" + "e" * 64,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.release = self.root / "candidate-release.json"
        self.rollback = self.root / "rollback-release.json"
        for path, release_id, release_digest in (
            (self.release, "west-lake-canonical-20260729", "8" * 64),
            (self.rollback, "pilot-002", "5" * 64),
        ):
            path.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_data.release_attestation",
                        "releaseId": release_id,
                        "payloadSha256": "sha256:" + release_digest,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "app_deployment_package_dir",
                return_value=self.app,
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "runtime_shared_deployment_package_dir",
                return_value=self.shared,
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "legal_static_deployment_package_dir",
                return_value=self.legal,
            )
        )
        self.provider_runtime = self.provider_runtime_fixture
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "compile_provider_runtime_composition",
                return_value=self.provider_runtime,
            )
        )
        self.observability_log_sink = (
            subject.materialize_observability_log_sink_package(
                "alpha",
                "alpha-local",
                self.provider_runtime,
            )
        )
        subject.materialize_provider_runtime_package("alpha", "alpha-local")
        self.provider_images = {}
        for index, workload in enumerate(self.provider_runtime["workloads"], start=4):
            role = str(workload["role"])
            build_input_digest = "sha256:" + str(index) * 64
            self.provider_images[role] = {
                "buildInputDigest": build_input_digest,
                "ref": (
                    f"quwoquan/provider-runtime-{role}:"
                    f"{build_input_digest.removeprefix('sha256:')}"
                ),
                "imageDigest": "sha256:" + str(index + 2) * 64,
            }
        subject.seal_provider_runtime_package_images(
            "alpha",
            "alpha-local",
            self.candidate,
            self.provider_images,
        )
        first_party_images: dict[str, dict[str, str]] = {}
        first_party_refs: dict[str, str] = {}
        for index, service in enumerate(subject.first_party_service_names(), start=20):
            ref = (
                "localhost/quwoquan_service_"
                + service.replace("-", "_")
                + ":"
                + f"{index:064x}"
            )
            first_party_refs[service] = ref
            first_party_images[service] = {
                "ref": ref,
                "imageDigest": "sha256:" + f"{index + 40:064x}",
            }
        images = {**first_party_images, **self.provider_images}
        provider_refs = {
            role: {
                "buildInputDigest": descriptor["buildInputDigest"],
                "ref": descriptor["ref"],
            }
            for role, descriptor in sorted(self.provider_images.items())
        }
        oci = {
            "schema": "stackctl-package-oci-images",
            "environment": "alpha",
            "target": "alpha-local",
            "configurationDigest": digest,
            "buildInputDigest": subject._sha256_json(
                {
                    "firstPartyImageVersion": subject.immutable_image_digest(
                        first_party_refs
                    ),
                    "providerRuntimeDigest": self.provider_runtime[
                        "runtimeCompositionDigest"
                    ],
                    "providerImageRefs": provider_refs,
                }
            ),
            "imageDigest": subject._sha256_json(images),
            "images": images,
        }
        (self.shared / "oci-images.json").write_text(
            json.dumps(oci) + "\n",
            encoding="utf-8",
        )

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
            payload["runtimeSchemaVersion"],
            "environment-runtime-package",
        )
        self.assertEqual(
            payload["release"]["candidate"]["releaseId"],
            "west-lake-canonical-20260729",
        )
        self.assertEqual(payload["release"]["rollback"]["releaseId"], "pilot-002")
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

    def test_local_elasticsearch_image_accepts_only_pinned_package_forms(self) -> None:
        digest = "sha256:" + "1" * 64
        literal = "docker.elastic.co/elasticsearch/elasticsearch@" + digest

        self.assertEqual(
            subject.local_elasticsearch_image_digest(literal),
            digest,
        )
        self.assertEqual(
            subject.local_elasticsearch_image_digest(
                "${QWQ_COMPOSE_ELASTICSEARCH_IMAGE:-" + literal + "}"
            ),
            digest,
        )

        for invalid in (
            "docker.elastic.co/elasticsearch/elasticsearch:8.13.4",
            "${ELASTICSEARCH_IMAGE:-" + literal + "}",
            "${QWQ_COMPOSE_ELASTICSEARCH_IMAGE:-elasticsearch:8.13.4}",
            "${QWQ_COMPOSE_ELASTICSEARCH_IMAGE}",
        ):
            with (
                self.subTest(invalid=invalid),
                self.assertRaisesRegex(
                    ValueError,
                    "immutable Elastic digest",
                ),
            ):
                subject.local_elasticsearch_image_digest(invalid)

    def test_local_elasticsearch_package_resolves_platform_once(self) -> None:
        source = subject.yaml.safe_load(
            (
                subject.ROOT
                / "quwoquan_service/services/product-ops-service/deploy"
                / "local-elasticsearch.compose.yaml"
            ).read_text(encoding="utf-8")
        )
        arm = subject._local_elasticsearch_runtime_selection(
            source,
            machine="arm64",
        )
        amd = subject._local_elasticsearch_runtime_selection(
            source,
            machine="x86_64",
        )

        self.assertEqual(arm["platform"], "arm64")
        self.assertEqual(amd["platform"], "amd64")
        self.assertNotEqual(arm["imageDigest"], amd["imageDigest"])
        packaged = (
            self.candidate / self.observability_log_sink["composeRef"]
        ).read_text(encoding="utf-8")
        self.assertNotIn("x-qwq-package-elasticsearch", packaged)
        self.assertNotIn("QWQ_COMPOSE_ELASTICSEARCH_IMAGE", packaged)
        self.assertIn(self.observability_log_sink["imageDigest"], packaged)

    def test_candidate_rejects_tampered_observability_artifact(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        compose_ref = payload["observabilityLogSink"]["composeRef"]
        (self.candidate / compose_ref).write_text("tampered\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "artifact drifted"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_tampered_provider_runtime_identity(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["providerRuntime"]["composition"]["bindings"][0]["adapterId"] = (
            "ext.invalid"
        )

        with self.assertRaisesRegex(
            ValueError,
            "canonical environment Bindings|bindingDigest mismatch|local substitute",
        ):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_tampered_provider_runtime_artifact(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        artifact_ref = payload["providerRuntime"]["workloads"][0]["composeRef"]
        (self.candidate / artifact_ref).write_text("tampered\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "artifact drifted"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_tampered_provider_image_build_identity(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        role = next(iter(payload["providerRuntime"]["images"]))
        forged_digest = "sha256:" + "9" * 64
        payload["providerRuntime"]["images"][role]["buildInputDigest"] = forged_digest
        payload["providerRuntime"]["images"][role]["ref"] = (
            f"quwoquan/provider-runtime-{role}:"
            f"{forged_digest.removeprefix('sha256:')}"
        )
        provider_manifest = (
            self.candidate
            / "packages/runtime-shared/provider-runtime/manifest.json"
        )
        provider_manifest.write_text(
            json.dumps(payload["providerRuntime"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "differ from canonical OCI"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_runnable_candidate_validation_requires_candidate_root(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))

        with self.assertRaisesRegex(ValueError, "requires candidate_root"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
            )

    def test_candidate_write_rejects_symlinked_app_package_parent(self) -> None:
        external = self.root / "external-app-package"
        self.app.rename(external)
        self.app.symlink_to(external, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "symlink|unsafe"):
            subject.write_candidate_manifest(
                "alpha",
                "alpha-local",
                package_snapshot=self.snapshot,
                release_attestation=str(self.release),
                rollback_release_attestation=str(self.rollback),
            )

    def test_candidate_rejects_symlinked_observability_parent(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        artifact_root = (
            self.candidate
            / "packages/runtime-shared/observability-log-sink"
        )
        external = self.root / "external-observability-package"
        artifact_root.rename(external)
        artifact_root.symlink_to(external, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "unsafe"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_symlinked_provider_package_parent(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        package_root = self.candidate / "packages/runtime-shared/provider-runtime"
        external = self.root / "external-provider-package"
        package_root.rename(external)
        package_root.symlink_to(external, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "unsafe"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_symlinked_provider_package_manifest(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest = (
            self.candidate
            / "packages/runtime-shared/provider-runtime/manifest.json"
        )
        external = self.root / "external-provider-manifest.json"
        manifest.rename(external)
        manifest.symlink_to(external)

        with self.assertRaisesRegex(ValueError, "unsafe"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_symlinked_provider_composition(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        composition = self.candidate / payload["providerRuntime"]["compositionRef"]
        external = self.root / "external-provider-composition.json"
        composition.rename(external)
        composition.symlink_to(external)

        with self.assertRaisesRegex(ValueError, "unsafe"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_rejects_symlinked_oci_manifest(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        oci = self.shared / "oci-images.json"
        external = self.root / "external-oci-images.json"
        oci.rename(external)
        oci.symlink_to(external)

        with self.assertRaisesRegex(ValueError, "unsafe"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_load_rejects_symlinked_manifest(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        external = self.root / "external-candidate-manifest.json"
        path.rename(external)
        path.symlink_to(external)

        with (
            mock.patch.object(
                subject,
                "deployment_candidate_dir",
                return_value=self.candidate,
            ),
            self.assertRaisesRegex(ValueError, "symlink|non-regular"),
        ):
            subject.load_candidate_manifest(
                "alpha",
                "alpha-local",
                self.snapshot["baselineId"],
                require_full=True,
            )

    def test_candidate_rejects_symlinked_absolute_ancestor(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        linked_parent = self.root / "linked-candidate-parent"
        linked_parent.symlink_to(self.root, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "unsafe"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=linked_parent / "candidate",
            )

    def test_materializer_rejects_symlinked_absolute_ancestor(self) -> None:
        linked_parent = self.root / "linked-materializer-parent"
        linked_parent.symlink_to(self.root, target_is_directory=True)
        linked_shared = linked_parent / "candidate/packages/runtime-shared"

        with (
            mock.patch.object(
                subject,
                "runtime_shared_deployment_package_dir",
                return_value=linked_shared,
            ),
            self.assertRaisesRegex(ValueError, "ancestor|symlink"),
        ):
            subject.materialize_observability_log_sink_package(
                "alpha",
                "alpha-local",
                self.provider_runtime,
            )

    def test_candidate_rejects_unreferenced_payload_symlink(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        external = self.root / "external-runnable"
        external.write_text("do-not-read\n", encoding="utf-8")
        (self.app / "unreferenced-runnable").symlink_to(external)

        with self.assertRaisesRegex(ValueError, "payload tree is unsafe"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )
        self.assertEqual(external.read_text(encoding="utf-8"), "do-not-read\n")

    def test_candidate_rejects_non_regular_payload(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        os.mkfifo(self.app / "runtime.pipe")

        with self.assertRaisesRegex(ValueError, "payload tree is unsafe"):
            subject.validate_candidate_manifest(
                payload,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_full=True,
                candidate_root=self.candidate,
            )

    def test_candidate_manifest_is_create_once(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        before = path.read_bytes()

        with self.assertRaisesRegex(ValueError, "immutable and already exists"):
            subject.write_candidate_manifest(
                "alpha",
                "alpha-local",
                package_snapshot=self.snapshot,
                release_attestation=str(self.release),
                rollback_release_attestation=str(self.rollback),
            )

        self.assertEqual(path.read_bytes(), before)

    def test_candidate_write_rejects_symlinked_manifest_without_overwrite(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        external = self.root / "external-immutable-manifest.json"
        external.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(external)
        before = external.read_bytes()

        with self.assertRaisesRegex(ValueError, "symlink|non-regular"):
            subject.write_candidate_manifest(
                "alpha",
                "alpha-local",
                package_snapshot=self.snapshot,
                release_attestation=str(self.release),
                rollback_release_attestation=str(self.rollback),
            )

        self.assertEqual(external.read_bytes(), before)

    def test_candidate_manifest_parent_swap_cannot_write_external(self) -> None:
        external = self.root / "external-swap-target"
        external.mkdir()
        sentinel = external / "sentinel.txt"
        sentinel.write_text("preserve\n", encoding="utf-8")
        detached = self.root / "detached-candidate"
        original_revalidate = subject._revalidate_candidate_parent
        swapped = False

        def swap_before_activation(*args: object, **kwargs: object) -> None:
            nonlocal swapped
            if kwargs.get("label") == "deployment candidate manifest" and not swapped:
                swapped = True
                self.candidate.rename(detached)
                self.candidate.symlink_to(external, target_is_directory=True)
            original_revalidate(*args, **kwargs)

        with (
            mock.patch.object(
                subject,
                "_revalidate_candidate_parent",
                side_effect=swap_before_activation,
            ),
            self.assertRaisesRegex(ValueError, "parent|ancestor|symlink"),
        ):
            subject.write_candidate_manifest(
                "alpha",
                "alpha-local",
                package_snapshot=self.snapshot,
                release_attestation=str(self.release),
                rollback_release_attestation=str(self.rollback),
            )

        self.assertTrue(swapped)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")
        self.assertFalse((external / "manifest.json").exists())
        self.assertFalse((detached / "manifest.json").exists())

    def test_materializer_does_not_remove_external_existing_target(self) -> None:
        artifact = self.candidate / (
            "packages/runtime-shared/observability-log-sink"
        )
        preserved = self.root / "preserved-observability"
        artifact.rename(preserved)
        sentinel = preserved / "sentinel.txt"
        sentinel.write_text("preserve\n", encoding="utf-8")
        artifact.symlink_to(preserved, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "already exists"):
            subject.materialize_observability_log_sink_package(
                "alpha",
                "alpha-local",
                self.provider_runtime,
            )

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")

    def test_materializer_parent_swap_cannot_publish_external(self) -> None:
        artifact = self.candidate / (
            "packages/runtime-shared/observability-log-sink"
        )
        artifact.rename(self.root / "preserved-observability-package")
        external = self.root / "external-materializer-swap"
        external.mkdir()
        sentinel = external / "sentinel.txt"
        sentinel.write_text("preserve\n", encoding="utf-8")
        detached = self.root / "detached-materializer-candidate"
        original_revalidate = subject._revalidate_candidate_parent
        swapped = False

        def swap_before_publish(*args: object, **kwargs: object) -> None:
            nonlocal swapped
            if kwargs.get("label") == "observability log-sink package" and not swapped:
                swapped = True
                self.candidate.rename(detached)
                self.candidate.symlink_to(external, target_is_directory=True)
            original_revalidate(*args, **kwargs)

        with (
            mock.patch.object(
                subject,
                "_revalidate_candidate_parent",
                side_effect=swap_before_publish,
            ),
            self.assertRaisesRegex(ValueError, "ancestor|parent|symlink"),
        ):
            subject.materialize_observability_log_sink_package(
                "alpha",
                "alpha-local",
                self.provider_runtime,
            )

        self.assertTrue(swapped)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")
        self.assertFalse(
            (external / "packages/runtime-shared/observability-log-sink").exists()
        )
        self.assertFalse(
            (
                detached
                / "packages/runtime-shared/observability-log-sink"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()

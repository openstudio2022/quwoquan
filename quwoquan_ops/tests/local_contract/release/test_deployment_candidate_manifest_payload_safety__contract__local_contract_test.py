"""deployment candidate payload 树安全的本地契约。

由 test_deployment_candidate_manifest__contract__local_contract_test.py
（Python 1000 行硬顶治理）按场景拆出：candidate 树内任何 symlink、
非常规文件、parent swap（TOCTOU）与外部逃逸一律拒绝，manifest
create-once 且不可经 symlink 覆写。测试逐字搬移，共享 fixture 见
tests/support。
"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from quwoquan_ops.cli.lib import deployment_candidate_manifest as subject
from quwoquan_ops.tests.support.deployment_candidate_manifest_test_support import (
    DeploymentCandidateManifestContractBase,
)


class DeploymentCandidateManifestContractTest(
    DeploymentCandidateManifestContractBase
):
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

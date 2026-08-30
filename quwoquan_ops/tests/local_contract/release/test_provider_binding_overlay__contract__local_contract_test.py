"""候选 Provider Go overlay 的物化、校验与生产构建合同。"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import deployment_candidate_manifest as subject
from quwoquan_ops.cli.lib.deployment_candidate_manifest import provider_binding_overlay


class ProviderBindingOverlayContractTest(unittest.TestCase):
    def test_materializer_seals_sources_manifest_and_overlay_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source_root = root / "capsule"
            candidate_root = root / "candidate"
            source_root.mkdir()
            (candidate_root / "packages/runtime-shared").mkdir(parents=True)
            source = "package generated\n\nconst Environment = \"alpha\"\n"
            output_path = (
                "quwoquan_service/services/user-service/generated/account/"
                "user_account/external_provider_bindings.g.go"
            )
            binding_manifest = {
                "schema": (
                    "compiled-external-provider-binding-manifest."
                    "single-environment"
                ),
                "environment": "alpha",
                "target": "alpha-local",
                "bindingDigest": "sha256:" + "1" * 64,
                "readinessDigest": "sha256:" + "2" * 64,
                "descriptorDigest": "sha256:" + "3" * 64,
                "goSourceDigest": "sha256:" + "4" * 64,
                "descriptorCount": 1,
            }
            binding_manifest["manifestDigest"] = subject._sha256_json(
                binding_manifest
            )
            compiled = {
                "schema": "compiled-external-provider-bindings.single-environment",
                "environment": "alpha",
                "target": "alpha-local",
                "bindings": {},
                "readiness": {},
                "descriptors": [],
                "goSources": [
                    {
                        "rootId": "user.account.user_account",
                        "owner": "user-service",
                        "outputPath": output_path,
                        "sourceDigest": "sha256:"
                        + hashlib.sha256(source.encode("utf-8")).hexdigest(),
                        "source": source,
                    }
                ],
                "manifest": binding_manifest,
            }
            with (
                mock.patch.object(
                    subject,
                    "runtime_shared_deployment_package_dir",
                    return_value=candidate_root / "packages/runtime-shared",
                ),
                mock.patch.object(
                    provider_binding_overlay,
                    "compile_single_environment_bindings",
                    return_value=compiled,
                ) as compile_bindings,
            ):
                sealed = subject.materialize_provider_binding_overlay(
                    "alpha",
                    "alpha-local",
                    source_root=source_root,
                )

            compile_bindings.assert_called_once_with(
                environment="alpha",
                target="alpha-local",
                source_root=source_root,
            )
            artifact_root = (
                candidate_root
                / "packages/runtime-shared/compiled-provider-bindings"
            )
            manifest_path = artifact_root / "manifest.json"
            overlay_path = artifact_root / "go.overlay.json"
            self.assertEqual(
                manifest_path.read_text(encoding="utf-8"),
                json.dumps(sealed, ensure_ascii=False, indent=2) + "\n",
            )
            relative_source = sealed["sources"][0]["sourceRef"].removeprefix(
                "packages/runtime-shared/compiled-provider-bindings/"
            )
            self.assertEqual(
                (artifact_root / relative_source).read_text(encoding="utf-8"),
                source,
            )
            overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
            self.assertEqual(
                overlay,
                {
                    "Replace": {
                        output_path.removeprefix("quwoquan_service/"): (
                            "/run/qwq-provider-bindings/" + relative_source
                        )
                    }
                },
            )
            self.assertEqual(
                sealed["bindingManifestDigest"],
                binding_manifest["manifestDigest"],
            )

    def test_loader_uses_old_candidate_without_recompiling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            candidate_root = root / "candidate"
            artifact_root = (
                candidate_root
                / "packages/runtime-shared/compiled-provider-bindings"
            )
            source_path = artifact_root / "user.g.go"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("package generated\n", encoding="utf-8")
            source_digest = "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
            overlay_path = artifact_root / "go.overlay.json"
            overlay = {
                "Replace": {
                    (
                        "services/user-service/generated/account/user_account/"
                        "external_provider_bindings.g.go"
                    ): "/run/qwq-provider-bindings/user.g.go"
                }
            }
            overlay_path.write_text(json.dumps(overlay) + "\n", encoding="utf-8")
            binding_manifest = {
                "schema": (
                    "compiled-external-provider-binding-manifest."
                    "single-environment"
                ),
                "environment": "alpha",
                "target": "alpha-local",
                "bindingDigest": "sha256:" + "1" * 64,
                "readinessDigest": "sha256:" + "2" * 64,
                "descriptorDigest": "sha256:" + "3" * 64,
                "goSourceDigest": "sha256:" + "4" * 64,
                "descriptorCount": 1,
            }
            binding_manifest["manifestDigest"] = subject._sha256_json(
                binding_manifest
            )
            manifest = {
                "schema": provider_binding_overlay.PROVIDER_BINDING_OVERLAY_SCHEMA,
                "environment": "alpha",
                "target": "alpha-local",
                "bindingManifestDigest": binding_manifest["manifestDigest"],
                "bindingManifest": binding_manifest,
                "overlayRef": (
                    "packages/runtime-shared/compiled-provider-bindings/"
                    "go.overlay.json"
                ),
                "overlayDigest": "sha256:"
                + hashlib.sha256(overlay_path.read_bytes()).hexdigest(),
                "sources": [
                    {
                        "rootId": "user.account.user_account",
                        "owner": "user-service",
                        "outputPath": (
                            "quwoquan_service/services/user-service/generated/account/"
                            "user_account/external_provider_bindings.g.go"
                        ),
                        "sourceRef": (
                            "packages/runtime-shared/compiled-provider-bindings/"
                            "user.g.go"
                        ),
                        "sourceDigest": source_digest,
                    }
                ],
            }
            (artifact_root / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(
                provider_binding_overlay,
                "compile_single_environment_bindings",
                side_effect=AssertionError("rollback must not compile"),
            ):
                loaded = subject.load_provider_binding_overlay(
                    "alpha", "alpha-local", candidate_root
                )
        self.assertEqual(loaded, manifest)

    def test_go_runtime_builds_require_candidate_overlay(self) -> None:
        environment = {
            "QWQ_COMPOSE_ENV": "gamma",
            "LOCAL_GAMMA_CONFIG_VERSION": "sha256:" + "c" * 64,
            "QWQ_COMPOSE_GO_BASE_IMAGE": "golang:test",
            "QWQ_COMPOSE_ALPINE_BASE_IMAGE": "alpine:test",
        }
        with self.assertRaisesRegex(ValueError, "Provider binding overlay"):
            stackctl._runtime_image_build_spec(
                "service-core",
                source_root=stackctl.ROOT,
                environment=environment,
            )

    def test_go_runtime_build_spec_binds_candidate_overlay_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            overlay = Path(temporary) / "compiled-provider-bindings"
            overlay.mkdir()
            environment = {
                "QWQ_COMPOSE_ENV": "gamma",
                "LOCAL_GAMMA_CONFIG_VERSION": "sha256:" + "c" * 64,
                "QWQ_COMPOSE_GO_BASE_IMAGE": "golang:test",
                "QWQ_COMPOSE_ALPINE_BASE_IMAGE": "alpine:test",
                "QWQ_PROVIDER_BINDING_OVERLAY_CONTEXT": str(overlay),
                "QWQ_PROVIDER_BINDING_MANIFEST_DIGEST": "sha256:" + "d" * 64,
            }
            _, _, build_args = stackctl._runtime_image_build_spec(
                "service-core",
                source_root=stackctl.ROOT,
                environment=environment,
            )
        self.assertEqual(
            build_args["QWQ_PROVIDER_BINDING_OVERLAY_CONTEXT"],
            str(overlay),
        )
        self.assertEqual(
            build_args["QWQ_PROVIDER_BINDING_MANIFEST_DIGEST"],
            "sha256:" + "d" * 64,
        )

    def test_recommendation_runtime_does_not_require_go_overlay(self) -> None:
        environment = {
            "QWQ_COMPOSE_ENV": "gamma",
            "LOCAL_GAMMA_CONFIG_VERSION": "sha256:" + "c" * 64,
        }
        _, _, build_args = stackctl._runtime_image_build_spec(
            "recommendation-service",
            source_root=stackctl.ROOT,
            environment=environment,
        )
        self.assertNotIn("QWQ_PROVIDER_BINDING_OVERLAY", build_args)


if __name__ == "__main__":
    unittest.main()

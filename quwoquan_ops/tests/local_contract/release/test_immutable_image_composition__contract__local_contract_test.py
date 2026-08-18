from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import immutable_image_composition as composition
from quwoquan_ops.gate import verify_environment_assembly


ROOT = Path(__file__).resolve().parents[4]


class ImmutableImageCompositionContractTest(unittest.TestCase):
    """spec_ref: config-source-governance/GWT-001."""

    def test_all_first_party_image_owners_are_fail_closed(self) -> None:
        owners = composition.first_party_service_names(ROOT)
        self.assertGreaterEqual(len(owners), 15)
        self.assertIn("api-edge", owners)
        self.assertNotIn("travel-service", owners)
        self.assertFalse(
            (
                ROOT
                / "quwoquan_service/services/travel-service/config/schema.yaml"
            ).exists()
        )
        self.assertEqual(
            {service for service, _ in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS},
            set(composition.runtime_image_owner_names(ROOT)),
        )
        self.assertIn("service-core", composition.runtime_image_owner_names(ROOT))
        self.assertIn("search-service", owners)
        self.assertNotIn("search-service", composition.runtime_image_owner_names(ROOT))
        self.assertEqual(
            verify_environment_assembly.validate_first_party_image_composition_contract(),
            [],
        )

        tag_compose = yaml.safe_load(
            (
                ROOT
                / "quwoquan_service/services/tag-service/deploy/compose.yaml"
            ).read_text(encoding="utf-8")
        )
        migrate_environment = tag_compose["services"][
            "tag-service-migrate-taxonomy-snapshots"
        ]["environment"]
        self.assertTrue(
            migrate_environment["IMAGE_VERSION"].startswith(
                "${QWQ_COMPOSE_IMAGE_VERSION:?"
            )
        )

    def test_runtime_build_specs_resolve_from_canonical_compose_project(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        overlay = Path(temporary.name) / "compiled-provider-bindings"
        overlay.mkdir()
        environment = {
            "QWQ_COMPOSE_ENV": "gamma",
            "LOCAL_GAMMA_CONFIG_VERSION": "sha256:" + "c" * 64,
            "QWQ_COMPOSE_GO_BASE_IMAGE": "golang:test",
            "QWQ_COMPOSE_ALPINE_BASE_IMAGE": "alpine:test",
            "QWQ_COMPOSE_GO_BUILD_FLAGS": "-p=1",
            "QWQ_PROVIDER_BINDING_OVERLAY_CONTEXT": str(overlay),
            "QWQ_PROVIDER_BINDING_MANIFEST_DIGEST": "sha256:" + "d" * 64,
        }

        context, dockerfile, build_args = stackctl._runtime_image_build_spec(
            "platform-ops-service",
            source_root=ROOT,
            environment=environment,
        )
        self.assertEqual(context, ROOT)
        self.assertEqual(
            dockerfile,
            ROOT
            / "quwoquan_service/control-plane/platform-ops/build/Dockerfile",
        )
        self.assertEqual(build_args["GO_BASE_IMAGE"], "golang:test")
        self.assertEqual(build_args["ALPINE_BASE_IMAGE"], "alpine:test")
        self.assertEqual(build_args["QWQ_ARTIFACT_ENVIRONMENT"], "gamma")
        self.assertEqual(
            build_args["QWQ_ARTIFACT_CONFIG_DIGEST"],
            "sha256:" + "c" * 64,
        )

        context, dockerfile, _ = stackctl._runtime_image_build_spec(
            "recommendation-service",
            source_root=ROOT,
            environment=environment,
        )
        self.assertEqual(context, ROOT / "quwoquan_service")
        self.assertEqual(
            dockerfile,
            ROOT
            / "quwoquan_service/services/recommendation-service/build/Dockerfile",
        )

        for missing in ("QWQ_COMPOSE_ENV", "LOCAL_GAMMA_CONFIG_VERSION"):
            with self.subTest(missing=missing):
                invalid = dict(environment)
                invalid.pop(missing)
                with self.assertRaisesRegex(ValueError, "artifact"):
                    stackctl._runtime_image_build_spec(
                        "rtc-service",
                        source_root=ROOT,
                        environment=invalid,
                    )

    def test_package_binding_uses_environment_source_and_config_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            services = ("api-edge", "tag-service")
            digests = {
                "api-edge": "1" * 64,
                "tag-service": "2" * 64,
            }
            config_versions = {
                "api-edge": "3" * 64,
                "tag-service": "4" * 64,
            }
            for service in services:
                package = root / service
                package.mkdir(parents=True)
                (package / "provenance.json").write_text(
                    json.dumps(
                        {
                            "schema": "qwq.service_package",
                            "service": service,
                            "environment": "gamma",
                            "configVersion": f"sha256:{config_versions[service]}",
                            "digests": {
                                "sourceTree": f"sha256:{digests[service]}",
                            },
                        }
                    ),
                    encoding="utf-8",
                )

            with mock.patch.object(
                composition,
                "service_deployment_package_dir",
                side_effect=lambda environment, service: root / service,
            ):
                environment: dict[str, str] = {}
                receipt = composition.bind_packaged_image_composition(
                    "gamma",
                    environment,
                    services=services,
                    include_local_release_aliases=True,
                )
                gamma_refs = dict(receipt["images"])
                for service in services:
                    provenance = json.loads(
                        (root / service / "provenance.json").read_text(encoding="utf-8")
                    )
                    provenance["environment"] = "beta"
                    (root / service / "provenance.json").write_text(
                        json.dumps(provenance),
                        encoding="utf-8",
                    )
                beta_refs = {
                    service: composition.packaged_service_source_image_ref(
                        "beta", service
                    )
                    for service in services
                }

            self.assertRegex(str(receipt["digest"]), r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(
                environment["QWQ_COMPOSE_IMAGE_VERSION"],
                environment["LOCAL_GAMMA_IMAGE_VERSION"],
            )
            self.assertNotEqual(gamma_refs, beta_refs)
            for service in services:
                compose_key = composition.compose_image_environment_key(service)
                local_key = composition.local_release_image_environment_key(service)
                self.assertEqual(environment[compose_key], environment[local_key])
                self.assertRegex(environment[compose_key], r":[0-9a-f]{64}$")
                self.assertNotIn(":latest", environment[compose_key])

    def test_composition_digest_rejects_mutable_refs(self) -> None:
        for invalid_ref in (
            "example/api:latest",
            "example/api:down",
            "example/api:source-provenance-required",
            "example/api:0.1120222850435095399.992494410719750211",
        ):
            with self.subTest(ref=invalid_ref), self.assertRaisesRegex(
                ValueError,
                "mutable or non-canonical image ref",
            ):
                composition.immutable_image_digest({"api-edge": invalid_ref})
        with self.assertRaisesRegex(ValueError, "local image owner mismatch"):
            composition.immutable_image_digest(
                {
                    "api-edge": (
                        "localhost/quwoquan_service_content_service:" + "a" * 64
                    )
                }
            )
        first = composition.immutable_image_digest(
            {"api-edge": "example/api@sha256:" + "a" * 64}
        )
        second = composition.immutable_image_digest(
            {"api-edge": "example/api@sha256:" + "b" * 64}
        )
        self.assertNotEqual(first, second)
        self.assertIsNotNone(
            composition.IMMUTABLE_IMAGE_DIGEST_PATTERN.fullmatch(first)
        )

    def test_candidate_oci_projects_core_modules_to_one_image(self) -> None:
        candidate = "sha256:" + "a" * 64
        environment: dict[str, str] = {
            "QWQ_PROVIDER_BINDING_MANIFEST_DIGEST": "sha256:" + "d" * 64,
        }
        with (
            mock.patch.object(
                stackctl,
                "_packaged_service_source_image_ref",
                side_effect=lambda _env, service: (
                    f"localhost/quwoquan_service_{service.replace('-', '_')}:"
                    + "b" * 64
                ),
            ),
            mock.patch.object(
                stackctl,
                "_bind_gamma_packaged_configuration_digest",
                return_value="sha256:" + "c" * 64,
            ),
        ):
            projected = stackctl._bind_gamma_build_service_image_refs(
                "gamma",
                environment,
                candidate_digest=candidate,
            )

        images = set(projected["images"])
        self.assertIn("service-core", images)
        self.assertNotIn("search-service", images)
        self.assertRegex(
            projected["images"]["service-core"]["ref"],
            r"^localhost/quwoquan_service_core:[0-9a-f]{64}$",
        )
        self.assertFalse(
            projected["images"]["service-core"]["ref"].endswith("a" * 64)
        )
        self.assertEqual(
            environment["QWQ_COMPOSE_SERVICE_CORE_IMAGE"],
            projected["images"]["service-core"]["ref"],
        )

    def test_gamma_up_and_down_have_no_synthetic_image_identity(self) -> None:
        stackctl_source = (
            ROOT / "quwoquan_ops/cli/stackctl.py"
        ).read_text(encoding="utf-8")
        gamma_source = (
            ROOT / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        combined = stackctl_source + "\n" + gamma_source

        self.assertNotIn("source-provenance-required", combined)
        self.assertNotIn("quwoquan_service_${repository}:down", combined)
        self.assertNotIn('LOCAL_GAMMA_IMAGE_VERSION", "0.0.0"', combined)
        self.assertNotIn("LOCAL_GAMMA_IMAGE_REPOSITORY_ROOT", gamma_source)
        self.assertIn("_load_gamma_runtime_image_composition", stackctl_source)
        self.assertIn("validate_local_gamma_image_composition", gamma_source)
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        gate_block = makefile.split("\ngate-local-gamma:", 1)[1].split(
            "\n\n",
            1,
        )[0]
        self.assertIn(
            "python3 quwoquan_ops/cli/stackctl.py up --env gamma",
            gate_block,
        )
        self.assertNotIn(
            "bash quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
            gate_block,
        )


if __name__ == "__main__":
    unittest.main()

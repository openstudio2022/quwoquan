"""场景：gamma 运行时镜像绑定——compose 服务镜像全量绑定包 provenance、
运行时只认 package 精确 image id、非 active candidate 的包被拒绝。"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.tests.support.provider_binding_overlay_fixture import (
    write_provider_binding_overlay_fixture,
)
from quwoquan_ops.tests.support.stackctl_gamma_operation_lock_test_support import (
    StackctlGammaOperationLockContractTestBase,
)


class StackctlGammaOperationLockContractTest(
    StackctlGammaOperationLockContractTestBase
):
    def test_gamma_build_binds_all_compose_service_images_to_package_provenance(self) -> None:
        # The build tag closes over the compiled Provider binding, so the
        # candidate's binding manifest digest is a build input, not optional.
        binding_manifest_digest = "sha256:" + "9" * 64
        environment: dict[str, str] = {
            "QWQ_PROVIDER_BINDING_MANIFEST_DIGEST": binding_manifest_digest,
        }
        with (
            mock.patch.object(
                stackctl,
                "_packaged_service_source_image_ref",
                side_effect=lambda _env_name, service: (
                    self._packaged_service_source_ref(service, "a" * 64)
                ),
            ) as source_image,
            mock.patch.object(
                stackctl,
                "packaged_configuration_digest",
                return_value="sha256:" + "b" * 64,
            ),
        ):
            stackctl._bind_gamma_build_service_image_refs("gamma", environment)

        for service, environment_key in (
            stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
        ):
            source_ref = self._packaged_service_source_ref(service, "a" * 64)
            repository, _, source_tag = source_ref.rpartition(":")
            build_tag = hashlib.sha256(
                "\x00".join(
                    (service, source_tag, binding_manifest_digest)
                ).encode("utf-8")
            ).hexdigest()
            expected = repository + ":" + build_tag
            self.assertEqual(environment[environment_key], expected)
            self.assertEqual(
                environment[
                    stackctl.compose_image_environment_key(service)
                ],
                expected,
            )
        self.assertEqual(
            environment["LOCAL_GAMMA_IMAGE_VERSION"],
            environment["QWQ_COMPOSE_IMAGE_VERSION"],
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_CONFIG_VERSION"],
            "sha256:" + "b" * 64,
        )
        self.assertRegex(
            environment["QWQ_COMPOSE_IMAGE_VERSION"],
            r"^sha256:[0-9a-f]{64}$",
        )
        self.assertEqual(
            source_image.call_args_list,
            [
                mock.call("gamma", service)
                for service, _ in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
            ],
        )

    def test_gamma_runtime_binds_exact_package_image_ids_not_build_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            candidate_root = Path(temporary_dir).resolve() / "candidate"
            shared = candidate_root / "packages/runtime-shared"
            shared.mkdir(parents=True)
            binding_manifest_digest = write_provider_binding_overlay_fixture(
                candidate_root,
                environment="gamma",
                target="gamma-local",
            )
            source_refs = {
                service: self._packaged_service_source_ref(
                    service,
                    ("f" * 64 if service == stackctl.SERVICE_CORE_WORKLOAD else "build"),
                )
                for service, _ in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
            }
            build_refs = {
                service: self._packaged_service_build_ref(
                    service,
                    source_ref,
                    binding_manifest_digest,
                )
                for service, source_ref in source_refs.items()
            }
            images = {
                service: {
                    "ref": build_refs[service],
                    "imageDigest": "sha256:"
                    + format(index + 1, "064x"),
                }
                for index, (service, _) in enumerate(
                    stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
                )
            }
            provider_role = "provider-protocol-substitute"
            provider_descriptor = {
                "buildInputDigest": "sha256:" + "d" * 64,
                "ref": "quwoquan/provider-protocol-substitute:build",
                "imageDigest": "sha256:" + "e" * 64,
            }
            images[provider_role] = provider_descriptor
            image_set_digest = "sha256:" + stackctl.hashlib.sha256(
                json.dumps(
                    images,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            (shared / "oci-images.json").write_text(
                json.dumps(
                    {
                        "schema": stackctl.PACKAGE_OCI_IMAGES_SCHEMA,
                        "environment": "gamma",
                        "target": "gamma-local",
                        "configurationDigest": "sha256:" + "c" * 64,
                        "buildInputDigest": "sha256:" + "b" * 64,
                        "imageDigest": image_set_digest,
                        "images": images,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            environment = {
                "QWQ_LOCAL_RELEASE_TARGET": "gamma-local",
                "QWQ_LOCAL_RELEASE_ENV": "gamma",
                "QWQ_RUN_ROOT": str(Path(temporary_dir) / "run"),
            }
            candidate = {
                "baselineId": "sha256:" + "f" * 64,
                "imageDigest": image_set_digest,
                "buildInputDigest": "sha256:" + "b" * 64,
                "configurationDigest": "sha256:" + "c" * 64,
                "runtimeConfigDigest": "sha256:" + "a" * 64,
                "providerRuntime": {
                    "images": {provider_role: provider_descriptor}
                },
            }
            with (
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    return_value=candidate_root,
                ),
                mock.patch.object(
                    stackctl,
                    "_packaged_service_source_image_ref",
                    side_effect=lambda _env, service: source_refs[service],
                ),
                mock.patch.object(
                    stackctl,
                    "packaged_configuration_digest",
                    return_value="sha256:" + "c" * 64,
                ),
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    return_value={"baselineId": candidate["baselineId"]},
                ),
                mock.patch.object(
                    stackctl,
                    "load_candidate_manifest",
                    return_value=candidate,
                ),
            ):
                composition = stackctl._bind_gamma_packaged_service_image_refs(
                    "gamma",
                    environment,
                )

            drifted_candidate = {
                **candidate,
                "configurationDigest": "sha256:" + "d" * 64,
            }
            with (
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    return_value=candidate_root,
                ),
                mock.patch.object(
                    stackctl,
                    "_packaged_service_source_image_ref",
                    side_effect=lambda _env, service: source_refs[service],
                ),
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    return_value={"baselineId": candidate["baselineId"]},
                ),
                mock.patch.object(
                    stackctl,
                    "load_candidate_manifest",
                    return_value=drifted_candidate,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "package OCI configuration digest mismatch",
                ),
            ):
                stackctl._bind_gamma_packaged_service_image_refs(
                    "gamma",
                    {"QWQ_LOCAL_RELEASE_TARGET": "gamma-local"},
                )

            self.assertEqual(composition["imageDigest"], image_set_digest)
            self.assertEqual(composition["releaseCompositionId"], candidate["baselineId"])
            self.assertEqual(
                environment["QWQ_STARTUP_IMAGE_COMPOSITION_FILE"],
                str(shared / "oci-images.json"),
            )
            full_runtime_refs = {
                role: descriptor["imageDigest"]
                for role, descriptor in images.items()
            }
            self.assertEqual(
                environment["QWQ_STARTUP_IMAGE_TRANSPORT_TAG"],
                stackctl.immutable_image_digest(full_runtime_refs),
            )
            self.assertEqual(
                environment["LOCAL_GAMMA_IMAGE_VERSION"],
                composition["imageVersion"],
            )
            self.assertNotEqual(
                environment["LOCAL_GAMMA_IMAGE_VERSION"],
                environment["QWQ_STARTUP_IMAGE_TRANSPORT_TAG"],
            )
            for service, environment_key in (
                stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
            ):
                self.assertEqual(
                    environment[environment_key],
                    images[service]["imageDigest"],
                )
                self.assertNotEqual(environment[environment_key], build_refs[service])

    def test_gamma_runtime_refuses_a_package_that_is_not_the_active_candidate(
        self,
    ) -> None:
        for active, candidate, expected in (
            (None, None, "package OCI runtime has no active deployment candidate"),
            (
                {"baselineId": "sha256:" + "1" * 64},
                {
                    "baselineId": "sha256:" + "1" * 64,
                    "imageDigest": "sha256:" + "9" * 64,
                    "buildInputDigest": "sha256:" + "b" * 64,
                    "configurationDigest": "sha256:" + "c" * 64,
                    "runtimeConfigDigest": "sha256:" + "a" * 64,
                    "providerRuntime": {"images": {}},
                },
                "package OCI runtime differs from the active candidate",
            ),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary_dir:
                candidate_root = Path(temporary_dir).resolve() / "candidate"
                shared = candidate_root / "packages/runtime-shared"
                shared.mkdir(parents=True)
                binding_manifest_digest = write_provider_binding_overlay_fixture(
                    candidate_root,
                    environment="gamma",
                    target="gamma-local",
                )
                source_refs = {
                    service: self._packaged_service_source_ref(
                        service,
                        ("1" * 64 if service == stackctl.SERVICE_CORE_WORKLOAD else "build"),
                    )
                    for service, _ in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
                }
                build_refs = {
                    service: self._packaged_service_build_ref(
                        service,
                        source_ref,
                        binding_manifest_digest,
                    )
                    for service, source_ref in source_refs.items()
                }
                images = {
                    service: {
                        "ref": build_refs[service],
                        "imageDigest": "sha256:" + format(index + 1, "064x"),
                    }
                    for index, (service, _) in enumerate(
                        stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
                    )
                }
                image_set_digest = "sha256:" + stackctl.hashlib.sha256(
                    json.dumps(
                        images,
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest()
                (shared / "oci-images.json").write_text(
                    json.dumps(
                        {
                            "schema": stackctl.PACKAGE_OCI_IMAGES_SCHEMA,
                            "environment": "gamma",
                            "target": "gamma-local",
                            "configurationDigest": "sha256:" + "c" * 64,
                            "buildInputDigest": "sha256:" + "b" * 64,
                            "imageDigest": image_set_digest,
                            "images": images,
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                with (
                    mock.patch.object(
                        stackctl,
                        "deployment_candidate_dir",
                        return_value=candidate_root,
                    ),
                    mock.patch.object(
                        stackctl,
                        "_packaged_service_source_image_ref",
                        side_effect=lambda _env, service: source_refs[service],
                    ),
                    mock.patch.object(
                        stackctl,
                        "packaged_configuration_digest",
                        return_value="sha256:" + "c" * 64,
                    ),
                    mock.patch.object(
                        stackctl,
                        "active_deployment_candidate",
                        return_value=active,
                    ),
                    mock.patch.object(
                        stackctl,
                        "load_candidate_manifest",
                        return_value=candidate,
                    ),
                ):
                    with self.assertRaises(ValueError) as raised:
                        stackctl._bind_gamma_packaged_service_image_refs(
                            "gamma",
                            {"QWQ_LOCAL_RELEASE_TARGET": "gamma-local"},
                        )

                self.assertIn(expected, str(raised.exception))

"""场景：打包与构建输入真相源——startup 超时/基础镜像只来自 topology、打包前
脚本语法检查、单一 source digest 镜像集、Provider 构建上下文摘要与受保护值隔离。"""

from __future__ import annotations

import argparse
import contextlib
import tempfile
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.tests.support.stackctl_gamma_operation_lock_test_support import (
    StackctlGammaOperationLockContractTestBase,
)

BINDING_MANIFEST_DIGEST = "sha256:" + "9" * 64


def _provider_binding_overlay() -> dict[str, str]:
    """The candidate-sealed Provider binding overlay package build reads.

    Only the identity travels into the image build inputs here; overlay file
    materialization has its own contract.
    """

    return {
        "environment": "alpha",
        "target": "alpha-local",
        "bindingManifestDigest": BINDING_MANIFEST_DIGEST,
    }


class StackctlGammaOperationLockContractTest(
    StackctlGammaOperationLockContractTestBase
):
    def test_gamma_startup_timeouts_come_only_from_target_topology(self) -> None:
        topology = stackctl.load_environment_topology()
        target = stackctl.get_target(topology, "gamma-local")
        startup = target["startup"]
        build_images = target["buildImages"]

        environment = stackctl._gamma_env_from_port_manifest(
            topology,
            "gamma-local",
        )

        self.assertEqual(
            environment["LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS"],
            str(startup["composeBuildTimeoutSeconds"]),
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_DOCKER_PROBE_TIMEOUT_SECONDS"],
            str(startup["dockerProbeTimeoutSeconds"]),
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_COMPOSE_BUILD_NO_PROGRESS_TIMEOUT_SECONDS"],
            str(startup["composeBuildNoProgressTimeoutSeconds"]),
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS"],
            str(startup["composeUpTimeoutSeconds"]),
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_GO_BASE_IMAGE"],
            build_images["goBaseImage"],
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_ALPINE_BASE_IMAGE"],
            build_images["alpineBaseImage"],
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL"],
            target["publicBases"]["mediaUpload"],
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_RTC_MEDIA_CONNECTION_URL"],
            target["publicBases"]["rtc"],
        )

    def test_gamma_service_builds_require_topology_owned_base_images(self) -> None:
        service_root = stackctl.ROOT / "quwoquan_service"
        compose_files = sorted(service_root.glob("services/*/deploy/compose.yaml"))
        compose_files.append(
            service_root / "control-plane/platform-ops/deploy/compose.yaml"
        )

        for compose_file in compose_files:
            compose = compose_file.read_text(encoding="utf-8")
            if "GO_BASE_IMAGE:" not in compose:
                continue
            self.assertIn("QWQ_COMPOSE_GO_BASE_IMAGE:?", compose, compose_file)
            self.assertIn("QWQ_COMPOSE_ALPINE_BASE_IMAGE:?", compose, compose_file)
            self.assertNotIn("GO_ALPINE_BASE_IMAGE", compose, compose_file)
            self.assertNotIn(":-golang:", compose, compose_file)
            self.assertNotIn(":-alpine:", compose, compose_file)

            dockerfile_ref = compose.split("dockerfile: ", 1)[1].splitlines()[0]
            dockerfile = next(
                candidate
                for candidate in (
                    stackctl.ROOT / dockerfile_ref,
                    service_root / dockerfile_ref,
                )
                if candidate.is_file()
            )
            dockerfile_text = dockerfile.read_text(encoding="utf-8")
            self.assertIn("ARG GO_BASE_IMAGE\n", dockerfile_text, dockerfile)
            self.assertIn("ARG ALPINE_BASE_IMAGE\n", dockerfile_text, dockerfile)

    def test_gamma_up_checks_start_script_syntax_before_packaging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            argv_calls: list[list[str]] = []

            def fail_syntax(
                argv: list[str],
                *,
                env: dict[str, str] | None = None,
            ) -> CompletedProcess[str]:
                del env
                argv_calls.append(argv)
                return CompletedProcess(argv, 2, stdout="", stderr="syntax error")

            args = argparse.Namespace(
                env="gamma",
                target=None,
                workload="content-release",
                skip_app=True,
                skip_build=True,
                device_id="",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "validate_up_report_dir",
                    side_effect=lambda path, **_kwargs: Path(path),
                ),
                mock.patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value={"issues": []},
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={
                        "QWQ_COMPOSE_GO_BASE_IMAGE": "golang@sha256:" + "1" * 64,
                        "QWQ_COMPOSE_ALPINE_BASE_IMAGE": "alpine@sha256:" + "2" * 64,
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_optional_product_telemetry_environment",
                    return_value=({}, ""),
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(stackctl, "run", side_effect=fail_syntax),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            argv_calls,
            [["bash", "-n", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"]],
        )

    def test_package_reuses_one_source_digest_image_set_across_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            shared = root / "runtime-shared"
            shared.mkdir()
            composition = {
                "imageVersion": "sha256:" + "b" * 64,
                "configurationDigest": "sha256:" + "c" * 64,
                "images": {
                    "api-edge": {"ref": "localhost/api-edge:source"},
                    "user-service": {"ref": "localhost/user-service:source"},
                },
            }
            provider_digest = "sha256:" + "d" * 64
            provider_build_digest = "sha256:" + "e" * 64
            provider_images = {
                "provider-runtime": {
                    "buildInputDigest": provider_build_digest,
                    "ref": (
                        "quwoquan/provider-runtime-provider-runtime:"
                        + provider_build_digest.removeprefix("sha256:")
                    ),
                    "imageDigest": "sha256:" + "f" * 64,
                }
            }
            provider_runtime = {
                "composition": {"runtimeCompositionDigest": provider_digest},
                "images": {},
            }

            def inspect_only(
                argv: list[str],
                *,
                env: dict[str, str] | None = None,
            ) -> CompletedProcess[str]:
                del env
                self.assertEqual(argv[:4], ["docker", "image", "inspect", "--format"])
                digest = "1" if "api-edge" in argv[-1] else "2"
                return CompletedProcess(argv, 0, f"sha256:{digest * 64}\n", "")

            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={
                        "QWQ_COMPOSE_GO_BASE_IMAGE": "golang@sha256:" + "1" * 64,
                        "QWQ_COMPOSE_ALPINE_BASE_IMAGE": "alpine@sha256:" + "2" * 64,
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_provider_runtime_launch_environment",
                    return_value={},
                ),
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(stackctl, "_sync_object_storage_binding_aliases"),
                mock.patch.object(stackctl, "_bind_package_provider_reference_environment"),
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_build_service_image_refs",
                    return_value=composition,
                ),
                mock.patch.object(
                    stackctl,
                    "_build_provider_runtime_images",
                    return_value=provider_images,
                ),
                mock.patch.object(
                    stackctl,
                    "seal_provider_runtime_package_images",
                    return_value={
                        "composition": {
                            "runtimeCompositionDigest": provider_digest
                        },
                        "images": provider_images,
                    },
                ),
                mock.patch.object(stackctl, "target_cache_dir", return_value=root / "cache"),
                mock.patch.object(
                    stackctl,
                    "runtime_shared_deployment_package_dir",
                    return_value=shared,
                ),
                mock.patch.object(
                    stackctl,
                    "provider_binding_overlay_build_inputs",
                    return_value=(
                        root / "overlay",
                        root / "overlay/go.overlay.json",
                        BINDING_MANIFEST_DIGEST,
                    ),
                ),
                mock.patch.object(stackctl, "run", side_effect=inspect_only) as run,
            ):
                _, manifest = stackctl._build_package_bound_local_images(
                    "alpha",
                    "alpha-local",
                    report_dir=root / "report",
                    provider_binding_overlay=_provider_binding_overlay(),
                    provider_runtime=provider_runtime,
                    observability_log_sink=(
                        self._observability_runtime_binding("alpha", root)[
                            "composition"
                        ]
                    ),
                    candidate_root=root,
                    candidate_digest="sha256:" + "a" * 64,
                )

        self.assertEqual(run.call_count, 2)
        self.assertRegex(manifest["buildInputDigest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            set(manifest["images"]),
            {"api-edge", "user-service", "provider-runtime"},
        )

    def test_package_reports_successful_build_output_when_oci_digest_is_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir).resolve()
            shared = root / "runtime-shared"
            shared.mkdir()
            (root / "overlay").mkdir()
            provider_digest = "sha256:" + "d" * 64
            configuration_digest = "sha256:" + "c" * 64
            composition = {
                "imageVersion": "sha256:" + "b" * 64,
                "configurationDigest": configuration_digest,
                "images": {"api-edge": {"ref": "localhost/api-edge:source"}},
            }
            provider_runtime = {
                "composition": {"runtimeCompositionDigest": provider_digest},
                "images": {},
            }

            def bind_build_refs(
                _env_name: str,
                environment: dict[str, str],
                **_kwargs: object,
            ) -> dict[str, object]:
                # The real binder publishes the packaged configuration digest
                # that the image build then freezes as artifact identity.
                environment["LOCAL_GAMMA_CONFIG_VERSION"] = configuration_digest
                return composition

            def missing_after_successful_build(
                argv: list[str],
                *,
                cwd: Path | None = None,
                env: dict[str, str] | None = None,
            ) -> CompletedProcess[str]:
                if argv[:4] == ["docker", "image", "inspect", "--format"]:
                    return CompletedProcess(argv, 1, "", "No such image")
                self.assertEqual(cwd, stackctl.ROOT)
                self.assertIsNotNone(env)
                self.assertEqual(
                    env["QWQ_RELEASE_CANDIDATE_DIGEST"],  # type: ignore[index]
                    "sha256:" + "a" * 64,
                )
                self.assertEqual(argv[:3], ["docker", "build", "--tag"])
                self.assertIn("--file", argv)
                self.assertIn("--build-arg", argv)
                return CompletedProcess(
                    argv,
                    0,
                    "prepared artifacts only\n",
                    "unexpected early-success branch\n",
                )

            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={
                        "QWQ_COMPOSE_GO_BASE_IMAGE": "golang@sha256:" + "1" * 64,
                        "QWQ_COMPOSE_ALPINE_BASE_IMAGE": "alpine@sha256:" + "2" * 64,
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_provider_runtime_launch_environment",
                    return_value={},
                ),
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(stackctl, "_sync_object_storage_binding_aliases"),
                mock.patch.object(stackctl, "_bind_package_provider_reference_environment"),
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_build_service_image_refs",
                    side_effect=bind_build_refs,
                ),
                mock.patch.object(
                    stackctl,
                    "_build_provider_runtime_images",
                    return_value={},
                ),
                mock.patch.object(stackctl, "target_cache_dir", return_value=root / "cache"),
                mock.patch.object(
                    stackctl,
                    "provider_binding_overlay_build_inputs",
                    return_value=(
                        root / "overlay",
                        root / "overlay/go.overlay.json",
                        BINDING_MANIFEST_DIGEST,
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "run",
                    side_effect=missing_after_successful_build,
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "OCI build stdout tail: prepared artifacts only",
                ) as raised:
                    stackctl._build_package_bound_local_images(
                        "alpha",
                        "alpha-local",
                        report_dir=root / "report",
                        provider_binding_overlay=_provider_binding_overlay(),
                        provider_runtime=provider_runtime,
                        observability_log_sink=(
                            self._observability_runtime_binding("alpha", root)[
                                "composition"
                            ]
                        ),
                        candidate_root=root,
                        candidate_digest="sha256:" + "a" * 64,
                    )

        self.assertIn(
            "OCI build stderr tail: unexpected early-success branch",
            str(raised.exception),
        )

    def test_provider_image_tag_changes_with_complete_build_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir).resolve()
            provider_root = root / "provider"
            deploy = provider_root / "deploy"
            deploy.mkdir(parents=True)
            dockerfile = deploy / "Dockerfile"
            dockerfile.write_text("FROM ${GO_BASE_IMAGE}\n", encoding="utf-8")
            source = provider_root / "main.go"
            source.write_text("package main\n", encoding="utf-8")
            compose = deploy / "compose.yaml"
            compose.write_text(
                "services:\n"
                "  provider-runtime:\n"
                "    image: provider-runtime:local\n"
                "    build:\n"
                "      context: ..\n"
                "      dockerfile: deploy/Dockerfile\n"
                "      args:\n"
                "        GO_BASE_IMAGE: ${QWQ_COMPOSE_GO_BASE_IMAGE:?required}\n",
                encoding="utf-8",
            )
            validated = {
                "runtimeCompositionDigest": "sha256:" + "a" * 64,
                "workloads": [
                    {
                        "role": "provider-runtime",
                        "composeRef": "provider/deploy/compose.yaml",
                        "composeDigest": stackctl._sha256_file(compose),
                    }
                ],
            }
            environment = {
                "LOCAL_GAMMA_GO_BASE_IMAGE": "golang@sha256:" + "b" * 64
            }
            with (
                mock.patch.object(stackctl, "ROOT", root),
                mock.patch.object(
                    stackctl,
                    "validate_provider_runtime_composition",
                    return_value=validated,
                ),
            ):
                before = stackctl._provider_runtime_build_specs(
                    {"composition": {"environment": "alpha", "target": "alpha-local"}},
                    environment,
                )[0]
                source.write_text("package main\n// changed\n", encoding="utf-8")
                after = stackctl._provider_runtime_build_specs(
                    {"composition": {"environment": "alpha", "target": "alpha-local"}},
                    environment,
                )[0]

        self.assertNotEqual(before["buildInputDigest"], after["buildInputDigest"])
        self.assertNotEqual(before["ref"], after["ref"])
        self.assertTrue(before["ref"].endswith(before["buildInputDigest"][7:]))

    def test_provider_runtime_projects_exact_image_id_from_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            candidate_root = Path(temporary_dir).resolve()
            compose_path = candidate_root / "packages/provider.compose.yaml"
            compose_path.parent.mkdir(parents=True)
            compose_path.write_text("services: {}\n", encoding="utf-8")
            compose_digest = stackctl._sha256_file(compose_path)
            build_input_digest = "sha256:" + "a" * 64
            image_digest = "sha256:" + "b" * 64
            composition = {
                "environment": "alpha",
                "target": "alpha-local",
            }
            validated = {
                "runtimeCompositionDigest": "sha256:" + "c" * 64,
                "workloads": [
                    {
                        "role": "provider-runtime",
                        "composeProfiles": ["provider-runtime"],
                    }
                ],
            }
            provider_runtime = {
                "composition": composition,
                "workloads": [
                    {
                        "role": "provider-runtime",
                        "composeRef": "packages/provider.compose.yaml",
                        "composeDigest": compose_digest,
                    }
                ],
                "images": {
                    "provider-runtime": {
                        "buildInputDigest": build_input_digest,
                        "ref": (
                            "quwoquan/provider-runtime-provider-runtime:"
                            + build_input_digest.removeprefix("sha256:")
                        ),
                        "imageDigest": image_digest,
                    }
                },
            }
            with mock.patch.object(
                stackctl,
                "validate_provider_runtime_composition",
                return_value=validated,
            ):
                projected = stackctl._provider_runtime_launch_environment(
                    provider_runtime,
                    candidate_root=candidate_root,
                    workload="full",
                )

        self.assertEqual(
            projected["QWQ_PROVIDER_RUNTIME_PROVIDER_RUNTIME_IMAGE"],
            image_digest,
        )
        self.assertEqual(
            projected["QWQ_PROVIDER_RUNTIME_COMPOSE_DIGESTS"],
            compose_digest,
        )
        self.assertNotIn(
            provider_runtime["images"]["provider-runtime"]["ref"],
            projected.values(),
        )

    def test_package_build_never_receives_protected_provider_values(self) -> None:
        environment = {
            "ASSISTANT_MODEL_API_KEY": "protected-real-value",
            "LOCAL_GAMMA_SMS_SUBSTITUTE_PORT": "17080",
        }
        with mock.patch.object(
            stackctl,
            "validate_provider_runtime_composition",
            return_value={
                "materialKeys": {
                    "endpoint": ["ASSISTANT_MODEL_COMPLETION_URL"],
                    "secret": [
                        "ASSISTANT_MODEL_API_KEY",
                        "INTEGRATION_PUSH_APNS_KEY_FILE",
                    ],
                }
            },
        ):
            stackctl._bind_package_provider_reference_environment(
                environment,
                environment_name="alpha",
                runtime_composition={},
            )

        self.assertEqual(
            environment["ASSISTANT_MODEL_COMPLETION_URL"],
            "https://127.0.0.1",
        )
        self.assertEqual(
            environment["ASSISTANT_MODEL_API_KEY"],
            "package-build-not-runtime",
        )
        self.assertEqual(
            environment["INTEGRATION_PUSH_APNS_KEY_FILE"],
            "/tmp/qwq-package-build-not-runtime",
        )

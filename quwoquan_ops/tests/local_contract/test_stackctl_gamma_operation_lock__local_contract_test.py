from __future__ import annotations

import argparse
import contextlib
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from quwoquan_ops.cli import stackctl


class StackctlGammaOperationLockContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.deploy_root = tempfile.TemporaryDirectory()
        self.addCleanup(self.deploy_root.cleanup)
        environment = mock.patch.dict(
            os.environ,
            {"QWQ_DEPLOY_WORK_ROOT": str(Path(self.deploy_root.name) / "deploy")},
        )
        environment.start()
        self.addCleanup(environment.stop)
        availability = mock.patch.object(
            stackctl,
            "assert_local_runtime_available",
        )
        self.availability = availability.start()
        self.addCleanup(availability.stop)
        package_reuse = mock.patch.object(
            stackctl,
            "can_reuse_package",
            return_value=(True, "fixed candidate ready"),
        )
        self.package_reuse = package_reuse.start()
        self.addCleanup(package_reuse.stop)
        tls = mock.patch.object(
            stackctl,
            "tls_profile",
            return_value=("local-managed", "local-managed", {}),
        )
        tls.start()
        self.addCleanup(tls.stop)
        certificate = mock.patch.object(
            stackctl,
            "verify_certificate",
            return_value={"target": "local", "status": "ready"},
        )
        certificate.start()
        self.addCleanup(certificate.stop)
        handoff = mock.patch.object(
            stackctl,
            "materialize_handoff",
            return_value={"target": "local", "status": "ready"},
        )
        handoff.start()
        self.addCleanup(handoff.stop)

    def test_bounded_content_workloads_do_not_materialize_unrelated_providers(
        self,
    ) -> None:
        auth = mock.Mock(environment={"AUTH_JWT_SECRET": "protected"})
        storage = mock.Mock(
            environment={"LOCAL_GAMMA_OBJECT_STORAGE_BUCKET": "alpha-bucket"},
            host_endpoint="https://upload.alpha.quwoquan.com:17100",
        )
        topology = {
            "targets": {
                "alpha-local": {
                    "portProfile": "alpha-local",
                    "publicBases": {
                        "mediaImage": "https://cdn.alpha.quwoquan.com:17100/media/image",
                        "mediaUpload": "https://upload.alpha.quwoquan.com:17100/media/upload",
                    },
                }
            }
        }
        for workload in ("content-release", "content-commercial"):
            environment: dict[str, str] = {}
            with self.subTest(workload=workload):
                with (
                    mock.patch.object(
                        stackctl,
                        "prepare_local_environment_auth",
                        return_value=auth,
                    ),
                    mock.patch.object(
                        stackctl,
                        "prepare_local_environment_object_storage",
                        return_value=storage,
                    ),
                    mock.patch.object(
                        stackctl,
                        "load_environment_topology",
                        return_value=topology,
                    ),
                    mock.patch.object(stackctl, "load_port_manifest", return_value={}),
                    mock.patch.object(
                        stackctl,
                        "profile_ports",
                        return_value={"object-storage-edge": 17100},
                    ),
                    mock.patch.object(stackctl, "_sync_object_storage_binding_aliases"),
                    mock.patch.object(
                        stackctl,
                        "_bind_local_external_provider_environment",
                    ) as bind_external,
                ):
                    error = stackctl._bind_formal_local_release_provider_environment(
                        environment,
                        environment_name="alpha",
                        target_name="alpha-local",
                        workload=workload,
                    )

                self.assertIsNone(error)
                self.assertEqual(environment["AUTH_JWT_SECRET"], "protected")
                bind_external.assert_not_called()

    def test_package_lock_serializes_one_target_and_allows_other_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            entered = threading.Event()

            def deployment_path(target: str, *parts: str) -> Path:
                return root / target / Path(*parts)

            def enter_same_target() -> None:
                with stackctl._target_package_lock("alpha-local"):
                    entered.set()

            with mock.patch.object(
                stackctl,
                "deployment_target_path",
                side_effect=deployment_path,
            ):
                with stackctl._target_package_lock("alpha-local"):
                    worker = threading.Thread(target=enter_same_target)
                    worker.start()
                    self.assertFalse(entered.wait(0.1))
                    with stackctl._target_package_lock("beta-local"):
                        pass
                self.assertTrue(entered.wait(1.0))
                worker.join(timeout=1.0)

        self.assertFalse(worker.is_alive())

    def test_gamma_down_parse_inputs_do_not_synthesize_image_identity(self) -> None:
        environment: dict[str, str] = {}

        stackctl._bind_gamma_down_parse_environment(environment)

        for suffix in (
            "ENDPOINT",
            "BUCKET",
            "REGION",
            "ACCESS_KEY_ID",
            "ACCESS_KEY_SECRET",
            "CDN_SIGN_KEY",
            "TLS_DIR",
        ):
            source = environment[f"LOCAL_GAMMA_OBJECT_STORAGE_{suffix}"]
            alias = environment[f"QWQ_COMPOSE_OBJECT_STORAGE_{suffix}"]
            self.assertTrue(source)
            self.assertEqual(alias, source)
        self.assertNotIn("LOCAL_GAMMA_IMAGE_VERSION", environment)
        self.assertNotIn("QWQ_COMPOSE_IMAGE_VERSION", environment)
        self.assertEqual(environment["RTC_MEDIA_API_KEY"], "down-not-used")
        self.assertEqual(environment["RTC_MEDIA_API_SECRET"], "down-not-used")
        for service, local_key in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
            self.assertNotIn(local_key, environment, service)
            self.assertNotIn(
                stackctl.compose_image_environment_key(service),
                environment,
                service,
            )

    def test_gamma_down_runtime_receipt_preserves_exact_started_composition(
        self,
    ) -> None:
        refs = {
            service: (
                f"localhost/quwoquan_service_{service.replace('-', '_')}:"
                + f"{index:064x}"
            )
            for index, (service, _) in enumerate(
                stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS,
                start=1,
            )
        }
        version = stackctl.immutable_image_digest(refs)
        configuration_digest = "sha256:" + "f" * 64
        composition = {
            "imageVersion": version,
            "images": {
                service: {"ref": ref}
                for service, ref in refs.items()
            },
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            process_dir = Path(temporary_dir)
            (process_dir / "stack_status.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "runtimeEnv": "gamma",
                        "composeProject": "quwoquan_gamma_release_old_1",
                        "configurationDigest": configuration_digest,
                        "imageTransportTag": version,
                        "imageComposition": composition,
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "startup_attempt_path",
                    return_value=process_dir / "startup_attempt.json",
                ),
                mock.patch.object(
                    stackctl,
                    "target_process_dir",
                    return_value=process_dir,
                ),
            ):
                loaded = stackctl._load_gamma_runtime_image_composition(
                    "gamma-local"
                )

        expected_composition = dict(composition)
        expected_composition["configurationDigest"] = configuration_digest
        self.assertEqual(
            loaded,
            (expected_composition, "quwoquan_gamma_release_old_1"),
        )

    def test_gamma_down_rejects_runtime_receipt_from_other_environment_project(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            process_dir = Path(temporary_dir)
            (process_dir / "stack_status.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "runtimeEnv": "gamma",
                        "composeProject": "quwoquan_beta_release_old_1",
                        "configurationDigest": "sha256:" + "f" * 64,
                        "imageTransportTag": "unused",
                        "imageComposition": {"images": {}},
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "startup_attempt_path",
                    return_value=process_dir / "startup_attempt.json",
                ),
                mock.patch.object(
                    stackctl,
                    "target_process_dir",
                    return_value=process_dir,
                ),
                self.assertRaisesRegex(ValueError, "Compose project mismatch"),
            ):
                stackctl._load_gamma_runtime_image_composition("gamma-local")

    def test_stopped_attempt_falls_back_to_successful_runtime_receipt(self) -> None:
        refs = {
            service: (
                f"localhost/quwoquan_service_{service.replace('-', '_')}:"
                + f"{index:064x}"
            )
            for index, (service, _) in enumerate(
                stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS,
                start=1,
            )
        }
        version = stackctl.immutable_image_digest(refs)
        with tempfile.TemporaryDirectory() as temporary_dir:
            process_dir = Path(temporary_dir)
            attempt = process_dir / "startup_attempt.json"
            attempt.write_text(json.dumps({"status": "stopped"}), encoding="utf-8")
            (process_dir / "stack_status.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "runtimeEnv": "alpha",
                        "composeProject": "quwoquan_alpha_release_old_1",
                        "configurationDigest": "sha256:" + "f" * 64,
                        "imageTransportTag": version,
                        "imageComposition": {
                            "imageVersion": version,
                            "images": {
                                service: {"ref": ref}
                                for service, ref in refs.items()
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "startup_attempt_path",
                    return_value=attempt,
                ),
                mock.patch.object(
                    stackctl,
                    "target_process_dir",
                    return_value=process_dir,
                ),
            ):
                loaded = stackctl._load_gamma_runtime_image_composition(
                    "alpha-local"
                )

        self.assertEqual(loaded[1], "quwoquan_alpha_release_old_1")

    def test_gamma_down_rejects_drifted_runtime_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            process_dir = Path(temporary_dir)
            (process_dir / "stack_status.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "runtimeEnv": "gamma",
                        "composeProject": "quwoquan_gamma_release_old_1",
                        "imageTransportTag": "0.1.2",
                        "imageComposition": {
                            "imageVersion": "0.1.2",
                            "images": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "startup_attempt_path",
                    return_value=process_dir / "startup_attempt.json",
                ),
                mock.patch.object(
                    stackctl,
                    "target_process_dir",
                    return_value=process_dir,
                ),
                self.assertRaisesRegex(ValueError, "composition is missing"),
            ):
                stackctl._load_gamma_runtime_image_composition("gamma-local")

    def test_gamma_down_materializes_compose_bindings_before_interpolation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            compose_environment = {"GAMMA_PORT": "19000"}

            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "gamma"},
                ),
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value=compose_environment,
                ),
                mock.patch.object(
                    stackctl,
                    "_load_gamma_runtime_image_composition",
                    return_value=None,
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_packaged_service_image_refs",
                    side_effect=lambda _environment_name, environment: environment.update(
                        {
                            "LOCAL_GAMMA_IMAGE_VERSION": "0.1.2",
                            "QWQ_COMPOSE_IMAGE_VERSION": "0.1.2",
                        }
                    ),
                ) as bind_composition,
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_down_parse_environment",
                    side_effect=lambda environment: environment.update(
                        {"QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_ID": "unused"}
                    ),
                ) as bind_environment,
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ) as run,
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_network_report",
                    return_value={"ports": []},
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(
                    argparse.Namespace(
                        target="gamma-local",
                        report_dir="",
                    )
                )

        self.assertEqual(result["exitCode"], 0)
        bind_composition.assert_called_once_with("gamma", compose_environment)
        bind_environment.assert_called_once_with(compose_environment)
        self.assertEqual(
            run.call_args_list[0].kwargs["env"][
                "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_ID"
            ],
            "unused",
        )

    def test_alpha_down_stops_release_and_app_runtimes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ) as run,
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={
                        "QWQ_LOCAL_RELEASE_ENV": "alpha",
                        "QWQ_LOCAL_RELEASE_TARGET": "alpha-local",
                        "LOCAL_GAMMA_COMPOSE_PROJECT_NAME": "quwoquan_alpha_release_new_2",
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_load_gamma_runtime_image_composition",
                    return_value=(
                        {"images": {}},
                        "quwoquan_alpha_release_old_1",
                    ),
                ),
                mock.patch.object(stackctl, "_apply_gamma_image_composition"),
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_network_report",
                    return_value={"ports": []},
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(
                    argparse.Namespace(
                        target="alpha-local",
                        report_dir="",
                    )
                )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(
            run.call_args_list[0].kwargs["env"][
                "LOCAL_GAMMA_COMPOSE_PROJECT_NAME"
            ],
            "quwoquan_alpha_release_old_1",
        )
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                [
                    "bash",
                    "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
                    "--down",
                ],
                [
                    "bash",
                    "quwoquan_app/scripts/device/stop_app_instance.sh",
                    "--env",
                    "alpha",
                    "--quiet",
                ],
            ],
        )

    def test_alpha_down_purges_only_runtime_receipt_bound_compose_volumes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            target_cache = Path(temporary_dir) / "target-cache"
            target_cache.mkdir()
            environment = {
                "QWQ_LOCAL_RELEASE_ENV": "alpha",
                "QWQ_LOCAL_RELEASE_TARGET": "alpha-local",
                "LOCAL_GAMMA_COMPOSE_PROJECT_NAME": "quwoquan_alpha_release_new_2",
            }
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "alpha"},
                ),
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value=environment,
                ),
                mock.patch.object(
                    stackctl,
                    "_load_gamma_runtime_image_composition",
                    return_value=(
                        {"images": {}},
                        "quwoquan_alpha_release_old_1",
                    ),
                ),
                mock.patch.object(stackctl, "_apply_gamma_image_composition"),
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ) as run,
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_network_report",
                    return_value={"ports": []},
                ),
                mock.patch.object(
                    stackctl,
                    "target_cache_dir",
                    return_value=target_cache,
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(
                    argparse.Namespace(
                        target="alpha-local",
                        report_dir="",
                        formal_release=False,
                        purge_rebuildable_state=True,
                    )
                )
            report = json.loads((report_dir / "report.json").read_text())

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(
            run.call_args_list[0].args[0],
            [
                "bash",
                "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
                "--down",
                "--purge-rebuildable-state",
            ],
        )
        self.assertEqual(
            run.call_args_list[0].kwargs["env"][
                "LOCAL_GAMMA_COMPOSE_PROJECT_NAME"
            ],
            "quwoquan_alpha_release_old_1",
        )
        self.assertTrue(report["destructiveRepairPerformed"])
        self.assertEqual(
            report["destructiveActions"],
            [
                "purge-compose-volumes:quwoquan_alpha_release_old_1",
                "purge-target-cache:alpha-local",
            ],
        )
        self.assertFalse(target_cache.exists())

    def test_alpha_down_fails_when_canonical_port_remains_occupied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={
                        "QWQ_LOCAL_RELEASE_ENV": "alpha",
                        "QWQ_LOCAL_RELEASE_TARGET": "alpha-local",
                        "LOCAL_GAMMA_COMPOSE_PROJECT_NAME": "quwoquan_alpha_release",
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_load_gamma_runtime_image_composition",
                    return_value=({"images": {}}, "quwoquan_alpha_release"),
                ),
                mock.patch.object(stackctl, "_apply_gamma_image_composition"),
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(
                    stackctl,
                    "_wait_for_network_ports_released",
                    return_value=[
                        {"name": "media-origin", "port": 17110, "open": True}
                    ],
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(
                    argparse.Namespace(target="alpha-local", report_dir="")
                )

        self.assertEqual(result["exitCode"], 2)
        self.assertIn("canonical port remains occupied", result["details"][0])

    def test_down_waits_for_host_port_forward_release(self) -> None:
        reports = iter(
            [
                {"ports": [{"name": "mongodb", "port": 17410, "open": True}]},
                {"ports": [{"name": "mongodb", "port": 17410, "open": False}]},
            ]
        )
        with (
            mock.patch.object(stackctl, "_network_report", side_effect=reports),
            mock.patch.object(stackctl.time, "sleep") as sleep,
        ):
            occupied = stackctl._wait_for_network_ports_released(
                "alpha-local",
                timeout_seconds=1.0,
                poll_interval_seconds=0.01,
            )

        self.assertEqual(occupied, [])
        sleep.assert_called_once_with(0.01)

    def test_orphan_repair_requires_explicit_confirmation(self) -> None:
        args = argparse.Namespace(
            target="alpha-local",
            fix="reclaim-orphaned-processes",
            confirm_orphaned_process_reclaim=False,
            report_dir="",
        )
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary_dir),
            ),
            mock.patch.object(stackctl, "_write_summary_bundle"),
            mock.patch.object(
                stackctl.alpha_content_release_runtime,
                "reclaim_orphaned_managed_processes",
                side_effect=RuntimeError("explicit confirmation required"),
            ) as reclaim,
        ):
            result = stackctl.command_repair(args)

        self.assertEqual(result["exitCode"], 2)
        reclaim.assert_called_once_with(confirm=False)

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

    def test_reclaim_build_cache_only_prunes_unused_builder_cache(self) -> None:
        args = argparse.Namespace(
            target="gamma-local",
            fix="reclaim-build-cache",
            report_dir="",
        )
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary_dir),
            ),
            mock.patch.object(stackctl, "_write_summary_bundle"),
            mock.patch.object(stackctl, "run") as run,
        ):
            run.side_effect = [
                CompletedProcess(["docker", "system", "df"], 0, "before", ""),
                CompletedProcess(
                    ["docker", "builder", "prune", "--all", "--force"],
                    0,
                    "reclaimed",
                    "",
                ),
                CompletedProcess(["docker", "system", "df"], 0, "after", ""),
            ]
            payload = stackctl.command_repair(args)

        self.assertEqual(payload["exitCode"], 0)
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["docker", "system", "df"],
                ["docker", "builder", "prune", "--all", "--force"],
                ["docker", "system", "df"],
            ],
        )

    def test_reclaim_build_cache_accepts_failed_pre_inventory_after_recovery(
        self,
    ) -> None:
        args = argparse.Namespace(
            target="gamma-local",
            fix="reclaim-build-cache",
            report_dir="",
        )
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary_dir),
            ),
            mock.patch.object(stackctl, "_write_summary_bundle"),
            mock.patch.object(stackctl, "run") as run,
        ):
            run.side_effect = [
                CompletedProcess(
                    ["docker", "system", "df"],
                    1,
                    "",
                    "no space left on device",
                ),
                CompletedProcess(
                    ["docker", "builder", "prune", "--all", "--force"],
                    0,
                    "reclaimed",
                    "",
                ),
                CompletedProcess(
                    ["docker", "system", "df"],
                    0,
                    "Build Cache 0B",
                    "",
                ),
            ]
            payload = stackctl.command_repair(args)

        self.assertEqual(payload["exitCode"], 0)
        self.assertEqual(
            payload["summary"],
            "gamma-local unused Docker build cache reclaimed",
        )

    def test_reclaim_build_cache_is_available_from_each_local_target(self) -> None:
        for target in ("alpha-local", "beta-local", "gamma-local"):
            args = argparse.Namespace(
                target=target,
                fix="reclaim-build-cache",
                report_dir="",
            )
            with (
                self.subTest(target=target),
                tempfile.TemporaryDirectory() as temporary_dir,
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=Path(temporary_dir),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "run") as run,
            ):
                run.side_effect = [
                    CompletedProcess(
                        ["docker", "system", "df"],
                        0,
                        "before",
                        "",
                    ),
                    CompletedProcess(
                        ["docker", "builder", "prune", "--all", "--force"],
                        0,
                        "reclaimed",
                        "",
                    ),
                    CompletedProcess(
                        ["docker", "system", "df"],
                        0,
                        "after",
                        "",
                    ),
                ]
                payload = stackctl.command_repair(args)

            self.assertEqual(payload["exitCode"], 0)
            self.assertEqual(
                payload["summary"],
                f"{target} unused Docker build cache reclaimed",
            )

    def test_gamma_lock_rejects_overlapping_stack_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            process_dir = Path(temporary_dir) / "process"
            with mock.patch.object(
                stackctl,
                "local_runtime_operation_lock_path",
                return_value=process_dir / ".stackctl-operation.lock",
            ):
                with stackctl._local_stack_operation_lock("gamma-local"):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "local stack operation is already running",
                    ):
                        with stackctl._local_stack_operation_lock("beta-local"):
                            pass

            lock_path = process_dir / ".stackctl-operation.lock"
            self.assertTrue(lock_path.is_file())
            self.assertEqual(lock_path.read_text(encoding="utf-8"), "")

    def test_beta_up_rejects_overlapping_stack_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            args = argparse.Namespace(
                env="beta",
                target=None,
                workload="content-release",
                skip_app=True,
                skip_build=False,
                build_only=False,
                build_services="",
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
                    "_local_stack_operation_lock",
                    side_effect=RuntimeError(
                        "local stack operation is already running: pid=42 target=gamma-local",
                    ),
                ) as operation_lock,
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(stackctl, "run") as run,
            ):
                result = stackctl.command_up(args)

            self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["summary"], "stackctl up is GATE_BLOCK for beta")
        self.assertIn(
            "wait for the active operation or stop the conflicting local runtime",
            result["details"],
        )
        operation_lock.assert_called_once_with("beta-local")
        run.assert_not_called()

    def test_alpha_full_workload_requires_fixed_package_without_reading_run_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            telemetry = mock.Mock(environment={})
            telemetry.redacted_receipt.return_value = {
                "source": "test",
                "status": "ready",
                "redactedDigest": "sha256:" + "a" * 64,
            }
            args = argparse.Namespace(
                env="alpha",
                target=None,
                workload="full",
                skip_app=True,
                skip_build=True,
                formal_release=False,
                release_manifest="",
                build_only=False,
                build_services="",
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
                    "can_reuse_package",
                    return_value=(False, "candidate fingerprint mismatch"),
                ),
                mock.patch.object(
                    stackctl,
                    "probe_migration_drift",
                    return_value=mock.Mock(has_drift=False),
                ),
                mock.patch.object(
                    stackctl,
                    "load_product_telemetry_log_sink",
                    return_value=telemetry,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_local_runtime_log_root",
                    side_effect=AssertionError(
                        "unsupported workload must not read local run state"
                    ),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(stackctl, "run") as run,
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertIn(
            "candidate fingerprint mismatch",
            "\n".join(result["details"]),
        )
        run.assert_not_called()

    def test_beta_down_rejects_active_patrol_runtime_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            args = argparse.Namespace(target="beta-local", report_dir="")
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    side_effect=RuntimeError(
                        "local stack operation is already running: "
                        "pid=42 target=beta-local purpose=environment-patrol-smoke"
                    ),
                ) as operation_lock,
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(stackctl, "run") as run,
            ):
                result = stackctl.command_down(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            result["summary"],
            "stackctl down is GATE_BLOCK for beta-local",
        )
        self.assertIn(
            "wait for the active Patrol/UAT runtime lease to finish",
            result["details"],
        )
        operation_lock.assert_called_once_with("beta-local")
        run.assert_not_called()

    def test_beta_up_releases_operation_lock_when_alpha_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            args = argparse.Namespace(
                env="beta",
                target=None,
                workload="content-release",
                skip_app=True,
                skip_build=False,
                build_only=False,
                build_services="",
                device_id="",
            )
            operation_lock = mock.MagicMock()
            operation_lock.__enter__.return_value = None
            self.availability.side_effect = RuntimeError(
                "beta-local cannot start while local runtime alpha-local is active"
            )
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=operation_lock,
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(stackctl, "run") as run,
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        operation_lock.__exit__.assert_called_once()
        run.assert_not_called()

    def test_beta_external_provider_environment_binds_substitute_topology(self) -> None:
        environment: dict[str, str] = {}
        values = {
            "CONTENT_EMBEDDING_ENDPOINT": (
                "http://integration-service:18089/v1/embeddings"
            ),
        }
        with mock.patch.object(
            stackctl,
            "load_nonprod_provider_environment",
            return_value=values,
        ):
            error = stackctl._bind_beta_external_provider_environment(environment)

        self.assertIsNone(error)
        self.assertIn("CONTENT_EMBEDDING_ENDPOINT", environment)
        self.assertEqual(
            environment["QWQ_COMPOSE_EMBEDDING_ENDPOINT"],
            values["CONTENT_EMBEDDING_ENDPOINT"],
        )
        self.assertNotIn("QWQ_COMPOSE_EMBEDDING_API_KEY", environment)

    def test_beta_full_workload_blocks_when_provider_materialization_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            args = argparse.Namespace(
                env="beta",
                target=None,
                workload="full",
                skip_app=True,
                skip_build=False,
                build_only=False,
                build_services="",
                device_id="",
            )
            telemetry = mock.Mock()
            telemetry.redacted_receipt.return_value = {
                "source": "service-config-postgres-telemetry",
                "status": "ready",
                "redactedDigest": "digest",
            }
            telemetry.environment = {}
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "load_product_telemetry_log_sink",
                    return_value=telemetry,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "_optional_product_telemetry_environment",
                    return_value=({}, ""),
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_formal_local_release_provider_environment",
                    return_value=(
                        "beta-local external provider materialization failed: boom"
                    ),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, "", ""),
                ) as run,
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertIn(
            "external provider materialization failed",
            "\n".join(result["details"]),
        )
        run.assert_called_once()

    def test_beta_content_release_blocks_when_provider_materialization_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            args = argparse.Namespace(
                env="beta",
                target=None,
                workload="content-release",
                skip_app=True,
                skip_build=False,
                build_only=False,
                build_services="",
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
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "_optional_product_telemetry_environment",
                    return_value=({}, ""),
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_formal_local_release_provider_environment",
                    return_value=(
                        "beta-local external provider materialization failed: boom"
                    ),
                ) as bind_release_providers,
                mock.patch.object(
                    stackctl,
                    "_run_with_live_output",
                    return_value=CompletedProcess([], 0, "", ""),
                ) as run,
                mock.patch.object(
                    stackctl,
                    "_tail_multiple_logs_for_startup",
                    return_value={},
                ),
                mock.patch.object(stackctl, "canonical_port", return_value=18080),
                mock.patch.object(
                    stackctl,
                    "fetch_url",
                    return_value=(True, 200, "{}", "application/json"),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertIn(
            "external provider materialization failed",
            "\n".join(result["details"]),
        )
        bind_release_providers.assert_called_once_with(
            mock.ANY,
            environment_name="beta",
            target_name="beta-local",
            workload="content-release",
        )
        run.assert_not_called()

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
                mock.patch.object(stackctl, "_gamma_env_from_port_manifest", return_value={}),
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
                mock.patch.object(stackctl, "_gamma_env_from_port_manifest", return_value={}),
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(stackctl, "_sync_object_storage_binding_aliases"),
                mock.patch.object(stackctl, "_bind_package_provider_reference_environment"),
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_build_service_image_refs",
                    return_value=composition,
                ),
                mock.patch.object(stackctl, "target_cache_dir", return_value=root / "cache"),
                mock.patch.object(
                    stackctl,
                    "runtime_shared_deployment_package_dir",
                    return_value=shared,
                ),
                mock.patch.object(stackctl, "run", side_effect=inspect_only) as run,
            ):
                _, manifest = stackctl._build_package_bound_local_images(
                    "alpha",
                    "alpha-local",
                    report_dir=root / "report",
                )

        self.assertEqual(run.call_count, 2)
        self.assertEqual(manifest["buildInputDigest"], composition["imageVersion"])
        self.assertEqual(set(manifest["images"]), {"api-edge", "user-service"})

    def test_package_build_never_receives_protected_provider_values(self) -> None:
        environment = {"ASSISTANT_MODEL_API_KEY": "protected-real-value"}
        with mock.patch.object(
            stackctl,
            "provider_environment_reference_names",
            return_value=(
                frozenset({"ASSISTANT_MODEL_COMPLETION_URL"}),
                frozenset(
                    {
                        "ASSISTANT_MODEL_API_KEY",
                        "INTEGRATION_PUSH_APNS_KEY_FILE",
                    }
                ),
            ),
        ):
            stackctl._bind_package_provider_reference_environment(
                environment,
                environment_name="alpha",
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

    def test_gamma_build_binds_all_compose_service_images_to_package_provenance(self) -> None:
        environment: dict[str, str] = {}
        with (
            mock.patch.object(
                stackctl,
                "_packaged_service_source_image_ref",
                side_effect=lambda _env_name, service: (
                    f"localhost/quwoquan_service_{service.replace('-', '_')}:"
                    + "a" * 64
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
            expected = (
                f"localhost/quwoquan_service_{service.replace('-', '_')}:"
                + "a" * 64
            )
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
            shared = Path(temporary_dir)
            build_refs = {
                service: f"localhost/{service}:build"
                for service, _ in stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
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
            environment = {"QWQ_LOCAL_RELEASE_TARGET": "gamma-local"}
            with (
                mock.patch.object(
                    stackctl,
                    "runtime_shared_deployment_package_dir",
                    return_value=shared,
                ),
                mock.patch.object(
                    stackctl,
                    "_packaged_service_source_image_ref",
                    side_effect=lambda _env, service: build_refs[service],
                ),
                mock.patch.object(
                    stackctl,
                    "packaged_configuration_digest",
                    return_value="sha256:" + "c" * 64,
                ),
            ):
                composition = stackctl._bind_gamma_packaged_service_image_refs(
                    "gamma",
                    environment,
                )

            self.assertEqual(composition["imageDigest"], image_set_digest)
            for service, environment_key in (
                stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
            ):
                self.assertEqual(
                    environment[environment_key],
                    images[service]["imageDigest"],
                )
                self.assertNotEqual(environment[environment_key], build_refs[service])

    def test_gamma_external_provider_environment_binds_substitute_topology(
        self,
    ) -> None:
        environment: dict[str, str] = {}
        storage = mock.Mock(
            environment={
                "LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT": "https://minio:19000",
            },
            host_endpoint="https://upload.gamma.quwoquan.com:19000",
        )
        values = {
            "RTC_MEDIA_CONNECTION_URL": "wss://rtc.nonprod.test",
            "RTC_MEDIA_API_KEY": "rtc-key",
            "RTC_MEDIA_API_SECRET": "rtc-secret",
        }
        with (
            mock.patch.object(
                stackctl,
                "prepare_local_gamma_object_storage",
                return_value=storage,
            ),
            mock.patch.object(
                stackctl,
                "load_nonprod_provider_environment",
                return_value=values,
            ) as prepare,
        ):
            error = stackctl._bind_gamma_external_provider_environment(environment)

        self.assertIsNone(error)
        prepare.assert_called_once_with(
            environment="gamma",
            target_name="gamma-local",
            source=environment,
        )
        self.assertEqual(
            environment["CONTENT_OSS_ENDPOINT"],
            storage.environment["LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT"],
        )
        self.assertNotIn("CONTENT_OSS_CA_FILE", environment)
        self.assertEqual(
            environment["QWQ_COMPOSE_OBJECT_STORAGE_ENDPOINT"],
            storage.environment["LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT"],
        )
        self.assertEqual(
            environment["LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL"],
            storage.host_endpoint,
        )
        self.assertEqual(
            environment["CONTENT_MEDIA_DELIVERY_BASE_URL"],
            "https://cdn.gamma.quwoquan.com:19100",
        )
        self.assertEqual(
            environment["CONTENT_MEDIA_UPLOAD_BASE_URL"],
            "https://upload.gamma.quwoquan.com:19130",
        )
        self.assertNotIn("QWQ_COMPOSE_EMBEDDING_ENDPOINT", environment)
        self.assertNotIn("QWQ_COMPOSE_EMBEDDING_API_KEY", environment)
        self.assertIn("RTC_MEDIA_API_KEY", environment)
        self.assertNotIn("PRODUCT_OPS_SLS_ENDPOINT", environment)
        self.assertNotIn("ALIBABA_CLOUD_ACCESS_KEY_ID", environment)

    def test_gamma_external_provider_environment_reports_materialization_failure(
        self,
    ) -> None:
        with mock.patch.object(
            stackctl,
            "prepare_local_gamma_object_storage",
            side_effect=RuntimeError("materializer unavailable"),
        ):
            error = stackctl._bind_gamma_external_provider_environment({})

        self.assertIn(
            "gamma-local object storage materialization failed",
            error or "",
        )

    def test_gamma_full_workload_uses_fixed_package_and_materializes_providers(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            work_root = Path(temporary_dir) / "deploy-work"
            argv_calls: list[list[str]] = []

            def successful_syntax_check(
                argv: list[str],
                *,
                env: dict[str, str] | None = None,
            ) -> CompletedProcess[str]:
                del env
                argv_calls.append(argv)
                return CompletedProcess(argv, 0, stdout="", stderr="")

            args = argparse.Namespace(
                env="gamma",
                target=None,
                workload="full",
                skip_app=True,
                skip_build=True,
                build_only=False,
                build_services="",
                device_id="",
                rollout_mode="",
            )
            telemetry = mock.Mock()
            telemetry.environment = {
                "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT": "http://elasticsearch:9200",
            }
            telemetry.redacted_receipt.return_value = {
                "source": "gamma-local-elasticsearch-topology",
                "status": "ready",
                "redactedDigest": "digest",
            }
            with (
                mock.patch.dict(
                    os.environ,
                    {"QWQ_DEPLOY_WORK_ROOT": str(work_root)},
                    clear=False,
                ),
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(stackctl, "_gamma_env_from_port_manifest", return_value={}),
                mock.patch.object(
                    stackctl,
                    "_optional_product_telemetry_environment",
                    return_value=({}, ""),
                ),
                mock.patch.object(
                    stackctl,
                    "load_product_telemetry_log_sink",
                    return_value=telemetry,
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_formal_local_release_provider_environment",
                    return_value=None,
                ) as bind_release_providers,
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_packaged_service_image_refs",
                    return_value={
                        "imageVersion": "sha256:" + "a" * 64,
                        "images": {},
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "activate_search_experiment_policy",
                    return_value={"status": "passed"},
                ),
                mock.patch.object(stackctl, "run", side_effect=successful_syntax_check),
                mock.patch.object(
                    stackctl,
                    "_run_with_live_output",
                    return_value=CompletedProcess(["gamma-start"], 0, stdout="", stderr=""),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 0, result)
        self.assertTrue(
            any("package" in " ".join(argv) for argv in argv_calls)
            or any("start_local_gamma_mirror" in " ".join(argv) for argv in argv_calls)
        )
        bind_release_providers.assert_called_once_with(
            mock.ANY,
            environment_name="gamma",
            target_name="gamma-local",
            workload="full",
        )

    def test_gamma_build_only_is_retired_from_up(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            args = argparse.Namespace(
                env="gamma",
                target=None,
                workload="full",
                skip_app=True,
                skip_build=False,
                build_only=True,
                build_services="assistant-service",
                device_id="",
                rollout_mode="",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={},
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
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_object_storage_environment",
                    return_value=None,
                ) as bind_object_storage,
                mock.patch.object(
                    stackctl,
                    "_bind_formal_local_release_provider_environment",
                ) as bind_external_provider,
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_packaged_service_image_refs",
                ),
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ),
                mock.patch.object(
                    stackctl,
                    "_run_with_live_output",
                    return_value=CompletedProcess([], 0, stdout="", stderr=""),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertIn("build-only is retired", result["summary"])
        bind_object_storage.assert_not_called()
        bind_external_provider.assert_not_called()

    def test_gamma_content_release_blocks_when_provider_materialization_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir) / "report"
            argv_calls: list[list[str]] = []

            def successful_syntax_check(
                argv: list[str],
                *,
                env: dict[str, str] | None = None,
            ) -> CompletedProcess[str]:
                del env
                argv_calls.append(argv)
                return CompletedProcess(argv, 0, stdout="", stderr="")

            args = argparse.Namespace(
                env="gamma",
                target=None,
                workload="content-release",
                skip_app=True,
                skip_build=True,
                build_only=False,
                build_services="",
                device_id="",
                rollout_mode="",
            )
            with (
                mock.patch.object(
                    stackctl,
                    "resolve_report_dir",
                    return_value=report_dir,
                ),
                mock.patch.object(stackctl, "_gamma_env_from_port_manifest", return_value={}),
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
                mock.patch.object(
                    stackctl,
                    "_bind_formal_local_release_provider_environment",
                    return_value=(
                        "gamma-local external provider materialization failed: "
                        "fixture service unavailable"
                    ),
                ) as bind_external_provider,
                mock.patch.object(
                    stackctl,
                    "_bind_gamma_packaged_service_image_refs",
                ),
                mock.patch.object(stackctl, "run", side_effect=successful_syntax_check),
                mock.patch.object(
                    stackctl,
                    "_run_with_live_output",
                    return_value=CompletedProcess(["gamma-start"], 0, stdout="", stderr=""),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_up(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            argv_calls,
            [["bash", "-n", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"]],
        )
        self.assertIn(
            "materialization failed",
            "\n".join(result["details"]),
        )
        bind_external_provider.assert_called_once()

    def test_gamma_build_only_cli_forwards_requested_service_slice(self) -> None:
        args = stackctl.build_parser().parse_args(
            [
                "up",
                "--env",
                "gamma",
                "--build-only",
                "--build-services",
                "chat-service,user-service",
                "--workload",
                "content-release",
            ]
        )

        self.assertTrue(args.build_only)
        self.assertEqual(args.build_services, "chat-service,user-service")
        self.assertEqual(
            stackctl._gamma_start_command(args),
            [
                "bash",
                "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
                "--build-only",
                "--build-services",
                "chat-service,user-service",
            ],
        )

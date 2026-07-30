from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl


DIGEST = "sha256:" + "a" * 64


def completed(returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout="", stderr="")


class PreprodFormalReleaseRuntimeTest(unittest.TestCase):
    def test_alpha_beta_topology_projection_has_no_auth_side_effect(self) -> None:
        topology = stackctl.load_environment_topology()
        for environment_name in ("alpha", "beta"):
            target_name = f"{environment_name}-local"
            with (
                self.subTest(target=target_name),
                mock.patch.object(
                    stackctl,
                    "prepare_local_environment_auth",
                    return_value=mock.Mock(environment={"AUTH": target_name}),
                ) as prepare_auth,
            ):
                environment = stackctl._gamma_env_from_port_manifest(
                    topology,
                    target_name,
                )
            prepare_auth.assert_not_called()
            self.assertEqual(environment["QWQ_LOCAL_RELEASE_ENV"], environment_name)
            self.assertEqual(environment["QWQ_LOCAL_RELEASE_TARGET"], target_name)
            self.assertEqual(
                environment["LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS"], "420"
            )
            self.assertIn(environment_name, environment["LOCAL_GAMMA_COMPOSE_PROJECT_NAME"])
            self.assertNotIn("AUTH", environment)

    def test_alpha_and_beta_formal_up_share_exact_candidate_path(self) -> None:
        composition = {
            "candidateId": DIGEST,
            "artifactDigest": "sha256:" + "b" * 64,
            "images": {"content-service": {"ref": "exact", "digest": DIGEST}},
        }
        telemetry = mock.Mock(environment={})
        telemetry.redacted_receipt.return_value = {
            "source": "service-config-postgres-telemetry",
            "status": "ready",
            "redactedDigest": DIGEST,
        }
        for target_name in ("alpha-local", "beta-local"):
            with self.subTest(target=target_name), tempfile.TemporaryDirectory() as temp:
                args = argparse.Namespace(
                    env="",
                    target=target_name,
                    workload="full",
                    skip_app=True,
                    skip_build=True,
                    formal_release=True,
                    release_manifest="manifest.json",
                    build_only=False,
                    build_services="",
                    device_id="",
                    rollout_mode="",
                )
                report_dir = Path(temp) / "report"
                runtime = {"content-service": {"ref": "exact", "digest": DIGEST}}
                with (
                    mock.patch.object(
                        stackctl,
                        "probe_migration_drift",
                        return_value=mock.Mock(has_drift=False),
                    ),
                    mock.patch.object(
                        stackctl, "resolve_report_dir", return_value=report_dir
                    ),
                    mock.patch.object(
                        stackctl,
                        "can_reuse_package",
                        return_value=(True, "fixed candidate ready"),
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
                    mock.patch.object(stackctl, "assert_local_runtime_available"),
                    mock.patch.object(
                        stackctl,
                        "_gamma_env_from_port_manifest",
                        return_value={
                            "QWQ_LOCAL_RELEASE_TARGET": target_name,
                            "LOCAL_GAMMA_COMPOSE_PROJECT_NAME": target_name,
                        },
                    ),
                    mock.patch.object(
                        stackctl,
                        "_optional_product_telemetry_environment",
                        return_value=({}, ""),
                    ),
                    mock.patch.object(
                        stackctl,
                        "_bind_formal_local_release_provider_environment",
                        return_value=None,
                    ) as bind_provider,
                    mock.patch.object(stackctl, "run", return_value=completed()),
                    mock.patch.object(
                        stackctl,
                        "_bind_gamma_release_image_refs",
                        return_value=composition,
                    ) as bind_candidate,
                    mock.patch.object(
                        stackctl, "_run_with_live_output", return_value=completed()
                    ) as run_runtime,
                    mock.patch.object(
                        stackctl,
                        "_inspect_gamma_release_runtime",
                        return_value=runtime,
                    ) as inspect_runtime,
                    mock.patch.object(stackctl, "_write_summary_bundle"),
                    mock.patch.object(stackctl, "relpath", side_effect=str),
                ):
                    result = stackctl.command_up(args)

                self.assertEqual(result["exitCode"], 0)
                bind_provider.assert_called_once()
                bind_candidate.assert_called_once()
                inspect_runtime.assert_called_once_with(composition, mock.ANY)
                command = run_runtime.call_args.args[0]
                self.assertIn("--formal-release", command)
                self.assertIn("--skip-build", command)

                report = json.loads((report_dir / "report.json").read_text())
                self.assertTrue(report["formalRelease"])
                self.assertEqual(report["runtimeMode"], "immutable-oci")
                self.assertEqual(report["runtimeCandidateDigest"], DIGEST)
                self.assertEqual(report["runtimeImages"], runtime)
                self.assertFalse(report["destructiveRepairPerformed"])

    def test_formal_candidate_images_pull_concurrently_before_binding(self) -> None:
        services = (
            ("service-a", "QWQ_COMPOSE_SERVICE_A_IMAGE"),
            ("service-b", "QWQ_COMPOSE_SERVICE_B_IMAGE"),
        )
        manifest = {
            "candidateId": DIGEST,
            "artifactDigest": "sha256:" + "b" * 64,
            "images": {
                service: {
                    "repository": f"ghcr.io/owner/repo/{service}",
                    "digest": DIGEST,
                    "ref": f"ghcr.io/owner/repo/{service}@{DIGEST}",
                }
                for service, _ in services
            },
        }
        both_started = threading.Event()
        call_lock = threading.Lock()
        call_count = 0

        def concurrent_pull(_argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            with call_lock:
                call_count += 1
                if call_count == len(services):
                    both_started.set()
            self.assertTrue(both_started.wait(timeout=1))
            return completed()

        with tempfile.TemporaryDirectory() as temp:
            manifest_path = Path(temp) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            environment: dict[str, str] = {}
            with (
                mock.patch.object(
                    stackctl,
                    "GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS",
                    services,
                ),
                mock.patch.object(
                    stackctl.finalize_mainline_release_artifact,
                    "validate_manifest",
                ),
                mock.patch.object(
                    stackctl.finalize_mainline_release_artifact,
                    "validate_manifest_files",
                ),
                mock.patch.object(
                    stackctl,
                    "packaged_configuration_digest",
                    return_value="sha256:" + "c" * 64,
                ),
                mock.patch.object(stackctl, "run", side_effect=concurrent_pull),
            ):
                composition = stackctl._bind_gamma_release_image_refs(
                    manifest_path,
                    environment,
                )

        self.assertTrue(both_started.is_set())
        self.assertEqual(composition["candidateId"], DIGEST)
        self.assertEqual(environment["QWQ_RELEASE_CANDIDATE_DIGEST"], DIGEST)
        self.assertEqual(
            environment["LOCAL_GAMMA_CONFIG_VERSION"],
            "sha256:" + "c" * 64,
        )
        self.assertEqual(
            set(composition["images"]),
            {"service-a", "service-b"},
        )

    def test_formal_runtime_image_inspection_is_bounded_parallel(self) -> None:
        refs = {
            service: f"ghcr.io/owner/repo/{service}@{DIGEST}"
            for service in ("service-a", "service-b")
        }
        composition = {
            "images": {
                service: {"ref": ref, "digest": DIGEST}
                for service, ref in refs.items()
            }
        }
        both_started = threading.Event()
        call_lock = threading.Lock()
        ps_count = 0

        def inspect_runtime(
            argv: list[str],
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            nonlocal ps_count
            if argv[:3] == ["docker", "ps", "-aq"]:
                service = argv[-1].rsplit("=", 1)[1]
                with call_lock:
                    ps_count += 1
                    if ps_count == len(refs):
                        both_started.set()
                self.assertTrue(both_started.wait(timeout=1))
                return subprocess.CompletedProcess(argv, 0, f"id-{service}\n", "")
            if argv[:2] == ["docker", "inspect"]:
                service = argv[2].removeprefix("id-")
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    json.dumps(
                        [
                            {
                                "Config": {"Image": refs[service]},
                                "Image": "sha256:" + "c" * 64,
                                "State": {"Status": "running"},
                            }
                        ]
                    ),
                    "",
                )
            if argv[:3] == ["docker", "image", "inspect"]:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    json.dumps([{"RepoDigests": [argv[3]]}]),
                    "",
                )
            raise AssertionError(argv)

        with mock.patch.object(stackctl, "run", side_effect=inspect_runtime):
            runtime = stackctl._inspect_gamma_release_runtime(
                composition,
                {"LOCAL_GAMMA_COMPOSE_PROJECT_NAME": "candidate"},
            )

        self.assertTrue(both_started.is_set())
        self.assertEqual(list(runtime), ["service-a", "service-b"])

    def test_formal_down_targets_only_candidate_scoped_compose_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "candidateId": DIGEST,
                        "artifactDigest": "sha256:" + "b" * 64,
                        "images": {
                            service: {
                                "repository": f"ghcr.io/owner/repo/{service}",
                                "digest": DIGEST,
                                "ref": f"ghcr.io/owner/repo/{service}@{DIGEST}",
                            }
                            for service, _ in (
                                stackctl.GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
                            )
                        },
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                target="beta-local",
                formal_release=True,
                release_manifest=str(manifest_path),
                report_dir="",
            )
            report_dir = root / "report"
            with (
                mock.patch.object(
                    stackctl, "resolve_report_dir", return_value=report_dir
                ),
                mock.patch.object(
                    stackctl,
                    "_local_stack_operation_lock",
                    return_value=contextlib.nullcontext(),
                ),
                mock.patch.object(stackctl, "active_consumer_leases", return_value=[]),
                mock.patch.object(
                    stackctl.finalize_mainline_release_artifact,
                    "validate_manifest",
                ),
                mock.patch.object(
                    stackctl.finalize_mainline_release_artifact,
                    "validate_manifest_files",
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={
                        "LOCAL_GAMMA_COMPOSE_PROJECT_NAME": "candidate-project",
                        "QWQ_LOCAL_RELEASE_ENV": "beta",
                        "QWQ_LOCAL_RELEASE_TARGET": "beta-local",
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "packaged_configuration_digest",
                    return_value="sha256:" + "c" * 64,
                ),
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(stackctl, "run", return_value=completed()) as run,
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_down(args)

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(
            run.call_args.args[0],
            [
                "bash",
                "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
                "--down",
                "--formal-release-teardown",
            ],
        )
        self.assertEqual(
            run.call_args.kwargs["env"]["LOCAL_GAMMA_COMPOSE_PROJECT_NAME"],
            "candidate-project",
        )
        self.assertRegex(
            run.call_args.kwargs["env"]["LOCAL_GAMMA_IMAGE_VERSION"],
            r"^sha256:[0-9a-f]{64}$",
        )
        self.assertEqual(
            run.call_args.kwargs["env"]["LOCAL_GAMMA_CONTENT_SERVICE_IMAGE"],
            f"ghcr.io/owner/repo/content-service@{DIGEST}",
        )

    def test_health_fails_fast_without_running_downstream_integration_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report_dir = Path(temp) / "health"
            args = argparse.Namespace(
                target="beta-local",
                scope="full",
                request_timeout_seconds=0,
                retry_attempts=0,
                retry_sleep_seconds=-1,
                read_only=False,
                deadline_epoch=0,
                require_non_empty_content_feed=False,
            )
            with (
                mock.patch.object(
                    stackctl, "resolve_report_dir", return_value=report_dir
                ),
                mock.patch.object(
                    stackctl,
                    "_health_checks_for_target",
                    return_value=[
                        {
                            "name": "api-health",
                            "scope": "edge",
                            "url": "https://api.beta.invalid/healthz",
                        }
                    ],
                ),
                mock.patch.object(
                    stackctl,
                    "fetch_url",
                    return_value=(False, None, "connection refused", ""),
                ),
                mock.patch.object(
                    stackctl, "_script_probes_for_target"
                ) as script_probes,
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "_write_stdout_markdown"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_health(args)

            self.assertEqual(result["exitCode"], 1)
            script_probes.assert_not_called()
            report = json.loads((report_dir / "report.json").read_text())
            integration = report["checks"][-1]
            self.assertEqual(integration["name"], "integration-readonly")
            self.assertTrue(integration["skipped"])
            self.assertFalse(integration["ok"])

    def test_health_http_checks_run_concurrently_and_preserve_declared_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report_dir = Path(temp) / "health"
            args = argparse.Namespace(
                target="beta-local",
                scope="full",
                request_timeout_seconds=1,
                retry_attempts=1,
                retry_sleep_seconds=0,
                read_only=True,
                deadline_epoch=0,
            )
            both_started = threading.Event()
            call_lock = threading.Lock()
            call_count = 0

            def fetch_concurrently(
                url: str,
                **_kwargs: object,
            ) -> tuple[bool, int, str, str]:
                nonlocal call_count
                with call_lock:
                    call_count += 1
                    if call_count == 2:
                        both_started.set()
                if url.endswith("/first"):
                    self.assertTrue(
                        both_started.wait(1),
                        "second health probe did not start concurrently",
                    )
                return True, 200, url, "application/json"

            declared_checks = [
                {"name": "first", "scope": "edge", "url": "https://probe/first"},
                {"name": "second", "scope": "edge", "url": "https://probe/second"},
            ]
            with (
                mock.patch.object(
                    stackctl, "resolve_report_dir", return_value=report_dir
                ),
                mock.patch.object(
                    stackctl,
                    "_health_checks_for_target",
                    return_value=declared_checks,
                ),
                mock.patch.object(
                    stackctl,
                    "fetch_url",
                    side_effect=fetch_concurrently,
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "_write_stdout_markdown"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_health(args)

            self.assertEqual(result["exitCode"], 0)
            report = json.loads((report_dir / "report.json").read_text())
            self.assertEqual(report["httpProbeConcurrency"], 2)
            self.assertEqual(
                [item["name"] for item in report["checks"]],
                ["first", "second"],
            )


if __name__ == "__main__":
    unittest.main()

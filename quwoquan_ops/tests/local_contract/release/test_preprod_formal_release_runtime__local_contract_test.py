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
from quwoquan_ops.cli.lib import read_only_user_availability


DIGEST = "sha256:" + "a" * 64

_AVAILABILITY_LAYERS = (
    "build_ready",
    "runtime_full_ready",
    "provider_ready",
    "release_active",
    "content_exact_queries_ready",
    "device_bound",
    "content_live_passed",
)


def completed(returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout="", stderr="")


def ready_availability_report(target: str, environment: str) -> dict[str, object]:
    """A ready read-only availability aggregate, so health exit code isolates one layer."""
    return {
        "schema": read_only_user_availability.SCHEMA,
        "target": target,
        "environment": environment,
        "observedAt": "2026-08-18T00:00:00Z",
        "status": "ready",
        "firstBlockerClass": "",
        "firstBlocker": "",
        "userAvailability": [
            {"name": name, "status": "ready", "issues": []}
            for name in _AVAILABILITY_LAYERS
        ],
        "metrics": [],
        "evidence": {},
    }


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

    def test_local_up_and_down_reject_retired_formal_release_options(self) -> None:
        parser = stackctl.build_parser()
        for command in ("up", "down"):
            for option in ("--formal-release", "--release-manifest"):
                argv = [command, "--target", "alpha-local", option]
                if option == "--release-manifest":
                    argv.append("/tmp/legacy.json")
                with self.subTest(command=command, option=option), self.assertRaises(SystemExit):
                    parser.parse_args(argv)


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

    def test_content_consumer_health_does_not_require_device_or_app_uat(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report_dir = Path(temp) / "health"
            args = argparse.Namespace(
                target="alpha-local",
                scope="content-consumer",
                request_timeout_seconds=1,
                retry_attempts=1,
                retry_sleep_seconds=0,
                read_only=True,
                deadline_epoch=0,
            )
            availability = ready_availability_report("alpha-local", "alpha")
            for layer in availability["userAvailability"]:
                if layer["name"] in {"device_bound", "content_live_passed"}:
                    layer.update(status="blocked", issues=[f"{layer['name']} not required"])
            availability.update(
                status="failed", firstBlockerClass="device",
                firstBlocker="device_bound not required",
            )
            with (
                mock.patch.object(stackctl, "resolve_report_dir", return_value=report_dir),
                mock.patch.object(
                    stackctl, "_health_checks_for_target",
                    return_value=[{"name": "api-health", "scope": "edge", "url": "https://api.alpha.invalid/healthz"}],
                ),
                mock.patch.object(
                    stackctl, "fetch_url", return_value=(True, 200, "ok", "application/json")
                ),
                mock.patch.object(
                    stackctl, "_read_only_user_availability_report", return_value=availability
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "_write_stdout_markdown"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_health(args)

            self.assertEqual(result["exitCode"], 0, result)
            report = json.loads((report_dir / "report.json").read_text())
            self.assertEqual(
                report["requiredUserAvailabilityLayers"],
                [
                    "build_ready", "runtime_full_ready", "provider_ready",
                    "release_active", "content_exact_queries_ready",
                ],
            )
            self.assertEqual(report["userAvailabilityReport"]["status"], "failed")

    def test_content_consumer_health_still_fails_on_api_required_layer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report_dir = Path(temp) / "health"
            args = argparse.Namespace(
                target="alpha-local",
                scope="content-consumer",
                request_timeout_seconds=1,
                retry_attempts=1,
                retry_sleep_seconds=0,
                read_only=True,
                deadline_epoch=0,
            )
            availability = ready_availability_report("alpha-local", "alpha")
            for layer in availability["userAvailability"]:
                if layer["name"] == "content_exact_queries_ready":
                    layer.update(status="blocked", issues=["content exact queries failed"])
            availability.update(
                status="failed", firstBlockerClass="content_exact_queries",
                firstBlocker="content exact queries failed",
            )
            with (
                mock.patch.object(stackctl, "resolve_report_dir", return_value=report_dir),
                mock.patch.object(
                    stackctl, "_health_checks_for_target",
                    return_value=[{"name": "api-health", "scope": "edge", "url": "https://api.alpha.invalid/healthz"}],
                ),
                mock.patch.object(
                    stackctl, "fetch_url", return_value=(True, 200, "ok", "application/json")
                ),
                mock.patch.object(
                    stackctl, "_read_only_user_availability_report", return_value=availability
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "_write_stdout_markdown"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_health(args)

            self.assertEqual(result["exitCode"], 1)
            self.assertIn("content exact queries failed", "\n".join(result["details"]))

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
                # HTTP 探测的并发与顺序是本用例的被测面。read-only user
                # availability 聚合读工作站真实候选/运行态，不隔离会让
                # exitCode 随本机状态漂移。
                mock.patch.object(
                    stackctl,
                    "_read_only_user_availability_report",
                    return_value=ready_availability_report("beta-local", "beta"),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
                mock.patch.object(stackctl, "_write_stdout_markdown"),
                mock.patch.object(stackctl, "relpath", side_effect=str),
            ):
                result = stackctl.command_health(args)

            self.assertEqual(result["exitCode"], 0, result["details"])
            report = json.loads((report_dir / "report.json").read_text())
            self.assertEqual(report["httpProbeConcurrency"], 2)
            self.assertEqual(
                [item["name"] for item in report["checks"]],
                ["first", "second"],
            )


if __name__ == "__main__":
    unittest.main()

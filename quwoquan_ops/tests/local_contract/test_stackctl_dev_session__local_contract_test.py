"""Dev sessions are the only package/up/health developer orchestration.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
"""
from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl


def _ok(summary: str) -> dict[str, object]:
    return {"exitCode": 0, "summary": summary, "details": [], "reportDir": summary}


def _handoff_completed() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["build_launcher_handoff.py"],
        returncode=0,
        stdout=json.dumps(
            {
                "launchPolicy": "test_live",
                "contentBindingState": "unbound",
            }
        ),
        stderr="",
    )


def _runtime_started(
    environment: str = "alpha",
    target: str = "alpha-local",
) -> dict[str, object]:
    return {
        "exitCode": 0,
        "blockerKind": "",
        "details": [],
        "runtime": {
            "environment": environment,
            "target": target,
            "composeProject": f"quwoquan_{environment}_test_live",
        },
        "phases": [
            {"name": "mutable-materialize", "exitCode": 0},
            {"name": "compose-render", "exitCode": 0},
            {"name": "compose-up", "exitCode": 0},
        ],
    }


def _runtime_started_with_identity(report_dir: Path) -> dict[str, object]:
    plan: dict[str, object] = {
        "schema": "stackctl.mutable_test_live_runtime.v1",
        "environment": "alpha",
        "target": "alpha-local",
        "composeProject": "quwoquan_alpha_test_live",
        "composeDigest": "sha256:" + "1" * 64,
        "configurationDigest": "sha256:" + "2" * 64,
        "providerRuntimeDigest": "sha256:" + "3" * 64,
        "portProfile": "alpha-local",
        "portBlock": {"start": 17000, "end": 17999},
        "publishedPorts": {"api-edge": 17000},
        "tlsProfile": "local-managed",
        "resolverHandoffDigest": "sha256:" + "4" * 64,
        "workspaceIdentity": {
            "sourceRevision": "a" * 40,
            "workspaceStatusDigest": "sha256:" + "5" * 64,
            "mutableStateDigest": "sha256:" + "6" * 64,
        },
    }
    receipt = {
        "schema": "stackctl.mutable_test_live_startup_attempt.v1",
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "unbound",
        "attemptId": "alpha-test-live-attempt-1",
        "status": "running",
        "runRoot": str(report_dir),
        **{
            field: plan[field]
            for field in (
                "environment",
                "target",
                "composeProject",
                "composeDigest",
                "configurationDigest",
                "providerRuntimeDigest",
                "portProfile",
                "portBlock",
                "publishedPorts",
                "tlsProfile",
                "resolverHandoffDigest",
            )
        },
        "sourceRevision": "a" * 40,
        "workspaceStatusDigest": "sha256:" + "5" * 64,
        "mutableStateDigest": "sha256:" + "6" * 64,
    }
    return {
        "exitCode": 0,
        "blockerKind": "",
        "details": [],
        "runtime": plan,
        "startupAttempt": receipt,
        "phases": [
            {"name": "mutable-materialize", "exitCode": 0},
            {"name": "compose-render", "exitCode": 0},
            {"name": "compose-up", "exitCode": 0},
            {"name": "mutable-startup-running", "exitCode": 0},
        ],
    }


class StackctlDevSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._mutable_receipt_loader = mock.patch.object(
            stackctl,
            "load_test_live_startup_attempt",
            return_value=None,
        )
        self._mutable_receipt_loader.start()
        self.addCleanup(self._mutable_receipt_loader.stop)

    def test_dev_session_only_resumes_exact_running_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_root = Path(temporary)
            runtime_payload = _runtime_started_with_identity(run_root)
            plan = dict(runtime_payload["runtime"])
            receipt = dict(runtime_payload["startupAttempt"])
            receipt.update(
                {
                    "workload": "full",
                    "startedAt": "2026-08-09T00:00:00Z",
                }
            )
            compose_path = run_root / "rendered-compose/00-full.json"
            compose_path.parent.mkdir(parents=True)
            compose_path.write_text(
                json.dumps(
                    {
                        "services": {
                            "api-edge": {
                                "environment": {"IMAGE_VERSION": "${IMAGE_VERSION}"},
                                "depends_on": {
                                    "mongo-init": {
                                        "condition": "service_completed_successfully"
                                    },
                                    "postgres": {"condition": "service_healthy"},
                                },
                            },
                            "integration-service": {
                                "environment": {"IMAGE_VERSION": "${IMAGE_VERSION}"}
                            },
                            "sms-provider-substitute": {
                                "environment": {
                                    "SMS_SUBSTITUTE_CONFIGURATION_DIGEST": "${DIGEST}"
                                }
                            },
                            "content-service": {
                                "environment": {"IMAGE_VERSION": "${IMAGE_VERSION}"},
                                "healthcheck": {"test": ["CMD", "true"]},
                            },
                            "recommendation-service": {
                                "environment": {"IMAGE_VERSION": "${IMAGE_VERSION}"},
                                "healthcheck": {"test": ["CMD", "true"]},
                            },
                            "gamma-proxy": {
                                "image": "caddy:2-alpine",
                                "healthcheck": {"test": ["CMD", "true"]},
                            },
                            "object-storage": {"image": "minio/minio:current"},
                            "assistant-service": {
                                "environment": {"IMAGE_VERSION": "${IMAGE_VERSION}"},
                                "healthcheck": {"test": ["CMD", "true"]},
                            },
                            "postgres": {
                                "image": "postgres:16-alpine",
                                "healthcheck": {"test": ["CMD", "true"]},
                            },
                            "mongo-init": {"image": "mongo:7-jammy"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            plan["executionComposeFiles"] = [str(compose_path)]
            (run_root / "mutable-runtime-plan.json").write_text(
                json.dumps(plan),
                encoding="utf-8",
            )
            mutable_digest = "sha256:" + "6" * 64
            configuration_digest = "sha256:" + "2" * 64
            containers = []
            for index, service in enumerate(
                ("api-edge", "integration-service", "sms-provider-substitute")
            ):
                environment_rows = (
                    [f"IMAGE_VERSION={mutable_digest}"]
                    if service != "sms-provider-substitute"
                    else [
                        "SMS_SUBSTITUTE_CONFIGURATION_DIGEST="
                        + configuration_digest
                    ]
                )
                image = (
                    f"quwoquan/test-live-alpha-local-{service}:{'6' * 16}"
                    if service != "sms-provider-substitute"
                    else "quwoquan/sms-provider-substitute:"
                    f"alpha-test-live-{'6' * 16}"
                )
                containers.append(
                    {
                        "Created": "2026-08-09T00:00:01Z",
                        "Config": {
                            "Image": image,
                            "Env": environment_rows,
                            "Labels": {
                                "com.docker.compose.project": "quwoquan_alpha_test_live",
                                "com.docker.compose.service": service,
                                "com.docker.compose.config-hash": f"hash-{index}",
                            },
                        },
                        "State": {"Status": "running"},
                    }
                )
            containers.extend(
                (
                    {
                        # Compose legitimately reuses persistent infrastructure
                        # created before this mutable startup attempt.
                        "Created": "2026-08-08T23:00:00Z",
                        "Config": {
                            "Image": "postgres:16-alpine",
                            "Env": [],
                            "Labels": {
                                "com.docker.compose.project": "quwoquan_alpha_test_live",
                                "com.docker.compose.service": "postgres",
                                "com.docker.compose.config-hash": "hash-postgres",
                            },
                        },
                        "State": {
                            "Status": "running",
                            "Health": {"Status": "healthy"},
                        },
                    },
                    {
                        # An init dependency declared completed-successfully is
                        # expected to be exited/0 rather than running forever.
                        "Created": "2026-08-08T23:00:01Z",
                        "Config": {
                            "Image": "mongo:7-jammy",
                            "Env": [],
                            "Labels": {
                                "com.docker.compose.project": "quwoquan_alpha_test_live",
                                "com.docker.compose.service": "mongo-init",
                                "com.docker.compose.config-hash": "hash-mongo-init",
                            },
                        },
                        "State": {"Status": "exited", "ExitCode": 0},
                    },
                )
            )
            for service in (
                "content-service",
                "recommendation-service",
                "assistant-service",
            ):
                containers.append(
                    {
                        "Created": "2026-08-09T00:00:02Z",
                        "Config": {
                            "Image": (
                                f"quwoquan/test-live-alpha-local-{service}:"
                                + "6" * 16
                            ),
                            "Env": [f"IMAGE_VERSION={mutable_digest}"],
                            "Labels": {
                                "com.docker.compose.project": "quwoquan_alpha_test_live",
                                "com.docker.compose.service": service,
                                "com.docker.compose.config-hash": f"hash-{service}",
                            },
                        },
                        "State": (
                            {
                                "Status": "exited",
                                "ExitCode": 1,
                                "Health": {"Status": "unhealthy"},
                            }
                            if service == "assistant-service"
                            else {
                                "Status": "running",
                                "Health": {"Status": "healthy"},
                            }
                        ),
                    }
                )
            containers.extend(
                (
                    {
                        "Created": "2026-08-09T00:00:03Z",
                        "Config": {
                            "Image": "caddy:2-alpine",
                            "Env": [],
                            "Labels": {
                                "com.docker.compose.project": "quwoquan_alpha_test_live",
                                "com.docker.compose.service": "gamma-proxy",
                                "com.docker.compose.config-hash": "hash-gamma-proxy",
                            },
                        },
                        "State": {
                            "Status": "running",
                            "Health": {"Status": "healthy"},
                        },
                    },
                    {
                        "Created": "2026-08-09T00:00:04Z",
                        "Config": {
                            "Image": "minio/minio:current",
                            "Env": [],
                            "Labels": {
                                "com.docker.compose.project": "quwoquan_alpha_test_live",
                                "com.docker.compose.service": "object-storage",
                                "com.docker.compose.config-hash": "hash-object-storage",
                            },
                        },
                        "State": {"Status": "running"},
                    },
                )
            )

            with (
                mock.patch.object(
                    stackctl,
                    "load_test_live_startup_attempt",
                    return_value=receipt,
                ),
                mock.patch.object(
                    stackctl,
                    "run",
                    side_effect=[
                        subprocess.CompletedProcess(
                            ["docker", "ps"],
                            0,
                            "one\ntwo\nthree\nfour\nfive\n",
                            "",
                        ),
                        subprocess.CompletedProcess(
                            ["docker", "inspect"], 0, json.dumps(containers), ""
                        ),
                    ],
                ),
            ):
                resumed, warnings = (
                    stackctl._dev_session_resume_running_mutable_runtime(
                        environment="alpha",
                        target="alpha-local",
                        workspace_snapshot=dict(plan["workspaceIdentity"]),
                        required_running_services=(
                            stackctl._TEST_LIVE_CONTENT_BINDING_REQUIRED_SERVICES
                        ),
                    )
                )

            self.assertTrue(
                any("assistant-service status=exited" in row for row in warnings)
            )
            self.assertIsNotNone(resumed)
            self.assertEqual(
                resumed["startupAttempt"]["attemptId"],
                "alpha-test-live-attempt-1",
            )
            self.assertEqual(resumed["runtimeRunRoot"], str(run_root))
            self.assertEqual(
                resumed["phases"][0]["name"],
                "mutable-runtime-resume",
            )

            with (
                mock.patch.object(
                    stackctl,
                    "load_test_live_startup_attempt",
                    return_value=receipt,
                ),
                mock.patch.object(
                    stackctl,
                    "run",
                    side_effect=[
                        subprocess.CompletedProcess(
                            ["docker", "ps"],
                            0,
                            "one\ntwo\nthree\nfour\nfive\n",
                            "",
                        ),
                        subprocess.CompletedProcess(
                            ["docker", "inspect"], 0, json.dumps(containers), ""
                        ),
                    ],
                ),
            ):
                drifted, drift_warnings = (
                    stackctl._dev_session_resume_running_mutable_runtime(
                        environment="alpha",
                        target="alpha-local",
                        workspace_snapshot={
                            **dict(plan["workspaceIdentity"]),
                            "mutableStateDigest": "sha256:" + "9" * 64,
                        },
                        required_running_services=(
                            stackctl._TEST_LIVE_CONTENT_BINDING_REQUIRED_SERVICES
                        ),
                    )
                )
            self.assertIsNotNone(drifted)
            self.assertEqual(
                drifted["startupAttempt"]["mutableStateDigest"],
                mutable_digest,
            )
            self.assertIn("reusing the exact verified deployed runtime", drift_warnings[0])

            def assert_rejected(
                observed: list[dict[str, object]],
                pattern: str,
            ) -> None:
                with (
                    mock.patch.object(
                        stackctl,
                        "load_test_live_startup_attempt",
                        return_value=receipt,
                    ),
                    mock.patch.object(
                        stackctl,
                        "run",
                        side_effect=[
                            subprocess.CompletedProcess(
                                ["docker", "ps"],
                                0,
                                "one\ntwo\nthree\nfour\nfive\n",
                                "",
                            ),
                            subprocess.CompletedProcess(
                                ["docker", "inspect"],
                                0,
                                json.dumps(observed),
                                "",
                            ),
                        ],
                    ),
                ):
                    with self.assertRaisesRegex(ValueError, pattern):
                        stackctl._dev_session_resume_running_mutable_runtime(
                            environment="alpha",
                            target="alpha-local",
                            workspace_snapshot=dict(plan["workspaceIdentity"]),
                            required_running_services=(
                                stackctl._TEST_LIVE_CONTENT_BINDING_REQUIRED_SERVICES
                            ),
                        )

            wrong_project = json.loads(json.dumps(containers))
            wrong_project[0]["Config"]["Labels"][
                "com.docker.compose.project"
            ] = "quwoquan_alpha_stale"
            assert_rejected(wrong_project, "not bound to this attempt")

            wrong_image = json.loads(json.dumps(containers))
            wrong_image[0]["Config"]["Image"] = (
                "quwoquan/test-live-alpha-local-api-edge:" + "9" * 16
            )
            assert_rejected(wrong_image, "image ref drifted: api-edge")

            failed_init = json.loads(json.dumps(containers))
            next(
                item
                for item in failed_init
                if item["Config"]["Labels"]["com.docker.compose.service"]
                == "mongo-init"
            )["State"] = {"Status": "exited", "ExitCode": 1}
            assert_rejected(
                failed_init,
                "completed service did not exit successfully: mongo-init",
            )

            for required_service in (
                "api-edge",
                "content-service",
                "recommendation-service",
                "gamma-proxy",
                "object-storage",
            ):
                failed_required = json.loads(json.dumps(containers))
                failed_container = next(
                    item
                    for item in failed_required
                    if item["Config"]["Labels"]["com.docker.compose.service"]
                    == required_service
                )
                failed_container["State"] = {
                    "Status": "exited",
                    "ExitCode": 1,
                    "Health": {"Status": "unhealthy"},
                }
                assert_rejected(
                    failed_required,
                    f"required service is .*: {required_service}",
                )

            plan_path = run_root / "mutable-runtime-plan.json"
            plan_path.unlink()
            plan_path.symlink_to(compose_path)
            with mock.patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                return_value=receipt,
            ):
                with self.assertRaisesRegex(ValueError, "non-symlink"):
                    stackctl._dev_session_resume_running_mutable_runtime(
                        environment="alpha",
                        target="alpha-local",
                        workspace_snapshot=dict(plan["workspaceIdentity"]),
                    )

    def test_mutable_compose_execution_copy_resolves_each_source_build_context(self) -> None:
        with tempfile.TemporaryDirectory(dir=stackctl.output_root()) as temporary:
            report_dir = Path(temporary)
            source_dir = report_dir / "source" / "deploy"
            build_context = report_dir / "source"
            (build_context / "build").mkdir(parents=True)
            (build_context / "build/Dockerfile").write_text(
                "FROM scratch\n", encoding="utf-8"
            )
            source_dir.mkdir(parents=True)
            source = source_dir / "compose.yaml"
            source.write_text(
                "services:\n  api:\n    build:\n      context: ..\n"
                "      dockerfile: build/Dockerfile\n",
                encoding="utf-8",
            )
            with mock.patch.object(stackctl, "ROOT", report_dir):
                outputs = stackctl._dev_session_materialize_compose_files(
                    [source],
                    destination_root=report_dir / "rendered",
                )
            payload = json.loads(outputs[0].read_text(encoding="utf-8"))
            self.assertEqual(
                payload["services"]["api"]["build"]["context"],
                str(build_context.resolve()),
            )
            self.assertEqual(
                payload["services"]["api"]["build"]["dockerfile"],
                "build/Dockerfile",
            )

    def test_mutable_compose_execution_copy_supports_base_relative_fragments(self) -> None:
        with tempfile.TemporaryDirectory(dir=stackctl.output_root()) as temporary:
            root = Path(temporary)
            base_dir = root / "ops/environments/compose"
            base_dir.mkdir(parents=True)
            base = base_dir / "base.yaml"
            base.write_text("services: {}\n", encoding="utf-8")
            service_dir = root / "service/services/api/deploy"
            service_dir.mkdir(parents=True)
            (root / "service/services/api/build").mkdir(parents=True)
            (root / "service/services/api/build/Dockerfile").write_text(
                "FROM scratch\n", encoding="utf-8"
            )
            fragment = service_dir / "compose.yaml"
            fragment.write_text(
                "services:\n  api:\n    build:\n"
                "      context: ../../../service\n"
                "      dockerfile: services/api/build/Dockerfile\n",
                encoding="utf-8",
            )
            with mock.patch.object(stackctl, "ROOT", root):
                outputs = stackctl._dev_session_materialize_compose_files(
                    [base, fragment], destination_root=root / "rendered"
                )
            payload = json.loads(outputs[1].read_text(encoding="utf-8"))
            self.assertEqual(
                payload["services"]["api"]["build"]["context"],
                str((root / "service").resolve()),
            )

    def test_mutable_runtime_dependencies_exist_only_in_execution_copies(self) -> None:
        with tempfile.TemporaryDirectory(dir=stackctl.output_root()) as temporary:
            root = Path(temporary)
            base = root / "quwoquan_ops/environments/compose/base.yaml"
            base.parent.mkdir(parents=True)
            base.write_text("services: {}\n", encoding="utf-8")
            source = (
                root
                / "quwoquan_service/services/content-service/deploy/compose.yaml"
            )
            source.parent.mkdir(parents=True)
            build_context = root / "quwoquan_service"
            dockerfile = build_context / "services/content-service/build/Dockerfile"
            dockerfile.parent.mkdir(parents=True)
            dockerfile.write_text("FROM scratch\n", encoding="utf-8")
            source.write_text(
                "services:\n"
                "  content-service:\n"
                "    build:\n"
                "      context: ../../../quwoquan_service\n"
                "      dockerfile: services/content-service/build/Dockerfile\n"
                "    depends_on:\n"
                "      mongodb:\n"
                "        condition: service_healthy\n",
                encoding="utf-8",
            )
            recommendation_source = (
                root
                / "quwoquan_service/services/recommendation-service/deploy/compose.yaml"
            )
            recommendation_source.parent.mkdir(parents=True)
            recommendation_dockerfile = (
                build_context
                / "services/recommendation-service/build/Dockerfile"
            )
            recommendation_dockerfile.parent.mkdir(parents=True)
            recommendation_dockerfile.write_text("FROM scratch\n", encoding="utf-8")
            recommendation_source.write_text(
                "services:\n"
                "  recommendation-service:\n"
                "    build:\n"
                "      context: ../../../quwoquan_service\n"
                "      dockerfile: services/recommendation-service/build/Dockerfile\n",
                encoding="utf-8",
            )
            with mock.patch.object(stackctl, "ROOT", root):
                outputs = stackctl._dev_session_materialize_compose_files(
                    [base, source, recommendation_source],
                    destination_root=root / "rendered",
                )
            payload = json.loads(outputs[1].read_text(encoding="utf-8"))
            dependencies = payload["services"]["content-service"]["depends_on"]
            self.assertEqual(
                dependencies["elasticsearch"],
                {"condition": "service_healthy"},
            )
            self.assertEqual(
                dependencies["mongodb"],
                {"condition": "service_healthy"},
            )
            self.assertEqual(
                dependencies["postgres"],
                {"condition": "service_healthy"},
            )
            self.assertNotIn("elasticsearch:", source.read_text(encoding="utf-8"))
            recommendation_payload = json.loads(
                outputs[2].read_text(encoding="utf-8")
            )
            self.assertEqual(
                recommendation_payload["services"]["recommendation-service"][
                    "depends_on"
                ]["redis"],
                {"condition": "service_healthy"},
            )
            self.assertNotIn(
                "depends_on:", recommendation_source.read_text(encoding="utf-8")
            )

    def test_mutable_projection_exposes_target_public_api_host(self) -> None:
        topology = stackctl.load_environment_topology()
        for environment in ("alpha", "beta", "gamma"):
            target = f"{environment}-local"
            projected = stackctl._gamma_env_from_port_manifest(topology, target)
            self.assertEqual(projected["COMPOSE_PARALLEL_LIMIT"], "1")
            self.assertEqual(
                projected["QWQ_OUTPUT_ROOT"],
                str(stackctl.output_root().expanduser().resolve()),
            )
            self.assertEqual(
                projected["QWQ_PUBLIC_API_HOST"],
                f"api.{environment}.quwoquan.com",
            )
            self.assertEqual(
                projected["QWQ_PUBLIC_WEB_HOST"],
                f"{environment}.quwoquan.com",
            )
            self.assertEqual(
                projected["QWQ_PUBLIC_RTC_HOST"],
                f"rtc.{environment}.quwoquan.com",
            )
            self.assertEqual(
                projected["QWQ_PUBLIC_OPS_HOST"],
                f"ops.{environment}.quwoquan.com",
            )
            self.assertEqual(
                projected["QWQ_PUBLIC_CDN_HOST"],
                f"cdn.{environment}.quwoquan.com",
            )
            self.assertEqual(
                projected["QWQ_PUBLIC_UPLOAD_HOST"],
                f"upload.{environment}.quwoquan.com",
            )

    def test_mutable_runtime_uses_exact_project_and_current_source_compose(self) -> None:
        rendered = {
            "plan": {
                "composeProject": "quwoquan_alpha_test_live",
                "composeDigest": "sha256:" + "1" * 64,
                "configurationDigest": "sha256:" + "2" * 64,
                "publishedPorts": {"product-ops-service": 17250},
            },
            "environment": {
                "LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS": "3600",
                "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS": "45",
            },
            "composeFiles": [Path("/repo/current/base.compose.yaml")],
            "composeProfiles": ["assistant-runtime", "edge-media"],
        }
        executions: list[list[str]] = []
        timeouts: list[float] = []
        receipt_transitions: list[dict[str, object]] = []

        def execute(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            executions.append(argv)
            timeouts.append(float(kwargs["timeout_seconds"]))
            return subprocess.CompletedProcess(argv, 0, "", "")

        def transition(**kwargs: object) -> dict[str, object]:
            receipt_transitions.append(kwargs)
            return {
                "attemptId": kwargs["attempt_id"],
                "status": kwargs["status"],
                "configurationDigest": "sha256:" + "2" * 64,
            }

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "_dev_session_render_runtime_inputs",
                return_value=rendered,
            ),
            mock.patch.object(stackctl, "run", side_effect=execute),
            mock.patch.object(
                stackctl,
                "activate_test_live_experiment_policies",
                return_value={
                    "status": "passed",
                    "runtimeIdentityDigest": "sha256:" + "3" * 64,
                },
            ),
            mock.patch.object(
                stackctl,
                "transition_test_live_startup_attempt",
                side_effect=transition,
            ),
            mock.patch.object(
                stackctl,
                "command_package",
                side_effect=AssertionError("mutable runtime must not package"),
            ),
            mock.patch.object(
                stackctl,
                "active_deployment_candidate",
                side_effect=AssertionError("mutable runtime must not select a candidate"),
            ),
        ):
            result = stackctl._start_mutable_test_live_runtime(
                environment="alpha",
                target="alpha-local",
                report_dir=Path(temporary),
                workspace_snapshot={"mutableStateDigest": "sha256:" + "2" * 64},
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(len(executions), 5)
        self.assertEqual(timeouts, [90.0, 3600.0, 3600.0, 3600.0, 3600.0])
        for command in executions:
            self.assertEqual(command[:5], ["docker", "compose", "-p", "quwoquan_alpha_test_live", "-f"])
            self.assertNotIn("package", command)
            self.assertNotIn("candidate", " ".join(command))
        self.assertEqual(executions[0][-2:], ["config", "--quiet"])
        self.assertEqual(executions[1][-4:], ["up", "--build", "-d", "product-ops-service"])
        self.assertEqual(executions[2][-1:], ["build"])
        self.assertEqual(executions[3][-3:], ["up", "-d", "--no-deps"])
        self.assertEqual(executions[4][-3:], ["up", "-d", "--remove-orphans"])
        self.assertEqual(
            [row["status"] for row in receipt_transitions],
            ["prepared", "partial", "running"],
        )
        self.assertEqual(result["startupAttempt"]["status"], "running")

    def test_mutable_compose_up_failure_keeps_partial_receipt(self) -> None:
        rendered = {
            "plan": {
                "composeProject": "quwoquan_alpha_test_live",
                "composeDigest": "sha256:" + "1" * 64,
                "configurationDigest": "sha256:" + "2" * 64,
                "publishedPorts": {"product-ops-service": 17250},
            },
            "environment": {
                "LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS": "3600",
                "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS": "45",
            },
            "composeFiles": [Path("/repo/current/base.compose.yaml")],
            "composeProfiles": [],
        }
        transitions: list[dict[str, object]] = []

        def transition(**kwargs: object) -> dict[str, object]:
            transitions.append(kwargs)
            return {
                "attemptId": kwargs["attempt_id"],
                "status": kwargs["status"],
                "configurationDigest": "sha256:" + "2" * 64,
                "failure": kwargs.get("failure") or None,
            }

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "_dev_session_render_runtime_inputs",
                return_value=rendered,
            ),
            mock.patch.object(
                stackctl,
                "run",
                side_effect=[
                    subprocess.CompletedProcess(
                        ["docker", "compose", "config"], 0, "", ""
                    ),
                    subprocess.CompletedProcess(
                        ["docker", "compose", "up", "product-ops-service"],
                        0,
                        "",
                        "",
                    ),
                    subprocess.CompletedProcess(
                        ["docker", "compose", "build"], 0, "", ""
                    ),
                    subprocess.CompletedProcess(
                        ["docker", "compose", "up", "--no-deps"], 0, "", ""
                    ),
                    subprocess.CompletedProcess(
                        ["docker", "compose", "up"], 1, "", "up failed"
                    ),
                ],
            ),
            mock.patch.object(
                stackctl,
                "activate_test_live_experiment_policies",
                return_value={
                    "status": "passed",
                    "runtimeIdentityDigest": "sha256:" + "3" * 64,
                },
            ),
            mock.patch.object(
                stackctl,
                "transition_test_live_startup_attempt",
                side_effect=transition,
            ),
        ):
            result = stackctl._start_mutable_test_live_runtime(
                environment="alpha",
                target="alpha-local",
                report_dir=Path(temporary),
                workspace_snapshot={},
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "mutable_compose_up_failed")
        self.assertEqual(
            [row["status"] for row in transitions],
            ["prepared", "partial", "partial"],
        )
        self.assertIn("docker compose up exited 1", transitions[-1]["failure"])
        self.assertEqual(result["startupAttempt"]["status"], "partial")

    def test_mutable_compose_build_failure_blocks_before_replacement(self) -> None:
        rendered = {
            "plan": {
                "composeProject": "quwoquan_alpha_test_live",
                "composeDigest": "sha256:" + "1" * 64,
                "configurationDigest": "sha256:" + "2" * 64,
                "publishedPorts": {"product-ops-service": 17250},
            },
            "environment": {
                "LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS": "3600",
                "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS": "45",
            },
            "composeFiles": [Path("/repo/current/base.compose.yaml")],
            "composeProfiles": [],
        }
        transitions: list[dict[str, object]] = []

        def transition(**kwargs: object) -> dict[str, object]:
            transitions.append(kwargs)
            return {
                "attemptId": kwargs["attempt_id"],
                "status": kwargs["status"],
                "configurationDigest": "sha256:" + "2" * 64,
                "failure": kwargs.get("failure") or None,
            }

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "_dev_session_render_runtime_inputs",
                return_value=rendered,
            ),
            mock.patch.object(
                stackctl,
                "run",
                side_effect=[
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 1, "", "build failed"),
                ],
            ) as run_mock,
            mock.patch.object(
                stackctl,
                "activate_test_live_experiment_policies",
                return_value={
                    "status": "passed",
                    "runtimeIdentityDigest": "sha256:" + "3" * 64,
                },
            ),
            mock.patch.object(
                stackctl,
                "transition_test_live_startup_attempt",
                side_effect=transition,
            ),
        ):
            result = stackctl._start_mutable_test_live_runtime(
                environment="alpha",
                target="alpha-local",
                report_dir=Path(temporary),
                workspace_snapshot={},
            )

        self.assertEqual(result["blockerKind"], "mutable_compose_build_failed")
        self.assertEqual(run_mock.call_count, 3)
        self.assertEqual(
            [row["status"] for row in transitions],
            ["prepared", "partial", "partial"],
        )

    def test_mutable_compose_replacement_failure_blocks_before_full_up(self) -> None:
        rendered = {
            "plan": {
                "composeProject": "quwoquan_alpha_test_live",
                "composeDigest": "sha256:" + "1" * 64,
                "configurationDigest": "sha256:" + "2" * 64,
                "publishedPorts": {"product-ops-service": 17250},
            },
            "environment": {
                "LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS": "3600",
                "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS": "45",
            },
            "composeFiles": [Path("/repo/current/base.compose.yaml")],
            "composeProfiles": [],
        }
        transitions: list[dict[str, object]] = []

        def transition(**kwargs: object) -> dict[str, object]:
            transitions.append(kwargs)
            return {
                "attemptId": kwargs["attempt_id"],
                "status": kwargs["status"],
                "configurationDigest": "sha256:" + "2" * 64,
                "failure": kwargs.get("failure") or None,
            }

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "_dev_session_render_runtime_inputs",
                return_value=rendered,
            ),
            mock.patch.object(
                stackctl,
                "run",
                side_effect=[
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 1, "", "replacement failed"),
                ],
            ) as run_mock,
            mock.patch.object(
                stackctl,
                "activate_test_live_experiment_policies",
                return_value={
                    "status": "passed",
                    "runtimeIdentityDigest": "sha256:" + "3" * 64,
                },
            ),
            mock.patch.object(
                stackctl,
                "transition_test_live_startup_attempt",
                side_effect=transition,
            ),
        ):
            result = stackctl._start_mutable_test_live_runtime(
                environment="alpha",
                target="alpha-local",
                report_dir=Path(temporary),
                workspace_snapshot={},
            )

        self.assertEqual(
            result["blockerKind"], "mutable_compose_service_replacement_failed"
        )
        self.assertEqual(run_mock.call_count, 4)
        self.assertEqual(
            [row["status"] for row in transitions],
            ["prepared", "partial", "partial"],
        )

    def test_policy_owner_bootstrap_failure_blocks_before_full_up(self) -> None:
        rendered = {
            "plan": {
                "composeProject": "quwoquan_alpha_test_live",
                "composeDigest": "sha256:" + "1" * 64,
                "configurationDigest": "sha256:" + "2" * 64,
                "publishedPorts": {"product-ops-service": 17250},
            },
            "environment": {
                "LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS": "3600",
                "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS": "45",
            },
            "composeFiles": [Path("/repo/current/base.compose.yaml")],
            "composeProfiles": [],
        }
        transitions: list[dict[str, object]] = []

        def transition(**kwargs: object) -> dict[str, object]:
            transitions.append(kwargs)
            return {
                "attemptId": kwargs["attempt_id"],
                "status": kwargs["status"],
                "configurationDigest": "sha256:" + "2" * 64,
                "failure": kwargs.get("failure") or None,
            }

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl, "_dev_session_render_runtime_inputs", return_value=rendered
            ),
            mock.patch.object(
                stackctl,
                "run",
                side_effect=[
                    subprocess.CompletedProcess(["compose", "config"], 0, "", ""),
                    subprocess.CompletedProcess(
                        ["compose", "up", "product-ops-service"], 1, "", "owner failed"
                    ),
                ],
            ) as execute,
            mock.patch.object(
                stackctl,
                "transition_test_live_startup_attempt",
                side_effect=transition,
            ),
            mock.patch.object(
                stackctl, "activate_test_live_experiment_policies"
            ) as activate,
        ):
            result = stackctl._start_mutable_test_live_runtime(
                environment="alpha",
                target="alpha-local",
                report_dir=Path(temporary),
                workspace_snapshot={},
            )

        self.assertEqual(result["blockerKind"], "test_live_policy_owner_bootstrap_failed")
        self.assertEqual(execute.call_count, 2)
        activate.assert_not_called()
        self.assertEqual([row["status"] for row in transitions], ["prepared", "partial", "partial"])

    def test_policy_activation_failure_blocks_before_full_up(self) -> None:
        rendered = {
            "plan": {
                "composeProject": "quwoquan_alpha_test_live",
                "composeDigest": "sha256:" + "1" * 64,
                "configurationDigest": "sha256:" + "2" * 64,
                "publishedPorts": {"product-ops-service": 17250},
            },
            "environment": {
                "LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS": "3600",
                "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS": "45",
            },
            "composeFiles": [Path("/repo/current/base.compose.yaml")],
            "composeProfiles": [],
        }
        transitions: list[dict[str, object]] = []

        def transition(**kwargs: object) -> dict[str, object]:
            transitions.append(kwargs)
            return {
                "attemptId": kwargs["attempt_id"],
                "status": kwargs["status"],
                "configurationDigest": "sha256:" + "2" * 64,
                "failure": kwargs.get("failure") or None,
            }

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl, "_dev_session_render_runtime_inputs", return_value=rendered
            ),
            mock.patch.object(
                stackctl,
                "run",
                side_effect=[
                    subprocess.CompletedProcess(["compose", "config"], 0, "", ""),
                    subprocess.CompletedProcess(
                        ["compose", "up", "product-ops-service"], 0, "", ""
                    ),
                ],
            ) as execute,
            mock.patch.object(
                stackctl,
                "transition_test_live_startup_attempt",
                side_effect=transition,
            ),
            mock.patch.object(
                stackctl,
                "activate_test_live_experiment_policies",
                side_effect=stackctl.ExperimentPolicyActivationError(
                    "public command unavailable"
                ),
            ),
        ):
            result = stackctl._start_mutable_test_live_runtime(
                environment="alpha",
                target="alpha-local",
                report_dir=Path(temporary),
                workspace_snapshot={},
            )

        self.assertEqual(
            result["blockerKind"], "test_live_experiment_policy_activation_failed"
        )
        self.assertEqual(execute.call_count, 2)
        self.assertEqual([row["status"] for row in transitions], ["prepared", "partial", "partial"])

    def test_mutable_runtime_supersedes_interrupted_partial_before_retry(self) -> None:
        rendered = {
            "plan": {
                "composeProject": "quwoquan_alpha_test_live",
                "composeDigest": "sha256:" + "1" * 64,
                "configurationDigest": "sha256:" + "2" * 64,
                "publishedPorts": {"product-ops-service": 17250},
            },
            "environment": {
                "LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS": "3600",
                "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS": "45",
            },
            "composeFiles": [Path("/repo/current/base.compose.yaml")],
            "composeProfiles": [],
        }
        transitions: list[dict[str, object]] = []

        def transition(**kwargs: object) -> dict[str, object]:
            transitions.append(kwargs)
            return {
                "attemptId": kwargs["attempt_id"],
                "status": kwargs["status"],
                "configurationDigest": "sha256:" + "2" * 64,
            }

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "_dev_session_render_runtime_inputs",
                return_value=rendered,
            ),
            mock.patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                return_value={
                    "attemptId": "alpha-test-live-interrupted",
                    "status": "partial",
                    "failure": None,
                },
            ),
            mock.patch.object(
                stackctl,
                "transition_test_live_startup_attempt",
                side_effect=transition,
            ),
            mock.patch.object(
                stackctl,
                "run",
                side_effect=lambda argv, **_kwargs: subprocess.CompletedProcess(
                    argv, 0, "", ""
                ),
            ),
            mock.patch.object(
                stackctl,
                "activate_test_live_experiment_policies",
                return_value={
                    "status": "passed",
                    "runtimeIdentityDigest": "sha256:" + "3" * 64,
                },
            ),
        ):
            result = stackctl._start_mutable_test_live_runtime(
                environment="alpha",
                target="alpha-local",
                report_dir=Path(temporary),
                workspace_snapshot={},
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(
            [row["status"] for row in transitions],
            ["stopped", "prepared", "partial", "running"],
        )
        self.assertIn("explicit mutable dev-session retry", transitions[0]["failure"])
        self.assertEqual(result["phases"][2]["name"], "mutable-startup-retry")

    def test_mutable_receipt_failure_blocks_before_compose_up(self) -> None:
        rendered = {
            "plan": {
                "composeProject": "quwoquan_alpha_test_live",
                "composeDigest": "sha256:" + "1" * 64,
            },
            "environment": {
                "LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS": "3600",
                "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS": "45",
            },
            "composeFiles": [Path("/repo/current/base.compose.yaml")],
            "composeProfiles": [],
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "_dev_session_render_runtime_inputs",
                return_value=rendered,
            ),
            mock.patch.object(
                stackctl,
                "run",
                return_value=subprocess.CompletedProcess(
                    ["docker", "compose", "config"], 0, "", ""
                ),
            ) as execute,
            mock.patch.object(
                stackctl,
                "transition_test_live_startup_attempt",
                side_effect=ValueError("receipt identity invalid"),
            ),
        ):
            result = stackctl._start_mutable_test_live_runtime(
                environment="alpha",
                target="alpha-local",
                report_dir=Path(temporary),
                workspace_snapshot={},
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "mutable_startup_receipt_failed")
        execute.assert_called_once()

    def test_mutable_compose_render_failure_blocks_before_up(self) -> None:
        rendered = {
            "plan": {
                "composeProject": "quwoquan_beta_test_live",
                "composeDigest": "sha256:" + "1" * 64,
            },
            "environment": {
                "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS": "45",
            },
            "composeFiles": [Path("/repo/current/base.compose.yaml")],
            "composeProfiles": [],
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "_dev_session_render_runtime_inputs",
                return_value=rendered,
            ),
            mock.patch.object(
                stackctl,
                "run",
                return_value=subprocess.CompletedProcess(
                    ["docker", "compose", "config"],
                    1,
                    "",
                    "unsafe interpolation",
                ),
            ) as execute,
        ):
            result = stackctl._start_mutable_test_live_runtime(
                environment="beta",
                target="beta-local",
                report_dir=Path(temporary),
                workspace_snapshot={},
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "mutable_compose_render_failed")
        execute.assert_called_once()

    def test_mutable_project_and_port_profile_are_target_exact(self) -> None:
        self.assertEqual(
            stackctl._dev_session_compose_project("gamma", "gamma-local"),
            "quwoquan_gamma_test_live",
        )
        for environment, target in (
            ("prod", "prod-hosted"),
            ("alpha", "beta-local"),
        ):
            with self.subTest(environment=environment, target=target):
                with self.assertRaises(ValueError):
                    stackctl._dev_session_compose_project(environment, target)

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(
                stackctl,
                "get_target",
                return_value={"env": "alpha", "portProfile": "beta-local"},
            ),
        ):
            with self.assertRaisesRegex(ValueError, "canonical port profile"):
                stackctl._dev_session_render_runtime_inputs(
                    environment="alpha",
                    target="alpha-local",
                    report_dir=Path(temporary),
                    workspace_snapshot={},
                )

    def test_mutable_operation_identity_is_target_bound_and_non_promotable(self) -> None:
        for environment in ("alpha", "beta", "gamma"):
            target = f"{environment}-local"
            with self.subTest(environment=environment):
                identity = stackctl._mutable_test_live_operation_identity_environment(
                    environment=environment,
                    target=target,
                    mutable_state_digest="sha256:" + "1" * 64,
                    api_edge_config_version="sha256:" + "2" * 64,
                )
                self.assertEqual(
                    identity,
                    {
                        "QWQ_RELEASE_CANDIDATE_DIGEST": "sha256:" + "1" * 64,
                        "QWQ_RUNTIME_IDENTITY_SCHEMA": "stackctl.mutable_test_live_runtime.v1",
                        "QWQ_RUNTIME_LAUNCH_POLICY": "test_live",
                        "QWQ_RUNTIME_NON_PROMOTABLE": "true",
                        "QWQ_RUNTIME_ENVIRONMENT": environment,
                        "QWQ_RUNTIME_TARGET": target,
                        "QWQ_RUNTIME_MUTABLE_STATE_DIGEST": "sha256:" + "1" * 64,
                        "QWQ_RUNTIME_CONFIGURATION_DIGEST": "sha256:" + "2" * 64,
                    },
                )

        for environment, target in (
            ("prod", "prod"),
            ("alpha", "beta-local"),
        ):
            with self.subTest(environment=environment, target=target):
                with self.assertRaises(ValueError):
                    stackctl._mutable_test_live_operation_identity_environment(
                        environment=environment,
                        target=target,
                        mutable_state_digest="sha256:" + "1" * 64,
                        api_edge_config_version="sha256:" + "2" * 64,
                    )

        with self.assertRaisesRegex(ValueError, "mutable state digest"):
            stackctl._mutable_test_live_operation_identity_environment(
                environment="alpha",
                target="alpha-local",
                mutable_state_digest="sha256:stale",
                api_edge_config_version="sha256:" + "2" * 64,
            )

    def test_mutable_media_root_is_the_topology_owned_target_release_path(self) -> None:
        target_contract = {
            "env": "alpha",
            "portProfile": "alpha-local",
            "dataRelease": {
                "mode": "local-import",
                "mediaLocalRef": "cache/media",
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary) / "alpha-local"
            with mock.patch.object(
                stackctl,
                "target_local_dir",
                return_value=target_root,
            ):
                media_ref, media_root = stackctl._dev_session_target_media_root(
                    target="alpha-local",
                    target_contract=target_contract,
                )
                self.assertEqual(media_ref, "cache/media")
                self.assertEqual(
                    media_root,
                    (target_root / "cache/media").resolve(),
                )

            for unsafe_ref in ("", ".", "../media", "/tmp/media"):
                target_contract["dataRelease"]["mediaLocalRef"] = unsafe_ref
                with (
                    mock.patch.object(
                        stackctl,
                        "target_local_dir",
                        return_value=target_root,
                    ),
                    self.assertRaisesRegex(ValueError, "safe target-local path"),
                ):
                    stackctl._dev_session_target_media_root(
                        target="alpha-local",
                        target_contract=target_contract,
                    )

            target_contract["dataRelease"]["mediaLocalRef"] = "linked/media"
            (target_root / "linked").symlink_to(Path(temporary) / "outside")
            with (
                mock.patch.object(
                    stackctl,
                    "target_local_dir",
                    return_value=target_root,
                ),
                self.assertRaisesRegex(ValueError, "contains a symlink"),
            ):
                stackctl._dev_session_target_media_root(
                    target="alpha-local",
                    target_contract=target_contract,
                )

    def test_dev_session_operation_conflict_blocks_before_runtime_mutation(self) -> None:
        args = argparse.Namespace(
            command="dev-session",
            all_nonprod=False,
            env="alpha",
            target="",
            device_id="",
            launch_app=False,
            report_dir="",
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary),
            ),
            mock.patch.object(
                stackctl,
                "_local_stack_operation_lock",
                side_effect=RuntimeError("local stack operation is already running"),
            ),
            mock.patch.object(
                stackctl,
                "_run_dev_session_target",
                side_effect=AssertionError("runtime mutation must not begin"),
            ),
        ):
            result = stackctl.command_dev_session(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "runtime_operation_conflict")

    def test_mutable_session_renders_preflight_and_health_without_package(self) -> None:
        events: list[str] = []

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "command_package",
                side_effect=AssertionError("test_live must not package"),
            ),
            mock.patch.object(
                stackctl,
                "command_up",
                side_effect=AssertionError("test_live must not use immutable up"),
            ),
            mock.patch.object(
                stackctl,
                "command_app_debug_preflight",
                side_effect=lambda _args: events.append("preflight")
                or {
                    **_ok("preflight"),
                    "status": "warning",
                    "warnings": ["api-edge unavailable"],
                    "mutableWorkspaceWarnings": ["active candidate stale"],
                },
            ),
            mock.patch.object(
                stackctl,
                "command_health",
                side_effect=lambda _args: events.append("health")
                or {
                    "exitCode": 2,
                    "summary": "runtime unavailable",
                    "details": ["api-edge is not ready"],
                },
            ),
            mock.patch.object(stackctl.subprocess, "run", return_value=_handoff_completed()),
            mock.patch.object(
                stackctl,
                "_start_mutable_test_live_runtime",
                return_value=_runtime_started(),
            ),
            mock.patch.object(
                stackctl,
                "_mutable_workspace_snapshot",
                side_effect=[
                    {"sourceRevision": "a", "workspaceStatusDigest": "one"},
                    {"sourceRevision": "a", "workspaceStatusDigest": "two"},
                ],
            ),
            mock.patch.object(stackctl, "load_startup_attempt", return_value=None),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                return_value=None,
            ),
        ):
            result = stackctl._run_dev_session_target(
                environment="alpha",
                target="alpha-local",
                device_id="emulator-5554",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(events, ["preflight", "health"])
        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["sessionKind"], "mutable")
        self.assertEqual(result["launchPolicy"], "test_live")
        self.assertEqual(result["contentBindingState"], "unbound")
        self.assertTrue(result["warnings"])
        self.assertIn("./run.sh --env alpha -d emulator-5554", result["details"][0])

    def test_running_full_runtime_is_observed_but_never_repackaged(self) -> None:
        events: list[str] = []
        full_attempt = {
            "attemptId": "full-1",
            "status": "running",
            "workload": "full",
        }

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "command_package",
                side_effect=AssertionError("test_live must not package"),
            ),
            mock.patch.object(
                stackctl,
                "command_up",
                side_effect=AssertionError("hot session must not call up"),
            ),
            mock.patch.object(
                stackctl,
                "command_app_debug_preflight",
                side_effect=lambda _args: events.append("preflight")
                or {**_ok("preflight"), "status": "passed", "warnings": []},
            ),
            mock.patch.object(
                stackctl,
                "command_health",
                side_effect=lambda _args: events.append("health") or _ok("health"),
            ),
            mock.patch.object(stackctl.subprocess, "run", return_value=_handoff_completed()),
            mock.patch.object(
                stackctl,
                "_start_mutable_test_live_runtime",
                return_value=_runtime_started("beta", "beta-local"),
            ),
            mock.patch.object(
                stackctl,
                "_mutable_workspace_snapshot",
                return_value={"sourceRevision": "a", "workspaceStatusDigest": "same"},
            ),
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                side_effect=lambda target: (
                    full_attempt if target == "beta-local" else None
                ),
            ),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                side_effect=lambda target, workload: (
                    full_attempt
                    if target == "beta-local" and workload == "full"
                    else None
                ),
            ),
        ):
            result = stackctl._run_dev_session_target(
                environment="beta",
                target="beta-local",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["sessionKind"], "mutable")
        self.assertTrue(result["fullRuntimeSelected"])
        self.assertEqual(events, ["preflight", "health"])
        self.assertEqual(
            [phase["name"] for phase in result["phases"]],
            [
                "mutable-materialize",
                "compose-render",
                "compose-up",
                "preflight",
                "launcher-handoff",
                "health",
            ],
        )

    def test_running_bounded_workload_blocks_before_package(self) -> None:
        for workload in ("content-release", "content-commercial"):
            with self.subTest(workload=workload):
                attempt = {
                    "attemptId": f"{workload}-1",
                    "status": "running",
                    "workload": workload,
                }
                with (
                    tempfile.TemporaryDirectory() as temporary,
                    mock.patch.object(
                        stackctl,
                        "command_package",
                        side_effect=AssertionError("package must be skipped"),
                    ),
                    mock.patch.object(
                        stackctl,
                        "command_up",
                        side_effect=AssertionError("up must be skipped"),
                    ),
                    mock.patch.object(
                        stackctl,
                        "command_health",
                        side_effect=AssertionError("health must be skipped"),
                    ),
                    mock.patch.object(
                        stackctl,
                        "load_startup_attempt",
                        side_effect=lambda target: (
                            attempt if target == "alpha-local" else None
                        ),
                    ),
                    mock.patch.object(
                        stackctl,
                        "load_workload_startup_attempt",
                        side_effect=lambda target, scoped_workload: (
                            attempt
                            if target == "alpha-local"
                            and scoped_workload == workload
                            else None
                        ),
                    ),
                ):
                    result = stackctl._run_dev_session_target(
                        environment="alpha",
                        target="alpha-local",
                        device_id="",
                        launch_app_requested=False,
                        report_dir=Path(temporary),
                    )

                self.assertEqual(result["exitCode"], 2)
                self.assertEqual(
                    result["blockerKind"],
                    "runtime_workload_conflict",
                )
                self.assertEqual(result["activeRuntime"]["workload"], workload)
                self.assertEqual(
                    result["activeRuntime"]["attemptId"],
                    f"{workload}-1",
                )
                self.assertIn(
                    f"down --target alpha-local --workload {workload}",
                    result["details"][-1],
                )
                self.assertEqual(result["phases"], [])

    def test_stale_startup_receipt_is_warning_for_test_live(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "_dev_session_runtime_preflight",
                side_effect=ValueError("startup attempt target identity mismatch"),
            ),
            mock.patch.object(stackctl.subprocess, "run", return_value=_handoff_completed()),
            mock.patch.object(
                stackctl,
                "_start_mutable_test_live_runtime",
                return_value=_runtime_started(),
            ),
            mock.patch.object(
                stackctl,
                "command_app_debug_preflight",
                return_value={**_ok("preflight"), "status": "passed", "warnings": []},
            ),
            mock.patch.object(stackctl, "command_health", return_value=_ok("health")),
            mock.patch.object(
                stackctl,
                "_mutable_workspace_snapshot",
                return_value={"sourceRevision": "a", "workspaceStatusDigest": "same"},
            ),
        ):
            result = stackctl._run_dev_session_target(
                environment="alpha",
                target="alpha-local",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["status"], "warning")
        self.assertIn("stale runtime receipt ignored", result["warnings"][0])

    def test_stopped_bounded_receipt_allows_mutable_session(self) -> None:
        events: list[str] = []
        stopped = {
            "attemptId": "content-release-old",
            "status": "stopped",
            "workload": "content-release",
        }

        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "command_package",
                side_effect=AssertionError("test_live must not package"),
            ),
            mock.patch.object(
                stackctl,
                "command_up",
                side_effect=AssertionError("test_live must not use immutable up"),
            ),
            mock.patch.object(
                stackctl,
                "command_app_debug_preflight",
                side_effect=lambda _args: events.append("preflight")
                or {**_ok("preflight"), "status": "passed", "warnings": []},
            ),
            mock.patch.object(
                stackctl,
                "command_health",
                side_effect=lambda _args: events.append("health") or _ok("health"),
            ),
            mock.patch.object(stackctl.subprocess, "run", return_value=_handoff_completed()),
            mock.patch.object(
                stackctl,
                "_start_mutable_test_live_runtime",
                return_value=_runtime_started("gamma", "gamma-local"),
            ),
            mock.patch.object(
                stackctl,
                "_mutable_workspace_snapshot",
                return_value={"sourceRevision": "a", "workspaceStatusDigest": "same"},
            ),
            mock.patch.object(stackctl, "load_startup_attempt", return_value=None),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                side_effect=lambda target, workload: (
                    stopped
                    if target == "gamma-local" and workload == "content-release"
                    else None
                ),
            ),
        ):
            result = stackctl._run_dev_session_target(
                environment="gamma",
                target="gamma-local",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["sessionKind"], "mutable")
        self.assertEqual(events, ["preflight", "health"])

    def test_active_workload_receipt_blocks_when_target_receipt_is_stale(self) -> None:
        scoped_attempt = {
            "attemptId": "content-release-scoped-1",
            "status": "running",
            "workload": "content-release",
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "command_package",
                side_effect=AssertionError("package must be skipped"),
            ),
            mock.patch.object(stackctl, "load_startup_attempt", return_value=None),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                side_effect=lambda target, workload: (
                    scoped_attempt
                    if target == "alpha-local" and workload == "content-release"
                    else None
                ),
            ),
        ):
            result = stackctl._run_dev_session_target(
                environment="alpha",
                target="alpha-local",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "runtime_workload_conflict")
        self.assertEqual(
            result["activeRuntime"]["receiptScope"],
            "workload:content-release",
        )

    def test_invalid_mutable_handoff_stops_after_running_before_health(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    args=["build_launcher_handoff.py"],
                    returncode=2,
                    stdout="",
                    stderr="unsafe production endpoint",
                ),
            ),
            mock.patch.object(stackctl, "_mutable_workspace_snapshot", return_value={}),
            mock.patch.object(
                stackctl,
                "_dev_session_runtime_preflight",
                return_value=(None, None),
            ),
            mock.patch.object(
                stackctl,
                "_start_mutable_test_live_runtime",
                return_value=_runtime_started(),
            ),
            mock.patch.object(
                stackctl,
                "command_app_debug_preflight",
                return_value={**_ok("preflight"), "status": "passed", "warnings": []},
            ),
            mock.patch.object(
                stackctl,
                "command_health",
                side_effect=AssertionError("health must be skipped"),
            ),
            mock.patch.object(stackctl, "load_startup_attempt", return_value=None),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                return_value=None,
            ),
        ):
            result = stackctl._run_dev_session_target(
                environment="gamma",
                target="gamma-local",
                device_id="",
                launch_app_requested=False,
                report_dir=Path(temporary),
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "launcher_handoff_invalid")
        self.assertIn("unsafe production endpoint", result["details"][0])

    def test_all_nonprod_is_serial_and_failure_stops_later_targets(self) -> None:
        visited: list[str] = []
        def run_target(**kwargs: object) -> dict[str, object]:
            target = str(kwargs["target"])
            visited.append(target)
            if target == "beta-local":
                return {
                    "exitCode": 2,
                    "sessionKind": "cold",
                    "blockerKind": "runtime_health_failed",
                    "details": ["beta failed"],
                    "fullRuntimeSelected": False,
                    "phases": [],
                }
            return {
                "exitCode": 0,
                "sessionKind": "cold",
                "blockerKind": "",
                "details": [],
                "fullRuntimeSelected": True,
                "phases": [],
            }

        args = argparse.Namespace(
            command="dev-session",
            all_nonprod=True,
            env="",
            target="",
            device_id="",
            launch_app=False,
            report_dir="",
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary),
            ),
            mock.patch.object(
                stackctl,
                "_local_stack_operation_lock",
                return_value=contextlib.nullcontext(),
            ),
            mock.patch.object(stackctl, "_run_dev_session_target", side_effect=run_target),
            mock.patch.object(
                stackctl,
                "command_down",
                side_effect=AssertionError("mutable dev-session must not auto-down"),
            ),
        ):
            result = stackctl.command_dev_session(args)

        self.assertEqual(visited, ["alpha-local", "beta-local"])
        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "runtime_health_failed")

    def test_all_nonprod_cross_target_bounded_conflict_preserves_runtime(self) -> None:
        bounded_attempt = {
            "attemptId": "commercial-beta-1",
            "status": "running",
            "workload": "content-commercial",
        }
        args = argparse.Namespace(
            command="dev-session",
            all_nonprod=True,
            env="",
            target="",
            device_id="",
            launch_app=False,
            report_dir="",
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary),
            ),
            mock.patch.object(
                stackctl,
                "_local_stack_operation_lock",
                return_value=contextlib.nullcontext(),
            ),
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                side_effect=lambda target: (
                    bounded_attempt if target == "beta-local" else None
                ),
            ),
            mock.patch.object(
                stackctl,
                "load_workload_startup_attempt",
                side_effect=lambda target, workload: (
                    bounded_attempt
                    if target == "beta-local"
                    and workload == "content-commercial"
                    else None
                ),
            ),
            mock.patch.object(
                stackctl,
                "command_package",
                side_effect=AssertionError("package must be skipped"),
            ),
            mock.patch.object(
                stackctl,
                "command_down",
                side_effect=AssertionError("active bounded runtime must not be downed"),
            ),
        ):
            result = stackctl.command_dev_session(args)

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "runtime_workload_conflict")
        self.assertEqual(len(result["sessions"]), 1)
        self.assertEqual(result["sessions"][0]["target"], "alpha-local")
        self.assertEqual(
            result["sessions"][0]["activeRuntime"],
            {
                "target": "beta-local",
                "workload": "content-commercial",
                "attemptId": "commercial-beta-1",
                "status": "running",
                "receiptScope": "target",
            },
        )

    def test_bounded_workload_reuses_full_and_targeted_down_is_noop(self) -> None:
        fixed_identity = {
            "candidateDigest": "sha256:" + "1" * 64,
            "configurationDigest": "sha256:" + "2" * 64,
            "providerRuntimeDigest": "sha256:" + "3" * 64,
            "observabilityLogSinkDigest": "sha256:" + "4" * 64,
            "imageComposition": {"identity": "full-oci"},
        }
        full_attempt = {
            "attemptId": "full-1",
            "status": "running",
            "workload": "full",
            **fixed_identity,
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary),
            ),
            mock.patch.object(
                stackctl,
                "command_health",
                return_value={"exitCode": 0, "details": ["full health ok"]},
            ),
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value=full_attempt,
            ),
            mock.patch.object(
                stackctl,
                "_fixed_candidate_runtime_identity",
                return_value=fixed_identity,
            ),
            mock.patch.object(
                stackctl,
                "assert_active_deployment_candidate_snapshot",
            ),
        ):
            reused = stackctl._reuse_running_full_for_bounded_workload(
                argparse.Namespace(workload="content-release"),
                candidate_snapshot={"baselineId": fixed_identity["candidateDigest"]},
                target_name="alpha-local",
                env_name="alpha",
                report_target="alpha-local",
                report_dir=Path(temporary) / "up",
                started_monotonic=0.0,
                started_at="2026-01-01T00:00:00Z",
            )
            down = stackctl._bounded_workload_down_decision(
                argparse.Namespace(
                    target="alpha-local",
                    workload="content-release",
                    report_dir=str(Path(temporary) / "down"),
                )
            )

        self.assertIsNotNone(reused)
        self.assertTrue(reused["runtimeReused"])
        self.assertIsNotNone(down)
        self.assertTrue(down["runtimeReused"])
        self.assertEqual(full_attempt["status"], "running")

    def test_fixed_runtime_identity_uses_one_snapshot_for_every_component(
        self,
    ) -> None:
        baseline_id = "sha256:" + "1" * 64
        candidate_root = Path("/candidate/alpha")
        snapshot = {"baselineId": baseline_id, "manifest": {}}
        startup_images = {
            "environment": "alpha",
            "target": "alpha-local",
            "imageVersion": "sha256:" + "5" * 64,
            "images": {"api": "sha256:" + "6" * 64},
        }
        provider = {
            "composition": {"runtimeCompositionDigest": "sha256:" + "3" * 64}
        }
        observability = {
            "composition": {"composeDigest": "sha256:" + "4" * 64}
        }
        with (
            mock.patch.object(
                stackctl,
                "_fixed_candidate_identity",
                return_value=(baseline_id, candidate_root, {}),
            ) as fixed_identity,
            mock.patch.object(
                stackctl,
                "_candidate_bindings_from_snapshot",
                return_value=(provider, observability),
            ) as candidate_bindings,
            mock.patch.object(
                stackctl,
                "_load_package_bound_local_image_composition",
                return_value={
                    "configurationDigest": "sha256:" + "2" * 64,
                    "startupImageComposition": startup_images,
                },
            ) as image_composition,
        ):
            actual = stackctl._fixed_candidate_runtime_identity(
                snapshot,
                environment_name="alpha",
                target_name="alpha-local",
            )

        self.assertEqual(
            actual,
            {
                "candidateDigest": baseline_id,
                "configurationDigest": "sha256:" + "2" * 64,
                "providerRuntimeDigest": "sha256:" + "3" * 64,
                "observabilityLogSinkDigest": "sha256:" + "4" * 64,
                "imageComposition": startup_images,
            },
        )
        fixed_identity.assert_called_once_with(
            snapshot,
            environment_name="alpha",
            target_name="alpha-local",
        )
        candidate_bindings.assert_called_once_with(
            snapshot,
            environment_name="alpha",
            target_name="alpha-local",
        )
        image_composition.assert_called_once_with(
            "alpha",
            "alpha-local",
            candidate_snapshot=snapshot,
        )

    def test_bounded_workload_rejects_receipt_identity_drift_and_pointer_switch(
        self,
    ) -> None:
        expected = {
            "candidateDigest": "sha256:" + "1" * 64,
            "configurationDigest": "sha256:" + "2" * 64,
            "providerRuntimeDigest": "sha256:" + "3" * 64,
            "observabilityLogSinkDigest": "sha256:" + "4" * 64,
            "imageComposition": {"identity": "full-oci"},
        }
        snapshot = {"baselineId": expected["candidateDigest"]}
        for field in expected:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                receipt = {
                    "attemptId": "full-1",
                    "status": "running",
                    "workload": "full",
                    **expected,
                }
                receipt[field] = None
                with (
                    mock.patch.object(
                        stackctl,
                        "load_startup_attempt",
                        return_value=receipt,
                    ),
                    mock.patch.object(
                        stackctl,
                        "_fixed_candidate_runtime_identity",
                        return_value=expected,
                    ),
                    mock.patch.object(
                        stackctl,
                        "assert_active_deployment_candidate_snapshot",
                    ) as snapshot_check,
                    mock.patch.object(stackctl, "_write_summary_bundle"),
                ):
                    result = stackctl._reuse_running_full_for_bounded_workload(
                        argparse.Namespace(workload="content-release"),
                        candidate_snapshot=snapshot,
                        target_name="alpha-local",
                        env_name="alpha",
                        report_target="alpha-local",
                        report_dir=Path(temporary),
                        started_monotonic=0.0,
                        started_at="2026-01-01T00:00:00Z",
                    )

                self.assertEqual(result["exitCode"], 2)
                self.assertEqual(
                    result["blockerKind"],
                    "candidate_identity_mismatch",
                )
                snapshot_check.assert_not_called()

        with tempfile.TemporaryDirectory() as temporary, (
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value={
                    "attemptId": "full-1",
                    "status": "running",
                    "workload": "full",
                    **expected,
                },
            )
        ), mock.patch.object(
            stackctl,
            "_fixed_candidate_runtime_identity",
            return_value=expected,
        ), mock.patch.object(
            stackctl,
            "assert_active_deployment_candidate_snapshot",
            side_effect=ValueError("pointer switched"),
        ), mock.patch.object(stackctl, "_write_summary_bundle"):
            result = stackctl._reuse_running_full_for_bounded_workload(
                argparse.Namespace(workload="content-release"),
                candidate_snapshot=snapshot,
                target_name="alpha-local",
                env_name="alpha",
                report_target="alpha-local",
                report_dir=Path(temporary),
                started_monotonic=0.0,
                started_at="2026-01-01T00:00:00Z",
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "candidate_pointer_changed")

    def test_bounded_workload_rejects_unhealthy_full_runtime(self) -> None:
        expected = {
            "candidateDigest": "sha256:" + "1" * 64,
            "configurationDigest": "sha256:" + "2" * 64,
            "providerRuntimeDigest": "sha256:" + "3" * 64,
            "observabilityLogSinkDigest": "sha256:" + "4" * 64,
            "imageComposition": {"identity": "full-oci"},
        }
        with tempfile.TemporaryDirectory() as temporary, (
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value={
                    "attemptId": "full-1",
                    "status": "running",
                    "workload": "full",
                    **expected,
                },
            )
        ), mock.patch.object(
            stackctl,
            "_fixed_candidate_runtime_identity",
            return_value=expected,
        ), mock.patch.object(
            stackctl,
            "assert_active_deployment_candidate_snapshot",
        ), mock.patch.object(
            stackctl,
            "command_health",
            return_value={
                "exitCode": 2,
                "details": ["api-edge healthz failed"],
            },
        ), mock.patch.object(stackctl, "_write_summary_bundle"):
            result = stackctl._reuse_running_full_for_bounded_workload(
                argparse.Namespace(workload="content-release"),
                candidate_snapshot={"baselineId": expected["candidateDigest"]},
                target_name="alpha-local",
                env_name="alpha",
                report_target="alpha-local",
                report_dir=Path(temporary),
                started_monotonic=0.0,
                started_at="2026-01-01T00:00:00Z",
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "runtime_health_failed")


if __name__ == "__main__":
    unittest.main()

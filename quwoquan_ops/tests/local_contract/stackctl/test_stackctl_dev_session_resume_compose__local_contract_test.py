"""dev-session 精确恢复与 mutable compose 物化/投影语义。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
spec_ref: specs/feature-tree/runtime/runtime-config/environment-ops-cli-and-skill/spec.md#gwt-001
"""
from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl

from quwoquan_ops.tests.support.stackctl_dev_session_test_support import (
    _ok,
    _handoff_completed,
    _runtime_started,
    _runtime_started_with_identity,
    StackctlDevSessionTestBase,
)


class StackctlDevSessionResumeComposeTest(StackctlDevSessionTestBase):
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
                            "service-core": {
                                "environment": {"IMAGE_VERSION": "${IMAGE_VERSION}"},
                                "depends_on": {
                                    "mongo-init": {
                                        "condition": "service_completed_successfully"
                                    },
                                    "postgres": {"condition": "service_healthy"},
                                },
                            },
                            "sms-provider-substitute": {
                                "environment": {
                                    "SMS_SUBSTITUTE_CONFIGURATION_DIGEST": "${DIGEST}"
                                }
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
                            "elasticsearch": {
                                "image": "quwoquan/elasticsearch-cjk:8.13.4",
                                "healthcheck": {"test": ["CMD", "true"]},
                            },
                            "platform-ops-service": {
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
                ("service-core", "sms-provider-substitute")
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
                "recommendation-service",
                "platform-ops-service",
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
                            if service == "platform-ops-service"
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
                    {
                        # This repository-owned, version-pinned infrastructure
                        # image is not rebuilt from the mutable workspace.
                        "Created": "2026-08-09T00:00:05Z",
                        "Config": {
                            "Image": "quwoquan/elasticsearch-cjk:8.13.4",
                            "Env": [],
                            "Labels": {
                                "com.docker.compose.project": "quwoquan_alpha_test_live",
                                "com.docker.compose.service": "elasticsearch",
                                "com.docker.compose.config-hash": "hash-elasticsearch",
                            },
                        },
                        "State": {
                            "Status": "running",
                            "Health": {"Status": "healthy"},
                        },
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
                any("platform-ops-service status=exited" in row for row in warnings)
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
                "quwoquan/test-live-alpha-local-service-core:" + "9" * 16
            )
            assert_rejected(wrong_image, "image ref drifted: service-core")

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
                "service-core",
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
            # symlink TMPDIR（macOS /var -> /private/var）下两侧展开程度可能不同，比较前归一。
            self.assertEqual(
                Path(payload["services"]["api"]["build"]["context"]).resolve(),
                build_context.resolve(),
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
                Path(payload["services"]["api"]["build"]["context"]).resolve(),
                (root / "service").resolve(),
            )

    def test_mutable_compose_execution_copy_resolves_relative_bind_sources(self) -> None:
        with tempfile.TemporaryDirectory(dir=stackctl.output_root()) as temporary:
            root = Path(temporary)
            source_dir = root / "service/deploy"
            source_dir.mkdir(parents=True)
            policy = root / "ops/policy.yaml"
            policy.parent.mkdir(parents=True)
            policy.write_text("schema: test\n", encoding="utf-8")
            source = source_dir / "compose.yaml"
            source.write_text(
                "services:\n"
                "  product-ops-service:\n"
                "    volumes:\n"
                "      - ../../ops/policy.yaml:/etc/qwq/policy.yaml:ro\n",
                encoding="utf-8",
            )

            with mock.patch.object(stackctl, "ROOT", root):
                outputs = stackctl._dev_session_materialize_compose_files(
                    [source],
                    destination_root=root / "rendered",
                )

            payload = json.loads(outputs[0].read_text(encoding="utf-8"))
            [bind] = payload["services"]["product-ops-service"]["volumes"]
            bind_source, bind_rest = bind.split(":", 1)
            self.assertEqual(Path(bind_source).resolve(), policy.resolve())
            self.assertEqual(bind_rest, "/etc/qwq/policy.yaml:ro")

    def test_product_ops_policy_bind_resolves_from_canonical_source(self) -> None:
        source = (
            stackctl.ROOT
            / "quwoquan_service/services/product-ops-service/deploy/compose.yaml"
        )
        expected = (
            stackctl.ROOT
            / "quwoquan_ops/observability/elasticsearch/product_telemetry_alerts.yaml"
        ).resolve()
        base = (
            stackctl.ROOT
            / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
        )
        with tempfile.TemporaryDirectory(dir=stackctl.output_root()) as temporary:
            outputs = stackctl._dev_session_materialize_compose_files(
                [base, source],
                destination_root=Path(temporary) / "rendered",
            )

            payload = json.loads(outputs[1].read_text(encoding="utf-8"))

        volumes = payload["services"]["product-ops-service"]["volumes"]
        self.assertIn(
            f"{expected}:/etc/qwq/observability/product_telemetry_alerts.yaml:ro",
            volumes,
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
            self.assertNotIn("content-service", payload["services"])
            dependencies = payload["services"]["service-core"]["depends_on"]
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
        self.assertEqual(len(executions), 7)
        self.assertEqual(timeouts, [90.0, *([3600.0] * 6)])
        for command in executions:
            self.assertEqual(command[:5], ["docker", "compose", "-p", "quwoquan_alpha_test_live", "-f"])
            self.assertNotIn("package", command)
            self.assertNotIn("candidate", " ".join(command))
        self.assertEqual(executions[0][-2:], ["config", "--quiet"])
        # The policy owner is brought up in three staged steps before the
        # project-wide build, because Recommendation refuses a full runtime
        # until Product Ops has published the run-bound policy facts.
        self.assertEqual(
            executions[1][-9:],
            [
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "45",
                "postgres",
                "mongodb",
                "redis",
                "elasticsearch",
            ],
        )
        self.assertEqual(executions[2][-3:], ["up", "--no-deps", "mongo-init"])
        self.assertEqual(
            executions[3][-5:],
            ["up", "--build", "-d", "--no-deps", "product-ops-service"],
        )
        self.assertEqual(executions[4][-1:], ["build"])
        self.assertEqual(executions[5][-3:], ["up", "-d", "--no-deps"])
        self.assertEqual(executions[6][-3:], ["up", "-d", "--remove-orphans"])
        self.assertEqual(
            [row["status"] for row in receipt_transitions],
            ["prepared", "partial", "running"],
        )
        self.assertEqual(result["startupAttempt"]["status"], "running")

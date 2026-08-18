"""dev-session mutable 启动失败闭环: compose/policy/receipt/handoff 各阶段 fail-fast 语义。

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


class StackctlDevSessionMutableStartupGateTest(StackctlDevSessionTestBase):
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
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "", ""),
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
        self.assertEqual(run_mock.call_count, 5)
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
        self.assertEqual(run_mock.call_count, 6)
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
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "", ""),
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
        self.assertEqual(execute.call_count, 4)
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertIn("--wait", commands[1])
        self.assertNotIn("service-core", commands[1])
        self.assertNotIn("recommendation-service", commands[1])
        self.assertEqual(commands[2][-3:], ["up", "--no-deps", "mongo-init"])
        self.assertEqual(
            commands[3][-4:],
            ["--build", "-d", "--no-deps", "product-ops-service"],
        )
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
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "", ""),
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
        self.assertEqual(execute.call_count, 4)
        self.assertEqual([row["status"] for row in transitions], ["prepared", "partial", "partial"])

    def test_mutable_runtime_blocks_retry_until_partial_receipt_is_stopped(self) -> None:
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
                    "runRoot": str(Path(temporary) / "interrupted-run"),
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

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "mutable_startup_attempt_active")
        self.assertEqual(transitions, [])
        self.assertIn(
            "attemptId=alpha-test-live-interrupted",
            result["details"],
        )
        self.assertIn(
            "status=partial",
            result["details"],
        )
        self.assertTrue(
            any(detail.endswith("down --target alpha-local") for detail in result["details"])
        )

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
                        "QWQ_RUNTIME_IDENTITY_SCHEMA": "stackctl.mutable_test_live_runtime",
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
                # 无 sha256: 前缀的非 canonical digest，必须被拒绝。
                mutable_state_digest="not-a-canonical-digest",
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

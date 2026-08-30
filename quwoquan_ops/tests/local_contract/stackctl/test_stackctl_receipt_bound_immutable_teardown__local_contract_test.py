"""Receipt-bound immutable local teardown contracts.

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import inspect
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.data_execution_fleet import load_data_execution_fleet_config
from quwoquan_ops.cli.lib.port_manifest import load_port_manifest, profile_ports


def _running_attempt(
    candidate_digest: str,
    *,
    environment: str = "alpha",
    target: str = "alpha-local",
) -> dict[str, object]:
    return {
        "schema": "stackctl-local-startup-attempt",
        "status": "running",
        "env": environment,
        "target": target,
        "workload": "full",
        "attemptId": "attempt-alpha-receipt-bound",
        "candidateDigest": candidate_digest,
        "providerRuntimeDigest": "sha256:" + "2" * 64,
        "observabilityLogSinkDigest": "sha256:" + "3" * 64,
    }


def _stopped_attempt(candidate_digest: str) -> dict[str, object]:
    attempt = _running_attempt(candidate_digest)
    attempt["status"] = "stopped"
    return attempt


def _down_args(
    report_dir: Path,
    *,
    target: str = "alpha-local",
) -> argparse.Namespace:
    return argparse.Namespace(
        target=target,
        workload="full",
        formal_release=False,
        release_manifest="",
        purge_rebuildable_state=False,
        report_dir=str(report_dir),
    )


class StackctlReceiptBoundImmutableTeardownTest(unittest.TestCase):
    def test_published_endpoint_probe_is_transport_exact_and_udp_errors_fail_closed(
        self,
    ) -> None:
        tcp_endpoint = {
            "role": "coturn",
            "hostPort": 17180,
            "protocol": "tcp",
        }
        with mock.patch.object(stackctl, "socket_probe", return_value=True) as tcp_probe:
            self.assertTrue(stackctl._published_endpoint_is_occupied(tcp_endpoint))
        tcp_probe.assert_called_once_with(17180)

        tcp_socket = mock.MagicMock()
        tcp_socket.__enter__.return_value = tcp_socket
        tcp_socket.connect_ex.return_value = errno.EACCES
        with (
            mock.patch.object(stackctl.socket, "socket", return_value=tcp_socket),
            self.assertRaisesRegex(RuntimeError, "TCP published endpoint probe failed"),
        ):
            stackctl._published_endpoint_is_occupied(tcp_endpoint)

        tcp_socket.connect_ex.return_value = errno.ECONNREFUSED
        with mock.patch.object(stackctl.socket, "socket", return_value=tcp_socket):
            self.assertFalse(stackctl._published_endpoint_is_occupied(tcp_endpoint))
        tcp_socket.connect_ex.assert_called_with(("127.0.0.1", 17180))

        tcp_socket.connect_ex.return_value = 0
        with mock.patch.object(stackctl.socket, "socket", return_value=tcp_socket):
            self.assertTrue(stackctl._published_endpoint_is_occupied(tcp_endpoint))

        udp_endpoint = {
            "role": "coturn",
            "hostPort": 17180,
            "protocol": "udp",
        }
        udp_socket = mock.MagicMock()
        udp_socket.__enter__.return_value = udp_socket
        udp_socket.bind.side_effect = OSError(errno.EADDRINUSE, "address in use")
        with mock.patch.object(stackctl.socket, "socket", return_value=udp_socket):
            self.assertTrue(stackctl._published_endpoint_is_occupied(udp_endpoint))
        udp_socket.bind.assert_called_once_with(("127.0.0.1", 17180))

        udp_socket.bind.side_effect = OSError(errno.EACCES, "permission denied")
        with (
            mock.patch.object(stackctl.socket, "socket", return_value=udp_socket),
            self.assertRaisesRegex(RuntimeError, "UDP published endpoint probe failed"),
        ):
            stackctl._published_endpoint_is_occupied(udp_endpoint)

    def test_endpoint_wait_preserves_udp_only_residue_and_transport_identity(
        self,
    ) -> None:
        endpoints = [
            {"role": "coturn", "hostPort": 17180, "protocol": "tcp"},
            {"role": "coturn", "hostPort": 17180, "protocol": "udp"},
        ]
        with (
            mock.patch.object(
                stackctl,
                "_published_endpoint_is_occupied",
                side_effect=[True, True, False, False],
            ),
            mock.patch.object(stackctl.time, "monotonic", side_effect=[0.0, 0.0, 0.1]),
            mock.patch.object(stackctl.time, "sleep") as sleep,
        ):
            occupied = stackctl._wait_for_published_endpoints_released(
                endpoints,
                timeout_seconds=1.0,
                poll_interval_seconds=0.01,
            )
        self.assertEqual(occupied, [])
        sleep.assert_called_once_with(0.01)

        udp_only = [endpoints[1]]
        with (
            mock.patch.object(
                stackctl,
                "_published_endpoint_is_occupied",
                return_value=True,
            ),
            mock.patch.object(stackctl.time, "monotonic", side_effect=[0.0, 0.0]),
        ):
            occupied = stackctl._wait_for_published_endpoints_released(
                udp_only,
                timeout_seconds=0.0,
            )
        self.assertEqual(occupied, udp_only)

    def test_runtime_owned_endpoints_exclude_independent_data_fleet_ports(
        self,
    ) -> None:
        manifest = load_port_manifest()
        canonical_ports = profile_ports(manifest, "beta-local")
        fleet = load_data_execution_fleet_config()
        runtime_endpoint = {
            "role": "api-edge",
            "hostPort": canonical_ports["api-edge"],
            "protocol": "tcp",
        }
        fleet_endpoints = [
            {
                "role": role,
                "hostPort": canonical_ports[role],
                "protocol": "tcp",
            }
            for role in (fleet.mongo_port_role, fleet.redis_port_role)
        ]

        projected = stackctl._project_target_runtime_owned_ports(
            "beta-local",
            published_ports=[runtime_endpoint, *fleet_endpoints],
            manifest=manifest,
        )

        self.assertEqual(projected, [runtime_endpoint])

    def test_bind_projects_exact_receipt_candidate_root_without_active_fallback(
        self,
    ) -> None:
        receipt_candidate = "sha256:" + "1" * 64
        switched_active_candidate = "sha256:" + "9" * 64
        runtime_composition = {
            "configurationDigest": "sha256:" + "4" * 64,
            "images": {},
        }
        environment: dict[str, str] = {}
        with tempfile.TemporaryDirectory() as temporary:
            candidate_root = (Path(temporary) / "receipt-candidate").resolve()
            with (
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=_running_attempt(receipt_candidate),
                ),
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    return_value=candidate_root,
                ),
                mock.patch.object(
                    stackctl,
                    "load_candidate_manifest",
                    return_value={"baselineId": receipt_candidate},
                ) as load_manifest,
                mock.patch.object(
                    stackctl,
                    "_candidate_provider_runtime",
                    return_value={
                        "candidateRoot": candidate_root,
                        "providerRuntime": {"composition": {}},
                    },
                ) as candidate_provider,
                mock.patch.object(
                    stackctl,
                    "_provider_runtime_launch_environment",
                    return_value={
                        "QWQ_PROVIDER_RUNTIME_DIGEST": "sha256:" + "2" * 64
                    },
                ) as provider_environment,
                mock.patch.object(
                    stackctl,
                    "_candidate_observability_log_sink",
                    return_value={
                        "candidateRoot": candidate_root,
                        "composition": {},
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_observability_log_sink_launch_environment",
                    return_value={
                        "QWQ_OBSERVABILITY_LOG_SINK_DIGEST": "sha256:" + "3" * 64
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_load_gamma_runtime_image_composition",
                    return_value=(runtime_composition, "quwoquan_alpha_release"),
                ),
                mock.patch.object(stackctl, "_apply_gamma_image_composition"),
                mock.patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    return_value={"baselineId": switched_active_candidate},
                ) as active_candidate,
            ):
                bound = stackctl._bind_local_teardown_runtime(
                    env_name="alpha",
                    target_name="alpha-local",
                    environment=environment,
                    purge_rebuildable_state=False,
                )

        self.assertEqual(bound[1], "runtime-receipt")
        self.assertEqual(
            environment[stackctl.RUNTIME_CANDIDATE_ROOT_ENV],
            str(candidate_root),
        )
        self.assertEqual(
            environment["QWQ_RELEASE_CANDIDATE_DIGEST"],
            receipt_candidate,
        )
        candidate_provider.assert_called_once_with(
            "alpha",
            "alpha-local",
            receipt_candidate,
            candidate_manifest={"baselineId": receipt_candidate},
            candidate_root=candidate_root,
        )
        # teardown 读的是回执记下的那个候选包，它可能早于当前 ContractGraph；
        # 专用用途保持完整候选字节校验，只允许退出历史 non-prod-sim 候选时投影
        # 新增的 nullable appLaunchBundle 字段。
        load_manifest.assert_called_once_with(
            "alpha",
            "alpha-local",
            receipt_candidate,
            require_full=True,
            purpose="teardown",
        )
        provider_environment.assert_called_once_with(
            {"composition": {}},
            candidate_root=candidate_root,
            workload="full",
        )
        active_candidate.assert_not_called()

    def test_purging_rebuildable_state_binds_a_rolled_back_stopped_receipt(
        self,
    ) -> None:
        """启动失败会自己回滚成 stopped，但挡住下次启动的卷还在原处。

        把 stopped 一并拒掉，唯一受支持的清理入口就只在不需要它的时候可用。
        """
        receipt_candidate = "sha256:" + "1" * 64
        environment: dict[str, str] = {}
        with tempfile.TemporaryDirectory() as temporary:
            candidate_root = (Path(temporary) / "receipt-candidate").resolve()
            with self._bound_teardown_dependencies(
                receipt_candidate,
                candidate_root,
                attempt=_stopped_attempt(receipt_candidate),
            ):
                bound = stackctl._bind_local_teardown_runtime(
                    env_name="alpha",
                    target_name="alpha-local",
                    environment=environment,
                    purge_rebuildable_state=True,
                )

        self.assertEqual(bound[1], "runtime-receipt")
        # 清理仍绑定回执身份，不是盲删：Compose 项目来自刚被拆掉的那次运行。
        self.assertEqual(bound[2], "quwoquan_alpha_release")
        self.assertEqual(environment["QWQ_RELEASE_CANDIDATE_DIGEST"], receipt_candidate)

    def test_plain_teardown_still_requires_a_non_stopped_receipt(self) -> None:
        """不带清理的 down 对已停止的运行时无事可做，判据保持收紧。"""
        receipt_candidate = "sha256:" + "1" * 64
        with (
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value=_stopped_attempt(receipt_candidate),
            ),
            self.assertRaisesRegex(ValueError, "non-stopped canonical startup receipt"),
        ):
            stackctl._bind_local_teardown_runtime(
                env_name="alpha",
                target_name="alpha-local",
                environment={},
                purge_rebuildable_state=False,
            )

    def test_missing_receipt_is_refused_even_when_purging(self) -> None:
        """回执缺席时没有可绑定的身份，清理必须转显式 repair 而不是盲删。"""
        with (
            mock.patch.object(stackctl, "load_startup_attempt", return_value=None),
            self.assertRaisesRegex(ValueError, "canonical startup receipt"),
        ):
            stackctl._bind_local_teardown_runtime(
                env_name="alpha",
                target_name="alpha-local",
                environment={},
                purge_rebuildable_state=True,
            )

    @contextlib.contextmanager
    def _bound_teardown_dependencies(
        self,
        receipt_candidate: str,
        candidate_root: Path,
        *,
        attempt: dict[str, object],
    ):
        with (
            mock.patch.object(
                stackctl, "load_startup_attempt", return_value=attempt
            ),
            mock.patch.object(
                stackctl, "deployment_candidate_dir", return_value=candidate_root
            ),
            mock.patch.object(
                stackctl,
                "load_candidate_manifest",
                return_value={"baselineId": receipt_candidate},
            ),
            mock.patch.object(
                stackctl,
                "_candidate_provider_runtime",
                return_value={
                    "candidateRoot": candidate_root,
                    "providerRuntime": {"composition": {}},
                },
            ),
            mock.patch.object(
                stackctl,
                "_provider_runtime_launch_environment",
                return_value={"QWQ_PROVIDER_RUNTIME_DIGEST": "sha256:" + "2" * 64},
            ),
            mock.patch.object(
                stackctl,
                "_candidate_observability_log_sink",
                return_value={"candidateRoot": candidate_root, "composition": {}},
            ),
            mock.patch.object(
                stackctl,
                "_observability_log_sink_launch_environment",
                return_value={
                    "QWQ_OBSERVABILITY_LOG_SINK_DIGEST": "sha256:" + "3" * 64
                },
            ),
            mock.patch.object(
                stackctl,
                "_load_gamma_runtime_image_composition",
                return_value=(
                    {"configurationDigest": "sha256:" + "4" * 64, "images": {}},
                    "quwoquan_alpha_release",
                ),
            ),
            mock.patch.object(stackctl, "_apply_gamma_image_composition"),
        ):
            yield

    def test_candidate_provider_rejects_root_outside_receipt_baseline(self) -> None:
        receipt_candidate = "sha256:" + "1" * 64
        with tempfile.TemporaryDirectory() as temporary:
            expected_root = (Path(temporary) / "expected").resolve()
            wrong_root = (Path(temporary) / "active-pointer-drift").resolve()
            with (
                mock.patch.object(
                    stackctl,
                    "deployment_candidate_dir",
                    return_value=expected_root,
                ),
                mock.patch.object(stackctl, "load_candidate_manifest") as manifest,
                self.assertRaisesRegex(
                    ValueError,
                    "root differs from its baseline identity",
                ),
            ):
                stackctl._candidate_provider_runtime(
                    "alpha",
                    "alpha-local",
                    receipt_candidate,
                    candidate_root=wrong_root,
                )

        manifest.assert_not_called()

    def test_receipt_bound_compose_model_clears_ambient_profiles_and_replays_candidate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            candidate_root = (Path(temporary) / "candidate").resolve()
            candidate_root.mkdir()
            shared_root = candidate_root / "packages/runtime-shared"
            policy = (
                shared_root
                / "runtime-topology/policies/recommendation_policy.yaml"
            )
            policy.parent.mkdir(parents=True)
            for source in (
                shared_root / "Caddyfile",
                shared_root / "livekit.yaml",
                shared_root / "object-storage-lifecycle.json",
                policy,
            ):
                source.write_text("fixture\n", encoding="utf-8")
            legal_root = candidate_root / "packages/legal-static/current/public"
            legal_root.mkdir(parents=True)
            topology_compose = candidate_root / "runtime-compose.yaml"
            provider_compose = candidate_root / "provider-compose.yaml"
            observability_compose = candidate_root / "observability-compose.yaml"
            for compose_file in (
                topology_compose,
                provider_compose,
                observability_compose,
            ):
                compose_file.write_text("services: {}\n", encoding="utf-8")
            environment = {
                stackctl.RUNTIME_CANDIDATE_ROOT_ENV: str(candidate_root),
                "LOCAL_GAMMA_HTTP_PORT": "17000",
                "QWQ_PROVIDER_RUNTIME_COMPOSE_FILES": str(provider_compose),
                "QWQ_PROVIDER_RUNTIME_COMPOSE_PROFILES": "provider-a,provider-b",
                "QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE": str(
                    observability_compose
                ),
                "COMPOSE_PROFILES": "ambient-profile",
            }
            rendered_model = {"services": {"api-edge": {}}}
            with (
                mock.patch.object(
                    stackctl,
                    "load_runtime_topology_package",
                    return_value={"composeFiles": [topology_compose]},
                ) as load_topology,
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        [],
                        0,
                        stdout=json.dumps(rendered_model),
                        stderr="",
                    ),
                ) as run,
            ):
                actual = stackctl._receipt_bound_local_compose_model(
                    environment_name="alpha",
                    target_name="alpha-local",
                    workload="full",
                    compose_project="quwoquan_alpha_release",
                    environment=environment,
                )

        self.assertEqual(actual, rendered_model)
        load_topology.assert_called_once_with(
            candidate_root,
            environment="alpha",
            target="alpha-local",
            workload="full",
        )
        command = run.call_args.args[0]
        self.assertEqual(
            command,
            [
                "docker",
                "compose",
                "-p",
                "quwoquan_alpha_release",
                "-f",
                str(topology_compose),
                "-f",
                str(provider_compose),
                "-f",
                str(observability_compose),
                # 声明位闭集按字典序展开；Compose 的 --profile 是集合语义，顺序
                # 不影响激活结果，但断言固定顺序才能锁住「不多不少」。
                "--profile",
                "assistant-runtime",
                "--profile",
                "commercial-observability",
                "--profile",
                "control-plane",
                "--profile",
                "edge-media",
                # Provider profile 来自回执，永远排在声明闭集之后。
                "--profile",
                "provider-a",
                "--profile",
                "provider-b",
                "config",
                "--format",
                "json",
            ],
        )
        render_environment = run.call_args.kwargs["env"]
        self.assertEqual(render_environment["COMPOSE_PROFILES"], "")
        self.assertEqual(render_environment["QWQ_COMPOSE_HTTP_PORT"], "17000")
        self.assertEqual(render_environment["QWQ_COMPOSE_ENV"], "alpha")
        self.assertEqual(
            render_environment["LOCAL_GAMMA_LIVEKIT_CONFIG_FILE"],
            str(shared_root / "livekit.yaml"),
        )
        self.assertEqual(
            render_environment["LOCAL_GAMMA_LEGAL_STATIC_ROOT"], str(legal_root)
        )
        self.assertEqual(
            render_environment["LOCAL_GAMMA_PUBLIC_WEB_ROOT"],
            "/nonexistent/quwoquan-teardown-port-projection/alpha-local/public-web",
        )
        self.assertEqual(run.call_args.kwargs["timeout_seconds"], 90)

    def test_receipt_bound_profile_closure_matches_the_launcher_declaration(
        self,
    ) -> None:
        # down 侧要复现启动时的 Compose 服务集合，才能把 published endpoint 归属到
        # 正确 role。任一侧新增 profile 而另一侧漏掉，都会让 down 少投影一批
        # publisher 并静默跳过端口释放校验。
        # Python 侧（immutable down 投影与 mutable test_live 装配）已收敛到
        # FULL_WORKLOAD_COMPOSE_PROFILES 一处声明，故这里直接比对启动器声明与该
        # 闭集；shell 启动器无法 import Python，是唯一剩余的并列声明，由本断言锁定。
        launcher = (
            stackctl.ROOT
            / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        full_declaration = re.search(
            r'export COMPOSE_PROFILES="\$\{COMPOSE_PROFILES:\+\$\{COMPOSE_PROFILES\},\}'
            r'(?P<profiles>[a-z0-9,-]+),'
            r'\$\{QWQ_PROVIDER_RUNTIME_COMPOSE_PROFILES\}"',
            launcher,
        )
        self.assertIsNotNone(
            full_declaration,
            "launcher no longer declares the full workload profile closure inline",
        )
        launcher_full_profiles = full_declaration.group("profiles").split(",")
        commercial_declaration = re.findall(
            r'^\s*COMPOSE_PROFILES="(?P<profiles>[a-z0-9,-]+)"\s*$',
            launcher,
            re.M,
        )
        self.assertEqual(
            sorted(launcher_full_profiles),
            sorted(stackctl.FULL_WORKLOAD_COMPOSE_PROFILES),
            "launcher full-workload profile closure drifted from the declaration",
        )
        self.assertEqual(
            commercial_declaration,
            sorted(stackctl.CONTENT_COMMERCIAL_COMPOSE_PROFILES),
            "launcher commercial profile closure drifted from the declaration",
        )

        # down 投影必须消费声明位而不是自己抄一份字面量。
        down_source = inspect.getsource(
            stackctl._receipt_bound_local_compose_model
        )
        self.assertIn("FULL_WORKLOAD_COMPOSE_PROFILES", down_source)
        for profile in launcher_full_profiles:
            self.assertNotIn(
                f'"{profile}"',
                down_source,
                f"down projection must not inline the {profile} profile literal",
            )

    def test_receipt_bound_parse_never_reads_the_mutable_active_candidate(self) -> None:
        environment = {"LOCAL_GAMMA_SMS_SUBSTITUTE_PORT": "17001"}
        with mock.patch(
            "quwoquan_ops.cli.commands.runtime_image_composition."
            "candidate_service_config_versions",
            side_effect=AssertionError("active candidate must not be read"),
        ):
            stackctl._bind_gamma_down_parse_environment(
                environment,
                receipt_bound=True,
            )

        self.assertEqual(environment["QWQ_COMPOSE_SMS_SUBSTITUTE_PORT"], "17001")

    def test_missing_receipt_candidate_sources_block_before_compose(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            candidate_root = Path(temporary).resolve()
            environment = {
                stackctl.RUNTIME_CANDIDATE_ROOT_ENV: str(candidate_root),
            }
            with (
                mock.patch.object(stackctl, "run") as run,
                self.assertRaisesRegex(
                    ValueError,
                    "receipt-bound candidate Compose source is unavailable",
                ),
            ):
                stackctl._receipt_bound_local_compose_model(
                    environment_name="alpha",
                    target_name="alpha-local",
                    workload="full",
                    compose_project="quwoquan_alpha_release",
                    environment=environment,
                )

        run.assert_not_called()

    def test_invalid_port_ownership_blocks_down_before_compose_and_transition(
        self,
    ) -> None:
        receipt_candidate = "sha256:" + "1" * 64
        attempt = _running_attempt(receipt_candidate)
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "alpha", "portProfile": "alpha-local"},
                ),
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
                mock.patch.object(stackctl, "active_consumer_leases", return_value=[]),
                mock.patch.object(
                    stackctl,
                    "load_test_live_startup_attempt",
                    return_value=None,
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=attempt,
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={
                        "QWQ_LOCAL_RELEASE_ENV": "alpha",
                        "QWQ_LOCAL_RELEASE_TARGET": "alpha-local",
                        "QWQ_WORKLOAD": "full",
                    },
                ),
                mock.patch.object(
                    stackctl,
                    "_bind_local_teardown_runtime",
                    return_value=(
                        {"images": {}},
                        "runtime-receipt",
                        "quwoquan_alpha_release",
                        False,
                    ),
                ),
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(
                    stackctl,
                    "_receipt_bound_local_compose_model",
                    side_effect=ValueError(
                        "runtime published endpoint ownership is required"
                    ),
                ),
                mock.patch.object(stackctl, "run") as run,
                mock.patch.object(stackctl, "transition_startup_attempt") as transition,
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(_down_args(report_dir))

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "runtime_port_ownership_invalid")
        self.assertTrue(
            any("runtime port ownership is invalid" in item for item in result["details"])
        )
        run.assert_not_called()
        transition.assert_not_called()

    def test_zero_lease_down_preserves_state_and_never_requests_purge(self) -> None:
        receipt_candidate = "sha256:" + "1" * 64
        attempt = _running_attempt(receipt_candidate)
        topology: dict[str, object] = {}
        port_manifest = load_port_manifest()
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value=topology,
                ) as topology_loader,
                mock.patch.object(
                    stackctl,
                    "load_port_manifest",
                    return_value=port_manifest,
                ) as manifest_loader,
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={"env": "alpha", "portProfile": "alpha-local"},
                ),
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
                    "active_consumer_leases",
                    return_value=[],
                ) as leases,
                mock.patch.object(
                    stackctl,
                    "load_test_live_startup_attempt",
                    return_value=None,
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=attempt,
                ),
                mock.patch.object(
                    stackctl,
                    "_gamma_env_from_port_manifest",
                    return_value={
                        "QWQ_LOCAL_RELEASE_ENV": "alpha",
                        "QWQ_LOCAL_RELEASE_TARGET": "alpha-local",
                        "QWQ_WORKLOAD": "full",
                    },
                ) as environment_projection,
                mock.patch.object(
                    stackctl,
                    "_bind_local_teardown_runtime",
                    return_value=(
                        {"images": {}},
                        "runtime-receipt",
                        "quwoquan_alpha_release",
                        False,
                    ),
                ) as bind_runtime,
                mock.patch.object(stackctl, "_bind_gamma_down_parse_environment"),
                mock.patch.object(
                    stackctl,
                    "_receipt_bound_local_compose_model",
                    return_value={"services": {}},
                ) as render_compose_model,
                mock.patch.object(
                    stackctl,
                    "project_compose_published_endpoints",
                    return_value=[
                        {
                            "role": "api-edge",
                            "hostPort": 17000,
                            "protocol": "tcp",
                        }
                    ],
                ) as project_endpoints,
                mock.patch.object(
                    stackctl,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        [], 0, stdout="", stderr=""
                    ),
                ) as run,
                mock.patch.object(
                    stackctl,
                    "_runtime_owned_port_occupancy_report",
                    return_value={
                        "profile": "alpha-local",
                        "publishedEndpoints": [
                            {
                                "role": "api-edge",
                                "hostPort": 17000,
                                "protocol": "tcp",
                                "open": False,
                            }
                        ],
                        "publicEndpoints": [],
                    },
                ) as ownership_report,
                mock.patch.object(
                    stackctl,
                    "_wait_for_published_endpoints_released",
                    return_value=[],
                ) as wait_for_ports,
                mock.patch.object(
                    stackctl,
                    "transition_startup_attempt",
                    return_value={"status": "stopped"},
                ),
                mock.patch.object(stackctl.shutil, "rmtree") as rmtree,
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_down(_down_args(report_dir))

            report = json.loads((report_dir / "report.json").read_text())

        self.assertEqual(result["exitCode"], 0, result)
        leases.assert_called_once_with("alpha-local")
        bind_runtime.assert_called_once_with(
            env_name="alpha",
            target_name="alpha-local",
            environment=mock.ANY,
            purge_rebuildable_state=False,
        )
        self.assertEqual(
            run.call_args_list[0].args[0],
            [
                "bash",
                "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
                "--down",
            ],
        )
        self.assertNotIn("--purge-rebuildable-state", run.call_args_list[0].args[0])
        topology_loader.assert_called_once_with()
        manifest_loader.assert_called_once_with()
        environment_projection.assert_called_once_with(
            topology,
            "alpha-local",
            manifest=port_manifest,
        )
        render_compose_model.assert_called_once_with(
            environment_name="alpha",
            target_name="alpha-local",
            workload="full",
            compose_project="quwoquan_alpha_release",
            environment=mock.ANY,
        )
        project_endpoints.assert_called_once_with(
            port_profile="alpha-local",
            compose_model={"services": {}},
            manifest=port_manifest,
        )
        ownership_report.assert_called_once_with(
            "alpha-local",
            published_ports=[
                {"role": "api-edge", "hostPort": 17000, "protocol": "tcp"}
            ],
            topology=topology,
            manifest=port_manifest,
        )
        wait_for_ports.assert_called_once_with(
            [{"role": "api-edge", "hostPort": 17000, "protocol": "tcp"}]
        )
        self.assertFalse(report["destructiveRepairPerformed"])
        self.assertEqual(report["destructiveActions"], [])
        rmtree.assert_not_called()


if __name__ == "__main__":
    unittest.main()

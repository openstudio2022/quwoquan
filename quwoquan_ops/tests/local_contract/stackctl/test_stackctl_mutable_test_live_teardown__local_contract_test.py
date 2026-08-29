"""Receipt-bound mutable test-live teardown contracts.

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.port_manifest import load_port_manifest, profile_ports
from quwoquan_ops.tests.support.stackctl_dev_session_test_support import (
    StackctlMutableTeardownTestBase,
    _mutable_teardown_down_args as _down_args,
    _mutable_teardown_receipt as _receipt,
)


def _completed(
    args: list[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


class StackctlMutableTestLiveTeardownTest(StackctlMutableTeardownTestBase):

    def test_down_selects_running_mutable_receipt_when_immutable_is_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            receipt = _receipt(report_dir)
            selected = {
                "exitCode": 0,
                "summary": "selected",
                "details": [],
                "runtimeMode": "mutable-test-live",
            }
            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
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
                    "load_test_live_startup_attempt",
                    return_value=receipt,
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value={"status": "stopped"},
                ),
                mock.patch.object(
                    stackctl,
                    "_command_mutable_test_live_down",
                    return_value=selected,
                ) as teardown,
            ):
                result = stackctl._command_down_unlocked(_down_args(report_dir))

        self.assertEqual(result, selected)
        teardown.assert_called_once_with(
            mock.ANY,
            env_name="alpha",
            report_dir=report_dir,
            receipt=receipt,
        )

    def test_down_selects_partial_receipt_for_strict_receipt_bound_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            receipt = _receipt(report_dir, status="partial")
            selected = {
                "exitCode": 2,
                "summary": "identity drift",
                "details": ["container belongs to another runRoot"],
                "runtimeMode": "mutable-test-live",
            }
            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
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
                    "load_test_live_startup_attempt",
                    return_value=receipt,
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value={"status": "stopped"},
                ),
                mock.patch.object(
                    stackctl,
                    "_command_mutable_test_live_down",
                    return_value=selected,
                ) as teardown,
            ):
                result = stackctl._command_down_unlocked(_down_args(report_dir))

        self.assertEqual(result, selected)
        teardown.assert_called_once_with(
            mock.ANY,
            env_name="alpha",
            report_dir=report_dir,
            receipt=receipt,
        )

    def test_down_rejects_ambiguous_mutable_and_immutable_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
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
                    "load_test_live_startup_attempt",
                    return_value=_receipt(report_dir),
                ),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value={"status": "running"},
                ),
                mock.patch.object(
                    stackctl,
                    "_command_mutable_test_live_down",
                ) as teardown,
            ):
                result = stackctl._command_down_unlocked(_down_args(report_dir))

            report = json.loads((report_dir / "report.json").read_text())

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["blockerKind"], "runtime_teardown_identity_ambiguous")
        self.assertEqual(report["status"], "gate_block")
        teardown.assert_not_called()

    def test_manifest_is_bound_to_run_root_project_config_labels_and_networks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_root = Path(temporary)
            compose_path = run_root / "compose.json"
            compose_path.write_text(
                json.dumps(
                    {
                        "services": {
                            "gamma-proxy": {"image": "quwoquan/gamma-proxy:old"},
                            "service-core": {"image": "quwoquan/service-core:old"},
                        }
                    }
                )
            )
            receipt = _receipt(run_root)
            runtime_plan = {"executionComposeFiles": [str(compose_path)]}

            containers = []
            for index, service in enumerate(("gamma-proxy", "service-core"), 1):
                containers.append(
                    {
                        "Id": f"container-{index}",
                        "Config": {
                            "Image": f"quwoquan/{service}:old",
                            "Labels": {
                                "com.docker.compose.project": "quwoquan_alpha_test_live",
                                "com.docker.compose.service": service,
                                "com.docker.compose.oneoff": "False",
                                "com.docker.compose.config-hash": f"hash-{index}",
                                "com.docker.compose.project.config_files": str(
                                    compose_path
                                ),
                            },
                        },
                        "HostConfig": {
                            "PortBindings": (
                                {"17000/tcp": [{"HostPort": "17000"}]}
                                if service == "gamma-proxy"
                                else {}
                            )
                        },
                        "NetworkSettings": {
                            "Networks": {"quwoquan_alpha_test_live_default": {}}
                        },
                    }
                )

            def run_command(
                command: list[str],
                **_: object,
            ) -> subprocess.CompletedProcess[str]:
                if command[:3] == ["docker", "ps", "-aq"]:
                    return _completed(command, stdout="container-1\ncontainer-2\n")
                if command[:2] == ["docker", "inspect"]:
                    return _completed(command, stdout=json.dumps(containers))
                if command[:3] == ["docker", "network", "ls"]:
                    return _completed(
                        command,
                        stdout="quwoquan_alpha_test_live_default\n",
                    )
                if command[:3] == ["docker", "network", "inspect"]:
                    return _completed(
                        command,
                        stdout=json.dumps(
                            [
                                {
                                    "Name": "quwoquan_alpha_test_live_default",
                                    "Labels": {
                                        "com.docker.compose.project": "quwoquan_alpha_test_live",
                                        "com.docker.compose.network": "default",
                                    },
                                }
                            ]
                        ),
                    )
                if command[:3] == ["docker", "volume", "ls"]:
                    return _completed(command, stdout="quwoquan_alpha_postgres\n")
                self.fail(f"unexpected command: {command}")

            with mock.patch.object(stackctl, "run", side_effect=run_command):
                manifest, container_ids, volumes = (
                    stackctl._mutable_test_live_teardown_manifest(
                        receipt=receipt,
                        runtime_plan=runtime_plan,
                        run_root=run_root,
                        port_manifest=load_port_manifest(),
                        port_profile="alpha-local",
                    )
                )

        self.assertEqual(container_ids, ["container-1", "container-2"])
        self.assertEqual(volumes, ["quwoquan_alpha_postgres"])
        self.assertEqual(
            manifest["networks"],
            {"default": {"name": "quwoquan_alpha_test_live_default"}},
        )
        self.assertEqual(
            set(manifest["services"]),
            {"gamma-proxy", "service-core"},
        )
        self.assertEqual(manifest["services"]["gamma-proxy"]["networks"], ["default"])

    def test_partial_manifest_accepts_receipt_bound_service_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_root = Path(temporary)
            compose_path = run_root / "compose.json"
            compose_path.write_text(
                json.dumps(
                    {
                        "services": {
                            "gamma-proxy": {"image": "quwoquan/gamma-proxy:old"},
                            "service-core": {"image": "quwoquan/service-core:old"},
                        }
                    }
                )
            )
            receipt = _receipt(run_root, status="partial")
            receipt["publishedPorts"] = [
                *receipt["publishedPorts"],
                {
                    "role": "product-ops-service",
                    "hostPort": profile_ports(load_port_manifest(), "alpha-local")[
                        "product-ops-service"
                    ],
                    "protocol": "tcp",
                },
            ]
            runtime_plan = {"executionComposeFiles": [str(compose_path)]}
            containers = [
                {
                    "Id": "container-1",
                    "Config": {
                        "Image": "quwoquan/gamma-proxy:old",
                        "Labels": {
                            "com.docker.compose.project": "quwoquan_alpha_test_live",
                            "com.docker.compose.service": "gamma-proxy",
                            "com.docker.compose.oneoff": "False",
                            "com.docker.compose.config-hash": "hash-1",
                            "com.docker.compose.project.config_files": str(
                                compose_path
                            ),
                        },
                    },
                    "HostConfig": {
                        "PortBindings": {"17000/tcp": [{"HostPort": "17000"}]}
                    },
                    "NetworkSettings": {
                        "Networks": {"quwoquan_alpha_test_live_default": {}}
                    },
                }
            ]

            def run_command(
                command: list[str],
                **_: object,
            ) -> subprocess.CompletedProcess[str]:
                if command[:3] == ["docker", "ps", "-aq"]:
                    return _completed(command, stdout="container-1\n")
                if command[:2] == ["docker", "inspect"]:
                    return _completed(command, stdout=json.dumps(containers))
                if command[:3] == ["docker", "network", "ls"]:
                    return _completed(
                        command,
                        stdout="quwoquan_alpha_test_live_default\n",
                    )
                if command[:3] == ["docker", "network", "inspect"]:
                    return _completed(
                        command,
                        stdout=json.dumps(
                            [
                                {
                                    "Name": "quwoquan_alpha_test_live_default",
                                    "Labels": {
                                        "com.docker.compose.project": "quwoquan_alpha_test_live",
                                        "com.docker.compose.network": "default",
                                    },
                                }
                            ]
                        ),
                    )
                if command[:3] == ["docker", "volume", "ls"]:
                    return _completed(command, stdout="quwoquan_alpha_postgres\n")
                self.fail(f"unexpected command: {command}")

            with mock.patch.object(stackctl, "run", side_effect=run_command):
                manifest, container_ids, _ = (
                    stackctl._mutable_test_live_teardown_manifest(
                        receipt=receipt,
                        runtime_plan=runtime_plan,
                        run_root=run_root,
                        port_manifest=load_port_manifest(),
                        port_profile="alpha-local",
                    )
                )

        self.assertEqual(container_ids, ["container-1"])
        self.assertEqual(set(manifest["services"]), {"gamma-proxy"})

    def test_manifest_rejects_live_publisher_drift_before_volume_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_root = Path(temporary)
            compose_path = run_root / "compose.json"
            compose_path.write_text(
                json.dumps(
                    {
                        "services": {
                            "gamma-proxy": {"image": "quwoquan/gamma-proxy:old"}
                        }
                    }
                )
            )
            receipt = _receipt(run_root)
            runtime_plan = {"executionComposeFiles": [str(compose_path)]}
            container = {
                "Id": "container-1",
                "Config": {
                    "Image": "quwoquan/gamma-proxy:old",
                    "Labels": {
                        "com.docker.compose.project": "quwoquan_alpha_test_live",
                        "com.docker.compose.service": "gamma-proxy",
                        "com.docker.compose.oneoff": "False",
                        "com.docker.compose.config-hash": "hash-1",
                        "com.docker.compose.project.config_files": str(compose_path),
                    },
                },
                "HostConfig": {
                    "PortBindings": {"17000/tcp": [{"HostPort": "17999"}]}
                },
                "NetworkSettings": {"Networks": {}},
            }

            def run_command(
                command: list[str],
                **_: object,
            ) -> subprocess.CompletedProcess[str]:
                if command[:3] == ["docker", "ps", "-aq"]:
                    return _completed(command, stdout="container-1\n")
                if command[:2] == ["docker", "inspect"]:
                    return _completed(command, stdout=json.dumps([container]))
                if command[:3] == ["docker", "network", "ls"]:
                    return _completed(command)
                if command[:3] == ["docker", "volume", "ls"]:
                    self.fail("volume inventory must not run after publisher drift")
                self.fail(f"unexpected command: {command}")

            with mock.patch.object(stackctl, "run", side_effect=run_command):
                with self.assertRaisesRegex(
                    ValueError,
                    "Compose published endpoint identity drifted",
                ):
                    stackctl._mutable_test_live_teardown_manifest(
                        receipt=receipt,
                        runtime_plan=runtime_plan,
                        run_root=run_root,
                        port_manifest=load_port_manifest(),
                        port_profile="alpha-local",
                    )

    def test_partial_teardown_preserves_volumes_and_commits_stopped_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            receipt = _receipt(report_dir, status="partial")
            runtime_plan = {"schema": "stackctl.mutable_test_live_runtime"}
            stopped = {**receipt, "status": "stopped"}
            run_results = [
                _completed(["stop-app"]),
                _completed(["compose-down"], stdout="removed\n"),
            ]
            with (
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_runtime_plan_from_receipt",
                    return_value=(runtime_plan, report_dir),
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_container_ids",
                    side_effect=[["container-1"], []],
                ),
                mock.patch.object(
                    stackctl,
                    "_dev_session_resume_running_mutable_runtime",
                    return_value=(
                        {"runtime": runtime_plan},
                        ["workspace digest warning"],
                    ),
                ) as resume,
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_teardown_manifest",
                    return_value=(
                        {"services": {"api-edge": {"image": "image"}}},
                        ["container-1"],
                        ["volume-1"],
                    ),
                ),
                mock.patch.object(stackctl, "run", side_effect=run_results) as runner,
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_resource_names",
                    side_effect=[[], ["volume-1"]],
                ),
                mock.patch.object(
                    stackctl,
                    "_wait_for_published_endpoints_released",
                    return_value=[],
                ),
                mock.patch.object(
                    stackctl,
                    "transition_test_live_startup_attempt",
                    return_value=stopped,
                ) as transition,
            ):
                result = stackctl._command_mutable_test_live_down(
                    _down_args(report_dir),
                    env_name="alpha",
                    report_dir=report_dir,
                    receipt=receipt,
                )

            report = json.loads((report_dir / "report.json").read_text())

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["runtimeMode"], "mutable-test-live")
        self.assertEqual(report["startupAttempt"]["status"], "stopped")
        self.assertEqual(report["namedVolumesPreserved"], ["volume-1"])
        resume.assert_not_called()
        compose_command = runner.call_args_list[1].args[0]
        self.assertIn("down", compose_command)
        self.assertIn("--remove-orphans", compose_command)
        self.assertNotIn("-v", compose_command)
        self.assertNotIn("--volumes", compose_command)
        transition.assert_called_once_with(
            environment="alpha",
            target="alpha-local",
            attempt_id="alpha-test-live-attempt-1",
            status="stopped",
            runtime_plan=runtime_plan,
            run_root=report_dir,
            failure="",
        )

    def test_cross_run_container_identity_blocks_before_any_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            receipt = _receipt(report_dir, status="partial")
            with (
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_runtime_plan_from_receipt",
                    return_value=({}, report_dir),
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_container_ids",
                    return_value=["container-from-another-run"],
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_teardown_manifest",
                    side_effect=ValueError(
                        "mutable test-live container is not bound to this receipt"
                    ),
                ),
                mock.patch.object(stackctl, "run") as runner,
                mock.patch.object(
                    stackctl,
                    "transition_test_live_startup_attempt",
                ) as transition,
            ):
                result = stackctl._command_mutable_test_live_down(
                    _down_args(report_dir),
                    env_name="alpha",
                    report_dir=report_dir,
                    receipt=receipt,
                )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            result["blockerKind"],
            "mutable_test_live_teardown_identity_invalid",
        )
        runner.assert_not_called()
        transition.assert_not_called()

    def test_missing_preserved_volume_blocks_stopped_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            receipt = _receipt(report_dir)
            with (
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_runtime_plan_from_receipt",
                    return_value=({}, report_dir),
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_container_ids",
                    side_effect=[["container-1"], []],
                ),
                mock.patch.object(
                    stackctl,
                    "_dev_session_resume_running_mutable_runtime",
                    return_value=({"runtime": {}}, []),
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_teardown_manifest",
                    return_value=(
                        {"services": {"api-edge": {"image": "image"}}},
                        ["container-1"],
                        ["volume-1"],
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "run",
                    side_effect=[
                        _completed(["stop-app"]),
                        _completed(["compose-down"]),
                    ],
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_resource_names",
                    side_effect=[[], []],
                ),
                mock.patch.object(
                    stackctl,
                    "_wait_for_published_endpoints_released",
                    return_value=[],
                ),
                mock.patch.object(
                    stackctl,
                    "transition_test_live_startup_attempt",
                ) as transition,
            ):
                result = stackctl._command_mutable_test_live_down(
                    _down_args(report_dir),
                    env_name="alpha",
                    report_dir=report_dir,
                    receipt=receipt,
                )

            report = json.loads((report_dir / "report.json").read_text())

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            result["blockerKind"],
            "mutable_test_live_teardown_not_converged",
        )
        self.assertEqual(report["startupAttempt"]["status"], "running")
        transition.assert_not_called()

    def test_orphaned_networks_are_reclaimed_and_down_converges(self) -> None:
        """无容器但残留孤儿网络时，down 必须回收后收敛，而不是死锁 GATE_BLOCK。"""
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            receipt = _receipt(report_dir)
            runtime_plan = {"schema": "stackctl.mutable_test_live_runtime"}
            stopped = {**receipt, "status": "stopped"}
            with (
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_runtime_plan_from_receipt",
                    return_value=(runtime_plan, report_dir),
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_container_ids",
                    side_effect=[[], []],
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_resource_names",
                    side_effect=[
                        ["volume-1"],
                        ["quwoquan_alpha_test_live_default"],
                        [],
                        ["volume-1"],
                    ],
                ),
                mock.patch.object(
                    stackctl,
                    "_reclaim_orphaned_project_networks",
                    return_value=(["quwoquan_alpha_test_live_default"], []),
                ) as reclaim,
                mock.patch.object(
                    stackctl,
                    "_wait_for_published_endpoints_released",
                    return_value=[],
                ),
                mock.patch.object(
                    stackctl,
                    "transition_test_live_startup_attempt",
                    return_value=stopped,
                ) as transition,
                mock.patch.object(stackctl, "run") as runner,
            ):
                result = stackctl._command_mutable_test_live_down(
                    _down_args(report_dir),
                    env_name="alpha",
                    report_dir=report_dir,
                    receipt=receipt,
                )

            report = json.loads((report_dir / "report.json").read_text())

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(report["startupAttempt"]["status"], "stopped")
        self.assertIn(
            "orphaned Compose networks reclaimed",
            " ".join(report["details"]),
        )
        reclaim.assert_called_once_with(
            ["quwoquan_alpha_test_live_default"],
            compose_project="quwoquan_alpha_test_live",
        )
        runner.assert_not_called()
        transition.assert_called_once()

    def test_unreclaimable_networks_keep_down_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            receipt = _receipt(report_dir)
            runtime_plan = {"schema": "stackctl.mutable_test_live_runtime"}
            with (
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_runtime_plan_from_receipt",
                    return_value=(runtime_plan, report_dir),
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_container_ids",
                    side_effect=[[], []],
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_resource_names",
                    side_effect=[
                        ["volume-1"],
                        ["quwoquan_alpha_test_live_default"],
                        ["quwoquan_alpha_test_live_default"],
                        ["volume-1"],
                    ],
                ),
                mock.patch.object(
                    stackctl,
                    "_reclaim_orphaned_project_networks",
                    return_value=(
                        [],
                        [
                            "orphaned Compose network was not reclaimed: "
                            "quwoquan_alpha_test_live_default: docker network rm "
                            "failed with exit code 1: network has active endpoints"
                        ],
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_wait_for_published_endpoints_released",
                    return_value=[],
                ),
                mock.patch.object(
                    stackctl,
                    "transition_test_live_startup_attempt",
                ) as transition,
                mock.patch.object(stackctl, "run"),
            ):
                result = stackctl._command_mutable_test_live_down(
                    _down_args(report_dir),
                    env_name="alpha",
                    report_dir=report_dir,
                    receipt=receipt,
                )

            report = json.loads((report_dir / "report.json").read_text())

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(
            result["blockerKind"],
            "mutable_test_live_teardown_not_converged",
        )
        reported = " ".join(report["resourceReleaseIssues"])
        self.assertIn("networks remain after down", reported)
        # 判否之外还必须带出未回收的根因，否则操作员只知道「仍在」不知道为什么。
        self.assertIn("network has active endpoints", reported)
        transition.assert_not_called()

    def test_reclaim_removes_only_endpoint_free_project_networks(self) -> None:
        """只删 label 复核通过且无 endpoint 的本项目网络；busy 与他项目网络不动。"""
        project = "quwoquan_alpha_test_live"

        def _run(command: list[str], **_kwargs: object) -> object:
            if command[:3] == ["docker", "network", "inspect"]:
                name = command[3]
                containers = (
                    {"cid": {"Name": "svc"}} if name == "net-busy" else {}
                )
                # net-foreign 在 ls 与 rm 之间被重建为他项目同名网络。
                label_project = "other_project" if name == "net-foreign" else project
                return _completed(
                    command,
                    stdout=json.dumps(
                        [
                            {
                                "Name": name,
                                "Containers": containers,
                                "Labels": {
                                    "com.docker.compose.project": label_project
                                },
                            }
                        ]
                    ),
                )
            if command[:3] == ["docker", "network", "rm"]:
                return _completed(command)
            raise AssertionError(f"unexpected command: {command}")

        with mock.patch.object(stackctl, "run", side_effect=_run) as runner:
            reclaimed, issues = stackctl._reclaim_orphaned_project_networks(
                ["net-busy", "net-empty", "net-foreign"],
                compose_project=project,
            )

        self.assertEqual(reclaimed, ["net-empty"])
        removed = [
            call.args[0][3]
            for call in runner.call_args_list
            if call.args[0][:3] == ["docker", "network", "rm"]
        ]
        self.assertEqual(removed, ["net-empty"])
        # 未回收的两条必须各自带上可判否的原因，而不是静默跳过。
        reported = " ".join(issues)
        self.assertIn("net-busy", reported)
        self.assertIn("still has attached endpoints", reported)
        self.assertIn("net-foreign", reported)
        self.assertIn("not this project at removal time", reported)
        self.assertNotIn("net-empty", reported)

    def test_reclaim_reports_inspect_and_removal_failure_reasons(self) -> None:
        """inspect/rm 的 stderr 是唯一的失败根因来源，不能丢。"""
        project = "quwoquan_alpha_test_live"

        def _run(command: list[str], **_kwargs: object) -> object:
            if command[:3] == ["docker", "network", "inspect"]:
                name = command[3]
                if name == "net-unreadable":
                    return _completed(command, returncode=1, stderr="daemon unreachable")
                if name == "net-malformed":
                    return _completed(command, stdout="{not json")
                return _completed(
                    command,
                    stdout=json.dumps(
                        [
                            {
                                "Name": name,
                                "Containers": {},
                                "Labels": {"com.docker.compose.project": project},
                            }
                        ]
                    ),
                )
            if command[:3] == ["docker", "network", "rm"]:
                return _completed(command, returncode=1, stderr="network has active endpoints")
            raise AssertionError(f"unexpected command: {command}")

        with mock.patch.object(stackctl, "run", side_effect=_run):
            reclaimed, issues = stackctl._reclaim_orphaned_project_networks(
                ["net-unreadable", "net-malformed", "net-stuck"],
                compose_project=project,
            )

        self.assertEqual(reclaimed, [])
        reported = " ".join(issues)
        self.assertIn("daemon unreachable", reported)
        self.assertIn("payload is unreadable", reported)
        self.assertIn("network has active endpoints", reported)

    def test_retry_after_compose_down_commits_stopped_receipt_from_readback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            receipt = _receipt(report_dir)
            runtime_plan = {"schema": "stackctl.mutable_test_live_runtime"}
            stopped = {**receipt, "status": "stopped"}
            with (
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_runtime_plan_from_receipt",
                    return_value=(runtime_plan, report_dir),
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_container_ids",
                    side_effect=[[], []],
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_resource_names",
                    side_effect=[["volume-1"], [], ["volume-1"]],
                ),
                mock.patch.object(
                    stackctl,
                    "_wait_for_published_endpoints_released",
                    return_value=[],
                ) as wait_ports,
                mock.patch.object(
                    stackctl,
                    "transition_test_live_startup_attempt",
                    return_value=stopped,
                ) as transition,
                mock.patch.object(stackctl, "run") as runner,
            ):
                result = stackctl._command_mutable_test_live_down(
                    _down_args(report_dir),
                    env_name="alpha",
                    report_dir=report_dir,
                    receipt=receipt,
                )

            report = json.loads((report_dir / "report.json").read_text())

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(report["startupAttempt"]["status"], "stopped")
        self.assertIn("recovery observed", " ".join(report["details"]))
        runner.assert_not_called()
        wait_ports.assert_called_once_with(
            [{"role": "api-edge", "hostPort": 17000, "protocol": "tcp"}]
        )
        transition.assert_called_once()


if __name__ == "__main__":
    unittest.main()

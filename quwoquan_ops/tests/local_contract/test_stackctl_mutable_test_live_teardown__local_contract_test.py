"""Receipt-bound mutable test-live teardown contracts.

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl


def _completed(
    args: list[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def _receipt(run_root: Path, *, status: str = "running") -> dict[str, object]:
    return {
        "schema": "stackctl.mutable_test_live_startup_attempt.v1",
        "launchPolicy": "test_live",
        "nonPromotable": True,
        "contentBindingState": "unbound",
        "attemptId": "alpha-test-live-attempt-1",
        "environment": "alpha",
        "target": "alpha-local",
        "status": status,
        "workload": "full",
        "composeProject": "quwoquan_alpha_test_live",
        "composeDigest": "sha256:" + "1" * 64,
        "configurationDigest": "sha256:" + "2" * 64,
        "providerRuntimeDigest": "sha256:" + "3" * 64,
        "portProfile": "alpha-local",
        "portBlock": {"start": 17000, "end": 17999},
        "publishedPorts": {"api-edge": 17000},
        "tlsProfile": "local-managed",
        "resolverHandoffDigest": "sha256:" + "4" * 64,
        "sourceRevision": "a" * 40,
        "workspaceStatusDigest": "sha256:" + "5" * 64,
        "mutableStateDigest": "sha256:" + "6" * 64,
        "runRoot": str(run_root),
        "startedAt": "2026-08-10T12:00:00Z",
        "updatedAt": "2026-08-10T12:00:01Z",
        "failure": None,
    }


def _down_args(report_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        target="alpha-local",
        workload="full",
        formal_release=False,
        release_manifest="",
        purge_rebuildable_state=False,
        report_dir=str(report_dir),
    )


class StackctlMutableTestLiveTeardownTest(unittest.TestCase):
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
                            "api-edge": {"image": "quwoquan/api-edge:old"},
                            "integration-service": {
                                "image": "quwoquan/integration-service:old"
                            },
                        }
                    }
                )
            )
            receipt = _receipt(run_root)
            runtime_plan = {"executionComposeFiles": [str(compose_path)]}

            containers = []
            for index, service in enumerate(("api-edge", "integration-service"), 1):
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
            {"api-edge", "integration-service"},
        )
        self.assertEqual(manifest["services"]["api-edge"]["networks"], ["default"])

    def test_successful_teardown_preserves_volumes_and_commits_stopped_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            receipt = _receipt(report_dir)
            runtime_plan = {"schema": "stackctl.mutable_test_live_runtime.v1"}
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
                mock.patch.object(stackctl, "run", side_effect=run_results) as runner,
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_resource_names",
                    side_effect=[[], ["volume-1"]],
                ),
                mock.patch.object(
                    stackctl,
                    "_wait_for_exact_tcp_ports_released",
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
                    "_wait_for_exact_tcp_ports_released",
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

    def test_retry_after_compose_down_commits_stopped_receipt_from_readback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            receipt = _receipt(report_dir)
            runtime_plan = {"schema": "stackctl.mutable_test_live_runtime.v1"}
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
                    "_wait_for_exact_tcp_ports_released",
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
        wait_ports.assert_called_once_with([17000])
        transition.assert_called_once()


if __name__ == "__main__":
    unittest.main()

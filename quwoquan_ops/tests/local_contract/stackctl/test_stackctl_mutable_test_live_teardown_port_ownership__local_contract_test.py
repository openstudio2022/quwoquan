"""mutable test_live teardown 的 runtime-owned port 收敛契约。

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.port_manifest import load_port_manifest, profile_ports
from quwoquan_ops.tests.support.stackctl_dev_session_test_support import (
    StackctlMutableTeardownTestBase,
    _mutable_teardown_down_args as _down_args,
    _mutable_teardown_receipt as _receipt,
)


class StackctlMutableTestLiveTeardownTest(StackctlMutableTeardownTestBase):
    def test_beta_teardown_waits_only_for_runtime_owned_receipt_ports(self) -> None:
        topology = stackctl.load_environment_topology()
        manifest = load_port_manifest()
        beta_ports = profile_ports(manifest, "beta-local")
        runtime_owned_endpoints = [
            {
                "role": "api-edge",
                "hostPort": beta_ports["api-edge"],
                "protocol": "tcp",
            },
            {
                "role": "coturn",
                "hostPort": beta_ports["coturn"],
                "protocol": "tcp",
            },
            {
                "role": "coturn",
                "hostPort": beta_ports["coturn"],
                "protocol": "udp",
            },
        ]
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            receipt = _receipt(report_dir)
            receipt.update(
                {
                    "environment": "beta",
                    "target": "beta-local",
                    "composeProject": "quwoquan_beta_test_live",
                    "portProfile": "beta-local",
                    "portBlock": {"start": 18000, "end": 18999},
                    "publishedPorts": runtime_owned_endpoints,
                }
            )
            stopped = {**receipt, "status": "stopped"}
            with (
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value=topology,
                ) as topology_loader,
                mock.patch.object(
                    stackctl,
                    "load_port_manifest",
                    return_value=manifest,
                ) as manifest_loader,
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_runtime_plan_from_receipt",
                    return_value=(
                        {"schema": "stackctl.mutable_test_live_runtime"},
                        report_dir,
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_project_target_runtime_owned_ports",
                    wraps=stackctl._project_target_runtime_owned_ports,
                ) as ownership_projection,
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
                ) as wait_endpoints,
                mock.patch.object(
                    stackctl,
                    "transition_test_live_startup_attempt",
                    return_value=stopped,
                ),
                mock.patch.object(stackctl, "run") as runner,
            ):
                result = stackctl._command_mutable_test_live_down(
                    _down_args(report_dir, target="beta-local"),
                    env_name="beta",
                    report_dir=report_dir,
                    receipt=receipt,
                )

        self.assertEqual(result["exitCode"], 0)
        topology_loader.assert_called_once_with()
        manifest_loader.assert_called_once_with()
        ownership_projection.assert_called_once_with(
            "beta-local",
            published_ports=receipt["publishedPorts"],
            topology=topology,
            manifest=manifest,
        )
        wait_endpoints.assert_called_once_with(runtime_owned_endpoints)
        runner.assert_not_called()

    def test_invalid_mutable_port_ownership_blocks_before_runtime_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            receipt = _receipt(report_dir)
            receipt["publishedPorts"] = []
            with (
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_runtime_plan_from_receipt",
                    return_value=(
                        {"schema": "stackctl.mutable_test_live_runtime"},
                        report_dir,
                    ),
                ),
                mock.patch.object(
                    stackctl,
                    "_mutable_test_live_container_ids",
                ) as container_inventory,
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
        self.assertTrue(
            any(
                "runtime published port ownership is required" in item
                for item in result["details"]
            )
        )
        container_inventory.assert_not_called()
        runner.assert_not_called()
        transition.assert_not_called()


if __name__ == "__main__":
    import unittest

    unittest.main()

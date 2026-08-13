# spec_ref: specs/feature-tree/runtime/runtime-testinfra/fault-injection-harness/spec.md#gwt-001
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.lib import fault_drill_orchestration as drill
from quwoquan_ops.cli.lib.local_controlled_edge_fault import ControlledEdgeFault


def _fake_fault(health_sequence: list[bool]) -> ControlledEdgeFault:
    probes = list(health_sequence)

    def health_probe(url: str) -> bool:  # noqa: ARG001
        return probes.pop(0) if probes else True

    def runner(command):  # noqa: ANN001
        stdout = ""
        if command[:2] == ["docker", "inspect"]:
            stdout = "running\n"
        return subprocess.CompletedProcess(
            args=list(command), returncode=0, stdout=stdout, stderr=""
        )

    return ControlledEdgeFault(
        target="gamma-local",
        environment="gamma",
        compose_project="quwoquan_gamma_release",
        configuration_digest="sha256:" + "0" * 64,
        health_url="https://gamma.example/healthz",
        containers=[
            {
                "service": "api-edge",
                "containerId": "c-edge",
                "imageRef": "img",
                "runtimeImageId": "sha",
                "statusBefore": "running",
            }
        ],
        started_at="2026-08-12T00:00:00Z",
        runner=runner,
        health_probe=health_probe,
        sleep=lambda _seconds: None,
    )


class DrillProfileClosedSetContractTest(unittest.TestCase):
    def test_profile_closed_set_is_declared(self) -> None:
        self.assertEqual(
            drill.FAULT_PROFILES, ("bandwidth", "disconnect", "error", "latency")
        )

    def test_prod_targets_are_refused_before_injection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                drill.run_drill(
                    env_name="prod",
                    target_name="prod-hosted",
                    profile="disconnect",
                    hold_seconds=0,
                    report_dir=Path(tmp),
                )

    def test_unknown_profile_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                drill.run_drill(
                    env_name="gamma",
                    target_name="gamma-local",
                    profile="chaos-monkey",
                    hold_seconds=0,
                    report_dir=Path(tmp),
                )

    def test_unimplemented_profile_returns_structured_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            payload = drill.run_drill(
                env_name="gamma",
                target_name="gamma-local",
                profile="latency",
                hold_seconds=0,
                report_dir=report_dir,
            )
            self.assertEqual(payload["status"], "unavailable")
            self.assertIn("disconnect", payload["reason"])
            persisted = json.loads(
                (report_dir / "receipt.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["schema"], drill.DRILL_SCHEMA)
            self.assertEqual(persisted["status"], "unavailable")


class DrillDisconnectClosureContractTest(unittest.TestCase):
    def test_disconnect_drill_produces_closed_receipt(self) -> None:
        # probe 序列：故障中不可达(False) → restore 内健康(True) → 恢复后确认(True)
        fault = _fake_fault([False, True, True])
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            payload = drill.run_drill(
                env_name="gamma",
                target_name="gamma-local",
                profile="disconnect",
                hold_seconds=0,
                report_dir=report_dir,
                fault_factory=lambda target: fault,
                sleep=lambda _seconds: None,
            )
            self.assertEqual(payload["status"], "restored")
            self.assertEqual(payload["injectedAt"], "2026-08-12T00:00:00Z")
            self.assertTrue(payload["restoredAt"])
            evidence = payload["healthEvidence"]
            self.assertTrue(evidence["unavailableDuringFault"])
            self.assertTrue(evidence["healthyAfterRestore"])
            self.assertEqual(payload["alertReadback"]["status"], "unavailable")
            persisted = json.loads(
                (report_dir / "receipt.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["status"], "restored")

    def test_unhealthy_restore_is_not_masked_as_success(self) -> None:
        # 恢复后 health 仍不可达：restore 内 probe True（容器已起）但最终确认 False
        fault = _fake_fault([False, True, False])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                drill.run_drill(
                    env_name="gamma",
                    target_name="gamma-local",
                    profile="disconnect",
                    hold_seconds=0,
                    report_dir=Path(tmp),
                    fault_factory=lambda target: fault,
                    sleep=lambda _seconds: None,
                )


if __name__ == "__main__":
    unittest.main()

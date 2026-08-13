# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from unittest.mock import patch

from quwoquan_ops.cli.lib import local_controlled_edge_fault as edge_fault


def _sha256_digest(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _FakeRunner:
    def __init__(self, *, api_image: str | None = None) -> None:
        api_image = api_image or _sha256_digest("image:api-edge")
        self.api_image = api_image
        self.commands: list[list[str]] = []

    def __call__(self, command: object) -> subprocess.CompletedProcess[str]:
        argv = [str(item) for item in command]  # type: ignore[arg-type]
        self.commands.append(argv)
        if argv[:3] == ["docker", "ps", "-aq"]:
            service = next(
                value.rsplit("=", 1)[1]
                for value in argv
                if value.startswith("label=com.docker.compose.service=")
            )
            return subprocess.CompletedProcess(argv, 0, f"container-{service}\n", "")
        if argv[:2] == ["docker", "inspect"] and "--format" not in argv:
            container_id = argv[-1]
            service = container_id.removeprefix("container-")
            image_ref = self.api_image if service == "api-edge" else "proxy:stable"
            payload = [
                {
                    "Config": {
                        "Image": image_ref,
                        "Labels": {
                            "com.docker.compose.project": "quwoquan_alpha_release_uat",
                            "com.docker.compose.service": service,
                        },
                    },
                    "Image": _sha256_digest(f"container:{service}"),
                    "State": {"Status": "running"},
                }
            ]
            return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")
        if argv[:4] == ["docker", "inspect", "--format", "{{.State.Status}}"]:
            return subprocess.CompletedProcess(argv, 0, "running\n", "")
        if argv[:2] in (["docker", "stop"], ["docker", "start"]):
            return subprocess.CompletedProcess(argv, 0, "ok\n", "")
        raise AssertionError(f"unexpected command: {argv}")


class ControlledEdgeFaultTest(unittest.TestCase):
    def _runtime_receipt(self) -> dict[str, object]:
        return {
            "status": "running",
            "env": "alpha",
            "target": "alpha-local",
            "workload": "full",
            "composeProject": "quwoquan_alpha_release_uat",
            "configurationDigest": "sha256:" + "1" * 64,
            "imageComposition": {
                "images": {"api-edge": {"ref": _sha256_digest("image:api-edge")}}
            },
        }

    def _topology(self) -> dict[str, object]:
        return {
            "targets": {
                "alpha-local": {
                    "env": "alpha",
                    "publicBases": {"api": "https://api.alpha.quwoquan.com:17000"},
                }
            }
        }

    def test_fault_binds_exact_runtime_containers_and_restores_idempotently(self) -> None:
        runner = _FakeRunner()
        health_results = iter((False, True))
        with (
            patch.object(edge_fault, "load_startup_attempt", return_value=self._runtime_receipt()),
            patch.object(edge_fault, "load_environment_topology", return_value=self._topology()),
        ):
            fault = edge_fault.begin_controlled_edge_fault(
                "alpha-local",
                runner=runner,
                health_probe=lambda _url: next(health_results),
                sleep=lambda _seconds: None,
            )
            self.assertEqual(fault.receipt()["status"], "fault_active")
            restored = fault.restore(timeout_seconds=1)
            repeated = fault.restore(timeout_seconds=1)

        self.assertEqual(restored["status"], "restored")
        self.assertEqual(repeated, restored)
        stop_commands = [command for command in runner.commands if command[:2] == ["docker", "stop"]]
        start_commands = [command for command in runner.commands if command[:2] == ["docker", "start"]]
        self.assertEqual(len(stop_commands), 1)
        self.assertEqual(len(start_commands), 1)
        self.assertEqual(
            stop_commands[0][-2:],
            ["container-api-edge", "container-gamma-proxy"],
        )

    def test_fault_rejects_api_edge_image_outside_runtime_receipt(self) -> None:
        runner = _FakeRunner(api_image=_sha256_digest("image:drifted-api-edge"))
        with (
            patch.object(edge_fault, "load_startup_attempt", return_value=self._runtime_receipt()),
            patch.object(edge_fault, "load_environment_topology", return_value=self._topology()),
        ):
            with self.assertRaisesRegex(ValueError, "image does not match"):
                edge_fault.begin_controlled_edge_fault(
                    "alpha-local",
                    runner=runner,
                    health_probe=lambda _url: False,
                )
        self.assertFalse(
            any(command[:2] == ["docker", "stop"] for command in runner.commands)
        )

    def test_fault_rejects_non_full_runtime(self) -> None:
        receipt = self._runtime_receipt()
        receipt["workload"] = "content-commercial"
        with patch.object(edge_fault, "load_startup_attempt", return_value=receipt):
            with self.assertRaisesRegex(ValueError, "full App runtime"):
                edge_fault.begin_controlled_edge_fault("alpha-local")


if __name__ == "__main__":
    unittest.main()

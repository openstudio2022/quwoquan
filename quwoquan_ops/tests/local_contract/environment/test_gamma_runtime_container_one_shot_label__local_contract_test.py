"""Gamma one-shot 容器的显式身份与 liveness 契约。

# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003
"""

from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from pathlib import Path

import yaml

from quwoquan_ops.cli.lib.runtime_container_liveness import (
    RUNTIME_ONE_SHOT_LABEL,
    RUNTIME_ONE_SHOT_LABEL_VALUE,
    inspect_compose_project_liveness,
)

ROOT = Path(__file__).resolve().parents[4]
COMPOSE_PATH = (
    ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
)


@dataclass(frozen=True)
class _Result:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def _row(name: str, service: str, state: str, status: str) -> dict[str, str]:
    return {
        "Names": name,
        "Service": service,
        "State": state,
        "Status": status,
    }


class _DockerRunner:
    def __init__(
        self,
        rows: list[dict[str, str]],
        labels: list[tuple[str, str, str, str]],
    ) -> None:
        self._rows = rows
        self._labels = labels
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], *, timeout_seconds: int) -> _Result:
        del timeout_seconds
        self.commands.append(command)
        if command[-1] == "json":
            return _Result(stdout="\n".join(json.dumps(row) for row in self._rows))
        return _Result(
            stdout="\n".join("\t".join(values) for values in self._labels)
        )


class GammaRuntimeContainerOneShotLabelTest(unittest.TestCase):
    def test_gamma_init_jobs_declare_canonical_self_label(self) -> None:
        compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
        services = compose["services"]

        for service in ("mongo-init", "object-storage-init"):
            with self.subTest(service=service):
                self.assertEqual(
                    services[service]["labels"][RUNTIME_ONE_SHOT_LABEL],
                    RUNTIME_ONE_SHOT_LABEL_VALUE,
                )
        self.assertNotIn("labels", services["object-storage"])

    def test_self_label_keeps_no_deps_completed_init_job_healthy(self) -> None:
        runner = _DockerRunner(
            [
                _row(
                    "gamma-object-storage-init-1",
                    "object-storage-init",
                    "exited",
                    "Exited (0) 1 minute ago",
                )
            ],
            [
                (
                    "gamma-object-storage-init-1",
                    "object-storage-init",
                    "",
                    RUNTIME_ONE_SHOT_LABEL_VALUE,
                )
            ],
        )
        report = inspect_compose_project_liveness(
            "gamma-project",
            runner=runner,
        )

        self.assertEqual(report.status, "healthy")
        self.assertTrue(report.containers[0].declared_one_shot)
        self.assertIn(RUNTIME_ONE_SHOT_LABEL, runner.commands[1][-1])

    def test_dependency_condition_remains_a_supported_declaration(self) -> None:
        report = inspect_compose_project_liveness(
            "gamma-project",
            runner=_DockerRunner(
                [_row("gamma-mongo-init-1", "mongo-init", "exited", "Exited (0)")],
                [
                    ("gamma-mongo-init-1", "mongo-init", "", ""),
                    (
                        "gamma-service-core-1",
                        "service-core",
                        "mongo-init:service_completed_successfully:false",
                        "",
                    ),
                ],
            ),
        )

        self.assertEqual(report.status, "healthy")
        self.assertTrue(report.containers[0].declared_one_shot)

    def test_zero_exit_and_service_name_never_infer_one_shot_identity(self) -> None:
        report = inspect_compose_project_liveness(
            "gamma-project",
            runner=_DockerRunner(
                [
                    _row(
                        "gamma-object-storage-init-1",
                        "object-storage-init",
                        "exited",
                        "Exited (0)",
                    )
                ],
                [("gamma-object-storage-init-1", "object-storage-init", "", "")],
            ),
        )

        self.assertEqual(report.status, "unavailable")
        self.assertFalse(report.containers[0].declared_one_shot)

    def test_invalid_self_label_fails_closed(self) -> None:
        for invalid in ("false", "yes", " true "):
            with (
                self.subTest(label=invalid),
                self.assertRaisesRegex(ValueError, "invalid canonical one-shot"),
            ):
                inspect_compose_project_liveness(
                    "gamma-project",
                    runner=_DockerRunner(
                        [
                            _row(
                                "gamma-object-storage-init-1",
                                "object-storage-init",
                                "exited",
                                "Exited (0)",
                            )
                        ],
                        [
                            (
                                "gamma-object-storage-init-1",
                                "object-storage-init",
                                "",
                                invalid,
                            )
                        ],
                    ),
                )

    def test_self_labeled_job_with_nonzero_exit_remains_degraded(self) -> None:
        report = inspect_compose_project_liveness(
            "gamma-project",
            runner=_DockerRunner(
                [
                    _row(
                        "gamma-object-storage-init-1",
                        "object-storage-init",
                        "exited",
                        "Exited (1)",
                    )
                ],
                [
                    (
                        "gamma-object-storage-init-1",
                        "object-storage-init",
                        "",
                        RUNTIME_ONE_SHOT_LABEL_VALUE,
                    )
                ],
            ),
        )

        self.assertEqual(report.status, "unavailable")
        self.assertTrue(report.containers[0].declared_one_shot)


if __name__ == "__main__":
    unittest.main()

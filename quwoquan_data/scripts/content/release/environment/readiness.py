"""Data-side adapter for the phase-scoped Ops environment receipt."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping

from core.io import write_json
from core.paths import REPO_ROOT
from content.release.model import DeploymentEnvironment


_STACKCTL = REPO_ROOT / "quwoquan_ops" / "cli" / "stackctl.py"
_RECEIPT_SCHEMA = "quwoquan_ops.ship_readiness_receipt"


class ShipReadinessPhase(StrEnum):
    IMPORT = "import"
    CONSUMER = "consumer"
    COMMERCIAL = "commercial"


@dataclass(frozen=True, slots=True)
class ShipReadinessReceipt:
    phase: ShipReadinessPhase
    environment: DeploymentEnvironment
    target: str
    outcome: str
    report_dir: str

    @property
    def passed(self) -> bool:
        return self.outcome == "PASS"


def phase_for_environment(
    environment: DeploymentEnvironment,
    *,
    consumer: bool,
) -> ShipReadinessPhase | None:
    if environment is DeploymentEnvironment.ALPHA:
        return None
    if environment is DeploymentEnvironment.PROD:
        return ShipReadinessPhase.COMMERCIAL
    if consumer and environment is DeploymentEnvironment.GAMMA:
        return ShipReadinessPhase.CONSUMER
    return ShipReadinessPhase.IMPORT


def _decode_receipt(value: object) -> ShipReadinessReceipt:
    if not isinstance(value, Mapping):
        raise ValueError("Ops ship readiness receipt must be an object")
    required = {"schema", "phase", "environment", "target", "outcome", "reportDir"}
    if not required.issubset(value) or value.get("schema") != _RECEIPT_SCHEMA:
        raise ValueError("Ops ship readiness receipt contract is invalid")
    return ShipReadinessReceipt(
        phase=ShipReadinessPhase(str(value["phase"])),
        environment=DeploymentEnvironment(str(value["environment"])),
        target=str(value["target"]),
        outcome=str(value["outcome"]),
        report_dir=str(value["reportDir"]),
    )


def require_environment_readiness(
    *,
    environment: DeploymentEnvironment,
    consumer: bool,
    run: Path,
) -> ShipReadinessReceipt | None:
    phase = phase_for_environment(environment, consumer=consumer)
    if phase is None:
        return None
    command = [
        sys.executable,
        str(_STACKCTL),
        "--output-format",
        "json",
        "content-readiness",
        "--phase",
        phase.value,
        "--env",
        environment.value,
        "--report-dir",
        str(run / "ops-readiness"),
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        receipt = _decode_receipt(json.loads(completed.stdout))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[ship] GATE_BLOCK {environment.value}/{phase.value}: Ops ship readiness receipt is invalid"
        ) from exc
    write_json(
        run / "environment-readiness.json",
        {
            "schema": "quwoquan_data.environment_readiness_ref",
            "phase": receipt.phase.value,
            "environment": receipt.environment.value,
            "target": receipt.target,
            "outcome": receipt.outcome,
            "opsReportDir": receipt.report_dir,
        },
    )
    if completed.returncode != 0 or not receipt.passed:
        raise SystemExit(
            f"[ship] GATE_BLOCK {environment.value}/{phase.value}: required environment capability is unavailable"
        )
    return receipt


__all__ = ["ShipReadinessPhase", "ShipReadinessReceipt", "phase_for_environment", "require_environment_readiness"]

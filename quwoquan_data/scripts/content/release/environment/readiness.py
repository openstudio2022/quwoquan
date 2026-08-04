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
    RESEARCH = "research"
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
    phase: ShipReadinessPhase,
    run: Path,
    release_id: str = "",
    verify_run_id: str = "",
    manifest_digest: str = "",
    lifecycle_exit_ref: str = "",
) -> ShipReadinessReceipt | None:
    release_id = str(release_id or "").strip()
    verify_run_id = str(verify_run_id or "").strip()
    manifest_digest = str(manifest_digest or "").strip()
    lifecycle_exit_ref = str(lifecycle_exit_ref or "").strip()
    if phase in {ShipReadinessPhase.CONSUMER, ShipReadinessPhase.COMMERCIAL} and (
        not release_id or not verify_run_id or not manifest_digest
    ):
        raise SystemExit(
            f"[ship] GATE_BLOCK {environment.value}/{phase.value}: "
            "releaseId, verifyRunId and manifestDigest are required"
        )
    if phase is ShipReadinessPhase.COMMERCIAL and not lifecycle_exit_ref:
        raise SystemExit(
            f"[ship] GATE_BLOCK {environment.value}/{phase.value}: "
            "lifecycleExitRef is required"
        )
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
    if phase is ShipReadinessPhase.RESEARCH and (
        not release_id or not manifest_digest
    ):
        raise SystemExit(
            f"[ship] GATE_BLOCK {environment.value}/{phase.value}: "
            "releaseId and manifestDigest are required"
        )
    if phase in {
        ShipReadinessPhase.RESEARCH,
        ShipReadinessPhase.CONSUMER,
        ShipReadinessPhase.COMMERCIAL,
    }:
        command.extend(
            [
                "--release-id",
                release_id,
                "--manifest-digest",
                manifest_digest,
            ]
        )
        if verify_run_id:
            command.extend(["--verify-run-id", verify_run_id])
        if lifecycle_exit_ref:
            command.extend(["--lifecycle-exit-ref", lifecycle_exit_ref])
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


__all__ = ["ShipReadinessPhase", "ShipReadinessReceipt", "require_environment_readiness"]

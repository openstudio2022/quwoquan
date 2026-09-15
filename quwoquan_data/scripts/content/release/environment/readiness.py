"""Data-side adapter for the action-scoped Ops environment receipt."""
from __future__ import annotations

import hashlib
import json
import os
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


class ShipReadinessAction(StrEnum):
    IMPORT = "import"
    VERIFY = "verify"


@dataclass(frozen=True, slots=True)
class ShipReadinessReceipt:
    action: ShipReadinessAction
    environment: DeploymentEnvironment
    target: str
    outcome: str
    report_dir: str
    workload: str
    candidate_digest: str
    provider_runtime_digest: str
    startup_attempt_id: str

    @property
    def passed(self) -> bool:
        return self.outcome == "PASS"


def _decode_receipt(value: object) -> ShipReadinessReceipt:
    if not isinstance(value, Mapping):
        raise ValueError("Ops ship readiness receipt must be an object")
    required = {
        "schema", "action", "environment", "target", "outcome", "reportDir",
        "workload", "candidateDigest", "providerRuntimeDigest", "startupAttemptId",
    }
    if not required.issubset(value) or value.get("schema") != _RECEIPT_SCHEMA:
        raise ValueError("Ops ship readiness receipt contract is invalid")
    return ShipReadinessReceipt(
        action=ShipReadinessAction(str(value["action"])),
        environment=DeploymentEnvironment(str(value["environment"])),
        target=str(value["target"]),
        outcome=str(value["outcome"]),
        report_dir=str(value["reportDir"]),
        workload=str(value["workload"]),
        candidate_digest=str(value["candidateDigest"]),
        provider_runtime_digest=str(value["providerRuntimeDigest"]),
        startup_attempt_id=str(value["startupAttemptId"]),
    )


def require_environment_readiness(
    *,
    environment: DeploymentEnvironment,
    action: ShipReadinessAction,
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
    if action is ShipReadinessAction.VERIFY and (
        not release_id or not verify_run_id or not manifest_digest
    ):
        raise SystemExit(
            f"[ship] GATE_BLOCK {environment.value}/{action.value}: "
            "releaseId, verifyRunId and manifestDigest are required"
        )
    command = [
        sys.executable,
        str(_STACKCTL),
        "--output-format",
        "json",
        "content-readiness",
        "--action",
        action.value,
        "--env",
        environment.value,
    ]
    if action is ShipReadinessAction.VERIFY:
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
    ops_env = dict(os.environ)
    for name in (
        "QWQ_DATA_ROOT",
        "QWQ_OUTPUT_ROOT",
        "QWQ_PUBLISH_ROOT",
        "QWQ_LIBRARY_ROOT",
        "QWQ_CARRIED_MEDIA_ROOT",
        "QWQ_DATA_PYTHON",
        "QWQ_DATA_CLI_BOOTSTRAPPED",
    ):
        ops_env.pop(name, None)
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=ops_env,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        receipt = _decode_receipt(json.loads(completed.stdout))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise SystemExit(
            f"[ship] GATE_BLOCK {environment.value}/{action.value}: Ops ship readiness receipt is invalid"
        ) from exc
    ops_report = Path(receipt.report_dir).expanduser().resolve() / "report.json"
    try:
        report_bytes = ops_report.read_bytes()
    except OSError as exc:
        raise SystemExit(
            f"[ship] GATE_BLOCK {environment.value}/{action.value}: "
            "canonical Ops readiness report is unavailable"
        ) from exc
    report_digest = "sha256:" + hashlib.sha256(report_bytes).hexdigest()
    evidence: dict[str, object] = {
        "schema": "quwoquan_data.environment_readiness_ref",
        "action": receipt.action.value,
        "environment": receipt.environment.value,
        "target": receipt.target,
        "outcome": receipt.outcome,
        "workload": receipt.workload,
        "candidateDigest": receipt.candidate_digest,
        "providerRuntimeDigest": receipt.provider_runtime_digest,
        "startupAttemptId": receipt.startup_attempt_id,
        "opsReceiptRef": str(ops_report),
        "opsReceiptDigest": report_digest,
    }
    if lifecycle_exit_ref:
        evidence["lifecycleExitRef"] = lifecycle_exit_ref
    write_json(run / "environment-readiness.json", evidence)
    if receipt.environment is not environment or receipt.action is not action:
        raise SystemExit(f"[ship] GATE_BLOCK {environment.value}/{action.value}: Ops readiness identity differs")
    if completed.returncode != 0 or not receipt.passed:
        raise SystemExit(
            f"[ship] GATE_BLOCK {environment.value}/{action.value}: required environment capability is unavailable"
        )
    return receipt


__all__ = ["ShipReadinessAction", "ShipReadinessReceipt", "require_environment_readiness"]

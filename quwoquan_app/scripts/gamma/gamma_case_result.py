#!/usr/bin/env python3
"""Produce candidate-bound Gamma release-consumer/device-UAT CaseResult evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_app.scripts.gamma import verify_local_gamma_mirror as gamma_verifier
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    load_candidate_manifest,
)
from quwoquan_ops.cli.lib.output_paths import (
    active_deployment_candidate,
    output_root,
)
from quwoquan_ops.cli.lib.startup_attempt_receipt import load_startup_attempt


ENVIRONMENT = "gamma"
TARGET = "gamma-local"
IDENTITY_SNAPSHOT_SCHEMA = "quwoquan.gamma-case-result-identity"
IDENTITY_FIELDS = (
    "environment",
    "target",
    "baselineId",
    "attemptId",
    "packageDigest",
    "configurationDigest",
    "providerRuntimeDigest",
    "observabilityLogSinkDigest",
    "imageDigest",
)
IDENTITY_SNAPSHOT_FIELDS = frozenset(
    {"schema", "phase", "preparedAt", "identity"}
)


class GammaCaseResultError(ValueError):
    """The current runtime cannot support a passed Gamma CaseResult."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GammaCaseResultError(f"{label} is invalid") from exc
    if parsed.tzinfo is None:
        raise GammaCaseResultError(f"{label} must include a timezone")
    return text


def resolve_gamma_evidence_path(raw_value: str, *, label: str) -> Path:
    """Keep every Gamma CaseResult artifact in the target evidence plane."""

    evidence_root_lexical = Path(
        os.path.abspath(output_root() / "env" / ENVIRONMENT / "runs")
    )
    evidence_root = evidence_root_lexical.resolve()
    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    candidate = Path(os.path.abspath(candidate))
    try:
        relative = candidate.relative_to(evidence_root_lexical)
    except ValueError as exc:
        raise GammaCaseResultError(
            f"{label} must stay below QWQ_OUTPUT_ROOT/env/gamma/runs"
        ) from exc

    # Do not resolve first: doing so would hide a symlink at the leaf or in an
    # existing parent.  Every existing component below the canonical evidence
    # root must be a physical directory/file owned by this target.
    current = evidence_root_lexical
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise GammaCaseResultError(f"{label} cannot traverse a symlink")

    resolved = candidate.resolve()
    try:
        resolved.relative_to(evidence_root)
    except ValueError as exc:
        raise GammaCaseResultError(
            f"{label} resolved outside QWQ_OUTPUT_ROOT/env/gamma/runs"
        ) from exc
    return resolved


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise GammaCaseResultError(f"{label} is missing or unsafe")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GammaCaseResultError(f"{label} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise GammaCaseResultError(f"{label} root must be an object")
    return payload


def _normalize_identity(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != set(IDENTITY_FIELDS):
        raise GammaCaseResultError("Gamma execution identity fields mismatch")
    identity = {field: str(value.get(field) or "") for field in IDENTITY_FIELDS}
    if identity["environment"] != ENVIRONMENT or identity["target"] != TARGET:
        raise GammaCaseResultError("Gamma execution identity target mismatch")
    return identity


def load_gamma_execution_identity() -> dict[str, str]:
    """Read one stable identity from the active candidate and running receipt."""

    try:
        startup = load_startup_attempt(TARGET)
        if startup is None:
            raise GammaCaseResultError("Gamma running startup receipt is missing")
        active = active_deployment_candidate(TARGET)
        if not isinstance(active, dict):
            raise GammaCaseResultError("Gamma active deployment candidate is missing")
        baseline_id = str(active.get("baselineId") or "")
        candidate = load_candidate_manifest(
            ENVIRONMENT,
            TARGET,
            baseline_id,
            require_full=True,
        )
        identity = gamma_verifier._candidate_identity(
            startup=startup,
            active=active,
            candidate=candidate,
            configuration_digest=str(startup.get("configurationDigest") or ""),
        )
        startup_after = load_startup_attempt(TARGET)
        active_after = active_deployment_candidate(TARGET)
    except GammaCaseResultError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise GammaCaseResultError(str(exc)) from exc

    if startup_after != startup or active_after != active:
        raise GammaCaseResultError(
            "Gamma startup or active candidate changed during identity validation"
        )
    return _normalize_identity(identity)


def require_unchanged_identity(expected: Mapping[str, str]) -> dict[str, str]:
    normalized = _normalize_identity(dict(expected))
    current = load_gamma_execution_identity()
    if current != normalized:
        raise GammaCaseResultError(
            "Gamma startup or active candidate changed during test execution"
        )
    return current


def build_passed_case_result(
    *,
    phase: str,
    identity: Mapping[str, str],
    executed: int,
    skipped: int,
    failed: int,
    executed_at: str,
) -> dict[str, Any]:
    normalized_identity = _normalize_identity(dict(identity))
    payload: dict[str, Any] = {
        "schema": gamma_verifier.CASE_RESULT_SCHEMA,
        "caseId": gamma_verifier.CASE_IDS[phase],
        "status": "passed",
        **normalized_identity,
        "executed": executed,
        "skipped": skipped,
        "failed": failed,
        "executedAt": _timestamp(executed_at, label=f"{phase} executedAt"),
        "specRefs": list(gamma_verifier.CASE_SPEC_REFS),
    }
    try:
        return gamma_verifier.validate_gamma_case_result(
            payload,
            phase=phase,
            identity=normalized_identity,
        )
    except (TypeError, ValueError) as exc:
        raise GammaCaseResultError(str(exc)) from exc


def blocked_case_result(
    *,
    phase: str,
    reason: str,
    identity: Mapping[str, str] | None = None,
    status: str = "gate_block",
    executed: int = 0,
    skipped: int = 0,
    failed: int = 0,
) -> dict[str, Any]:
    if status not in {"gate_block", "failed"}:
        raise GammaCaseResultError("blocked CaseResult status is invalid")
    payload: dict[str, Any] = {
        "schema": gamma_verifier.CASE_RESULT_SCHEMA,
        "caseId": gamma_verifier.CASE_IDS[phase],
        "status": status,
        "executed": executed,
        "skipped": skipped,
        "failed": failed,
        "executedAt": utc_now(),
        "specRefs": list(gamma_verifier.CASE_SPEC_REFS),
        "reason": str(reason or "Gamma execution did not produce passed evidence"),
    }
    if identity is not None:
        payload.update(_normalize_identity(dict(identity)))
    return payload


def write_blocked_case_result(
    *,
    report_path: Path,
    phase: str,
    reason: str,
    identity: Mapping[str, str] | None = None,
    status: str = "gate_block",
    executed: int = 0,
    skipped: int = 0,
    failed: int = 0,
) -> dict[str, Any]:
    payload = blocked_case_result(
        phase=phase,
        reason=reason,
        identity=identity,
        status=status,
        executed=executed,
        skipped=skipped,
        failed=failed,
    )
    _write_json(report_path, payload)
    return payload


def write_passed_case_result(
    *,
    report_path: Path,
    phase: str,
    identity: Mapping[str, str],
    executed: int,
    skipped: int,
    failed: int,
    executed_at: str,
) -> dict[str, Any]:
    payload = build_passed_case_result(
        phase=phase,
        identity=identity,
        executed=executed,
        skipped=skipped,
        failed=failed,
        executed_at=executed_at,
    )
    _write_json(report_path, payload)
    return payload


def write_identity_snapshot(
    *,
    path: Path,
    phase: str,
    identity: Mapping[str, str],
) -> dict[str, Any]:
    if phase not in gamma_verifier.CASE_IDS:
        raise GammaCaseResultError(f"unsupported Gamma CaseResult phase: {phase}")
    payload = {
        "schema": IDENTITY_SNAPSHOT_SCHEMA,
        "phase": phase,
        "preparedAt": utc_now(),
        "identity": _normalize_identity(dict(identity)),
    }
    _write_json(path, payload)
    return payload


def load_identity_snapshot(*, path: Path, phase: str) -> dict[str, str]:
    payload = _load_json(path, label=f"{phase} identity snapshot")
    if (
        set(payload) != IDENTITY_SNAPSHOT_FIELDS
        or payload.get("schema") != IDENTITY_SNAPSHOT_SCHEMA
        or payload.get("phase") != phase
    ):
        raise GammaCaseResultError(f"{phase} identity snapshot fields mismatch")
    _timestamp(payload.get("preparedAt"), label=f"{phase} identity preparedAt")
    return _normalize_identity(payload.get("identity"))


def prepare_device_uat(
    *,
    report_path: Path,
    identity_snapshot_path: Path,
    patrol_report_path: Path,
) -> dict[str, str]:
    # Invalidate every reusable input before identity validation.  A stopped or
    # missing receipt must never leave an earlier passed CaseResult/snapshot/raw
    # Patrol report available for a later finalize invocation.
    write_blocked_case_result(
        report_path=report_path,
        phase="device_uat",
        reason="Gamma device-UAT identity validation has not completed",
    )
    _write_json(
        identity_snapshot_path,
        {
            "schema": IDENTITY_SNAPSHOT_SCHEMA,
            "phase": "device_uat",
            "status": "gate_block",
            "preparedAt": utc_now(),
        },
    )
    _write_json(
        patrol_report_path,
        {
            "schema": "quwoquan.gamma-device-uat-patrol-preflight",
            "status": "gate_block",
            "reason": "Gamma device-UAT Patrol execution has not started",
            "preparedAt": utc_now(),
        },
    )
    # Resolve the raw evidence path before executing Patrol so a symlink or an
    # out-of-plane override cannot redirect the underlying report.
    resolve_gamma_evidence_path(
        str(patrol_report_path),
        label="Gamma device-UAT Patrol report",
    )
    identity = load_gamma_execution_identity()
    write_blocked_case_result(
        report_path=report_path,
        phase="device_uat",
        reason="Gamma device-UAT execution has not completed",
        identity=identity,
    )
    write_identity_snapshot(
        path=identity_snapshot_path,
        phase="device_uat",
        identity=identity,
    )
    return identity


def _patrol_execution_counts(payload: Mapping[str, Any]) -> tuple[int, int, int, str]:
    if payload.get("status") != "passed":
        raise GammaCaseResultError(
            f"Gamma device-UAT Patrol report status is {payload.get('status') or 'missing'}"
        )
    if (
        payload.get("composition") != "production_remote"
        or payload.get("evidenceClass") != "user_acceptance_remote"
        or payload.get("runtimeEnv") != ENVIRONMENT
        or payload.get("apiContractEnv") != ENVIRONMENT
        or payload.get("environmentAlias") not in {"local-gamma", TARGET}
    ):
        raise GammaCaseResultError("Gamma device-UAT Patrol composition identity mismatch")

    devices = payload.get("devices")
    runs = payload.get("runs")
    cases = payload.get("caseResults")
    if (
        not isinstance(devices, list)
        or not devices
        or not isinstance(runs, list)
        or not runs
        or not isinstance(cases, list)
        or not cases
        or len(runs) != len(cases)
    ):
        raise GammaCaseResultError("Gamma device-UAT Patrol report has no executed device matrix")

    device_ids = {
        str(device.get("id") or "").strip()
        for device in devices
        if isinstance(device, dict)
    }
    case_device_ids = {
        str(case.get("deviceId") or "").strip()
        for case in cases
        if isinstance(case, dict)
    }
    if (
        "" in device_ids
        or "" in case_device_ids
        or not case_device_ids
        or not case_device_ids.issubset(device_ids)
    ):
        raise GammaCaseResultError("Gamma device-UAT Patrol device identity is incomplete")

    executed = 0
    skipped = 0
    failed = 0
    for index, (run, case) in enumerate(zip(runs, cases, strict=True)):
        if not isinstance(run, dict) or not isinstance(case, dict):
            raise GammaCaseResultError("Gamma device-UAT Patrol run entry is invalid")
        run_summary = run.get("testExecution")
        case_summary = case.get("testExecution")
        if (
            run.get("exitCode") != 0
            or case.get("status") != "passed"
            or run_summary != case_summary
            or not isinstance(run_summary, dict)
        ):
            raise GammaCaseResultError(
                f"Gamma device-UAT Patrol run {index} is not a passed execution"
            )
        counts = tuple(
            run_summary.get(field) for field in ("executed", "skipped", "failed")
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in counts
        ):
            raise GammaCaseResultError(
                f"Gamma device-UAT Patrol run {index} execution counts are invalid"
            )
        run_executed, run_skipped, run_failed = counts
        executed += run_executed
        skipped += run_skipped
        failed += run_failed

    if executed <= 0 or skipped != 0 or failed != 0:
        raise GammaCaseResultError(
            "Gamma device-UAT requires executed>0, skipped=0, failed=0"
        )
    return (
        executed,
        skipped,
        failed,
        _timestamp(payload.get("endedAt"), label="Gamma device-UAT Patrol endedAt"),
    )


def finalize_device_uat(
    *,
    report_path: Path,
    identity_snapshot_path: Path,
    patrol_report_path: Path,
    dry_run: bool,
    runner_exit_code: int = 0,
) -> dict[str, Any]:
    identity: dict[str, str] | None = None
    try:
        identity = load_identity_snapshot(
            path=identity_snapshot_path,
            phase="device_uat",
        )
        require_unchanged_identity(identity)
        if runner_exit_code != 0:
            raise GammaCaseResultError(
                f"Gamma device-UAT Patrol runner exited with {runner_exit_code}"
            )
        if dry_run:
            raise GammaCaseResultError("Gamma device-UAT dry-run has no executed CaseResult")
        patrol_report = _load_json(
            patrol_report_path,
            label="Gamma device-UAT Patrol report",
        )
        executed, skipped, failed, executed_at = _patrol_execution_counts(
            patrol_report
        )
        payload = build_passed_case_result(
            phase="device_uat",
            identity=identity,
            executed=executed,
            skipped=skipped,
            failed=failed,
            executed_at=executed_at,
        )
        _write_json(report_path, payload)
        return payload
    except GammaCaseResultError as exc:
        source_status = ""
        source_executed = 0
        source_skipped = 0
        source_failed = 0
        try:
            source = _load_json(
                patrol_report_path,
                label="Gamma device-UAT Patrol report",
            )
            source_status = str(source.get("status") or "")
            for case in source.get("caseResults") or []:
                if not isinstance(case, dict):
                    continue
                summary = case.get("testExecution")
                if not isinstance(summary, dict):
                    continue
                values = [summary.get(field) for field in ("executed", "skipped", "failed")]
                if all(
                    isinstance(value, int) and not isinstance(value, bool)
                    for value in values
                ):
                    source_executed += values[0]
                    source_skipped += values[1]
                    source_failed += values[2]
        except GammaCaseResultError:
            pass
        return write_blocked_case_result(
            report_path=report_path,
            phase="device_uat",
            reason=str(exc),
            identity=identity,
            status="failed" if source_status == "failed" else "gate_block",
            executed=source_executed,
            skipped=source_skipped,
            failed=source_failed,
        )


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    report = resolve_gamma_evidence_path(args.report, label="Gamma device-UAT CaseResult")
    identity = resolve_gamma_evidence_path(
        args.identity_snapshot,
        label="Gamma device-UAT identity snapshot",
    )
    patrol = resolve_gamma_evidence_path(
        args.patrol_report,
        label="Gamma device-UAT Patrol report",
    )
    if len({report, identity, patrol}) != 3:
        raise GammaCaseResultError("Gamma device-UAT evidence paths must be distinct")
    return report, identity, patrol


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("prepare-device-uat", "finalize-device-uat", "block-device-uat"):
        child = subparsers.add_parser(command)
        child.add_argument("--report", required=True)
        child.add_argument("--identity-snapshot", required=True)
        child.add_argument("--patrol-report", required=True)
        if command == "finalize-device-uat":
            child.add_argument("--dry-run", action="store_true")
            child.add_argument("--runner-exit-code", type=int, default=0)
        if command == "block-device-uat":
            child.add_argument("--reason", required=True)

    args = parser.parse_args()
    try:
        report_path, identity_path, patrol_path = _paths(args)
        if args.command == "prepare-device-uat":
            prepare_device_uat(
                report_path=report_path,
                identity_snapshot_path=identity_path,
                patrol_report_path=patrol_path,
            )
            return 0
        if args.command == "finalize-device-uat":
            payload = finalize_device_uat(
                report_path=report_path,
                identity_snapshot_path=identity_path,
                patrol_report_path=patrol_path,
                dry_run=bool(args.dry_run),
                runner_exit_code=int(args.runner_exit_code),
            )
            if payload["status"] == "passed":
                return 0
            return 1 if payload["status"] == "failed" else 2

        identity: dict[str, str] | None = None
        try:
            identity = load_identity_snapshot(path=identity_path, phase="device_uat")
        except GammaCaseResultError:
            pass
        write_blocked_case_result(
            report_path=report_path,
            phase="device_uat",
            reason=args.reason,
            identity=identity,
        )
        return 2
    except GammaCaseResultError as exc:
        print(f"Gamma device-UAT GATE_BLOCK: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

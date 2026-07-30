"""stackctl matrix：固定候选上的 Alpha → Beta → Gamma 串行门禁。"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from quwoquan_ops.cli.lib.local_env_gate_timing import (
    PhaseTimer,
    load_local_env_matrix_budgets,
    utc_now,
    write_timing_bundle,
)
from quwoquan_ops.cli.lib.local_postgres_migration_drift import (
    format_drift_gate_block,
    probe_migration_drift,
)
from quwoquan_ops.cli.lib.output_paths import output_root


ROOT = Path(__file__).resolve().parents[3]
PROFILE_LOCAL_ENV_GATE = "local-env-gate"
CANONICAL_TARGETS = ("alpha-local", "beta-local", "gamma-local")
TARGET_ENVIRONMENTS = {
    "alpha-local": "alpha",
    "beta-local": "beta",
    "gamma-local": "gamma",
}
SPEC_REFS = (
    "AppRoot/JNY-002/SCN-005/UAT-003",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-001",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-002",
    "runtime/runtime-config/environment-ops-cli-and-skill/GWT-001",
    "runtime/deliver-deploy-prod-pipeline/SIT-001",
    "runtime/system-architecture-and-engineering-guide/SIT-003",
    "runtime/runtime-data-engineering/SIT-001",
)

EnvRunner = Callable[..., dict[str, Any]]


def _repo_matrix_dir() -> Path:
    path = output_root() / "env" / "repo" / "runs" / "local-env-gate"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _evidence_path(path: Path) -> str:
    """Keep repo evidence relative while allowing isolated test/output roots."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _namespace(**kwargs: Any) -> Any:
    import argparse

    return argparse.Namespace(**kwargs)


def _run_commit_gate() -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        ["make", "commit-gate"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    summary_path = (
        ROOT
        / ".qwq_output"
        / "env"
        / "repo"
        / "runs"
        / "commit-gate"
        / "summary.json"
    )
    summary: dict[str, Any] = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "exitCode": result.returncode,
        "durationMs": int((time.monotonic() - started) * 1000),
        "summary": summary,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
        "reportDir": (
            str(summary_path.parent.relative_to(ROOT)) if summary_path.exists() else ""
        ),
    }


def _docker_daemon_ready() -> tuple[bool, str]:
    result = subprocess.run(
        ["docker", "info"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return True, "docker daemon ready"
    detail = (result.stderr or result.stdout or "docker info failed").strip()
    return False, detail[:300]


def _record_phase(
    phases: list[dict[str, Any]],
    *,
    name: str,
    payload: dict[str, Any],
) -> int:
    exit_code = int(payload.get("exitCode") or 0)
    phases.append(
        PhaseTimer(name).finish(
            status="passed" if exit_code == 0 else "gate_block",
            details=[str(payload.get("summary") or "")]
            + [str(item) for item in list(payload.get("details") or [])[:8]],
            report_dir=str(payload.get("reportDir") or ""),
        )
    )
    return exit_code


def _down_target(target: str, *, down_fn: EnvRunner) -> dict[str, Any]:
    """Only use stackctl down; never kill listeners, clear locks, or wipe state."""
    return down_fn(
        _namespace(
            command="down",
            target=target,
            formal_release_teardown=False,
            release_manifest="",
            output_format="json",
            report_dir="",
        )
    )


def _write_matrix_result(
    *,
    matrix_dir: Path,
    phases: list[dict[str, Any]],
    environments: dict[str, Any],
    budgets: dict[str, Any],
    wall_seconds: float,
    exit_code: int,
    failure_category: str,
) -> dict[str, Any]:
    passed = exit_code == 0 and tuple(environments) == CANONICAL_TARGETS
    claim = "ALPHA_BETA_GAMMA_LOCAL_GREEN" if passed else "GATE_BLOCK"
    status = "passed" if passed else "gate_block"
    executed = len(phases)
    skipped = 0
    timing_path = write_timing_bundle(
        matrix_dir,
        phases=phases,
        wall_clock_seconds=wall_seconds,
        budgets=budgets,
        claim=claim,
        cache_mode="package-bound",
        extras={
            "failureCategory": failure_category,
            "targets": list(CANONICAL_TARGETS),
            "executed": executed,
            "skipped": skipped,
        },
    )
    payload = {
        "schema": "quwoquan.test.case-result",
        "generatedAt": utc_now(),
        "caseId": "stackctl.local-env-gate.alpha-beta-gamma",
        "status": status,
        "claim": claim,
        "executed": executed,
        "skipped": skipped,
        "specRefs": list(SPEC_REFS),
        "targets": list(CANONICAL_TARGETS),
        "wallClockSeconds": round(wall_seconds, 3),
        "softBudgetSeconds": budgets["softBudgetSeconds"],
        "hardBudgetSeconds": budgets["hardBudgetSeconds"],
        "failureCategory": failure_category,
        "timingPath": _evidence_path(timing_path),
        "phases": phases,
        "environments": environments,
    }
    (matrix_dir / "matrix.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (matrix_dir / "matrix.md").write_text(
        "\n".join(
            [
                "# Alpha / Beta / Gamma local gate",
                "",
                f"- status: `{status}`",
                f"- claim: `{claim}`",
                f"- executed/skipped: `{executed}/{skipped}`",
                f"- failureCategory: `{failure_category or 'none'}`",
                f"- timing: `{_evidence_path(timing_path)}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "exitCode": 0 if passed else (exit_code or 2),
        "summary": f"stackctl matrix {PROFILE_LOCAL_ENV_GATE}: {claim}",
        "details": [
            f"status={status}",
            f"executed={executed}",
            f"skipped={skipped}",
            f"timing={_evidence_path(timing_path)}",
            f"failureCategory={failure_category or 'none'}",
        ],
        "reportDir": _evidence_path(matrix_dir),
        "claim": claim,
        "status": status,
        "executed": executed,
        "skipped": skipped,
        "wallClockSeconds": round(wall_seconds, 3),
    }


def run_local_env_gate_matrix(
    *,
    package_fn: EnvRunner,
    up_fn: EnvRunner,
    health_fn: EnvRunner,
    verify_fn: EnvRunner,
    down_fn: EnvRunner,
    targets: tuple[str, ...] = CANONICAL_TARGETS,
    include_l0: bool = True,
    release_attestation: str = "",
    rollback_release_attestation: str = "",
) -> dict[str, Any]:
    """Run one package-bound full-workload state machine per local environment."""
    if tuple(targets) != CANONICAL_TARGETS:
        return {
            "exitCode": 2,
            "summary": "stackctl matrix target set is GATE_BLOCK",
            "details": [
                "--targets must be exactly alpha-local,beta-local,gamma-local in order"
            ],
            "claim": "GATE_BLOCK",
            "status": "gate_block",
            "executed": 0,
            "skipped": 0,
        }

    budgets = load_local_env_matrix_budgets()
    matrix_dir = _repo_matrix_dir()
    wall_started = time.monotonic()
    phases: list[dict[str, Any]] = []
    environments: dict[str, Any] = {}
    overall_exit = 0
    failure_category = ""

    docker_ok, docker_detail = _docker_daemon_ready()
    phases.append(
        PhaseTimer("docker_daemon_preflight").finish(
            status="passed" if docker_ok else "gate_block",
            details=[docker_detail],
        )
    )
    if not docker_ok:
        overall_exit = 2
        failure_category = "docker"

    if overall_exit == 0 and include_l0:
        l0 = _run_commit_gate()
        phases.append(
            PhaseTimer("L0_commit_gate").finish(
                status="passed" if l0["exitCode"] == 0 else "gate_block",
                details=[f"exit={l0['exitCode']}"],
                report_dir=l0.get("reportDir", ""),
            )
        )
        if l0["exitCode"] != 0:
            overall_exit = int(l0["exitCode"] or 2)
            failure_category = "l0"

    for target in targets:
        if overall_exit != 0:
            break
        if time.monotonic() - wall_started > int(budgets["hardBudgetSeconds"]):
            overall_exit = 2
            failure_category = "budget"
            phases.append(
                PhaseTimer(f"{target}_budget").finish(
                    status="gate_block",
                    details=["hard budget exhausted before target execution"],
                )
            )
            break

        env_name = TARGET_ENVIRONMENTS[target]
        block: dict[str, Any] = {
            "target": target,
            "environment": env_name,
            "workload": "full",
            "profile": "integration",
        }

        # The local targets share resources. Normal down is the sole cleanup path.
        for other in CANONICAL_TARGETS:
            down_payload = _down_target(other, down_fn=down_fn)
            down_exit = _record_phase(
                phases,
                name=f"{target}_pre_down_{other}",
                payload=down_payload,
            )
            if down_exit != 0:
                block["preDown"] = down_payload
                overall_exit = down_exit
                failure_category = "down"
                break
        if overall_exit != 0:
            environments[target] = block
            break

        package_payload = package_fn(
            _namespace(
                command="package",
                kind="runtime",
                env=env_name,
                service="",
                include_services=True,
                target=target,
                output_format="json",
                report_dir="",
                apk_path="",
                verify_remote_apk=False,
                release_attestation=release_attestation,
                rollback_release_attestation=rollback_release_attestation,
            )
        )
        block["package"] = package_payload
        package_exit = _record_phase(
            phases,
            name=f"{target}_package",
            payload=package_payload,
        )
        if package_exit != 0:
            overall_exit = package_exit
            failure_category = "package"
            environments[target] = block
            break

        if target in {"alpha-local", "beta-local"}:
            drift = probe_migration_drift(target)
            phases.append(
                PhaseTimer(f"{target}_migration_drift_probe").finish(
                    status="gate_block" if drift.has_drift else "passed",
                    details=[
                        format_drift_gate_block(drift) if drift.has_drift else drift.detail
                    ],
                )
            )
            if drift.has_drift:
                overall_exit = 2
                failure_category = "migration_drift"
                environments[target] = block
                break

        up_payload = up_fn(
            _namespace(
                command="up",
                env=env_name,
                target="",
                workload="full",
                skip_app=True,
                skip_build=True,
                build_only=False,
                build_services="",
                formal_release=False,
                release_manifest="",
                rollout_mode="",
                device_id="",
                output_format="json",
                report_dir="",
            )
        )
        block["up"] = up_payload
        up_exit = _record_phase(phases, name=f"{target}_up", payload=up_payload)
        if up_exit != 0:
            overall_exit = up_exit
            failure_category = "up"
            environments[target] = block
            break

        health_payload = health_fn(
            _namespace(
                command="health",
                target=target,
                scope="all",
                output_format="json",
                report_dir="",
                request_timeout_seconds=0,
                retry_attempts=0,
                retry_sleep_seconds=-1.0,
            )
        )
        block["health"] = health_payload
        health_exit = _record_phase(
            phases,
            name=f"{target}_health",
            payload=health_payload,
        )
        if health_exit != 0:
            overall_exit = health_exit
            failure_category = "health"

        if overall_exit == 0:
            verify_payload = verify_fn(
                _namespace(
                    command="verify",
                    kind="all",
                    env=env_name,
                    target=target,
                    profile="integration",
                    service="",
                    output_format="json",
                    report_dir="",
                    backup_recovery_receipt="",
                    data_release_id="",
                    data_verify_run_id="",
                    data_manifest_digest="",
                    data_lifecycle_exit_ref="",
                    distribution_root="",
                    verify_hosted=False,
                )
            )
            block["verify"] = verify_payload
            verify_exit = _record_phase(
                phases,
                name=f"{target}_verify_integration",
                payload=verify_payload,
            )
            if verify_exit != 0:
                overall_exit = verify_exit
                failure_category = "verify"

        down_payload = _down_target(target, down_fn=down_fn)
        block["down"] = down_payload
        down_exit = _record_phase(
            phases,
            name=f"{target}_down",
            payload=down_payload,
        )
        if down_exit != 0:
            overall_exit = down_exit
            failure_category = "down"

        environments[target] = block
        if overall_exit != 0:
            break

    wall_seconds = time.monotonic() - wall_started
    if wall_seconds > int(budgets["hardBudgetSeconds"]) and overall_exit == 0:
        overall_exit = 2
        failure_category = "budget"
    return _write_matrix_result(
        matrix_dir=matrix_dir,
        phases=phases,
        environments=environments,
        budgets=budgets,
        wall_seconds=wall_seconds,
        exit_code=overall_exit,
        failure_category=failure_category,
    )

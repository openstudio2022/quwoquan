"""stackctl matrix：固定候选上的 Alpha → Beta → Gamma 串行门禁。"""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

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
from quwoquan_ops.cli.lib.startup_attempt_receipt import load_startup_attempt


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
    "AppRoot/JNY-001/SCN-004/UAT-009",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-001",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-002",
    "runtime/runtime-config/environment-ops-cli-and-skill/GWT-001",
    "runtime/deliver-deploy-prod-pipeline/SIT-001",
    "runtime/system-architecture-and-engineering-guide/SIT-003",
    "runtime/runtime-data-engineering/SIT-001",
    "runtime/runtime-external-integration/provider-adapter-conformance-suite/GWT-002",
)

EnvRunner = Callable[..., dict[str, Any]]
DataRunner = Callable[..., dict[str, Any]]
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")


def _new_matrix_run_id() -> str:
    return (
        "matrix-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid4().hex[:12]
    )


def _matrix_lease_path() -> Path:
    path = (
        output_root()
        / "env"
        / "repo"
        / "local"
        / "process"
        / "local-env-gate.lock"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class MatrixExecutionLeaseBusy(RuntimeError):
    """Another live local environment matrix still owns the repository lease."""


@contextmanager
def _matrix_execution_lease(matrix_run_id: str) -> Iterator[Path]:
    """Bind live matrix exclusion to one process lifetime via an OS lock."""
    path = _matrix_lease_path()
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            owner = handle.read().strip()
            detail = owner if owner else "owner metadata unavailable"
            raise MatrixExecutionLeaseBusy(
                f"live local environment matrix lease is already held: {detail}"
            ) from exc

        owner = {
            "schema": "quwoquan_ops.local_env_gate_matrix_lease",
            "status": "active",
            "matrixRunId": matrix_run_id,
            "pid": os.getpid(),
            "startedAt": utc_now(),
        }
        handle.seek(0)
        handle.truncate()
        json.dump(owner, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        try:
            yield path
        finally:
            released = {
                **owner,
                "status": "released",
                "releasedAt": utc_now(),
            }
            try:
                handle.seek(0)
                handle.truncate()
                json.dump(released, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _repo_matrix_dir(matrix_run_id: str) -> Path:
    path = (
        output_root()
        / "env"
        / "repo"
        / "runs"
        / "local-env-gate"
        / matrix_run_id
    )
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


def _release_binding(attestation: str, *, label: str) -> dict[str, str]:
    path = Path(str(attestation or "").strip()).expanduser()
    if not str(attestation or "").strip():
        raise ValueError(f"{label} release attestation is required")
    try:
        payload = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} release attestation is unreadable: {exc}") from exc
    release_id = str(payload.get("releaseId") or "").strip() if isinstance(payload, dict) else ""
    digest = str(payload.get("payloadSha256") or "").strip() if isinstance(payload, dict) else ""
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "quwoquan_data.release_attestation"
        or not release_id
        or _SHA256.fullmatch(digest) is None
    ):
        raise ValueError(f"{label} release attestation identity is invalid")
    return {"releaseId": release_id, "releaseDigest": digest, "attestation": str(path.resolve())}


def _data_cli_runner(*, argv: list[str], report_path: Path, **_: Any) -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    stdout_payload: dict[str, Any] | None = None
    try:
        parsed = json.loads(result.stdout)
        if isinstance(parsed, dict):
            stdout_payload = parsed
    except json.JSONDecodeError:
        pass
    return {
        "exitCode": result.returncode,
        "summary": " ".join(argv[2:5]) + (" passed" if result.returncode == 0 else " failed"),
        "details": [
            line.strip()
            for line in (result.stderr or result.stdout or "").splitlines()
            if line.strip()
        ][-8:],
        "reportDir": _evidence_path(report_path.parent),
        "reportPath": _evidence_path(report_path),
        "payload": stdout_payload,
        "durationMs": int((time.monotonic() - started) * 1000),
    }


def _data_run_ids(matrix_run_id: str, environment: str) -> dict[str, str]:
    prefix = f"{matrix_run_id}-{environment}"
    return {
        "originalImport": f"{prefix}-original-import",
        "originalVerify": f"{prefix}-original-verify",
        "rollbackImport": f"{prefix}-rollback-import",
        "rollbackVerify": f"{prefix}-rollback-verify",
        "replayImport": f"{prefix}-replay-import",
        "replayVerify": f"{prefix}-replay-verify",
        "lifecycleExit": f"{prefix}-lifecycle-exit",
    }


def _data_readiness_path(environment: str, release_id: str, run_id: str) -> Path:
    return (
        output_root()
        / "env"
        / environment
        / "runs"
        / "data-release"
        / release_id
        / run_id
        / "release-readiness.json"
    )


def _lifecycle_exit_path(environment: str, release_id: str, run_id: str) -> Path:
    return (
        output_root()
        / "env"
        / environment
        / "runs"
        / "release-lifecycle-exit"
        / release_id
        / run_id
        / "lifecycle-exit.json"
    )


def _homepage_release_evidence(
    *,
    readiness_path: Path,
    environment: str,
    release_id: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(readiness_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {
            "exitCode": 2,
            "summary": "homepage release readiness is unreadable",
            "details": [str(exc)],
            "reportDir": _evidence_path(readiness_path.parent),
        }
    feed_queries = payload.get("feedQueries") if isinstance(payload, dict) else None
    homepage = next(
        (
            item
            for item in feed_queries or []
            if isinstance(item, dict) and item.get("name") == "homepage_recommend"
        ),
        None,
    )
    matched = list(homepage.get("matchedPostIds") or []) if isinstance(homepage, dict) else []
    passed = (
        payload.get("schema") == "quwoquan_data.environment_release_readiness"
        and payload.get("environment") == environment
        and payload.get("releaseId") == release_id
        and payload.get("readinessPhase") == "consumer"
        and not any(
            isinstance(item, dict) and item.get("name") == "premium_stream"
            for item in feed_queries or []
        )
        and isinstance(homepage, dict)
        and homepage.get("status") == 200
        and homepage.get("releaseBound") is True
        and bool(matched)
    )
    return {
        "exitCode": 0 if passed else 2,
        "summary": (
            "homepage recommendation release evidence passed"
            if passed
            else "homepage recommendation release evidence is GATE_BLOCK"
        ),
        "details": [
            f"environment={environment}",
            f"releaseId={release_id}",
            f"outcome={'content' if matched else 'empty'}",
            f"emptyReason={'none' if matched else 'release_content_missing'}",
            f"itemCount={len(matched)}",
        ],
        "reportDir": _evidence_path(readiness_path.parent),
        "reportPath": _evidence_path(readiness_path),
        "outcome": "content" if matched else "empty",
        "emptyReason": None if matched else "release_content_missing",
        "itemCount": len(matched),
    }


def _acceptance_lease_event(
    payload: dict[str, Any],
    *,
    action: str,
    environment: str,
    release_id: str,
    lease_id: str,
) -> dict[str, Any]:
    event = payload.get("payload")
    if (
        not isinstance(event, dict)
        or event.get("schema") != "quwoquan_data.release_acceptance_lease_event"
        or event.get("action") != action
        or event.get("environment") != environment
        or event.get("releaseId") != release_id
        or event.get("leaseId") != lease_id
        or not str(event.get("eventRef") or "").strip()
    ):
        raise ValueError(
            f"Data acceptance lease {action} returned identity-drifted evidence"
        )
    return event


def _run_data_phase(
    phases: list[dict[str, Any]],
    *,
    phase_name: str,
    environment: str,
    action: str,
    argv: list[str],
    report_path: Path,
    data_fn: DataRunner,
) -> tuple[int, dict[str, Any]]:
    started = time.monotonic()
    try:
        payload = data_fn(
            environment=environment,
            action=action,
            argv=argv,
            report_path=report_path,
        )
    except Exception as exc:
        payload = {
            "exitCode": 2,
            "summary": f"{action} raised an exception",
            "details": [f"{type(exc).__name__}: {exc}"],
            "reportDir": _evidence_path(report_path.parent),
            "durationMs": int((time.monotonic() - started) * 1000),
        }
    return (
        _record_phase(phases, name=phase_name, payload=payload),
        payload,
    )


def _record_phase(
    phases: list[dict[str, Any]],
    *,
    name: str,
    payload: dict[str, Any],
) -> int:
    raw_exit_code = payload.get("exitCode")
    exit_code = int(raw_exit_code) if isinstance(raw_exit_code, int) else 2
    phase = PhaseTimer(name).finish(
        status="passed" if exit_code == 0 else "gate_block",
        details=[str(payload.get("summary") or "")]
        + [str(item) for item in list(payload.get("details") or [])[:8]],
        report_dir=str(payload.get("reportDir") or ""),
    )
    duration_ms = payload.get("durationMs")
    if isinstance(duration_ms, int) and duration_ms >= 0:
        phase["durationMs"] = duration_ms
    phases.append(phase)
    return exit_code


def _invoke_env(fn: EnvRunner, args: Any, *, action: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        payload = fn(args)
        if not isinstance(payload, dict):
            raise TypeError("runner returned a non-object payload")
        return payload
    except Exception as exc:
        return {
            "exitCode": 2,
            "summary": f"{action} raised an exception",
            "details": [f"{type(exc).__name__}: {exc}"],
            "reportDir": "",
            "durationMs": int((time.monotonic() - started) * 1000),
        }


def _down_target(target: str, *, down_fn: EnvRunner) -> dict[str, Any]:
    """Only use stackctl down; never kill listeners, clear locks, or wipe state."""
    return _invoke_env(
        down_fn,
        _namespace(
            command="down",
            target=target,
            formal_release_teardown=False,
            release_manifest="",
            output_format="json",
            report_dir="",
        ),
        action=f"{target} down",
    )


def _live_matrix_evidence_errors(
    environments: dict[str, Any],
    *,
    baseline_id: str,
) -> list[str]:
    errors: list[str] = []
    required_steps = (
        "package",
        "up",
        "health",
        "candidateVerify",
        "verify",
        "replayVerify",
        "homepageReleaseEvidence",
        "lifecycleExit",
        "replayReferenceVerify",
        "down",
    )
    for target in CANONICAL_TARGETS:
        block = environments.get(target)
        if not isinstance(block, dict):
            errors.append(f"{target}: environment evidence block is missing")
            continue
        if block.get("target") != target or block.get("environment") != TARGET_ENVIRONMENTS[target]:
            errors.append(f"{target}: environment evidence identity drifted")
        package = block.get("package")
        if not isinstance(package, dict) or package.get("baselineId") != baseline_id:
            errors.append(f"{target}: package baselineId is missing or drifted")
        for step in required_steps:
            evidence = block.get(step)
            if (
                not isinstance(evidence, dict)
                or evidence.get("exitCode") != 0
                or not str(evidence.get("reportDir") or "").strip()
            ):
                errors.append(f"{target}: {step} has no successful report-bound evidence")
        attempt = block.get("startupAttempt")
        if (
            not isinstance(attempt, dict)
            or attempt.get("status") != "running"
            or attempt.get("target") != target
            or attempt.get("env") != TARGET_ENVIRONMENTS[target]
        ):
            errors.append(f"{target}: running startup attempt evidence is missing")
        homepage = block.get("homepageReleaseEvidence")
        if (
            not isinstance(homepage, dict)
            or homepage.get("outcome") != "content"
            or homepage.get("emptyReason") is not None
            or int(homepage.get("itemCount") or 0) <= 0
        ):
            errors.append(f"{target}: homepage content outcome is not canonical")
    return errors


def _write_matrix_result(
    *,
    matrix_dir: Path,
    phases: list[dict[str, Any]],
    environments: dict[str, Any],
    budgets: dict[str, Any],
    wall_seconds: float,
    exit_code: int,
    failure_category: str,
    baseline_id: str,
    release: dict[str, str],
    matrix_run_id: str,
    execution_class: str,
) -> dict[str, Any]:
    passed = exit_code == 0 and tuple(environments) == CANONICAL_TARGETS
    live_evidence = execution_class == "live"
    claim = (
        "ALPHA_BETA_GAMMA_LOCAL_GREEN"
        if passed and live_evidence
        else "CONTRACT_SIMULATION_PASSED"
        if passed
        else "GATE_BLOCK"
    )
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
            "matrixRunId": matrix_run_id,
            "executionClass": execution_class,
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
        "matrixRunId": matrix_run_id,
        "executionClass": execution_class,
        "baselineId": baseline_id,
        "releaseId": release.get("releaseId", ""),
        "releaseDigest": release.get("releaseDigest", ""),
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


def _run_local_env_gate_matrix(
    *,
    package_fn: EnvRunner,
    up_fn: EnvRunner,
    health_fn: EnvRunner,
    verify_fn: EnvRunner,
    down_fn: EnvRunner,
    filter_catalog_fn: EnvRunner | None = None,
    targets: tuple[str, ...] = CANONICAL_TARGETS,
    include_l0: bool = True,
    release_attestation: str = "",
    rollback_release_attestation: str = "",
    nonprod_data_evidence: dict[str, str] | None = None,
    data_fn: DataRunner = _data_cli_runner,
    execution_class: str = "live",
    matrix_run_id: str,
) -> dict[str, Any]:
    """Run one package-bound content-consumer state machine per local environment."""
    if execution_class not in {"live", "contract-simulation"}:
        raise ValueError("execution_class must be live or contract-simulation")
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
    try:
        candidate_release = _release_binding(release_attestation, label="candidate")
        rollback_release = _release_binding(
            rollback_release_attestation,
            label="rollback",
        )
        if candidate_release["releaseId"] == rollback_release["releaseId"]:
            raise ValueError("candidate and rollback release must be different")
        # The local matrix proves the content consumer slice. Provider/share/
        # reliability evidence belongs to the full commercial integration gate,
        # whose services and protected material are intentionally absent here.
        _ = nonprod_data_evidence
    except ValueError as exc:
        return {
            "exitCode": 2,
            "summary": "stackctl matrix release/data inputs are GATE_BLOCK",
            "details": [str(exc)],
            "claim": "GATE_BLOCK",
            "status": "gate_block",
            "executed": 0,
            "skipped": 0,
        }

    budgets = load_local_env_matrix_budgets()
    matrix_dir = _repo_matrix_dir(matrix_run_id)
    wall_started = time.monotonic()
    phases: list[dict[str, Any]] = []
    environments: dict[str, Any] = {}
    overall_exit = 0
    failure_category = ""
    matrix_baseline_id = ""

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
            "workload": "content-release",
            "profile": "content-consumer",
            "matrixRunId": matrix_run_id,
            "release": candidate_release,
            "rollbackRelease": rollback_release,
        }
        data_ids = _data_run_ids(matrix_run_id, env_name)
        block["dataRunIds"] = data_ids

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

        package_payload = _invoke_env(
            package_fn,
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
            ),
            action=f"{target} package",
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
        package_baseline = str(package_payload.get("baselineId") or "").strip()
        if _SHA256.fullmatch(package_baseline) is None:
            overall_exit = 2
            failure_category = "package_identity"
            phases.append(
                PhaseTimer(f"{target}_package_identity").finish(
                    status="gate_block",
                    details=["package result is missing canonical baselineId"],
                )
            )
            environments[target] = block
            break
        if matrix_baseline_id and package_baseline != matrix_baseline_id:
            overall_exit = 2
            failure_category = "workspace_drift"
            phases.append(
                PhaseTimer(f"{target}_package_identity").finish(
                    status="gate_block",
                    details=[
                        "Alpha/Beta/Gamma package baselineId drifted during the serial matrix",
                        f"expected={matrix_baseline_id}",
                        f"actual={package_baseline}",
                    ],
                )
            )
            environments[target] = block
            break
        matrix_baseline_id = package_baseline

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

        up_payload = _invoke_env(
            up_fn,
            _namespace(
                command="up",
                env=env_name,
                target="",
                workload="content-release",
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
            ),
            action=f"{target} up",
        )
        block["up"] = up_payload
        up_exit = _record_phase(phases, name=f"{target}_up", payload=up_payload)
        if up_exit != 0:
            overall_exit = up_exit
            failure_category = "up"
            cleanup_payload = _down_target(target, down_fn=down_fn)
            block["failedUpCleanup"] = cleanup_payload
            cleanup_exit = _record_phase(
                phases,
                name=f"{target}_failed_up_cleanup",
                payload=cleanup_payload,
            )
            if cleanup_exit != 0:
                overall_exit = cleanup_exit
                failure_category = "down"
            environments[target] = block
            break

        if execution_class == "live":
            try:
                startup_attempt = load_startup_attempt(target)
            except ValueError as exc:
                startup_attempt = None
                startup_detail = str(exc)
            else:
                startup_detail = ""
            block["startupAttempt"] = startup_attempt
            startup_identity_ok = (
                isinstance(startup_attempt, dict)
                and startup_attempt.get("status") == "running"
                and startup_attempt.get("target") == target
                and startup_attempt.get("env") == env_name
                and startup_attempt.get("workload") == "content-release"
                and str(startup_attempt.get("composeProject") or "").strip()
                and _SHA256.fullmatch(
                    str(startup_attempt.get("configurationDigest") or "")
                )
                is not None
                and _SHA256.fullmatch(
                    str(startup_attempt.get("imageTransportTag") or "")
                )
                is not None
            )
            phases.append(
                PhaseTimer(f"{target}_startup_attempt_identity").finish(
                    status="passed" if startup_identity_ok else "gate_block",
                    details=[
                        "running startup attempt identity verified"
                        if startup_identity_ok
                        else startup_detail
                        or "running startup attempt identity is missing or drifted"
                    ],
                )
            )
            if not startup_identity_ok:
                overall_exit = 2
                failure_category = "startup_identity"

        if overall_exit != 0:
            cleanup_payload = _down_target(target, down_fn=down_fn)
            block["startupIdentityCleanup"] = cleanup_payload
            cleanup_exit = _record_phase(
                phases,
                name=f"{target}_startup_identity_cleanup",
                payload=cleanup_payload,
            )
            if cleanup_exit != 0:
                overall_exit = cleanup_exit
                failure_category = "down"
            environments[target] = block
            break

        health_payload = _invoke_env(
            health_fn,
            _namespace(
                command="health",
                target=target,
                scope="content-import",
                output_format="json",
                report_dir="",
                request_timeout_seconds=0,
                retry_attempts=0,
                retry_sleep_seconds=-1.0,
            ),
            action=f"{target} health",
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
            data_root = ["python3", "quwoquan_data/scripts/cli.py"]
            original_readiness = _data_readiness_path(
                env_name,
                candidate_release["releaseId"],
                data_ids["originalVerify"],
            )
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_candidate_apply",
                environment=env_name,
                action="candidate-apply",
                argv=[
                    *data_root,
                    "ship",
                    "apply",
                    "--release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--run-id",
                    data_ids["originalImport"],
                    "--import",
                    "--full-sync",
                ],
                report_path=(original_readiness.parent.parent / data_ids["originalImport"] / "result.json"),
                data_fn=data_fn,
            )
            block["candidateApply"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_candidate_apply"

        if overall_exit == 0:
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_candidate_verify",
                environment=env_name,
                action="candidate-verify",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "verify",
                    "--release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--import-run-id",
                    data_ids["originalImport"],
                    "--run-id",
                    data_ids["originalVerify"],
                    "--readiness-phase",
                    "consumer",
                ],
                report_path=original_readiness,
                data_fn=data_fn,
            )
            block["candidateVerify"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_candidate_verify"

        if overall_exit == 0:
            verify_payload = _invoke_env(
                verify_fn,
                _namespace(
                    command="verify",
                    kind="all",
                    env=env_name,
                    target=target,
                    profile="smoke",
                    service="",
                    output_format="json",
                    report_dir="",
                    backup_recovery_receipt="",
                    data_release_id=candidate_release["releaseId"],
                    data_verify_run_id=data_ids["originalVerify"],
                    data_manifest_digest=candidate_release["releaseDigest"],
                    nonprod_data_evidence="",
                    data_lifecycle_exit_ref="",
                    distribution_root="",
                    verify_hosted=False,
                ),
                action=f"{target} content consumer smoke verify",
            )
            block["verify"] = verify_payload
            verify_exit = _record_phase(
                phases,
                name=f"{target}_verify_consumer_smoke",
                payload=verify_payload,
            )
            if verify_exit != 0:
                overall_exit = verify_exit
                failure_category = "verify"

        if overall_exit == 0:
            rollback_readiness = _data_readiness_path(
                env_name,
                rollback_release["releaseId"],
                data_ids["rollbackVerify"],
            )
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_rollback_apply",
                environment=env_name,
                action="rollback-apply",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "rollback",
                    "--to-release",
                    rollback_release["releaseId"],
                    "--from-release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--run-id",
                    data_ids["rollbackImport"],
                    "--import",
                ],
                report_path=(rollback_readiness.parent.parent / data_ids["rollbackImport"] / "result.json"),
                data_fn=data_fn,
            )
            block["rollbackApply"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_rollback"

        if overall_exit == 0:
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_rollback_verify",
                environment=env_name,
                action="rollback-verify",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "verify",
                    "--release-id",
                    rollback_release["releaseId"],
                    "--env",
                    env_name,
                    "--import-run-id",
                    data_ids["rollbackImport"],
                    "--run-id",
                    data_ids["rollbackVerify"],
                    "--readiness-phase",
                    "consumer",
                ],
                report_path=rollback_readiness,
                data_fn=data_fn,
            )
            block["rollbackVerify"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_rollback_verify"

        if overall_exit == 0:
            replay_readiness = _data_readiness_path(
                env_name,
                candidate_release["releaseId"],
                data_ids["replayVerify"],
            )
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_replay_apply",
                environment=env_name,
                action="replay-apply",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "apply",
                    "--release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--run-id",
                    data_ids["replayImport"],
                    "--import",
                    "--full-sync",
                ],
                report_path=(replay_readiness.parent.parent / data_ids["replayImport"] / "result.json"),
                data_fn=data_fn,
            )
            block["replayApply"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_replay"

        if overall_exit == 0:
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_replay_verify",
                environment=env_name,
                action="replay-verify",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "verify",
                    "--release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--import-run-id",
                    data_ids["replayImport"],
                    "--run-id",
                    data_ids["replayVerify"],
                    "--readiness-phase",
                    "consumer",
                ],
                report_path=replay_readiness,
                data_fn=data_fn,
            )
            block["replayVerify"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_replay_verify"

        if overall_exit == 0 and execution_class == "live":
            homepage_payload = _homepage_release_evidence(
                readiness_path=replay_readiness,
                environment=env_name,
                release_id=candidate_release["releaseId"],
            )
            block["homepageReleaseEvidence"] = homepage_payload
            homepage_exit = _record_phase(
                phases,
                name=f"{target}_homepage_release_evidence",
                payload=homepage_payload,
            )
            if homepage_exit != 0:
                overall_exit = homepage_exit
                failure_category = "homepage_release_evidence"

        if overall_exit == 0:
            lifecycle_path = _lifecycle_exit_path(
                env_name,
                candidate_release["releaseId"],
                data_ids["lifecycleExit"],
            )
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_lifecycle_exit",
                environment=env_name,
                action="lifecycle-exit",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "release",
                    "lifecycle-exit",
                    "--env",
                    env_name,
                    "--original-release-id",
                    candidate_release["releaseId"],
                    "--original-import-run-id",
                    data_ids["originalImport"],
                    "--original-verify-run-id",
                    data_ids["originalVerify"],
                    "--rollback-to-release-id",
                    rollback_release["releaseId"],
                    "--rollback-run-id",
                    data_ids["rollbackImport"],
                    "--rollback-verify-run-id",
                    data_ids["rollbackVerify"],
                    "--replay-import-run-id",
                    data_ids["replayImport"],
                    "--replay-verify-run-id",
                    data_ids["replayVerify"],
                    "--run-id",
                    data_ids["lifecycleExit"],
                ],
                report_path=lifecycle_path,
                data_fn=data_fn,
            )
            block["lifecycleExit"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_lifecycle_exit"

        if overall_exit == 0:
            replay_reference_payload = _invoke_env(
                verify_fn,
                _namespace(
                    command="verify",
                    kind="all",
                    env=env_name,
                    target=target,
                    profile="smoke",
                    service="",
                    output_format="json",
                    report_dir="",
                    backup_recovery_receipt="",
                    data_release_id=candidate_release["releaseId"],
                    data_verify_run_id=data_ids["originalVerify"],
                    data_manifest_digest=candidate_release["releaseDigest"],
                    nonprod_data_evidence="",
                    data_lifecycle_exit_ref="",
                    distribution_root="",
                    verify_hosted=False,
                ),
                action=f"{target} replay runtime smoke verify",
            )
            block["replayReferenceVerify"] = replay_reference_payload
            replay_reference_exit = _record_phase(
                phases,
                name=f"{target}_runtime_smoke_revalidate",
                payload=replay_reference_payload,
            )
            if replay_reference_exit != 0:
                overall_exit = replay_reference_exit
                failure_category = "runtime_smoke_revalidate"

        lease_id = f"{matrix_run_id}-{env_name}-device-uat"
        lease_acquire_event: dict[str, Any] | None = None
        if overall_exit == 0:
            lease_exit, lease_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_acceptance_lease_acquire",
                environment=env_name,
                action="acceptance-lease-acquire",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "release",
                    "acceptance-lease",
                    "acquire",
                    "--env",
                    env_name,
                    "--release-id",
                    candidate_release["releaseId"],
                    "--lease-id",
                    lease_id,
                    "--import-run-id",
                    data_ids["replayImport"],
                    "--verify-run-id",
                    data_ids["replayVerify"],
                ],
                report_path=lifecycle_path.parent / "acceptance-lease-acquire.json",
                data_fn=data_fn,
            )
            block["acceptanceLeaseAcquire"] = lease_payload
            if lease_exit != 0:
                overall_exit = lease_exit
                failure_category = "acceptance_lease_acquire"
            else:
                try:
                    lease_acquire_event = _acceptance_lease_event(
                        lease_payload,
                        action="acquire",
                        environment=env_name,
                        release_id=candidate_release["releaseId"],
                        lease_id=lease_id,
                    )
                except ValueError as exc:
                    overall_exit = 2
                    failure_category = "acceptance_lease_acquire"
                    phases.append(
                        PhaseTimer(f"{target}_acceptance_lease_identity").finish(
                            status="gate_block",
                            details=[str(exc)],
                        )
                    )

        if lease_acquire_event is not None:
            revoke_exit, revoke_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_acceptance_lease_revoke",
                environment=env_name,
                action="acceptance-lease-revoke",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "release",
                    "acceptance-lease",
                    "revoke",
                    "--env",
                    env_name,
                    "--release-id",
                    candidate_release["releaseId"],
                    "--lease-id",
                    lease_id,
                    "--acquire-event-ref",
                    str(lease_acquire_event["eventRef"]),
                ],
                report_path=lifecycle_path.parent / "acceptance-lease-revoke.json",
                data_fn=data_fn,
            )
            block["acceptanceLeaseRevoke"] = revoke_payload
            if revoke_exit == 0:
                try:
                    _acceptance_lease_event(
                        revoke_payload,
                        action="revoke",
                        environment=env_name,
                        release_id=candidate_release["releaseId"],
                        lease_id=lease_id,
                    )
                except ValueError as exc:
                    revoke_exit = 2
                    phases.append(
                        PhaseTimer(f"{target}_acceptance_lease_revoke_identity").finish(
                            status="gate_block",
                            details=[str(exc)],
                        )
                    )
            if revoke_exit != 0:
                overall_exit = revoke_exit
                failure_category = "acceptance_lease_revoke"

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

    if overall_exit == 0 and execution_class == "live":
        evidence_errors = _live_matrix_evidence_errors(
            environments,
            baseline_id=matrix_baseline_id,
        )
        phases.append(
            PhaseTimer("live_matrix_evidence_identity").finish(
                status="gate_block" if evidence_errors else "passed",
                details=evidence_errors or ["all live evidence identities are report-bound"],
            )
        )
        if evidence_errors:
            overall_exit = 2
            failure_category = "evidence_identity"

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
        baseline_id=matrix_baseline_id,
        release=candidate_release,
        matrix_run_id=matrix_run_id,
        execution_class=execution_class,
    )


def run_local_env_gate_matrix(
    *,
    package_fn: EnvRunner,
    up_fn: EnvRunner,
    health_fn: EnvRunner,
    verify_fn: EnvRunner,
    down_fn: EnvRunner,
    filter_catalog_fn: EnvRunner | None = None,
    targets: tuple[str, ...] = CANONICAL_TARGETS,
    include_l0: bool = True,
    release_attestation: str = "",
    rollback_release_attestation: str = "",
    nonprod_data_evidence: dict[str, str] | None = None,
    data_fn: DataRunner = _data_cli_runner,
    execution_class: str = "live",
) -> dict[str, Any]:
    """Run the matrix under a process-bound lease for live execution only."""
    if execution_class not in {"live", "contract-simulation"}:
        raise ValueError("execution_class must be live or contract-simulation")
    matrix_run_id = _new_matrix_run_id()
    kwargs = {
        "package_fn": package_fn,
        "up_fn": up_fn,
        "health_fn": health_fn,
        "verify_fn": verify_fn,
        "down_fn": down_fn,
        "filter_catalog_fn": filter_catalog_fn,
        "targets": targets,
        "include_l0": include_l0,
        "release_attestation": release_attestation,
        "rollback_release_attestation": rollback_release_attestation,
        "nonprod_data_evidence": nonprod_data_evidence,
        "data_fn": data_fn,
        "execution_class": execution_class,
        "matrix_run_id": matrix_run_id,
    }
    if execution_class == "contract-simulation":
        return _run_local_env_gate_matrix(**kwargs)
    try:
        with _matrix_execution_lease(matrix_run_id):
            return _run_local_env_gate_matrix(**kwargs)
    except MatrixExecutionLeaseBusy as exc:
        return {
            "exitCode": 2,
            "summary": "stackctl live matrix execution lease is GATE_BLOCK",
            "details": [str(exc)],
            "claim": "GATE_BLOCK",
            "status": "gate_block",
            "executed": 0,
            "skipped": 0,
            "matrixRunId": matrix_run_id,
            "executionClass": execution_class,
        }

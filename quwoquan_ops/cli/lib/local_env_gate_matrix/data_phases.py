"""Data CLI 阶段执行、阶段记录与 runner 调用封装（自原单文件逐字搬移）。"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.local_env_gate_timing import PhaseTimer

# 测试通过 mock.patch.object(matrix_mod, "output_root") 重定向输出根；保持包属性延迟访问。
import quwoquan_ops.cli.lib.local_env_gate_matrix as _matrix_pkg
from quwoquan_ops.cli.lib.local_env_gate_matrix.identity import (
    DataRunner,
    EnvRunner,
    ROOT,
    _evidence_path,
)


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
        _matrix_pkg.output_root()
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
        _matrix_pkg.output_root()
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
        and payload.get("readinessPhase") in {"consumer", "commercial"}
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

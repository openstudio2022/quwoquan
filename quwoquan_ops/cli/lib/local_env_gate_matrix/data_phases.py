"""Data CLI 阶段执行、阶段记录与 runner 调用封装（自原单文件逐字搬移）。"""
from __future__ import annotations

import argparse
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


def _parse_data_args(argv: list[str]) -> argparse.Namespace:
    """复用 Data 门面及现役 parser，只解析而不调用 handler。"""
    from quwoquan_data.scripts import cli

    parser = argparse.ArgumentParser(prog="qwq-data")
    subparsers = parser.add_subparsers(dest="command", required=True)
    cli._register_selected_command(subparsers, argv[0])
    return parser.parse_args(argv)


def _query_active_release(*, environment: str, report_path: Path) -> dict[str, Any]:
    """复用 Data 的 Content query adapter，不另起 runner 或推算 revision。"""
    from quwoquan_data.scripts import cli  # noqa: F401：建立 Data canonical import 根
    from content.release.environment.importers import query_content_active_release
    from content.release.environment.topology import resolve_environment_release_target

    target = resolve_environment_release_target(environment)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    evidence = query_content_active_release(
        env=environment, mongo_uri=target.mongo_uri, report_path=report_path,
        output_root=_matrix_pkg.output_root(),
    )
    return {"exitCode": 0, "summary": "Content active pointer queried",
            "payload": dict(evidence.document), "reportPath": str(evidence.path),
            "reportDir": _evidence_path(evidence.path.parent),
            "receiptRef": evidence.ref, "receiptDigest": evidence.digest}


def _data_cli_runner(
    *, argv: list[str], report_path: Path, action: str = "", environment: str = "", **_: Any,
) -> dict[str, Any]:
    if action == "rollback-active-query":
        return _query_active_release(environment=environment, report_path=report_path)
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
        "originalApply": f"{prefix}-original-apply",
        "originalActivate": f"{prefix}-original-activate",
        "originalVerify": f"{prefix}-original-verify",
        "rollbackApply": f"{prefix}-rollback-apply",
        "rollbackRun": f"{prefix}-rollback",
        "rollbackVerify": f"{prefix}-rollback-verify",
        "replayApply": f"{prefix}-replay-apply",
        "replayActivate": f"{prefix}-replay-activate",
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
        isinstance(payload, dict)
        and payload.get("schema") == "quwoquan_data.environment_release_readiness"
        and payload.get("passed") is True
        and payload.get("environment") == environment
        and payload.get("releaseId") == release_id
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
    import_run_id: str = "",
    verify_run_id: str = "",
) -> dict[str, Any]:
    event = payload.get("payload")
    if (
        not isinstance(event, dict)
        or event.get("schema") != "quwoquan_data.release_acceptance_lease_event"
        or event.get("action") != action
        or event.get("environment") != environment
        or event.get("releaseId") != release_id
        or event.get("leaseId") != lease_id
        or (import_run_id and event.get("importRunId") != import_run_id)
        or (verify_run_id and event.get("verifyRunId") != verify_run_id)
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
    expected_result: dict[str, Any] | None = None,
    expected_kind: str = "",
    required_status: str = "completed",
) -> tuple[int, dict[str, Any]]:
    started = time.monotonic()
    payload: dict[str, Any] = {}
    try:
        if argv:
            _parse_data_args(argv[2:])
        payload = data_fn(
            environment=environment,
            action=action,
            argv=argv,
            report_path=report_path,
        )
        if payload.get("exitCode") == 0 and expected_result is not None:
            from content.release.environment.run_evidence import read_environment_result

            result = read_environment_result(
                report_path.parent / "result.json", expected=expected_result,
                required_status=required_status,
            )
            run = json.loads((report_path.parent / "run.json").read_text(encoding="utf-8"))
            if (run.get("kind") != expected_kind
                    or any(run.get(key) != expected_result[key]
                           for key in ("environment", "releaseId", "runId"))):
                raise ValueError("Data run kind or exact identity drifted")
            payload = {**payload, "result": result}
    except (Exception, SystemExit) as exc:
        payload = {
            **payload,
            "exitCode": 2,
            "summary": f"{action} is GATE_BLOCK",
            "details": [f"{type(exc).__name__}: {exc}"],
            "reportDir": _evidence_path(report_path.parent),
            "durationMs": int((time.monotonic() - started) * 1000),
        }
    return (
        _record_phase(phases, name=phase_name, payload=payload),
        payload,
    )


def _rollback_source(
    payload: dict[str, Any], *, environment: str, candidate: dict[str, Any],
    activated_result: dict[str, Any],
) -> dict[str, Any]:
    """新鲜 query 必须仍等于本轮 activation 的实际 post-CAS 身份。"""
    import hashlib

    ref = activated_result["contentPostActiveReceiptRef"]
    path = _matrix_pkg.output_root() / ref
    if not path.resolve().is_relative_to(_matrix_pkg.output_root().resolve()):
        raise ValueError("Content activation receipt escapes output root")
    raw = path.read_bytes()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != activated_result["contentPostActiveReceiptDigest"]:
        raise ValueError("Content activation post receipt digest drifted")
    post = json.loads(raw)
    active = payload.get("payload")
    expected = {"schema": "quwoquan.content_release_active_receipt", "status": "found",
                "environment": environment, "sourceOwner": "qwq_data",
                "releaseId": candidate["releaseId"], "manifestDigest": candidate["releaseDigest"]}
    if (not isinstance(active, dict) or not isinstance(post, dict)
            or any(active.get(key) != value or post.get(key) != value for key, value in expected.items())
            or type(active.get("revision")) is not int or active["revision"] <= 0
            or active["revision"] != post.get("revision")):
        raise ValueError("CONTENT.RELEASE.ACTIVE_CAS_CONFLICT: queried release/digest/revision drifted")
    return active


def _run_data_lifecycle(
    *, phases: list[dict[str, Any]], block: dict[str, Any], target: str,
    environment: str, candidate: dict[str, Any], rollback: dict[str, Any],
    data_ids: dict[str, str], data_fn: DataRunner,
    previous_readiness: dict[str, str] | None = None,
) -> tuple[int, str]:
    """只编排 Data 单轨；每步校验 raw result 后再推进，首错即停。"""
    steps = (
        ("candidateApply", "candidate-apply", "apply", candidate, "originalApply", ""),
        ("candidateActivate", "candidate-activate", "activate", candidate, "originalActivate", "originalApply"),
        ("candidateVerify", "candidate-verify", "verify", candidate, "originalVerify", "originalActivate"),
        ("rollbackPrepare", "rollback-prepare", "apply", rollback, "rollbackApply", ""),
        ("rollbackApply", "rollback-apply", "rollback", rollback, "rollbackRun", "rollbackApply"),
        ("rollbackVerify", "rollback-verify", "verify", rollback, "rollbackVerify", "rollbackRun"),
        ("replayApply", "replay-apply", "apply", candidate, "replayApply", ""),
        ("replayActivate", "replay-activate", "activate", candidate, "replayActivate", "replayApply"),
        ("replayVerify", "replay-verify", "verify", candidate, "replayVerify", "replayActivate"),
    )
    for key, action, kind, release, run_key, predecessor in steps:
        readiness = _data_readiness_path(environment, release["releaseId"], data_ids[run_key])
        argv = ["python3", "quwoquan_data/scripts/cli.py", "ship", kind,
                *release["admissionArgv"], "--env", environment, "--run-id", data_ids[run_key]]
        expected = {"environment": environment, "releaseId": release["releaseId"],
                    "manifestDigest": release["releaseDigest"], "runId": data_ids[run_key],
                    "containsUnverifiedAssets": release["containsUnverifiedAssets"],
                    **release["admissionEnvelope"]}
        if predecessor:
            argv.extend(("--import-run-id", data_ids[predecessor]))
            expected["importRunId"] = data_ids[predecessor]
        if kind == "apply":
            argv.extend(("--import", "--full-sync"))
        if kind == "verify" and release.get("milestone") is not None and previous_readiness:
            argv.extend(("--previous-environment-readiness", previous_readiness.get(key, "")))
        if kind == "rollback":
            query_exit, query = _run_data_phase(
                phases, phase_name=f"{target}_data_rollback_active_query",
                environment=environment, action="rollback-active-query", argv=[],
                report_path=readiness.parent.parent / f"{data_ids[run_key]}-preflight" / "content-active.json",
                data_fn=data_fn,
            )
            block["rollbackActiveQuery"] = query
            if query_exit:
                return query_exit, "data_rollback_active_query"
            try:
                active = _rollback_source(
                    query, environment=environment, candidate=candidate,
                    activated_result=block["candidateActivate"]["result"],
                )
            except (KeyError, OSError, TypeError, ValueError) as exc:
                query = {**query, "exitCode": 2, "summary": str(exc)}
                block["rollbackActiveQuery"] = query
                _record_phase(phases, name=f"{target}_data_rollback_active_identity", payload=query)
                return 2, "data_rollback_active_identity"
            argv.extend(("--import", "--from-release-id", active["releaseId"],
                         "--from-manifest-digest", active["manifestDigest"],
                         "--from-revision", str(active["revision"])))
        exit_code, payload = _run_data_phase(
            phases, phase_name=f"{target}_data_{action.replace('-', '_')}",
            environment=environment, action=action, argv=argv,
            report_path=readiness if kind == "verify" else readiness.parent / "result.json",
            data_fn=data_fn, expected_result=expected, expected_kind=kind,
            required_status="prepared" if kind == "apply" else "completed",
        )
        block[key] = payload
        if exit_code:
            return exit_code, f"data_{action.replace('-', '_')}"
    return 0, ""


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

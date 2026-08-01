"""Run and classify real Cursor SDK startup probes for data execution admission."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from core.cursor_model import CursorModelSelection
from core.runtime_policy import active_runtime_policy
from core.python_environment import (
    DEFAULT_CURSOR_STARTUP_MODEL,
    DEFAULT_CURSOR_STARTUP_RUNTIME,
    REPO_ROOT,
    _redact_secret_text,
    _redact_secret_value,
    resolve_data_agent_python,
)

def cursor_startup_probe(
    *,
    model: str | CursorModelSelection = DEFAULT_CURSOR_STARTUP_MODEL,
    runtime: str = DEFAULT_CURSOR_STARTUP_RUNTIME,
    timeout_seconds: float | None = None,
    cwd: Path | None = None,
) -> dict:
    """Run a minimal real Cursor SDK Agent.prompt startup probe.

    Import/network/key checks are necessary but not sufficient: a batch can
    still fail at the bridge/account/startup boundary.  The probe runs in a
    short subprocess so a stuck SDK call cannot wedge the parent readiness gate.
    """

    selection = CursorModelSelection.from_value(model)
    try:
        from core.cursor_credentials import resolve_cursor_api_key
    except Exception:  # noqa: BLE001
        from cursor_credentials import resolve_cursor_api_key  # type: ignore
    # Pass the key only through stdin to this short-lived probe. Its environment
    # and argv remain credential-free, including for any bridge it spawns.
    key = resolve_cursor_api_key()
    if not key:
        return {
            "checked": False,
            "ready": False,
            "started": False,
            "runtime": runtime,
            "model": selection.model_id,
            "modelParameters": selection.parameters_document(),
            "issues": ["credential_not_ready"],
        }
    runtime_policy = active_runtime_policy()
    effective_timeout_seconds = float(
        timeout_seconds
        if timeout_seconds is not None
        else runtime_policy.startup_timeout_seconds
    )
    probe_cwd = str((cwd or REPO_ROOT).resolve())
    probe_python = resolve_data_agent_python(include_current=True) or Path(sys.executable)
    code = r'''
import json
import os
import sys

token_patch_warning = None
try:
    from cursor_sdk import Agent, AgentOptions, CloudAgentOptions, LocalAgentOptions, Client
    from cursor_sdk.types import ModelSelection
    try:
        from cursor_sdk.errors import CursorAgentError
    except Exception:
        from cursor_sdk import CursorAgentError
    try:
        import cursor_sdk._tool_callback as tool_callback
        _original_new_auth_token = getattr(tool_callback, "_new_auth_token", None)
        if callable(_original_new_auth_token) and not getattr(_original_new_auth_token, "_qwq_safe_token_factory", False):
            def _new_auth_token_without_leading_dash():
                token = str(_original_new_auth_token() or "")
                if token.startswith("-"):
                    return "qwq_" + token.lstrip("-")
                return token
            setattr(_new_auth_token_without_leading_dash, "_qwq_safe_token_factory", True)
            setattr(tool_callback, "_new_auth_token", _new_auth_token_without_leading_dash)
    except Exception as exc:
        token_patch_warning = type(exc).__name__
except Exception as exc:
    print(json.dumps({"ready": False, "started": False, "error": f"cursor_sdk unavailable: {exc}"}, ensure_ascii=False))
    raise SystemExit(0)

api_key = sys.stdin.readline().strip()
model = ModelSelection.from_json(json.loads(sys.argv[1]))
runtime = sys.argv[2]
cwd = sys.argv[3]
bridge_timeout = int(sys.argv[4])
try:
    with Client.launch_bridge(
        workspace=cwd,
        timeout=bridge_timeout,
        local=LocalAgentOptions(cwd=cwd, setting_sources=[]),
        allow_api_key_env_fallback=False,
    ) as client:
        bridge = getattr(client, "_owned_bridge", None)
        endpoint = getattr(bridge, "endpoint", None)
        if runtime == "cloud":
            opts = AgentOptions(api_key=api_key, model=model, cloud=CloudAgentOptions(repos=[]))
        else:
            opts = AgentOptions(
                api_key=api_key,
                model=model,
                local=LocalAgentOptions(cwd=cwd, setting_sources=[]),
            )
        agent = Agent.create(opts, client=client)
        terminal_status_message = ""
        try:
            run = agent.send(
                "quwoquan_data env startup probe. Do not edit files. Reply with the single word READY."
            )
            for event in run.events():
                message = getattr(event, "sdk_message", None)
                if (
                    getattr(message, "type", "") == "status"
                    and str(getattr(message, "status", "")).casefold() == "error"
                ):
                    terminal_status_message = str(
                        getattr(message, "message", "") or ""
                    ).strip()
            result = run.wait()
        finally:
            agent.close()
    status = getattr(result, "status", "")
    print(json.dumps({
        "ready": status == "finished",
        "started": True,
        "probeType": "agent_prompt_smoke",
        "status": status,
        "errorClass": "AgentStatusError" if status != "finished" else None,
        "error": terminal_status_message if status != "finished" else None,
        "errorCode": "provider_rejected" if terminal_status_message else None,
        "retryable": False,
        "agentId": getattr(result, "agent_id", None),
        "runId": getattr(result, "id", None),
        "bridgePid": getattr(endpoint, "pid", None),
        "bridgeVersion": getattr(endpoint, "server_version", ""),
        "tokenPatchWarning": token_patch_warning,
    }, ensure_ascii=False))
except CursorAgentError as exc:
    print(json.dumps({
        "ready": False,
        "started": False,
        "probeType": "agent_prompt_smoke",
        "status": "error",
        "errorClass": type(exc).__name__,
        "error": getattr(exc, "message", str(exc)),
        "retryable": bool(getattr(exc, "is_retryable", False)),
        "errorCode": getattr(exc, "code", None),
        "httpStatus": getattr(exc, "status", None),
        "protoErrorCode": getattr(exc, "proto_error_code", None),
        "requestId": getattr(exc, "request_id", None),
        "details": getattr(exc, "details", None),
        "headers": dict(getattr(exc, "headers", {}) or {}),
        "retryAfter": getattr(exc, "retry_after", None),
    }, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({
        "ready": False,
        "started": False,
        "probeType": "agent_prompt_smoke",
        "status": "error",
        "errorClass": type(exc).__name__,
        "error": str(exc),
    }, ensure_ascii=False))
'''
    deadline = time.monotonic() + max(1, effective_timeout_seconds)
    attempts: list[dict] = []
    payload: dict = {"ready": False, "started": False, "error": "cursor startup probe not run"}
    returncode = 0
    for attempt in range(1, runtime_policy.preflight_startup_attempts + 1):
        attempt_started_at = datetime.now(timezone.utc).isoformat()
        remaining = max(1, int(deadline - time.monotonic()))
        try:
            proc = subprocess.run(
                [
                    str(probe_python),
                    "-c",
                    code,
                    json.dumps(selection.to_sdk_document(), ensure_ascii=True, sort_keys=True),
                    str(runtime),
                    probe_cwd,
                    str(runtime_policy.cursor_bridge_handshake_timeout_seconds),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=remaining,
                env={
                    name: value
                    for name, value in os.environ.items()
                    if name != "CURSOR_API_KEY"
                },
                input=f"{key}\n",
                cwd=probe_cwd,
            )
        except subprocess.TimeoutExpired:
            attempts.append(
                {
                    "attempt": attempt,
                    "startedAt": attempt_started_at,
                    "ready": False,
                    "status": "timeout",
                    "errorClass": "TimeoutExpired",
                    "error": f"cursor startup probe timed out after {int(effective_timeout_seconds)}s",
                    "httpStatus": None,
                    "errorCode": "timeout",
                    "requestId": None,
                    "retryable": True,
                    "retryAfter": None,
                    "agentId": None,
                    "runId": None,
                }
            )
            return {
                "checked": True,
                "ready": False,
                "started": False,
                "runtime": runtime,
                "model": selection.model_id,
                "modelParameters": selection.parameters_document(),
                "probePython": str(probe_python),
                "status": "timeout",
                "retryable": True,
                "probeType": "agent_prompt_smoke",
                "errorClass": "TimeoutExpired",
                "errorCode": "timeout",
                "httpStatus": None,
                "protoErrorCode": None,
                "requestId": None,
                "details": [],
                "headers": {},
                "retryAfter": None,
                "attemptCount": attempt,
                "attempts": attempts,
                "issues": [f"cursor startup probe timed out after {int(effective_timeout_seconds)}s"],
            }
        returncode = proc.returncode
        try:
            payload = json.loads((proc.stdout or "{}").strip() or "{}")
        except json.JSONDecodeError:
            payload = {
                "ready": False,
                "started": False,
                "status": "error",
                "error": proc.stderr.strip() or "cursor startup probe did not return JSON",
            }
        payload = payload if isinstance(payload, dict) else {"ready": False, "started": False, "error": "invalid probe payload"}
        if returncode != 0 and payload.get("ready"):
            payload["ready"] = False
            payload["error"] = f"cursor startup probe exited {returncode}"
        retryable = bool(payload.get("retryable", False))
        if not payload.get("ready") and not _cursor_probe_attempt_is_auth(payload):
            retryable = retryable or _cursor_probe_attempt_has_5xx(
                payload
            ) or _cursor_probe_attempt_is_bridge_disconnect(payload)
        payload["retryable"] = retryable
        attempts.append(
            {
                "attempt": attempt,
                    "startedAt": attempt_started_at,
                "ready": bool(payload.get("ready")),
                "status": payload.get("status"),
                "errorClass": _redact_secret_value(
                    payload.get("errorClass"),
                    secrets=(key,),
                ),
                "error": _redact_secret_value(
                    payload.get("error"),
                    secrets=(key,),
                ),
                "httpStatus": payload.get("httpStatus"),
                "errorCode": payload.get("errorCode"),
                "requestId": payload.get("requestId"),
                "retryable": bool(payload.get("retryable", False)),
                "retryAfter": _redact_secret_value(
                    payload.get("retryAfter"),
                    secrets=(key,),
                ),
                "agentId": payload.get("agentId"),
                "runId": payload.get("runId"),
            }
        )
        if payload.get("ready"):
            break
        if (
            not bool(payload.get("retryable", False))
            or attempt >= runtime_policy.preflight_startup_attempts
        ):
            break
        retry_after = payload.get("retryAfter")
        try:
            requested_delay = float(retry_after) if retry_after is not None else 0.0
        except (TypeError, ValueError):
            requested_delay = 0.0
        exponential_delay = float(
            runtime_policy.preflight_retry_delay_seconds * (2 ** (attempt - 1))
        )
        sleep_seconds = min(
            max(exponential_delay, requested_delay),
            max(0.0, deadline - time.monotonic()),
        )
        if sleep_seconds <= 0:
            break
        time.sleep(sleep_seconds)
    issues = []
    if not payload.get("ready"):
        issues.append(
            _redact_secret_text(
                str(
                    payload.get("error")
                    or payload.get("status")
                    or "cursor startup probe failed"
                ),
                secrets=(key,),
            )
        )
    return {
        "checked": True,
        "ready": bool(payload.get("ready")),
        "started": bool(payload.get("started")),
        "probeType": payload.get("probeType") or "agent_prompt_smoke",
        "runtime": runtime,
        "model": selection.model_id,
        "modelParameters": selection.parameters_document(),
        "probePython": str(probe_python),
        "status": payload.get("status"),
        "error": _redact_secret_value(payload.get("error"), secrets=(key,)),
        "errorClass": _redact_secret_value(
            payload.get("errorClass"),
            secrets=(key,),
        ),
        "retryable": bool(payload.get("retryable", False)),
        "errorCode": payload.get("errorCode"),
        "httpStatus": payload.get("httpStatus"),
        "protoErrorCode": payload.get("protoErrorCode"),
        "requestId": payload.get("requestId"),
        "details": _redact_secret_value(
            payload.get("details") or [],
            secrets=(key,),
        ),
        "headers": _redact_secret_value(
            payload.get("headers") or {},
            secrets=(key,),
        ),
        "retryAfter": _redact_secret_value(
            payload.get("retryAfter"),
            secrets=(key,),
        ),
        "attemptCount": len(attempts),
        "attempts": attempts,
        "issues": issues,
    }


def _cursor_probe_attempt_has_5xx(payload: Mapping[str, object]) -> bool:
    rows = list(payload.get("attempts") or []) if isinstance(payload.get("attempts"), list) else []
    candidates: list[Mapping[str, object]] = [payload]
    candidates.extend(row for row in rows if isinstance(row, Mapping))
    for row in candidates:
        status = row.get("httpStatus")
        try:
            status_int = int(status) if status is not None else 0
        except (TypeError, ValueError):
            status_int = 0
        if 500 <= status_int < 600:
            return True
        if str(row.get("errorClass") or "") == "InternalServerError":
            return True
        if str(row.get("errorCode") or "") == "internal":
            return True
    return False


def _cursor_probe_attempt_is_auth(payload: Mapping[str, object]) -> bool:
    try:
        from core.cursor_credentials import is_cursor_auth_error
    except Exception:  # noqa: BLE001
        from cursor_credentials import is_cursor_auth_error  # type: ignore
    rows = list(payload.get("attempts") or []) if isinstance(payload.get("attempts"), list) else []
    candidates: list[Mapping[str, object]] = [payload]
    candidates.extend(row for row in rows if isinstance(row, Mapping))
    for row in candidates:
        if is_cursor_auth_error(
            str(row.get("error") or row.get("status") or ""),
            code=str(row.get("errorCode") or ""),
            status=row.get("httpStatus"),
        ):
            return True
    return False


def _cursor_probe_attempt_is_bridge_disconnect(payload: Mapping[str, object]) -> bool:
    rows = list(payload.get("attempts") or []) if isinstance(payload.get("attempts"), list) else []
    candidates: list[Mapping[str, object]] = [payload]
    candidates.extend(row for row in rows if isinstance(row, Mapping))
    markers = (
        "connection refused",
        "connecterror",
        "connection reset",
        "server disconnected",
        "remoteprotocolerror",
        "bridge request failed",
        "exited before discovery",
        "failed before discovery",
    )
    for row in candidates:
        text = f"{row.get('errorClass') or ''} {row.get('error') or ''}".casefold()
        if any(marker in text for marker in markers):
            return True
    return False


def _cursor_probe_is_startup_timeout(payload: Mapping[str, object]) -> bool:
    """探针终态是否是启动超时（subprocess.TimeoutExpired）。

    冷启动期间子尝试可能短暂遇到 5xx/InternalServerError，但若整次探针最终在
    预算内未拿到干净结论而是被超时切断，结论是 "startupTimeout"，不得据子尝试的
    冷启动 5xx 把整次记为 true5xx——那是过度归因，会把"超时/延迟"问题误报成
    "后端 5xx 不稳定"。timeout 单列，优先级高于 5xx。
    """
    if str(payload.get("status") or "") == "timeout":
        return True
    if str(payload.get("errorClass") or "") == "TimeoutExpired":
        return True
    if str(payload.get("errorCode") or "") == "timeout":
        return True
    return False


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999999) - 1))
    return round(ordered[index], 4)


def cursor_startup_probe_suite(
    *,
    model: str | CursorModelSelection = DEFAULT_CURSOR_STARTUP_MODEL,
    runtime: str = DEFAULT_CURSOR_STARTUP_RUNTIME,
    attempts: int | None = None,
    timeout_seconds: float | None = None,
    cwd: Path | None = None,
) -> dict:
    """Run repeated Cursor startup probes and classify admission blockers.

    This is the formal P0 report used before scaled authoring.  A single
    preflight can hide intermittent startup failures; the suite assigns each
    attempt exactly one *primary* class with precedence
    ``ready > auth > startupTimeout > true5xx > bridgeDisconnect > other`` so
    that a probe whose final verdict is a subprocess timeout is bucketed as
    ``startupTimeout`` and is **never** counted as ``true5xx`` (cold-start 5xx
    sub-attempts under a timeout are not a stable backend 5xx verdict).
    """
    runtime_policy = active_runtime_policy()
    selection = CursorModelSelection.from_value(model)
    total = int(
        attempts
        if attempts is not None
        else runtime_policy.startup_probe_suite_attempts
    )
    effective_timeout_seconds = float(
        timeout_seconds
        if timeout_seconds is not None
        else runtime_policy.startup_timeout_seconds
    )
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    suite_started = time.monotonic()
    rows: list[dict] = []
    latencies: list[float] = []
    success_count = 0
    auth_failures = 0
    true_5xx_count = 0
    startup_timeout_count = 0
    bridge_disconnect_count = 0
    cold_start_5xx_observed = 0
    worker_limit = min(
        total,
        runtime_policy.author_workers,
        runtime_policy.cursor_bridge_instances,
    )
    active_workers = 0
    maximum_active_workers = 0
    active_lock = threading.Lock()

    def run_probe(index: int) -> tuple[int, dict, float]:
        nonlocal active_workers, maximum_active_workers
        with active_lock:
            active_workers += 1
            maximum_active_workers = max(maximum_active_workers, active_workers)
        begin = time.monotonic()
        try:
            payload = cursor_startup_probe(
                model=selection,
                runtime=runtime,
                timeout_seconds=effective_timeout_seconds,
                cwd=cwd,
            )
        except Exception as exc:  # noqa: BLE001 - external SDK boundary
            payload = {
                "ready": False,
                "status": "error",
                "errorClass": type(exc).__name__,
                "error": _redact_secret_text(str(exc)),
            }
        finally:
            with active_lock:
                active_workers -= 1
        return index, payload, round(time.monotonic() - begin, 4)

    with ThreadPoolExecutor(max_workers=worker_limit) as executor:
        futures = [executor.submit(run_probe, index) for index in range(1, total + 1)]
        outcomes = [future.result() for future in as_completed(futures)]

    for index, payload, elapsed in outcomes:
        latencies.append(elapsed)
        ready = bool(payload.get("ready"))
        has_auth = _cursor_probe_attempt_is_auth(payload)
        is_startup_timeout = _cursor_probe_is_startup_timeout(payload)
        raw_5xx = _cursor_probe_attempt_has_5xx(payload)
        has_bridge_disconnect = _cursor_probe_attempt_is_bridge_disconnect(payload)
        # 单一 primary 归类（互斥），timeout 优先于 5xx：终态超时不计 5xx。
        if ready:
            primary = "ready"
        elif has_auth:
            primary = "auth"
        elif is_startup_timeout:
            primary = "startupTimeout"
        elif raw_5xx:
            primary = "true5xx"
        elif has_bridge_disconnect:
            primary = "bridgeDisconnect"
        else:
            primary = "other"
        if primary == "ready":
            success_count += 1
        elif primary == "auth":
            auth_failures += 1
        elif primary == "startupTimeout":
            startup_timeout_count += 1
        elif primary == "true5xx":
            true_5xx_count += 1
        elif primary == "bridgeDisconnect":
            bridge_disconnect_count += 1
        if raw_5xx:
            cold_start_5xx_observed += 1
        rows.append(
            {
                "attempt": index,
                "ready": ready,
                "latencySeconds": elapsed,
                "status": payload.get("status"),
                "errorClass": _redact_secret_value(payload.get("errorClass")),
                "errorCode": payload.get("errorCode"),
                "httpStatus": payload.get("httpStatus"),
                "primaryClass": primary,
                "authFailure": primary == "auth",
                "startupTimeout": primary == "startupTimeout",
                "true5xx": primary == "true5xx",
                "bridgeDisconnect": primary == "bridgeDisconnect",
                "coldStart5xxObserved": raw_5xx,
                "attemptCount": payload.get("attemptCount"),
            }
        )
    rows.sort(key=lambda row: int(row["attempt"]))
    elapsed_seconds = round(time.monotonic() - suite_started, 4)
    probe_jobs_per_hour = (
        round((success_count / elapsed_seconds) * 3600, 4)
        if elapsed_seconds > 0
        else 0.0
    )
    true_5xx_rate = round(true_5xx_count / total, 4)
    startup_timeout_rate = round(startup_timeout_count / total, 4)
    bridge_disconnect_rate = round(bridge_disconnect_count / total, 4)
    issues: list[str] = []
    if auth_failures:
        issues.append(f"Cursor auth failures observed: {auth_failures}/{total}")
    if true_5xx_rate >= runtime_policy.cursor_true_5xx_rate_limit:
        issues.append(
            f"Cursor true 5xx rate {true_5xx_rate:.2%} >= "
            f"{runtime_policy.cursor_true_5xx_rate_limit:.0%}"
        )
    if startup_timeout_rate >= runtime_policy.cursor_startup_timeout_rate_limit:
        issues.append(
            f"Cursor startup timeout rate {startup_timeout_rate:.2%} >= "
            f"{runtime_policy.cursor_startup_timeout_rate_limit:.0%} "
            f"(raise --startup-timeout-seconds / warm bridge reuse; not a backend 5xx)"
        )
    if success_count == 0:
        issues.append("Cursor startup probe never succeeded")
    return {
        "schema": "quwoquan_data.cursor_startup_probe_suite",
        "model": selection.model_id,
        "modelParameters": selection.parameters_document(),
        "runtime": runtime,
        "attempts": total,
        "timeoutSeconds": round(effective_timeout_seconds, 4),
        "successCount": success_count,
        "authFailures": auth_failures,
        "true5xxCount": true_5xx_count,
        "true5xxRate": true_5xx_rate,
        "startupTimeoutCount": startup_timeout_count,
        "startupTimeoutRate": startup_timeout_rate,
        "coldStart5xxObservedCount": cold_start_5xx_observed,
        "bridgeDisconnectCount": bridge_disconnect_count,
        "bridgeDisconnectRate": bridge_disconnect_rate,
        "startupLatencyP95": _p95(latencies),
        "elapsedSeconds": elapsed_seconds,
        "configuredConcurrency": worker_limit,
        "effectiveConcurrency": maximum_active_workers,
        "probeJobsPerHour": probe_jobs_per_hour,
        "unrecoveredFailures": total - success_count,
        "ready": not issues,
        "issues": issues,
        "startedAt": started_at,
        "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": rows,
    }

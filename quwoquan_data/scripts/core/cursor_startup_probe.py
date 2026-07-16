"""Run and classify real Cursor SDK startup probes for data execution admission."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

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
    model: str = DEFAULT_CURSOR_STARTUP_MODEL,
    runtime: str = DEFAULT_CURSOR_STARTUP_RUNTIME,
    timeout_seconds: float | None = None,
    cwd: Path | None = None,
) -> dict:
    """Run a minimal real Cursor SDK Agent.prompt startup probe.

    Import/network/key checks are necessary but not sufficient: a batch can
    still fail at the bridge/account/startup boundary.  The probe runs in a
    short subprocess so a stuck SDK call cannot wedge the parent readiness gate.
    """

    try:
        from core.cursor_credentials import resolve_cursor_api_key
    except Exception:  # noqa: BLE001
        from cursor_credentials import resolve_cursor_api_key  # type: ignore
    # reload 最新 key（key 文件优先）并回写 os.environ，子进程探针继承轮换后的 key。
    key = resolve_cursor_api_key()
    if not key:
        return {
            "checked": False,
            "ready": False,
            "started": False,
            "runtime": runtime,
            "model": model,
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

api_key = os.environ.get("CURSOR_API_KEY", "")
model = sys.argv[1]
runtime = sys.argv[2]
cwd = sys.argv[3]
bridge_timeout = int(sys.argv[4])
try:
    with Client.launch_bridge(
        workspace=cwd,
        timeout=bridge_timeout,
        local=LocalAgentOptions(cwd=cwd, setting_sources=[]),
        allow_api_key_env_fallback=True,
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
        result = Agent.prompt(
            "quwoquan_data env startup probe. Do not edit files. Reply with the single word READY.",
            opts,
            client=client,
        )
    status = getattr(result, "status", "")
    print(json.dumps({
        "ready": status == "finished",
        "started": True,
        "probeType": "agent_prompt_smoke",
        "status": status,
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
                    str(model),
                    str(runtime),
                    probe_cwd,
                    str(runtime_policy.cursor_bridge_handshake_timeout_seconds),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=remaining,
                env=os.environ.copy(),
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
                "model": model,
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
        attempts.append(
            {
                "attempt": attempt,
                    "startedAt": attempt_started_at,
                "ready": bool(payload.get("ready")),
                "status": payload.get("status"),
                "errorClass": _redact_secret_value(payload.get("errorClass")),
                "error": _redact_secret_value(payload.get("error")),
                "httpStatus": payload.get("httpStatus"),
                "errorCode": payload.get("errorCode"),
                "requestId": payload.get("requestId"),
                "retryable": bool(payload.get("retryable", False)),
                "retryAfter": _redact_secret_value(payload.get("retryAfter")),
                "agentId": payload.get("agentId"),
                "runId": payload.get("runId"),
            }
        )
        if payload.get("ready"):
            break
        if not bool(payload.get("retryable", False)) or attempt >= 3:
            break
        retry_after = payload.get("retryAfter")
        try:
            requested_delay = float(retry_after) if retry_after is not None else 0.0
        except (TypeError, ValueError):
            requested_delay = 0.0
        exponential_delay = float(2 ** (attempt - 1))
        sleep_seconds = min(
            max(exponential_delay, requested_delay),
            max(0.0, deadline - time.monotonic()),
        )
        if sleep_seconds <= 0:
            break
        time.sleep(sleep_seconds)
    issues = []
    if not payload.get("ready"):
        issues.append(_redact_secret_text(str(payload.get("error") or payload.get("status") or "cursor startup probe failed")))
    return {
        "checked": True,
        "ready": bool(payload.get("ready")),
        "started": bool(payload.get("started")),
        "probeType": payload.get("probeType") or "agent_prompt_smoke",
        "runtime": runtime,
        "model": model,
        "probePython": str(probe_python),
        "status": payload.get("status"),
        "error": _redact_secret_value(payload.get("error")),
        "errorClass": _redact_secret_value(payload.get("errorClass")),
        "retryable": bool(payload.get("retryable", False)),
        "errorCode": payload.get("errorCode"),
        "httpStatus": payload.get("httpStatus"),
        "protoErrorCode": payload.get("protoErrorCode"),
        "requestId": payload.get("requestId"),
        "details": _redact_secret_value(payload.get("details") or []),
        "headers": _redact_secret_value(payload.get("headers") or {}),
        "retryAfter": _redact_secret_value(payload.get("retryAfter")),
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
    model: str = DEFAULT_CURSOR_STARTUP_MODEL,
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
    rows: list[dict] = []
    latencies: list[float] = []
    success_count = 0
    auth_failures = 0
    true_5xx_count = 0
    startup_timeout_count = 0
    bridge_disconnect_count = 0
    cold_start_5xx_observed = 0
    for index in range(1, total + 1):
        begin = time.monotonic()
        payload = cursor_startup_probe(
            model=model,
            runtime=runtime,
            timeout_seconds=effective_timeout_seconds,
            cwd=cwd,
        )
        elapsed = round(time.monotonic() - begin, 4)
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
        "schemaVersion": "quwoquan_data.cursor_startup_probe_suite/2",
        "model": model,
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
        "ready": not issues,
        "issues": issues,
        "startedAt": started_at,
        "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": rows,
    }


_CURSOR_STARTUP_PROBE_CACHE_FILENAME = "cursor_startup_probe_cache.json"


def _cursor_startup_probe_cache_ttl_seconds() -> float:
    raw = os.environ.get("QWQ_CURSOR_STARTUP_PROBE_CACHE_TTL_SECONDS", "")
    try:
        value = float(raw) if raw else 600.0
    except ValueError:
        value = 600.0
    return max(0.0, value)


def _cursor_startup_probe_cache_path() -> Path:
    from core.paths import DATA_LOCAL_ROOT

    return DATA_LOCAL_ROOT / "cache" / "cursor" / _CURSOR_STARTUP_PROBE_CACHE_FILENAME


def _cached_cursor_startup_probe(
    *,
    model: str,
    runtime: str,
    timeout_seconds: float,
) -> dict:
    """resume 轮 preflight 降本：TTL 内复用最近一次成功的 startup probe。

    只缓存 ready=true 的结果（失败必须重新探测）；缓存键不包含凭据派生值。
    凭据轮换后应通过 ``task preflight`` 重新探测，而不是从缓存推断鉴权结论。
    """
    ttl = _cursor_startup_probe_cache_ttl_seconds()
    cache_key = f"{model}::{runtime}"
    cache_path = _cursor_startup_probe_cache_path()
    if ttl > 0 and cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            entry = cached.get(cache_key) if isinstance(cached, dict) else None
            if (
                isinstance(entry, dict)
                and bool((entry.get("report") or {}).get("ready"))
                and (time.time() - float(entry.get("cachedAtEpoch") or 0)) < ttl
            ):
                report = dict(entry["report"])
                report["cacheHit"] = True
                report["cachedAt"] = entry.get("cachedAt")
                return report
        except (OSError, ValueError, TypeError):
            pass
    report = cursor_startup_probe(
        model=model,
        runtime=runtime,
        timeout_seconds=timeout_seconds,
    )
    if ttl > 0 and bool(report.get("ready")):
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            existing: dict = {}
            if cache_path.is_file():
                try:
                    existing = json.loads(cache_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    existing = {}
            if not isinstance(existing, dict):
                existing = {}
            existing[cache_key] = {
                "cachedAtEpoch": time.time(),
                "cachedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "report": report,
            }
            cache_path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
    return report

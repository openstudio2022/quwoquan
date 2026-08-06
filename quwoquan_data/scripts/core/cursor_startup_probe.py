"""Run and classify real Cursor SDK startup probes for data execution admission."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from core.cursor_model import CursorModelSelection
from core.cursor_probe_classification import (
    cursor_probe_attempt_has_5xx as _cursor_probe_attempt_has_5xx,
    cursor_probe_attempt_is_auth as _cursor_probe_attempt_is_auth,
    cursor_probe_attempt_is_bridge_disconnect as _cursor_probe_attempt_is_bridge_disconnect,
)
from core.python_environment import (
    DEFAULT_SEMANTIC_AGENT_MODEL,
    DEFAULT_SEMANTIC_AGENT_RUNTIME,
    REPO_ROOT,
    _redact_secret_text,
    _redact_secret_value,
    resolve_data_agent_python,
)
from core.runtime_policy import active_runtime_policy


def cursor_startup_probe(
    *,
    model: str | CursorModelSelection = DEFAULT_SEMANTIC_AGENT_MODEL,
    runtime: str = DEFAULT_SEMANTIC_AGENT_RUNTIME,
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
        from core.cursor_credentials import (
            cursor_credential_subprocess_env,
            protected_cursor_api_key_fd,
            resolve_cursor_api_key,
        )
    except Exception:  # noqa: BLE001
        from cursor_credentials import (  # type: ignore
            cursor_credential_subprocess_env,
            protected_cursor_api_key_fd,
            resolve_cursor_api_key,
        )
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
    probe_python = resolve_data_agent_python(include_current=True) or Path(
        sys.executable
    )
    code = r"""
import importlib.metadata
import json
import os
import sys

sys.path.insert(0, sys.argv[5])
from core.cursor_bridge_transport import protected_cursor_client

try:
    from cursor_sdk import (
        Agent,
        AgentOptions,
        CloudAgentOptions,
        CursorAgentError,
        LocalAgentOptions,
        ModelParameterValue,
        ModelSelection,
    )
except Exception as exc:
    print(json.dumps({"ready": False, "started": False, "error": f"cursor_sdk unavailable: {exc}"}, ensure_ascii=False))
    raise SystemExit(0)

credential_fd = int(os.environ.pop("QWQ_CURSOR_API_KEY_FD"))
with os.fdopen(credential_fd, "r", encoding="utf-8", closefd=True) as credential_stream:
    api_key = credential_stream.readline().strip()
model_doc = json.loads(sys.argv[1])
model = ModelSelection(
    id=str(model_doc["id"]),
    params=tuple(
        ModelParameterValue(id=str(parameter["id"]), value=str(parameter["value"]))
        for parameter in model_doc.get("params", [])
    ),
)
runtime = sys.argv[2]
cwd = sys.argv[3]
bridge_timeout = int(sys.argv[4])
def is_provider_rejection(message):
    lowered = str(message or "").casefold()
    return any(
        marker in lowered
        for marker in (
            "you've hit your usage limit",
            "usage limit",
            "spend limit",
            "monthly cycle ends",
            "insufficient credits",
        )
    )

try:
    with protected_cursor_client(
        workspace=cwd,
        timeout=bridge_timeout,
        max_retries=0,
    ) as client:
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
    raw_status = getattr(result, "status", "")
    status = str(getattr(raw_status, "value", raw_status))
    agent_id = str(getattr(result, "agent_id", "") or "")
    run_id = str(getattr(result, "id", "") or "")
    identity_ready = bool(agent_id and run_id)
    ready = status == "finished" and identity_ready
    print(json.dumps({
        "ready": ready,
        "started": True,
        "probeType": "agent_prompt_smoke",
        "status": status,
        "errorClass": "AgentStatusError" if not ready else None,
        "error": (
            terminal_status_message
            if status != "finished"
            else ("finished Cursor run is missing agentId/runId" if not identity_ready else None)
        ),
        "errorCode": (
            "provider_rejected"
            if terminal_status_message
            else ("invalid_run_identity" if not identity_ready else None)
        ),
        "retryable": False,
        "agentId": agent_id or None,
        "runId": run_id or None,
        "sdkVersion": importlib.metadata.version("cursor-sdk"),
    }, ensure_ascii=False))
except CursorAgentError as exc:
    error_message = getattr(exc, "message", str(exc))
    provider_rejected = is_provider_rejection(error_message)
    print(json.dumps({
        "ready": False,
        "started": False,
        "probeType": "agent_prompt_smoke",
        "status": "error",
        "errorClass": type(exc).__name__,
        "error": error_message,
        "retryable": False if provider_rejected else bool(getattr(exc, "is_retryable", False)),
        "errorCode": "provider_rejected" if provider_rejected else getattr(exc, "code", None),
        "httpStatus": getattr(exc, "status", None),
        "protoErrorCode": getattr(exc, "proto_error_code", None),
        "requestId": getattr(exc, "request_id", None),
        "details": getattr(exc, "details", None),
        "headers": dict(getattr(exc, "headers", {}) or {}),
        "retryAfter": getattr(exc, "retry_after", None),
        "sdkVersion": importlib.metadata.version("cursor-sdk"),
    }, ensure_ascii=False))
except Exception as exc:
    print(json.dumps({
        "ready": False,
        "started": False,
        "probeType": "agent_prompt_smoke",
        "status": "error",
        "errorClass": type(exc).__name__,
        "error": str(exc),
        "sdkVersion": importlib.metadata.version("cursor-sdk"),
    }, ensure_ascii=False))
"""
    deadline = time.monotonic() + max(1, effective_timeout_seconds)
    attempts: list[dict] = []
    payload: dict = {
        "ready": False,
        "started": False,
        "error": "cursor startup probe not run",
    }
    returncode = 0
    for attempt in range(1, runtime_policy.preflight_startup_attempts + 1):
        attempt_started_at = datetime.now(timezone.utc).isoformat()
        remaining = max(1, int(deadline - time.monotonic()))
        try:
            with protected_cursor_api_key_fd(key) as credential_fd:
                proc = subprocess.run(
                    [
                        str(probe_python),
                        "-c",
                        code,
                        json.dumps(
                            selection.to_sdk_document(),
                            ensure_ascii=True,
                            sort_keys=True,
                        ),
                        str(runtime),
                        probe_cwd,
                        str(runtime_policy.cursor_bridge_handshake_timeout_seconds),
                        str(Path(__file__).resolve().parents[1]),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=remaining,
                    env=cursor_credential_subprocess_env(
                        os.environ, credential_fd=credential_fd
                    ),
                    stdin=subprocess.DEVNULL,
                    pass_fds=(credential_fd,),
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
                "issues": [
                    f"cursor startup probe timed out after {int(effective_timeout_seconds)}s"
                ],
            }
        returncode = proc.returncode
        try:
            payload = json.loads((proc.stdout or "{}").strip() or "{}")
        except json.JSONDecodeError:
            payload = {
                "ready": False,
                "started": False,
                "status": "error",
                "error": proc.stderr.strip()
                or "cursor startup probe did not return JSON",
            }
        payload = (
            payload
            if isinstance(payload, dict)
            else {"ready": False, "started": False, "error": "invalid probe payload"}
        )
        if returncode != 0 and payload.get("ready"):
            payload["ready"] = False
            payload["error"] = f"cursor startup probe exited {returncode}"
        retryable = bool(payload.get("retryable", False))
        if not payload.get("ready") and not _cursor_probe_attempt_is_auth(payload):
            retryable = (
                retryable
                or _cursor_probe_attempt_has_5xx(payload)
                or _cursor_probe_attempt_is_bridge_disconnect(payload)
            )
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
        "agentId": payload.get("agentId"),
        "runId": payload.get("runId"),
        "sdkVersion": payload.get("sdkVersion"),
        "attemptCount": len(attempts),
        "attempts": attempts,
        "issues": issues,
    }

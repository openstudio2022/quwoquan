"""Canonical Python runtime resolution for data/agent CLI commands."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import venv
from pathlib import Path
from typing import Iterable, Mapping
from urllib import error as urlerror
from urllib import request as urlrequest

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = SCRIPTS_ROOT.parent
REPO_ROOT = DATA_ROOT.parent
REQUIREMENTS_PATH = DATA_ROOT / "requirements.txt"
DATA_VENV_DIR = DATA_ROOT / ".venv"
FANOUT_VENV_DIR = REPO_ROOT / ".venv-fanout"

AGENT_RUNTIME_MODULES = ("cursor_sdk", "PIL", "cv2", "numpy", "yaml", "pytesseract", "imagehash")
AGENT_RUNTIME_BINARIES = ("tesseract",)
BOOTSTRAP_ENV = "QWQ_DATA_CLI_BOOTSTRAPPED"
NETWORK_SKIP_ENV = "QWQ_ENV_SKIP_NETWORK_CHECK"
DEFAULT_NETWORK_ENDPOINTS = (
    "https://api2.cursor.sh/",
    "https://www.wikipedia.org/",
    "https://commons.wikimedia.org/",
)
CURSOR_CLOUD_API_ME_URL = "https://api.cursor.com/v1/me"
DEFAULT_CURSOR_STARTUP_MODEL = os.environ.get("QWQ_CURSOR_AGENT_MODEL", "composer")
DEFAULT_CURSOR_STARTUP_RUNTIME = "local"
CURSOR_STARTUP_TIMEOUT_ENV = "QWQ_CURSOR_STARTUP_TIMEOUT_SECONDS"
DEFAULT_CURSOR_STARTUP_TIMEOUT_SECONDS = 240.0


def resolve_cursor_startup_timeout_seconds(
    value: object | None = None,
    *,
    default: float = DEFAULT_CURSOR_STARTUP_TIMEOUT_SECONDS,
) -> float:
    raw = value
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raw = os.environ.get(CURSOR_STARTUP_TIMEOUT_ENV)
    try:
        seconds = float(raw) if raw not in (None, "") else float(default)
    except (TypeError, ValueError):
        seconds = float(default)
    return max(1.0, seconds)


def _redact_secret_text(value: str) -> str:
    return re.sub(r"crsr_[A-Za-z0-9]+", "<redacted-cursor-key>", str(value or ""))


def _redact_secret_value(value):
    if isinstance(value, dict):
        return {
            _redact_secret_text(str(k)): _redact_secret_value(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_secret_value(item) for item in value]
    if isinstance(value, str):
        return _redact_secret_text(value)
    return value


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


DATA_VENV_PYTHON = _venv_python(DATA_VENV_DIR)
FANOUT_VENV_PYTHON = _venv_python(FANOUT_VENV_DIR)


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def candidate_pythons(*, include_current: bool = True) -> list[Path]:
    """Return Python candidates in the only supported preference order."""
    configured = os.environ.get("QWQ_DATA_PYTHON")
    paths: list[Path] = []
    if include_current:
        paths.append(Path(sys.executable))
    if configured:
        paths.append(Path(configured).expanduser())
    paths.extend([DATA_VENV_PYTHON, FANOUT_VENV_PYTHON])
    return [p for p in _dedupe_paths(paths) if p.is_file()]


def python_has_modules(python: Path, modules: Iterable[str]) -> tuple[bool, list[str]]:
    """Import modules in the target interpreter and return missing names."""
    module_list = [str(m) for m in modules]
    if not module_list:
        return True, []
    code = (
        "import json, sys\n"
        "missing=[]\n"
        "for name in sys.argv[1:]:\n"
        "    try:\n"
        "        __import__(name)\n"
        "    except Exception as exc:\n"
        "        missing.append(f'{name}: {exc}')\n"
        "print(json.dumps({'missing': missing}, ensure_ascii=False))\n"
        "raise SystemExit(1 if missing else 0)\n"
    )
    proc = subprocess.run(
        [str(python), "-c", code, *module_list],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads((proc.stdout or "{}").strip() or "{}")
    except json.JSONDecodeError:
        payload = {"missing": [proc.stderr.strip() or f"{python}: module check failed"]}
    missing = [str(item) for item in (payload.get("missing") or [])]
    if proc.returncode != 0 and not missing:
        missing = [proc.stderr.strip() or f"{python}: module check failed"]
    return not missing, missing


def resolve_python_for_modules(
    modules: Iterable[str] = AGENT_RUNTIME_MODULES,
    *,
    include_current: bool = True,
) -> Path | None:
    """Resolve the first interpreter that can import all requested modules."""
    for python in candidate_pythons(include_current=include_current):
        ok, _missing = python_has_modules(python, modules)
        if ok:
            return python
    return None


def resolve_data_agent_python(*, include_current: bool = True) -> Path | None:
    return resolve_python_for_modules(AGENT_RUNTIME_MODULES, include_current=include_current)


def agent_command_needs_bootstrap(argv: list[str]) -> bool:
    """Detect CLI commands that must run inside the data agent interpreter."""
    args = list(argv[1:])
    if len(args) >= 3 and args[:3] == ["task", "scaled-e2e", "run"]:
        return True
    if len(args) >= 3 and args[:3] == ["task", "scaled-e2e", "author-runner"]:
        return True
    if len(args) >= 2 and args[:2] == ["task", "run"] and "--managed" in args:
        return True
    if len(args) >= 3 and args[:3] == ["data", "workflow", "run"] and "--managed" in args:
        return True
    return False


def maybe_reexec_for_agent_command(argv: list[str]) -> None:
    """Re-exec agent commands into the prepared data runtime when needed."""
    if os.environ.get(BOOTSTRAP_ENV) == "1":
        return
    if not agent_command_needs_bootstrap(argv):
        return
    ok, _missing = python_has_modules(Path(sys.executable), AGENT_RUNTIME_MODULES)
    if ok:
        return
    python = resolve_data_agent_python(include_current=False)
    if python is None:
        missing = ", ".join(AGENT_RUNTIME_MODULES)
        print(
            f"[qwq-data env] current Python lacks agent dependencies ({missing}); "
            "run `python3 quwoquan_data/scripts/cli.py env ready` first.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    env = os.environ.copy()
    env[BOOTSTRAP_ENV] = "1"
    os.execvpe(str(python), [str(python), *argv], env)


def prepare_data_runtime(*, python: Path | None = None, requirements: Path | None = None) -> dict:
    """Create/update the canonical data venv and install pinned requirements."""
    venv_python = python or DATA_VENV_PYTHON
    requirements_path = requirements or REQUIREMENTS_PATH
    if not requirements_path.is_file():
        raise RuntimeError(f"requirements file missing: {requirements_path}")
    if not venv_python.is_file():
        venv.create(DATA_VENV_DIR, with_pip=True)
    proc = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-r", str(requirements_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    ok, missing = python_has_modules(venv_python, AGENT_RUNTIME_MODULES)
    missing_binaries = [name for name in AGENT_RUNTIME_BINARIES if shutil.which(name) is None]
    return {
        "python": str(venv_python),
        "requirements": str(requirements_path),
        "installReturnCode": proc.returncode,
        "stdoutTail": (proc.stdout or "")[-2000:],
        "stderrTail": (proc.stderr or "")[-2000:],
        "ready": proc.returncode == 0 and ok and not missing_binaries,
        "missing": missing + [f"{name}: binary not found on PATH" for name in missing_binaries],
    }


def runtime_report() -> dict:
    current = Path(sys.executable)
    rows = []
    missing_binaries = [name for name in AGENT_RUNTIME_BINARIES if shutil.which(name) is None]
    for python in candidate_pythons(include_current=True):
        ok, missing = python_has_modules(python, AGENT_RUNTIME_MODULES)
        full_missing = missing + [f"{name}: binary not found on PATH" for name in missing_binaries]
        rows.append({"python": str(python), "ready": ok and not missing_binaries, "missing": full_missing})
    resolved = resolve_data_agent_python(include_current=True)
    if resolved is not None and missing_binaries:
        resolved = None
    return {
        "schemaVersion": "quwoquan_data.python_runtime",
        "currentPython": str(current),
        "requirements": str(REQUIREMENTS_PATH),
        "agentModules": list(AGENT_RUNTIME_MODULES),
        "agentBinaries": list(AGENT_RUNTIME_BINARIES),
        "resolvedPython": str(resolved) if resolved else None,
        "ready": resolved is not None,
        "candidates": rows,
    }


def _cursor_key_report(value: str | None) -> dict:
    key = str(value or "").strip()
    if not key:
        return {"present": False, "format": "missing", "valid": False}
    valid = key.startswith("crsr_") and len(key) >= 24
    return {
        "present": True,
        "format": "cursor_api_key" if valid else "invalid",
        "valid": valid,
        "redacted": "<present>",
    }


def _parse_json_bytes(payload: bytes) -> dict:
    try:
        decoded = payload.decode("utf-8")
    except Exception:  # noqa: BLE001
        return {}
    try:
        parsed = json.loads(decoded or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _cursor_cloud_api_key_type(payload: Mapping[str, object]) -> str:
    if payload.get("userId") or payload.get("userEmail"):
        return "user_api_key"
    if payload.get("apiKeyName"):
        return "service_account_api_key"
    return "unknown"


def _cursor_cloud_api_result(
    *,
    status: int | None,
    payload: Mapping[str, object] | None = None,
    fallback_message: str = "",
) -> dict:
    body = payload if isinstance(payload, Mapping) else {}
    if status == 200:
        return {
            "checked": True,
            "ready": True,
            "endpoint": CURSOR_CLOUD_API_ME_URL,
            "status": 200,
            "keyType": _cursor_cloud_api_key_type(body),
            "issues": [],
        }
    error_payload = body.get("error") if isinstance(body.get("error"), Mapping) else {}
    error_code = str(error_payload.get("code") or "").strip() or None
    message = _redact_secret_text(
        str(error_payload.get("message") or fallback_message or f"HTTP {status or 'unknown'}")
    )
    issue = (
        "Cursor Cloud Agent unavailable for current API key: "
        f"{error_code or 'forbidden'} ({message})"
        if error_code == "plan_required"
        else (
            f"CURSOR_API_KEY unauthorized for Cursor Cloud Agent API ({message})"
            if int(status or 0) == 401
            else (
                "CURSOR_API_KEY rejected by Cursor Cloud Agent API: "
                f"{error_code or 'http_' + str(status or 'unknown')} ({message})"
            )
        )
    )
    return {
        "checked": True,
        "ready": False,
        "endpoint": CURSOR_CLOUD_API_ME_URL,
        "status": status,
        "keyType": _cursor_cloud_api_key_type(body),
        "errorCode": error_code,
        "message": message,
        "issues": [issue],
    }


def _cursor_cloud_api_probe_with_curl(key: str, *, timeout_seconds: float) -> dict | None:
    curl = shutil.which("curl")
    if not curl:
        return None
    proc = subprocess.run(
        [
            curl,
            "-sS",
            "-L",
            "--max-time",
            str(max(1, int(timeout_seconds))),
            "-H",
            f"Authorization: Bearer {key}",
            "-H",
            "Accept: application/json",
            "-H",
            "User-Agent: quwoquan-data-env-preflight",
            "--output",
            "-",
            "--write-out",
            "\n%{http_code}",
            CURSOR_CLOUD_API_ME_URL,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = (proc.stdout or "").splitlines()
    status_text = lines[-1].strip() if lines else ""
    try:
        status = int(status_text)
    except ValueError:
        status = 0
    body_text = "\n".join(lines[:-1]) if len(lines) > 1 else ""
    payload = {}
    if body_text.strip():
        try:
            parsed = json.loads(body_text)
        except json.JSONDecodeError:
            parsed = {}
        payload = parsed if isinstance(parsed, dict) else {}
    if status:
        return _cursor_cloud_api_result(
            status=status,
            payload=payload,
            fallback_message=(proc.stderr or "").strip(),
        )
    message = _redact_secret_text((proc.stderr or "").strip() or body_text.strip())
    return {
        "checked": True,
        "ready": False,
        "endpoint": CURSOR_CLOUD_API_ME_URL,
        "status": None,
        "keyType": "unknown",
        "errorCode": None,
        "message": message,
        "issues": [f"Cursor Cloud Agent API probe failed: {message or 'curl unavailable'}"],
    }


def _cursor_cloud_api_probe(*, timeout_seconds: float = 5.0) -> dict:
    key = str(os.environ.get("CURSOR_API_KEY") or "").strip()
    if not key:
        return {
            "checked": False,
            "ready": True,
            "endpoint": CURSOR_CLOUD_API_ME_URL,
            "issues": [],
            "skipReason": "CURSOR_API_KEY missing",
        }
    request = urlrequest.Request(
        CURSOR_CLOUD_API_ME_URL,
        method="GET",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "quwoquan-data-env-preflight",
        },
    )
    try:
        with urlrequest.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            return _cursor_cloud_api_result(
                status=int(getattr(response, "status", 0) or 0),
                payload=_parse_json_bytes(response.read()),
            )
    except urlerror.HTTPError as exc:
        return _cursor_cloud_api_result(
            status=int(exc.code),
            payload=_parse_json_bytes(exc.read()),
            fallback_message=str(exc.reason or f"HTTP {exc.code}"),
        )
    except Exception as exc:  # noqa: BLE001
        curl_report = _cursor_cloud_api_probe_with_curl(key, timeout_seconds=timeout_seconds)
        if curl_report is not None:
            return curl_report
        message = _redact_secret_text(str(exc))
        return {
            "checked": True,
            "ready": False,
            "endpoint": CURSOR_CLOUD_API_ME_URL,
            "status": None,
            "keyType": "unknown",
            "errorCode": None,
            "message": message,
            "issues": [f"Cursor Cloud Agent API probe failed: {type(exc).__name__}: {message}"],
        }


def _probe_endpoint(url: str, *, timeout_seconds: float) -> dict:
    row = {"url": url, "reachable": False, "status": None, "error": "", "method": ""}
    last_error = ""
    for method in ("HEAD", "GET"):
        request = urlrequest.Request(
            url,
            method=method,
            headers={"User-Agent": "quwoquan-data-env-preflight"},
        )
        try:
            with urlrequest.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                row["status"] = int(getattr(response, "status", 0) or 0)
                row["reachable"] = True
                row["method"] = method
                row["error"] = ""
                return row
        except urlerror.HTTPError as exc:
            row["status"] = int(exc.code)
            row["method"] = method
            # 401/403/404/405 still prove DNS/TLS/routing reached the service.
            row["reachable"] = exc.code < 500
            row["error"] = "" if row["reachable"] else str(exc)
            if row["reachable"]:
                return row
            last_error = str(exc)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            # Some endpoints close TLS/HTTP2 HEAD probes but accept GET. Retry
            # with GET before declaring the network unavailable.
            if method == "HEAD":
                continue
            row["method"] = method
            row["error"] = last_error
    curl_row = _probe_endpoint_with_curl(url, timeout_seconds=timeout_seconds)
    if curl_row["reachable"]:
        return curl_row
    if not row["error"]:
        row["error"] = curl_row.get("error") or last_error
    return row


def _probe_endpoint_with_curl(url: str, *, timeout_seconds: float) -> dict:
    row = {"url": url, "reachable": False, "status": None, "error": "", "method": "curl"}
    curl = shutil.which("curl")
    if not curl:
        row["error"] = "curl not found"
        return row
    proc = subprocess.run(
        [
            curl,
            "-I",
            "-L",
            "--retry",
            "2",
            "--retry-delay",
            "1",
            "--retry-all-errors",
            "--max-time",
            str(max(1, int(timeout_seconds))),
            "--silent",
            "--show-error",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    code_text = (proc.stdout or "").strip()
    try:
        status = int(code_text)
    except ValueError:
        status = 0
    row["status"] = status or None
    if proc.returncode == 0 and status and status < 500:
        row["reachable"] = True
        return row
    row["error"] = (proc.stderr or "").strip() or f"curl status={status or 'unknown'}"
    return row


def check_network_endpoints(
    endpoints: Iterable[str] | None = None,
    *,
    timeout_seconds: float = 5.0,
) -> dict:
    """Probe Cursor and source-network reachability without exposing credentials."""
    configured = os.environ.get("QWQ_ENV_NETWORK_ENDPOINTS")
    if endpoints is None and configured:
        endpoints = [part.strip() for part in configured.split(",") if part.strip()]
    urls = list(endpoints or DEFAULT_NETWORK_ENDPOINTS)
    if os.environ.get(NETWORK_SKIP_ENV) == "1":
        return {
            "checked": False,
            "skipped": True,
            "skipReason": f"{NETWORK_SKIP_ENV}=1",
            "ready": True,
            "endpoints": [{"url": url, "reachable": None, "status": None, "error": ""} for url in urls],
            "issues": [],
        }
    rows = [_probe_endpoint(url, timeout_seconds=timeout_seconds) for url in urls]
    issues = [
        f"network endpoint unreachable: {row['url']}: {row.get('error') or row.get('status') or 'unknown'}"
        for row in rows
        if not row.get("reachable")
    ]
    return {
        "checked": True,
        "skipped": False,
        "ready": not issues,
        "endpoints": rows,
        "issues": issues,
    }


def cursor_startup_probe(
    *,
    model: str = DEFAULT_CURSOR_STARTUP_MODEL,
    runtime: str = DEFAULT_CURSOR_STARTUP_RUNTIME,
    timeout_seconds: float = 180.0,
    cwd: Path | None = None,
) -> dict:
    """Run a minimal real Cursor SDK Agent.prompt startup probe.

    Import/network/key checks are necessary but not sufficient: a batch can
    still fail at the bridge/account/startup boundary.  The probe runs in a
    short subprocess so a stuck SDK call cannot wedge the parent readiness gate.
    """

    try:
        from _common.cursor_credentials import resolve_cursor_api_key
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
            "issues": ["CURSOR_API_KEY missing"],
        }
    probe_cwd = str((cwd or REPO_ROOT).resolve())
    probe_python = resolve_data_agent_python(include_current=True) or Path(sys.executable)
    code = r'''
import json
import os
import sys

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
    except Exception:
        pass
except Exception as exc:
    print(json.dumps({"ready": False, "started": False, "error": f"cursor_sdk unavailable: {exc}"}, ensure_ascii=False))
    raise SystemExit(0)

import time as _time

api_key = os.environ.get("CURSOR_API_KEY", "")
model = sys.argv[1]
runtime = sys.argv[2]
cwd = sys.argv[3]


def _transient(exc) -> bool:
    cls = type(exc).__name__
    msg = str(getattr(exc, "message", "") or str(exc)).casefold()
    code = str(getattr(exc, "code", "") or "").casefold()
    status = getattr(exc, "status", None)
    try:
        status_int = int(status) if status is not None else 0
    except (TypeError, ValueError):
        status_int = 0
    markers = ("connection refused", "connecterror", "connection reset",
               "server disconnected", "remoteprotocolerror", "bridge request failed",
               "internal error", "exited before discovery", "failed before discovery")
    return (
        cls in ("InternalServerError", "NetworkError")
        or code == "internal"
        or 500 <= status_int < 600
        or any(m in msg for m in markers)
    )


# Launch one bridge and warm it with retries: the Cursor backend/bridge
# intermittently fails the first call after a cold launch, but the same warm
# bridge is then stable.  Reusing one warm bridge mirrors the stable runtime
# path and avoids relaunching a cold bridge per attempt.
try:
    bridge_timeout = max(10, int(float(os.environ.get("QWQ_CURSOR_BRIDGE_TIMEOUT", "60"))))
    client = Client.launch_bridge(workspace=cwd, timeout=bridge_timeout, allow_api_key_env_fallback=True)
    if runtime == "cloud":
        opts = AgentOptions(api_key=api_key, model=model, cloud=CloudAgentOptions(repos=[]))
    else:
        opts = AgentOptions(api_key=api_key, model=model, local=LocalAgentOptions(cwd=cwd))
    warm_attempts = max(1, int(float(os.environ.get("QWQ_CURSOR_WARM_ATTEMPTS", "6"))))
    result = None
    last_exc = None
    try:
        for _i in range(warm_attempts):
            try:
                result = Agent.prompt("quwoquan_data env startup probe. Do not edit files. Reply with the single word READY.", opts, client=client)
                if getattr(result, "status", "") == "finished":
                    break
            except CursorAgentError as exc:
                last_exc = exc
                if not _transient(exc):
                    raise
            except Exception as exc:
                last_exc = exc
                if not _transient(exc):
                    raise
            _time.sleep(2)
    finally:
        bridge = getattr(client, "_owned_bridge", None)
        endpoint = getattr(bridge, "endpoint", None)
        client.close()
    if result is None and last_exc is not None:
        raise last_exc
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
    deadline = time.monotonic() + max(1, float(timeout_seconds))
    attempts: list[dict] = []
    payload: dict = {"ready": False, "started": False, "error": "cursor startup probe not run"}
    returncode = 0
    for attempt in range(1, 4):
        remaining = max(1, int(deadline - time.monotonic()))
        try:
            proc = subprocess.run(
                [str(probe_python), "-c", code, str(model), str(runtime), probe_cwd],
                capture_output=True,
                text=True,
                check=False,
                timeout=remaining,
                env=os.environ.copy(),
                cwd=probe_cwd,
            )
        except subprocess.TimeoutExpired:
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
                "issues": [f"cursor startup probe timed out after {int(timeout_seconds)}s"],
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
                "ready": bool(payload.get("ready")),
                "status": payload.get("status"),
                "errorClass": _redact_secret_value(payload.get("errorClass")),
                "error": _redact_secret_value(payload.get("error")),
                "httpStatus": payload.get("httpStatus"),
            }
        )
        if payload.get("ready"):
            break
        error_text = str(payload.get("error") or "")
        error_class = str(payload.get("errorClass") or "")
        bridge_not_ready = (
            error_class == "NetworkError"
            and ("Connection refused" in error_text or "ConnectError" in error_text)
        )
        # Cursor backend intermittently returns HTTP 5xx / InternalServerError on
        # the first Agent.prompt of a freshly launched bridge (cold start); an
        # immediate retry succeeds.  5xx is the canonical transient class, so the
        # probe retries it instead of failing admission on a single cold 500.
        http_status = payload.get("httpStatus")
        try:
            http_status_int = int(http_status) if http_status is not None else 0
        except (TypeError, ValueError):
            http_status_int = 0
        transient_server_error = (
            error_class == "InternalServerError"
            or str(payload.get("errorCode") or "") == "internal"
            or 500 <= http_status_int < 600
        )
        if (not bridge_not_ready and not transient_server_error) or attempt >= 3:
            break
        sleep_seconds = min(2.0, max(0.25, deadline - time.monotonic()))
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
        from _common.cursor_credentials import is_cursor_auth_error
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
    attempts: int = 20,
    timeout_seconds: float = 180.0,
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
    total = max(1, int(attempts or 1))
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
            timeout_seconds=timeout_seconds,
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
    if true_5xx_rate >= 0.10:
        issues.append(f"Cursor true 5xx rate {true_5xx_rate:.2%} >= 10%")
    if startup_timeout_rate >= 0.50:
        issues.append(
            f"Cursor startup timeout rate {startup_timeout_rate:.2%} >= 50% "
            f"(raise --startup-timeout-seconds / warm bridge reuse; not a backend 5xx)"
        )
    if success_count == 0:
        issues.append("Cursor startup probe never succeeded")
    return {
        "schemaVersion": "quwoquan_data.cursor_startup_probe_suite/2",
        "model": model,
        "runtime": runtime,
        "attempts": total,
        "timeoutSeconds": round(float(timeout_seconds), 4),
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
    from _common.paths import current_runtime_root

    return current_runtime_root() / "env" / _CURSOR_STARTUP_PROBE_CACHE_FILENAME


def _cached_cursor_startup_probe(
    *,
    model: str,
    runtime: str,
    timeout_seconds: float,
) -> dict:
    """resume 轮 preflight 降本：TTL 内复用最近一次成功的 startup probe。

    只缓存 ready=true 的结果（失败必须重新探测）；缓存键 = model+runtime+key 指纹，
    避免换 key/换模型后误用旧结论。TTL=0 关闭缓存。
    """
    ttl = _cursor_startup_probe_cache_ttl_seconds()
    key_fingerprint = (os.environ.get("CURSOR_API_KEY") or "")[-8:]
    cache_key = f"{model}::{runtime}::{key_fingerprint}"
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


def environment_preflight(
    *,
    require_cursor_key: bool = True,
    check_network: bool = True,
    check_cursor_cloud_api: bool = True,
    endpoints: Iterable[str] | None = None,
    timeout_seconds: float = 5.0,
    check_cursor_startup: bool = False,
    cursor_startup_model: str = DEFAULT_CURSOR_STARTUP_MODEL,
    cursor_startup_runtime: str = DEFAULT_CURSOR_STARTUP_RUNTIME,
    cursor_startup_timeout_seconds: float = 45.0,
) -> dict:
    """Single pre-run readiness gate for managed data workflows."""
    if require_cursor_key:
        try:
            from _common.cursor_credentials import resolve_cursor_api_key
        except Exception:  # noqa: BLE001
            from cursor_credentials import resolve_cursor_api_key  # type: ignore
        resolve_cursor_api_key()
    runtime = runtime_report()
    cursor_key = _cursor_key_report(os.environ.get("CURSOR_API_KEY"))
    issues: list[str] = []
    if not runtime.get("ready"):
        issues.append(
            "agent runtime missing: run `python3 quwoquan_data/scripts/cli.py env ready`"
        )
    if require_cursor_key:
        if not cursor_key.get("present"):
            issues.append("CURSOR_API_KEY missing")
        elif not cursor_key.get("valid"):
            issues.append("CURSOR_API_KEY format invalid")
    local_blocked = bool(issues)
    if check_network and not local_blocked:
        network = check_network_endpoints(endpoints=endpoints, timeout_seconds=timeout_seconds)
        issues.extend(network.get("issues") or [])
    else:
        network = {
            "checked": False,
            "skipped": True,
            "skipReason": "disabled" if not check_network else "local_preflight_failed",
            "ready": True,
            "endpoints": [],
            "issues": [],
        }
    if require_cursor_key and check_cursor_cloud_api and not issues:
        cursor_cloud_api = _cursor_cloud_api_probe(timeout_seconds=max(3.0, timeout_seconds))
        issues.extend(cursor_cloud_api.get("issues") or [])
    else:
        cursor_cloud_api = {
            "checked": False,
            "ready": True,
            "endpoint": CURSOR_CLOUD_API_ME_URL,
            "issues": [],
            "skipReason": (
                "cursor_key_not_required"
                if not require_cursor_key
                else (
                    "local_runtime_only"
                    if not check_cursor_cloud_api
                    else "local_preflight_failed_or_network_unavailable"
                )
            ),
        }
    if check_cursor_startup and not issues and require_cursor_key:
        cursor_startup = _cached_cursor_startup_probe(
            model=cursor_startup_model,
            runtime=cursor_startup_runtime,
            timeout_seconds=cursor_startup_timeout_seconds,
        )
        issues.extend(cursor_startup.get("issues") or [])
    else:
        cursor_startup = {
            "checked": False,
            "ready": True,
            "started": False,
            "runtime": cursor_startup_runtime,
            "model": cursor_startup_model,
            "issues": [],
            "skipReason": (
                "disabled"
                if not check_cursor_startup
                else "local_preflight_failed_or_cursor_key_not_required"
            ),
        }
    return {
        "schemaVersion": "quwoquan_data.environment_preflight",
        "runtime": runtime,
        "cursorApiKey": cursor_key,
        "network": network,
        "cursorCloudApi": cursor_cloud_api,
        "cursorStartup": cursor_startup,
        "ready": not issues,
        "issues": issues,
    }

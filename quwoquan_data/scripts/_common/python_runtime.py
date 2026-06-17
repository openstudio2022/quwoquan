"""Canonical Python runtime resolution for data/agent CLI commands."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from typing import Iterable
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


def environment_preflight(
    *,
    require_cursor_key: bool = True,
    check_network: bool = True,
    endpoints: Iterable[str] | None = None,
    timeout_seconds: float = 5.0,
) -> dict:
    """Single pre-run readiness gate for managed data workflows."""
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
    return {
        "schemaVersion": "quwoquan_data.environment_preflight",
        "runtime": runtime,
        "cursorApiKey": cursor_key,
        "network": network,
        "ready": not issues,
        "issues": issues,
    }

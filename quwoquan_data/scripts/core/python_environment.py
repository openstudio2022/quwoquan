"""Resolve or rebuild the disposable data-agent Python tool cache."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import venv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping
from urllib import error as urlerror
from urllib import request as urlrequest

from core.runtime_policy import active_runtime_policy

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = SCRIPTS_ROOT.parent
REPO_ROOT = DATA_ROOT.parent
REQUIREMENTS_PATH = DATA_ROOT / "requirements.txt"
DEFAULT_PYTHON_CACHE_ROOT = (
    Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    / "quwoquan"
    / "python-envs"
)


def resolve_python_cache_root(value: str | None = None) -> Path:
    """Return the external tool-cache root and reject disposable-output paths."""
    candidate = Path(
        value
        or os.environ.get("QWQ_PYTHON_CACHE_ROOT")
        or DEFAULT_PYTHON_CACHE_ROOT
    ).expanduser().resolve()
    output_root = (REPO_ROOT / ".qwq_output").resolve()
    try:
        candidate.relative_to(output_root)
    except ValueError:
        return candidate
    raise ValueError("QWQ_PYTHON_CACHE_ROOT must not be inside .qwq_output")


PYTHON_CACHE_ROOT = resolve_python_cache_root()
DATA_VENV_CACHE_DIR = PYTHON_CACHE_ROOT / "quwoquan-data"

AGENT_RUNTIME_MODULES = (
    "cursor_sdk",
    "PIL",
    "cv2",
    "numpy",
    "yaml",
    "pytesseract",
    "imagehash",
    "imageio_ffmpeg",
)
AGENT_RUNTIME_BINARIES = ("tesseract",)
BOOTSTRAP_ENV = "QWQ_DATA_CLI_BOOTSTRAPPED"
NETWORK_SKIP_ENV = "QWQ_ENV_SKIP_NETWORK_CHECK"
DEFAULT_NETWORK_ENDPOINTS = (
    "https://api2.cursor.sh/",
    "https://www.wikipedia.org/",
    "https://commons.wikimedia.org/",
)
_RUNTIME_POLICY = active_runtime_policy()
DEFAULT_CURSOR_STARTUP_MODEL = _RUNTIME_POLICY.cursor_model_selection
DEFAULT_CURSOR_STARTUP_RUNTIME = _RUNTIME_POLICY.cursor_runtime.value
DEFAULT_CURSOR_STARTUP_TIMEOUT_SECONDS = float(_RUNTIME_POLICY.startup_timeout_seconds)


def resolve_cursor_startup_timeout_seconds(
    value: object | None = None,
) -> float:
    raw = value
    try:
        seconds = (
            float(raw)
            if raw not in (None, "")
            else float(active_runtime_policy().startup_timeout_seconds)
        )
    except (TypeError, ValueError):
        raise ValueError("cursor startup timeout must be numeric") from None
    return max(1.0, seconds)


def _redact_secret_text(
    value: str,
    *,
    secrets: Iterable[str | None] = (),
) -> str:
    """Redact resolved credentials before retaining any runtime diagnostics."""
    text = str(value or "")
    for secret in secrets:
        if secret:
            text = text.replace(str(secret), "<redacted-cursor-key>")
    return re.sub(r"crsr_[A-Za-z0-9_-]+", "<redacted-cursor-key>", text)


def _redact_secret_value(value, *, secrets: Iterable[str | None] = ()):
    if isinstance(value, dict):
        return {
            _redact_secret_text(str(k), secrets=secrets): _redact_secret_value(
                v,
                secrets=secrets,
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_secret_value(item, secrets=secrets) for item in value]
    if isinstance(value, str):
        return _redact_secret_text(value, secrets=secrets)
    return value


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


DATA_VENV_PYTHON = _venv_python(DATA_VENV_CACHE_DIR)


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
    paths.append(DATA_VENV_PYTHON)
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
    if len(args) >= 2 and args[:2] == ["task", "execute"]:
        return True
    if len(args) >= 2 and args[:2] == ["verify", "homepage-draft"]:
        return True
    if len(args) >= 2 and args[:2] == ["governance", "media-probe"]:
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
            "run `python3 quwoquan_data/scripts/cli.py task preflight` first.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    env = os.environ.copy()
    env[BOOTSTRAP_ENV] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    os.execvpe(str(python), [str(python), *argv], env)


def prepare_data_runtime_cache(
    *,
    python: Path | None = None,
    requirements: Path | None = None,
    cache_dir: Path | None = None,
) -> dict:
    """Rebuild an optional tool cache solely from repository-owned requirements."""
    target_cache_dir = cache_dir or DATA_VENV_CACHE_DIR
    venv_python = python or _venv_python(target_cache_dir)
    requirements_path = requirements or REQUIREMENTS_PATH
    if not requirements_path.is_file():
        raise RuntimeError(f"requirements file missing: {requirements_path}")
    if not venv_python.is_file():
        venv.create(target_cache_dir, with_pip=True)
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
        "toolCache": str(target_cache_dir),
        "sourceTruth": str(requirements_path),
        "cachePersistenceRequired": False,
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
        "schema": "quwoquan_data.python_runtime",
        "currentPython": str(current),
        "requirements": str(REQUIREMENTS_PATH),
        "agentModules": list(AGENT_RUNTIME_MODULES),
        "agentBinaries": list(AGENT_RUNTIME_BINARIES),
        "resolvedPython": str(resolved) if resolved else None,
        "ready": resolved is not None,
        "candidates": rows,
    }

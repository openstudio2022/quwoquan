"""stackctl 受管 Python cache、入口重执行与依赖前置检查。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parents[3]
OPS_REQUIREMENTS_PATH = ROOT / "quwoquan_ops" / "requirements.txt"
OPS_REQUIRED_MODULES = ("yaml", "jsonschema", "pydantic", "psycopg", "redis", "docker", "pymongo")
OPS_BOOTSTRAP_ENV = "QWQ_STACKCTL_OPS_BOOTSTRAPPED"
DEFAULT_PYTHON_CACHE_ROOT = (
    Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    / "quwoquan"
    / "python-envs"
)


def _python_cache_root() -> Path:
    candidate = Path(
        os.environ.get("QWQ_PYTHON_CACHE_ROOT") or DEFAULT_PYTHON_CACHE_ROOT
    ).expanduser().resolve()
    try:
        candidate.relative_to((ROOT / ".qwq_output").resolve())
    except ValueError:
        return candidate
    raise RuntimeError("STACKCTL_MANAGED_PYTHON_CACHE_INSIDE_OUTPUT")


def ops_venv_dir() -> Path:
    return _python_cache_root() / "quwoquan-ops"


def ops_venv_python() -> Path:
    suffix = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    return ops_venv_dir() / suffix


def managed_stackctl_python_executable(executable: str | None = None) -> str:
    """校验并保留 venv Python lexical path，真实目标只用于安全校验。"""
    path = Path(sys.executable if executable is None else executable)
    if not path.is_absolute():
        raise RuntimeError("STACKCTL_MANAGED_PYTHON_RELATIVE")
    try:
        lexical = path.lstat()
        target = path.stat()
    except OSError as exc:
        raise RuntimeError("STACKCTL_MANAGED_PYTHON_UNAVAILABLE") from exc
    trusted_uids = {0, os.geteuid()}
    if (
        not stat.S_ISREG(target.st_mode)
        or not os.access(path, os.X_OK)
        or lexical.st_uid not in trusted_uids
        or target.st_uid not in trusted_uids
        or target.st_mode & 0o022
    ):
        raise RuntimeError("STACKCTL_MANAGED_PYTHON_UNSAFE_EXECUTABLE")
    try:
        resolved_target = path.resolve(strict=True)
    except OSError as exc:
        raise RuntimeError("STACKCTL_MANAGED_PYTHON_UNAVAILABLE") from exc
    checked_parents: set[Path] = set()
    for parent in (*path.parents, *resolved_target.parents):
        if parent in checked_parents:
            continue
        checked_parents.add(parent)
        try:
            metadata = parent.stat()
        except OSError as exc:
            raise RuntimeError("STACKCTL_MANAGED_PYTHON_UNSAFE_BOUNDARY") from exc
        writable_by_others = bool(metadata.st_mode & 0o022)
        sticky_shared_root = bool(metadata.st_mode & stat.S_ISVTX) and metadata.st_uid == 0
        untrusted_writable = writable_by_others and metadata.st_uid != os.geteuid() and not sticky_shared_root
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid not in trusted_uids
            or untrusted_writable
        ):
            raise RuntimeError("STACKCTL_MANAGED_PYTHON_UNSAFE_BOUNDARY")
    return str(path)


def _preflight_code() -> str:
    return (
        "import json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        + "\n".join(f"import {name}" for name in OPS_REQUIRED_MODULES)
        + "\nfrom quwoquan_ops.cli.lib.generated.post_safety_runtime import PostSafetyDeploymentStartupMaterial\n"
        + "PostSafetyDeploymentStartupMaterial.model_json_schema()\n"
        + "print(json.dumps({'ready': True}))\n"
    )


def preflight_ops_python(python: Path | None = None) -> tuple[bool, list[str]]:
    candidate = python or ops_venv_python()
    if not candidate.is_file():
        return False, [f"managed interpreter missing: {candidate}"]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    proc = subprocess.run(
        [str(candidate), "-I", "-B", "-c", _preflight_code(), str(ROOT)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
        return True, []
    detail = (proc.stderr or proc.stdout or "Ops dependency preflight failed").strip()
    return False, [detail[-2000:]]


def prepare_ops_runtime_cache() -> dict[str, object]:
    python = ops_venv_python()
    if not OPS_REQUIREMENTS_PATH.is_file():
        raise RuntimeError(f"requirements file missing: {OPS_REQUIREMENTS_PATH}")
    if not python.is_file():
        venv.create(ops_venv_dir(), with_pip=True)
    proc = subprocess.run(
        [str(python), "-m", "pip", "install", "-r", str(OPS_REQUIREMENTS_PATH)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    ready, missing = preflight_ops_python(python)
    return {
        "python": str(python),
        "requirements": str(OPS_REQUIREMENTS_PATH),
        "toolCache": str(ops_venv_dir()),
        "installReturnCode": proc.returncode,
        "ready": proc.returncode == 0 and ready,
        "missing": missing,
        "stdoutTail": (proc.stdout or "")[-2000:],
        "stderrTail": (proc.stderr or "")[-2000:],
    }


def ensure_managed_stackctl_runtime(argv: list[str]) -> None:
    """在加载命令图及任何基础设施 mutation 前进入并验证 Ops venv。"""
    expected = ops_venv_python()
    current = Path(sys.executable)
    if current.absolute() == expected.absolute():
        managed_stackctl_python_executable(str(current))
        ready, missing = preflight_ops_python(current)
        if not ready:
            raise RuntimeError("STACKCTL_OPS_PREFLIGHT_FAILED: " + "; ".join(missing))
        os.environ["QWQ_STACKCTL_PYTHON"] = str(current)
        return
    if os.environ.get(OPS_BOOTSTRAP_ENV) == "1":
        raise RuntimeError("STACKCTL_MANAGED_PYTHON_REEXEC_LOOP")
    managed = managed_stackctl_python_executable(str(expected))
    ready, missing = preflight_ops_python(expected)
    if not ready:
        raise RuntimeError("STACKCTL_OPS_PREFLIGHT_FAILED: " + "; ".join(missing))
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment[OPS_BOOTSTRAP_ENV] = "1"
    environment["QWQ_STACKCTL_PYTHON"] = managed
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    os.execve(managed, [managed, "-B", *argv], environment)


def bind_managed_stackctl_python(environment: dict[str, str]) -> None:
    """以当前已受管 stackctl executable 覆盖任何 ambient caller 值。"""
    environment["QWQ_STACKCTL_PYTHON"] = managed_stackctl_python_executable()

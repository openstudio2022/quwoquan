"""物理树枚举与 Python 治理边界分类。"""
from __future__ import annotations

import os
import shutil
import subprocess
from fnmatch import fnmatch
from pathlib import Path
from typing import Sequence

from .constants import (
    ACCEPTANCE_ROOT,
    FORBIDDEN_CACHE_DIR_NAMES,
    OPS_MANAGED_ROOTS,
    PYTHON_SCOPE_ROOTS,
    RIPGREP_EXCLUDED_GLOBS,
    SCRIPT_SUFFIXES,
    TRAVERSAL_IGNORED_DIR_NAMES,
)
from .models import PythonFileRecord, relative_path


def script_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file()
        and candidate.suffix in SCRIPT_SUFFIXES
        and "__pycache__" not in candidate.parts
    )


def enumerate_scripts(root: Path, scope: str) -> list[Path]:
    if scope == "app":
        return script_files(root / "quwoquan_app/scripts")
    if scope == "service":
        return script_files(root / "quwoquan_service/scripts")
    if scope == "data":
        return script_files(root / "quwoquan_data/scripts")
    if scope == "ops":
        paths: set[Path] = set()
        for relative in OPS_MANAGED_ROOTS:
            paths.update(script_files(root / "quwoquan_ops" / relative))
        paths.update(script_files(root / ACCEPTANCE_ROOT))
        return sorted(paths)
    raise ValueError(f"unsupported scope: {scope}")


def ripgrep_files(
    root: Path,
    *,
    include_globs: Sequence[str],
    no_ignore: bool = False,
) -> list[Path]:
    if not root.is_dir():
        return []
    ripgrep = shutil.which("rg")
    if ripgrep is None:
        return _walk_files(root, include_globs=include_globs)
    command = [ripgrep, "--files", "--hidden"]
    if no_ignore:
        command.append("--no-ignore")
    for pattern in (*include_globs, *RIPGREP_EXCLUDED_GLOBS):
        command.extend(("--glob", pattern))
    command.append(str(root))
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in {0, 1}:
        raise RuntimeError(
            f"unable to enumerate Python governance files under {root}: "
            f"{completed.stderr.strip()}"
        )
    return sorted(
        Path(line)
        for line in completed.stdout.splitlines()
        if line.strip()
    )


def _walk_files(root: Path, *, include_globs: Sequence[str]) -> list[Path]:
    """Mirror the governed ``rg --files`` projection when rg is unavailable."""
    positive_globs = tuple(
        pattern for pattern in include_globs if not pattern.startswith("!")
    )
    files: list[Path] = []
    for directory, child_directories, names in os.walk(root, followlinks=False):
        child_directories[:] = sorted(
            name
            for name in child_directories
            if name not in TRAVERSAL_IGNORED_DIR_NAMES
        )
        for name in sorted(names):
            candidate = Path(directory) / name
            relative = candidate.relative_to(root)
            relative_text = relative.as_posix()
            if positive_globs and not any(
                relative.match(pattern)
                or fnmatch(relative_text, pattern)
                or fnmatch(name, pattern)
                for pattern in positive_globs
            ):
                continue
            files.append(candidate)
    return sorted(files)


def enumerate_python_files(root: Path, scope: str) -> list[Path]:
    return [
        path
        for path in ripgrep_files(
            root / PYTHON_SCOPE_ROOTS[scope],
            include_globs=("*.py",),
            no_ignore=True,
        )
        if not any(
            part in FORBIDDEN_CACHE_DIR_NAMES for part in path.parts
        )
    ]


def python_boundary(
    root: Path,
    scope: str,
    path: Path,
    managed_scripts: set[Path],
) -> str:
    if path in managed_scripts:
        return "managed_script"
    local = path.relative_to(root / PYTHON_SCOPE_ROOTS[scope])
    parts = local.parts
    if "vendor" in parts:
        return "vendor"
    if (
        "generated" in parts
        or "ephemeral" in parts
        or path.name.endswith((".g.py", "_generated.py"))
    ):
        return "generated"
    test_segment = "test" if scope == "app" else "tests"
    if test_segment in parts:
        if "support" in parts or path.name in {"conftest.py", "__init__.py"}:
            return "test_support"
        return "test_evidence"
    if scope == "service" and parts and parts[0] in {
        "contracts",
        "services",
        "runtime",
        "internal",
        "control-plane",
        "tools",
    }:
        return "production_module"
    if scope == "app" and parts and parts[0] in {"tool"}:
        return "production_module"
    if scope == "ops" and path.name == "__init__.py":
        return "production_module"
    return "unknown"


def python_file_records(
    root: Path,
    scopes: Sequence[str],
    scripts_by_scope: dict[str, list[Path]],
) -> list[PythonFileRecord]:
    records: list[PythonFileRecord] = []
    for scope in scopes:
        managed = {
            path.resolve()
            for path in scripts_by_scope.get(scope, ())
            if path.suffix == ".py"
        }
        for path in enumerate_python_files(root, scope):
            records.append(
                PythonFileRecord(
                    path=relative_path(root, path),
                    scope=scope,
                    boundary=python_boundary(root, scope, path.resolve(), managed),
                )
            )
    return records

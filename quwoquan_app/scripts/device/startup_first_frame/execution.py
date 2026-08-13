"""子进程执行与构建溯源辅助（run / sha256 / git provenance）。"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any


def run(
    cmd: list[str],
    *,
    check: bool = True,
    timeout: float | None = None,
    stdout: Any = subprocess.PIPE,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=stdout,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_provenance() -> dict[str, Any]:
    revision = run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        timeout=15,
    )
    dirty = run(
        ["git", "status", "--porcelain"],
        check=False,
        timeout=15,
    )
    return {
        "revision": revision.stdout.strip() if revision.returncode == 0 else "unknown",
        "workspaceDirty": bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
    }

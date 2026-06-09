"""Subprocess helpers for qwq-app CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_checked(
    args: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=capture,
    )

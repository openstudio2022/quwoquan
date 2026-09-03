"""Verify public CLI imports no retired orchestration family."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from core import paths

PUBLIC_COMMANDS = ("task", "filter-catalog", "release", "ship", "template", "verify")
FORBIDDEN_TOKENS = (
    "content.execution.controller", "content.execution.queue", "content.execution.campaign",
    "content.execution.planning", "content.execution.closure", "source-pool",
    "publish-execution", "semantic-wave", "pool-precheck", "pool-inspect",
)


def issues() -> list[str]:
    found: list[str] = []
    for command in PUBLIC_COMMANDS:
        result = subprocess.run(
            [sys.executable, "-B", "quwoquan_data/scripts/cli.py", command, "--help"],
            cwd=paths.REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr
        if result.returncode:
            found.append(f"{command}: help import failed: {output.strip()}")
        for token in FORBIDDEN_TOKENS:
            if token in output:
                found.append(f"{command}: retired token remains visible: {token}")
    return found


def main(argv: list[str] | None = None) -> int:
    del argv
    found = issues()
    if found:
        print("[verify public-cli-live-import-zero] FAIL")
        for item in found: print(f"  - {item}")
        return 1
    print("[verify public-cli-live-import-zero] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

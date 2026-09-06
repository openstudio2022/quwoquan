"""Verify public CLI imports no retired orchestration family."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from core import paths

PUBLIC_COMMANDS = ("task", "filter-catalog", "release", "ship", "template", "verify", "governance")
GOVERNANCE_HELP_SURFACES = (("governance",), ("governance", "coverage"))
FORBIDDEN_TOKENS = (
    "content.execution.controller", "content.execution.queue", "content.execution.campaign",
    "content.execution.planning", "content.execution.closure", "source-pool",
    "publish-execution", "semantic-wave", "pool-precheck", "pool-inspect",
    "workstream-baseline", "output-layout-migration", "discover", "source-ready",
    "maturity", "benchmark", "worker", "resume", "checkpoint", "saturation",
)


def issues() -> list[str]:
    found: list[str] = []
    surfaces = [(command,) for command in PUBLIC_COMMANDS]
    surfaces.extend(GOVERNANCE_HELP_SURFACES)
    for surface in surfaces:
        label = " ".join(surface)
        result = subprocess.run(
            [sys.executable, "-B", "quwoquan_data/scripts/cli.py", *surface, "--help"],
            cwd=paths.REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr
        if result.returncode:
            found.append(f"{label}: help import failed: {output.strip()}")
        for token in FORBIDDEN_TOKENS:
            if token in output:
                found.append(f"{label}: retired token remains visible: {token}")
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

"""Preflight guard for data verification.

Full data gates must run against a quiet workspace. Long-running data workflow
processes can legitimately write runtime/publish evidence while tests are
running, which would make isolation gates report misleading leaks. This guard
blocks early and asks the operator to rerun after the active runtime exits.
"""
from __future__ import annotations

import subprocess
import shlex
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_CLI_MARKERS = (
    "quwoquan_data/scripts/cli.py",
    str(REPO_ROOT / "quwoquan_data" / "scripts" / "cli.py"),
)
ACTIVE_COMMAND_MARKERS = (
    " task execute ",
    " task scaled-e2e run ",
)


def _process_lines() -> list[str]:
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _process_worktree_root(pid: str) -> Path | None:
    """Resolve a runtime process's Git worktree without trusting its argv."""
    try:
        cwd_probe = subprocess.run(
            ["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    cwd = next(
        (
            line[1:]
            for line in cwd_probe.stdout.splitlines()
            if line.startswith("n") and line[1:]
        ),
        "",
    )
    if not cwd:
        return None
    try:
        root_probe = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(root_probe.stdout.strip()).resolve()
    except (OSError, subprocess.CalledProcessError):
        return None


def active_runtime_processes(process_lines: list[str] | None = None) -> list[str]:
    supplied_lines = process_lines is not None
    lines = process_lines if process_lines is not None else _process_lines()
    active: list[str] = []
    for line in lines:
        if "verify_no_active_data_runtime.py" in line:
            continue
        _pid, _separator, command = line.partition(" ")
        try:
            argv = shlex.split(command)
        except ValueError:
            continue
        if not argv or not Path(argv[0]).name.lower().startswith("python"):
            continue
        if not any(argument.endswith("scripts/cli.py") for argument in argv[1:]):
            continue
        if not any(
            tuple(argv[index : index + 2]) == ("task", "execute")
            or tuple(argv[index : index + 3]) == ("task", "scaled-e2e", "run")
            for index in range(len(argv))
        ):
            continue
        # Full gates only require the *current* worktree to be quiet. Other
        # detached campaign worktrees may legitimately generate in parallel.
        if not supplied_lines:
            worktree_root = _process_worktree_root(_pid)
            if worktree_root is not None and worktree_root != REPO_ROOT.resolve():
                continue
        active.append(line)
    return active


def main() -> int:
    active = active_runtime_processes()
    if active:
        print("GATE_BLOCK verify_no_active_data_runtime:")
        for line in active[:10]:
            print(f"  - {line}")
        if len(active) > 10:
            print(f"  - ... {len(active) - 10} more")
        print("Rerun data/repo gate after active data runtime processes exit.")
        return 1
    print("[verify_no_active_data_runtime] OK")
    return 0

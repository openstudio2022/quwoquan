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
RETIRED_RUNTIME_SCRIPTS = frozenset(
    {
        "defend_video_m100.py",
        "run_video_m100_supervisor.py",
    }
)
RETIRED_LAUNCH_AGENT_NAMES = frozenset(
    {
        "com.local.dev.rtq-cp-guard.plist",
        "com.local.dev.rtq-cp-watch.plist",
    }
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


def _argument_uses_retired_output(argument: str) -> bool:
    """Recognize a real path under any checkout's retired Data output root."""

    value = str(argument or "").split("=", 1)[-1].strip().strip("'\"")
    if not value:
        return False
    parts = Path(value).parts
    return any(
        parts[index : index + 2] == ("quwoquan_data", ".qwq_output")
        for index in range(max(0, len(parts) - 1))
    )


def _is_retired_runtime_command(argv: list[str]) -> bool:
    if not argv:
        return False
    executable = Path(argv[0]).name.lower()
    supported = (
        executable.startswith("python")
        or executable == "mongod"
        or executable.startswith("redis-server")
    )
    if not supported:
        return False
    return any(Path(argument).name in RETIRED_RUNTIME_SCRIPTS for argument in argv[1:]) or any(
        _argument_uses_retired_output(argument) for argument in argv[1:]
    )


def retired_launch_agents(home: Path | None = None) -> list[str]:
    """Return launch agents capable of reviving a retired Data runtime."""

    root = (home or Path.home()) / "Library" / "LaunchAgents"
    if not root.is_dir():
        return []
    out: list[str] = []
    for path in sorted(root.glob("*.plist")):
        try:
            payload = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if (
            path.name in RETIRED_LAUNCH_AGENT_NAMES
            or "quwoquan_data/.qwq_output" in payload
        ):
            out.append(str(path))
    return out


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
        retired_runtime = _is_retired_runtime_command(argv)
        data_cli_runtime = (
            bool(argv)
            and Path(argv[0]).name.lower().startswith("python")
            and any(argument.endswith("scripts/cli.py") for argument in argv[1:])
            and any(
            tuple(argv[index : index + 2]) == ("task", "execute")
            or tuple(argv[index : index + 3]) == ("task", "scaled-e2e", "run")
            for index in range(len(argv))
            )
        )
        if not retired_runtime and not data_cli_runtime:
            continue
        # Full gates only require the *current* worktree to be quiet. Other
        # detached campaign worktrees may legitimately generate in parallel.
        if not supplied_lines and data_cli_runtime and not retired_runtime:
            worktree_root = _process_worktree_root(_pid)
            if worktree_root is not None and worktree_root != REPO_ROOT.resolve():
                continue
        active.append(line)
    return active


def main() -> int:
    active = active_runtime_processes()
    launch_agents = retired_launch_agents()
    if active or launch_agents:
        print("GATE_BLOCK verify_no_active_data_runtime:")
        for line in active[:10]:
            print(f"  - {line}")
        if len(active) > 10:
            print(f"  - ... {len(active) - 10} more")
        for path in launch_agents[:10]:
            print(f"  - retired launch agent: {path}")
        if len(launch_agents) > 10:
            print(f"  - ... {len(launch_agents) - 10} more launch agents")
        print("Rerun data/repo gate after active data runtime processes exit.")
        return 1
    print("[verify_no_active_data_runtime] OK")
    return 0

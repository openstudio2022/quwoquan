"""Explicit deletion of one inactive, disposable execution work package."""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from core import paths as core_paths
from core.controller_lease import active_controller_issue

from content.execution.identity import validate_execution_id
from content.execution.workspace import (
    archive_frozen_target_set,
    execution_root,
    transaction_workspace_root,
)
from content.release.canonical.garbage_collection import (
    release_identity_incident_protected_execution_ids,
)
from content.release.canonical.release_identity_incident import (
    release_identity_protection_lock,
)


def _is_task_execute_command(command: str, execution_id: str) -> bool:
    """Match the actual CLI process boundary, never a shell command string."""

    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    try:
        cli_index = next(
            index
            for index, argument in enumerate(argv)
            if argument.endswith("quwoquan_data/scripts/cli.py")
        )
    except StopIteration:
        return False
    command_args = argv[cli_index + 1 :]
    if len(command_args) < 3 or command_args[:2] != ["task", "execute"]:
        return False
    for index, argument in enumerate(command_args[2:]):
        if argument == "--execution-id" and index + 3 < len(command_args):
            return command_args[index + 3] == execution_id
        if argument == f"--execution-id={execution_id}":
            return True
    return False


def _active_execution_processes(execution_id: str) -> tuple[str, ...]:
    """Return live CLI controllers for exactly one execution identity."""

    process = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode:
        raise RuntimeError("unable to inspect active data controllers before discard")
    rows: list[tuple[int, int, str]] = []
    for line in process.stdout.splitlines():
        fields = line.strip().split(maxsplit=2)
        if len(fields) != 3:
            continue
        try:
            rows.append((int(fields[0]), int(fields[1]), fields[2]))
        except ValueError:
            continue
    parents = {pid: parent_pid for pid, parent_pid, _command in rows}
    own_ancestry: set[int] = set()
    pid = os.getpid()
    while pid > 0 and pid not in own_ancestry:
        own_ancestry.add(pid)
        pid = parents.get(pid, 0)
    return tuple(
        f"{pid} {command}"
        for pid, _parent_pid, command in rows
        if pid not in own_ancestry and _is_task_execute_command(command, execution_id)
    )


def discard_execution(
    execution_id: str,
    *,
    output_root: Path | None = None,
) -> None:
    """Delete only an inactive execution and its derived transaction workspace."""

    normalized_id = validate_execution_id(execution_id)
    root = execution_root(normalized_id)
    if not root.is_dir():
        raise FileNotFoundError(f"execution output does not exist: {normalized_id}")
    selected_output_root = (output_root or core_paths.OUTPUT_ROOT).resolve()
    with release_identity_protection_lock(
        output_root=selected_output_root,
        exclusive=True,
    ):
        protected_ids = release_identity_incident_protected_execution_ids(
            selected_output_root
        )
        if normalized_id in protected_ids:
            raise RuntimeError(
                "GATE_BLOCK DATA.EXECUTION.IDENTITY_INCIDENT_PROTECTED: "
                f"executionId={normalized_id} is protected by append-only "
                "release identity incident evidence"
            )
        lease_issue = active_controller_issue(normalized_id)
        if lease_issue:
            raise RuntimeError(lease_issue)
        active_processes = _active_execution_processes(normalized_id)
        if active_processes:
            raise RuntimeError(
                "GATE_BLOCK active task execute process owns execution: "
                + "; ".join(active_processes)
            )
        archive_frozen_target_set(normalized_id)
        if (root / "evidence" / "reliabletask").is_dir():
            from content.execution.reliabletask_fleet import (
                discard_reliabletask_execution,
            )

            discard_reliabletask_execution(normalized_id)
        shutil.rmtree(root)
        transaction_root = transaction_workspace_root()
        if transaction_root.is_dir():
            for candidate in transaction_root.glob(f"{normalized_id}--*"):
                if candidate.is_dir():
                    shutil.rmtree(candidate)


def handle_discard(args: argparse.Namespace) -> None:
    execution_id = str(getattr(args, "execution_id", "") or "").strip()
    try:
        discard_execution(execution_id)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"[task discard] GATE_BLOCK {exc}") from exc
    print(f"[task discard] removed executionId={execution_id}")


def register_task_discard_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "discard",
        help="删除一个无活跃 controller 的可重跑 execution 输出",
    )
    parser.add_argument("--execution-id", required=True, help="要删除的 executionId")
    parser.set_defaults(handler=handle_discard)


__all__ = ["discard_execution", "register_task_discard_parser"]

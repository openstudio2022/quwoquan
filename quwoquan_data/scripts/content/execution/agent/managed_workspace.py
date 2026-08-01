"""Managed-local workspace locking and bridge cleanup."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from content.execution.context import (
    ExecutionContext,
    load_execution_state,
    save_execution_state,
)
from content.execution import store


def managed_local_workspace_lock_path(workspace: str) -> Path:
    digest = hashlib.sha256(workspace.encode("utf-8")).hexdigest()[:16]
    root = Path(os.environ.get("QWQ_MANAGED_LOCAL_LOCK_DIR", tempfile.gettempdir()))
    return root / f"qwq-managed-local-{digest}.lock"


@contextmanager
def managed_local_workspace_guard(ctx: ExecutionContext):
    from content.execution.agent.agent_conflicts import (
        _cleanup_managed_local_workspace_conflicts,
        _cross_task_managed_data_cli_conflicts,
        _managed_local_workspace_conflicts,
        _managed_workspace_conflicts_for_provider,
    )

    if not ctx.managed or str(ctx.runtime) != "local":
        yield
        return
    try:
        import fcntl  # type: ignore
    except Exception:  # noqa: BLE001
        yield
        return
    workspace = str(Path.cwd())
    lock_path = managed_local_workspace_lock_path(workspace)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.seek(0)
            owner = lock_file.read().strip()
            raise RuntimeError(
                "another managed-local execution is already running in this workspace"
                + (f" ({owner})" if owner else "")
            ) from exc
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "executionId": ctx.execution_id,
                    "startedAt": store.now_iso(),
                },
                ensure_ascii=False,
            )
        )
        lock_file.flush()
        try:
            conflicts = _managed_workspace_conflicts_for_provider(
                _managed_local_workspace_conflicts(Path.cwd()),
                ctx.agent_provider,
            )
            if conflicts and ctx.force_clean_workspace_agent_state:
                cross_task_conflicts = _cross_task_managed_data_cli_conflicts(
                    conflicts,
                    execution_id=ctx.execution_id,
                )
                cleanup_reports: list[dict[str, Any]] = []
                if cross_task_conflicts:
                    cleanup_reports.append(
                        {
                            "schema": "quwoquan_data.managed_workspace_cleanup",
                            "mode": "force_clean_workspace_agent_state_observed_cross_task_after_lock",
                            "requestedConflictCount": len(conflicts),
                            "crossTaskConflictCount": len(cross_task_conflicts),
                            "conflicts": cross_task_conflicts[:20],
                        }
                    )
                    cross_task_pids = {
                        int(item.get("pid") or 0) for item in cross_task_conflicts
                    }
                    conflicts = [
                        item
                        for item in conflicts
                        if int(item.get("pid") or 0) not in cross_task_pids
                    ]
                if conflicts:
                    cleanup_reports.append(
                        _cleanup_managed_local_workspace_conflicts(conflicts)
                    )
                    conflicts = _managed_workspace_conflicts_for_provider(
                        _managed_local_workspace_conflicts(Path.cwd()),
                        ctx.agent_provider,
                    )
                    if cross_task_conflicts:
                        cross_task_pids = {
                            int(item.get("pid") or 0) for item in cross_task_conflicts
                        }
                        conflicts = [
                            item
                            for item in conflicts
                            if int(item.get("pid") or 0) not in cross_task_pids
                        ]
                state = load_execution_state(ctx.execution_id)
                reports = state.workspace_cleanup_reports
                if isinstance(reports, list):
                    reports.extend(cleanup_reports)
                    state.workspace_cleanup_reports = reports[-20:]
                    state.heartbeat_at = store.now_iso()
                    save_execution_state(state)
            if conflicts:
                rendered = "; ".join(
                    f"{item.get('kind')} pid={item.get('pid')} pgid={item.get('pgid')} "
                    f"cmd={redact_managed_secret(str(item.get('command') or ''))[:220]}"
                    for item in conflicts[:8]
                )
                raise RuntimeError(
                    "managed local workspace conflicts appeared after acquiring lock: "
                    + rendered
                )
            yield
        finally:
            lock_file.seek(0)
            lock_file.truncate()
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def terminate_workspace_cursor_bridges(workspace: Path) -> None:
    """Best-effort cleanup for half-started Cursor SDK bridges in this workspace."""
    from content.execution.agent.agent_worker import _terminate_pid_tree_if_alive

    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return
    workspace_text = str(workspace)
    current_pid = os.getpid()
    for line in proc.stdout.splitlines():
        if "cursor-sdk-bridge" not in line or workspace_text not in line:
            continue
        parts = line.strip().split(maxsplit=1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid <= 0 or pid == current_pid:
            continue
        _terminate_pid_tree_if_alive(pid)


def redact_managed_secret(text: str, *, api_key: str | None = None) -> str:
    """Redact the active key even when its provider format lacks a stable prefix."""
    try:
        from core.cursor_credentials import redact_cursor_api_key
    except Exception:  # noqa: BLE001
        from cursor_credentials import redact_cursor_api_key  # type: ignore
    text = redact_cursor_api_key(text, api_key=api_key)
    text = re.sub(r"crsr_[A-Za-z0-9_-]+", "<redacted-cursor-key>", text)
    return re.sub(
        r"(--tool-callback-auth-token\s+)[^\s]+",
        r"\1<redacted-token>",
        text,
    )

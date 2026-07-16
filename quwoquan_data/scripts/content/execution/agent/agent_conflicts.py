"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.support import Any, Mapping, Path, Sequence, _MANAGED_LOCAL_DATA_CLI_MARKERS, _MANAGED_LOCAL_DESTRUCTIVE_MARKERS, _normalize_managed_agent_provider, os, re, shlex, signal, store, time

def _managed_process_monitor_command(command: str) -> bool:
    stripped = command.strip()
    return (
        stripped.startswith("rg ")
        or " rg " in command
        or "| rg " in command
        or ("ps " in command and "rg " in command)
    )

def _process_in_workspace(process_cwd: str, workspace: Path, command: str = "") -> bool:
    workspace_path = workspace.resolve()
    command_text = str(command or "")
    # 路径边界感知匹配：workspace 文本后必须是路径分隔符/空白/引号/结尾，
    # 否则 /a/repo 会误命中兄弟 worktree /a/repo-wt-x 的进程并将其清场（互杀）。
    if re.search(re.escape(str(workspace_path)) + r"""(?=[/\s'"]|$)""", command_text):
        return True
    if not process_cwd:
        return False
    try:
        cwd_path = Path(process_cwd).resolve()
    except OSError:
        cwd_path = Path(process_cwd)
    return cwd_path == workspace_path or workspace_path in cwd_path.parents

def _cursor_bridge_workspace_from_command(command: str) -> str:
    try:
        parts = shlex.split(str(command or ""))
    except ValueError:
        parts = str(command or "").split()
    for index, part in enumerate(parts):
        if part == "--workspace" and index + 1 < len(parts):
            return parts[index + 1]
        if part.startswith("--workspace="):
            return part.split("=", 1)[1]
    return ""

def _managed_command_execution_id(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = str(command or "").split()
    execution_id = ""
    for index, part in enumerate(parts):
        if part == "--execution-id" and index + 1 < len(parts):
            execution_id = parts[index + 1]
        elif part.startswith("--execution-id="):
            execution_id = part.split("=", 1)[1]
    return str(execution_id or "")

def _cursor_bridge_in_workspace(command: str, process_cwd: str, workspace: Path) -> bool:
    bridge_workspace = _cursor_bridge_workspace_from_command(command)
    if bridge_workspace:
        return _process_in_workspace(bridge_workspace, workspace)
    return _process_in_workspace(process_cwd, workspace)

def _managed_local_workspace_conflicts(workspace: Path) -> list[dict[str, Any]]:
    """Find live same-workspace data jobs that can corrupt local Cursor runs.
    Local Cursor Agent execution is process- and workspace-sensitive: orphaned
    bridges and a second managed workflow in the same checkout can steal the
    bridge callback port or terminate each other's subprocesses.  Detect these
    before creating or resuming a managed batch so failures surface as preflight
    blockers instead of content-quality noise.
    """
    from content.execution.agent.agent_runner import _redact_managed_secret
    from content.execution.pipeline.preflight import _current_process_family_pids, _process_cwd, _process_rows
    rows = _process_rows()
    ignore_pids = _current_process_family_pids(rows)
    workspace_path = workspace.resolve()
    cwd_by_pid: dict[int, str] = {}
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        pid = int(row.get("pid") or 0)
        if pid <= 0 or pid in ignore_pids:
            continue
        command = str(row.get("command") or "")
        monitor_command = _managed_process_monitor_command(command)
        process_cwd = ""
        kind = ""
        if "cursor-sdk-bridge" in command:
            process_cwd = cwd_by_pid.setdefault(pid, _process_cwd(pid))
            if _cursor_bridge_in_workspace(command, process_cwd, workspace_path):
                kind = "cursor_sdk_bridge"
        elif (
            "_managed_agent_worker_main" in command
            and "from content.execution.agent.agent_worker import _managed_agent_worker_main" in command
        ):
            process_cwd = cwd_by_pid.setdefault(pid, _process_cwd(pid))
            if _process_in_workspace(process_cwd, workspace_path, command):
                kind = "managed_agent_worker"
        elif (
            not monitor_command
            and
            ("quwoquan_data/scripts/cli.py" in command or "scripts/cli.py" in command)
            and any(marker in command for marker in _MANAGED_LOCAL_DATA_CLI_MARKERS)
            and any(marker in command for marker in _MANAGED_LOCAL_DESTRUCTIVE_MARKERS)
        ):
            process_cwd = cwd_by_pid.setdefault(pid, _process_cwd(pid))
            if _process_in_workspace(process_cwd, workspace_path, command):
                kind = "destructive_data_cli"
        elif (
            not monitor_command
            and
            ("quwoquan_data/scripts/cli.py" in command or "scripts/cli.py" in command)
            and any(marker in command for marker in _MANAGED_LOCAL_DATA_CLI_MARKERS)
        ):
            process_cwd = cwd_by_pid.setdefault(pid, _process_cwd(pid))
            if _process_in_workspace(process_cwd, workspace_path, command):
                kind = "data_cli"
        if not kind:
            continue
        conflicts.append(
            {
                "kind": kind,
                "pid": pid,
                "ppid": int(row.get("ppid") or 0),
                "pgid": int(row.get("pgid") or 0),
                "cwd": process_cwd,
                "command": _redact_managed_secret(command),
            }
        )
    return conflicts

def _managed_workspace_conflicts_for_provider(
    conflicts: Sequence[Mapping[str, Any]],
    provider: str,
) -> list[dict[str, Any]]:
    normalized = _normalize_managed_agent_provider(provider)
    if normalized == "cursor_sdk":
        return [dict(item) for item in conflicts]
    return [
        dict(item)
        for item in conflicts
        if str(item.get("kind") or "") != "cursor_sdk_bridge"
    ]

def _cross_task_managed_data_cli_conflicts(
    conflicts: Sequence[Mapping[str, Any]],
    *,
    execution_id: str,
) -> list[dict[str, Any]]:
    current_execution_id = str(execution_id or "")
    out: list[dict[str, Any]] = []
    for item in conflicts:
        if str(item.get("kind") or "") not in {"data_cli", "managed_agent_worker"}:
            continue
        command = str(item.get("command") or "")
        observed_execution_id = _managed_command_execution_id(command)
        if observed_execution_id != current_execution_id:
            out.append(dict(item))
    return out

def _cleanup_managed_local_workspace_conflicts(
    conflicts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    from content.execution.agent.agent_worker import _terminate_pid_tree_if_alive
    from content.execution.pipeline.preflight import _current_process_family_pids
    report: dict[str, Any] = {
        "schemaVersion": "quwoquan_data.managed_workspace_cleanup",
        "mode": "force_clean_workspace_agent_state",
        "startedAt": store.now_iso(),
        "requestedConflictCount": len(conflicts),
        "terminated": [],
        "skipped": [],
    }
    current_family = _current_process_family_pids()
    current_pgid = os.getpgrp()
    terminated = report["terminated"]
    skipped = report["skipped"]
    seen_groups: set[int] = set()
    for item in conflicts:
        pid = int(item.get("pid") or 0)
        pgid = int(item.get("pgid") or 0)
        kind = str(item.get("kind") or "")
        row = {
            "kind": kind,
            "pid": pid,
            "pgid": pgid,
            "command": str(item.get("command") or ""),
        }
        if pid <= 0 or pid in current_family:
            skipped.append({**row, "reason": "current process family"})
            continue
        if pgid == current_pgid:
            # 同进程组禁止 killpg（会波及当前进程）。但 ppid=1 的 cursor bridge 是
            # 上游 runner 子进程退出后的孤儿（reparent 到 launchd 仍保留旧 pgid），
            # 不回收会让同组后续 managed preflight 永久 BLOCK（WP5 实测死锁）；
            # 按 pid 树精准回收，绝不触碰进程组。
            if int(item.get("ppid") or 0) == 1 and kind == "cursor_sdk_bridge":
                try:
                    _terminate_pid_tree_if_alive(pid)
                    terminated.append(
                        {**row, "signal": "SIGTERM/SIGKILL", "scope": "orphan_pid_tree_same_pgid"}
                    )
                except Exception as exc:  # noqa: BLE001
                    skipped.append({**row, "reason": f"terminate orphan bridge failed: {exc}"})
            else:
                skipped.append({**row, "reason": "current process group"})
            continue
        if kind in {"data_cli", "destructive_data_cli"} and pgid > 0 and pgid not in seen_groups:
            seen_groups.add(pgid)
            try:
                os.killpg(pgid, signal.SIGTERM)
                terminated.append({**row, "signal": "SIGTERM", "scope": "process_group"})
            except OSError as exc:
                skipped.append({**row, "reason": f"killpg failed: {exc}"})
            continue
        try:
            _terminate_pid_tree_if_alive(pid)
            terminated.append({**row, "signal": "SIGTERM/SIGKILL", "scope": "pid_tree"})
        except Exception as exc:  # noqa: BLE001
            skipped.append({**row, "reason": f"terminate pid tree failed: {exc}"})
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        remaining = _managed_local_workspace_conflicts(Path.cwd())
        remaining_pids = {int(item.get("pid") or 0) for item in remaining}
        target_pids = {int(item.get("pid") or 0) for item in conflicts}
        if not remaining_pids.intersection(target_pids):
            break
        time.sleep(0.25)
    report["finishedAt"] = store.now_iso()
    report["remainingConflicts"] = _managed_local_workspace_conflicts(Path.cwd())[:20]
    return report

"""Fixed OS and filesystem observations for runtime evidence sampling."""
from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.io import read_json

from content.execution.campaign.runtime import runtime_snapshot_path
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.runtime_evidence.contract import (
    ProcessInspector,
    ProcessObservation,
    RuntimeEvidenceError,
    RuntimeEvidenceIdentity,
    resolve_ref,
    safe_ref,
)


def _parse_time(value: object, *, label: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RuntimeEvidenceError(f"{label} must be RFC3339 date-time") from exc
    if parsed.tzinfo is None:
        raise RuntimeEvidenceError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


def _fixed_command(*argv: str, timeout_seconds: float) -> str:
    result = subprocess.run(
        list(argv), check=False, capture_output=True, text=True,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise RuntimeEvidenceError(
            f"fixed process inspection failed: {argv[0]} exit={result.returncode}"
        )
    return str(result.stdout or "").strip()


class SystemProcessInspector:
    def __init__(self, *, timeout_seconds: float) -> None:
        if timeout_seconds <= 0:
            raise ValueError("process inspection timeout must be positive")
        self._timeout_seconds = timeout_seconds

    def _ps(self, pid: int, field: str) -> str:
        return _fixed_command(
            "ps",
            "-p",
            str(pid),
            "-o",
            f"{field}=",
            timeout_seconds=self._timeout_seconds,
        )

    def _fd_count(self, pid: int) -> int:
        proc_fd = Path("/proc") / str(pid) / "fd"
        if proc_fd.is_dir():
            try:
                return sum(1 for _ in proc_fd.iterdir())
            except OSError as exc:
                raise RuntimeEvidenceError(f"cannot inspect process FDs: {pid}") from exc
        if sys.platform == "darwin":
            output = _fixed_command(
                "lsof",
                "-a",
                "-p",
                str(pid),
                "-Fn",
                timeout_seconds=self._timeout_seconds,
            )
            return sum(1 for line in output.splitlines() if line.startswith("f"))
        raise RuntimeEvidenceError("current platform has no governed FD inspector")

    def observe(self, pid: int) -> ProcessObservation:
        if pid < 2:
            raise RuntimeEvidenceError("process PID must be >= 2")
        try:
            os.kill(pid, 0)
        except (OSError, PermissionError) as exc:
            raise RuntimeEvidenceError(f"registered process is not alive: {pid}") from exc
        try:
            pgid = int(self._ps(pid, "pgid"))
            rss_bytes = int(self._ps(pid, "rss")) * 1024
            cpu_percent = float(self._ps(pid, "%cpu"))
        except ValueError as exc:
            raise RuntimeEvidenceError(f"process metrics are invalid: {pid}") from exc
        command = self._ps(pid, "command")
        start_token = self._ps(pid, "lstart")
        if not command or not start_token:
            raise RuntimeEvidenceError(f"process identity is incomplete: {pid}")
        return ProcessObservation(
            pid=pid,
            pgid=pgid,
            command=command,
            start_token=start_token,
            rss_bytes=rss_bytes,
            cpu_percent=cpu_percent,
            open_fd_count=self._fd_count(pid),
        )

    def observe_group(self, pgid: int) -> tuple[ProcessObservation, ...]:
        if pgid < 2:
            raise RuntimeEvidenceError("process group ID must be >= 2")
        output = _fixed_command(
            "ps",
            "-ax",
            "-o",
            "pid=",
            "-o",
            "pgid=",
            timeout_seconds=self._timeout_seconds,
        )
        pids: list[int] = []
        for line in output.splitlines():
            fields = line.split()
            if len(fields) != 2:
                raise RuntimeEvidenceError("process group inspection returned invalid rows")
            try:
                pid_value, pgid_value = (int(field) for field in fields)
            except ValueError as exc:
                raise RuntimeEvidenceError(
                    "process group inspection returned invalid identity"
                ) from exc
            if pgid_value == pgid:
                pids.append(pid_value)
        if not pids:
            raise RuntimeEvidenceError(f"registered process group is empty: {pgid}")
        if len(pids) != len(set(pids)):
            raise RuntimeEvidenceError(f"process group contains duplicate PIDs: {pgid}")
        return tuple(self.observe(pid) for pid in sorted(pids))


def process_measurements(
    session: Mapping[str, Any], inspector: ProcessInspector
) -> list[dict[str, Any]]:
    registrations = [session["controller"], *session["workers"]]
    rows: list[dict[str, Any]] = []
    owners_by_pid: dict[int, tuple[str, str | None, str]] = {}
    for registration in registrations:
        registered_pid = int(registration["pid"])
        pgid = int(registration["pgid"])
        observations = inspector.observe_group(pgid)
        leaders = [row for row in observations if row.pid == registered_pid]
        if len(leaders) != 1 or leaders[0].identity_digest != registration[
            "processIdentityDigest"
        ]:
            raise RuntimeEvidenceError(
                f"registered process identity changed: {registration['executionId']}"
            )
        owner = (
            str(registration["role"]),
            registration["carrier"],
            str(registration["executionId"]),
        )
        for observation in observations:
            if observation.pgid != pgid:
                raise RuntimeEvidenceError(
                    f"process escaped registered group: {observation.pid}/{pgid}"
                )
            prior = owners_by_pid.get(observation.pid)
            if prior is not None and prior != owner:
                raise RuntimeEvidenceError(
                    f"process belongs to multiple runtime owners: {observation.pid}"
                )
            if prior is not None:
                continue
            owners_by_pid[observation.pid] = owner
            rows.append(
                {
                    "role": registration["role"],
                    "carrier": registration["carrier"],
                    "executionId": registration["executionId"],
                    "registrationPid": registered_pid,
                    "isRegisteredProcess": observation.pid == registered_pid,
                    "pid": observation.pid,
                    "pgid": observation.pgid,
                    "processIdentityDigest": observation.identity_digest,
                    "rssBytes": observation.rss_bytes,
                    "cpuPercent": observation.cpu_percent,
                    "isCursorSdkBridge": "cursor-sdk-bridge" in observation.command,
                    "openFdCount": observation.open_fd_count,
                }
            )
    if len(owners_by_pid) != len(rows):
        raise RuntimeEvidenceError("runtime process measurements contain duplicate PIDs")
    return rows


def _directory_bytes(path: Path) -> int:
    if path.is_symlink() or not path.is_dir():
        raise RuntimeEvidenceError(f"registered workspace is missing or unsafe: {path}")
    total = 0
    for item in path.rglob("*"):
        if item.is_symlink():
            raise RuntimeEvidenceError(f"registered workspace contains symlink: {item}")
        if item.is_file():
            total += item.stat().st_size
    return total


def workspace_measurements(
    session: Mapping[str, Any], *, output_root: Path
) -> list[dict[str, Any]]:
    measured: dict[str, dict[str, Any]] = {}
    for worker in session["workers"]:
        ref = str(worker["workspaceRef"])
        path = resolve_ref(ref, output_root=output_root, require_file=False)
        measured[ref] = {
            "workspaceRef": ref,
            "kind": "execution",
            "bytes": _directory_bytes(path),
        }
        checkpoint = read_json(
            resolve_ref(str(worker["checkpointRef"]), output_root=output_root)
        )
        capsule_ref = str(checkpoint.get("capsuleRef") or "")
        capsule = resolve_ref(
            capsule_ref, output_root=output_root, require_file=False
        )
        measured[capsule_ref] = {
            "workspaceRef": capsule_ref,
            "kind": "capsule",
            "bytes": _directory_bytes(capsule),
        }
    transactions = output_root / "data/local/workspace/object-transactions"
    if transactions.is_dir() and not transactions.is_symlink():
        execution_ids = {str(row["executionId"]) for row in session["workers"]}
        for transaction in transactions.iterdir():
            if not transaction.is_dir() or transaction.is_symlink():
                continue
            if not any(transaction.name.startswith(f"{value}--") for value in execution_ids):
                continue
            staging = transaction / "staging"
            if not staging.is_dir():
                continue
            ref = safe_ref(staging, output_root=output_root, require_file=False)
            measured[ref] = {
                "workspaceRef": ref,
                "kind": "transaction_staging",
                "bytes": _directory_bytes(staging),
            }
    return [measured[key] for key in sorted(measured)]


def _worker_runtime_times(
    session: Mapping[str, Any], *, output_root: Path
) -> list[tuple[datetime, datetime]]:
    rows: list[tuple[datetime, datetime]] = []
    for worker in session["workers"]:
        root = resolve_ref(
            str(worker["workspaceRef"]), output_root=output_root, require_file=False
        )
        progress_times: list[datetime] = []
        heartbeat_times: list[datetime] = []
        for name in ("execution_progress.json", "execution_state.json"):
            path = root / "_shared" / name
            if not path.is_file() or path.is_symlink():
                continue
            payload = read_json(path)
            if not isinstance(payload, Mapping) or not payload.get("updatedAt"):
                continue
            updated = _parse_time(payload["updatedAt"], label=f"{name}.updatedAt")
            progress_times.append(updated)
            heartbeat_times.append(
                _parse_time(
                    payload.get("heartbeatAt") or payload["updatedAt"],
                    label=f"{name}.heartbeatAt",
                )
            )
        if not progress_times or not heartbeat_times:
            raise RuntimeEvidenceError(
                f"execution has no observable progress/heartbeat: {worker['executionId']}"
            )
        rows.append((max(progress_times), max(heartbeat_times)))
    return rows


def progress_and_heartbeat_age(
    session: Mapping[str, Any],
    *,
    runtime: CampaignRuntimePaths,
    identity: RuntimeEvidenceIdentity,
    now: datetime,
) -> tuple[int, int]:
    runtime_times = _worker_runtime_times(session, output_root=runtime.output_root)
    progress_age = max(max(0, int((now - row[0]).total_seconds())) for row in runtime_times)
    snapshot = read_json(runtime_snapshot_path(runtime, identity.root_execution_id))
    controller_heartbeat = _parse_time(
        snapshot.get("heartbeatAt"), label="campaign heartbeat"
    )
    heartbeat_times = [controller_heartbeat, *(row[1] for row in runtime_times)]
    heartbeat_age = max(max(0, int((now - value).total_seconds())) for value in heartbeat_times)
    return progress_age, heartbeat_age


__all__ = [
    "SystemProcessInspector",
    "process_measurements",
    "progress_and_heartbeat_age",
    "workspace_measurements",
]

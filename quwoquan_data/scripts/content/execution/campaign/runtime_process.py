"""Identity-safe cleanup for orphaned campaign lane process groups."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import socket
import subprocess
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.io import read_json, write_json


class CampaignControllerTerminated(RuntimeError):
    """SIGTERM reached the controller and must unwind owned lane processes."""

    def __init__(self, signum: int) -> None:
        super().__init__(
            "DATA.CAMPAIGN.CONTROLLER_TERMINATED "
            f"signal={signal.Signals(signum).name}"
        )
        self.signum = signum


class CampaignLeaseTakeoverError(RuntimeError):
    """A live-stall takeover could not prove the exact stale controller owner."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code} {detail}")


@dataclass(frozen=True, slots=True)
class CampaignControllerTermination:
    pid: int
    pgid: int
    root_execution_id: str
    run_id: str
    generation: int
    fencing_token: str
    process_identity: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def campaign_snapshot_guard(
    path: Path,
    *,
    timeout_seconds: float | None = None,
) -> Iterator[None]:
    """Serialize heartbeat writes with a prospective live-stall takeover."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        if timeout_seconds is None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        else:
            deadline = time.monotonic() + timeout_seconds
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise CampaignLeaseTakeoverError(
                            "DATA.CAMPAIGN.TAKEOVER_SNAPSHOT_LOCKED",
                            "stale controller still owns the snapshot mutation guard",
                        ) from exc
                    time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def stale_takeover_candidate(
    snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if snapshot is None or snapshot.get("status") != "active":
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_RUNTIME_MISMATCH",
            "controller lock is busy without one active runtime snapshot",
        )
    heartbeat_at = str(snapshot.get("heartbeatAt") or "").strip()
    lease_seconds = snapshot.get("leaseSeconds")
    if (
        isinstance(lease_seconds, bool)
        or not isinstance(lease_seconds, int)
        or lease_seconds < 1
    ):
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_LEASE_INVALID",
            "active runtime leaseSeconds is invalid",
        )
    try:
        heartbeat = datetime.fromisoformat(heartbeat_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_LEASE_INVALID",
            "active runtime heartbeatAt is invalid",
        ) from exc
    if heartbeat.tzinfo is None:
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_LEASE_INVALID",
            "active runtime heartbeatAt must include timezone",
        )
    age_seconds = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    if age_seconds <= lease_seconds:
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.LEASE_ACTIVE",
            f"controller heartbeat age={age_seconds:.3f}s lease={lease_seconds}s",
        )
    return dict(snapshot)


def same_controller_identity(
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> bool:
    return all(
        expected.get(key) == observed.get(key)
        for key in (
            "rootExecutionId",
            "runId",
            "generation",
            "fencingToken",
            "hostname",
            "pid",
            "pgid",
            "controllerProcessIdentity",
        )
    )


def append_runtime_event(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(
            json.dumps(
                dict(payload),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_runtime_mapping(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise TypeError(f"campaign runtime document must be an object: {path}")
    return payload


def reconcile_stale_generation(
    *,
    runtime_root_path: Path,
    snapshot_path: Path,
    events_path: Path,
    root_execution_id: str,
    snapshot: Mapping[str, Any],
    process_termination_timeout_seconds: float,
    controller_termination: str | None,
    event_schema: str,
) -> None:
    run_id = str(snapshot.get("runId") or "")
    generation = int(snapshot.get("generation") or 0)
    reconciled_lanes: list[dict[str, Any]] = []
    lane_dir = runtime_root_path / "lanes"
    if lane_dir.is_dir():
        for path in sorted(lane_dir.glob("*.json")):
            checkpoint = _read_runtime_mapping(path)
            if not checkpoint:
                continue
            if (
                str(checkpoint.get("runId") or "") != run_id
                or int(checkpoint.get("generation") or 0) != generation
                or str(checkpoint.get("status") or "") not in {"starting", "running"}
            ):
                continue
            termination = terminate_lane_process(
                checkpoint,
                grace_seconds=process_termination_timeout_seconds,
            )
            updated = dict(checkpoint)
            updated.update(
                {
                    "status": "interrupted",
                    "error": "DATA.CAMPAIGN.STALE_GENERATION",
                    "termination": termination,
                    "updatedAt": _utc_now(),
                }
            )
            write_json(path, updated)
            reconciled_lanes.append(
                {
                    "carrier": str(updated.get("carrier") or path.stem),
                    "executionId": str(updated.get("executionId") or ""),
                    "termination": termination,
                }
            )
    interrupted = dict(snapshot)
    interrupted.update(
        {
            "status": "interrupted",
            "phase": "stale_reconciliation",
            "heartbeatAt": _utc_now(),
            "updatedAt": _utc_now(),
            "failure": "DATA.CAMPAIGN.STALE_GENERATION",
            "controllerTermination": controller_termination,
        }
    )
    with campaign_snapshot_guard(runtime_root_path / ".snapshot.lock"):
        write_json(snapshot_path, interrupted)
    append_runtime_event(
        events_path,
        {
            "schema": event_schema,
            "rootExecutionId": root_execution_id,
            "runId": run_id,
            "generation": generation,
            "eventType": "stale_generation_reconciled",
            "recordedAt": _utc_now(),
            "lanes": reconciled_lanes,
            "controllerTermination": controller_termination,
        },
    )


def new_campaign_run_identity(
    root_execution_id: str,
    generation: int,
) -> tuple[str, str]:
    seed = (
        f"{root_execution_id}|{generation}|{os.getpid()}|{socket.gethostname()}|"
        f"{datetime.now(timezone.utc).isoformat()}|{time.monotonic_ns()}"
    )
    run_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    fencing_seed = (
        f"{root_execution_id}|{run_id}|{generation}|campaign-runtime-v1"
    )
    token = "sha256:" + hashlib.sha256(fencing_seed.encode("utf-8")).hexdigest()
    return run_id, token


@contextmanager
def controller_signal_guard() -> Iterator[None]:
    """Turn SIGTERM into normal unwinding while preserving the caller handler."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.getsignal(signal.SIGTERM)

    def terminate(signum: int, _frame: object) -> None:
        raise CampaignControllerTerminated(signum)

    signal.signal(signal.SIGTERM, terminate)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def _pid_alive(pid: object) -> bool:
    try:
        value = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    state = subprocess.run(
        ["ps", "-p", str(value), "-o", "stat="],
        check=False,
        capture_output=True,
        text=True,
    )
    if state.returncode != 0:
        return False
    return not str(state.stdout or "").strip().startswith("Z")


def _process_command(pid: int) -> str:
    if pid <= 0:
        return ""
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        check=False,
        capture_output=True,
        text=True,
    )
    return str(result.stdout or "").strip() if result.returncode == 0 else ""


def _process_started_at(pid: int) -> str:
    if pid < 2:
        return ""
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        check=False,
        capture_output=True,
        text=True,
    )
    return " ".join(str(result.stdout or "").split()) if result.returncode == 0 else ""


def campaign_controller_process_identity(
    root_execution_id: str,
    *,
    run_id: str,
    generation: int,
    fencing_token: str,
    pid: int,
    pgid: int,
) -> str:
    """Bind one controller generation to an exact host process incarnation."""

    if pid < 2 or pgid < 2 or generation < 1:
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_IDENTITY_INVALID",
            "controller pid/pgid/generation is unsafe",
        )
    try:
        observed_pgid = os.getpgid(pid)
    except OSError as exc:
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_IDENTITY_UNAVAILABLE",
            f"controller process is unavailable pid={pid}",
        ) from exc
    command = _process_command(pid)
    started_at = _process_started_at(pid)
    if observed_pgid != pgid or not command or not started_at:
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_IDENTITY_MISMATCH",
            f"controller process facts drifted pid={pid} pgid={pgid}",
        )
    stable = {
        "hostname": socket.gethostname(),
        "pid": pid,
        "pgid": pgid,
        "startedAt": started_at,
        "commandSha256": hashlib.sha256(command.encode()).hexdigest(),
        "rootExecutionId": str(root_execution_id),
        "runId": str(run_id),
        "generation": generation,
        "fencingToken": str(fencing_token),
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def begin_stale_controller_termination(
    snapshot: Mapping[str, Any],
    *,
    root_execution_id: str,
) -> CampaignControllerTermination:
    """Validate and signal the exact isolated controller process group once."""

    try:
        pid = int(snapshot.get("pid") or 0)
        pgid = int(snapshot.get("pgid") or 0)
        generation = int(snapshot.get("generation") or 0)
    except (TypeError, ValueError) as exc:
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_IDENTITY_INVALID",
            "controller pid/pgid/generation is invalid",
        ) from exc
    run_id = str(snapshot.get("runId") or "").strip()
    fencing_token = str(snapshot.get("fencingToken") or "").strip()
    expected_identity = str(snapshot.get("controllerProcessIdentity") or "").strip()
    if (
        snapshot.get("rootExecutionId") != root_execution_id
        or not run_id
        or generation < 1
        or not fencing_token.startswith("sha256:")
        or len(fencing_token) != 71
        or not expected_identity.startswith("sha256:")
        or len(expected_identity) != 71
    ):
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_IDENTITY_INVALID",
            "controller runtime identity is incomplete",
        )
    if (
        pid < 2
        or pgid < 2
        or pid != pgid
        or pid == os.getpid()
        or pgid == os.getpgrp()
    ):
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_PROCESS_GROUP_UNSAFE",
            f"refusing controller process group pid={pid} pgid={pgid}",
        )
    if snapshot.get("hostname") != socket.gethostname() or not _pid_alive(pid):
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_IDENTITY_MISMATCH",
            "controller host or liveness no longer matches the snapshot",
        )
    command = _process_command(pid).replace("\\", "/")
    if "quwoquan_data/scripts/cli.py" not in command or root_execution_id not in command:
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_COMMAND_MISMATCH",
            "controller command does not name the canonical CLI and root execution",
        )
    observed_identity = campaign_controller_process_identity(
        root_execution_id,
        run_id=run_id,
        generation=generation,
        fencing_token=fencing_token,
        pid=pid,
        pgid=pgid,
    )
    if observed_identity != expected_identity:
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_IDENTITY_MISMATCH",
            "controller process identity/run/generation/fence drifted",
        )
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    return CampaignControllerTermination(
        pid=pid,
        pgid=pgid,
        root_execution_id=root_execution_id,
        run_id=run_id,
        generation=generation,
        fencing_token=fencing_token,
        process_identity=expected_identity,
    )


def finish_stale_controller_termination(
    termination: CampaignControllerTermination,
    *,
    grace_seconds: float,
) -> str:
    """Wait for the signalled controller, then hard-stop only the same group."""

    if grace_seconds <= 0:
        raise ValueError("campaign process termination grace must be positive")
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _pid_alive(termination.pid):
            return "terminated"
        time.sleep(0.05)
    try:
        if os.getpgid(termination.pid) != termination.pgid:
            raise CampaignLeaseTakeoverError(
                "DATA.CAMPAIGN.TAKEOVER_IDENTITY_MISMATCH",
                "controller process group changed before SIGKILL",
            )
        observed_identity = campaign_controller_process_identity(
            termination.root_execution_id,
            run_id=termination.run_id,
            generation=termination.generation,
            fencing_token=termination.fencing_token,
            pid=termination.pid,
            pgid=termination.pgid,
        )
    except (ProcessLookupError, CampaignLeaseTakeoverError) as exc:
        if not _pid_alive(termination.pid):
            return "terminated"
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_IDENTITY_MISMATCH",
            "controller identity became unavailable before SIGKILL",
        ) from exc
    if observed_identity != termination.process_identity:
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_IDENTITY_MISMATCH",
            "controller process incarnation changed before SIGKILL",
        )
    try:
        os.killpg(termination.pgid, signal.SIGKILL)
    except ProcessLookupError:
        return "terminated"
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _pid_alive(termination.pid):
            return "killed"
        time.sleep(0.05)
    if _pid_alive(termination.pid):
        raise CampaignLeaseTakeoverError(
            "DATA.CAMPAIGN.TAKEOVER_TERMINATION_FAILED",
            f"controller remained alive pid={termination.pid}",
        )
    return "killed"


def _safe_lane_process(checkpoint: Mapping[str, Any]) -> bool:
    """Only signal a process that still names the frozen lane execution."""
    try:
        pid = int(checkpoint.get("pid") or 0)
        pgid = int(checkpoint.get("pgid") or 0)
    except (TypeError, ValueError):
        return False
    execution_id = str(checkpoint.get("executionId") or "").strip()
    if (
        pid <= 0
        or pgid <= 0
        or pid != pgid
        or pid == os.getpid()
        or pgid == os.getpgrp()
        or not execution_id
        or not _pid_alive(pid)
    ):
        return False
    command = _process_command(pid)
    return bool(
        command
        and "quwoquan_data/scripts/cli.py" in command.replace("\\", "/")
        and execution_id in command
    )


def terminate_lane_process(
    checkpoint: Mapping[str, Any],
    *,
    grace_seconds: float,
) -> str:
    if grace_seconds <= 0:
        raise ValueError("campaign process termination grace must be positive")
    if not _safe_lane_process(checkpoint):
        return "not_alive_or_identity_mismatch"
    pgid = int(checkpoint["pgid"])
    pid = int(checkpoint["pid"])
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return "already_exited"
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return "terminated"
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return "terminated"
    return "killed"


__all__ = [
    "CampaignControllerTerminated",
    "CampaignControllerTermination",
    "CampaignLeaseTakeoverError",
    "append_runtime_event",
    "begin_stale_controller_termination",
    "campaign_controller_process_identity",
    "campaign_snapshot_guard",
    "controller_signal_guard",
    "finish_stale_controller_termination",
    "new_campaign_run_identity",
    "reconcile_stale_generation",
    "same_controller_identity",
    "stale_takeover_candidate",
    "terminate_lane_process",
]

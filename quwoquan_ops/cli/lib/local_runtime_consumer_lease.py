from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.common import utc_now, write_json
from quwoquan_ops.cli.lib.output_paths import repo_local_dir, safe_segment


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
DEFAULT_BUILD_GRACE_SECONDS = 20 * 60
MAX_LEASE_AGE_SECONDS = 12 * 60 * 60


def consumer_lease_dir() -> Path:
    return repo_local_dir("local-runtime-consumers")


def _lease_path(*, target: str, device: str, consumer: str) -> Path:
    filename = "--".join(
        (
            safe_segment(target, fallback="target"),
            safe_segment(device, fallback="device"),
            safe_segment(consumer, fallback="consumer"),
        )
    )
    return consumer_lease_dir() / f"{filename}.json"


def acquire_consumer_lease(
    *,
    target: str,
    device: str,
    consumer: str,
    package_name: str,
    ports: Sequence[int],
    build_grace_seconds: int = DEFAULT_BUILD_GRACE_SECONDS,
) -> dict[str, Any]:
    normalized_ports = sorted({int(port) for port in ports if int(port) > 0})
    if not target.strip() or not device.strip() or not consumer.strip():
        raise ValueError("target, device and consumer are required")
    if not package_name.strip():
        raise ValueError("package_name is required")
    if not normalized_ports:
        raise ValueError("at least one positive port is required")
    path = _lease_path(target=target, device=device, consumer=consumer)
    lease_id = "sha256:" + hashlib.sha256(
        f"{target.strip()}\0{device.strip()}\0{consumer.strip()}".encode("utf-8")
    ).hexdigest()
    payload: dict[str, Any] = {
        "schema": "qwq.local_runtime_consumer_lease.v1",
        "leaseId": lease_id,
        "target": target.strip(),
        "device": device.strip(),
        "consumer": consumer.strip(),
        "packageName": package_name.strip(),
        "ports": normalized_ports,
        "startedAt": utc_now(),
        "buildGraceSeconds": max(0, int(build_grace_seconds)),
    }
    write_json(path, payload)
    return {**payload, "path": str(path)}


def release_consumer_lease(*, target: str, device: str, consumer: str) -> bool:
    path = _lease_path(target=target, device=device, consumer=consumer)
    if not path.is_file():
        return False
    path.unlink()
    return True


def list_consumer_leases(target: str | None = None) -> list[dict[str, Any]]:
    directory = consumer_lease_dir()
    if not directory.is_dir():
        return []
    leases: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if target and str(payload.get("target") or "") != target:
            continue
        leases.append({**payload, "path": str(path)})
    return leases


def active_consumer_leases(
    target: str,
    *,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
    adb_path: str | None = None,
) -> list[dict[str, Any]]:
    current = now or datetime.now(timezone.utc)
    command_runner = runner or _run_command
    active: list[dict[str, Any]] = []
    for lease in list_consumer_leases(target):
        state, detail = _inspect_lease(
            lease,
            runner=command_runner,
            now=current,
            adb_path=adb_path,
        )
        if state == "stale":
            Path(str(lease["path"])).unlink(missing_ok=True)
            continue
        active.append({**lease, "state": state, "detail": detail})
    return active


def _inspect_lease(
    lease: dict[str, Any],
    *,
    runner: CommandRunner,
    now: datetime,
    adb_path: str | None,
) -> tuple[str, str]:
    started_at = _parse_time(str(lease.get("startedAt") or ""))
    if started_at is None:
        return "stale", "invalid startedAt"
    age_seconds = max(0, int((now - started_at).total_seconds()))
    if age_seconds > MAX_LEASE_AGE_SECONDS:
        return "stale", "maximum lease age exceeded"
    grace = max(0, int(lease.get("buildGraceSeconds") or 0))
    if age_seconds <= grace:
        return "build_grace", f"build grace active ({age_seconds}s/{grace}s)"

    executable = adb_path or shutil.which("adb")
    if not executable:
        return "active_unverified", "adb unavailable; lease retained safely"
    device = str(lease.get("device") or "").strip()
    package_name = str(lease.get("packageName") or "").strip()
    if not device or not package_name:
        return "stale", "device or packageName missing"
    device_state = runner([executable, "-s", device, "get-state"])
    if device_state.returncode != 0 or device_state.stdout.strip() != "device":
        return "stale", "device is not connected"
    process = runner([executable, "-s", device, "shell", "pidof", package_name])
    if process.returncode != 0 or not process.stdout.strip():
        return "stale", "application process is not running"
    reverses = runner([executable, "-s", device, "reverse", "--list"])
    if reverses.returncode != 0:
        return "active_unverified", "application runs but adb reverse is unreadable"
    reverse_text = reverses.stdout
    required_ports = [int(port) for port in lease.get("ports") or []]
    missing = [
        port
        for port in required_ports
        if f"tcp:{port} tcp:{port}" not in reverse_text
    ]
    if missing:
        return "stale", f"adb reverse missing ports {missing}"
    return "active", "application process and adb reverse are active"


def _parse_time(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _run_command(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

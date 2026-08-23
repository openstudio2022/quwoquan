from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.common import utc_now, write_json
from quwoquan_ops.cli.lib.output_paths import repo_local_dir, safe_segment


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
DEFAULT_BUILD_GRACE_SECONDS = 20 * 60
MAX_LEASE_AGE_SECONDS = 12 * 60 * 60
SUPPORTED_PLATFORMS = frozenset({"android", "ios-simulator", "ios-physical"})


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
    platform: str = "android",
    handoff_digest: str = "",
    release_id: str = "",
    manifest_digest: str = "",
    readiness_receipt_digest: str = "",
    build_grace_seconds: int = DEFAULT_BUILD_GRACE_SECONDS,
) -> dict[str, Any]:
    normalized_platform = platform.strip().lower()
    normalized_ports = sorted({int(port) for port in ports if int(port) > 0})
    if not target.strip() or not device.strip() or not consumer.strip():
        raise ValueError("target, device and consumer are required")
    if not package_name.strip():
        raise ValueError("package_name is required")
    if normalized_platform not in SUPPORTED_PLATFORMS:
        raise ValueError(
            "platform must be one of " + ", ".join(sorted(SUPPORTED_PLATFORMS))
        )
    if normalized_platform == "android" and not normalized_ports:
        raise ValueError("at least one positive port is required for Android")
    path = _lease_path(target=target, device=device, consumer=consumer)
    lease_id = "sha256:" + hashlib.sha256(
        (
            f"{normalized_platform}\0{target.strip()}\0{device.strip()}\0"
            f"{consumer.strip()}"
        ).encode("utf-8")
    ).hexdigest()
    payload: dict[str, Any] = {
        "schema": "qwq.local_runtime_consumer_lease",
        "leaseId": lease_id,
        "platform": normalized_platform,
        "target": target.strip(),
        "device": device.strip(),
        "consumer": consumer.strip(),
        "packageName": package_name.strip(),
        "ports": normalized_ports,
        "startedAt": utc_now(),
        "buildGraceSeconds": max(0, int(build_grace_seconds)),
    }
    if normalized_platform.startswith("ios-"):
        payload["bundleId"] = package_name.strip()
    for key, value in (
        ("handoffDigest", handoff_digest),
        ("releaseId", release_id),
        ("manifestDigest", manifest_digest),
        ("readinessReceiptDigest", readiness_receipt_digest),
    ):
        if value.strip():
            payload[key] = value.strip()
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


def inspect_consumer_leases(
    target: str,
    *,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
    adb_path: str | None = None,
    xcrun_path: str | None = None,
) -> list[dict[str, Any]]:
    """只读返回全部 lease，包括不会提升可用性的 stale 回执。"""

    current = now or datetime.now(timezone.utc)
    command_runner = runner or _run_command
    inspected: list[dict[str, Any]] = []
    for lease in list_consumer_leases(target):
        state, detail = _inspect_lease(
            lease,
            runner=command_runner,
            now=current,
            adb_path=adb_path,
            xcrun_path=xcrun_path,
        )
        inspected.append({**lease, "state": state, "detail": detail})
    return inspected


def active_consumer_leases(
    target: str,
    *,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
    adb_path: str | None = None,
    xcrun_path: str | None = None,
) -> list[dict[str, Any]]:
    return [
        lease
        for lease in inspect_consumer_leases(
            target,
            runner=runner,
            now=now,
            adb_path=adb_path,
            xcrun_path=xcrun_path,
        )
        if lease["state"] != "stale"
    ]


def _inspect_lease(
    lease: dict[str, Any],
    *,
    runner: CommandRunner,
    now: datetime,
    adb_path: str | None,
    xcrun_path: str | None,
) -> tuple[str, str]:
    started_at = _parse_time(str(lease.get("startedAt") or ""))
    if started_at is None:
        return "stale", "invalid startedAt"
    age_seconds = max(0, int((now - started_at).total_seconds()))
    grace = max(0, int(lease.get("buildGraceSeconds") or 0))
    if age_seconds <= grace and age_seconds <= MAX_LEASE_AGE_SECONDS:
        return "build_grace", f"build grace active ({age_seconds}s/{grace}s)"

    platform = str(lease.get("platform") or "android").strip().lower()
    if platform in {"ios-simulator", "ios-physical"}:
        inspector = (
            _inspect_ios_simulator_lease
            if platform == "ios-simulator"
            else _inspect_ios_physical_lease
        )
        state, detail = inspector(
            lease,
            runner=runner,
            xcrun_path=xcrun_path,
        )
        return _apply_unverified_age_limit(
            state,
            detail,
            age_seconds=age_seconds,
        )
    if platform != "android":
        return "stale", f"unsupported platform {platform!r}"

    executable = adb_path or shutil.which("adb")
    if not executable:
        return _apply_unverified_age_limit(
            "active_unverified",
            "adb unavailable; lease retained safely",
            age_seconds=age_seconds,
        )
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


def _apply_unverified_age_limit(
    state: str,
    detail: str,
    *,
    age_seconds: int,
) -> tuple[str, str]:
    if state == "active_unverified" and age_seconds > MAX_LEASE_AGE_SECONDS:
        return "stale", "unverified provisional lease exceeded maximum age"
    return state, detail


def _inspect_ios_simulator_lease(
    lease: dict[str, Any],
    *,
    runner: CommandRunner,
    xcrun_path: str | None,
) -> tuple[str, str]:
    executable = xcrun_path or shutil.which("xcrun")
    if not executable:
        return "active_unverified", "xcrun unavailable; lease retained safely"
    device = str(lease.get("device") or "").strip()
    bundle_id = str(
        lease.get("bundleId") or lease.get("packageName") or ""
    ).strip()
    if not device or not bundle_id:
        return "stale", "device or bundleId missing"

    booted = runner([executable, "simctl", "list", "devices", "booted", "--json"])
    if booted.returncode != 0:
        return "active_unverified", "Simulator liveness is unreadable"
    try:
        payload = json.loads(booted.stdout)
    except json.JSONDecodeError:
        return "active_unverified", "Simulator liveness response is malformed"
    devices = payload.get("devices") if isinstance(payload, dict) else None
    is_booted = any(
        isinstance(candidate, dict)
        and str(candidate.get("udid") or "") == device
        and str(candidate.get("state") or "") == "Booted"
        for runtime_devices in (devices or {}).values()
        if isinstance(runtime_devices, list)
        for candidate in runtime_devices
    )
    if not is_booted:
        return "stale", "Simulator is not booted"

    uid = runner([executable, "simctl", "spawn", device, "id", "-u"])
    simulator_uid = uid.stdout.strip()
    if uid.returncode != 0 or not simulator_uid.isdigit():
        return "active_unverified", "Simulator user launchd domain is unreadable"

    app_container = runner(
        [executable, "simctl", "get_app_container", device, bundle_id, "app"]
    )
    installed_app_path = app_container.stdout.strip()
    if app_container.returncode != 0 or not installed_app_path:
        return "stale", "application is not installed"

    services = runner(
        [
            executable,
            "simctl",
            "spawn",
            device,
            "launchctl",
            "print",
            f"user/{simulator_uid}",
        ]
    )
    if services.returncode != 0:
        return "active_unverified", "Simulator is booted but app liveness is unreadable"
    service_label = f"UIKitApplication:{bundle_id}["
    if service_label not in services.stdout:
        return "stale", "application process is not running"
    if installed_app_path not in services.stdout:
        return (
            "active_unverified",
            "application service exists but executable path is not confirmed",
        )
    return "active", "Simulator application service and executable are active"


def _inspect_ios_physical_lease(
    lease: dict[str, Any],
    *,
    runner: CommandRunner,
    xcrun_path: str | None,
) -> tuple[str, str]:
    executable = xcrun_path or shutil.which("xcrun")
    if not executable:
        return "active_unverified", "xcrun unavailable; lease retained safely"
    device = str(lease.get("device") or "").strip()
    bundle_id = str(
        lease.get("bundleId") or lease.get("packageName") or ""
    ).strip()
    if not device or not bundle_id:
        return "stale", "device or bundleId missing"

    try:
        apps = _read_devicectl_result(
            runner,
            [
                executable,
                "devicectl",
                "device",
                "info",
                "apps",
                "--device",
                device,
                "--bundle-id",
                bundle_id,
            ],
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return "active_unverified", f"iPhone application state is unreadable: {exc}"
    installed_apps = apps.get("apps")
    if not isinstance(installed_apps, list):
        return "active_unverified", "iPhone application listing is malformed"
    matching_apps = [
        app
        for app in installed_apps
        if isinstance(app, dict)
        and str(app.get("bundleIdentifier") or "") == bundle_id
    ]
    if not matching_apps:
        return "stale", "application is not installed"
    app_url = str(matching_apps[0].get("url") or "").rstrip("/")
    if not app_url:
        return "active_unverified", "iPhone application URL is missing"

    try:
        processes = _read_devicectl_result(
            runner,
            [
                executable,
                "devicectl",
                "device",
                "info",
                "processes",
                "--device",
                device,
            ],
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return "active_unverified", f"iPhone process state is unreadable: {exc}"
    running_processes = processes.get("runningProcesses")
    if not isinstance(running_processes, list):
        return "active_unverified", "iPhone process listing is malformed"
    if not any(
        isinstance(process, dict)
        and str(process.get("executable") or "").startswith(app_url + "/")
        and isinstance(process.get("processIdentifier"), int)
        and int(process["processIdentifier"]) > 0
        for process in running_processes
    ):
        return "stale", "application process is not running"
    return "active", "registered iPhone application executable is active"


def _read_devicectl_result(
    runner: CommandRunner,
    command: list[str],
) -> dict[str, Any]:
    directory = repo_local_dir("local-runtime-consumer-probes")
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(
        prefix="devicectl-",
        suffix=".json",
        dir=directory,
    )
    os.close(descriptor)
    output_path = Path(raw_path)
    output_path.unlink(missing_ok=True)
    try:
        result = runner([*command, "--json-output", str(output_path)])
        if result.returncode != 0:
            raise RuntimeError(f"devicectl exited with code {result.returncode}")
        if not output_path.is_file():
            raise RuntimeError("devicectl did not create structured output")
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("devicectl structured output is invalid") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
            raise ValueError("devicectl structured result is missing")
        return payload["result"]
    finally:
        output_path.unlink(missing_ok=True)


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

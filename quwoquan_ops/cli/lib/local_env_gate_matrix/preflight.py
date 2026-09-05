"""L0 commit gate、Docker 就绪与设备/发布绑定前置校验（自原单文件逐字搬移）。"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.local_env_gate_matrix.identity import (
    _SHA256,
    DEVICE_PROFILE_FULL,
    DEVICE_PROFILES,
    ROOT,
)


def _run_commit_gate() -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        ["make", "commit-gate"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    summary_path = (
        ROOT
        / ".qwq_output"
        / "env"
        / "repo"
        / "runs"
        / "commit-gate"
        / "summary.json"
    )
    summary: dict[str, Any] = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "exitCode": result.returncode,
        "durationMs": int((time.monotonic() - started) * 1000),
        "summary": summary,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
        "reportDir": (
            str(summary_path.parent.relative_to(ROOT)) if summary_path.exists() else ""
        ),
    }


def _docker_daemon_ready() -> tuple[bool, str]:
    result = subprocess.run(
        ["docker", "info"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return True, "docker daemon ready"
    detail = (result.stderr or result.stdout or "docker info failed").strip()
    return False, detail[:300]


def _device_uat_bindings(
    *,
    device_profile: str,
    ios_simulator_device: str,
    android_emulator_device: str,
    android_physical_device: str,
    ios_physical_device: str = "",
) -> tuple[tuple[str, str, str], ...]:
    if device_profile not in DEVICE_PROFILES:
        raise ValueError(
            "device_profile must be one of " + ", ".join(DEVICE_PROFILES)
        )
    bindings = [
        ("iosSimulatorUAT", "ios-simulator", ios_simulator_device),
        ("androidEmulatorUAT", "android", android_emulator_device),
    ]
    if device_profile == DEVICE_PROFILE_FULL:
        bindings.extend((
            ("androidPhysicalUAT", "android", android_physical_device),
            ("iosPhysicalUAT", "ios-physical", ios_physical_device),
        ))
    return tuple(bindings)


def _device_binding_errors(
    *,
    device_profile: str = DEVICE_PROFILE_FULL,
    ios_simulator_device: str,
    android_emulator_device: str,
    android_physical_device: str,
    ios_physical_device: str = "",
) -> list[str]:
    """Reject absent or misclassified device bindings before mutating runtimes."""

    errors: list[str] = []
    try:
        uat_bindings = _device_uat_bindings(
            device_profile=device_profile,
            ios_simulator_device=ios_simulator_device,
            android_emulator_device=android_emulator_device,
            android_physical_device=android_physical_device,
            ios_physical_device=ios_physical_device,
        )
    except ValueError as exc:
        return [str(exc)]
    labels = {
        "iosSimulatorUAT": "iOS Simulator",
        "androidEmulatorUAT": "Android Emulator",
        "androidPhysicalUAT": "Android physical device",
        "iosPhysicalUAT": "iOS physical device",
    }
    bindings = {
        labels[key]: device_id.strip()
        for key, _, device_id in uat_bindings
    }
    for label, device_id in bindings.items():
        if not device_id:
            errors.append(f"{label} device id is required")
    if device_profile == DEVICE_PROFILE_FULL:
        android_ids = {
            android_emulator_device.strip(),
            android_physical_device.strip(),
        }
        android_ids.discard("")
        if len(android_ids) != 2 and len(android_ids) > 0:
            errors.append("Android Emulator and physical device must be distinct")
    if errors:
        return errors

    try:
        simulator = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "available", "--json"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        errors.append("xcrun simctl is unavailable")
        return errors
    try:
        simulator_payload = json.loads(simulator.stdout)
    except json.JSONDecodeError:
        simulator_payload = {}
    available_ids = {
        str(item.get("udid") or "")
        for items in (simulator_payload.get("devices") or {}).values()
        if isinstance(items, list)
        for item in items
        if isinstance(item, dict) and item.get("isAvailable") is not False
    }
    if simulator.returncode != 0 or ios_simulator_device not in available_ids:
        errors.append("configured iOS Simulator is not available")

    for key, platform, device_id in uat_bindings:
        if platform == "ios-physical":
            try:
                physical = subprocess.run(
                    ["xcrun", "devicectl", "list", "devices", "--json-output", "/dev/stdout"],
                    text=True, capture_output=True, check=False,
                )
                physical_payload = json.loads(physical.stdout)
            except (OSError, json.JSONDecodeError):
                errors.append("xcrun devicectl physical inventory is unavailable")
                continue
            serialized = json.dumps(physical_payload, ensure_ascii=False)
            if physical.returncode != 0 or device_id not in serialized:
                errors.append("configured iOS physical device is not connected")
            continue
        if platform != "android":
            continue
        label = labels[key]
        expected_qemu = "1" if key == "androidEmulatorUAT" else "0"
        try:
            state = subprocess.run(
                ["adb", "-s", device_id, "get-state"],
                text=True,
                capture_output=True,
                check=False,
            )
            qemu = subprocess.run(
                ["adb", "-s", device_id, "shell", "getprop", "ro.kernel.qemu"],
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError:
            errors.append("adb is unavailable")
            break
        actual_qemu = (qemu.stdout or "0").strip() or "0"
        if state.returncode != 0 or state.stdout.strip() != "device":
            errors.append(f"configured {label} is not connected")
        elif actual_qemu != expected_qemu:
            errors.append(f"configured {label} has the wrong device class")
    return errors


def _release_binding(attestation: str, *, label: str) -> dict[str, Any]:
    path = Path(str(attestation or "").strip()).expanduser()
    if not str(attestation or "").strip():
        raise ValueError(f"{label} release attestation is required")
    try:
        payload = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} release attestation is unreadable: {exc}") from exc
    release_id = str(payload.get("releaseId") or "").strip() if isinstance(payload, dict) else ""
    digest = str(payload.get("payloadSha256") or "").strip() if isinstance(payload, dict) else ""
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "quwoquan_data.release_attestation"
        or not release_id
        or _SHA256.fullmatch(digest) is None
    ):
        raise ValueError(f"{label} release attestation identity is invalid")
    release_class = payload.get("releaseClass")
    lifecycle_state = payload.get("productLifecycleState")
    contains_unverified_assets = payload.get("containsUnverifiedAssets")
    if (
        release_class not in {"research", "commercial"}
        or lifecycle_state != release_class
        or not isinstance(contains_unverified_assets, bool)
        or (
            release_class == "commercial"
            and contains_unverified_assets is not False
        )
    ):
        raise ValueError(
            f"{label} release attestation lifecycle identity is invalid"
        )
    return {
        "releaseId": release_id,
        "releaseDigest": digest,
        "releaseClass": release_class,
        "productLifecycleState": lifecycle_state,
        "containsUnverifiedAssets": contains_unverified_assets,
        "attestation": str(path.resolve()),
    }

"""设备发现与选择：iOS 模拟器 runtime 版本、Android adb 清单、dry-run 设备与 iOS 产物桥接。

正文自 run_environment_patrol_smoke.py 逐字搬入。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from typing import Any, Callable

from quwoquan_ops.ci.device_matrix.android import resolve_android_debug_bridge

from .cli_args import summarize_output
from .constants import (
    IOS_RUNTIME_VERSION_PATTERN,
    IOS_SDK_VERSION_PATTERN,
    PATROL_IOS_PRODUCTS_DIR,
    REPO_ROOT,
    XCODE_GLOBAL_PRODUCTS_DIR,
    XCODE_IOS_SIMULATOR_SDK_PATTERN,
)


def ios_sdk_version(device: dict[str, Any]) -> tuple[int, int] | None:
    sdk = str(device.get("sdk", "")).strip()
    match = IOS_SDK_VERSION_PATTERN.search(sdk)
    if match is None:
        return None
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    return (major, minor)


def _enrich_ios_simulator_runtime_versions(
    devices: list[dict[str, Any]],
    *,
    xcrun_path: str | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[dict[str, Any]]:
    simulators = [
        device
        for device in devices
        if str(device.get("targetPlatform", "")).strip().lower() == "ios"
        and bool(device.get("emulator", False))
    ]
    if not simulators:
        return devices
    executable = xcrun_path or shutil.which("xcrun")
    if not executable:
        raise RuntimeError(
            "GATE_BLOCK: xcrun is required to resolve the exact iOS Simulator runtime"
        )
    result = command_runner(
        [executable, "simctl", "list", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = ((result.stderr or result.stdout) or "unknown simctl failure").strip()
        raise RuntimeError(
            "GATE_BLOCK: cannot resolve iOS Simulator runtimes: " + detail
        )
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "GATE_BLOCK: simctl returned invalid iOS Simulator runtime JSON"
        ) from exc
    runtime_versions = {
        str(runtime.get("identifier") or "").strip(): str(
            runtime.get("version") or ""
        ).strip()
        for runtime in payload.get("runtimes") or []
        if isinstance(runtime, dict)
        and bool(runtime.get("isAvailable", True))
        and IOS_RUNTIME_VERSION_PATTERN.fullmatch(
            str(runtime.get("version") or "").strip()
        )
    }
    device_versions: dict[str, str] = {}
    raw_devices = payload.get("devices")
    if isinstance(raw_devices, dict):
        for runtime_identifier, runtime_devices in raw_devices.items():
            version = runtime_versions.get(str(runtime_identifier).strip(), "")
            if not version or not isinstance(runtime_devices, list):
                continue
            for device in runtime_devices:
                if not isinstance(device, dict) or not bool(
                    device.get("isAvailable", True)
                ):
                    continue
                device_id = str(device.get("udid") or "").strip()
                if device_id:
                    device_versions[device_id] = version
    enriched: list[dict[str, Any]] = []
    for device in devices:
        if device not in simulators:
            enriched.append(device)
            continue
        device_id = str(device.get("id") or "").strip()
        version = device_versions.get(device_id, "")
        if not version:
            raise RuntimeError(
                "GATE_BLOCK: exact iOS Simulator runtime is unavailable for "
                f"device {device_id or '<empty>'}"
            )
        enriched.append({**device, "runtimeVersion": version})
    return enriched


def patrol_ios_runtime_argument(device: dict[str, Any]) -> str | None:
    """Return Patrol's explicit simulator runtime argument for an iOS device."""
    if str(device.get("targetPlatform", "")).strip().lower() != "ios":
        return None
    if not bool(device.get("emulator", False)):
        return None
    runtime_version = str(device.get("runtimeVersion") or "").strip()
    if runtime_version:
        if not IOS_RUNTIME_VERSION_PATTERN.fullmatch(runtime_version):
            raise ValueError(
                f"invalid iOS simulator runtime version: {runtime_version!r}"
            )
        return f"--ios={runtime_version}"
    version = ios_sdk_version(device)
    if version is None:
        raise ValueError("iOS simulator runtime is missing or unparseable")
    return f"--ios={version[0]}.{version[1]}"


def xcode_ios_simulator_sdk_version() -> tuple[int, int]:
    result = subprocess.run(
        ["xcodebuild", "-showsdks"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("xcodebuild -showsdks failed")
    versions = [
        (int(match.group(1)), int(match.group(2) or 0))
        for match in XCODE_IOS_SIMULATOR_SDK_PATTERN.finditer(result.stdout)
    ]
    if not versions:
        raise RuntimeError("Xcode reports no iOS Simulator SDK")
    return max(versions)


def _select_compatible_ios_devices(
    devices: list[dict[str, Any]],
    *,
    simulator_sdk_version: tuple[int, int],
) -> list[dict[str, Any]]:
    simulators = [
        device
        for device in devices
        if str(device.get("targetPlatform", "")).strip().lower() == "ios"
        and bool(device.get("emulator", False))
    ]
    compatible_versions = [
        version
        for device in simulators
        for version in [ios_sdk_version(device)]
        if version is not None and version <= simulator_sdk_version
    ]
    if simulators and not compatible_versions:
        requested = ", ".join(
            sorted({str(device.get("sdk", "")).strip() for device in simulators})
        )
        supported = f"{simulator_sdk_version[0]}.{simulator_sdk_version[1]}"
        raise RuntimeError(
            f"no discovered iOS simulator runtime is compatible with Xcode SDK {supported}: {requested}"
        )
    if not compatible_versions:
        return devices
    selected_version = max(compatible_versions)
    selected = [
        device
        for device in devices
        if not (
            str(device.get("targetPlatform", "")).strip().lower() == "ios"
            and bool(device.get("emulator", False))
        )
        or ios_sdk_version(device) == selected_version
    ]
    patrol_keys: set[tuple[tuple[int, int] | None, str]] = set()
    for device in selected:
        if str(device.get("targetPlatform", "")).strip().lower() != "ios":
            continue
        key = (ios_sdk_version(device), str(device.get("name", "")).strip())
        if key in patrol_keys:
            raise RuntimeError(
                "Patrol cannot select duplicate iOS devices with the same runtime and name: "
                f"{key[1]} iOS {key[0]}"
            )
        patrol_keys.add(key)
    return selected


def _explicit_android_devices(device_ids: list[str]) -> list[dict[str, Any]]:
    """Resolve explicitly selected Android devices directly from ADB.

    A running Flutter development session may hold the Flutter tool lock for a
    long time.  Explicit Patrol destinations do not need global Flutter device
    discovery, so ADB is the narrower and authoritative boundary here.
    """
    requested = tuple(dict.fromkeys(item.strip() for item in device_ids if item.strip()))
    if not requested:
        return []
    adb = resolve_android_debug_bridge()
    result = subprocess.run(
        [adb, "devices", "-l"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("adb devices -l failed:\n" + summarize_output(result.stderr or ""))
    inventory: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 2 or fields[1] != "device":
            continue
        properties = {
            key: value
            for field in fields[2:]
            if ":" in field
            for key, value in [field.split(":", 1)]
        }
        inventory[fields[0]] = properties
    missing = [device_id for device_id in requested if device_id not in inventory]
    if missing:
        raise RuntimeError(
            "explicit Android Patrol devices are unavailable: " + ", ".join(missing)
        )
    return [
        {
            "id": device_id,
            "name": inventory[device_id].get("model") or device_id,
            "targetPlatform": _android_target_platform(inventory[device_id]),
            "sdk": inventory[device_id].get("device") or "adb",
            "emulator": device_id.startswith("emulator-"),
            "ephemeral": False,
            "category": "mobile",
        }
        for device_id in requested
    ]


def _android_target_platform(properties: dict[str, str]) -> str:
    descriptor = " ".join(properties.values()).lower()
    if "arm64" in descriptor or "aarch64" in descriptor:
        return "android-arm64"
    if "x86_64" in descriptor or "x64" in descriptor:
        return "android-x64"
    if "x86" in descriptor:
        return "android-x86"
    return "android-arm"


def discover_devices(platform: str, device_ids: list[str]) -> list[dict[str, Any]]:
    allowed_ids = {item for item in device_ids if item}
    if platform == "android" and allowed_ids:
        return _explicit_android_devices(device_ids)
    payload = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "quwoquan_app"
                / "scripts"
                / "tools"
                / "device"
                / "discover_flutter_mobile_devices.py"
            ),
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if payload.returncode != 0:
        raise RuntimeError(
            "discover_flutter_mobile_devices.py failed:\n"
            + summarize_output((payload.stdout or "") + (payload.stderr or ""))
        )
    data = json.loads(payload.stdout)
    devices = list(data.get("devices") or [])
    selected: list[dict[str, Any]] = []
    for device in devices:
        target = str(device.get("targetPlatform", "")).lower()
        device_id = str(device.get("id", "")).strip()
        if not device_id:
            continue
        if allowed_ids and device_id not in allowed_ids:
            continue
        if platform == "android" and not target.startswith("android"):
            continue
        if platform == "ios" and target != "ios":
            continue
        if platform == "all" and target != "ios" and not target.startswith("android"):
            continue
        selected.append(device)
    selected = _enrich_ios_simulator_runtime_versions(selected)
    if not allowed_ids and platform in ("ios", "all"):
        selected = _select_compatible_ios_devices(
            selected,
            simulator_sdk_version=xcode_ios_simulator_sdk_version(),
        )
    return selected


def ensure_patrol_ios_products_bridge() -> None:
    """Bridge Patrol's expected ios_integ products path to Xcode 26 global products."""
    patrol_products = PATROL_IOS_PRODUCTS_DIR
    patrol_products.parent.mkdir(parents=True, exist_ok=True)
    if patrol_products.is_symlink():
        try:
            if patrol_products.resolve() == XCODE_GLOBAL_PRODUCTS_DIR.resolve():
                return
        except FileNotFoundError:
            patrol_products.unlink()
    elif patrol_products.exists():
        return
    patrol_products.symlink_to(XCODE_GLOBAL_PRODUCTS_DIR)


def dry_run_devices(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Synthesize devices for a dry run, resolving real iOS simulator runtimes.

    A dry run exists to validate the exact command that a real run would issue.
    An iOS simulator entry has no meaning without a runtime identity, so the
    synthetic sdk string must not stand in for one: the iOS entries go through
    the same runtime enrichment as discovery, which fails closed when the
    requested simulator does not exist.
    """
    raw_ids = args.device_id or ["dry-run-device"]
    devices = []
    for device_id in raw_ids:
        target_platform = "ios" if args.platform == "ios" else "android-arm64"
        if args.platform == "all":
            target_platform = "ios"
        devices.append(
            {
                "id": device_id,
                "name": "Dry Run Device",
                "targetPlatform": target_platform,
                "sdk": "dry-run",
                "emulator": True,
                "screenClass": "phone",
            }
        )
    return _enrich_ios_simulator_runtime_versions(devices)

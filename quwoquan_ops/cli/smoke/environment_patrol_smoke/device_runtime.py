"""设备侧运行环境：命令 env 注入、本地端口反转、consumer lease 与 release UAT 状态复位。

正文自 run_environment_patrol_smoke.py 逐字搬入。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.device_matrix.android import resolve_android_debug_bridge
from quwoquan_ops.ci.device_matrix.evidence import sanitize_device_id
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.flutter_android_device_proxy import (
    ANDROID_DEVICE_INVENTORY_ENV,
    REAL_FLUTTER_ENV,
)
from quwoquan_ops.cli.lib.local_runtime_consumer_lease import (
    acquire_consumer_lease,
)
from quwoquan_ops.cli.lib.package_reuse.patrol_command_envelope import (
    PATROL_COMMAND_ENVELOPE_DIGEST_ENV,
    closed_patrol_child_environment,
    strip_proxy_environment,
    validate_patrol_command_environment,
)

from .cli_args import summarize_output
from .constants import (
    ANDROID_DEVICE_PROXY,
    PATROL_FLUTTER_COMMAND_ENV,
    android_release_uat_package,
    ios_release_uat_bundle_ids,
)
from .handoff import (
    _apply_launcher_handoff_to_command_env,
    _effective_base_urls_for_device,
)
from .session import (
    _is_local_target,
    _local_target_for_environment_alias,
    _runtime_env_for_alias,
)


def _canonical_emulator_flag(device: dict[str, Any]) -> bool:
    emulator = device.get("emulator")
    if type(emulator) is not bool:
        raise RuntimeError(
            "GATE_BLOCK: Patrol device emulator field must be an explicit boolean"
        )
    return emulator


def _resolved_patrol_flutter(environment: dict[str, str]) -> tuple[str, bool]:
    if environment.get(PATROL_COMMAND_ENVELOPE_DIGEST_ENV):
        try:
            identity = validate_patrol_command_environment(environment)
        except (OSError, TypeError, ValueError) as error:
            raise RuntimeError(
                "GATE_BLOCK: Patrol sealed Flutter command identity drifted"
            ) from error
        return identity["executable"], True
    discovered = shutil.which("flutter", path=environment.get("PATH", ""))
    if discovered is None:
        raise RuntimeError("GATE_BLOCK: Flutter executable is required for Patrol")
    return str(Path(discovered).resolve()), False


def _device_command_env(
    args: argparse.Namespace,
    device: dict[str, Any],
    *,
    launcher_handoff: dict[str, Any] | None = None,
) -> dict[str, str]:
    if os.environ.get(PATROL_COMMAND_ENVELOPE_DIGEST_ENV):
        try:
            env = closed_patrol_child_environment(os.environ)
        except (OSError, TypeError, ValueError) as error:
            raise RuntimeError(
                "GATE_BLOCK: Patrol sealed command environment drifted"
            ) from error
    else:
        env = strip_proxy_environment(os.environ)
    emulator = _canonical_emulator_flag(device)
    runtime_env = args.runtime_env.strip() or _runtime_env_for_alias(args.env_name)
    launch_target = _local_target_for_environment_alias(args.env_name)
    try:
        get_target(load_environment_topology(), launch_target)
    except KeyError as exc:
        raise ValueError(
            "environment alias does not resolve to a canonical launch target: "
            f"{args.env_name!r}"
        ) from exc
    env["QWQ_APP_RUNTIME_ENV"] = runtime_env
    env["QWQ_LAUNCH_TARGET"] = launch_target
    target = str(device.get("targetPlatform", "")).strip().lower()
    if target.startswith("android"):
        device_id = str(device.get("id", "")).strip()
        if not device_id:
            raise RuntimeError(
                "GATE_BLOCK: Android Patrol requires an explicit device id"
            )
        env["QWQ_RUN_DEVICE_ID"] = device_id
        env["ANDROID_SERIAL"] = device_id
        adb = resolve_android_debug_bridge()
        real_flutter, sealed = _resolved_patrol_flutter(env)
        if not sealed:
            adb_directory = str(Path(adb).parent) if adb else ""
            existing_path = env.get("PATH", "")
            path_entries = existing_path.split(os.pathsep) if existing_path else []
            if adb_directory and adb_directory not in path_entries:
                env["PATH"] = (
                    f"{adb_directory}{os.pathsep}{existing_path}"
                    if existing_path
                    else adb_directory
                )
        proxy_devices = [
            {
                "id": str(device.get("id", "")).strip(),
                "name": str(device.get("name", "")).strip(),
                "targetPlatform": str(device.get("targetPlatform", "")).strip(),
                "emulator": emulator,
                "isSupported": True,
            }
        ]
        env[PATROL_FLUTTER_COMMAND_ENV] = f"{sys.executable} {ANDROID_DEVICE_PROXY}"
        env[REAL_FLUTTER_ENV] = real_flutter
        env[ANDROID_DEVICE_INVENTORY_ENV] = json.dumps(
            proxy_devices,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    elif target == "ios" and emulator and _is_local_target(args.env_name):
        device_id = str(device.get("id", "")).strip()
        if not device_id:
            raise RuntimeError(
                "GATE_BLOCK: local iOS Simulator Patrol requires an explicit device id"
            )
        env["QWQ_IOS_SIMULATOR_UDID"] = device_id
        real_flutter, _sealed = _resolved_patrol_flutter(env)
        env[PATROL_FLUTTER_COMMAND_ENV] = f"{sys.executable} {ANDROID_DEVICE_PROXY}"
        env[REAL_FLUTTER_ENV] = real_flutter
    if launcher_handoff is not None:
        _apply_launcher_handoff_to_command_env(env, launcher_handoff)
        if env["QWQ_APP_RUNTIME_ENV"] != runtime_env:
            raise ValueError("launcher handoff environment does not match Patrol")
        if env["QWQ_LAUNCH_TARGET"] != launch_target:
            raise ValueError("launcher handoff target does not match Patrol")
    return env


def _local_tls_trust_evidence(*, dry_run: bool) -> dict[str, str]:
    """Describe the public-CA boundary without mutating device trust state."""

    if dry_run:
        return {"status": "skipped", "reason": "not-required"}
    return {"status": "system-public-ca", "reason": "dns-01"}


def _prepare_android_local_port_reverse(
    args: argparse.Namespace,
    device: dict[str, Any],
) -> dict[str, Any]:
    """反向映射 canonical HTTPS/WSS authority 使用的本地 target 端口。"""

    target_platform = str(device.get("targetPlatform", "")).strip().lower()
    if not (_is_local_target(args.env_name) and target_platform.startswith("android")):
        return {"status": "skipped", "reason": "not-required"}
    adb = resolve_android_debug_bridge()
    device_id = str(device.get("id", "")).strip()
    if not adb:
        raise RuntimeError(
            "GATE_BLOCK: adb is required to reverse local target ports for Android Patrol "
            "(set ANDROID_SDK_ROOT/ANDROID_HOME or install platform-tools)",
        )
    if not device_id:
        raise RuntimeError(
            "GATE_BLOCK: Android Patrol device is missing an explicit device id",
        )
    base_urls = _effective_base_urls_for_device(args, device)
    ports: set[int] = set()
    for value in base_urls.values():
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"https", "wss"} or not parsed.hostname:
            continue
        ports.add(parsed.port or 443)
    if not ports:
        raise RuntimeError(
            "GATE_BLOCK: no secure HTTP/WebSocket local target ports are available for Android Patrol",
        )
    mappings: list[dict[str, int]] = []
    for port in sorted(ports):
        command = [
            adb,
            "-s",
            device_id,
            "reverse",
            f"tcp:{port}",
            f"tcp:{port}",
        ]
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                "GATE_BLOCK: failed to configure Android local target port "
                f"reverse tcp:{port}: {detail or result.returncode}",
            )
        mappings.append({"devicePort": port, "hostPort": port})
    return {
        "status": "installed",
        "deviceId": device_id,
        "mappings": mappings,
    }


def _acquire_patrol_consumer_lease(
    args: argparse.Namespace,
    device: dict[str, Any],
    android_port_reverse: dict[str, Any],
    command_env: dict[str, str],
) -> tuple[str, str, str, str] | None:
    """Bind one Android or iOS Simulator Patrol build to its local runtime."""

    target_platform = str(device.get("targetPlatform", "")).strip().lower()
    emulator = _canonical_emulator_flag(device)
    is_android = target_platform.startswith("android")
    is_ios_simulator = target_platform == "ios" and emulator
    if not _is_local_target(args.env_name) or not (is_android or is_ios_simulator):
        return None
    device_id = str(device.get("id", "")).strip()
    if not device_id:
        raise RuntimeError("GATE_BLOCK: Patrol consumer device identity is missing")
    mappings = android_port_reverse.get("mappings") if is_android else []
    if is_android and not isinstance(mappings, list):
        raise RuntimeError(
            "GATE_BLOCK: Android Patrol must install local port reverse before "
            "acquiring its runtime consumer lease",
        )
    ports = sorted(
        {
            int(mapping.get("devicePort") or 0)
            for mapping in mappings
            if isinstance(mapping, dict) and int(mapping.get("devicePort") or 0) > 0
        }
    )
    if is_android and not ports:
        raise RuntimeError(
            "GATE_BLOCK: Android Patrol local runtime consumer lease has no ports",
        )
    target_name = _local_target_for_environment_alias(args.env_name)
    consumer = f"environment-patrol-{os.getpid()}-{sanitize_device_id(device_id)}"
    lease_runtime_env = str(getattr(args, "runtime_env", "") or "").strip() or (
        _runtime_env_for_alias(args.env_name)
    )
    lease = acquire_consumer_lease(
        target=target_name,
        device=device_id,
        consumer=consumer,
        package_name=(
            android_release_uat_package(lease_runtime_env, "debug")
            if is_android
            else ios_release_uat_bundle_ids(lease_runtime_env, "debug")[0]
        ),
        ports=ports,
        platform="android" if is_android else "ios-simulator",
    )
    command_env.update(
        {
            "QWQ_RUN_CONSUMER_ID": consumer,
            "QWQ_CONSUMER_LEASE_ACQUIRED": "1",
            "QWQ_CONSUMER_LEASE_ID": str(lease["leaseId"]),
        }
    )
    if is_android:
        port_list = ",".join(str(port) for port in ports)
        reverse_receipt_digest = (
            "sha256:"
            + hashlib.sha256(
                f"{target_name}\0{device_id}\0{port_list}".encode()
            ).hexdigest()
        )
        command_env.update(
            {
                "QWQ_ANDROID_LOCAL_PORTS": port_list,
                "QWQ_ANDROID_REVERSE_EXPECTED_PORTS": port_list,
                "QWQ_ANDROID_REVERSE_ACTUAL_PORTS": port_list,
                "QWQ_ANDROID_REVERSE_RECEIPT_DIGEST": reverse_receipt_digest,
            }
        )
    return target_name, device_id, consumer, str(lease["leaseId"])


def _bind_patrol_consumer_lease_to_handoff(
    args: argparse.Namespace,
    device: dict[str, Any],
    consumer_lease: tuple[str, str, str, str],
    command_env: dict[str, str],
    handoff: dict[str, Any],
) -> None:
    """Update the same deterministic lease with its exact launcher identity."""

    target_name, device_id, consumer, lease_id = consumer_lease
    is_android = str(device.get("targetPlatform") or "").lower().startswith("android")
    ports = [
        int(value)
        for value in command_env.get("QWQ_ANDROID_LOCAL_PORTS", "").split(",")
        if value.strip()
    ]
    rebind_runtime_env = str(getattr(args, "runtime_env", "") or "").strip() or (
        _runtime_env_for_alias(args.env_name)
    )
    rebound = acquire_consumer_lease(
        target=target_name,
        device=device_id,
        consumer=consumer,
        package_name=(
            android_release_uat_package(rebind_runtime_env, "debug")
            if is_android
            else ios_release_uat_bundle_ids(rebind_runtime_env, "debug")[0]
        ),
        ports=ports,
        platform="android" if is_android else "ios-simulator",
        handoff_digest=str(handoff["effectiveLaunchManifestDigest"]),
    )
    if rebound.get("leaseId") != lease_id:
        raise RuntimeError(
            "GATE_BLOCK: runtime consumer lease identity changed while binding handoff"
        )
    command_env["QWQ_CONSUMER_LEASE_ID"] = lease_id


def _reset_release_uat_device_state(
    args: argparse.Namespace,
    device: dict[str, Any],
) -> dict[str, Any]:
    """Guarantee release-bound journeys start without a persisted App session."""
    if not str(getattr(args, "release_uat_cases", "") or "").strip():
        return {"status": "skipped", "reason": "not-release-bound"}
    if args.dry_run:
        return {"status": "planned", "reason": "release-bound-cold-start"}

    device_id = str(device.get("id", "")).strip()
    target = str(device.get("targetPlatform", "")).strip().lower()
    emulator = _canonical_emulator_flag(device)
    if not device_id:
        raise RuntimeError("release-bound UAT device identity is empty")

    # patrol UAT 以 Flutter Debug 构建执行，App 身份必须按环境 × BuildMode 推导，
    # 与安装制品的 applicationId/bundle id 单轨一致，禁止字面值。
    runtime_env = str(getattr(args, "runtime_env", "") or "").strip() or (
        _runtime_env_for_alias(args.env_name)
    )
    reset_rows: list[dict[str, Any]] = []
    if target == "ios":
        if not emulator:
            raise RuntimeError(
                "release-bound iOS UAT requires a simulator with resettable App state"
            )
        for bundle_id in ios_release_uat_bundle_ids(runtime_env, "debug"):
            command = ["xcrun", "simctl", "uninstall", device_id, bundle_id]
            result = subprocess.run(
                command, text=True, capture_output=True, check=False
            )
            output = ((result.stdout or "") + (result.stderr or "")).strip()
            absent = (
                "not installed" in output.lower() or "no such file" in output.lower()
            )
            if result.returncode != 0 and not absent:
                raise RuntimeError(
                    f"release-bound iOS UAT App reset failed for {bundle_id}: "
                    f"{summarize_output(output)}"
                )
            reset_rows.append(
                {
                    "bundleId": bundle_id,
                    "exitCode": result.returncode,
                    "alreadyAbsent": result.returncode != 0,
                }
            )
    elif target.startswith("android"):
        adb = resolve_android_debug_bridge()
        if adb is None:
            raise RuntimeError(
                "release-bound Android UAT requires adb for App state reset"
            )
        android_uat_package = android_release_uat_package(runtime_env, "debug")
        package_path_command = [
            str(adb),
            "-s",
            device_id,
            "shell",
            "pm",
            "path",
            android_uat_package,
        ]
        package_path = subprocess.run(
            package_path_command,
            text=True,
            capture_output=True,
            check=False,
        )
        package_path_output = (
            (package_path.stdout or "") + (package_path.stderr or "")
        ).strip()
        installed = package_path.returncode == 0 and package_path_output.startswith(
            "package:"
        )
        if not installed and package_path.returncode not in (0, 1):
            raise RuntimeError(
                "release-bound Android UAT App presence check failed: "
                f"{summarize_output(package_path_output)}"
            )
        if installed:
            clear_command = [
                str(adb),
                "-s",
                device_id,
                "shell",
                "pm",
                "clear",
                android_uat_package,
            ]
            clear_result = subprocess.run(
                clear_command,
                text=True,
                capture_output=True,
                check=False,
            )
            clear_output = (
                (clear_result.stdout or "") + (clear_result.stderr or "")
            ).strip()
            if clear_result.returncode != 0 or "success" not in clear_output.lower():
                raise RuntimeError(
                    "release-bound Android UAT App reset failed: "
                    f"{summarize_output(clear_output)}"
                )
        reset_rows.append(
            {
                "package": android_uat_package,
                "exitCode": 0,
                "alreadyAbsent": not installed,
            }
        )
    else:
        raise RuntimeError(
            f"release-bound UAT does not support non-mobile target platform: {target}"
        )
    return {
        "status": "reset",
        "reason": "release-bound-cold-start",
        "applications": reset_rows,
    }

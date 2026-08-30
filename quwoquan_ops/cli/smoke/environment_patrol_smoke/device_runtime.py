"""设备侧运行环境：命令 env 注入、本地端口反转、consumer lease 与 release UAT 状态复位。

正文自 run_environment_patrol_smoke.py 逐字搬入。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
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

from .cli_args import _redact_text
from .constants import (
    ANDROID_DEVICE_PROXY,
    PATROL_FLUTTER_COMMAND_ENV,
    REPO_ROOT,
    android_release_uat_package,
    ios_release_uat_bundle_ids,
)
from .execution import run_command
from .handoff import (
    _apply_launcher_handoff_to_command_env,
    _effective_base_urls_for_device,
)
from .session import (
    _is_local_target,
    _local_target_for_environment_alias,
    _runtime_env_for_alias,
)

_DEVICE_PREFLIGHT_COMMAND_TIMEOUT_SECONDS = 60
_DEVICE_PREFLIGHT_BLOCKER = "APP.LAUNCH.device_unavailable"
_DEVICE_COMMAND_ENVIRONMENT_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "ANDROID_HOME",
        "ANDROID_SDK_ROOT",
        "DEVELOPER_DIR",
        "SDKROOT",
        "TOOLCHAINS",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "TMP",
        "TEMP",
    }
)
_SECRET_ENVIRONMENT_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


def _device_preflight_command_environment() -> dict[str, str]:
    sanitized = strip_proxy_environment(os.environ)
    return {
        key: str(value)
        for key, value in sanitized.items()
        if key in _DEVICE_COMMAND_ENVIRONMENT_KEYS
    }


def _device_preflight_secret_values() -> tuple[str, ...]:
    return tuple(
        str(value)
        for key, value in os.environ.items()
        if value
        and any(marker in key.upper() for marker in _SECRET_ENVIRONMENT_MARKERS)
    )


def _device_preflight_log_path(
    args: argparse.Namespace,
    device: dict[str, Any],
    *,
    operation: str,
) -> Path:
    report_value = str(getattr(args, "report", "") or "").strip()
    device_id = str(device.get("id") or "").strip()
    if not report_value or not device_id or not operation.replace("-", "").isalnum():
        raise RuntimeError(
            f"GATE_BLOCK: {_DEVICE_PREFLIGHT_BLOCKER}: "
            "managed device preflight log identity is invalid"
        )
    report_path = Path(report_value)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    return (
        report_path.parent
        / "runs"
        / sanitize_device_id(device_id)
        / f"device-preflight-{operation}.log"
    )


def _device_preflight_failure(
    operation: str,
    *,
    result: dict[str, Any] | None = None,
) -> RuntimeError:
    status = "did not complete"
    diagnostic = ""
    if result is not None:
        if result.get("timedOut") is True or result.get("exitCode") == 124:
            status = "timed out"
        else:
            status = "failed"
        summary = _redact_text(
            str(result.get("outputSummary") or ""),
            _device_preflight_secret_values(),
        )
        if summary:
            diagnostic = (
                " diagnosticDigest=sha256:"
                + hashlib.sha256(summary.encode("utf-8")).hexdigest()
            )
    return RuntimeError(
        f"GATE_BLOCK: {_DEVICE_PREFLIGHT_BLOCKER}: {operation} {status}{diagnostic}"
    )


def _run_device_preflight_command(
    args: argparse.Namespace,
    device: dict[str, Any],
    *,
    operation: str,
    command: list[str],
) -> dict[str, Any]:
    """Run one device mutation through the bounded, logged process-group runner."""

    secret_values = _device_preflight_secret_values()
    try:
        result = run_command(
            command,
            cwd=REPO_ROOT,
            env=_device_preflight_command_environment(),
            timeout_seconds=_DEVICE_PREFLIGHT_COMMAND_TIMEOUT_SECONDS,
            log_path=_device_preflight_log_path(
                args,
                device,
                operation=operation,
            ),
            secret_values=secret_values,
        )
    except Exception as error:
        raise _device_preflight_failure(operation) from error
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("exitCode"), int)
        or type(result.get("timedOut")) is not bool
        or not isinstance(result.get("outputSummary"), str)
    ):
        raise _device_preflight_failure(operation)
    result["outputSummary"] = _redact_text(result["outputSummary"], secret_values)
    return result


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
    command_environment = _device_preflight_command_environment()
    home_value = str(command_environment.get("HOME") or "").strip()
    adb = resolve_android_debug_bridge(
        environ=command_environment,
        home_dir=Path(home_value) if home_value else Path("/__qwq_missing_home__"),
    )
    device_id = str(device.get("id", "")).strip()
    if not adb:
        raise _device_preflight_failure("android-reverse-adb-resolution")
    if not device_id:
        raise _device_preflight_failure("android-reverse-device-resolution")
    base_urls = _effective_base_urls_for_device(args, device)
    ports: set[int] = set()
    for value in base_urls.values():
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"https", "wss"} or not parsed.hostname:
            continue
        ports.add(parsed.port or 443)
    if not ports:
        raise _device_preflight_failure("android-reverse-port-resolution")
    mappings: list[dict[str, Any]] = []
    for port in sorted(ports):
        command = [
            adb,
            "-s",
            device_id,
            "reverse",
            f"tcp:{port}",
            f"tcp:{port}",
        ]
        result = _run_device_preflight_command(
            args,
            device,
            operation=f"android-reverse-{port}",
            command=command,
        )
        if result["exitCode"] != 0:
            raise _device_preflight_failure(
                f"android-reverse-{port}",
                result=result,
            )
        mapping: dict[str, Any] = {"devicePort": port, "hostPort": port}
        if result.get("logPath"):
            mapping["logPath"] = str(result["logPath"])
        mappings.append(mapping)
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
    is_ios = target_platform == "ios"
    if not _is_local_target(args.env_name) or not (is_android or is_ios):
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
        platform=(
            "android" if is_android else "ios-simulator" if emulator else "ios-physical"
        ),
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
    emulator = _canonical_emulator_flag(device)
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
        platform=(
            "android" if is_android else "ios-simulator" if emulator else "ios-physical"
        ),
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
        raise _device_preflight_failure("release-uat-device-resolution")

    # patrol UAT 以 Flutter Debug 构建执行，App 身份必须按环境 × BuildMode 推导，
    # 与安装制品的 applicationId/bundle id 单轨一致，禁止字面值。
    runtime_env = str(getattr(args, "runtime_env", "") or "").strip() or (
        _runtime_env_for_alias(args.env_name)
    )
    reset_rows: list[dict[str, Any]] = []
    if target == "ios":
        for index, bundle_id in enumerate(
            ios_release_uat_bundle_ids(runtime_env, "debug"),
            start=1,
        ):
            command = (
                ["xcrun", "simctl", "uninstall", device_id, bundle_id]
                if emulator
                else [
                    "xcrun", "devicectl", "device", "uninstall", "app",
                    "--device", device_id, bundle_id,
                ]
            )
            result = _run_device_preflight_command(
                args,
                device,
                operation=f"ios-uninstall-{index}",
                command=command,
            )
            if result["timedOut"] is True or result["exitCode"] == 124:
                raise _device_preflight_failure(
                    f"ios-uninstall-{index}",
                    result=result,
                )
            output = str(result["outputSummary"]).strip()
            absent = (
                "not installed" in output.lower() or "no such file" in output.lower()
            )
            if result["exitCode"] != 0 and not absent:
                raise _device_preflight_failure(
                    f"ios-uninstall-{index}",
                    result=result,
                )
            row: dict[str, Any] = {
                "bundleId": bundle_id,
                "exitCode": result["exitCode"],
                "alreadyAbsent": result["exitCode"] != 0,
            }
            if result.get("logPath"):
                row["logPath"] = str(result["logPath"])
            reset_rows.append(row)
    elif target.startswith("android"):
        command_environment = _device_preflight_command_environment()
        home_value = str(command_environment.get("HOME") or "").strip()
        adb = resolve_android_debug_bridge(
            environ=command_environment,
            home_dir=(
                Path(home_value) if home_value else Path("/__qwq_missing_home__")
            ),
        )
        if adb is None:
            raise _device_preflight_failure("android-reset-adb-resolution")
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
        package_path = _run_device_preflight_command(
            args,
            device,
            operation="android-pm-path",
            command=package_path_command,
        )
        package_path_output = str(package_path["outputSummary"]).strip()
        installed = package_path["exitCode"] == 0 and package_path_output.startswith(
            "package:"
        )
        if not installed and package_path["exitCode"] not in (0, 1):
            raise _device_preflight_failure(
                "android-pm-path",
                result=package_path,
            )
        clear_result: dict[str, Any] | None = None
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
            clear_result = _run_device_preflight_command(
                args,
                device,
                operation="android-pm-clear",
                command=clear_command,
            )
            clear_output = str(clear_result["outputSummary"]).strip()
            if clear_result["exitCode"] != 0 or "success" not in clear_output.lower():
                raise _device_preflight_failure(
                    "android-pm-clear",
                    result=clear_result,
                )
        row = {
            "package": android_uat_package,
            "exitCode": 0,
            "alreadyAbsent": not installed,
        }
        terminal_result = clear_result or package_path
        if terminal_result.get("logPath"):
            row["logPath"] = str(terminal_result["logPath"])
        reset_rows.append(row)
    else:
        raise _device_preflight_failure("release-uat-platform-resolution")
    return {
        "status": "reset",
        "reason": "release-bound-cold-start",
        "applications": reset_rows,
    }

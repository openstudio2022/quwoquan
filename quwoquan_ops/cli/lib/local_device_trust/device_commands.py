"""受管设备发现、命令执行与 receipt 读写原语（逐字搬移）。

``_require_success`` / ``_receipt_path`` 是测试的 patch 锚点，包内消费
一律经 ``_pkg.`` 属性访问；``ssl`` 保持为包属性以维持
``patch.object(local_device_trust.ssl, ...)`` 语义。
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import quwoquan_ops.cli.lib.local_device_trust as _pkg

from ..environment_topology import get_target, load_environment_topology
from ..output_paths import target_process_dir
from .constants import SCHEMA, _ROOT, _SAFE
from .errors import LocalDeviceTrustError


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run(argv: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LocalDeviceTrustError(f"device trust command failed: {argv[0]}") from exc


def _require_success(
    argv: list[str],
    *,
    action: str,
    timeout: int = 90,
) -> subprocess.CompletedProcess[str]:
    result = _run(argv, timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise LocalDeviceTrustError(
            f"{action} failed"
            + (f": {detail[:500]}" if detail else f" (exit={result.returncode})")
        )
    return result


def _root_fingerprint(path: Path) -> str:
    try:
        pem = path.read_text(encoding="ascii")
        der = ssl.PEM_cert_to_DER_cert(pem)
    except (OSError, UnicodeError, ValueError) as exc:
        raise LocalDeviceTrustError(
            "local-managed root certificate is invalid"
        ) from exc
    return hashlib.sha256(der).hexdigest().upper()


def _receipt_path(target: str, platform_name: str, device: str) -> Path:
    segment = _SAFE.sub("-", device).strip("-") or "device"
    return (
        target_process_dir(target) / "device-trust" / platform_name / f"{segment}.json"
    )


def _read_receipt(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LocalDeviceTrustError(
            f"device trust receipt is unreadable: {exc}"
        ) from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise LocalDeviceTrustError("device trust receipt schema mismatch")
    return value


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _booted_ios_simulators() -> dict[str, dict[str, Any]]:
    result = _pkg._require_success(
        ["xcrun", "simctl", "list", "devices", "booted", "--json"],
        action="iOS Simulator discovery",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise LocalDeviceTrustError(
            "iOS Simulator discovery returned invalid JSON"
        ) from exc
    discovered: dict[str, dict[str, Any]] = {}
    for devices in (payload.get("devices") or {}).values():
        if not isinstance(devices, list):
            continue
        for device in devices:
            if (
                isinstance(device, dict)
                and device.get("state") == "Booted"
                and device.get("isAvailable") is not False
            ):
                discovered[str(device.get("udid") or "")] = device
    return {key: value for key, value in discovered.items() if key}


def resolve_managed_device(platform_name: str, device: str = "") -> str:
    requested = str(device or "").strip()
    if platform_name == "ios-simulator":
        devices = _booted_ios_simulators()
        if requested:
            if requested not in devices:
                raise LocalDeviceTrustError(
                    f"selected device is not a booted iOS Simulator: {requested}"
                )
            return requested
        if len(devices) != 1:
            raise LocalDeviceTrustError(
                "select exactly one booted iOS Simulator with an explicit device id"
            )
        return next(iter(devices))
    if platform_name == "android-emulator":
        result = _pkg._require_success(
            ["adb", "devices"],
            action="Android Emulator discovery",
        )
        devices = [
            line.split("\t", 1)[0]
            for line in result.stdout.splitlines()
            if "\tdevice" in line and line.split("\t", 1)[0].startswith("emulator-")
        ]
        if requested:
            if requested not in devices:
                raise LocalDeviceTrustError(
                    f"selected device is not a connected Android Emulator: {requested}"
                )
            return requested
        if len(devices) != 1:
            raise LocalDeviceTrustError(
                "select exactly one Android Emulator with an explicit device id"
            )
        return devices[0]
    raise LocalDeviceTrustError(f"unsupported managed device platform: {platform_name}")


def _target_probe_url(target: str) -> str:
    topology = load_environment_topology()
    row = get_target(topology, target)
    api = str((row.get("publicBases") or {}).get("api") or "").rstrip("/")
    if not api.startswith("https://"):
        raise LocalDeviceTrustError("local target has no canonical HTTPS API URL")
    return api + "/healthz"

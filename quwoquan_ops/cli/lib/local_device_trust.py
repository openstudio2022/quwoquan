"""Install and prove target-scoped local CA trust on managed simulators."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import ssl
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.output_paths import target_cache_dir, target_process_dir
from quwoquan_ops.cli.lib.public_domain_tls import (
    root_certificate_path,
    verify_certificate,
)


SCHEMA = "stackctl-local-device-system-trust"
PLATFORMS = ("ios-simulator", "android-emulator")
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_ROOT = Path(__file__).resolve().parents[3]


class LocalDeviceTrustError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run(argv: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
        raise LocalDeviceTrustError("local-managed root certificate is invalid") from exc
    return hashlib.sha256(der).hexdigest().upper()


def _receipt_path(target: str, platform_name: str, device: str) -> Path:
    segment = _SAFE.sub("-", device).strip("-") or "device"
    return (
        target_process_dir(target)
        / "device-trust"
        / platform_name
        / f"{segment}.json"
    )


def _read_receipt(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LocalDeviceTrustError(f"device trust receipt is unreadable: {exc}") from exc
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
    result = _require_success(
        ["xcrun", "simctl", "list", "devices", "booted", "--json"],
        action="iOS Simulator discovery",
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise LocalDeviceTrustError("iOS Simulator discovery returned invalid JSON") from exc
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
        result = _require_success(
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


def _ios_probe_binary(target: str) -> Path:
    source = (
        _ROOT
        / "quwoquan_ops/cli/tools/ios_simulator_system_trust_probe.swift"
    )
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    binary = target_cache_dir(target) / "device-trust" / f"ios-probe-{source_digest}"
    if binary.is_file():
        return binary
    binary.parent.mkdir(parents=True, exist_ok=True)
    sdk = _require_success(
        ["xcrun", "--sdk", "iphonesimulator", "--show-sdk-path"],
        action="iOS Simulator SDK resolution",
    ).stdout.strip()
    architecture = "arm64" if platform.machine() == "arm64" else "x86_64"
    _require_success(
        [
            "xcrun",
            "--sdk",
            "iphonesimulator",
            "swiftc",
            "-sdk",
            sdk,
            "-target",
            f"{architecture}-apple-ios17.0-simulator",
            str(source),
            "-o",
            str(binary),
        ],
        action="iOS system-trust probe build",
        timeout=180,
    )
    return binary


def _probe_ios_system_trust(target: str, device: str) -> str:
    probe = _ios_probe_binary(target)
    result = _require_success(
        [
            "xcrun",
            "simctl",
            "spawn",
            device,
            str(probe),
            _target_probe_url(target),
        ],
        action="iOS Simulator default system-trust HTTPS probe",
        timeout=40,
    )
    if "system-trust-ok" not in result.stdout:
        raise LocalDeviceTrustError("iOS system-trust probe emitted no success receipt")
    return result.stdout.strip()


def _install_ios(target: str, device: str, root: Path) -> str:
    _require_success(
        ["xcrun", "simctl", "keychain", device, "add-root-cert", str(root)],
        action="iOS Simulator root certificate installation",
    )
    return _probe_ios_system_trust(target, device)


def _android_property(device: str, name: str) -> str:
    return _require_success(
        ["adb", "-s", device, "shell", "getprop", name],
        action=f"Android property {name}",
    ).stdout.strip()


def _install_android(target: str, device: str, root: Path) -> str:
    if _android_property(device, "ro.kernel.qemu") != "1":
        raise LocalDeviceTrustError("physical Android devices are not eligible for local CA trust")
    api = int(_android_property(device, "ro.build.version.sdk") or "0")
    if api >= 34:
        raise LocalDeviceTrustError(
            "Android 14+ requires a managed AVD image with the CA provisioned in the Conscrypt trust store"
        )
    subject_hash = _require_success(
        ["openssl", "x509", "-in", str(root), "-subject_hash_old", "-noout"],
        action="Android CA subject hash",
    ).stdout.strip()
    if re.fullmatch(r"[0-9a-fA-F]{8}", subject_hash) is None:
        raise LocalDeviceTrustError("Android CA subject hash is invalid")
    remote = f"/system/etc/security/cacerts/{subject_hash}.0"
    _require_success(["adb", "-s", device, "root"], action="Android Emulator adb root")
    _require_success(["adb", "-s", device, "wait-for-device"], action="Android Emulator wait")
    _require_success(["adb", "-s", device, "remount"], action="Android Emulator remount")
    staged = f"/data/local/tmp/{subject_hash}.0"
    _require_success(["adb", "-s", device, "push", str(root), staged], action="Android CA push")
    _require_success(
        [
            "adb",
            "-s",
            device,
            "shell",
            "cp",
            staged,
            remote,
        ],
        action="Android CA system installation",
    )
    _require_success(
        ["adb", "-s", device, "shell", "chmod", "0644", remote],
        action="Android CA permissions",
    )
    _require_success(
        ["adb", "-s", device, "shell", "rm", "-f", staged],
        action="Android CA staging cleanup",
    )
    return remote


def install_device_trust(
    *,
    target: str,
    platform_name: str,
    device: str = "",
    lease_id: str = "",
) -> dict[str, Any]:
    verify_certificate(target)
    selected = resolve_managed_device(platform_name, device)
    root = root_certificate_path(target)
    fingerprint = _root_fingerprint(root)
    path = _receipt_path(target, platform_name, selected)
    previous = _read_receipt(path)
    leases = list(previous.get("leases") or []) if previous else []
    normalized_lease = str(lease_id or "").strip() or uuid4().hex
    if normalized_lease not in leases:
        leases.append(normalized_lease)
    proof = (
        _install_ios(target, selected, root)
        if platform_name == "ios-simulator"
        else _install_android(target, selected, root)
    )
    payload = {
        "schema": SCHEMA,
        "target": target,
        "platform": platform_name,
        "device": selected,
        "rootFingerprintSha256": fingerprint,
        "systemTrustStore": True,
        "verification": proof,
        "leases": sorted(leases),
        "status": "installed",
        "updatedAt": _utc_now(),
    }
    _write_receipt(path, payload)
    return {**payload, "receipt": str(path), "leaseId": normalized_lease}


def verify_device_trust(
    *,
    target: str,
    platform_name: str,
    device: str,
) -> dict[str, Any]:
    selected = resolve_managed_device(platform_name, device)
    path = _receipt_path(target, platform_name, selected)
    receipt = _read_receipt(path)
    if receipt is None:
        raise LocalDeviceTrustError("device system-trust receipt is missing")
    root = root_certificate_path(target)
    fingerprint = _root_fingerprint(root)
    if (
        receipt.get("target") != target
        or receipt.get("platform") != platform_name
        or receipt.get("device") != selected
        or receipt.get("rootFingerprintSha256") != fingerprint
        or receipt.get("status") != "installed"
    ):
        raise LocalDeviceTrustError("device system-trust receipt identity mismatch")
    proof = (
        _probe_ios_system_trust(target, selected)
        if platform_name == "ios-simulator"
        else str(receipt.get("verification") or "")
    )
    payload = {**receipt, "verification": proof, "verifiedAt": _utc_now()}
    _write_receipt(path, payload)
    return {**payload, "receipt": str(path)}


def release_device_trust(
    *,
    target: str,
    platform_name: str,
    device: str,
    lease_id: str,
) -> dict[str, Any]:
    selected = resolve_managed_device(platform_name, device)
    path = _receipt_path(target, platform_name, selected)
    receipt = _read_receipt(path)
    if receipt is None:
        raise LocalDeviceTrustError("device system-trust receipt is missing")
    leases = [value for value in receipt.get("leases") or [] if value != lease_id]
    payload = {
        **receipt,
        "leases": leases,
        "status": "installed" if leases else "managed-root-retained",
        "updatedAt": _utc_now(),
    }
    _write_receipt(path, payload)
    return {
        **payload,
        "receipt": str(path),
        "revocation": (
            "lease-released"
            if leases
            else "root retained; simctl has no certificate-scoped removal API"
        ),
    }

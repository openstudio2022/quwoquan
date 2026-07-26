"""本地环境 target 的根证书解析与 iOS Simulator 信任安装边界。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.output_paths import certificate_export_dir


LOCAL_TLS_TARGETS = frozenset(
    {"alpha-local", "beta-local", "gamma-local", "prod-sim"}
)
TARGET_ALIASES = {
    "alpha": "alpha-local",
    "alpha-local": "alpha-local",
    "beta": "beta-local",
    "beta-local": "beta-local",
    "gamma": "gamma-local",
    "local-gamma": "gamma-local",
    "gamma-local": "gamma-local",
    "prod": "prod-sim",
    "prod-sim": "prod-sim",
}
LOCAL_TRUST_ROOT_RELATIVE_PATHS = (
    Path("root.crt"),
    Path("object-storage") / "ca.crt",
)
LOCAL_OBJECT_STORAGE_TLS_TARGETS = frozenset(
    {"alpha-local", "beta-local", "gamma-local"}
)
LOCAL_APP_TRUST_BUNDLE_NAME = "app-local-trust-bundle.crt"


class LocalTargetTlsError(RuntimeError):
    """本地 target 的 TLS preflight 不能满足。"""


def normalize_local_tls_target(target_name: str) -> str:
    normalized = TARGET_ALIASES.get(target_name.strip().lower(), "")
    if normalized not in LOCAL_TLS_TARGETS:
        raise LocalTargetTlsError(
            "GATE_BLOCK: local TLS target must be one of "
            f"{', '.join(sorted(LOCAL_TLS_TARGETS))}; got {target_name!r}"
        )
    return normalized


def resolve_local_target_root_ca(target_name: str) -> Path:
    """返回 target 唯一规范路径的 root.crt，缺失时 fail-closed。"""

    target = normalize_local_tls_target(target_name)
    cert_path = certificate_export_dir(target) / "root.crt"
    if not cert_path.is_file():
        raise LocalTargetTlsError(
            "GATE_BLOCK: local root CA missing for "
            f"{target}: {cert_path}. Start the target stack before device UAT."
        )
    return cert_path


def resolve_local_target_trust_roots(target_name: str) -> tuple[Path, ...]:
    """返回本地 App 数据平面需要信任的全部现有根证书。"""

    target = normalize_local_tls_target(target_name)
    cert_dir = certificate_export_dir(target)
    gateway_root = resolve_local_target_root_ca(target)
    object_storage_root = cert_dir / LOCAL_TRUST_ROOT_RELATIVE_PATHS[1]
    if target in LOCAL_OBJECT_STORAGE_TLS_TARGETS and not object_storage_root.is_file():
        raise LocalTargetTlsError(
            "GATE_BLOCK: local object-storage CA missing for "
            f"{target}: {object_storage_root}. Start the complete target stack "
            "before device UAT."
        )
    roots = [gateway_root]
    roots.extend(
        cert_dir / relative_path
        for relative_path in LOCAL_TRUST_ROOT_RELATIVE_PATHS[1:]
        if (cert_dir / relative_path).is_file()
    )
    return tuple(roots)


def materialize_local_target_trust_bundle(target_name: str) -> Path:
    """原子生成供 Dart/Android 网络栈消费的本地 CA PEM bundle。"""

    target = normalize_local_tls_target(target_name)
    cert_dir = certificate_export_dir(target)
    roots = resolve_local_target_trust_roots(target)
    payload_parts: list[bytes] = []
    for cert_path in roots:
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(cafile=str(cert_path))
            cert_bytes = cert_path.read_bytes().rstrip()
        except (OSError, ssl.SSLError) as exc:
            raise LocalTargetTlsError(
                "GATE_BLOCK: invalid local trust root for "
                f"{target}: {cert_path}: {exc}"
            ) from exc
        payload_parts.append(cert_bytes + b"\n")
    payload = b"".join(payload_parts)
    destination = cert_dir / LOCAL_APP_TRUST_BUNDLE_NAME
    if destination.is_file() and destination.read_bytes() == payload:
        return destination
    cert_dir.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{LOCAL_APP_TRUST_BUNDLE_NAME}.",
        dir=cert_dir,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(0o644)
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return destination


def install_ios_simulator_root_ca(
    target_name: str,
    simulator_udid: str,
    *,
    xcrun_path: str | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """向指定 Simulator 安装全部本地根证书；绝不猜测 booted 目标。"""

    target = normalize_local_tls_target(target_name)
    device_id = simulator_udid.strip()
    if not device_id:
        raise LocalTargetTlsError(
            "GATE_BLOCK: an explicit iOS Simulator UDID is required for local TLS trust"
        )
    cert_paths = resolve_local_target_trust_roots(target)
    executable = xcrun_path or shutil.which("xcrun")
    if not executable:
        raise LocalTargetTlsError(
            "GATE_BLOCK: xcrun is unavailable; cannot install the local root CA "
            f"for {target} on Simulator {device_id}"
        )
    for cert_path in cert_paths:
        result = command_runner(
            [
                executable,
                "simctl",
                "keychain",
                device_id,
                "add-root-cert",
                str(cert_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            detail = ((result.stderr or result.stdout) or "unknown simctl failure").strip()
            raise LocalTargetTlsError(
                "GATE_BLOCK: failed to install local root CA "
                f"{cert_path} for {target} on Simulator {device_id}: {detail}"
            )
    return {
        "status": "installed",
        "target": target,
        "deviceId": device_id,
        "certPath": str(cert_paths[0]),
        "certPaths": [str(path) for path in cert_paths],
    }


def is_ios_simulator_device(
    device_id: str,
    *,
    xcrun_path: str | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    """仅识别明确列在 simctl inventory 中的 Simulator UDID。"""

    selected = device_id.strip()
    executable = xcrun_path or shutil.which("xcrun")
    if not selected or not executable:
        return False
    result = command_runner(
        [executable, "simctl", "list", "devices", "--json"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False
    devices = payload.get("devices")
    if not isinstance(devices, dict):
        return False
    return any(
        isinstance(device, dict) and str(device.get("udid") or "").strip() == selected
        for runtime_devices in devices.values()
        if isinstance(runtime_devices, list)
        for device in runtime_devices
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    resolve_parser = subparsers.add_parser("resolve-root-ca")
    resolve_parser.add_argument("--target", required=True)
    bundle_parser = subparsers.add_parser("materialize-app-trust-bundle")
    bundle_parser.add_argument("--target", required=True)
    install_parser = subparsers.add_parser("install-ios-simulator-ca")
    install_parser.add_argument("--target", required=True)
    install_parser.add_argument("--simulator-udid", required=True)
    simulator_parser = subparsers.add_parser("is-ios-simulator")
    simulator_parser.add_argument("--device-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "resolve-root-ca":
            payload = {
                "target": normalize_local_tls_target(args.target),
                "certPath": str(resolve_local_target_root_ca(args.target)),
            }
        elif args.command == "materialize-app-trust-bundle":
            bundle_path = materialize_local_target_trust_bundle(args.target)
            payload = {
                "target": normalize_local_tls_target(args.target),
                "certPath": str(bundle_path),
                "certPaths": [
                    str(path) for path in resolve_local_target_trust_roots(args.target)
                ],
            }
        elif args.command == "install-ios-simulator-ca":
            payload = install_ios_simulator_root_ca(
                args.target,
                args.simulator_udid,
            )
        else:
            payload = {
                "deviceId": args.device_id.strip(),
                "isSimulator": is_ios_simulator_device(args.device_id),
            }
    except LocalTargetTlsError as exc:
        print(str(exc))
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload.get("isSimulator", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""本地环境 target 的根证书解析与 iOS Simulator 信任安装边界。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

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


def install_ios_simulator_root_ca(
    target_name: str,
    simulator_udid: str,
    *,
    xcrun_path: str | None = None,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, str]:
    """向指定 Simulator 安装根证书；绝不根据 booted 状态猜测目标。"""

    target = normalize_local_tls_target(target_name)
    device_id = simulator_udid.strip()
    if not device_id:
        raise LocalTargetTlsError(
            "GATE_BLOCK: an explicit iOS Simulator UDID is required for local TLS trust"
        )
    cert_path = resolve_local_target_root_ca(target)
    executable = xcrun_path or shutil.which("xcrun")
    if not executable:
        raise LocalTargetTlsError(
            "GATE_BLOCK: xcrun is unavailable; cannot install the local root CA "
            f"for {target} on Simulator {device_id}"
        )
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
            f"for {target} on Simulator {device_id}: {detail}"
        )
    return {
        "status": "installed",
        "target": target,
        "deviceId": device_id,
        "certPath": str(cert_path),
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

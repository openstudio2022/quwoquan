"""stackctl `device-trust` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；业务逻辑保持在
`quwoquan_ops/cli/lib/**`。stackctl 命名空间符号一律经函数内延迟导入
`_stackctl` 属性访问，保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    device_trust_parser = subparsers.add_parser(
        "device-trust",
        help="安装并验证受管 Simulator/Emulator 的 local-managed 系统信任",
    )
    device_trust_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    device_trust_parser.add_argument(
        "--platform",
        choices=("ios-simulator", "android-emulator"),
        required=True,
    )
    device_trust_parser.add_argument(
        "--action",
        choices=("install", "verify", "release"),
        required=True,
    )
    device_trust_parser.add_argument("--device", default="")
    device_trust_parser.add_argument("--lease-id", default="")
    device_trust_parser.add_argument(
        "--defer-endpoint-probe",
        action="store_true",
        help=(
            "仅安装 Simulator 系统根证书，不探测受管端点；"
            "只允许 App 启动入口，环境/UAT verify 仍须端点成功"
        ),
    )
    device_trust_parser.add_argument(
        "--allow-unprovisioned-system-trust",
        action="store_true",
        help=(
            "只允许 Android 直接 App 启动在不可写系统 CA 的 Emulator 上进入降级 Shell；"
            "不会产生 system-trust/UAT 通过证据"
        ),
    )
    device_trust_parser.add_argument("--report-dir", default=argparse.SUPPRESS)


def command_device_trust(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    env_name = str(
        _stackctl.get_target(_stackctl.load_environment_topology(), args.target)["env"]
    )
    report_dir = _stackctl.resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _stackctl._start_timing()
    defer_endpoint_probe = bool(getattr(args, "defer_endpoint_probe", False))
    allow_unprovisioned_system_trust = bool(
        getattr(args, "allow_unprovisioned_system_trust", False)
    )
    try:
        if args.action == "install":
            evidence = _stackctl.install_device_trust(
                target=args.target,
                platform_name=args.platform,
                device=args.device,
                lease_id=args.lease_id,
                endpoint_probe=not defer_endpoint_probe,
                allow_unprovisioned_system_trust=allow_unprovisioned_system_trust,
            )
        elif args.action == "verify":
            if defer_endpoint_probe or allow_unprovisioned_system_trust:
                raise _stackctl.LocalDeviceTrustError(
                    "startup-only trust flags are valid only for device-trust install"
                )
            if not str(args.device or "").strip():
                raise _stackctl.LocalDeviceTrustError(
                    "device-trust verify requires --device"
                )
            evidence = _stackctl.verify_device_trust(
                target=args.target,
                platform_name=args.platform,
                device=args.device,
            )
        else:
            if defer_endpoint_probe or allow_unprovisioned_system_trust:
                raise _stackctl.LocalDeviceTrustError(
                    "startup-only trust flags are valid only for device-trust install"
                )
            if not str(args.device or "").strip() or not str(args.lease_id or "").strip():
                raise _stackctl.LocalDeviceTrustError(
                    "device-trust release requires --device and --lease-id"
                )
            evidence = _stackctl.release_device_trust(
                target=args.target,
                platform_name=args.platform,
                device=args.device,
                lease_id=args.lease_id,
            )
        exit_code = 0
        details = [
            f"device={evidence['device']}",
            f"rootFingerprintSha256={evidence['rootFingerprintSha256']}",
            f"receipt={evidence['receipt']}",
        ]
    except (
        _stackctl.LocalDeviceTrustError,
        _stackctl.PublicDomainTlsError,
        OSError,
        ValueError,
    ) as exc:
        evidence = {}
        exit_code = 2
        details = [str(exc)]
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    status = (
        "launch_degraded"
        if exit_code == 0 and evidence.get("systemTrustStore") is False
        else "passed"
        if exit_code == 0
        else "gate_block"
    )
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "device-trust",
            "target": args.target,
            "platform": args.platform,
            "action": args.action,
            "status": status,
            "evidence": evidence,
            "details": details,
            **timing,
        },
    )
    return {
        "exitCode": exit_code,
        "summary": (
            f"stackctl device-trust {args.action} {status} for {args.target}"
        ),
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        "evidence": evidence,
        **timing,
    }

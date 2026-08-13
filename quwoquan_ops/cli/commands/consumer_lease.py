"""stackctl `consumer-lease` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；业务逻辑保持在
`quwoquan_ops/cli/lib/**`。stackctl 命名空间符号一律经函数内延迟导入
`_stackctl` 属性访问，保持 monkeypatch 语义并避免顶层循环 import。
注意：`_consumer_lease_down_gate` 属 down 域，仍留在 stackctl.py。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    consumer_lease_parser = subparsers.add_parser(
        "consumer-lease",
        help="protect a local runtime while a true-device app consumes it",
    )
    consumer_lease_parser.add_argument(
        "action",
        choices=("acquire", "release", "status"),
    )
    consumer_lease_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local", "prod-sim"),
        required=True,
    )
    consumer_lease_parser.add_argument("--device", default="")
    consumer_lease_parser.add_argument("--consumer", default="flutter-run")
    consumer_lease_parser.add_argument(
        "--platform",
        choices=("android", "ios-simulator"),
        default="android",
    )
    consumer_lease_parser.add_argument(
        "--package-name",
        default="com.quwoquan.quwoquan_app",
    )
    consumer_lease_parser.add_argument("--bundle-id", default="")
    consumer_lease_parser.add_argument(
        "--ports",
        default="17000,17010,17100",
        help="comma-separated adb reverse ports",
    )
    consumer_lease_parser.add_argument(
        "--build-grace-seconds",
        type=int,
        default=_stackctl.DEFAULT_BUILD_GRACE_SECONDS,
    )
    consumer_lease_parser.add_argument("--handoff-digest", default="")
    consumer_lease_parser.add_argument("--release-id", default="")
    consumer_lease_parser.add_argument("--manifest-digest", default="")
    consumer_lease_parser.add_argument("--readiness-receipt-digest", default="")


def command_consumer_lease(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    action = str(args.action)
    target = str(args.target)
    device = str(getattr(args, "device", "") or "").strip()
    consumer = str(getattr(args, "consumer", "flutter-run") or "flutter-run").strip()
    platform = str(getattr(args, "platform", "android") or "android").strip()
    if action in {"acquire", "release"} and not device:
        return {
            "exitCode": 2,
            "summary": f"consumer-lease {action} requires --device",
            "details": ["select one connected Android device or booted iOS Simulator"],
        }
    try:
        if action == "acquire":
            ports = [
                int(value.strip())
                for value in str(args.ports).split(",")
                if value.strip()
            ]
            with _stackctl._local_stack_operation_lock(target):
                application_id = str(args.package_name)
                if platform == "ios-simulator":
                    application_id = str(getattr(args, "bundle_id", "") or "").strip()
                    if not application_id:
                        raise ValueError("--bundle-id is required for ios-simulator")
                lease = _stackctl.acquire_consumer_lease(
                    target=target,
                    device=device,
                    consumer=consumer,
                    package_name=application_id,
                    ports=ports,
                    platform=platform,
                    handoff_digest=str(getattr(args, "handoff_digest", "") or ""),
                    release_id=str(getattr(args, "release_id", "") or ""),
                    manifest_digest=str(
                        getattr(args, "manifest_digest", "") or ""
                    ),
                    readiness_receipt_digest=str(
                        getattr(args, "readiness_receipt_digest", "") or ""
                    ),
                    build_grace_seconds=int(args.build_grace_seconds),
                )
            return {
                "exitCode": 0,
                "summary": f"consumer lease acquired for {target}",
                "details": [
                    f"device={device}",
                    f"platform={platform}",
                    f"consumer={consumer}",
                    f"ports={','.join(str(port) for port in ports) or 'none'}",
                    f"leaseId={lease['leaseId']}",
                    f"lease={_stackctl.relpath(Path(str(lease['path'])))}",
                ],
                "lease": lease,
            }
        if action == "release":
            with _stackctl._local_stack_operation_lock(target):
                released = _stackctl.release_consumer_lease(
                    target=target,
                    device=device,
                    consumer=consumer,
                )
            return {
                "exitCode": 0,
                "summary": f"consumer lease released for {target}",
                "details": [
                    f"device={device}",
                    f"consumer={consumer}",
                    f"existed={str(released).lower()}",
                ],
            }
        leases = _stackctl.active_consumer_leases(target)
        return {
            "exitCode": 0,
            "summary": f"consumer lease status for {target}",
            "details": [
                (
                    f"device={lease.get('device')} consumer={lease.get('consumer')} "
                    f"platform={lease.get('platform', 'android')} "
                    f"state={lease.get('state')} detail={lease.get('detail')}"
                )
                for lease in leases
            ]
            or ["no active consumer lease"],
            "leases": leases,
        }
    except (RuntimeError, ValueError) as exc:
        return {
            "exitCode": 2,
            "summary": f"consumer-lease {action} is GATE_BLOCK for {target}",
            "details": [str(exc)],
        }

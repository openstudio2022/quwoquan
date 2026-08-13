"""stackctl `prod-hosted-plan` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；prod-hosted 拓扑
执行计划仍由 `quwoquan_ops/cli/prod/prod_hosted_topology.py` 渲染。
stackctl 命名空间符号（`run` / `_start_timing` / `_finish_timing`）
一律经函数内延迟导入 `_stackctl` 属性访问，保持 monkeypatch 语义
并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    hosted_plan_parser = subparsers.add_parser(
        "prod-hosted-plan",
        help="render the read-only prod-hosted host/instance/replica execution plan",
    )
    hosted_plan_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    hosted_plan_parser.add_argument(
        "--deployment-instance",
        choices=("prevalidate", "gray", "prod"),
        required=True,
    )
    hosted_plan_parser.add_argument(
        "--plane",
        action="append",
        choices=("service", "edge"),
    )
    hosted_plan_parser.add_argument("--host-id", action="append", default=[])
    hosted_plan_parser.add_argument("--ssh-host", default="")
    hosted_plan_parser.add_argument(
        "--require-release-redundancy",
        action="store_true",
        help=(
            "GATE_BLOCK unless the complete formal gray/prod service+edge "
            "inventory has two real hosts and replicas per plane"
        ),
    )


def command_prod_hosted_plan(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    started_monotonic, started_at = _stackctl._start_timing()
    argv = [
        "python3",
        "quwoquan_ops/cli/prod/prod_hosted_topology.py",
        "--instance",
        args.deployment_instance,
    ]
    for plane in args.plane or []:
        argv.extend(["--plane", plane])
    for host_id in args.host_id or []:
        argv.extend(["--host-id", host_id])
    if args.ssh_host:
        argv.extend(["--ssh-host", args.ssh_host])
    if args.require_release_redundancy:
        argv.append("--require-release-redundancy")
    result = _stackctl.run(argv)
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    if result.returncode != 0:
        return {
            "exitCode": result.returncode,
            "summary": "stackctl prod-hosted plan blocked",
            "details": [result.stderr.strip() or result.stdout.strip()],
            **timing,
        }
    try:
        plan = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "exitCode": 2,
            "summary": "stackctl prod-hosted plan returned invalid JSON",
            "details": [result.stdout],
            **timing,
        }
    return {
        "exitCode": 0,
        "summary": (
            "stackctl prod-hosted plan resolved "
            f"{plan.get('replicaCount', 0)} plane replicas"
        ),
        "details": [
            f"instance={plan.get('instance')}",
            f"hosts={','.join(plan.get('hosts') or [])}",
        ],
        "deploymentPlan": plan,
        **timing,
    }

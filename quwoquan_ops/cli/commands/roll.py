"""stackctl `roll` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；本地目标的滚动重启
复用 stackctl 命名空间拥有的 `command_up` 全量启动语义。stackctl
命名空间符号一律经函数内延迟导入 `_stackctl` 属性访问，保持
monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    roll_parser = subparsers.add_parser("roll")
    roll_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    roll_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    roll_parser.add_argument("--mode", choices=("restart", "rollout"), default="restart")
    roll_parser.add_argument("--stage", default="")


def command_roll(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    started_monotonic, started_at = _stackctl._start_timing()

    if args.target in {"alpha-local", "beta-local", "gamma-local"}:
        env_map = {
            "alpha-local": "alpha",
            "beta-local": "beta",
            "gamma-local": "gamma",
        }
        nested_args = argparse.Namespace(
            command="up",
            env=env_map[args.target],
            target=args.target,
            device_id="",
            skip_app=True,
            skip_build=False,
            workload="full",
            rollout_mode="",
            output_format="json",
            report_dir=getattr(args, "report_dir", ""),
        )
        payload = _stackctl.command_up(nested_args)
        payload["summary"] = f"stackctl roll {args.mode} completed for {args.target}"
        return payload

    timing = _stackctl._finish_timing(started_monotonic, started_at)
    return {
        "exitCode": 2,
        "summary": f"stackctl roll does not support target {args.target}",
        "details": [],
        **timing,
    }

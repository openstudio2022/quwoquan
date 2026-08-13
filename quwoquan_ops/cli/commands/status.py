"""stackctl `status` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；健康检查与候选漂移
报告逻辑仍由 stackctl 命名空间拥有（`command_health` /
`_candidate_workspace_report` 等），命令函数体内一律经函数内延迟导入
`_stackctl` 属性访问，保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    status_parser.add_argument("--target", choices=_stackctl.TARGETS, required=True)
    status_parser.add_argument(
        "--currentness",
        action="store_true",
        help="explicitly compare the active candidate with its declared source closure",
    )


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    scope = _stackctl._current_runtime_health_scope(args.target)
    health_args = argparse.Namespace(
        command="health",
        target=args.target,
        scope=scope,
        read_only=True,
        output_format=getattr(args, "output_format", "text"),
        report_dir=str(_stackctl.resolve_report_dir(args, str(_stackctl.get_target(_stackctl.load_environment_topology(), args.target)["env"]), args.target)),
        request_timeout_seconds=1.0,
        retry_attempts=1,
        retry_sleep_seconds=0.0,
        deadline_epoch=int(time.time()) + 8,
    )
    result = _stackctl.command_health(health_args)
    candidate_workspace = (
        _stackctl._candidate_workspace_report(args.target, purpose="currentness")
        if getattr(args, "currentness", False)
        else _stackctl._candidate_workspace_report(args.target)
    )
    report_path = Path(health_args.report_dir) / "report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if isinstance(report, dict):
            report["candidateWorkspace"] = candidate_workspace
            _stackctl.write_json(report_path, report)
    except (OSError, json.JSONDecodeError):
        # status 的健康结果仍由 command_health 拥有；候选漂移是只读附加信息，
        # 报告文件异常不能被包装成新的运行时健康结论。
        pass
    result["candidateWorkspace"] = candidate_workspace
    return result

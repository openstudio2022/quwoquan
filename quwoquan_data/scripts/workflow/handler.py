"""qwq-data data workflow — 任务级编排入口（canonical）。

该入口只承载 workflow/run 编排壳，不新增业务逻辑；实际执行复用 `task.run`。
"""
from __future__ import annotations

import argparse

from task.run import register_run_parser


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("workflow", help="任务级 workflow 编排入口")
    sub = p.add_subparsers(dest="workflow_command")
    register_run_parser(sub)

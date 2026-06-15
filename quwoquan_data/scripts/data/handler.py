"""qwq-data data — 数据工程命令族根。"""
from __future__ import annotations

import argparse

from data.baseline import register_parser as reg_baseline
from download.handler import register_parser as reg_download
from download.research_plan import register_parser as reg_research_plan
from explore.handler import register_parser as reg_explore
from build.handler import register_parser as reg_build
from produce.handler import register_parser as reg_produce
from publish.handler import register_parser as reg_publish
from workflow.handler import register_parser as reg_workflow


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "data",
        help="数据工程命令族（explore/baseline/download/build/produce/publish/workflow）",
    )
    sub = p.add_subparsers(dest="data_command")
    reg_explore(sub)
    reg_baseline(sub)
    reg_research_plan(sub)
    reg_download(sub)
    reg_build(sub)
    reg_produce(sub)
    reg_publish(sub)
    reg_workflow(sub)

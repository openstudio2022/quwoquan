"""Public content-execution facade.

The data CLI deliberately exposes only durable end-to-end execution commands.
Stage runners and static task CRUD are implementation
details and must not become a second control plane.
"""
from __future__ import annotations

import argparse

from content.execution.preflight.handler import register_task_preflight_parser
from content.execution.recipe import register_recipe_parser
from content.execution.reliabletask_worker import (
    register_execute_object_worker_parser,
)
from content.execution.reliabletask_fleet import (
    register_reliabletask_fleet_parser,
)
from content.source.sourced_video_cli import (
    register_sourced_video_ingest_parser,
)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "task",
        help="内容执行门面：唯一 execution 工作包编排",
    )
    commands = parser.add_subparsers(dest="task_command")
    register_task_preflight_parser(commands)
    register_recipe_parser(commands)
    register_execute_object_worker_parser(commands)
    register_reliabletask_fleet_parser(commands)
    register_sourced_video_ingest_parser(commands)

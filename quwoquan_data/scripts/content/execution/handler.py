"""Public host-only content-execution CLI facade."""
from __future__ import annotations

import argparse

from content.execution.execution_supersession import register_supersede_execution_parser
from content.execution.stage_receipt_cli import register_stage_receipt_parsers
from content.execution.task_init_cli import (
    register_task_init_parser,
    register_task_init_projection_parser,
    register_task_materialize_sources_parser,
)
from content.execution.planning.work_request_cli import register_compile_intent_parser
from content.execution.terminal_evidence_precheck import register_terminal_evidence_precheck_parser
from content.homepage.homepage_media_freeze_cli import register_freeze_homepage_media_parser
from content.source.media.acquire_images_cli import register_acquire_images_parser
from content.source.media.acquire_videos_cli import register_acquire_videos_parser


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("task", help="宿主执行门面：确定性初始化、receipt 与 claim/status")
    commands = parser.add_subparsers(dest="task_command")
    register_task_init_parser(commands)
    register_task_init_projection_parser(commands)
    register_task_materialize_sources_parser(commands)
    register_compile_intent_parser(commands)
    register_stage_receipt_parsers(commands)
    register_acquire_images_parser(commands)
    register_acquire_videos_parser(commands)
    register_freeze_homepage_media_parser(commands)
    register_supersede_execution_parser(commands)
    register_terminal_evidence_precheck_parser(commands)

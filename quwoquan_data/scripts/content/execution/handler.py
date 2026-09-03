"""最小内容 execution CLI 门面。"""
from __future__ import annotations

import argparse

from content.execution.stage_receipt_cli import register_stage_receipt_parsers
from content.execution.task_init_cli import register_task_init_parser
from content.source.media.acquire_images_cli import handle_acquire_images
from content.source.media.acquire_videos_cli import handle_acquire_videos
from content.source.atomic_source_cli import register_atomic_source_parsers


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("task", help="最小 execution 内核与原子媒体命令")
    commands = parser.add_subparsers(dest="task_command")
    register_task_init_parser(commands)
    register_stage_receipt_parsers(commands)
    register_atomic_source_parsers(commands)
    images = commands.add_parser(
        "acquire-images",
        help="通过公开直链、平台支持 API 或人工文件取得研究图片",
    )
    images.add_argument("--manifest", required=True)
    images.add_argument("--manual-root")
    images.add_argument("--output-root")
    images.set_defaults(handler=handle_acquire_images)

    videos = commands.add_parser(
        "acquire-videos",
        help="通过公开直链、平台支持 API 或人工文件取得研究视频",
    )
    videos.add_argument("--manifest", required=True)
    videos.add_argument("--manual-root")
    videos.add_argument("--output-root")
    videos.set_defaults(handler=handle_acquire_videos)

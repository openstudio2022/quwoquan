"""data produce — content production by type (article/image/video)."""
from __future__ import annotations

import argparse

from _common.paths import ensure_batch_layout, batch_command_root


CONTENT_TYPES = ("article", "image", "video")


def handle_produce(args: argparse.Namespace) -> None:
    """Orchestrate produce: quality_analysis → compose → review → reverse_extract.

    All steps auto-flow within a single command invocation.
    Agent performs semantic processing at each step.

    Output: batches/{batch_id}/produce/posts/{type}/{topic_id}/
    """
    task_id = args.task
    batch_id = args.batch
    content_type = args.type

    if content_type not in CONTENT_TYPES:
        print(f"[produce] ERROR: --type must be one of {CONTENT_TYPES}")
        return

    ensure_batch_layout(task_id, batch_id)
    produce_root = batch_command_root(task_id, batch_id, "produce")

    print(f"[produce] Task: {task_id}, Batch: {batch_id}, Type: {content_type}")
    print(f"[produce] Work dir: {produce_root}")
    print(f"[produce] Steps: quality_analysis → compose → review → reverse_extract")
    print(f"[produce] Posts output: {produce_root}/posts/{content_type}/")
    print(f"[produce] Ready for Agent semantic processing.")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("produce", help="Produce content (article/image/video)")
    p.add_argument("--task", required=True, help="Task ID")
    p.add_argument("--batch", required=True, help="Batch ID")
    p.add_argument("--type", required=True, choices=CONTENT_TYPES, help="Content type")
    p.set_defaults(handler=handle_produce)
